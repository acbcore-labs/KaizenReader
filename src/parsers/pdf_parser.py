"""PDF Semantic AST Parser.

Applies line-aware structural heuristics: suppresses running headers, footers,
and page numbering, repairs broken line-hyphens, identifies Table of Contents
and back matter components without fragmentation, stitches subtitles,
and constructs a clean document hierarchy with deterministic content-hashed IDs.
"""
from pathlib import Path
import re
from pypdf import PdfReader

from src.parsers.base import Document, Chapter, ParagraphNode, SentenceNode, deterministic_doc_id
from src.tts.normalizer import split_into_sentences, unhyphenate
from src.parsers.classifier import classify_title

# Patterns that indicate a standalone structural heading line in a PDF
_BOOK_PART_RE = re.compile(
    r"^(Book|Part|Volume|Section|Act)\s+([0-9IVXLCDM]+|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|First|Second|Third|Fourth|Fifth)\b\s*([:\-–—\.]\s*.*)?$",
    re.IGNORECASE,
)
_CHAPTER_RE = re.compile(
    r"^(Chapter|Ch\.?|Chapitre|Kapitel)\s+([0-9IVXLCDM]+|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|First|Second|Third|Fourth|Fifth)\b\s*([:\-–—\.]\s*.*)?$",
    re.IGNORECASE,
)
_TOC_HEADING_RE = re.compile(
    r"^(Table\s+of\s+Contents|Contents|Index\s+of\s+Chapters|Brief\s+Contents|Detailed\s+Contents|Sommaire|Table\s+des\s+matières|Inhaltsverzeichnis|TOC)$",
    re.IGNORECASE,
)
_BACK_MATTER_RE = re.compile(
    r"^(Appendix(\s+[A-Z0-9]+)?|Appendices|Index|Subject\s+Index|Author\s+Index|General\s+Index|Bibliography|References|Works\s+Cited|Glossary|Notes|Endnotes|Extras|Testament\s+of\s+Solomon|The\s+Testament\s+of\s+Solomon|Book\s+of\s+the\s+Giants|The\s+Book\s+of\s+the\s+Giants|Evidence\s+of\s+Giants|External\s+References\s+to\s+Enoch)\b.*$",
    re.IGNORECASE,
)

# Reject lines that look like sentences rather than standalone headings
_SENTENCE_INDICATORS = re.compile(
    r"\b(several|thousand|earlier|than|buried|under|appearance|wearing|because|although|whereas|which|that|their|there)\b",
    re.IGNORECASE,
)


def _is_clean_heading(line: str) -> bool:
    """Check if a line looks like a valid standalone heading rather than sentence fragment."""
    if len(line) > 75 or len(line) < 3:
        return False
    if line.endswith((",", ";", "-", "—")):
        return False
    if ")" in line and "(" not in line:
        return False
    if _SENTENCE_INDICATORS.search(line):
        return False
    return True


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
        lines = [re.sub(r"[\t\r\f]+", " ", l).strip() for l in p_txt.splitlines() if l.strip()]
        if lines:
            header_candidates[lines[0]] = header_candidates.get(lines[0], 0) + 1
            footer_candidates[lines[-1]] = footer_candidates.get(lines[-1], 0) + 1

    num_pages = len(pages_raw)
    threshold = max(2, int(num_pages * 0.3))
    frequent_headers = {line for line, cnt in header_candidates.items() if cnt >= threshold}
    frequent_footers = {line for line, cnt in footer_candidates.items() if cnt >= threshold}

    chapter_idx = 0
    current_book_prefix = ""
    current_part_title = None
    current_chapter_title = "Title & Copyright"
    current_category = "front_matter"
    current_section_type = "title_page"
    current_paragraphs: list[ParagraphNode] = []
    p_idx = 0
    in_toc = False

    def emit_paragraph(text_str: str, is_heading: bool = False, node_type: str = "p"):
        nonlocal p_idx
        clean_p = unhyphenate(text_str)
        clean_p = re.sub(r"[\t\r\f]+", " ", clean_p)
        clean_p = re.sub(r"\s+", " ", clean_p).strip()
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

    def flush_chapter(next_title: str, next_category: str = "body", next_section_type: str = "chapter", part_title: str = None):
        nonlocal chapter_idx, current_chapter_title, current_category, current_section_type, current_part_title, current_paragraphs, p_idx
        # Filter out empty dummy chapters (e.g. part divider pages with no content)
        is_empty_dummy = (
            current_paragraphs
            and len(current_paragraphs) <= 1
            and (
                len(current_paragraphs) == 0
                or current_paragraphs[0].text.strip().lower() == current_chapter_title.strip().lower()
                or len(current_paragraphs[0].text.split()) <= 5
            )
            and current_section_type == "part"
        )
        if current_paragraphs and not is_empty_dummy:
            document.chapters.append(Chapter(
                id=f"ch_{chapter_idx}",
                index=chapter_idx,
                title=current_chapter_title,
                display_title=f"{current_part_title} · {current_chapter_title}" if current_part_title else current_chapter_title,
                category=current_category,
                section_type=current_section_type,
                part_title=current_part_title,
                is_toc=(current_section_type == "toc"),
                is_front_matter=(current_category == "front_matter"),
                is_back_matter=(current_category == "back_matter"),
                paragraphs=current_paragraphs,
            ))
            chapter_idx += 1
        current_chapter_title = next_title
        current_category = next_category
        current_section_type = next_section_type
        current_part_title = part_title
        current_paragraphs = []
        p_idx = 0

    for page_idx, raw_page in enumerate(pages_raw):
        raw_lines = raw_page.splitlines()
        cleaned_lines: list[str] = []
        for line in raw_lines:
            s_line = re.sub(r"[\t\r\f]+", " ", line).strip()
            if not s_line:
                cleaned_lines.append("")
                continue
            if s_line in frequent_headers or s_line in frequent_footers:
                continue
            if re.match(r"^\d{1,4}$", s_line) or re.match(r"^[ivxlcdm]+$", s_line, re.IGNORECASE):
                continue
            cleaned_lines.append(s_line)

        non_blank = [l for l in cleaned_lines if l]
        if not non_blank:
            continue

        # 1. Check for Table of Contents header on this page
        has_toc_header = False
        for line in non_blank[:5]:
            if _TOC_HEADING_RE.match(line):
                has_toc_header = True
                break

        if has_toc_header and not in_toc:
            flush_chapter("Table of Contents", next_category="front_matter", next_section_type="toc")
            in_toc = True

        # 2. Check if active Table of Contents has ended (e.g. running prose paragraphs start)
        if in_toc and not has_toc_header:
            prose_lines = [
                l for l in non_blank
                if len(l.split()) >= 12
                and not _BOOK_PART_RE.match(l)
                and not _CHAPTER_RE.match(l)
            ]
            if len(prose_lines) >= 2 or (len(non_blank) > 0 and len(non_blank[0].split()) > 20):
                # TOC has ended; next section begins
                in_toc = False
                first_l = non_blank[0]
                if "About the Book" in first_l or "Introduction" in first_l:
                    flush_chapter(first_l, next_category="front_matter", next_section_type="introduction")
                elif _BOOK_PART_RE.match(first_l):
                    current_book_prefix = first_l
                    flush_chapter(first_l, next_category="body", next_section_type="part")
                elif _CHAPTER_RE.match(first_l):
                    flush_chapter(first_l, next_category="body", next_section_type="chapter")
                else:
                    flush_chapter("Introduction", next_category="front_matter", next_section_type="introduction")

        curr_buf: list[str] = []

        def flush_buf():
            if curr_buf:
                joined = "\n".join(curr_buf)
                emit_paragraph(joined, is_heading=False, node_type="p")
                curr_buf.clear()

        idx = 0
        while idx < len(cleaned_lines):
            line = cleaned_lines[idx]
            if not line:
                flush_buf()
                idx += 1
                continue

            prev_blank = (idx == 0) or (not cleaned_lines[idx - 1])

            # While in TOC mode, collect all lines as entries of the TOC chapter
            if in_toc:
                emit_paragraph(line, is_heading=_TOC_HEADING_RE.match(line) is not None, node_type="list_item")
                idx += 1
                continue

            # Check for Book / Part heading (e.g. "Book 1: The Watchers", "Part I")
            m_part = _BOOK_PART_RE.match(line)
            if m_part and prev_blank and _is_clean_heading(line):
                flush_buf()
                current_book_prefix = line
                # Do NOT create a standalone empty dummy chapter for the part divider!
                # It is stored as current_book_prefix so upcoming chapters inherit it as part_title.
                idx += 1
                continue

            # Check for Chapter heading (e.g. "Chapter 1", "Chapter 2")
            m_chap = _CHAPTER_RE.match(line)
            if m_chap and prev_blank and _is_clean_heading(line):
                flush_buf()
                chap_title = line
                # Lookahead to see if next non-empty line is a chapter subtitle (e.g. "The Creation")
                peek_idx = idx + 1
                while peek_idx < len(cleaned_lines) and not cleaned_lines[peek_idx]:
                    peek_idx += 1
                if peek_idx < len(cleaned_lines):
                    next_l = cleaned_lines[peek_idx]
                    if (
                        len(next_l) <= 60
                        and not next_l.endswith((".", ",", ";", "!", "?"))
                        and not _CHAPTER_RE.match(next_l)
                        and not re.match(r"^\d+$", next_l)
                        and not _SENTENCE_INDICATORS.search(next_l)
                    ):
                        chap_title = f"{line}: {next_l}"
                        idx = peek_idx  # consume subtitle line

                flush_chapter(chap_title, next_category="body", next_section_type="chapter", part_title=current_book_prefix)
                emit_paragraph(chap_title, is_heading=True, node_type="h2")
                idx += 1
                continue

            # Check for Back Matter heading (e.g. "The Book of the Giants", "The Testament of Solomon", "Index")
            m_back = _BACK_MATTER_RE.match(line)
            if m_back and prev_blank and _is_clean_heading(line):
                flush_buf()
                current_book_prefix = None  # Reset part prefix for back matter
                cat, s_type, _ = classify_title(line, position_ratio=page_idx / max(1, num_pages))
                flush_chapter(line, next_category="back_matter", next_section_type=s_type, part_title=None)
                emit_paragraph(line, is_heading=True, node_type="h2")
                idx += 1
                continue

            # Check for generic standalone heading (short title line surrounded by blank lines)
            next_blank = (idx == len(cleaned_lines) - 1) or (not cleaned_lines[idx + 1])
            if (
                prev_blank
                and next_blank
                and len(line) <= 50
                and not line.endswith((".", "!", "?", ",", ";", ":"))
                and (line.isupper() or (line[0].isupper() and len(line.split()) <= 7))
                and not _SENTENCE_INDICATORS.search(line)
            ):
                flush_buf()
                emit_paragraph(line, is_heading=True, node_type="h2")
                idx += 1
                continue

            curr_buf.append(line)
            idx += 1

        flush_buf()

    if current_paragraphs:
        document.chapters.append(Chapter(
            id=f"ch_{chapter_idx}",
            index=chapter_idx,
            title=current_chapter_title,
            category=current_category,
            section_type=current_section_type,
            is_toc=(current_section_type == "toc"),
            is_front_matter=(current_category == "front_matter"),
            is_back_matter=(current_category == "back_matter"),
            paragraphs=current_paragraphs,
        ))

    document.compute_stats()
    return document
