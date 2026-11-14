"""PDF Semantic AST Parser.

Applies line-aware structural heuristics: suppresses running headers, footers,
and page numbering, repairs broken line-hyphens, separates standalone headings
from body paragraphs before stitching, and uses deterministic content-hashed IDs.
"""
from pathlib import Path
import re
from pypdf import PdfReader

from src.parsers.base import Document, Chapter, ParagraphNode, SentenceNode, deterministic_doc_id
from src.tts.normalizer import split_into_sentences, unhyphenate

# Patterns that indicate a standalone structural heading line in a PDF
_BOOK_PART_RE = re.compile(
    r'^(Book|Part|Section|Act)\s+([0-9IVXLCDM]+|[A-Z][a-z]+)\b(.*)$',
    re.IGNORECASE,
)
_CHAPTER_RE = re.compile(
    r'^(Chapter|Ch\.?)\s+([0-9IVXLCDM]+|[A-Z][a-z]+)\b(.*)$',
    re.IGNORECASE,
)
_TOC_ENTRY_LINE_RE = re.compile(r'^.+\.{3,}\s*\d+$')


def _is_heading_line(line: str, prev_blank: bool, next_blank: bool) -> tuple[bool, bool]:
    """Return (is_heading, is_chapter_break) for a single stripped PDF line."""
    if len(line) > 95 or line.endswith((',', ';')):
        return False, False

    if _BOOK_PART_RE.match(line) and not line.endswith('.'):
        return True, True

    if _CHAPTER_RE.match(line) and not line.endswith('.'):
        return True, True

    # Short standalone title line surrounded by whitespace or uppercase
    if len(line) <= 65 and not line.endswith(('.', '!', '?')):
        if line.isupper() and len(line) >= 4:
            return True, False
        if (prev_blank or next_blank) and line[0].isupper():
            words = line.split()
            if 1 <= len(words) <= 9:
                return True, False

    return False, False


def parse_pdf(file_path: Path) -> Document:
    reader = PdfReader(str(file_path))

    title = file_path.stem.replace("_", " ").title()
    author = "Unknown Author"

    if reader.metadata:
        if reader.metadata.title and reader.metadata.title.strip():
            title = reader.metadata.title.strip()
        if reader.metadata.author and reader.metadata.author.strip():
            author = reader.metadata.author.strip()

    doc_id = deterministic_doc_id(file_path)
    document = Document(
        id=doc_id,
        title=title,
        author=author,
        file_format="pdf",
        file_path=str(file_path),
    )

    pages_raw: list[str] = []
    for page in reader.pages:
        try:
            pages_raw.append(page.extract_text() or "")
        except Exception:
            pages_raw.append("")

    # Detect repeating headers/footers across pages
    header_candidates: dict[str, int] = {}
    footer_candidates: dict[str, int] = {}
    for p_txt in pages_raw:
        lines = [l.strip() for l in p_txt.splitlines() if l.strip()]
        if lines:
            header_candidates[lines[0]] = header_candidates.get(lines[0], 0) + 1
            footer_candidates[lines[-1]] = footer_candidates.get(lines[-1], 0) + 1

    num_pages = len(pages_raw)
    threshold = max(2, int(num_pages * 0.3))
    frequent_headers = {line for line, cnt in header_candidates.items() if cnt >= threshold}
    frequent_footers = {line for line, cnt in footer_candidates.items() if cnt >= threshold}

    chapter_idx = 0
    current_book_prefix = ""
    current_chapter_title = "Introduction"
    current_paragraphs: list[ParagraphNode] = []
    p_idx = 0

    def emit_paragraph(text_str: str, is_heading: bool = False, node_type: str = "p"):
        nonlocal p_idx
        clean_p = unhyphenate(text_str)
        clean_p = re.sub(r'[\t\r\f]+', ' ', clean_p)
        clean_p = re.sub(r'\s+', ' ', clean_p).strip()
        if not clean_p or len(clean_p) < 2:
            return

        node_id = f"p_{chapter_idx}_{p_idx}"
        node = ParagraphNode(
            id=node_id,
            text=clean_p,
            node_type=node_type,
            is_heading=is_heading,
        )
        for s_idx, (s_text, s_start, s_end) in enumerate(split_into_sentences(clean_p)):
            node.sentences.append(SentenceNode(
                id=f"s_{chapter_idx}_{p_idx}_{s_idx}",
                text=s_text,
                skip_tts=False,
                char_start=s_start,
                char_end=s_end,
            ))
        if node.sentences:
            current_paragraphs.append(node)
            p_idx += 1

    def flush_chapter(next_title: str):
        nonlocal chapter_idx, current_chapter_title, current_paragraphs, p_idx
        if current_paragraphs:
            document.chapters.append(Chapter(
                id=f"ch_{chapter_idx}",
                index=chapter_idx,
                title=current_chapter_title,
                paragraphs=current_paragraphs,
            ))
            chapter_idx += 1
        current_chapter_title = next_title
        current_paragraphs = []
        p_idx = 0

    for raw_page in pages_raw:
        raw_lines = raw_page.splitlines()
        cleaned_lines: list[str] = []
        for line in raw_lines:
            s_line = re.sub(r'[\t\r\f]+', ' ', line).strip()
            if not s_line:
                cleaned_lines.append("")
                continue
            if s_line in frequent_headers or s_line in frequent_footers:
                continue
            if re.match(r'^\d{1,4}$', s_line) or re.match(r'^[ivxlcdm]+$', s_line, re.IGNORECASE):
                continue
            if _TOC_ENTRY_LINE_RE.match(s_line):
                continue
            cleaned_lines.append(s_line)

        curr_buf: list[str] = []

        def flush_buf():
            if curr_buf:
                joined = "\n".join(curr_buf)
                emit_paragraph(joined, is_heading=False, node_type="p")
                curr_buf.clear()

        for idx, line in enumerate(cleaned_lines):
            if not line:
                flush_buf()
                continue

            prev_blank = (idx == 0) or (not cleaned_lines[idx - 1])
            next_blank = (idx == len(cleaned_lines) - 1) or (not cleaned_lines[idx + 1])

            is_heading, is_chap_break = _is_heading_line(line, prev_blank, next_blank)

            if is_chap_break:
                flush_buf()
                if _BOOK_PART_RE.match(line):
                    current_book_prefix = line
                    flush_chapter(line)
                    emit_paragraph(line, is_heading=True, node_type="h1")
                else:
                    chap_label = f"{current_book_prefix} · {line}" if current_book_prefix and len(current_book_prefix) < 40 else line
                    flush_chapter(chap_label)
                    emit_paragraph(line, is_heading=True, node_type="h2")
                continue

            if is_heading:
                flush_buf()
                emit_paragraph(line, is_heading=True, node_type="h2")
                continue

            curr_buf.append(line)

        flush_buf()

    if current_paragraphs:
        document.chapters.append(Chapter(
            id=f"ch_{chapter_idx}",
            index=chapter_idx,
            title=current_chapter_title,
            paragraphs=current_paragraphs,
        ))

    document.compute_stats()
    return document
