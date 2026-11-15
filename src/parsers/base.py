"""Document AST and Semantic Node Definitions for KaizenReader.

Enforces Semantic Rigor: documents are structured hierarchies of chapters,
sections, paragraphs, and sentence nodes with deterministic content-hashed IDs
and exact character coordinates.
"""
import hashlib
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field


def deterministic_doc_id(file_path: Path) -> str:
    """Compute a stable 12-char ID from file content so bookmarks survive restarts."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()[:12]


class SentenceNode(BaseModel):
    id: str
    text: str
    skip_tts: bool = False
    char_start: int
    char_end: int


class ParagraphNode(BaseModel):
    id: str
    text: str
    node_type: str = "p"  # "p", "h1", "h2", "h3", "h4", "blockquote", "code", "list_item"
    is_heading: bool = False
    is_code: bool = False
    is_quote: bool = False
    sentences: List[SentenceNode] = Field(default_factory=list)


class Chapter(BaseModel):
    id: str
    index: int
    title: str
    display_title: Optional[str] = None
    category: str = "body"  # "front_matter", "body", "back_matter"
    section_type: str = "chapter"  # "toc", "title_page", "copyright", "introduction", "chapter", "part", "appendix", "index", etc.
    chapter_number: Optional[int] = None
    part_title: Optional[str] = None
    is_toc: bool = False
    is_front_matter: bool = False
    is_back_matter: bool = False
    badge_label: Optional[str] = None
    paragraphs: List[ParagraphNode] = Field(default_factory=list)


class Document(BaseModel):
    id: str
    title: str
    author: str = "Unknown"
    file_format: str
    file_path: Optional[str] = None
    is_sample: bool = False
    created_at: Optional[float] = None
    chapters: List[Chapter] = Field(default_factory=list)
    total_words: int = 0
    total_sentences: int = 0
    total_body_chapters: int = 0
    has_toc: bool = False

    def compute_stats(self):
        from src.parsers.classifier import categorize_document_chapters, filter_empty_part_dividers

        # Filter out empty part divider pages that only repeat the part title
        self.chapters = filter_empty_part_dividers(self.chapters)
        for idx, ch in enumerate(self.chapters):
            ch.index = idx
            ch.id = f"ch_{idx}"

        w_count = 0
        s_count = 0
        for ch in self.chapters:
            for p in ch.paragraphs:
                w_count += len(p.text.split())
                s_count += len(p.sentences)
        self.total_words = w_count
        self.total_sentences = s_count
        self.total_body_chapters = categorize_document_chapters(self.chapters)
        self.has_toc = any(ch.is_toc for ch in self.chapters)
