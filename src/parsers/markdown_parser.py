"""Markdown / CommonMark Semantic AST Parser.

Parses headings into chapters/sections, isolates fenced code blocks,
and maintains paragraph structure for technical and literary documents.
"""
from pathlib import Path
import re
import uuid

from src.parsers.base import Document, Chapter, ParagraphNode, SentenceNode
from src.tts.normalizer import split_into_sentences, normalize_text_for_tts, unhyphenate
from src.config import SMART_AUDIO_MODE

def parse_markdown(file_path: Path) -> Document:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    
    doc_id = str(uuid.uuid4())[:8]
    title = file_path.stem.replace("_", " ").title()
    
    # Check first H1 for title
    first_h1 = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
    if first_h1:
        title = first_h1.group(1).strip()

    document = Document(
        id=doc_id,
        title=title,
        author="Author",
        file_format="markdown",
        file_path=str(file_path)
    )

    lines = text.splitlines()
    chapter_idx = 0
    current_chapter_title = title
    current_paragraphs: list[ParagraphNode] = []
    p_idx = 0

    in_code_block = False
    code_lang = ""
    code_lines: list[str] = []
    para_lines: list[str] = []

    def flush_paragraph():
        nonlocal p_idx, current_paragraphs, para_lines
        if not para_lines:
            return
        p_text = " ".join(para_lines).strip()
        para_lines = []
        if not p_text:
            return
        
        clean_p = unhyphenate(p_text)
        is_quote = clean_p.startswith(">")
        if is_quote:
            clean_p = re.sub(r'^>\s*', '', clean_p)

        node_id = f"p_{chapter_idx}_{p_idx}"
        node = ParagraphNode(
            id=node_id,
            text=clean_p,
            node_type="blockquote" if is_quote else "p",
            is_quote=is_quote
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

    for line in lines:
        stripped = line.strip()

        # Handle fenced code blocks
        if stripped.startswith("```"):
            if not in_code_block:
                flush_paragraph()
                in_code_block = True
                code_lang = stripped[3:].strip()
                code_lines = []
            else:
                in_code_block = False
                raw_code = "\n".join(code_lines)
                node_id = f"p_{chapter_idx}_{p_idx}"
                node = ParagraphNode(
                    id=node_id,
                    text=f"```{code_lang}\n{raw_code}\n```",
                    node_type="code",
                    is_code=True
                )
                # In smart audio mode, code blocks are kept for visual reading but skipped in TTS
                node.sentences.append(SentenceNode(
                    id=f"s_{chapter_idx}_{p_idx}_0",
                    text=raw_code if raw_code else "Code block",
                    tts_text="" if SMART_AUDIO_MODE else f"Code snippet in {code_lang or 'text'}",
                    char_start=0,
                    char_end=len(raw_code)
                ))
                current_paragraphs.append(node)
                p_idx += 1
                code_lines = []
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        # Check for Headings (# or ##)
        heading_match = re.match(r'^(#{1,3})\s+(.+)$', stripped)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            h_text = heading_match.group(2).strip()

            if level <= 2 and current_paragraphs:
                # Demarcate new chapter
                document.chapters.append(Chapter(
                    id=f"ch_{chapter_idx}",
                    index=chapter_idx,
                    title=current_chapter_title,
                    paragraphs=current_paragraphs
                ))
                chapter_idx += 1
                current_chapter_title = h_text
                current_paragraphs = []
                p_idx = 0

            node_id = f"p_{chapter_idx}_{p_idx}"
            node = ParagraphNode(
                id=node_id,
                text=h_text,
                node_type=f"h{level}",
                is_heading=True
            )
            node.sentences.append(SentenceNode(
                id=f"s_{chapter_idx}_{p_idx}_0",
                text=h_text,
                tts_text=normalize_text_for_tts(h_text),
                char_start=0,
                char_end=len(h_text)
            ))
            current_paragraphs.append(node)
            p_idx += 1
            continue

        # Blank line separates paragraphs
        if not stripped:
            flush_paragraph()
        else:
            para_lines.append(stripped)

    flush_paragraph()

    if current_paragraphs:
        document.chapters.append(Chapter(
            id=f"ch_{chapter_idx}",
            index=chapter_idx,
            title=current_chapter_title,
            paragraphs=current_paragraphs
        ))

    document.compute_stats()
    return document
