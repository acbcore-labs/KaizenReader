"""Semantic Rigor Text Normalizer & Depth-Aware Sentence Disambiguator.

Engineered specifically for complex literature, scholarly introductions,
patristic citations, and biblical/classical works (e.g. The Book of Enoch, Origen, Charles).
"""
import re
from typing import List, Tuple
from src.tts.lexicon import LexiconManager

# Roman numerals mapping
ROMAN_MAP = {
    'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
    'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10',
    'XI': '11', 'XII': '12', 'XIII': '13', 'XIV': '14', 'XV': '15',
    'XVI': '16', 'XVII': '17', 'XVIII': '18', 'XIX': '19', 'XX': '20',
    'XXI': '21', 'XXII': '22', 'XXIII': '23', 'XXIV': '24', 'XXV': '25',
    'XXVI': '26', 'XXVII': '27', 'XXVIII': '28', 'XXIX': '29', 'XXX': '30',
    'XXXI': '31', 'XXXII': '32', 'XXXIII': '33', 'XXXIV': '34', 'XXXV': '35',
    'XXXVI': '36', 'XXXVII': '37', 'XXXVIII': '38', 'XXXIX': '39', 'XL': '40',
    'L': '50', 'LX': '60', 'LXX': '70', 'LXXX': '80', 'XC': '90', 'C': '100'
}

# Number words for basic currency & subdivision expansion
UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
         "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
         "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

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
    if n < 1000000:
        return num_to_words(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + num_to_words(n % 1000))
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
    """Repair soft line-break hyphens: 'in-\nteresting' -> 'interesting'."""
    return re.sub(r'(\b[a-zA-Z]{2,})-\s*\n\s*([a-zA-Z]{2,}\b)', r'\1\2', text)

def clean_footnotes(text: str) -> str:
    """Remove footnote markers like [1], [12], (3) from TTS stream."""
    text = re.sub(r'\[\s*\d+\s*\]', '', text)
    text = re.sub(r'(?<=[a-zA-Z])\s*\(\d+\)', '', text)
    return text

def convert_structural_roman(text: str) -> str:
    """Convert Roman numerals in chapters/sections (e.g. 'Ch. IV' -> 'Chapter 4', 'Chapters I-XXXVI' -> 'Chapters 1 to 36')."""
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

    # Range: e.g. Chapters I-XXXVI
    text = re.sub(
        r'\b(Chapters|Sections|Books|Parts|Vols|Volumes)\s+([IVXLCDM]+)\s*[-–]\s*([IVXLCDM]+)\b',
        repl_range, text, flags=re.IGNORECASE
    )
    # Single: e.g. Chapter IV, Section II, Ch. VI
    text = re.sub(
        r'\b(Chapter|Section|Book|Part|Volume|Act|Scene|Ch|Chap|Sec|Pt|Vol)\.?\s+([IVXLCDM]+)\b',
        repl_single, text, flags=re.IGNORECASE
    )
    return text

def expand_currencies(text: str) -> str:
    """Expand $100 -> 'one hundred dollars', $15.50 -> 'fifteen dollars and fifty cents'."""
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

    text = re.sub(r'\$([0-9,]+)(?:\.([0-9]{2}))?', repl_dollars, text)
    text = re.sub(r'£([0-9,]+)', lambda m: num_to_words(int(m.group(1).replace(',', ''))) + " pounds", text)
    text = re.sub(r'€([0-9,]+)', lambda m: num_to_words(int(m.group(1).replace(',', ''))) + " euros", text)
    return text

def normalize_citations_and_references(text: str) -> str:
    """Naturalize classical, patristic, and biblical citations in literature."""
    # Classical works
    text = re.sub(r'\bComm\b\.?', 'Commentary', text, flags=re.IGNORECASE)
    text = re.sub(r'\bHom\b\.?', 'Homily', text, flags=re.IGNORECASE)
    text = re.sub(r'\bTract\b\.?', 'Tractate', text, flags=re.IGNORECASE)
    text = re.sub(r'\bEp\b\.?', 'Epistle', text, flags=re.IGNORECASE)
    text = re.sub(r'\bEpp\b\.?', 'Epistles', text, flags=re.IGNORECASE)
    text = re.sub(r'\bHist\b\.?', 'History', text, flags=re.IGNORECASE)
    text = re.sub(r'\bDe Cultu Fem\b\.?', 'De Cultu Feminarum', text, flags=re.IGNORECASE)
    text = re.sub(r'\bStrom\b\.?', 'Stromata', text, flags=re.IGNORECASE)

    # Biblical books
    biblical = {
        r'\bMatt\b\.?': 'Matthew',
        r'\bMk\b\.?': 'Mark',
        r'\bLk\b\.?': 'Luke',
        r'\bJn\b\.?': 'John',
        r'\bRom\b\.?': 'Romans',
        r'\bCor\b\.?': 'Corinthians',
        r'\bGal\b\.?': 'Galatians',
        r'\bEph\b\.?': 'Ephesians',
        r'\bPhil\b\.?': 'Philippians',
        r'\bCol\b\.?': 'Colossians',
        r'\bThess\b\.?': 'Thessalonians',
        r'\bTim\b\.?': 'Timothy',
        r'\bTit\b\.?': 'Titus',
        r'\bHeb\b\.?': 'Hebrews',
        r'\bJas\b\.?': 'James',
        r'\bPet\b\.?': 'Peter',
        r'\bRev\b\.?': 'Revelation',
        r'\bGen\b\.?': 'Genesis',
        r'\bEx\b\.?': 'Exodus',
        r'\bLev\b\.?': 'Leviticus',
        r'\bNum\b\.?': 'Numbers',
        r'\bDeut\b\.?': 'Deuteronomy',
        r'\bPs\b\.?': 'Psalm',
        r'\bPss\b\.?': 'Psalms',
        r'\bProv\b\.?': 'Proverbs',
        r'\bIsa\b\.?': 'Isaiah',
        r'\bJer\b\.?': 'Jeremiah',
    }
    for pat, name in biblical.items():
        text = re.sub(pat, name, text)

    # Chapter and verse notation: e.g. Matthew 10.18 -> Matthew, chapter 10, verse 18
    def repl_chap_verse(m):
        book = m.group(1)
        ch = m.group(2)
        vs = m.group(3)
        return f"{book}, chapter {ch}, verse {vs}"

    text = re.sub(
        r'\b(Matthew|Mark|Luke|John|Romans|Corinthians|Galatians|Ephesians|Philippians|Colossians|Thessalonians|Timothy|Titus|Hebrews|James|Peter|Revelation|Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Psalm|Psalms|Proverbs|Isaiah|Jeremiah)\s+(\d+)[:.](\d+)\b',
        repl_chap_verse, text
    )

    # Page with line/subdivision: p. 13.881 -> page 13, eight eighty-one
    def repl_p_sub(m):
        pg = m.group(1)
        sub = m.group(2)
        sub_words = format_subdivision(sub)
        return f"page {pg}, {sub_words}"

    text = re.sub(r'\bp\.?\s*(\d+)\.(\d+)\b', repl_p_sub, text)
    text = re.sub(r'\bp\.?\s*(\d+)\b', r'page \1', text)
    text = re.sub(r'\bpp\.?\s*(\d+)\s*[-–]\s*(\d+)\b', r'pages \1 to \2', text)
    text = re.sub(r'\bpp\.?\s*(\d+)\b', r'pages \1', text)

    # Turn parenthetical citations into natural spoken pauses without saying 'open paren'
    def repl_parens(m):
        inside = m.group(1).strip()
        # Convert semicolons inside citations to commas
        inside = re.sub(r';\s*', ', ', inside)
        return f", {inside},"

    # Match parens containing citation words
    text = re.sub(r'\(([^)]*?(?:Commentary|Matthew|chapter|page|verse|ibid|compare|et al|Section|Chapter)[^)]*?)\)', repl_parens, text)
    return text

def normalize_general_abbreviations(text: str) -> str:
    """Expand structural and literary abbreviations into full phonemes."""
    # Structural book notations
    text = re.sub(r'\b(?:Ch|ch)\.?\s*(\d+)\b', r'Chapter \1', text)
    text = re.sub(r'\b(?:Chap|chap)\.?\s*(\d+)\b', r'Chapter \1', text)
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
    text = re.sub(r'\bvs\b\.?', 'versus', text)

    # Publishing
    text = re.sub(r'\b(?:ed|Ed)\b\.', 'edition', text)
    text = re.sub(r'\b(?:eds|Eds)\b\.', 'editions', text)
    text = re.sub(r'\b(?:trans|Trans)\b\.', 'translated by', text)
    text = re.sub(r'\b(?:intro|Intro)\b\.', 'Introduction', text)
    text = re.sub(r'\b(?:pref|Pref)\b\.', 'Preface', text)
    text = re.sub(r'\b(?:prol|Prol)\b\.', 'Prologue', text)

    # Titles & Honorifics
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
    text = re.sub(r'\b&\b', 'and', text)

    return text

def normalize_text_for_tts(text: str) -> str:
    """Full normalization pipeline for text sent to Kokoro."""
    if not text:
        return ""

    text = unhyphenate(text)
    text = clean_footnotes(text)
    text = convert_structural_roman(text)
    text = expand_currencies(text)
    text = normalize_citations_and_references(text)
    text = normalize_general_abbreviations(text)

    # Apply pronunciation lexicon (names like Manasseh, Origen, etc.)
    lex = LexiconManager.get_instance()
    text = lex.apply(text)

    # Clean redundant punctuation and symbols
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
    'cf', 'ca', 'c', 'ed', 'eds', 'ibid', 'viz', 'al', 'eg', 'e.g', 'ie', 'i.e', 'etc', 'vs'
}

def split_into_sentences(text: str) -> List[Tuple[str, int, int]]:
    """Depth-aware sentence boundary disambiguation.

    Guarantees that:
    1. Parenthetical expressions (citations, asides) are NEVER split mid-sentence.
    2. Abbreviations (e.g. Ch., p., Matt., Comm., Dr.) are never mistaken for sentence boundaries.
    3. Decimal numbers and chapter.verse notations (e.g. 10.18, 13.881) never trigger splits.
    """
    if not text:
        return []

    sentences = []
    n = len(text)
    start = 0
    depth = 0

    i = 0
    while i < n:
        ch = text[i]

        # Track parenthesis and bracket depth
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth = max(0, depth - 1)

        # Candidate terminal punctuation
        if depth == 0 and ch in '.!?':
            # Check for multiple dots / ellipsis (e.g. '...' or '..')
            if ch == '.' and ((i + 1 < n and text[i+1] == '.') or (i > 0 and text[i-1] == '.')):
                i += 1
                continue

            # Check preceding word to see if it's an abbreviation
            is_abbr = False
            w_match = re.search(r'([a-zA-Z]+)\.$', text[:i+1])
            if w_match:
                word = w_match.group(1).lower()
                # Single letter initial (e.g. 'A.' or 'J.')
                if len(word) == 1 or word in PROTECTED_ABBRS:
                    is_abbr = True

            # Check if followed by digit (decimal number e.g. 3.14, 10.18, 13.881)
            if not is_abbr and ch == '.' and i + 1 < n and text[i+1].isdigit():
                is_abbr = True

            if not is_abbr:
                # Find punctuation sequence (e.g. '."', '?!')
                end_punc = i + 1
                while end_punc < n and text[end_punc] in '\"\'”’)]}':
                    end_punc += 1

                # Check following character: must be whitespace or EOF
                if end_punc >= n:
                    raw_s = text[start:end_punc].strip()
                    if raw_s:
                        sentences.append((raw_s, start, end_punc))
                    start = end_punc
                    i = end_punc
                    continue
                elif text[end_punc].isspace():
                    rem = text[end_punc:].lstrip()
                    # A true sentence end must be followed by capital letter, quote, em-dash, or EOF
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
