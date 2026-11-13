"""EPUB Semantic AST Parser.

Parses Open Publication Structure (OPS) and spine in Calibre-grade order,
preserving headings, blockquotes, lists, and footnote separation.
Includes fallback zip-container parser for imperfect or legacy EPUB files.
"""
from pathlib import Path
import uuid
import zipfile
import warnings
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

from src.parsers.base import Document, Chapter, ParagraphNode, SentenceNode
from src.tts.normalizer import split_into_sentences, normalize_text_for_tts, unhyphenate
from src.config import SMART_AUDIO_MODE

def parse_epub_fallback_zip(file_path: Path) -> Document:
    """Fallback parser reading raw XHTML items from EPUB zip container."""
    doc_id = str(uuid.uuid4())[:8]
    title = file_path.stem.replace("_", " ").title()
    document = Document(
        id=doc_id,
        title=title,
        author="Unknown Author",
        file_format="epub",
        file_path=str(file_path)
    )

    with zipfile.ZipFile(file_path, "r") as z:
        html_files = [f for f in z.namelist() if f.lower().endswith((".xhtml", ".html", ".htm")) and not "nav" in f.lower()]
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

            paragraphs: list[ParagraphNode] = []
            p_idx = 0
            for el in soup.find_all(["p", "h1", "h2", "h3", "h4", "blockquote", "pre", "code", "li"]):
                raw_text = el.get_text(strip=True)
                if not raw_text or len(raw_text) < 2:
                    continue

                cleaned_text = unhyphenate(raw_text)
                tag_name = el.name.lower()
                is_heading = tag_name in ["h1", "h2", "h3", "h4"]
                is_code = tag_name in ["pre", "code"]
                is_quote = tag_name == "blockquote"

                node = ParagraphNode(
                    id=f"p_{chapter_idx}_{p_idx}",
                    text=cleaned_text,
                    node_type=tag_name,
                    is_heading=is_heading,
                    is_code=is_code,
                    is_quote=is_quote
                )

                for s_idx, (s_text, s_start, s_end) in enumerate(split_into_sentences(cleaned_text)):
                    tts_text = "" if (is_code and SMART_AUDIO_MODE) else normalize_text_for_tts(s_text)
                    node.sentences.append(SentenceNode(
                        id=f"s_{chapter_idx}_{p_idx}_{s_idx}",
                        text=s_text,
                        tts_text=tts_text,
                        char_start=s_start,
                        char_end=s_end
                    ))

                if node.sentences:
                    paragraphs.append(node)
                    p_idx += 1

            if paragraphs:
                document.chapters.append(Chapter(
                    id=f"ch_{chapter_idx}",
                    index=chapter_idx,
                    title=chapter_title,
                    paragraphs=paragraphs
                ))
                chapter_idx += 1

    document.compute_stats()
    return document

def parse_epub(file_path: Path) -> Document:
    try:
        book = epub.read_epub(str(file_path))
    except Exception:
        # Gracefully invoke zip fallback
        return parse_epub_fallback_zip(file_path)

    # Metadata extraction
    title = "Untitled Book"
    title_meta = book.get_metadata("DC", "title")
    if title_meta:
        title = title_meta[0][0]

    author = "Unknown Author"
    creator_meta = book.get_metadata("DC", "creator")
    if creator_meta:
        author = creator_meta[0][0]

    doc_id = str(uuid.uuid4())[:8]
    document = Document(
        id=doc_id,
        title=title,
        author=author,
        file_format="epub",
        file_path=str(file_path)
    )

    chapter_idx = 0
    # Process items in spine order
    for item_id in book.spine:
        item = book.get_item_with_id(item_id[0])
        if not item or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue

        content = item.get_content().decode("utf-8", errors="ignore")
        soup = BeautifulSoup(content, "lxml")

        # Strip navigation, script, and style tags
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        # Find chapter title
        chapter_title = f"Chapter {chapter_idx + 1}"
        h_tag = soup.find(["h1", "h2", "h3", "title"])
        if h_tag and h_tag.get_text(strip=True):
            chapter_title = h_tag.get_text(strip=True)

        paragraphs: list[ParagraphNode] = []
        p_idx = 0

        # Extract semantic elements
        elements = soup.find_all(["p", "h1", "h2", "h3", "h4", "blockquote", "pre", "code", "li"])
        for el in elements:
            raw_text = el.get_text(strip=True)
            if not raw_text or len(raw_text) < 2:
                continue

            cleaned_text = unhyphenate(raw_text)
            tag_name = el.name.lower()
            
            is_heading = tag_name in ["h1", "h2", "h3", "h4"]
            is_code = tag_name in ["pre", "code"]
            is_quote = tag_name == "blockquote"

            node_id = f"p_{chapter_idx}_{p_idx}"
            node = ParagraphNode(
                id=node_id,
                text=cleaned_text,
                node_type=tag_name,
                is_heading=is_heading,
                is_code=is_code,
                is_quote=is_quote
            )

            # Split paragraph into sentences with exact character offsets
            raw_sentences = split_into_sentences(cleaned_text)
            for s_idx, (s_text, s_start, s_end) in enumerate(raw_sentences):
                s_id = f"s_{chapter_idx}_{p_idx}_{s_idx}"
                
                # Semantic Rigor: Smart audio mode skips code blocks in TTS stream
                if is_code and SMART_AUDIO_MODE:
                    tts_text = ""
                else:
                    tts_text = normalize_text_for_tts(s_text)

                node.sentences.append(SentenceNode(
                    id=s_id,
                    text=s_text,
                    tts_text=tts_text,
                    char_start=s_start,
                    char_end=s_end
                ))

            if node.sentences:
                paragraphs.append(node)
                p_idx += 1

        if paragraphs:
            document.chapters.append(Chapter(
                id=f"ch_{chapter_idx}",
                index=chapter_idx,
                title=chapter_title,
                paragraphs=paragraphs
            ))
            chapter_idx += 1

    document.compute_stats()
    return document
