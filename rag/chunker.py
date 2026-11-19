import re
from dataclasses import dataclass
from typing import List, Dict, Any
from .doc_loader import KnowledgeDocument

@dataclass
class DocumentChunk:
    """Represents an indexable chunk with semantic text and metadata."""
    chunk_id: str
    doc_id: str
    text: str
    section_title: str
    metadata: Dict[str, Any]

class MarkdownSemanticChunker:
    """
    Context-aware markdown chunker that respects section boundaries (##, ###)
    and prefixes each chunk with title/section breadcrumbs for maximum semantic clarity.
    """

    def __init__(self, chunk_size: int = 600, chunk_overlap: int = 100, min_chunk_size: int = 80):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def chunk_document(self, doc: KnowledgeDocument) -> List[DocumentChunk]:
        """Splits a KnowledgeDocument into high-quality semantic chunks."""
        sections = self._split_into_sections(doc.content)
        chunks: List[DocumentChunk] = []
        chunk_idx = 0

        for section_heading, section_text in sections:
            # Generate small sub-chunks if section is too long
            sub_texts = self._split_text_with_overlap(section_text)

            for sub_text in sub_texts:
                if len(sub_text.strip()) < self.min_chunk_size:
                    continue

                # Build a semantic header breadcrumb
                breadcrumb = f"[{doc.title} > {section_heading}]\n"
                full_chunk_text = breadcrumb + sub_text.strip()

                chunk_id = f"{doc.doc_id}_c{chunk_idx:03d}"

                metadata = {
                    "chunk_id": chunk_id,
                    "doc_id": doc.doc_id,
                    "title": doc.title,
                    "category": doc.category,
                    "section_title": section_heading,
                    "crops": ",".join(doc.crops),
                    "seasons": ",".join(doc.seasons),
                    "keywords": ",".join(doc.keywords[:15]),
                    "source_file": doc.file_path.name
                }

                chunks.append(DocumentChunk(
                    chunk_id=chunk_id,
                    doc_id=doc.doc_id,
                    text=full_chunk_text,
                    section_title=section_heading,
                    metadata=metadata
                ))
                chunk_idx += 1

        return chunks

    def _split_into_sections(self, content: str) -> List[tuple[str, str]]:
        """Splits markdown text on markdown headers (# , ## , ### )."""
        lines = content.splitlines()
        sections: List[tuple[str, str]] = []
        
        current_heading = "General"
        current_lines: List[str] = []

        header_regex = re.compile(r"^(#{1,4})\s+(.+)$")

        for line in lines:
            match = header_regex.match(line.strip())
            if match:
                # If we accumulated lines, save previous section
                if current_lines:
                    text = "\n".join(current_lines).strip()
                    if text:
                        sections.append((current_heading, text))
                    current_lines = []
                current_heading = match.group(2).strip()
            else:
                current_lines.append(line)

        # Flush final section
        if current_lines:
            text = "\n".join(current_lines).strip()
            if text:
                sections.append((current_heading, text))

        return sections if sections else [("General", content.strip())]

    def _split_text_with_overlap(self, text: str) -> List[str]:
        """Splits text into chunks respecting paragraphs and sentences."""
        if len(text) <= self.chunk_size:
            return [text]

        paragraphs = text.split("\n\n")
        chunks: List[str] = []
        current_chunk = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) + 2 <= self.chunk_size:
                current_chunk = f"{current_chunk}\n\n{para}".strip()
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                # If paragraph itself is larger than chunk_size, split by lines/sentences
                if len(para) > self.chunk_size:
                    sub_pieces = self._split_large_paragraph(para)
                    chunks.extend(sub_pieces[:-1])
                    current_chunk = sub_pieces[-1] if sub_pieces else ""
                else:
                    current_chunk = para

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    def _split_large_paragraph(self, para: str) -> List[str]:
        """Splits a very long paragraph by punctuation or line boundaries."""
        sentences = re.split(r"(?<=[.!?।\n])\s+", para)
        pieces: List[str] = []
        current = ""

        for s in sentences:
            if len(current) + len(s) + 1 <= self.chunk_size:
                current = f"{current} {s}".strip()
            else:
                if current:
                    pieces.append(current)
                current = s

        if current:
            pieces.append(current)

        return pieces if pieces else [para[:self.chunk_size]]
