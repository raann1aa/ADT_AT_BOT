# PROJECT CONTEXT: AI-POWERED FARMER COMMUNICATION AND AGRICULTURAL SUPPORT AUTOMATION SYSTEM

## 1. Project Identity & Master Context

- **Project Name:** AI-Powered Farmer Communication and Agricultural Support Automation System (Extending KrishiBot)
- **Base Repository:** `https://github.com/PranavShelar17/ADT-AI-BOT`
- **Target Role Automaton:** Agricultural Communication Coordinator
- **Core Stakeholders:**
  1. **Farmers:** Smallholders and progressive farmers across Maharashtra, Madhya Pradesh, and Punjab producing sugarcane, onion, cotton, soybean, wheat, rice, chilli, tomato, and vegetables.
  2. **Cane Development Officers (CDOs):** Field agricultural extension officers assigned to sugar factories and division clusters responsible for ground-level verification and farmer coordination.
  3. **Agronomists & Domain Experts:** Senior agricultural scientists and crop specialists handling complex pathologies, soil chemistry, and high-risk advisories.
  4. **Communication Coordinator:** Human operator overseeing incoming farmer inquiries, data collection, escalation triage, and follow-ups.

---

## 2. Core Problem Statement

The agricultural communication coordinator currently spends hundreds of manual hours per week managing high-volume communication across multiple channels and WhatsApp groups. Key responsibilities include:

1. Communicating with farmers via WhatsApp.
2. Sending routine and periodic requests to farmers for vital agronomic data.
3. Collecting, validating, and recording farm parameters:
   - Farmer identity (name, phone, village, taluka, district, division, factory).
   - Planting dates and seasons (Kharif, Rabi, Zaid, Adsali, Pre-seasonal, Suru).
   - Farm landholding area and crop acreage.
   - Soil profile: Soil type, pH, electrical conductivity (EC), organic carbon, and NPK values.
   - Irrigation methods (drip, sprinkler, flood) and water quality.
   - Crop growth stage, variety, and health status.
4. Monitoring farmer WhatsApp groups and direct communication channels.
5. Reading and filtering farmer questions, feedback, and complaints.
6. Responding to farmers fluently in **Marathi (मराठी)**, **Hindi (हिंदी)**, and **English**.
7. Requesting supplementary information when farmer queries lack essential diagnostic context.
8. Coordinating with the responsible CDO when farmer records are missing or require field visits.
9. Escalating high-risk or complex agricultural issues to agronomists with complete evidentiary history.
10. Tracking pending responses, scheduling reminders, and conducting follow-ups until issues reach confirmed resolution.

Farmers frequently communicate using voice notes, photographic evidence of crop damage, videos of field conditions, and regional/colloquial phrasing.

---

## 3. System Final Objective

Transform the prototype KrishiBot chatbot into an enterprise-grade, reliable, multi-stakeholder communication and workflow automation system that:
- Seamlessly receives and parses farmer messages across text, voice notes, photographs, and video clips.
- Uniquely and reliably identifies farmers using telephone numbers and persistent database records.
- Comprehends multilingual messages (Marathi, Hindi, English, Hinglish, and Romanized Marathi).
- Delivers grounded, scientifically accurate agricultural advisories strictly using domain-verified RAG knowledge.
- Collects missing farm data through natural, multi-turn conversational interviews without annoying the farmer.
- Retains context across conversations and tracks active issues over time.
- Automatically assigns, alerts, and coordinates with CDOs based on factory and division geography.
- Escalates critical crop diseases and emergencies to agronomists with human-in-the-loop oversight.
- Equips the communication coordinator with an operational analytics and management dashboard.

---

## 4. Mandatory Development Instructions & Compliance Rules

1. **No Rebuilds from Scratch:** Extend the existing repository architecture (`agent/`, `rag/`, `gateway/`, `form_automation/`).
2. **Inspect Before Changing:** Every modification must be preceded by static code analysis and live verification.
3. **Reuse Working Code:** Preserve functional modules (ChromaDB vector store, document loaders, chunker, response formatting).
4. **Approval for Deletions:** No existing feature or file may be deleted without documented rationale and explicit approval.
5. **Preserve RAG Pipeline:** Retain the hybrid semantic + lexical retrieval engine unless a technical incompatibility is proven.
6. **Lean Dependencies:** Do not introduce unneeded third-party libraries or monolithic orchestration frameworks.
7. **Zero Hardcoded Secrets:** API keys, database credentials, access tokens, and phone numbers must reside in environment variables.
8. **Persistent Storage:** All operational data, profiles, conversations, and issue histories must reside in persistent storage (not volatile memory or loose Excel workbooks).
9. **Backward Compatibility:** Existing webhook endpoints and CLI utilities must continue to operate.
10. **Modular, Tested Code:** Every significant component must include automated unit/integration tests with documented execution logs.
11. **Empirical Verification:** Never claim a feature works without verifiable test output.
12. **Zero Hallucination Policy:** Never fabricate agronomic recommendations, dosages, farmer records, or expert quotes. If knowledge is missing, escalate.
13. **Human Review for Risk:** High-risk chemical applications or uncertain diagnoses require coordinator/agronomist confirmation.
14. **Official WhatsApp API Compliance:** Adhere strictly to the official Meta WhatsApp Business Cloud API specification. Never rely on unofficial scrapers or reverse-engineered WhatsApp Web wrappers.
15. **Strict Incremental Phases:** Execute one phase at a time; generate full documentation and await approval before advancing.

---

## 5. WhatsApp API & Messaging Protocol Realities

### Meta Cloud API (v21.0) Capabilities:
- **Individual Peer-to-Peer Messaging (1-to-1):** Full bidirectional support for text messages, media upload/download (audio, images, videos, documents), template messages, and interactive buttons/lists.
- **Webhook Events:** Real-time push delivery of incoming messages, media IDs, read receipts, and delivery statuses.
- **Group Messaging Constraints:**
  - *Standard Meta WhatsApp Cloud API does not support bots participating as members in standard WhatsApp groups.*
  - The existing codebase uses a group simulation model (`group_manager.py` and `simulate_whatsapp_group.py`) and passes group IDs into `to` fields in dry-run mode.
  - In production, direct coordinator-farmer communication, CDO alerts, and agronomist notifications operate via 1-to-1 WhatsApp messages or approved template messages within the 24-hour service window.

---

## 6. Language & Localization Requirements

The target agricultural belt covers Maharashtra (Vidarbha, Marathwada, Western Maharashtra) and central India:
- **Primary Regional Language:** Marathi (मराठी) — Devanagari script and Romanized transliteration (e.g., *"Kandyala karpa aala aahe, kay karu?"*).
- **Secondary National Language:** Hindi (हिंदी) — Devanagari script and Hinglish.
- **Administrative Language:** English — for technical reports, agronomist logs, and coordinator interfaces.
- **Terminology Preservation:** Botanical names, chemical active ingredients (e.g., *Propiconazole 25% EC*, *Chlorantraniliprole 18.5% SC*), government scheme acronyms (*PMFBY*, *PM-KISAN*, *KCC*), and regional agronomic units (*guntha*, *bigha*, *acre*, *quintal*).
