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
