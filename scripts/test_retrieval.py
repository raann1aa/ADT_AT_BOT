"""
Automated retrieval evaluation test suite for Farming RAG.
Tests realistic farmer queries in English, Hindi, and Hinglish.
Usage:
    python scripts/test_retrieval.py
"""

import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from rag.pipeline import FarmingRAGPipeline

TEST_CASES = [
    {
        "query": "How to treat yellow rust in wheat?",
        "language": "English",
        "expected_topic": "Yellow Rust",
        "expected_crop": "wheat"
    },
    {
        "query": "गेहूं में पीली पत्तियां और पीला रतुआ का इलाज क्या है?",
        "language": "Hindi (Devanagari)",
        "expected_topic": "Yellow Rust",
        "expected_crop": "wheat"
    },
    {
        "query": "Kapas me gulabi sundi ke liye kaun sa spray kare?",
        "language": "Hinglish",
        "expected_topic": "Pink Bollworm",
        "expected_crop": "cotton"
    },
    {
        "query": "PM kisan 6000 installment eKYC kaise kare aur land seeding pending hai",
        "language": "Hinglish (Scheme)",
        "expected_topic": "PM-KISAN",
        "expected_crop": None
    },
    {
        "query": "Mirch me patta marod aur churda murda thrips dawai",
        "language": "Hinglish",
        "expected_topic": "Chilli Leaf Curl",
        "expected_crop": "chilli"
    },
    {
        "query": "Pyaj me kanda sadi aur warehouse storage rot kaise roke?",
        "language": "Hinglish",
        "expected_topic": "Purple Blotch",
        "expected_crop": "onion"
    },
    {
        "query": "Crop insurance claim 72 ghante me kaise kare fasal kharab hone par?",
        "language": "Hinglish (Scheme)",
        "expected_topic": "PM Fasal Bima",
        "expected_crop": None
    },
    {
        "query": "Makka me fall armyworm keede aur whorl ko kaise bachaye?",
        "language": "Hinglish",
        "expected_topic": "Fall Armyworm",
        "expected_crop": "maize"
    },
    {
        "query": "Drip irrigation lateral pipe acid treatment for salt clogging",
        "language": "English (Technical)",
        "expected_topic": "Drip Irrigation Maintenance",
        "expected_crop": None
    },
    {
        "query": "Paddy blast rog me gardan tod aur safed balian stem borer",
        "language": "Hinglish",
        "expected_topic": "Rice Stem Borer",
        "expected_crop": "rice"
    },
    {
        "query": "Tomato me fal fatna aur blossom end rot calcium ki kami",
        "language": "Hinglish",
        "expected_topic": "Tomato",
        "expected_crop": "tomato"
    },
    {
        "query": "1 acre gehu me pehli sinchai kab kare aur urea kitna dale?",
        "language": "Hinglish",
        "expected_topic": "Wheat",
        "expected_crop": "wheat"
    }
]

def run_tests():
    print("=" * 80)
    print("🧪 RUNNING FARMING RAG RETRIEVAL VERIFICATION TEST SUITE")
    print("=" * 80)

    pipeline = FarmingRAGPipeline()
    stats = pipeline.stats()
    print(f"📊 Vector DB chunks loaded: {stats['chunks_count']}\n")

    passed_count = 0
    total_tests = len(TEST_CASES)

    for idx, test in enumerate(TEST_CASES, 1):
        q = test["query"]
        expected = test["expected_topic"].lower()
        lang = test["language"]

        print(f"[{idx}/{total_tests}] Testing ({lang}): \"{q}\"")
        chunks = pipeline.query(query=q, top_k=3)

        if not chunks:
            print("  ❌ FAILED: No chunks returned!\n")
            continue

        # Check top-1 and top-3 hit
        top_chunk = chunks[0]
        titles_in_top3 = [c.title.lower() for c in chunks]
        
        hit_top1 = expected in top_chunk.title.lower()
        hit_top3 = any(expected in t for t in titles_in_top3)

        if hit_top1:
            passed_count += 1
            print(f"  ✅ PASS (Rank 1) [{top_chunk.similarity_score:.1%}]: {top_chunk.title} > {top_chunk.section_title}")
        elif hit_top3:
            passed_count += 1
            print(f"  ⚠️ PASS (Rank 2-3) [{top_chunk.similarity_score:.1%}]: Top was '{top_chunk.title}', found '{expected}' in Top 3")
        else:
            print(f"  ❌ MISS: Expected '{expected}', got: {[c.title for c in chunks]}")

        # Show preview of top snippet
        snippet = top_chunk.text.replace("\n", " ")[:140]
        print(f"     Preview: \"{snippet}...\"\n")

    accuracy = (passed_count / total_tests) * 100
    print("=" * 80)
    print(f"🎯 TEST SUMMARY: {passed_count}/{total_tests} PASSED ({accuracy:.1f}% Top-3 Accuracy)")
    print("=" * 80)

    return passed_count == total_tests

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
