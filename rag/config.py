import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

# Base project paths
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_KB_DIR = BASE_DIR / "knowledge_base"
DEFAULT_DB_DIR = BASE_DIR / "data" / "chroma_db"

@dataclass
class RAGConfig:
    """Configuration settings for the Farming RAG pipeline."""
    # File Paths
    kb_dir: Path = field(default_factory=lambda: DEFAULT_KB_DIR)
    db_dir: Path = field(default_factory=lambda: DEFAULT_DB_DIR)
    
    # ChromaDB Collection
    collection_name: str = "farming_knowledge_base"
    
    # Embedding Model Settings
    # Default is the locally cached sentence-transformers/all-MiniLM-L6-v2 model
    embedding_model_name: str = field(
        default_factory=lambda: os.environ.get("EMBEDDING_MODEL_PATH")
        or os.environ.get("EMBEDDING_MODEL_NAME")
        or "sentence-transformers/all-MiniLM-L6-v2"
    )
    local_files_only: bool = field(
        default_factory=lambda: os.environ.get("EMBEDDING_LOCAL_FILES_ONLY", "true").lower() in ("1", "true", "yes")
    )
    embedding_dimension: int = 384
    
    # Chunking Parameters
    chunk_size: int = 600          # Target character length per chunk
    chunk_overlap: int = 100       # Overlap between consecutive chunks
    min_chunk_size: int = 80       # Discard trivial tiny chunks
    
    # Retrieval Settings
    default_top_k: int = 4         # Number of chunks to return for WhatsApp prompt context
    distance_metric: str = "cosine" # Cosine similarity
    similarity_threshold: float = 0.75 # Minimum acceptable cosine similarity
    
    # Optional API Keys for Cloud Embedding / LLM
    gemini_api_key: Optional[str] = field(
        default_factory=lambda: os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    )
    
    def validate(self) -> None:
        """Ensure necessary directories exist or can be created."""
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        self.db_dir.mkdir(parents=True, exist_ok=True)
