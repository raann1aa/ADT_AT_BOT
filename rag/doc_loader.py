import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

try:
    import yaml
except ImportError:
    yaml = None

@dataclass
class KnowledgeDocument:
    """Represents a loaded agricultural document with its metadata."""
    doc_id: str
    file_path: Path
    title: str
    category: str
    crops: List[str] = field(default_factory=list)
    seasons: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    summary: str = ""
    content: str = ""
    raw_frontmatter: Dict[str, Any] = field(default_factory=dict)

class MarkdownKBLoader:
    """Recursively scans and parses Markdown documents from the knowledge base directory."""

    def __init__(self, kb_dir: Path):
        self.kb_dir = Path(kb_dir)

    def load_all(self) -> List[KnowledgeDocument]:
        """Loads all .md files found in the knowledge base directory."""
        if not self.kb_dir.exists():
            raise FileNotFoundError(f"Knowledge base directory not found at: {self.kb_dir}")

        md_files = sorted(list(self.kb_dir.rglob("*.md")))
        documents = []

        for md_file in md_files:
            # Skip hidden files or README if in root
            if md_file.name.startswith(".") or md_file.name.lower() == "readme.md":
                continue
            doc = self.parse_file(md_file)
            if doc:
                documents.append(doc)

        return documents

    def parse_file(self, file_path: Path) -> Optional[KnowledgeDocument]:
        """Parses a single markdown document with YAML frontmatter."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return None

        frontmatter, body = self._split_frontmatter(text)
        
        # Deduce category from folder name if not provided in frontmatter
        rel_dir = file_path.parent.relative_to(self.kb_dir) if file_path.is_relative_to(self.kb_dir) else ""
        default_category = str(rel_dir).replace("\\", "/") or "general"

        title = frontmatter.get("title") or file_path.stem.replace("_", " ").title()
        category = frontmatter.get("category") or default_category
        crops = frontmatter.get("crops") or []
        seasons = frontmatter.get("seasons") or []
        keywords = frontmatter.get("keywords") or []
        summary = frontmatter.get("summary") or ""

        # Normalize crops and keywords to lists of lower-case strings
        if isinstance(crops, str):
            crops = [c.strip().lower() for c in crops.split(",")]
        else:
            crops = [str(c).strip().lower() for c in crops]

        if isinstance(keywords, str):
            keywords = [k.strip().lower() for k in keywords.split(",")]
        else:
            keywords = [str(k).strip().lower() for k in keywords]

        if isinstance(seasons, str):
            seasons = [s.strip() for s in seasons.split(",")]

        doc_id = f"{category}_{file_path.stem}"

        return KnowledgeDocument(
            doc_id=doc_id,
            file_path=file_path,
            title=title,
            category=category,
            crops=crops,
            seasons=seasons,
            keywords=keywords,
            summary=summary,
            content=body.strip(),
            raw_frontmatter=frontmatter
        )

    def _split_frontmatter(self, text: str) -> tuple[Dict[str, Any], str]:
        """Extracts YAML frontmatter if present between triple dashes ---."""
        pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
        match = re.match(pattern, text, re.DOTALL)
        if not match:
            return {}, text

        yaml_text, body = match.groups()
        metadata: Dict[str, Any] = {}

        if yaml:
            try:
                metadata = yaml.safe_load(yaml_text) or {}
            except Exception:
                metadata = self._fallback_yaml_parse(yaml_text)
        else:
            metadata = self._fallback_yaml_parse(yaml_text)

        return metadata, body

    def _fallback_yaml_parse(self, yaml_text: str) -> Dict[str, Any]:
        """Lightweight key-value parser if PyYAML is not present."""
        data = {}
        for line in yaml_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if v.startswith("[") and v.endswith("]"):
                    items = [item.strip().strip('"').strip("'") for item in v[1:-1].split(",") if item.strip()]
                    data[k] = items
                else:
                    data[k] = v
        return data
