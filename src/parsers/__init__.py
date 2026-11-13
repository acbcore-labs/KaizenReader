"""Document Parser Dispatcher.

Routes documents to their format-specific AST parser based on file extension.
"""
from pathlib import Path
from typing import Union
from src.parsers.base import Document
from src.parsers.epub_parser import parse_epub
from src.parsers.pdf_parser import parse_pdf
from src.parsers.markdown_parser import parse_markdown
from src.parsers.docx_parser import parse_docx
from src.parsers.text_parser import parse_text

def parse_document(file_path: Union[str, Path]) -> Document:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".epub":
        return parse_epub(path)
    elif suffix == ".pdf":
        return parse_pdf(path)
    elif suffix in [".md", ".markdown"]:
        return parse_markdown(path)
    elif suffix == ".docx":
        return parse_docx(path)
    elif suffix in [".txt", ".text", ".html", ".htm"]:
        return parse_text(path)
    else:
        # Default fallback to text parser
        return parse_text(path)
