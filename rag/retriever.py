import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from .vector_store import ChromaVectorStore
from .embedding_manager import LocalSentenceTransformerEmbedding

@dataclass
class RetrievedChunk:
    """Represents a single retrieved chunk with its text, similarity score, and metadata."""
    chunk_id: str
    doc_id: str
    title: str
    category: str
    section_title: str
    text: str
    similarity_score: float  # Cosine similarity + lexical boost (0.0 to 1.0)
    metadata: Dict[str, Any]

class FarmingRetriever:
    """
    Retrieves and filters knowledge chunks relevant to a farmer's question.
    Employs hybrid scoring: dense semantic vectors + domain keyword boosting.
    """

    def __init__(self, vector_store: ChromaVectorStore):
        self.vector_store = vector_store

    def retrieve(
        self,
        query: str,
        top_k: int = 4,
        category: Optional[str] = None,
        crop: Optional[str] = None,
        min_similarity: float = 0.20
    ) -> List[RetrievedChunk]:
        """
        Retrieves top_k relevant chunks for a user query.
        """
        expanded_query = LocalSentenceTransformerEmbedding.expand_query(query)

        where_filter = None
        conditions = []
        if category:
            conditions.append({"category": category})
        
        if len(conditions) == 1:
            where_filter = conditions[0]
        elif len(conditions) > 1:
            where_filter = {"$and": conditions}

        # Fetch extra candidates for hybrid re-ranking
        fetch_k = max(top_k * 4, 12)
        raw_results = self.vector_store.query(
            query_text=expanded_query,
            n_results=fetch_k,
            where=where_filter
        )

        documents = raw_results.get("documents", [[]])[0]
        metadatas = raw_results.get("metadatas", [[]])[0]
        distances = raw_results.get("distances", [[]])[0]

        candidates: List[RetrievedChunk] = []

        # Tokenize query for lexical overlap (ignoring very short stop words)
        q_tokens = set(re.findall(r"\w+", query.lower() + " " + expanded_query.lower()))
        stop_words = {"in", "on", "at", "for", "the", "a", "an", "is", "of", "and", "me", "ka", "ki", "ke", "hai", "kare", "ko", "se", "aur", "kya", "kar"}
        informative_q_tokens = {t for t in q_tokens if t not in stop_words and len(t) > 1}

        for doc_text, meta, distance in zip(documents, metadatas, distances):
            # Base cosine similarity
            base_similarity = max(0.0, 1.0 - distance)

            # Crop filter
            if crop:
                crop_lower = crop.lower()
                doc_crops = meta.get("crops", "").lower()
                if crop_lower not in doc_crops and crop_lower not in meta.get("title", "").lower():
                    continue

            # Lexical boost: check matching tokens in doc title, section, and keywords
            doc_context_text = f"{meta.get('title', '')} {meta.get('section_title', '')} {meta.get('keywords', '')}".lower()
            doc_tokens = set(re.findall(r"\w+", doc_context_text))
            
            matching_tokens = informative_q_tokens.intersection(doc_tokens)
            
            # Additional penalty/boost for disambiguation: e.g. "pm kisan" vs "kcc"
            lexical_boost = 0.0
            if "kisan" in informative_q_tokens and "pm" in informative_q_tokens:
                if "pm-kisan" in doc_context_text or "pm kisan" in doc_context_text:
                    lexical_boost += 0.25
                elif "credit card" in doc_context_text:
                    lexical_boost -= 0.15

            if matching_tokens:
                lexical_boost += min(0.20, len(matching_tokens) * 0.04)

            combined_score = min(0.99, max(0.0, base_similarity + lexical_boost))

            if combined_score < min_similarity:
                continue

            chunk = RetrievedChunk(
                chunk_id=meta.get("chunk_id", ""),
                doc_id=meta.get("doc_id", ""),
                title=meta.get("title", ""),
                category=meta.get("category", ""),
                section_title=meta.get("section_title", ""),
                text=doc_text,
                similarity_score=round(combined_score, 4),
                metadata=meta
            )
            candidates.append(chunk)

        # Sort candidates by combined score descending
        candidates.sort(key=lambda c: c.similarity_score, reverse=True)

        return candidates[:top_k]

    def format_context_for_llm(self, chunks: List[RetrievedChunk]) -> str:
        """
        Formats retrieved chunks into a clean, well-delimited string
        ready for injection into the Gemini/LLM system prompt.
        """
        if not chunks:
            return "No relevant farming knowledge found in the database."

        formatted_pieces = []
        for i, chunk in enumerate(chunks, 1):
            source_tag = f"Source {i}: {chunk.title} ({chunk.category}) | Section: {chunk.section_title} [Confidence: {chunk.similarity_score:.0%}]"
            formatted_pieces.append(f"--- {source_tag} ---\n{chunk.text}")

        return "\n\n".join(formatted_pieces)
