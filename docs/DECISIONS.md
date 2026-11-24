# ARCHITECTURAL DECISION RECORDS (ADRs)

**Project:** AI-Powered Farmer Communication and Agricultural Support Automation System  
**Current Phase:** Phase 1 Stabilised Baseline  

---

## ADR-001: Retention of ChromaDB and Sentence-Transformers RAG Architecture

### Context
The existing repository includes a working document ingestion, markdown chunking, and hybrid retrieval engine in `rag/`. It uses ChromaDB (`chromadb>=1.5.0`) as a persistent vector store on SQLite and `sentence-transformers/all-MiniLM-L6-v2` with domain synonym expansion.

### Decision
We retain the existing ChromaDB and Sentence-Transformers RAG pipeline rather than replacing it with an external vector cloud service (e.g. Pinecone) or an alternative framework (e.g. LlamaIndex).

### Rationale
- The existing design achieves sub-10ms local retrieval on CPU.
- It operates offline without external API rate limits or egress charges.
- The hybrid scoring logic (combining vector similarity with domain keyword boosts) effectively solves disambiguation between similar agricultural schemes (e.g., PM-KISAN vs Kisan Credit Card).
- Mandatory Rule 5 explicitly states: *"Do not replace the existing RAG pipeline without a demonstrated technical reason."*

---

## ADR-002: Fixing HuggingFace Offline Dependency Loading in Phase 1

### Context
During Phase 0 audit testing, running `test_retrieval.py` failed because `rag/config.py` specifies `local_files_only: bool = True` for `sentence-transformers/all-MiniLM-L6-v2`, but the model snapshot is not pre-populated in the local HuggingFace cache (`~/.cache/huggingface/hub`).

### Decision
In Phase 1 (Stabilisation), we will ensure that:
1. When weights are missing locally and internet is available, the system can smoothly download or cache the model once with `local_files_only=False`.
2. A configurable environment variable `HF_MODEL_PATH` or fallback logic is introduced so the local cache path can be explicitly targeted.
3. If weights cannot be downloaded due to offline sandbox restrictions, a graceful fallback or pre-downloading script is provided.

### Rationale
- The application must be runnable and all baseline integration tests must pass cleanly.

---

## ADR-003: Migration from Excel Flatfile to Relational Database in Phase 2

### Context
The prototype currently uses an Excel workbook (`data/farmer_profiles.xlsx`) accessed via pandas as its farmer registry.
Issues identified:
- Excel provides zero transaction isolation, no ACID guarantees, and no foreign key constraints.
- High concurrent webhook traffic can result in file write locks, race conditions, or corrupted workbooks.
- Operational coordinator workflows require relational tables for CDOs, agronomists, division assignments, multi-turn conversation states, issues, and audit trails.

### Decision
In Phase 2, we will design and deploy a relational database schema using SQLAlchemy 2.0 ORM.
- **Production Engine:** PostgreSQL.
- **Local / Test Engine:** SQLite (with seamless switching via `DATABASE_URL`).
- **Excel Compatibility:** Two-way export/import tools will be provided to retain full backward compatibility with legacy Excel workflows without deleting or breaking `farmer_profiles.xlsx`.

### Rationale
- Eliminates concurrency bottlenecks.
- Enables persistent tracking of verified vs unverified agronomic fields.
- Satisfies Mandatory Rule 9: *"Use persistent storage for operational data."*

---

## ADR-004: Strict Adherence to Official Meta WhatsApp Cloud API (Graph API v21.0)

### Context
The problem statement involves monitoring farmer communications and interacting with farmers, CDOs, and agronomists. The existing codebase includes simulation files (`group_manager.py`, `simulate_whatsapp_group.py`) that mock WhatsApp groups.
However, official Meta WhatsApp Cloud API does not permit standard bot numbers to participate in user-created WhatsApp groups. Standard Cloud API endpoints only support individual 1-to-1 messaging (`recipient_type: individual`).

### Decision
- All live outgoing and incoming automated communications will strictly use the official Meta WhatsApp Cloud API (Graph API v21.0) for 1-to-1 farmer dialogues, CDO inquiries, and agronomist notifications.
- We will NOT implement unofficial scraping, web-automation (Puppeteer/Selenium on WhatsApp Web), or third-party reverse-engineered WhatsApp APIs.
- The group simulation harness will be retained as an offline testing fixture, while production communication models will be architected around direct 1-to-1 messaging and approved WhatsApp Business interactive messages/templates.

### Rationale
- Mandatory Rule 16 mandates: *"Verify official WhatsApp Business API capabilities before implementing group automation. Never rely on unofficial WhatsApp automation."*
- Unofficial automation causes phone number bans, violates Meta Terms of Service, and creates massive security and reliability liabilities.

---

## ADR-005: Conversational State Machine for Missing Agronomic Data Collection

### Context
The coordinator must collect parameters such as planting date, planting season, farm area, NPK values, and soil fertility. Farmers cannot and will not fill out a 20-field form all at once.

### Decision
In Phase 3, we will implement a session-based Conversational State Machine.
- The system will detect missing fields from the farmer's persistent profile.
- When an interaction occurs, the agent answers the farmer's immediate question first to provide immediate value.
- The agent then asks at most one gentle, targeted follow-up question per turn to elicit the highest-priority missing field.
- Extracted responses are validated (e.g. valid date ranges, realistic NPK ratios, recognized soil types) and flagged as `UNVERIFIED_FARMER_INPUT`.

### Rationale
- Prevents farmer frustration and conversational drop-off.
- Ensures progressive data enrichment over time.

---

## ADR-006: Marathi-First Multilingual Strategy

### Context
The existing classifier and prompts focus primarily on Hindi and Hinglish. However, our primary operational agricultural belt is Maharashtra (sugarcane, onion, cotton, soybean).

### Decision
- Prioritize Marathi (मराठी) across Devanagari script and Romanized Marathi (e.g., *"Kandyala karpa aala aahe"*).
- Expand `AGRI_SYNONYMS` in `rag/embedding_manager.py` with comprehensive Marathi agricultural terminology.
- Design prompts in `agent/prompts.py` to recognize Marathi syntax, idioms, and agricultural metrics (*guntha*, *ton*, *talyat*, *khurpat*).
- Support Hindi, Hinglish, and English concurrently.

### Rationale
- Farmers communicate in their mother tongue; advice in an alien or poorly translated language is ignored or misapplied.

---

## ADR-007: Human-in-the-Loop Safeguards for Agronomic Pathologies & Uncertainty

### Context
Incorrect pesticide or fertilizer dosages can cause severe crop damage, economic ruin, or health hazards.

### Decision
- RAG synthesis prompts must enforce strict grounding: if a dosage or chemical is not found in the verified knowledge base, KrishiBot must never fabricate it.
- When visual or textual evidence is ambiguous, or when a high-risk pathogen (e.g., Red Rot in sugarcane, Fall Armyworm severe infestation, or sudden wilt) is detected, the system automatically routes the ticket to `ASSIGNED_AGRONOMIST` with status `NEW`.
- The farmer is informed that an agricultural specialist is reviewing their query, and coordinator approval is required before dispatching high-risk advice.

### Rationale
- Mandatory Rule 14 & 15: *"Never fabricate farmer data, agricultural facts or expert responses. Use human review for uncertain agricultural diagnoses and high-risk recommendations."*

---

## ADR-008: Webhook Ingress Resilience, Immediate Deduplication, and PII Masking

### Context
During Phase 1 stabilization, incoming webhook events from Meta WhatsApp Cloud API were found to be susceptible to:
1. Malformed non-JSON or non-object payloads causing unhandled 500 exceptions.
2. Concurrent duplicate message deliveries causing redundant background task queueing.
3. Plain-text logging of verification secrets (`hub.verify_token`) and farmer phone numbers.
4. Non-text media messages (audio, images, videos) crashing text message parsers.

### Decision
1. Implemented strict defensive input validation:
   - Malformed JSON or non-object payloads immediately return HTTP 400 Bad Request.
   - Non-text media types (`audio`, `image`, `video`) are logged cleanly and skipped without raising exceptions.
2. Implemented double-layer deduplication:
   - Check `message_id` immediately upon ingress in `receive_whatsapp_event` to prevent queueing duplicate background workers.
   - Retained the secondary check inside `process_message_background`.
3. PII & Secret Redaction:
   - Verification token logging removed from `verify_meta_webhook`.
   - Farmer telephone numbers in log streams are masked (e.g. `******1111`).
4. Isolated Background Execution:
   - Entire background processing wrapped in `try...except Exception` blocks, recording an `ERROR` audit log entry instead of failing silently.

### Rationale
- Ensures 100% gateway uptime, eliminates duplicate outbound WhatsApp messages, and satisfies security/PII requirements.

---

## ADR-009: Normalized Multi-Plot Relational Schema with Data Provenance and Verification Lifecycle

### Context
A farmer may own multiple land parcels in different locations, each with distinct crops, planting dates, acreage, irrigation infrastructure, and soil health profiles. Storing these in a single denormalized table or flatfile spreadsheet causes severe data duplication, overwrite anomalies, and prevents tracking which data points are scientifically verified vs farmer-reported.

### Decision
In Phase 2, we separated:
1. `Farmer` (Master personal and contact record with stable business ID `FARM-XXXXX` and primary 10-digit phone).
2. `FarmerContact` (Alternate numbers, sons, brothers, and shared device tracking).
3. `FarmPlot` (Distinct geographic land parcels with area, unit, drip status, and water source).
4. `CropRecord` (1-to-many cultivation history per plot with planting dates and Indian planting seasons: `SURU`, `ADSALI`, `PRE_SEASONAL`, `KHARIF`, `RABI`).
5. `SoilProfile` (1-to-many chemical profiles per plot with NPK in kg/ha, pH, EC, and Soil Health Card tracking).

Every significant agronomic field is coupled with a `VerificationStatus` (`VERIFIED`, `UNVERIFIED`, `MISSING`, `NEEDS_CORRECTION`) and provenance metadata (`data_source`, `supplied_by`, `created_at`, `last_updated_at`, `verified_at`, `verified_by`). Unsupplied fields are left `None` or marked `MISSING`; no synthetic defaults are ever fabricated.

### Rationale
- Satisfies Mandatory Rules: Multi-plot land support, zero fabrication of missing data, and persistent tracking of verified agronomic facts.

---

## ADR-010: Persistent Webhook Deduplication and Idempotency Architecture

### Context
Meta WhatsApp Cloud API implements retry semantics when a webhook server takes longer than 20 seconds to respond or when network blips occur. In Phase 1, deduplication relied on an in-memory `deque(maxlen=1000)` in `gateway/webhook_server.py`. If the server restarted, this deque cleared, risking duplicate query processing and spamming farmer WhatsApp groups with duplicate outbound messages.

### Decision
In Phase 2, we implemented persistent, database-backed idempotency using the `webhook_events` table and a hybrid `DeduplicationService`:
1. **Thread-Safe RAM Cache:** A bounded deque and set guarded by `threading.Lock()` provides <0.1ms ingress rejection for immediate duplicates.
2. **Persistent DB Ledger:** An atomic transaction attempts to claim the `message_id` with status `PROCESSING`. A database-level unique constraint on `message_id` guarantees that concurrent or post-restart retries are rejected.
3. **Lifecycle Tracking:** Messages are transitioned to `COMPLETED` upon successful WhatsApp dispatch or `FAILED` with error text on exception.

### Rationale
- Guarantees exactly-once processing across server reboots and concurrent multi-threaded requests.

---

## ADR-011: Safe, Idempotent Excel Ingestion with Mandatory Timestamped Backup Strategy

### Context
Existing farmer profiles were stored in `data/farmer_profiles.xlsx`. Migrating to a relational database carries risks of data corruption, accidental deletion, or race conditions if external processes still reference the spreadsheet.

### Decision
We engineered `ExcelMigrationService` with the following guarantees:
1. **Mandatory Backup:** Before reading or touching data, an immutable timestamped copy is created in `data/backups/farmer_profiles_backup_YYYYMMDD_HHMMSS.xlsx`.
2. **Full Idempotency:** The migration matches farmers by normalized 10-digit primary phone. Re-running the migration updates existing records and creates zero duplicate rows.
3. **Two-Way Compatibility:** `form_automation/excel_manager.py` was refactored to read and write through `FarmerService` while maintaining the Excel sheet, ensuring that legacy endpoints (`/api/farmers`, `/api/form-submission`) continue operating without breakage.
4. **Export Capability:** Provides a full reverse export method to generate an Excel sheet matching the legacy format directly from the database.

### Rationale
- Prevents data loss, provides auditability, and preserves backward compatibility without breaking existing workflows.

---

## ADR-012: Data Integrity, Conflict Resolution, and Recovery Architecture (Phase 2 Final Audit)

### Context
Following Phase 2 implementation, a rigorous empirical data integrity audit tested five critical areas:
1. Excel migration overwrite risks and unnecessary rewrite tracking.
2. Webhook exactly-once processing, worker crashes during `PROCESSING`, and external WhatsApp dispatch coupling.
3. Farmer identity, unique constraints, and shared mobile numbers in rural households.
4. Field-level verification isolation versus temporal history preservation.
5. PostgreSQL compatibility and staging requirements.

### Decisions & Safeguards Implemented

1. **Excel Conflict Resolution Strategy & Change Detection:**
   - **Protection of Verified Data:** If a database attribute has `VerificationStatus.VERIFIED` (e.g., confirmed by CDO or land revenue records), `ExcelMigrationService` will NEVER overwrite it with unverified Excel spreadsheet values.
   - **Change Detection:** `ExcelMigrationService` compares incoming values with existing values. It only bumps `last_updated_at` when values genuinely differ, tracking both `updated_count` and `unchanged_count`.
   - **In-Batch Duplicate Phone Guard:** If two rows in the same Excel spreadsheet share a phone number, the service flags a warning and refuses to overwrite the first row with the second row, preventing destructive household merges.

2. **Webhook Recovery & Transaction Boundary:**
   - **Stale Processing Reclamation:** `IdempotencyRepository.claim_message` was enhanced with `stale_threshold_seconds` support to reclaim messages orphaned in `PROCESSING` status if a worker crashed. Explicit `created_at=datetime.now()` was added during model instantiation to ensure deterministic age calculation across both SQLite and PostgreSQL.
   - **Explicit Failed Retry:** Added `allow_failed_retry` capability for controlled re-dispatch.
   - **Outbound WhatsApp Delivery Limitation & Outbox Pattern:** Identified and verified that outbound WhatsApp API calls (`WhatsAppCloudClient.send_message`) occur before `complete_message()` is committed. This means the system does NOT claim exactly-once external WhatsApp delivery. To eliminate duplicate delivery risks if DB commits fail after successful HTTP transport, a **Transactional Outbox Pattern** (`outbox_messages` table + background dispatcher) is scheduled for Phase 3.

3. **Multi-Farmer Disambiguation:**
   - Added `FarmerRepository.lookup_all_by_phone(phone)` returning a list of all farmers sharing a primary or alternate contact, eliminating arbitrary `.first()` resolution.

4. **Field-Level Isolation:**
   - Verified that field verification statuses (`name_status`, `area_status`, `planting_date_status`, `crop_status`, `soil_type_status`) are strictly isolated. Updating one field never alters the verification state of another.

### Rationale
- Protects verified agronomic truth from legacy data pollution while providing clean recovery paths for distributed messaging.

---

## ADR-013: Conversational Memory, State Machine, and Polite Follow-Up Engine

### Context
In Phase 1 and 2, agent interactions were stateless: each incoming message was treated as a discrete turn without memory of previous questions or context. To elicit missing agronomic information from farmers without spamming them or overwriting verified profile facts, KrishiBot required persistent conversational sessions, dialog state management, and strict provenance protection.

### Decision
1. Implement `ConversationSession` and `ConversationMessage` in the relational database.
2. Introduce a finite state machine via `ConversationState` (`ACTIVE`, `AWAITING_FIELD_INPUT`, `ESCALATED`, `RESOLVED`, `CLOSED`).
3. Store conversation turns chronologically and inject recent turns into the LLM prompt context while strictly partitioning sessions by farmer ID to prevent cross-farmer contamination.
4. Build `FollowupEngine` to inspect 10 agronomic parameters across 5 verification states (`MISSING`, `NOT_PROVIDED`, `UNKNOWN`, `PENDING_CONFIRMATION`, `VERIFIED`).
5. Enforce that fields marked `VERIFIED` are strictly protected and can never be overwritten by conversational AI extraction. Conversational updates are marked `UNVERIFIED` with `WHATSAPP_CHAT` provenance and recorded in `FieldHistory`.
6. Enforce polite follow-up UX: at most 1 question per turn, duplicate question avoidance, and support for Marathi, Hindi, and English phrasing.

### Rationale
- Farmers disengage if asked multiple questions at once or repeatedly asked for information they have already provided.
- Strict protection of verified data prevents automated hallucinations from corrupting ground-truth agronomic records.

---

## ADR-014: 13-Category Agricultural Intent Taxonomy and Transactional Outbox Pattern

### Context
The baseline system used 5 coarse-grained categories (`FARMING_QUERY`, `FORM_RELATED`, `URGENT_DISTRESS`, `GREETING_OR_CHATTER`, `SPAM_OR_OFF_TOPIC`). As the system expands toward CDO coordination, sugar factory harvesting schedules, and weather advisories, granular intent routing is necessary. Furthermore, direct synchronous external calls to Meta's WhatsApp API risk message loss or duplicate dispatch during server crashes and network timeouts.

### Decision
1. Expand agricultural classification to 13 granular intents (`CROP_DISEASE_PEST`, `FERTILIZER_NUTRITION`, `IRRIGATION_WATER`, `VARIETY_SELECTION`, `PLANTING_SOWING`, `HARVESTING_POST_HARVEST`, `WEATHER_CLIMATE`, `GOVERNMENT_SCHEME_SUBSIDY`, `CDO_COORDINATION_INQUIRY`, `FARMER_PROFILE_UPDATE`, `GENERAL_GREETING`, `DISTRESS_EMERGENCY`, `OFF_TOPIC_OTHER`).
2. Maintain 100% backward compatibility via `INTENT_TO_LEGACY_CATEGORY` mapping all granular intents to the legacy 5 categories for existing consumers.
3. Implement the Transactional Outbox pattern via `OutboxMessage` table and `OutboxService`. Outbound replies are committed to the database in the same transaction as incoming message processing before external dispatch.
4. Support idempotency keys and exponential backoff retry tracking for outbound WhatsApp messages.

### Rationale
- Granular classification enables precise downstream workflow routing while preserving backward compatibility.
- The transactional outbox guarantees that outbound messages are never lost during process crashes and provides auditability for all external communications.

