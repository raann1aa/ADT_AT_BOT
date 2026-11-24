# TEST SUITE & EMPIRICAL VERIFICATION REPORT

**Project:** AI-Powered Farmer Communication and Agricultural Support Automation System  
**Current Phase:** PHASE 1 — STABILISATION  
**Last Test Execution:** 2026-11-22  
**Overall Test Pass Rate:** 100% (All 4 automated suites passing cleanly)  

---

## 1. Test Architecture & Overview

The project maintains automated regression, retrieval, unit, and integration test suites in `scripts/`:

```
scripts/
├── test_retrieval.py        # 12-case multilingual RAG semantic retrieval verification
├── test_phase_b.py          # 16-rule classifier verification & 5 end-to-end agent scenarios
├── test_webhook_flow.py     # 8-step FastAPI integration, webhook resilience, & Excel tests
└── simulate_whatsapp_group.py # 7-message realistic WhatsApp group chat simulation
```

---

## 2. Test Execution Summary

| Test Suite Script | Test Scope | Cases / Steps | Result | Baseline (Phase 0) | Current (Phase 1) |
|---|---|---|---|---|---|
| `scripts/test_retrieval.py` | Multilingual RAG Retrieval | 12 queries | ✅ **12/12 PASSED (100%)** | ❌ FAILED (`LocalEntryNotFoundError`) | ✅ **100% Top-1 Hit** |
| `scripts/test_phase_b.py` | Message Classifier & Agent | 16 unit + 5 E2E | ✅ **21/21 PASSED (100%)** | ⚠️ Partial (Classifier 100%, E2E failed on RAG) | ✅ **100% Classifier & E2E** |
| `scripts/test_webhook_flow.py` | Gateway, Webhook, Dashboard, & Resilience | 8 steps | ✅ **8/8 PASSED (100%)** | ⚠️ Partial (Failed at step 5 on RAG) | ✅ **100% Passed** |
| `scripts/simulate_whatsapp_group.py` | Live District Group Simulation | 7 messages | ✅ **7/7 PASSED (100%)** | ❌ Blocked on RAG loading | ✅ **100% Noise Filtered & Answered** |
| *Live Uvicorn Server Test* | Port Binding & HTTP Root Diagnostics | Live HTTP 200 | ✅ **PASSED** | Not tested | ✅ **HTTP 200 OK** |

---

## 3. Detailed Test Suite Reports

### 3.1 Suite 1: Multilingual RAG Retrieval (`scripts/test_retrieval.py`)
- **Execution Command:** `python scripts/test_retrieval.py`
- **ChromaDB Chunks Loaded:** 193 indexed chunks
- **Embedding Model:** `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)
- **Results Table:**

| # | Query | Language | Expected Topic | Retrieved Source (Rank 1) | Confidence | Status |
|---|---|---|---|---|---|---|
| 1 | How to treat yellow rust in wheat? | English | Yellow Rust | Wheat Yellow Rust Identification & Control > Symptoms | 81.5% | ✅ PASS (Rank 1) |
| 2 | गेहूं में पीली पत्तियां और पीला रतुआ का इलाज क्या है? | Hindi (Devanagari) | Yellow Rust | Wheat Yellow Rust > Chemical Control (Treatment) | 85.6% | ✅ PASS (Rank 1) |
| 3 | Kapas me gulabi sundi ke liye kaun sa spray kare? | Hinglish | Pink Bollworm | Pink Bollworm in Cotton > Diagnostic Field Signs | 84.1% | ✅ PASS (Rank 1) |
| 4 | PM kisan 6000 installment eKYC kaise kare aur land seeding pending hai | Hinglish (Scheme) | PM-KISAN | PM-KISAN Samman Nidhi > Mandatory Prerequisites | 99.0% | ✅ PASS (Rank 1) |
| 5 | Mirch me patta marod aur churda murda thrips dawai | Hinglish | Chilli Leaf Curl | Chilli Leaf Curl, Thrips, & Mites > Mite Management | 77.8% | ✅ PASS (Rank 1) |
| 6 | Pyaj me kanda sadi aur warehouse storage rot kaise roke? | Hinglish | Purple Blotch / Rot | Purple Blotch & Storage Rot in Onion > Storage Rot | 85.8% | ✅ PASS (Rank 1) |
| 7 | Crop insurance claim 72 ghante me kaise kare fasal kharab hone par? | Hinglish (Scheme) | PM Fasal Bima | PM Fasal Bima Yojana > Farmer Premium Rates | 88.0% | ✅ PASS (Rank 1) |
| 8 | Makka me fall armyworm keede aur whorl ko kaise bachaye? | Hinglish | Fall Armyworm | Maize Cultivation & Fall Armyworm > Seasons & Seed Rate | 87.9% | ✅ PASS (Rank 1) |
| 9 | Drip irrigation lateral pipe acid treatment for salt clogging | English (Technical) | Drip Maintenance | Drip Irrigation Maintenance > Acid Treatment for Clogged Drippers | 87.9% | ✅ PASS (Rank 1) |
| 10 | Paddy blast rog me gardan tod aur safed balian stem borer | Hinglish | Rice Stem Borer | Rice Stem Borer & Blast Disease > Symptoms by Stage | 90.5% | ✅ PASS (Rank 1) |
| 11 | Tomato me fal fatna aur blossom end rot calcium ki kami | Hinglish | Tomato | Tomato Farming, Trellising, & Yield > Preventing BER | 77.9% | ✅ PASS (Rank 1) |
| 12 | 1 acre gehu me pehli sinchai kab kare aur urea kitna dale? | Hinglish | Wheat Cultivation | Wheat Cultivation, Irrigation, & Fertilizer > Land Prep | 76.9% | ✅ PASS (Rank 1) |

**Summary:** 12/12 PASSED (100.0% Rank 1 Accuracy).

---

### 3.2 Suite 2: Message Classifier & End-to-End Agent (`scripts/test_phase_b.py`)
- **Execution Command:** `python scripts/test_phase_b.py`

#### Part A: Classifier Unit Verification (16 Tests)
- Greetings & Chatter: 7/7 correctly classified and flagged `IGNORE` (e.g., "Good morning", "सुप्रभात", "Ram Ram", "जय श्री राम", "धन्यवाद", emojis).
- Spam & Viral Forwards: 2/2 correctly classified and flagged `IGNORE` ("Forwarded as received", "Happy Diwali").
- Form Enquiries: 2/2 correctly classified and flagged `REPLY` (Google form link requests).
- Urgent Distress: 1/1 correctly classified and flagged `ESCALATE` (Farmer suicide distress signals).
- Farming Queries: 4/4 correctly classified and flagged `REPLY` (wheat, cotton, onion, PM-kisan).
- **Classifier Score:** 16/16 Passed (100.0% Accuracy).

#### Part B: Master FarmerAgent End-to-End Pipeline (5 Scenarios)
1. **Social Greeting:** `सुप्रभात जी 🙏` -> `IGNORED` (0.48 ms) -> ✅ CORRECT
2. **Google Form Query:** `Sir weekly farm details ka google form link bhejiye` -> `FORM_HELP` (0.20 ms) -> ✅ CORRECT
3. **Pest Query (Hinglish):** `Kapas me gulabi sundi ke liye kaun si dawai dale?` -> `ANSWERED` (RAG advisory: Trichogramma parasitoid & neem spray) -> ✅ CORRECT
4. **Disease Query (Hindi):** `गेहूं में पीली पत्तियां और पीला रतुआ का इलाज क्या है?` -> `ANSWERED` (RAG advisory: Rogor / Actara / Confidor) -> ✅ CORRECT
5. **Distress Signal:** `Sab fasal kharab ho gayi hai meri, ab mai suicide karunga` -> `ESCALATED` (Kisan Call Centre 1800-180-1551 & Tele-MANAS helpline dispatched) -> ✅ CORRECT

**Summary:** All 5/5 End-to-End Agent Pipeline Scenarios PASSED.

---

### 3.3 Suite 3: Gateway, Webhook, Dashboard & Resilience (`scripts/test_webhook_flow.py`)
- **Execution Command:** `python scripts/test_webhook_flow.py`

| Step | Test Name | Target Endpoint | Assertion | Result |
|---|---|---|---|---|
| 1 | Meta Webhook Handshake | `GET /webhook` | Returns challenge with 200 OK | ✅ PASS |
| 2 | System Diagnostics | `GET /` | Registered groups >= 3, farmers >= 6, chunks >= 190 | ✅ PASS |
| 3 | Excel Farmer Registry | `GET /api/farmers` | Retrieves profiles; Ramesh Patil (Nashik, Onion) verified | ✅ PASS |
| 4 | Greeting Webhook | `POST /webhook` | Returns 200 OK; background worker drops chatter | ✅ PASS |
| 5 | Agricultural Query Webhook | `POST /webhook` | Returns 200 OK; resolves farmer profile & runs RAG | ✅ PASS |
| 6 | Weekly Form Broadcast & Ingestion | `POST /api/broadcast-weekly-form` & `POST /api/form-submission` | Broadcasts to 3 groups; appends Mukesh Sharma to Excel | ✅ PASS |
| 7 | Dashboard UI & Analytics | `GET /dashboard`, `/api/dashboard/stats`, `/api/dashboard/messages` | HTML renders; stats return queries/noise; message audit stream available | ✅ PASS |
| 8.1 | Invalid Verify Token | `GET /webhook?hub.verify_token=wrong` | Returns HTTP 403 Forbidden | ✅ PASS |
| 8.2 | Malformed Non-JSON Body | `POST /webhook` (raw invalid bytes) | Returns HTTP 400 Bad Request | ✅ PASS |
| 8.3 | Non-Object JSON Payload | `POST /webhook` (JSON array) | Returns HTTP 400 Bad Request | ✅ PASS |
| 8.4 | Non-Text Media Message | `POST /webhook` (type: "audio") | Handled cleanly with 200 OK, non-crashing skip | ✅ PASS |
| 8.5 | Duplicate Message ID | `POST /webhook` (same ID twice) | Deduplicated at ingress with 200 OK | ✅ PASS |
| 8.6 | Empty Text Message | `POST /webhook` (empty body) | Safely skipped with 200 OK | ✅ PASS |

**Summary:** ALL 8/8 INTEGRATION & RESILIENCE TESTS PASSED (100%).

---

### 3.4 Live Application Startup Verification

Tested live Uvicorn startup and HTTP binding on `http://127.0.0.1:8000/`:
- **Command:** `uvicorn.run('gateway.webhook_server:app', host='127.0.0.1', port=8000)`
- **Response:**
  ```json
  {
    "service": "KrishiBot WhatsApp Gateway & RAG Service",
    "status": "online",
    "registered_groups": 3,
    "registered_farmers_in_excel": 7,
    "knowledge_chunks_indexed": 193,
    "whatsapp_client_mode": "DRY-RUN SIMULATION",
    "dashboard_url": "/dashboard"
  }
  ```
- **Result:** Status Code 200 OK. Application starts cleanly and serves endpoints.

---

## 4. Verification Matrix: Local vs External Services

| Capability | Local Verification Status | Production Dependency / Requirement |
|---|---|---|
| Webhook Verification (`GET /webhook`) | ✅ **Verified (100%)** | Requires Meta App Dashboard configuration |
| Webhook Event Parsing (`POST /webhook`) | ✅ **Verified (100%)** | Requires live Meta Cloud API webhook delivery |
| Ingress Deduplication | ✅ **Verified (100%)** | Operates locally via in-memory deque (DB in Phase 2) |
| Excel Profile Lookup & Cache | ✅ **Verified (100%)** | Operates on `data/farmer_profiles.xlsx` (DB in Phase 2) |
| Message Classification (5 categories) | ✅ **Verified (100%)** | Local regex heuristics (Expanded in Phase 3) |
| RAG Semantic Retrieval | ✅ **Verified (100%)** | Runs locally on CPU via ChromaDB & MiniLM |
| Extractive Fallback Synthesis | ✅ **Verified (100%)** | Fully offline; extracts verified knowledge context |
| Google Gemini 1.5 Flash API | ⚠️ **Offline Verified (Fallback)** | Requires valid `GEMINI_API_KEY` for live generative responses |
| WhatsApp Message Delivery | ⚠️ **Dry-run Verified** | Requires valid `WHATSAPP_TOKEN` & `WHATSAPP_PHONE_NUMBER_ID` for live delivery |
| Google Form Automation | ✅ **Verified (100%)** | Local Excel sync verified; live Google Sheets requires service account |

---

## 5. Pre-Phase 2 Final Verification: Test Integrity & Disclosures

### 5.1 Test Execution Nature: Real vs Fallback vs Simulated
- **`scripts/test_retrieval.py` (12 tests):**
  - **Retrieval Engine:** 100% REAL. Generates real 384-dimensional dense vectors using local PyTorch `BertModel` weights of `sentence-transformers/all-MiniLM-L6-v2` on CPU, queries persistent ChromaDB on SQLite disk store (`data/chroma_db`), and returns genuine matching markdown chunks from `knowledge_base/`.
- **`scripts/test_phase_b.py` (21 tests):**
  - **Classifier Unit Tests (16 tests):** 100% REAL. Executes `WhatsAppMessageClassifier.classify()` with regex heuristics.
  - **End-to-End Scenarios 1, 2, 5 (Greeting, Form Help, Distress):** 100% REAL rule-based logic.
  - **End-to-End Scenarios 3 & 4 (Pest & Disease Queries):** RAG vector retrieval is 100% REAL; LLM synthesis uses the local extractive fallback `_generate_local_fallback()` because no `GEMINI_API_KEY` was provided.
- **`scripts/test_webhook_flow.py` (8 steps):**
  - **Webhook Endpoints & Ingress Validation:** 100% REAL ASGI in-process HTTP dispatch via `fastapi.testclient.TestClient`.
  - **Excel Farmer Lookup & Write:** 100% REAL read/write against `data/farmer_profiles.xlsx`.
  - **Outbound WhatsApp Message Delivery:** SIMULATED. Operates via `WhatsAppCloudClient` in dry-run mode, printing messages to stdout rather than dispatching HTTP requests to Meta Graph API servers.
- **`scripts/simulate_whatsapp_group.py` (7 messages):**
  - **Group Environment:** 100% SIMULATED. Demonstrates filtering and advisory logic in an offline script. Does not establish or interact with live WhatsApp group chats.

### 5.2 Deduplication Architecture & Volatility Risk
- **Current Mechanism:** Webhook message IDs are stored in an in-memory `collections.deque(maxlen=1000)` (`processed_message_ids` in `gateway/webhook_server.py`).
- **Persistence:** Volatile only. **Message IDs DO NOT persist across application restarts.**
- **Identified Failure Modes:**
  1. If the server restarts while Meta is retrying an unacknowledged webhook, the event will be re-processed as a new message.
  2. If traffic exceeds 1,000 messages, earlier message IDs are evicted and late retries will duplicate.
  3. Multi-worker deployments (multiple Uvicorn worker processes) do not share this in-memory deque.
- **Scheduled Solution:** Persistent relational database table (`messages` / `idempotency_keys`) in Phase 2.

### 5.3 WhatsApp Cloud API Group Limitations
- Official Meta WhatsApp Cloud API (Graph API v21.0) strictly supports individual 1-to-1 messaging (`recipient_type: "individual"` with numeric E.164 phone numbers). It does NOT support bot accounts joining or posting to user-created WhatsApp groups.
- The group simulation in the repository is an offline demonstration harness only.
- Genuinely supported production flows: Inbound/outbound 1-to-1 farmer messaging, webhook handshake verification, Google Form ingestion, and 1-to-1 administrative notifications.

### 5.4 Canonical Documentation Location
- Canonical documentation is exclusively located within the Git repository at `ADT-AI-BOT/docs/`.
- Misplaced and duplicate documentation in the root workspace has been resolved by placing a pointer README in `docs/` directing all readers to the canonical `ADT-AI-BOT/docs/` directory.

---

## 6. Phase 2 Empirical Test Results: Database & Farmer Information Management

### 6.1 Test Suite Overview (`scripts/test_phase_2_database.py`)
- **Execution Command:** `python scripts/test_phase_2_database.py`
- **Total Tests Executed:** 62
- **Pass Rate:** **62/62 PASSED (100.0%)**
- **Test Database Engine:** In-memory SQLite (`sqlite:///:memory:`) using isolated fixtures to prevent modifying production or sample data.

### 6.2 Test Results by Functional Domain

| Section | Domain Tested | Test Count | Pass Rate | Key Verifications |
|---|---|---|---|---|
| **Section 1** | Database Initialization & Schema | 2 | 2/2 (100%) | Verified DB connectivity check; confirmed all 15 relational tables created. |
| **Section 2** | Geographic Hierarchy & CDO Directory | 7 | 7/7 (100%) | Verified District, Division, Factory, CDO creation, employee code lookup, and agronomist specialization index. |
| **Section 3** | Farmer CRUD & Phone Lookups | 7 | 7/7 (100%) | Verified farmer creation, 10-digit clean lookup, `+91` E.164 normalization, stable `farmer_id` lookup, unknown phone returns `None`. |
| **Section 4** | Multi-Plot Holdings, Crops & Soils | 7 | 7/7 (100%) | Verified multiple plots attached to 1 farmer; verified Indian seasons (`RABI`, `SURU`); verified NPK tracking in kg/ha; confirmed missing fields are flagged `MISSING` (zero fabrication). |
| **Section 5** | Verification Status & Provenance | 5 | 5/5 (100%) | Verified 4 lifecycle states (`VERIFIED`, `UNVERIFIED`, `MISSING`, `NEEDS_CORRECTION`); confirmed data source and timestamps stored. |
| **Section 6** | Shared & Alternate Phone Numbers | 2 | 2/2 (100%) | Verified alternate contact resolution; confirmed duplicate primary phones are rejected by unique constraints. |
| **Section 7** | Issue Lifecycle & Tasks | 5 | 5/5 (100%) | Verified issue code generation (`ISS-YYYYMM-XXXX`), escalation to CDO, follow-up task generation, resolution with audit notes. |
| **Section 8** | Persistent Audit Logging | 4 | 4/4 (100%) | Verified DB write of audit logs; confirmed statistics calculation; verified escalation tracking across restarts. |
| **Section 9** | Persistent Webhook Deduplication | 6 | 6/6 (100%) | Verified first claim succeeds; duplicate claim rejected; completed and failed states tracked; multi-threaded concurrent duplicate rejected (thread safety verified). |
| **Section 10** | Excel Migration & Idempotency | 5 | 5/5 (100%) | Verified timestamped backup created in `data/backups/`; first run imports valid & skips invalid; re-run updates without duplicates; export round-trip preserves format. |
| **Section 11** | FarmerService Compatibility | 4 | 4/4 (100%) | Verified `FarmerProfile` and `FarmerFormSubmission` model conversion from database layer. |
| **Section 12** | Webhook Regression Tests | 8 | 8/8 (100%) | Verified Meta handshake, text message processing, 400 Bad Request on malformed JSON, media skip, health endpoints. |

### 6.3 Regression Suites Verification (Zero Regressions)

| Test Script | Status | Results |
|---|---|---|
| `scripts/test_retrieval.py` | ✅ **PASSED** | 12/12 Rank 1 hits (100.0%) across English, Hindi, and Hinglish queries. |
| `scripts/test_phase_b.py` | ✅ **PASSED** | 16/16 classifier rules + 5/5 agent end-to-end scenarios (100.0%). |
| `scripts/test_webhook_flow.py` | ✅ **PASSED** | 8/8 steps including all 6 resilience edge cases (100.0%). |
| `scripts/test_phase_2_database.py` | ✅ **PASSED** | 62/62 database, repository, multi-plot, and deduplication tests (100.0%). |

---

## 7. Phase 2 Final Data Integrity & Reliability Audit Results

### 7.1 Audit Script Overview (`scripts/audit_phase_2_integrity.py`)
- **Execution Command:** `python scripts/audit_phase_2_integrity.py`
- **Execution Status:** Successfully executed against synthetic data fixtures.
- **Audit Findings & Safeguard Summary:**

| Audit Dimension | Test Scenario | Observed Implementation Behavior | Mitigation / Safeguard Applied |
|---|---|---|---|
| **Excel Migration Safety** | Unchanged record re-run | `updated_count` reported 1 because row was touched; `last_updated_at` was bumped | Added change detection: `last_updated_at` bumped only if values changed; reports `unchanged_count` |
| **Excel Migration Safety** | DB field verified, Excel unverified | Migration blindly overwrote verified DB value (`Sugarcane`) with stale Excel value (`Wheat`) | Added **Conflict Resolution Rule 1**: If field status is `VERIFIED`, Excel migration NEVER overwrites it |
| **Excel Migration Safety** | Multiple farmers sharing phone in Excel | Row 2 silently overwrote Row 1, merging two brothers into one profile | Added **In-Batch Duplicate Guard**: detects duplicate phone in Excel batch, flags warning, skips destructive merge |
| **Excel Migration Safety** | Farmer phone changes in Excel | Migration could not match by phone and created duplicate `FARM-00003` | Documented requirement for stable Farmer ID in future spreadsheets; phone changes require admin/CDO workflow |
| **Webhook Exactly-Once** | Concurrent worker claim | Thread-safe in-memory lock + DB unique constraint: `[True, False]` | Exactly-once claim guaranteed under concurrent race conditions |
| **Webhook Exactly-Once** | Server restart dedup | RAM cache cleared; DB ledger rejected duplicate `wamid.xxx` | Persistent ledger survives server reboots |
| **Webhook Recovery** | Worker crash during `PROCESSING` | Status remained `PROCESSING`; Meta retry dropped without processing | Added `stale_threshold_seconds` to `IdempotencyRepository` to reclaim crashed locks |
| **Webhook Recovery** | Outbound WhatsApp vs DB coupling | External HTTP dispatch happens inline; failure between HTTP and DB risks retry spam | Documented architectural requirement for **Transactional Outbox Pattern** in Phase 3 |
| **Farmer Identity** | Two farmers with same primary phone | SQLite/PostgreSQL unique constraint raises `IntegrityError` | Enforces 1 primary phone per farmer; shared family phones must use `FarmerContact` |
| **Farmer Identity** | Multi-farmer lookup by shared phone | `lookup_by_phone` used `.first()`, arbitrarily picking the first farmer | Added `lookup_all_by_phone(phone)` returning full list of matching farmers for disambiguation |
| **Field Verification** | Updating one field's status | Updating `planting_date` status to `VERIFIED` left `name_status` and `area_status` unchanged | Confirmed field-level verification isolation |
| **Provenance & History** | Preserving previous field values | In-place updates overwrite previous column values | Confirmed absence of temporal table; recommended dedicated `field_history` table for Phase 3 |
| **PostgreSQL Compatibility** | Enums, FKs, pooling, migrations | Portable VARCHAR enums (`native_enum=False`), `QueuePool` for Postgres, batch migrations | Compatible schema; row-level locking (`SELECT FOR UPDATE`) requires staging verification |

---

## 8. Phase 2 Final Correction and Sign-Off Test Results

### 8.1 Test Suite Overview (`scripts/test_phase_2_final_verification.py`)
- **Execution Command:** `python scripts/test_phase_2_final_verification.py`
- **Total Tests Executed:** 27
- **Pass Rate:** **27/27 PASSED (100.0%)**
- **Test Database Engine:** In-memory SQLite (`sqlite:///:memory:`) using completely isolated fixtures.

### 8.2 Breakdown of Verified Scenarios

| Section | Target Area | Tests | Result | Verified Behaviors |
|---|---|:---:|:---:|---|
| **Section 1** | Excel Migration Conflict Protection | 7 | 7/7 (100%) | First run creates record; identical re-run counts record as unchanged without touching `last_updated_at`; `VERIFIED` DB fields are never overwritten by stale Excel values; duplicate phone in Excel batch is skipped to prevent merging; genuinely changed unverified field is updated; missing Excel field does not corrupt record; timestamped backups created per run. |
| **Section 2** | Webhook Processing Reliability | 8 | 8/8 (100%) | Exactly one worker claims concurrent incoming message; persistent DB ledger blocks duplicates post server restart; stale `PROCESSING` event (>300s) reclaimed; fresh `PROCESSING` (<300s) not reclaimed; `FAILED` blocked by default but retryable with `allow_failed_retry=True`; `COMPLETED` never reprocessed; external WhatsApp delivery limitation documented (Transactional Outbox required for Phase 3). |
| **Section 3** | Field-Level Verification | 6 | 6/6 (100%) | Farmer model has per-field statuses (`name_status`, `village_status`, `tehsil_status`); CropRecord has 5 granular statuses; SoilProfile has 3 granular statuses; FarmPlot has 2 per-field statuses; updating one field status leaves all other fields intact; documented gap of missing `field_history` temporal table. |
| **Section 4** | Farmer Identity | 6 | 6/6 (100%) | `farmer_id` is stable business identity; changing phone number preserves `farmer_id` and DB PK; multiple farmers can share a phone via `FarmerContact`; duplicate primary phone rejected by unique constraint; `lookup_all_by_phone` returns all matches to eliminate arbitrary `.first()` selection; `generate_next_farmer_id` produces unique `FARM-XXXXX` sequence. |
