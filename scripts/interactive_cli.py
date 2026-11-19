"""
Interactive CLI for querying the Farming RAG knowledge base.
Usage:
    python scripts/interactive_cli.py
"""

import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from rag.pipeline import FarmingRAGPipeline

def main():
    print("=" * 75)
    print("🌾 FARMER AI AGENT - RAG INTERACTIVE QUERY CONSOLE")
    print("=" * 75)
    print("Type your farming question in English, Hindi, or Hinglish.")
    print("Type 'exit' or 'quit' to close.\n")

    pipeline = FarmingRAGPipeline()
    stats = pipeline.stats()
    print(f"📊 Vector Database active with {stats['chunks_count']} knowledge chunks.\n")

    while True:
        try:
            query = input("\n👨‍🌾 Enter Farmer Query > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if not query:
            continue
        if query.lower() in ["exit", "quit", "q"]:
            print("Goodbye! 🚜")
            break

        print("\n🔍 Searching knowledge base...")
        chunks = pipeline.query(query=query, top_k=3)

        if not chunks:
            print("⚠️ No relevant knowledge found.")
            continue

        print(f"\n✅ Found {len(chunks)} relevant knowledge sources:\n" + "-" * 75)
        for idx, chunk in enumerate(chunks, 1):
            print(f"[{idx}] {chunk.title} > {chunk.section_title}")
            print(f"    Category: {chunk.category.upper()} | Confidence: {chunk.similarity_score:.1%}")
            preview = chunk.text.replace("\n", "\n    ")
            print(f"    Content:\n    {preview}\n" + "-" * 75)

if __name__ == "__main__":
    main()
