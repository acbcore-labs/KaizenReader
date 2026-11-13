"""DOCX Semantic AST Parser.

Parses Microsoft Word documents using native XML styles, extracting headings
as chapter delimiters and standard paragraphs into sentence nodes.
"""
from pathlib import Path
import uuid
import docx

from src.parsers.base import Document, Chapter, ParagraphNode, SentenceNode
from src.tts.normalizer import split_into_sentences, normalize_text_for_tts, unhyphenate

def parse_docx(file_path: Path) -> Document:
    doc = docx.Document(str(file_path))
    
    doc_id = str(uuid.uuid4())[:8]
    title = file_path.stem.replace("_", " ").title()

    # Read core properties if available
    author = "Unknown Author"
    if doc.core_properties:
        if doc.core_properties.title:
            title = doc.core_properties.title
        if doc.core_properties.author:
            author = doc.core_properties.author

    document = Document(
        id=doc_id,
        title=title,
        author=author,
        file_format="docx",
        file_path=str(file_path)
    )

    chapter_idx = 0
    current_chapter_title = title
    current_paragraphs: list[ParagraphNode] = []
    p_idx = 0

    for p in doc.paragraphs:
        raw_text = p.text.strip()
        if not raw_text:
            continue

        style_name = p.style.name.lower() if p.style else ""
        is_heading = "heading" in style_name or "title" in style_name
        is_h1_or_h2 = "heading 1" in style_name or "heading 2" in style_name or "title" in style_name

        clean_text = unhyphenate(raw_text)

        if is_h1_or_h2 and current_paragraphs:
            document.chapters.append(Chapter(
                id=f"ch_{chapter_idx}",
                index=chapter_idx,
                title=current_chapter_title,
                paragraphs=current_paragraphs
            ))
            chapter_idx += 1
            current_chapter_title = clean_text
            current_paragraphs = []
            p_idx = 0

        node_id = f"p_{chapter_idx}_{p_idx}"
        node = ParagraphNode(
            id=node_id,
            text=clean_text,
            node_type="h1" if is_h1_or_h2 else ("h2" if is_heading else "p"),
            is_heading=is_heading
        )

        for s_idx, (s_text, s_start, s_end) in enumerate(split_into_sentences(clean_text)):
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
