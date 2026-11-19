# 🌾 WhatsApp Farmer AI Agent — Agricultural RAG Pipeline (Phase A)

An AI-driven Retrieval-Augmented Generation (RAG) engine designed for Indian agricultural WhatsApp farmer groups. It ingests domain-verified agricultural knowledge (crops, pests, soils, fertilizers, schemes, irrigation) and performs semantic and hybrid retrieval for queries in **English**, **Hindi (Devanagari)**, and **Hinglish**.

---

## 📁 Project Architecture

```
ADT-AI-Chatbot/
├── knowledge_base/               # Curated Agricultural Knowledge (Markdown + Frontmatter)
│   ├── crops/                   # Wheat, Rice, Cotton, Sugarcane, Onion, Tomato, Soybean, etc.
│   ├── pests_diseases/          # Yellow Rust, Pink Bollworm, Fall Armyworm, Leaf Curl, etc.
│   ├── soil/                    # Indian soil types, NPK dosages, Micronutrients, Salinity/pH
│   ├── schemes/                 # PM-KISAN, PMFBY 72-hr rule, KCC 4% interest, KUSUM, etc.
│   └── irrigation_weather/      # Drip acid treatment, Critical irrigation stages, Frost/Heatwave
├── rag/                         # Core RAG Engine Package (Phase A)
│   ├── config.py                # Pipeline settings, chunk sizes, collection configuration
│   ├── doc_loader.py            # Markdown loader with YAML frontmatter parser
│   ├── chunker.py               # Semantic section-based chunker with breadcrumbs
│   ├── embedding_manager.py     # Local SentenceTransformer embedding + bilingual expansion
│   ├── vector_store.py          # Persistent ChromaDB collection manager
│   ├── retriever.py             # Hybrid dense-semantic + lexical re-ranking
│   └── pipeline.py              # FarmingRAGPipeline unified interface
├── agent/                       # Master Agent & Classifier Package (Phase B)
│   ├── classifier.py            # Hybrid Message Classifier (Noise/Spam/Query/Form/Distress)
│   ├── prompts.py               # Optimized prompts for KrishiBot, language adaptation & safety
│   ├── llm_client.py            # Google Gemini LLM Client + Local Extractive Fallback
│   ├── response_formatter.py    # WhatsApp formatting (bold, bullets, character limits)
│   └── farmer_agent.py          # Central FarmerAgent orchestrating Classifier + RAG + LLM
├── gateway/                     # WhatsApp Webhook & Gateway Service (Phase 1)
│   ├── whatsapp_client.py       # Meta Cloud API (v21.0) client + dry-run simulator
│   ├── group_manager.py         # Multi-district WhatsApp group directory
│   └── webhook_server.py        # Production FastAPI server (Webhook, Forms, Excel sync)
├── form_automation/             # Google Form & Excel Synchronization (Phase 4)
│   ├── models.py                # Pydantic models for farmer submissions & district groups
│   ├── excel_manager.py         # Excel workbook manager (O(1) phone lookup cache)
│   └── form_broadcast.py        # Localized weekly Google Form link broadcaster
├── scripts/
│   ├── ingest_knowledge_base.py # Ingestion CLI to chunk and index docs into ChromaDB
│   ├── test_retrieval.py        # Automated multi-lingual retrieval verification test suite
│   ├── test_phase_b.py          # Comprehensive test suite for Classifier & Agent pipeline
│   ├── simulate_whatsapp_group.py # Live WhatsApp district group chat simulation
│   ├── test_webhook_flow.py     # End-to-end integration test (Webhook, Excel, Broadcast)
│   ├── run_server.py            # FastAPI server runner on port 8000
│   └── interactive_cli.py       # Live interactive terminal query console
├── data/
│   ├── chroma_db/               # Persistent ChromaDB vector storage on disk
│   └── farmer_profiles.xlsx     # Live Excel database of registered farmers
├── requirements.txt             # Python dependencies
└── README.md
```

---

## 🚀 Quickstart & Verification

### 1. Ingest Knowledge Base (Phase A)
```bash
python scripts/ingest_knowledge_base.py --force
```

### 2. Run Automated Verification Tests
- **RAG Retrieval Tests (Phase A):**
  ```bash
  python scripts/test_retrieval.py
  ```
- **Message Classifier & End-to-End Agent Tests (Phase B):**
  ```bash
  python scripts/test_phase_b.py
  ```
  *Current benchmark: **100% Classifier Accuracy** and **100% End-to-End Scenario Success**.*

### 3. Run Live WhatsApp Group Simulator (Phase B)
See how KrishiBot automatically filters out greetings, forwards, and spam while answering agricultural questions in a real group:
```bash
python scripts/simulate_whatsapp_group.py
```

### 4. Run WhatsApp Webhook & Excel Server (Phase 1 & 4)
Start the FastAPI server on port 8000:
```bash
python scripts/run_server.py
```
- Interactive Swagger API docs: `http://localhost:8000/docs`
- Meta Cloud API Webhook URL: `http://localhost:8000/webhook`

### 5. Run Full End-to-End Integration Suite
Tests Meta Webhook verification, Excel farmer profile lookup, incoming message deduplication, and Google Form broadcast:
```bash
python scripts/test_webhook_flow.py
```
*Current benchmark: **All 6/6 Integration Tests Passed (100%)**.*

---

## 🧠 Key Innovations in Phase A

1. **Bilingual Query Expansion (`rag/embedding_manager.py`)**:
   Standard English-centric embeddings (like `all-MiniLM-L6-v2`) typically struggle with Devanagari Hindi or regional transliterations. Our query pre-processor expands terms like `"गेहूं में पीला रतुआ"` or `"gulabi sundi"` into canonical concepts, ensuring 0% token loss.
2. **Context-Aware Breadcrumb Chunking (`rag/chunker.py`)**:
   Instead of blind character splits, documents are split on section boundaries (`##`, `###`), and each chunk receives a title breadcrumb (e.g. `[Wheat Cultivation > Critical Irrigation Stages]`).
3. **Hybrid Re-Ranking (`rag/retriever.py`)**:
   Combines dense cosine similarity with lexical domain keyword matching to eliminate near-misses between overlapping government schemes or pest names.
4. **100% Offline & Local**:
   Runs completely on local CPU without incurring API charges or internet dependencies during retrieval.

---

## 🔜 Next Steps (Phase B)
- Connect Google Gemini 1.5 Pro via LangChain / Gemini API
- WhatsApp Message Preprocessor & Classifier (answer vs. ignore spam)
- Prompt template injecting retrieved context and farmer profile
