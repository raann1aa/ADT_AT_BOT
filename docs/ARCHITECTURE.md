# SYSTEM ARCHITECTURE: AGRICULTURAL SUPPORT & COORDINATION AUTOMATION

**System:** AI-Powered Farmer Communication and Agricultural Support Automation System  
**Current State:** Phase 1 Stabilised Baseline  
**Target State:** Complete Multi-Stakeholder Automation Platform (Phases 1–7)  

---

## 1. As-Is Architecture (Phase 1 Stabilised Baseline)

The system is structured as an asynchronous FastAPI application paired with an in-memory/Excel data layer and a local ChromaDB vector store, now fortified with defensive ingress validation, double-layer deduplication, and resilient model loading:

```
+-------------------------------------------------------------------------+
|                        META WHATSAPP CLOUD API                          |
|                       (Incoming Webhook Events)                         |
+------------------------------------+------------------------------------+
                                     |
                                     v HTTP POST /webhook
+-------------------------------------------------------------------------+
|                  FASTAPI GATEWAY (gateway/webhook_server.py)             |
|                                                                         |
|  - Webhook verification (GET /webhook) without credential logging       |
|  - Defensive JSON & structure validation (HTTP 400 on malformed payloads)|
|  - Immediate ingress deduplication (deque maxlen=1000)                  |
|  - Safe handling of non-text media messages (audio/images/videos)        |
|  - Immediate 200 OK response (<10ms)                                    |
|  - Background task scheduling with try/except error isolation           |
+------------------------------------+------------------------------------+
                                     |
                                     v (Background Task)
+-------------------------------------------------------------------------+
|                  FARMER AGENT & CLASSIFIER LAYER                        |
|                                                                         |
|  1. Farmer Profile Lookup: ExcelProfileManager (data/farmer_profiles.xlsx)|
|  2. Message Classifier (agent/classifier.py):                           |
|     - Regex pattern heuristics (Greeting, Spam, Form, Distress, Query)  |
|     - If Noise/Spam -> Silently Drop (No WhatsApp output)               |
|     - If Form -> Send Google Form Link                                  |
|     - If Distress -> Dispatch Emergency Helpline                        |
|     - If Query -> Forward to RAG Engine                                 |
+------------------------------------+------------------------------------+
                                     |
                                     v
+------------------------------------+------------------------------------+
|               RAG & INFERENCE PIPELINE (rag/pipeline.py)                |
|                                                                         |
|  1. Resilient Model Loading: checks local HuggingFace cache first,      |
|     falls back to download if allowed, or raises actionable error       |
|  2. Query Expansion: AGRI_SYNONYMS dictionary (Hindi/Hinglish to English)|
|  3. Dense Vector Retrieval: ChromaDB SQLite store (data/chroma_db)      |
|  4. Hybrid Scoring: Cosine distance + Domain lexical keyword boost      |
|  5. LLM Synthesis (agent/llm_client.py):                                |
|     - Google Gemini 1.5 Flash REST API                                  |
|     - Offline fallback: Extractive rule-based parsing                   |
|  6. Response Formatter: WhatsApp single-asterisk formatting             |
+------------------------------------+------------------------------------+
                                     |
                                     v
+------------------------------------+------------------------------------+
|                   DELIVERY & AUDIT TRACKING                             |
|                                                                         |
|  - WhatsApp Dispatcher: WhatsAppCloudClient (gateway/whatsapp_client.py)|
|    with E.164 phone number validation and PII-masked logging            |
|  - Audit Logger: AuditLogger deque with failure tracking                |
|  - Visual Dashboard: HTML/Tailwind/Chart.js (gateway/templates/dashboard.html)|
+-------------------------------------------------------------------------+
```

---

## 2. To-Be Target System Architecture (Phases 1–7)

The target architecture replaces ephemeral in-memory state and flatfiles with a resilient relational database, a stateful multi-turn conversation orchestrator, multimodal processors, and automated CDO/agronomist workflows.

```
                        +----------------------------+
                        |  FARMERS, CDOs, EXPERTS    |
                        |      (WhatsApp / Web)      |
                        +--------------+-------------+
                                       |
                                       v
         +---------------------------------------------------------+
         |               INGRESS / EGRESS GATEWAY                  |
         |  - Meta WhatsApp Cloud API (v21.0)                      |
         |  - Media Downloader (Audio, Photos, Video)              |
         |  - Signature Verification & HMAC Security               |
         |  - Redis / DB Persistent Idempotency & Deduplication    |
         +-----------------------------+---------------------------+
                                       |
                                       v
         +---------------------------------------------------------+
         |          MULTIMODAL & MULTILINGUAL ENGINE               |
         |  - Language Identifier: Marathi, Hindi, English, Mixed  |
         |  - Voice STT: Marathi / Hindi Audio Transcription       |
         |  - Vision Diagnostic: Plant symptom feature extractor   |
         |  - Video Processing: Keyframe extraction & analysis     |
         +-----------------------------+---------------------------+
                                       |
                                       v
         +---------------------------------------------------------+
         |            CENTRAL CONVERSATION ORCHESTRATOR            |
         |  - Intent Classifier (13 Granular Categories)           |
         |  - Persistent Session Manager (Stateful Multi-Turn)     |
         |  - Missing Agronomic Parameter Detective                |
         |  - Conversational Data Collection Engine                |
         |  - Grounded RAG Knowledge Retriever                     |
         |  - Tool Action Dispatcher (Safe DB Services)            |
         +---------+-------------------+-----------------+---------+
                   |                   |                 |
                   v                   v                 v
+----------------------+     +-----------------+   +---------------+
| CDO COORDINATION     |     | AGRONOMIST      |   | RAG KNOWLEDGE |
| - Factory routing    |     | ESCALATIONS     |   | - ChromaDB    |
| - Missing data alerts|     | - Expert triage |   | - Semantic    |
| - Follow-up engine   |     | - Review portal |   | - Lexical re-rank|
+----------+-----------+     +--------+--------+   +---------------+
           |                          |
           +------------+-------------+
                        |
                        v
         +---------------------------------------------------------+
         |                 PERSISTENT DATA LAYER                   |
         |  - PostgreSQL / Relational Database (SQLAlchemy)        |
         |  - Farmers, Profiles, Crops, Soil Data                  |
         |  - CDOs, Agronomists, Factory/Division Mapping          |
         |  - Issues, Escalations, Conversation History, Logs     |
         +-----------------------------+---------------------------+
                                       |
                                       v
         +---------------------------------------------------------+
         |          COORDINATOR OPERATIONS DASHBOARD               |
         |  - Live Operational KPI & Issue Stream                  |
         |  - Farmer Registry & Missing Field Verification         |
         |  - CDO Directory & Escalation Handoff Controls          |
         |  - Human Review / Safe Message Approval Gate            |
         +---------------------------------------------------------+
```

---

## 3. Data Flow Traces

### Flow 1: Farmer Agricultural Inquiry
1. Farmer sends text or voice message in Marathi: *"कांद्यावर करपा आला आहे, कोणती फवारणी करू?"*
2. **Ingress:** Webhook receives payload, checks signature, writes incoming event to persistent DB, queues background task, and returns HTTP 200.
3. **Multimodal Processing:** If voice, STT converts audio to text transcript. Language detector flags `Marathi (mr)`.
4. **Classification:** Intent classified as `CROP_DISEASE_PEST_QUERY`.
5. **Session Resolution:** Active session retrieved by phone number. Farmer identified as Ramesh Patil, District: Nashik, Crop: Onion.
6. **RAG Retrieval:** Query expanded with Marathi agronomic synonyms (`करपा -> purple blotch storage rot onion`). ChromaDB retrieves top 3 grounded chunks.
7. **Synthesis:** System prompt supplied with farmer profile, Marathi instruction, and retrieved literature. LLM generates grounded Marathi recommendation with dosage (e.g., *Mancozeb 75% WP @ 2.5 g/L* or *Carbendazim 50% WP @ 1 g/L*).
8. **Delivery & Audit:** Output formatted for WhatsApp and delivered. Interaction recorded in `conversation_records` and `audit_logs`.

### Flow 2: Automated Farm Parameter Collection
1. System recognizes that farmer Ramesh Patil has missing parameters: `planting_date`, `npk_values`, `planting_season`.
2. When the farmer interacts, the agent responds to the primary query first, then gently asks: *"दादा, तुमच्या कांदा पिकाची लागवड कोणत्या तारखेला झाली होती?"*
3. Farmer replies: *"गेल्या महिन्याच्या 15 तारखेला लागवड केली"* (Planting was on 15th of last month).
4. Information Extraction module parses date (`2026-10-15`), validates it, updates `farm_profiles.planting_date` with status `UNVERIFIED_FARMER_INPUT`.
5. System acknowledges and records the state, progressing to the next pending field (`npk_values`) in subsequent turns.

### Flow 3: CDO Coordination for Missing Critical Data
1. System detects that farmer is missing sugar factory register ID or soil fertility report required for cane harvesting scheduling.
2. Central Coordinator routes ticket to assigned CDO for the division/factory:
   - Message to CDO: *"CDO साहेब, शेतकरी Popat Rao (गाव: Niphad) यांची माती परीक्षण माहिती व ऊस लागवड तारीख अद्ययावत करणे बाकी आहे. कृपया पडताळणी करावी."*
3. CDO verifies on-site and replies with verified values.
4. System updates farmer record to `VERIFIED` with source `CDO_INPUT` and updates timestamp.

### Flow 4: Agronomist Escalation
1. Farmer uploads photograph of severely wilted sugarcane with red discoloration in internal stem tissue.
2. Vision model identifies symptoms consistent with Red Rot (*Colletotrichum falcatum*), a catastrophic pathogen.
3. System classifies issue as `URGENT_DISEASE_ESCALATION` (High Priority).
4. System creates record in `issues` table with status `ASSIGNED_TO_AGRONOMIST`, attaches photo evidence and farmer profile, and sends an alert to the on-duty agronomist.
5. Farmer receives interim message: *"तुमच्या उसाच्या पिकाची लक्षणे गंभीर दिसत आहेत. आमचे कृषी तज्ज्ञ यावर तात्काळ तपासणी करत असून लवकरच मार्गदर्शन करतील."*
6. Agronomist reviews via coordinator dashboard, confirms fungicide/field management advice, and approves dispatch.

---

## 4. Phase 2 Relational Database Schema Design (Preview)

The database will be implemented using SQLAlchemy ORM with support for PostgreSQL (production) and SQLite (local testing):

```
Table: farmers
- id: UUID / Integer (Primary Key)
- farmer_id: String (Unique, e.g. "FAR-MH-NAS-00102")
- full_name: String
- primary_phone: String (Unique, indexed, 10 digits)
- secondary_phone: String (Optional)
- village: String
- tehsil: String
- district: String (Indexed)
- division: String
- factory_id: ForeignKey(factories.id)
- assigned_cdo_id: ForeignKey(cdos.id)
- preferred_language: String (Default: 'mr')
- created_at: DateTime
- updated_at: DateTime

Table: farm_profiles
- id: UUID / Integer (Primary Key)
- farmer_id: ForeignKey(farmers.id)
- total_land_area_acres: Float
- crop_name: String (Indexed)
- crop_variety: String
- planting_date: Date
- planting_season: String (Suru, Adsali, Pre-seasonal, Kharif, Rabi)
- growth_stage: String (Sowing, Vegetative, Tillering, Flowering, Harvesting)
- irrigation_type: String (Drip, Sprinkler, Flood, Rainfed)
- verification_status: Enum (VERIFIED, UNVERIFIED, MISSING, NEEDS_CORRECTION)
- last_updated_by: String

Table: soil_profiles
- id: UUID / Integer (Primary Key)
- farmer_id: ForeignKey(farmers.id)
- soil_type: String (Black Cotton, Alluvial, Red, Sandy Loam)
- ph_level: Float
- electrical_conductivity: Float
- organic_carbon_pct: Float
- nitrogen_n_kg_ha: Float
- phosphorus_p_kg_ha: Float
- potassium_k_kg_ha: Float
- soil_health_card_number: String
- verification_status: Enum (VERIFIED, UNVERIFIED, MISSING, NEEDS_CORRECTION)

Table: cdo_directory
- id: UUID / Integer (Primary Key)
- cdo_code: String (Unique)
- name: String
- phone_number: String (Unique)
- email: String
- factory_name: String
- division: String
- active: Boolean

Table: agronomist_directory
- id: UUID / Integer (Primary Key)
- name: String
- phone_number: String
- specialization: String (Sugarcane Pathology, Soil Fertility, Entomology)
- active: Boolean

Table: conversation_sessions
- id: UUID / Integer (Primary Key)
- farmer_phone: String (Indexed)
- current_state: String (AWAITING_QUERY, COLLECTING_INFO, AWAITING_CLARIFICATION)
- pending_fields: JSON (List of missing fields currently being pursued)
- last_interaction: DateTime

Table: issues
- id: String (Primary Key, e.g. "ISS-202611-0042")
- farmer_id: ForeignKey(farmers.id)
- category: String (Disease, Nutrient, Irrigation, Scheme, Administrative)
- priority: Enum (LOW, MEDIUM, HIGH, CRITICAL)
- status: Enum (NEW, AWAITING_FARMER, AWAITING_CDO, ASSIGNED_AGRONOMIST, IN_PROGRESS, RESOLVED, CLOSED)
- description: Text
- media_urls: JSON
- assigned_cdo_id: ForeignKey(cdos.id, Nullable)
- assigned_agronomist_id: ForeignKey(agronomists.id, Nullable)
- resolution_notes: Text
- created_at: DateTime
- resolved_at: DateTime

Table: audit_logs
- id: UUID / Integer (Primary Key)
- timestamp: DateTime (Indexed)
- sender_phone: String
- direction: Enum (INBOUND, OUTBOUND)
- category: String
- action_taken: String
- rag_sources_used: JSON
- processing_time_ms: Float
- is_escalated: Boolean
- resolved: Boolean
```
