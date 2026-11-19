"""
Script to ingest the agricultural knowledge base into ChromaDB.
Usage:
    python scripts/ingest_knowledge_base.py [--force]
"""

import sys
import argparse
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from rag.pipeline import FarmingRAGPipeline
from rag.config import RAGConfig

def main():
    parser = argparse.ArgumentParser(description="Ingest farming documents into ChromaDB vector store.")
    parser.add_argument("--force", action="store_true", help="Force wipe and rebuild the vector collection.")
    args = parser.parse_args()

    print("=" * 70)
    print("🌾 FARMER AI AGENT - KNOWLEDGE BASE INGESTION PIPELINE")
    print("=" * 70)

    config = RAGConfig()
    print(f"📁 Knowledge Base Dir : {config.kb_dir}")
    print(f"💾 Vector DB Dir      : {config.db_dir}")
    print(f"🧠 Embedding Model    : {config.embedding_model_name}")
    print(f"📦 Collection Name    : {config.collection_name}")
    print(f"🔄 Force Reload       : {args.force}")
    print("-" * 70)

    pipeline = FarmingRAGPipeline(config=config)
    result = pipeline.ingest(force_reload=args.force)

    print("\n" + "=" * 70)
    print("✅ INGESTION COMPLETED SUCCESSFULLY!")
    print("=" * 70)
    print(f"📄 Documents Loaded   : {result['documents_loaded']}")
    print(f"🧩 Chunks Indexed     : {result['chunks_indexed']}")
    print(f"🗄️ Total in Vector DB : {result['total_chunks_in_db']}")
    print(f"⏱️ Time Taken         : {result['time_seconds']} seconds")
    print(f"🏷️ Categories Found   : {', '.join(result['categories'])}")
    print("=" * 70)

if __name__ == "__main__":
    main()
