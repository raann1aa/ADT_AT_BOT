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
