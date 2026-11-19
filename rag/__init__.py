"""
Farming RAG Engine Package for WhatsApp Farmer Bot.
Provides document parsing, semantic chunking, embedding generation,
ChromaDB vector indexing, and hybrid retrieval.
"""

from .pipeline import FarmingRAGPipeline
from .config import RAGConfig

__all__ = ["FarmingRAGPipeline", "RAGConfig"]
