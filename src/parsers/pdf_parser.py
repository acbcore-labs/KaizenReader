"""PDF Semantic AST Parser.

Applies structural heuristics: suppresses running headers, footers,
and page numbering, repairs broken line-hyphens, and re-stitches
paragraphs into continuous narrative flow.
"""
from pathlib import Path
import re
import uuid
from pypdf import PdfReader

from src.parsers.base import Document, Chapter, ParagraphNode, SentenceNode
from src.tts.normalizer import split_into_sentences, normalize_text_for_tts, unhyphenate

def parse_pdf(file_path: Path) -> Document:
    reader = PdfReader(str(file_path))
    
    title = file_path.stem.replace("_", " ").title()
    author = "Unknown Author"
    
    if reader.metadata:
        if reader.metadata.title:
            title = reader.metadata.title
        if reader.metadata.author:
            author = reader.metadata.author

    doc_id = str(uuid.uuid4())[:8]
    document = Document(
        id=doc_id,
        title=title,
        author=author,
        file_format="pdf",
        file_path=str(file_path)
    )

    # First pass: collect raw text per page
    pages_raw = []
    for page in reader.pages:
        try:
            txt = page.extract_text() or ""
            pages_raw.append(txt)
        except Exception:
            pages_raw.append("")

    # Detect repeating headers/footers across pages
    header_candidates = {}
    footer_candidates = {}
    for p_txt in pages_raw:
        lines = [l.strip() for l in p_txt.splitlines() if l.strip()]
        if lines:
            first_line = lines[0]
            last_line = lines[-1]
            header_candidates[first_line] = header_candidates.get(first_line, 0) + 1
            footer_candidates[last_line] = footer_candidates.get(last_line, 0) + 1

    num_pages = len(pages_raw)
    threshold = max(2, int(num_pages * 0.3))
    frequent_headers = {line for line, cnt in header_candidates.items() if cnt >= threshold}
    frequent_footers = {line for line, cnt in footer_candidates.items() if cnt >= threshold}

    # Second pass: clean and group into chapters
    chapter_idx = 0
    current_chapter_title = "Chapter 1"
    current_paragraphs: list[ParagraphNode] = []
    p_idx = 0

    for page_num, raw_page in enumerate(pages_raw):
        lines = raw_page.splitlines()
        cleaned_lines = []
        for line in lines:
            s_line = line.strip()
            if not s_line:
                cleaned_lines.append("")
                continue
            # Filter headers & footers
            if s_line in frequent_headers or s_line in frequent_footers:
                continue
            # Filter standalone page numbers
            if re.match(r'^\d{1,4}$', s_line) or re.match(r'^[ivxlcdm]+$', s_line, re.IGNORECASE):
                continue
            cleaned_lines.append(s_line)

        # Re-stitch lines into paragraphs
        raw_paras: list[str] = []
        curr_buf: list[str] = []

        for line in cleaned_lines:
            if not line:
                if curr_buf:
                    raw_paras.append(" ".join(curr_buf))
                    curr_buf = []
            else:
                curr_buf.append(line)
        if curr_buf:
            raw_paras.append(" ".join(curr_buf))

        # Check for chapter headings
        for p_str in raw_paras:
            clean_p = unhyphenate(p_str)
            clean_p = re.sub(r'[\t\r\f]+', ' ', clean_p)
            clean_p = re.sub(r'\s+', ' ', clean_p).strip()
            if not clean_p or len(clean_p) < 2:
                continue

            # Detect chapter title pattern
            is_new_chapter = False
            if re.match(r'^(Chapter|Section|Part|Book)\s+([0-9IVXLCDM]+|[A-Z][a-z]+)', clean_p, re.IGNORECASE) and len(clean_p) < 80:
                is_new_chapter = True

            if is_new_chapter and current_paragraphs:
                # Flush chapter
                document.chapters.append(Chapter(
                    id=f"ch_{chapter_idx}",
                    index=chapter_idx,
                    title=current_chapter_title,
                    paragraphs=current_paragraphs
                ))
                chapter_idx += 1
                current_chapter_title = clean_p
                current_paragraphs = []
                p_idx = 0

            # Create Paragraph Node
            is_heading = is_new_chapter or (len(clean_p) < 60 and clean_p.isupper())
            node_id = f"p_{chapter_idx}_{p_idx}"
            node = ParagraphNode(
                id=node_id,
                text=clean_p,
                node_type="h2" if is_heading else "p",
                is_heading=is_heading
            )

            # Sentence splitting
            raw_sentences = split_into_sentences(clean_p)
            for s_idx, (s_text, s_start, s_end) in enumerate(raw_sentences):
                s_id = f"s_{chapter_idx}_{p_idx}_{s_idx}"
                tts_text = normalize_text_for_tts(s_text)
                node.sentences.append(SentenceNode(
                    id=s_id,
                    text=s_text,
                    tts_text=tts_text,
                    char_start=s_start,
                    char_end=s_end
                ))

            if node.sentences:
                current_paragraphs.append(node)
                p_idx += 1

    # Flush final chapter
    if current_paragraphs:
        document.chapters.append(Chapter(
            id=f"ch_{chapter_idx}",
            index=chapter_idx,
            title=current_chapter_title,
            paragraphs=current_paragraphs
        ))

    # If no chapters were formed, wrap whole book into Chapter 1
    if not document.chapters and current_paragraphs:
        document.chapters.append(Chapter(
            id="ch_0",
            index=0,
            title="Full Document",
            paragraphs=current_paragraphs
        ))

    document.compute_stats()
    return document
