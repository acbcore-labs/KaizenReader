"""Semantic Document Component Classifier.

Accurately identifies, categorizes, and labels components of books and articles:
- Front Matter: Cover, Title Page, Copyright, Table of Contents (TOC), Dedication,
  Epigraph, Preface, Foreword, Introduction, Acknowledgments.
- Body: Parts, Volumes, Books, Chapters, Sections.
- Back Matter: Epilogue, Afterword, Appendices, Notes, Endnotes, Glossary,
  Bibliography, References, Works Cited, Index, Colophon, Author Bio.
"""
import re
from typing import Optional, NamedTuple


class SectionClassification(NamedTuple):
    category: str            # "front_matter", "body", "back_matter"
    section_type: str        # "toc", "title_page", "copyright", "introduction", "chapter", "part", "appendix", "index", etc.
    display_title: str
    is_toc: bool
    is_front_matter: bool
    is_back_matter: bool
    badge_label: str         # "TOC", "Front", "Ch 1", "App", "Index", "Refs", "Notes"
    chapter_number: Optional[int] = None
    part_title: Optional[str] = None


# Patterns for Table of Contents
_TOC_RE = re.compile(
    r"^(table\s+of\s+contents|contents|index\s+of\s+chapters|brief\s+contents|detailed\s+contents|sommaire|table\s+des\s+matières|inhaltsverzeichnis|toc)$",
    re.IGNORECASE,
)

# Patterns for Front Matter
_COVER_RE = re.compile(r"^(cover|ebook\s+cover|book\s+cover)$", re.IGNORECASE)
_TITLE_PAGE_RE = re.compile(r"^(title\s+page|half\s+title|title\s+and\s+copyright|title\s+&\s+copyright)$", re.IGNORECASE)
_COPYRIGHT_RE = re.compile(r"^(copyright|copyright\s+notice|copyright\s+page|all\s+rights\s+reserved|publication\s+details)$", re.IGNORECASE)
_DEDICATION_RE = re.compile(r"^(dedication|epigraph|in\s+memory\s+of|to\s+my\b.*)$", re.IGNORECASE)
_PREFACE_RE = re.compile(r"^(preface|foreword|prologue|prolog)$", re.IGNORECASE)
_ACKNOWLEDGMENTS_RE = re.compile(r"^(acknowledgments|acknowledgements|credits)$", re.IGNORECASE)
_INTRODUCTION_RE = re.compile(r"^(introduction|intro|about\s+the\s+book\b.*|about\s+this\s+book\b.*)$", re.IGNORECASE)

# Patterns for Back Matter
_INDEX_RE = re.compile(
    r"^(index|subject\s+index|author\s+index|general\s+index|alphabetical\s+index|keyword\s+index|name\s+index)$",
    re.IGNORECASE,
)
_APPENDIX_RE = re.compile(
    r"^(appendix(\s+[A-Z0-9]+)?|appendices|addendum|extras|supplement|supplementary\b.*|(the\s+)?testament\s+of\s+solomon|(the\s+)?book\s+of\s+(the\s+)?giants|evidence\s+of\s+giants)\b.*$",
    re.IGNORECASE,
)
_NOTES_RE = re.compile(r"^(notes|endnotes|chapter\s+notes|notes\s+and\s+sources|footnotes)$", re.IGNORECASE)
_GLOSSARY_RE = re.compile(r"^(glossary|vocabulary|definition\s+of\s+terms|terms)$", re.IGNORECASE)
_BIBLIOGRAPHY_RE = re.compile(
    r"^(bibliography|references|works\s+cited|sources|further\s+reading|external\s+references\b.*|selected\s+bibliography)$",
    re.IGNORECASE,
)
_EPILOGUE_RE = re.compile(r"^(epilogue|afterword|postscript|conclusion)$", re.IGNORECASE)
_COLOPHON_RE = re.compile(r"^(colophon|about\s+the\s+author|author\s+bio|about\s+the\s+publisher|also\s+by\b.*)$", re.IGNORECASE)

# Patterns for Body Parts and Chapters
_BOOK_PART_RE = re.compile(
    r"^(Book|Part|Volume|Section|Act)\s+([0-9IVXLCDM]+|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|First|Second|Third|Fourth|Fifth)\b\s*([:\-–—\.]\s*.*)?$",
    re.IGNORECASE,
)
_CHAPTER_SUB_RE = re.compile(
    r"\b(Chapter|Ch\.?|Chapitre|Kapitel)\s*([0-9]+|[IVXLCDM]+|One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)?\b",
    re.IGNORECASE,
)


def classify_title(title: str, position_ratio: float = 0.5) -> tuple[str, str, str]:
    """Classify a section title into (category, section_type, badge_label)."""
    s = title.strip()
    clean_s = re.sub(r"[\s\-_–—]+", " ", s)

    # 1. Table of Contents
    if _TOC_RE.match(clean_s) or "table of contents" in clean_s.lower():
        return ("front_matter", "toc", "TOC")

    # 2. Cover / Title / Copyright
    if _COVER_RE.match(clean_s):
        return ("front_matter", "cover", "Front")
    if _TITLE_PAGE_RE.match(clean_s):
        return ("front_matter", "title_page", "Front")
    if _COPYRIGHT_RE.match(clean_s):
        return ("front_matter", "copyright", "Front")
    if _DEDICATION_RE.match(clean_s):
        return ("front_matter", "dedication", "Front")
    if _PREFACE_RE.match(clean_s):
        return ("front_matter", "preface", "Preface")
    if _ACKNOWLEDGMENTS_RE.match(clean_s):
        return ("front_matter", "acknowledgments", "Front")

    # 3. Introduction (if near start of book)
    if _INTRODUCTION_RE.match(clean_s):
        if position_ratio < 0.4:
            return ("front_matter", "introduction", "Intro")
        return ("body", "chapter", "Ch")

    # 4. Back Matter - Index (high priority)
    if _INDEX_RE.match(clean_s):
        return ("back_matter", "index", "Index")
    if clean_s.lower().endswith(" index") and position_ratio > 0.4:
        return ("back_matter", "index", "Index")

    # 5. Back Matter - Appendices, Notes, Bibliography, Glossary
    if _APPENDIX_RE.match(clean_s):
        return ("back_matter", "appendix", "App")
    if _BIBLIOGRAPHY_RE.match(clean_s):
        return ("back_matter", "bibliography", "Refs")
    if _NOTES_RE.match(clean_s):
        return ("back_matter", "notes", "Notes")
    if _GLOSSARY_RE.match(clean_s):
        return ("back_matter", "glossary", "Gloss")
    if _EPILOGUE_RE.match(clean_s):
        return ("back_matter", "epilogue", "End")
    if _COLOPHON_RE.match(clean_s):
        return ("back_matter", "colophon", "End")

    # 6. Body Chapter if title explicitly contains Chapter or Ch.
    if _CHAPTER_SUB_RE.search(clean_s):
        return ("body", "chapter", "Ch")

    # 7. Body Part / Book division (without chapter)
    if _BOOK_PART_RE.match(clean_s):
        return ("body", "part", "Part")

    # 8. Default body chapter
    return ("body", "chapter", "Ch")


def filter_empty_part_dividers(chapters: list) -> list:
    """Filter out empty part divider pages that only repeat the part title with no prose."""
    cleaned = []
    active_part = None
    for ch in chapters:
        is_dummy = (
            getattr(ch, "section_type", None) == "part"
            and len(ch.paragraphs) <= 1
            and (
                len(ch.paragraphs) == 0
                or ch.paragraphs[0].text.strip().lower() == ch.title.strip().lower()
                or len(ch.paragraphs[0].text.split()) <= 5
            )
        )
        if is_dummy:
            active_part = ch.title
            continue
        if active_part and not getattr(ch, "part_title", None) and getattr(ch, "category", "body") == "body":
            ch.part_title = active_part
        cleaned.append(ch)
    return cleaned


def categorize_document_chapters(chapters: list) -> int:
    """Post-process a list of Chapter objects to assign consistent categories, numbers, and badges.
    
    Returns total count of body chapters.
    """
    total_count = len(chapters)
    body_ch_counter = 1
    current_part_title = None

    for idx, ch in enumerate(chapters):
        pos_ratio = idx / max(1, total_count)
        
        detected_cat, detected_type, detected_badge = classify_title(ch.title, pos_ratio)

        # Respect explicit TOC classification
        if getattr(ch, "is_toc", False) or getattr(ch, "section_type", None) == "toc":
            ch.category = "front_matter"
            ch.section_type = "toc"
            ch.badge_label = "TOC"
        elif getattr(ch, "section_type", None) in ("title_page", "copyright", "introduction", "cover"):
            ch.category = "front_matter"
            ch.badge_label = detected_badge
        elif getattr(ch, "section_type", None) in ("appendix", "index", "bibliography", "notes", "glossary"):
            ch.category = "back_matter"
            ch.badge_label = detected_badge
        else:
            ch.category = detected_cat
            ch.section_type = detected_type
            ch.badge_label = detected_badge

        # Update boolean flags
        ch.is_toc = (ch.section_type == "toc")
        ch.is_front_matter = (ch.category == "front_matter")
        ch.is_back_matter = (ch.category == "back_matter")

        # Track Part banner
        if ch.section_type == "part":
            current_part_title = ch.title
            ch.part_title = current_part_title
            ch.badge_label = "Part"
            ch.chapter_number = None

        # Number body chapters sequentially
        elif ch.category == "body" and ch.section_type in ("chapter", "section"):
            ch.chapter_number = body_ch_counter
            ch.badge_label = f"Ch {body_ch_counter}"
            body_ch_counter += 1
            if current_part_title and not getattr(ch, "part_title", None):
                ch.part_title = current_part_title
        elif ch.is_toc:
            ch.badge_label = "TOC"
            ch.chapter_number = None
        elif ch.section_type == "index":
            ch.badge_label = "Index"
            ch.chapter_number = None
        elif ch.section_type == "appendix":
            ch.badge_label = "App"
            ch.chapter_number = None
        elif ch.section_type == "bibliography":
            ch.badge_label = "Refs"
            ch.chapter_number = None
        else:
            ch.chapter_number = None

    total_body = body_ch_counter - 1
    return total_body
