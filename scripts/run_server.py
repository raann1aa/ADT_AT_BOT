"""
FastAPI Server Runner for WhatsApp Farmer AI Agent.
Runs Uvicorn server on http://localhost:8000.
Usage:
    python scripts/run_server.py [--port 8000] [--reload]
"""

import sys
import argparse
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import uvicorn

def main():
    parser = argparse.ArgumentParser(description="Start KrishiBot WhatsApp Webhook & RAG Server.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    print("=" * 75)
    print("🌾 STARTING KRISHIBOT WHATSAPP GATEWAY & RAG SERVICE")
    print("=" * 75)
    print(f"🚀 Server running on : http://{args.host}:{args.port}")
    print(f"📖 API Documentation : http://localhost:{args.port}/docs")
    print(f"🔗 Meta Webhook URL  : http://localhost:{args.port}/webhook")
    print("=" * 75)

    uvicorn.run("gateway.webhook_server:app", host=args.host, port=args.port, reload=args.reload)

if __name__ == "__main__":
    main()
