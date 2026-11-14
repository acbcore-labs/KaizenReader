"""Document Parser Dispatcher with High-Speed AST Disk Caching.

Routes documents to their format-specific AST parser based on file extension,
and caches serialised AST nodes in data/cache/ for sub-10ms instantaneous loads.
"""
import json
from pathlib import Path
from typing import Union
from src.config import AST_CACHE_DIR
from src.parsers.base import Document, deterministic_doc_id
from src.parsers.epub_parser import parse_epub
from src.parsers.pdf_parser import parse_pdf
from src.parsers.markdown_parser import parse_markdown
from src.parsers.docx_parser import parse_docx
from src.parsers.text_parser import parse_text


def parse_document(file_path: Union[str, Path], use_cache: bool = True) -> Document:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # Check AST disk cache by content hash
    doc_id = deterministic_doc_id(path)
    cache_file = AST_CACHE_DIR / f"ast_{doc_id}.json"

    if use_cache and cache_file.exists():
        try:
            cached_data = json.loads(cache_file.read_text(encoding="utf-8"))
            doc = Document.model_validate(cached_data)
            doc.file_path = str(path.resolve())
            return doc
        except Exception as e:
            print(f"[Parser] Cache read failed for {path.name}, reparsing: {e}")

    # Parse from scratch based on format
    suffix = path.suffix.lower()
    if suffix == ".epub":
        doc = parse_epub(path)
    elif suffix == ".pdf":
        doc = parse_pdf(path)
    elif suffix in [".md", ".markdown"]:
        doc = parse_markdown(path)
    elif suffix == ".docx":
        doc = parse_docx(path)
    elif suffix in [".txt", ".text", ".html", ".htm"]:
        doc = parse_text(path)
    else:
        # Default fallback to text parser
        doc = parse_text(path)

    # Persist AST to cache for instantaneous future loads
    try:
        temp_cache = cache_file.with_suffix(".tmp")
        temp_cache.write_text(json.dumps(doc.model_dump()), encoding="utf-8")
        temp_cache.replace(cache_file)
    except Exception as e:
        print(f"[Parser] Failed to write AST cache for {path.name}: {e}")

    return doc
