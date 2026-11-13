"""Plain Text & HTML Semantic AST Parser.

Parses plain text (.txt) and web articles/HTML (.html), handling
paragraph spacing, chapter indicators, and semantic hierarchy.
"""
from pathlib import Path
import re
import uuid
from bs4 import BeautifulSoup

from src.parsers.base import Document, Chapter, ParagraphNode, SentenceNode
from src.tts.normalizer import split_into_sentences, normalize_text_for_tts, unhyphenate

def parse_text(file_path: Path) -> Document:
    raw_content = file_path.read_text(encoding="utf-8", errors="ignore")
    is_html = file_path.suffix.lower() in [".html", ".htm"] or "<html" in raw_content[:200].lower()

    title = file_path.stem.replace("_", " ").title()
    doc_id = str(uuid.uuid4())[:8]

    if is_html:
        soup = BeautifulSoup(raw_content, "lxml")
        title_tag = soup.find(["h1", "title"])
        if title_tag and title_tag.get_text(strip=True):
            title = title_tag.get_text(strip=True)
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        # Convert HTML elements to paragraphs
        raw_paras = [p.get_text(strip=True) for p in soup.find_all(["p", "h1", "h2", "h3", "li", "blockquote"])]
    else:
        # Split on double newlines
        raw_paras = [p.strip() for p in re.split(r'\n\s*\n', raw_content) if p.strip()]

    document = Document(
        id=doc_id,
        title=title,
        author="Unknown Author",
        file_format="html" if is_html else "txt",
        file_path=str(file_path)
    )

    chapter_idx = 0
    current_chapter_title = title
    current_paragraphs: list[ParagraphNode] = []
    p_idx = 0

    for p_str in raw_paras:
        clean_p = unhyphenate(p_str)
        if not clean_p:
            continue

        # Check for chapter title
        is_chapter_heading = bool(re.match(r'^(Chapter|Section|Book|Part)\s+([0-9IVXLCDM]+|[A-Z][a-z]+)', clean_p, re.IGNORECASE)) and len(clean_p) < 80

        if is_chapter_heading and current_paragraphs:
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

        node_id = f"p_{chapter_idx}_{p_idx}"
        node = ParagraphNode(
            id=node_id,
            text=clean_p,
            node_type="h2" if is_chapter_heading else "p",
            is_heading=is_chapter_heading
        )

        for s_idx, (s_text, s_start, s_end) in enumerate(split_into_sentences(clean_p)):
            s_id = f"s_{chapter_idx}_{p_idx}_{s_idx}"
            node.sentences.append(SentenceNode(
                id=s_id,
                text=s_text,
                tts_text=normalize_text_for_tts(s_text),
                char_start=s_start,
                char_end=s_end
            ))

        if node.sentences:
            current_paragraphs.append(node)
            p_idx += 1

    if current_paragraphs:
        document.chapters.append(Chapter(
            id=f"ch_{chapter_idx}",
            index=chapter_idx,
            title=current_chapter_title,
            paragraphs=current_paragraphs
        ))

    document.compute_stats()
    return document
