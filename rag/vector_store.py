import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

import chromadb
from chromadb.config import Settings
from .chunker import DocumentChunk
from .embedding_manager import LocalSentenceTransformerEmbedding

logger = logging.getLogger(__name__)

class ChromaVectorStore:
    """
    Manages local persistent vector storage using ChromaDB.
    Persists vectors, text documents, and rich metadata on disk.
    """

    def __init__(
        self,
        persist_directory: Path,
        collection_name: str = "farming_knowledge_base",
        embedding_function: Optional[LocalSentenceTransformerEmbedding] = None
    ):
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name
        self.embedding_function = embedding_function or LocalSentenceTransformerEmbedding()

        # Initialize persistent Chroma client
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(anonymized_telemetry=False)
        )

        # Get or create collection with cosine distance
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine"}
        )

    def add_chunks(self, chunks: List[DocumentChunk], batch_size: int = 64) -> int:
        """
        Adds a list of DocumentChunks into the ChromaDB collection in safe batches.
        Returns the total number of chunks added.
        """
        if not chunks:
            return 0

        total_added = 0
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            
            ids = [chunk.chunk_id for chunk in batch]
            documents = [chunk.text for chunk in batch]
            metadatas = [chunk.metadata for chunk in batch]

            # Upsert into collection
            self.collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
            total_added += len(batch)

        logger.info(f"Upserted {total_added} chunks into collection '{self.collection_name}'")
        return total_added

    def query(
        self,
        query_text: str,
        n_results: int = 4,
        where: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Queries the vector collection for the closest semantic chunks.
        """
        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"]
        )
        return results

    def count(self) -> int:
        """Returns the total number of chunks currently stored in the collection."""
        return self.collection.count()

    def reset(self) -> None:
        """Deletes and recreates the collection."""
        try:
            self.client.delete_collection(name=self.collection_name)
        except Exception as e:
            logger.warning(f"Collection reset warning: {e}")

        self.collection = self.client.create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"Reset collection '{self.collection_name}'")
