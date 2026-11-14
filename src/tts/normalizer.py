"""Semantic Rigor Domain-General Text Normalizer & Sentence Boundary Disambiguator.

Handles technical/engineering prose, financial/legal notation, academic/patristic
citations, literary dialogue, and contextual English homographs without overfitting
to any single genre.
"""
from __future__ import annotations

import re
from typing import List, Tuple

# Roman numerals mapping (1..100 + common centuries/monarchs)
ROMAN_MAP = {
    'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
    'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10',
    'XI': '11', 'XII': '12', 'XIII': '13', 'XIV': '14', 'XV': '15',
    'XVI': '16', 'XVII': '17', 'XVIII': '18', 'XIX': '19', 'XX': '20',
    'XXI': '21', 'XXII': '22', 'XXIII': '23', 'XXIV': '24', 'XXV': '25',
    'XXVI': '26', 'XXVII': '27', 'XXVIII': '28', 'XXIX': '29', 'XXX': '30',
    'XXXI': '31', 'XXXII': '32', 'XXXIII': '33', 'XXXIV': '34', 'XXXV': '35',
    'XXXVI': '36', 'XXXVII': '37', 'XXXVIII': '38', 'XXXIX': '39', 'XL': '40',
    'L': '50', 'LX': '60', 'LXX': '70', 'LXXX': '80', 'XC': '90', 'C': '100',
}

ORDINALS = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
    6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
    11: "eleventh", 12: "twelfth", 13: "thirteenth", 14: "fourteenth",
    15: "fifteenth", 16: "sixteenth", 17: "seventeenth", 18: "eighteenth",
    19: "nineteenth", 20: "twentieth",
}

UNITS = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def num_to_words(n: int) -> str:
    """Convert integer to English words."""
    if n < 0:
        return "negative " + num_to_words(-n)
    if n < 20:
        return UNITS[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else "-" + UNITS[n % 10])
    if n < 1000:
        return UNITS[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + num_to_words(n % 100))
    if n < 1_000_000:
        return num_to_words(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + num_to_words(n % 1000))
    if n < 1_000_000_000:
        return num_to_words(n // 1_000_000) + " million" + ("" if n % 1_000_000 == 0 else " " + num_to_words(n % 1_000_000))
    return str(n)


def format_subdivision(val_str: str) -> str:
    """Format section/line subdivisions like 881 -> 'eight eighty-one', 45 -> 'forty-five'."""
    try:
        val = int(val_str)
        if val < 100:
            return num_to_words(val)
        elif val < 1000:
            h = val // 100
            rem = val % 100
            h_w = num_to_words(h)
            if rem == 0:
                return f"{h_w} hundred"
            elif rem < 10:
                return f"{h_w} oh {num_to_words(rem)}"
            else:
                return f"{h_w} {num_to_words(rem)}"
        return num_to_words(val)
    except ValueError:
        return val_str


def unhyphenate(text: str) -> str:
    """Repair soft line-break hyphens: 'in-\\nteresting' -> 'interesting'."""
    return re.sub(r'(\b[a-zA-Z]{2,})-\s*\n\s*([a-zA-Z]{2,}\b)', r'\1\2', text)


def clean_footnotes(text: str) -> str:
    """Remove inline footnote markers like [1], [12], (3) from TTS stream."""
    text = re.sub(r'\[\s*\d+(?:\s*,\s*\d+)*\s*\]', '', text)
    text = re.sub(r'(?<=[a-zA-Z.,;])\s*\(\d+\)', '', text)
    return text


def convert_structural_roman(text: str) -> str:
    """Convert Roman numerals in structural headers and monarch/pope titles."""
    def repl_range(m):
        prefix = m.group(1)
        r1 = m.group(2).upper()
        r2 = m.group(3).upper()
        n1 = ROMAN_MAP.get(r1, r1)
        n2 = ROMAN_MAP.get(r2, r2)
        return f"{prefix} {n1} to {n2}"

    def repl_single(m):
        prefix = m.group(1)
        r = m.group(2).upper()
        n = ROMAN_MAP.get(r, r)
        return f"{prefix} {n}"

    text = re.sub(
        r'\b(Chapters|Sections|Books|Parts|Vols|Volumes)\s+([IVXLCDM]+)\s*[-–]\s*([IVXLCDM]+)\b',
        repl_range, text, flags=re.IGNORECASE,
    )
    text = re.sub(
        r'\b(Chapter|Section|Book|Part|Volume|Act|Scene|Ch|Chap|Sec|Pt|Vol)\.?\s+([IVXLCDM]+)\b',
        repl_single, text, flags=re.IGNORECASE,
    )

    # Monarchs / Popes: Henry VIII, Louis XIV, Pope John Paul II
    def repl_monarch(m):
        name = m.group(1)
        r = m.group(2).upper()
        num_str = ROMAN_MAP.get(r)
        if not num_str:
            return m.group(0)
        ord_word = ORDINALS.get(int(num_str), num_str)
        return f"{name} the {ord_word}"

    text = re.sub(
        r'\b(Henry|Louis|Charles|George|Edward|Richard|Philip|James|William|Elizabeth|Pope\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|XIV|XV|XVI)\b',
        repl_monarch, text,
    )
    return text


def expand_currencies_and_numbers(text: str) -> str:
    """Expand currencies ($4.5M, $4,500.50), percentages, ISO dates, and units."""
    # Scaled currencies: $4.5M, $1.2B, $500K
    scale_map = {"K": "thousand", "M": "million", "B": "billion", "T": "trillion"}

    def repl_scaled_currency(m):
        sym = m.group(1)
        num = m.group(2)
        scale = scale_map.get(m.group(3).upper(), "")
        unit = {"$" : "dollars", "£": "pounds", "€": "euros"}.get(sym, "dollars")
        return f"{num} {scale} {unit}"

    text = re.sub(r'([\$£€])([0-9]+(?:\.[0-9]+)?)\s*([KMBT])\b', repl_scaled_currency, text, flags=re.IGNORECASE)

    # Exact currencies: $4,500.50
    def repl_dollars(match):
        dollars = match.group(1)
        cents = match.group(2)
        try:
            d_val = int(dollars.replace(',', ''))
            d_words = num_to_words(d_val) + (" dollar" if d_val == 1 else " dollars")
            if cents:
                c_val = int(cents)
                if c_val > 0:
                    c_words = num_to_words(c_val) + (" cent" if c_val == 1 else " cents")
                    return f"{d_words} and {c_words}"
            return d_words
        except ValueError:
            return match.group(0)

    text = re.sub(r'\$([0-9,]+)(?:\.([0-9]{2}))?\b', repl_dollars, text)
    text = re.sub(r'£([0-9,]+)\b', lambda m: num_to_words(int(m.group(1).replace(',', ''))) + " pounds", text)
    text = re.sub(r'€([0-9,]+)\b', lambda m: num_to_words(int(m.group(1).replace(',', ''))) + " euros", text)

    # ISO Dates: 2026-11-14 -> November 14, 2026
    def repl_iso_date(m):
        yr, mo, dy = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= dy <= 31:
            return f"{MONTHS[mo]} {dy}, {yr}"
        return m.group(0)

    text = re.sub(r'\b(19\d{2}|20\d{2})-(\d{2})-(\d{2})\b', repl_iso_date, text)

    # Percentages & Degrees
    text = re.sub(r'(\d+(?:\.\d+)?)\s*%', r'\1 percent', text)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*°\s*C\b', r'\1 degrees Celsius', text)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*°\s*F\b', r'\1 degrees Fahrenheit', text)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*°\b', r'\1 degrees', text)

    # Era markers: 500 BCE -> 500 B C E
    text = re.sub(r'\b(\d+)\s*BCE\b', r'\1 B C E', text)
    text = re.sub(r'\b(\d+)\s*CE\b', r'\1 C E', text)
    text = re.sub(r'\b(\d+)\s*BC\b', r'\1 B C', text)
    text = re.sub(r'\bAD\s*(\d+)\b', r'A D \1', text)

    return text


def normalize_technical_and_units(text: str) -> str:
    """Normalize engineering units, version tags, identifiers, and operators."""
    # Compound data-rate units first
    text = re.sub(r'\b(\d+(?:\.\d+)?)\s*GB/s\b', r'\1 gigabytes per second', text)
    text = re.sub(r'\b(\d+(?:\.\d+)?)\s*MB/s\b', r'\1 megabytes per second', text)
    text = re.sub(r'\b(\d+(?:\.\d+)?)\s*Gbps\b', r'\1 gigabits per second', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(\d+(?:\.\d+)?)\s*Mbps\b', r'\1 megabits per second', text, flags=re.IGNORECASE)

    unit_map = [
        (r'TB', 'terabytes'),
        (r'GB', 'gigabytes'),
        (r'MB', 'megabytes'),
        (r'KB', 'kilobytes'),
        (r'GHz', 'gigahertz'),
        (r'MHz', 'megahertz'),
        (r'kHz', 'kilohertz'),
        (r'Hz', 'hertz'),
        (r'ms', 'milliseconds'),
        (r'μs|us', 'microseconds'),
        (r'ns', 'nanoseconds'),
        (r'km', 'kilometers'),
        (r'cm', 'centimeters'),
        (r'mm', 'millimeters'),
        (r'kg', 'kilograms'),
        (r'mg', 'milligrams'),
        (r'kW', 'kilowatts'),
        (r'mW', 'milliwatts'),
    ]
    for abbr, full in unit_map:
        text = re.sub(rf'\b(\d+(?:\.\d+)?)\s*{abbr}\b', rf'\1 {full}', text)

    # Resolution / dimensions: 1920x1080 or 1920×1080
    text = re.sub(r'\b(\d+)\s*[x×]\s*(\d+)\b', r'\1 by \2', text)

    # Version numbers: v1.0.16 or v2.5 -> version 1 point 0 point 16
    def repl_version(m):
        parts = m.group(1).split('.')
        return "version " + " point ".join(parts)

    text = re.sub(r'\bv(\d+(?:\.\d+)+)\b', repl_version, text)

    # URLs in prose: https://docs.python.org/3/library -> docs dot python dot org
    text = re.sub(r'https?://([a-zA-Z0-9.-]+)(?:/[^\s)]*)?', lambda m: m.group(1).replace('.', ' dot '), text)

    # Operators & arrows
    text = text.replace('→', ' to ').replace('->', ' to ').replace('=>', ' yields ')
    text = text.replace('!=', ' not equal to ').replace('>=', ' greater than or equal to ').replace('<=', ' less than or equal to ')
    text = re.sub(r'(?<=[a-zA-Z0-9])/(?=[a-zA-Z0-9])', ' or ', text)

    # snake_case identifiers in prose -> spaced words
    text = re.sub(r'\b([a-zA-Z]+)_([a-zA-Z0-9_]+)\b', lambda m: f"{m.group(1)} {m.group(2).replace('_', ' ')}", text)

    return text


# Context-gated biblical/classical book abbreviations (only expand when followed by chapter/verse!)
CONTEXTUAL_BIBLICAL_ABBRS = {
    'Matt': 'Matthew', 'Mk': 'Mark', 'Lk': 'Luke', 'Jn': 'John',
    'Rom': 'Romans', 'Cor': 'Corinthians', 'Gal': 'Galatians', 'Eph': 'Ephesians',
    'Phil': 'Philippians', 'Col': 'Colossians', 'Thess': 'Thessalonians',
    'Tim': 'Timothy', 'Tit': 'Titus', 'Heb': 'Hebrews', 'Jas': 'James',
    'Pet': 'Peter', 'Rev': 'Revelation', 'Gen': 'Genesis', 'Ex': 'Exodus',
    'Lev': 'Leviticus', 'Num': 'Numbers', 'Deut': 'Deuteronomy',
    'Ps': 'Psalm', 'Pss': 'Psalms', 'Prov': 'Proverbs', 'Isa': 'Isaiah', 'Jer': 'Jeremiah',
}


def normalize_citations_and_references(text: str) -> str:
    """Naturalize classical, legal, academic, and biblical citations without colliding with titles."""
    # Classical/patristic works
    text = re.sub(r'\bComm\b\.?', 'Commentary', text, flags=re.IGNORECASE)
    text = re.sub(r'\bHom\b\.?', 'Homily', text, flags=re.IGNORECASE)
    text = re.sub(r'\bTract\b\.?', 'Tractate', text, flags=re.IGNORECASE)
    text = re.sub(r'\bEp\b\.', 'Epistle', text, flags=re.IGNORECASE)
    text = re.sub(r'\bEpp\b\.?', 'Epistles', text, flags=re.IGNORECASE)
    text = re.sub(r'\bHist\b\.', 'History', text, flags=re.IGNORECASE)
    text = re.sub(r'\bDe Cultu Fem\b\.?', 'De Cultu Feminarum', text, flags=re.IGNORECASE)
    text = re.sub(r'\bStrom\b\.?', 'Stromata', text, flags=re.IGNORECASE)

    # Context-gated biblical book expansion: ONLY when followed by chapter[:.]verse or chapter number
    abbr_pat = "|".join(CONTEXTUAL_BIBLICAL_ABBRS.keys())
    text = re.sub(
        rf'\b({abbr_pat})\.?\s+(?=\d+(?:[:.]\d+)?\b)',
        lambda m: CONTEXTUAL_BIBLICAL_ABBRS.get(m.group(1), m.group(1)) + " ",
        text,
    )

    # Numbered books: 1 Enoch, 2 Corinthians, 1 John -> First Enoch, Second Corinthians
    book_ordinals = {"1": "First", "2": "Second", "3": "Third"}
    numbered_books = (
        "Enoch|Baruch|Maccabees|Kings|Chronicles|Samuel|Corinthians|"
        "Thessalonians|Timothy|Peter|John|Esdras"
    )
    text = re.sub(
        rf'\b([123])\s+({numbered_books})\b',
        lambda m: f"{book_ordinals[m.group(1)]} {m.group(2)}",
        text,
    )

    # Chapter and verse notation: e.g. Matthew 10.18 or Genesis 1:1
    all_books = "|".join(set(CONTEXTUAL_BIBLICAL_ABBRS.values()) | {"Enoch", "Baruch", "Maccabees"})
    text = re.sub(
        rf'\b({all_books})\s+(\d+)[:.](\d+)\b',
        r'\1, chapter \2, verse \3',
        text,
    )

    # Lowercase Roman citation pairs like "i. 3" or "ii. 14" inside scholarly citations
    def repl_lower_roman(m):
        r = m.group(1).upper()
        n = ROMAN_MAP.get(r)
        if not n:
            return m.group(0)
        return f"book {n}, section {m.group(2)}"

    text = re.sub(r'\b([ivx]{1,4})\.\s*(\d+)\b', repl_lower_roman, text)

    # Legal section symbol
    text = re.sub(r'§§\s*(\d+)\s*[-–]\s*(\d+)', r'Sections \1 to \2', text)
    text = re.sub(r'§\s*(\d+)', r'Section \1', text)

    # Page with line/subdivision: p. 13.881 -> page 13, eight eighty-one
    text = re.sub(r'\bp\.?\s*(\d+)\.(\d+)\b', lambda m: f"page {m.group(1)}, {format_subdivision(m.group(2))}", text)
    text = re.sub(r'\bp\.?\s*(\d+)\b', r'page \1', text)
    text = re.sub(r'\bpp\.?\s*(\d+)\s*[-–]\s*(\d+)\b', r'pages \1 to \2', text)
    text = re.sub(r'\bpp\.?\s*(\d+)\b', r'pages \1', text)

    # Parenthetical citations -> natural spoken pause
    text = re.sub(
        r'\(([^)]*?(?:Commentary|chapter|page|verse|ibid|compare|et al|Section|Chapter|book)[^)]*?)\)',
        lambda m: f", {re.sub(r';\\s*', ', ', m.group(1).strip())},",
        text,
    )
    return text


def normalize_general_abbreviations(text: str) -> str:
    """Expand structural, scholarly, military/honorific, and street abbreviations."""
    text = re.sub(r'\b(?:Ch|ch|Chap|chap)\.?\s*(\d+)\b', r'Chapter \1', text)
    text = re.sub(r'\b(?:Sec|sec)\.?\s*(\d+)\b', r'Section \1', text)
    text = re.sub(r'\b(?:Bk|bk)\.?\s*(\d+)\b', r'Book \1', text)
    text = re.sub(r'\b(?:Pt|pt)\.?\s*(\d+)\b', r'Part \1', text)
    text = re.sub(r'\b(?:Vol|vol)\.?\s*(\d+)\b', r'Volume \1', text)
    text = re.sub(r'\b(?:Vols|vols)\.?\s*(\d+)\b', r'Volumes \1', text)
    text = re.sub(r'\b(?:fig|Fig)\.?\s*(\d+)\b', r'figure \1', text)
    text = re.sub(r'\b(?:figs|Figs)\.?\s*(\d+)\b', r'figures \1', text)
    text = re.sub(r'\b(?:no|No|NO)\.?\s*(\d+)\b', r'number \1', text)
    text = re.sub(r'\b(?:nos|Nos)\.?\s*(\d+)\b', r'numbers \1', text)
    text = re.sub(r'\b(?:app|App)\.?\s*([0-9A-Z]+)\b', r'Appendix \1', text)

    # Scholarly Latin
    text = re.sub(r'\bet al\b\.?', 'and others', text)
    text = re.sub(r'\bibid\b\.?', 'in the same place', text)
    text = re.sub(r'\bop\.?\s*cit\b\.?', 'in the work cited', text)
    text = re.sub(r'\bloc\.?\s*cit\b\.?', 'in the place cited', text)
    text = re.sub(r'\bcf\b\.', 'compare', text)
    text = re.sub(r'\bca\b\.', 'circa', text)
    text = re.sub(r'\bc\.\s*(?=\d{3,4})', 'circa ', text)
    text = re.sub(r'\be\.g\b\.?', 'for example,', text)
    text = re.sub(r'\bi\.e\b\.?', 'that is,', text)
    text = re.sub(r'\betc\b\.?', 'et cetera', text)
    text = re.sub(r'\bvs?\b\.', 'versus', text)

    # Publishing
    text = re.sub(r'\b(?:ed|Ed)\b\.', 'edition', text)
    text = re.sub(r'\b(?:eds|Eds)\b\.', 'editions', text)
    text = re.sub(r'\b(?:trans|Trans)\b\.', 'translated by', text)
    text = re.sub(r'\b(?:intro|Intro)\b\.', 'Introduction', text)
    text = re.sub(r'\b(?:pref|Pref)\b\.', 'Preface', text)
    text = re.sub(r'\b(?:prol|Prol)\b\.', 'Prologue', text)

    # Titles & Honorifics (safe now because Gen./Col./Rev. aren't blindly eaten)
    text = re.sub(r'\bDr\b\.', 'Doctor', text)
    text = re.sub(r'\bMr\b\.', 'Mister', text)
    text = re.sub(r'\bMrs\b\.', 'Missus', text)
    text = re.sub(r'\bMs\b\.', 'Mizz', text)
    text = re.sub(r'\bProf\b\.', 'Professor', text)
    text = re.sub(r'\bRev\b\.', 'Reverend', text)
    text = re.sub(r'\bGen\b\.', 'General', text)
    text = re.sub(r'\bCol\b\.', 'Colonel', text)
    text = re.sub(r'\bCapt\b\.', 'Captain', text)
    text = re.sub(r'\bLt\b\.', 'Lieutenant', text)
    text = re.sub(r'\bSgt\b\.', 'Sergeant', text)
    text = re.sub(r'\bMt\b\.', 'Mount', text)
    text = re.sub(r'\bJr\b\.', 'Junior', text)
    text = re.sub(r'\bSr\b\.', 'Senior', text)

    # Contextual St.: Saint vs Street
    text = re.sub(r'\bSt\.\s+(?=[A-Z])', 'Saint ', text)
    text = re.sub(r'\bSt\.\b', 'Street', text)

    # Shorthand
    text = re.sub(r'\bw/', 'with ', text)
    text = re.sub(r'\bw/o', 'without ', text)
    text = re.sub(r'\bb/c', 'because ', text)
    text = re.sub(r'\s+&\s+', ' and ', text)

    return text


def disambiguate_homographs(text: str) -> str:
    """Apply lightweight contextual IPA markers for common English homographs.

    Returns text where disambiguated homographs are replaced with /IPA/ tokens
    (which TTSEngine's hybrid phonemizer injects directly).
    """
    # 'read' (past /ɹˈɛd/ vs present /ɹˈiːd/)
    text = re.sub(
        r'\b(have|has|had|was|were|been|being|already|just|once|ever|never)\s+read\b',
        r'\1 /ɹˈɛd/',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'\bread\s+(by|through|about|that\s+book|the\s+book|it\s+yesterday)\b',
        r'/ɹˈɛd/ \1',
        text,
        flags=re.IGNORECASE,
    )

    # 'live' (adjective /lˈaɪv/ vs verb /lˈɪv/)
    text = re.sub(
        r'\b(a|the|this|my|our)\s+live\s+(stream|broadcast|performance|show|event|wire|feed|session|music|audience)\b',
        r'\1 /lˈaɪv/ \2',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'\blive\s+(stream|streaming|broadcast|wire|feed|coverage)\b',
        r'/lˈaɪv/ \1',
        text,
        flags=re.IGNORECASE,
    )

    # 'lead' (metal /lˈɛd/ vs verb/noun /lˈiːd/)
    text = re.sub(
        r'\b(heavy|made\s+of|molten|toxic)\s+lead\b',
        r'\1 /lˈɛd/',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r'\blead\s+(pipe|pipes|paint|poisoning|shielding|acid|weights?|bullets?)\b',
        r'/lˈɛd/ \1',
        text,
        flags=re.IGNORECASE,
    )

    # 'wind' (verb /wˈaɪnd/ vs noun /wˈɪnd/)
    text = re.sub(
        r'\b(to|will|can|could|should|would|must|may|might)\s+wind\b',
        r'\1 /wˈaɪnd/',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r'\bwind\s+(up|down)\b', r'/wˈaɪnd/ \1', text, flags=re.IGNORECASE)

    # 'minute' (adjective /maɪnjˈuːt/ vs time noun /mˈɪnɪt/)
    text = re.sub(
        r'\bminute\s+(details?|particles?|fraction|amount|differences?|scale)\b',
        r'/maɪnjˈuːt/ \1',
        text,
        flags=re.IGNORECASE,
    )

    # 'resume' (noun /ɹˈɛzəmeɪ/ vs verb /ɹɪzˈuːm/)
    text = re.sub(
        r'\b(a|the|my|your|his|her|their)\s+resume\b',
        r'\1 /ɹˈɛzəmeɪ/',
        text,
        flags=re.IGNORECASE,
    )

    return text


def normalize_text_for_tts(text: str) -> str:
    """Single-pass normalization pipeline preparing text for hybrid phonemization."""
    if not text:
        return ""

    text = unhyphenate(text)
    text = clean_footnotes(text)
    text = convert_structural_roman(text)
    text = expand_currencies_and_numbers(text)
    text = normalize_technical_and_units(text)
    text = normalize_citations_and_references(text)
    text = normalize_general_abbreviations(text)
    text = disambiguate_homographs(text)

    # Clean redundant markdown/punctuation symbols without stripping IPA slashes
    text = re.sub(r'[*_~`#^>|]', ' ', text)
    text = re.sub(r'["""]', '"', text)
    text = re.sub(r"[''']", "'", text)
    text = re.sub(r'—', ' — ', text)
    text = re.sub(r';\s*', ', ', text)
    text = re.sub(r'\s*,\s*,+', ',', text)
    text = re.sub(r'\s+,', ',', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip(' ,')


# Recognized abbreviations for sentence boundary protection
PROTECTED_ABBRS = {
    'mr', 'mrs', 'ms', 'dr', 'prof', 'rev', 'gen', 'col', 'capt', 'lt', 'sgt', 'st', 'mt', 'jr', 'sr',
    'ch', 'chap', 'sec', 'vol', 'vols', 'bk', 'pt', 'fig', 'figs', 'eq', 'eqs', 'fn', 'app', 'no', 'nos', 'p', 'pp',
    'comm', 'hom', 'ep', 'epp', 'tract', 'hist', 'matt', 'mk', 'lk', 'jn', 'rom', 'cor', 'gal', 'eph', 'phil', 'col',
    'thess', 'tim', 'tit', 'heb', 'jas', 'pet', 'rev', 'gen', 'ex', 'lev', 'num', 'deut', 'ps', 'pss', 'prov', 'isa', 'jer',
    'cf', 'ca', 'c', 'ed', 'eds', 'ibid', 'viz', 'al', 'eg', 'e.g', 'ie', 'i.e', 'etc', 'vs', 'v', 'inc', 'ltd', 'corp',
}


def split_into_sentences(text: str) -> List[Tuple[str, int, int]]:
    """Depth-aware sentence boundary disambiguation.

    Guarantees that:
    1. Parenthetical expressions (citations, asides) are never split mid-sentence.
    2. Abbreviations (Ch., p., Dr., Inc., v.) are never mistaken for sentence boundaries.
    3. Decimal numbers, version numbers, and chapter.verse notations never trigger splits.
    """
    if not text:
        return []

    sentences: List[Tuple[str, int, int]] = []
    n = len(text)
    start = 0
    depth = 0

    i = 0
    while i < n:
        ch = text[i]

        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth = max(0, depth - 1)

        if depth == 0 and ch in '.!?':
            if ch == '.' and ((i + 1 < n and text[i + 1] == '.') or (i > 0 and text[i - 1] == '.')):
                i += 1
                continue

            is_abbr = False
            w_match = re.search(r'([a-zA-Z]+)\.$', text[:i + 1])
            if w_match:
                word = w_match.group(1).lower()
                if len(word) == 1 or word in PROTECTED_ABBRS:
                    is_abbr = True

            if not is_abbr and ch == '.' and i + 1 < n and text[i + 1].isdigit():
                is_abbr = True

            if not is_abbr:
                end_punc = i + 1
                while end_punc < n and text[end_punc] in '\"\'”’)]}':
                    end_punc += 1

                if end_punc >= n:
                    raw_s = text[start:end_punc].strip()
                    if raw_s:
                        sentences.append((raw_s, start, end_punc))
                    start = end_punc
                    i = end_punc
                    continue
                elif text[end_punc].isspace():
                    rem = text[end_punc:].lstrip()
                    if not rem or rem[0].isupper() or rem[0] in '\"\'“‘—':
                        raw_s = text[start:end_punc].strip()
                        if raw_s:
                            s_start = text.find(raw_s, start)
                            s_end = s_start + len(raw_s)
                            sentences.append((raw_s, s_start, s_end))
                        start = end_punc
                        i = end_punc
                        continue
        i += 1

    if start < n:
        trailing = text[start:].strip()
        if trailing:
            s_start = text.find(trailing, start)
            s_end = s_start + len(trailing)
            sentences.append((trailing, s_start, s_end))

    return sentences
