"""EPUB Semantic AST Parser.

Parses Open Publication Structure (OPS) and spine in Calibre-grade order,
preserving headings, blockquotes, lists, and avoiding duplicate nested-tag
extraction. Includes zip fallback for legacy EPUB files.
"""
from pathlib import Path
import zipfile
import warnings
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, Tag, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from src.parsers.base import Document, Chapter, ParagraphNode, SentenceNode, deterministic_doc_id
from src.tts.normalizer import split_into_sentences, unhyphenate
from src.config import SMART_AUDIO_MODE

_BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "blockquote", "pre", "code", "li"}


def _extract_leaf_blocks(soup: BeautifulSoup) -> list[tuple[str, str, bool]]:
    """Extract (tag_name, text, is_quote_context) without double-emitting nested blocks."""
    results: list[tuple[str, str, bool]] = []
    for el in soup.find_all(_BLOCK_TAGS):
        if not isinstance(el, Tag):
            continue
        tag_name = el.name.lower()

        # Skip <code> nested inside <pre> (the <pre> emits the whole code block)
        if tag_name == "code" and el.find_parent("pre"):
            continue

        # Skip container <blockquote> or <li> if it contains child block tags
        if tag_name in ("blockquote", "li") and el.find(["p", "h1", "h2", "h3", "h4", "li"]):
            continue

        raw_text = el.get_text(" " if tag_name != "pre" else "\n", strip=True)
        if not raw_text or len(raw_text) < 2:
            continue

        in_quote = tag_name == "blockquote" or bool(el.find_parent("blockquote"))
        results.append((tag_name, raw_text, in_quote))
    return results


def _build_paragraphs_from_soup(soup: BeautifulSoup, chapter_idx: int) -> list[ParagraphNode]:
    paragraphs: list[ParagraphNode] = []
    p_idx = 0
    for tag_name, raw_text, in_quote in _extract_leaf_blocks(soup):
        cleaned_text = unhyphenate(raw_text)
        is_heading = tag_name in ("h1", "h2", "h3", "h4")
        is_code = tag_name in ("pre", "code")
        is_quote = in_quote and not is_heading and not is_code

        node = ParagraphNode(
            id=f"p_{chapter_idx}_{p_idx}",
            text=cleaned_text,
            node_type="blockquote" if is_quote else tag_name,
            is_heading=is_heading,
            is_code=is_code,
            is_quote=is_quote,
        )

        skip_tts = bool(is_code and SMART_AUDIO_MODE)
        for s_idx, (s_text, s_start, s_end) in enumerate(split_into_sentences(cleaned_text)):
            node.sentences.append(SentenceNode(
                id=f"s_{chapter_idx}_{p_idx}_{s_idx}",
                text=s_text,
                skip_tts=skip_tts,
                char_start=s_start,
                char_end=s_end,
            ))

        if node.sentences:
            paragraphs.append(node)
            p_idx += 1
    return paragraphs


def parse_epub_fallback_zip(file_path: Path) -> Document:
    """Fallback parser reading raw XHTML items from EPUB zip container."""
    doc_id = deterministic_doc_id(file_path)
    title = file_path.stem.replace("_", " ").title()
    document = Document(
        id=doc_id,
        title=title,
        author="Unknown Author",
        file_format="epub",
        file_path=str(file_path),
    )

    with zipfile.ZipFile(file_path, "r") as z:
        html_files = [
            f for f in z.namelist()
            if f.lower().endswith((".xhtml", ".html", ".htm")) and "nav" not in f.lower()
        ]
        html_files.sort()

        chapter_idx = 0
        for fname in html_files:
            content = z.read(fname).decode("utf-8", errors="ignore")
            soup = BeautifulSoup(content, "lxml")
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()

            chapter_title = f"Chapter {chapter_idx + 1}"
            h_tag = soup.find(["h1", "h2", "h3", "title"])
            if h_tag and h_tag.get_text(strip=True):
                chapter_title = h_tag.get_text(strip=True)

            paragraphs = _build_paragraphs_from_soup(soup, chapter_idx)
            if paragraphs:
                document.chapters.append(Chapter(
                    id=f"ch_{chapter_idx}",
                    index=chapter_idx,
                    title=chapter_title,
                    paragraphs=paragraphs,
                ))
                chapter_idx += 1

    document.compute_stats()
    return document


def parse_epub(file_path: Path) -> Document:
    try:
        book = epub.read_epub(str(file_path))
    except Exception:
        return parse_epub_fallback_zip(file_path)

    title = file_path.stem.replace("_", " ").title()
    title_meta = book.get_metadata("DC", "title")
    if title_meta and title_meta[0][0]:
        title = title_meta[0][0]

    author = "Unknown Author"
    creator_meta = book.get_metadata("DC", "creator")
    if creator_meta and creator_meta[0][0]:
        author = creator_meta[0][0]

    doc_id = deterministic_doc_id(file_path)
    document = Document(
        id=doc_id,
        title=title,
        author=author,
        file_format="epub",
        file_path=str(file_path),
    )

    chapter_idx = 0
    for item_id in book.spine:
        item = book.get_item_with_id(item_id[0])
        if not item or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue

        content = item.get_content().decode("utf-8", errors="ignore")
        soup = BeautifulSoup(content, "lxml")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        chapter_title = f"Chapter {chapter_idx + 1}"
        h_tag = soup.find(["h1", "h2", "h3", "title"])
        if h_tag and h_tag.get_text(strip=True):
            chapter_title = h_tag.get_text(strip=True)

        paragraphs = _build_paragraphs_from_soup(soup, chapter_idx)
        if paragraphs:
            document.chapters.append(Chapter(
                id=f"ch_{chapter_idx}",
                index=chapter_idx,
                title=chapter_title,
                paragraphs=paragraphs,
            ))
            chapter_idx += 1

    document.compute_stats()
    return document
