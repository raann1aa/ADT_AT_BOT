import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from .config import RAGConfig
from .doc_loader import MarkdownKBLoader, KnowledgeDocument
from .chunker import MarkdownSemanticChunker, DocumentChunk
from .embedding_manager import LocalSentenceTransformerEmbedding
from .vector_store import ChromaVectorStore
from .retriever import FarmingRetriever, RetrievedChunk

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("FarmingRAGPipeline")

class FarmingRAGPipeline:
    """
    Unified end-to-end RAG pipeline for the WhatsApp Farmer Bot.
    Manages document loading, semantic chunking, vector indexing,
    and hybrid retrieval.
    """

    def __init__(self, config: Optional[RAGConfig] = None):
        self.config = config or RAGConfig()
        self.config.validate()

        self.loader = MarkdownKBLoader(kb_dir=self.config.kb_dir)
        self.chunker = MarkdownSemanticChunker(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
            min_chunk_size=self.config.min_chunk_size
        )
        self.embedding_fn = LocalSentenceTransformerEmbedding(
            model_name=self.config.embedding_model_name,
            local_files_only=self.config.local_files_only
        )
        self.vector_store = ChromaVectorStore(
            persist_directory=self.config.db_dir,
            collection_name=self.config.collection_name,
            embedding_function=self.embedding_fn
        )
        self.retriever = FarmingRetriever(vector_store=self.vector_store)

    def ingest(self, force_reload: bool = False) -> Dict[str, Any]:
        """
        Parses all knowledge base markdown documents, chunks them,
        and indexes them into ChromaDB.
        """
        start_time = time.time()
        logger.info(f"Starting knowledge base ingestion from {self.config.kb_dir}...")

        if force_reload:
            logger.info("force_reload=True: Clearing existing vector collection...")
            self.vector_store.reset()

        # Step 1: Load documents
        documents = self.loader.load_all()
        logger.info(f"Loaded {len(documents)} markdown knowledge documents.")

        # Step 2: Semantic Chunking
        all_chunks: List[DocumentChunk] = []
        doc_chunk_distribution: Dict[str, int] = {}

        for doc in documents:
            chunks = self.chunker.chunk_document(doc)
            all_chunks.extend(chunks)
            doc_chunk_distribution[doc.doc_id] = len(chunks)

        logger.info(f"Generated {len(all_chunks)} semantic chunks across {len(documents)} documents.")

        # Step 3: Vector Store Upsert
        added_count = self.vector_store.add_chunks(all_chunks, batch_size=64)
        elapsed = round(time.time() - start_time, 2)

        summary = {
            "status": "success",
            "documents_loaded": len(documents),
            "chunks_indexed": added_count,
            "total_chunks_in_db": self.vector_store.count(),
            "time_seconds": elapsed,
            "categories": sorted(list(set(doc.category for doc in documents))),
            "sample_chunk_distribution": dict(list(doc_chunk_distribution.items())[:5])
        }

        logger.info(f"Ingestion completed in {elapsed}s. Total chunks in DB: {summary['total_chunks_in_db']}")
        return summary

    def query(
        self,
        query: str,
        top_k: Optional[int] = None,
        category: Optional[str] = None,
        crop: Optional[str] = None,
        min_similarity: Optional[float] = None
    ) -> List[RetrievedChunk]:
        """
        Retrieves top relevant chunks for a user query.
        """
        k = top_k or self.config.default_top_k
        min_sim = min_similarity if min_similarity is not None else 0.20
        return self.retriever.retrieve(
            query=query,
            top_k=k,
            category=category,
            crop=crop,
            min_similarity=min_sim
        )

    def get_context_for_llm(
        self,
        query: str,
        top_k: Optional[int] = None,
        category: Optional[str] = None,
        crop: Optional[str] = None
    ) -> str:
        """
        Retrieves top relevant chunks and formats them into an LLM-ready context block.
        """
        chunks = self.query(query=query, top_k=top_k, category=category, crop=crop)
        return self.retriever.format_context_for_llm(chunks)

    def stats(self) -> Dict[str, Any]:
        """Returns statistics about the current RAG database."""
        return {
            "collection_name": self.config.collection_name,
            "chunks_count": self.vector_store.count(),
            "db_directory": str(self.config.db_dir),
            "kb_directory": str(self.config.kb_dir),
            "embedding_model": self.config.embedding_model_name
        }
