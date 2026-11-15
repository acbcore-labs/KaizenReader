"""Pronunciation Lexicon & Direct IPA Phoneme Engine.

Supports both verified IPA transcriptions (wrapped in /.../ or containing IPA
symbols) and intuitive respellings (e.g. 'muh-NASS-uh'), compiling respellings
into clean Kokoro-compatible IPA so espeak-ng never spells uppercase syllables
as acronyms or adds unnatural stress to every syllable.

Persists user overrides in data/lexicon.json.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from typing import Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from src.config import DATA_DIR

LEXICON_FILE = DATA_DIR / "lexicon.json"
SAVED_PRONUNCIATIONS_FILE = DATA_DIR / "saved_pronunciations.json"

# Kokoro v1.0 valid phoneme vocabulary (114 symbols)
KOKORO_VOCAB_CHARS = set(
    ' !"(),.:;?AIOQSTWYabcdefhijklmnopqrstuvwxyz'
    'æçðøŋœɐɑɒɔɕɖəɚɛɜɟɡɣɤɥɨɪɯɰɲɳɴɸɹɻɽɾʁʂʃʈʊʋʌʎʒʔʝʣʤʥʦʧʨ'
    'ʰʲˈˌː̃βθχᵊᵝᵻ—“”…→↓↗↘ꭧ'
)

IPA_INDICATORS = set("əɚɛɜɪʊʌɑɔæθðʃʒʧʤŋɹɡˈˌːɐɒɨɯɲɳɸɻɽɾʁʂʈʋʎʒʔʝβχ")

# Domain-general built-in IPA lexicon covering Tech/CS, Science, Philosophy,
# Literature, Classical/Biblical, and Tricky English/Loanwords.
DEFAULT_LEXICON: Dict[str, str] = {
    # --- Technology, Engineering & Computer Science ---
    "Nginx": "/ˌɛnʤɪnˈɛks/",
    "Kubernetes": "/kˌuːbɚnˈɛtiːz/",
    "kubectl": "/kjˈuːbkˈʌtəl/",
    "PostgreSQL": "/pˈoʊstɡɹɛs kjˈuː ˈɛl/",
    "SQLite": "/ˌɛs kjˈuː ˈɛl lˈaɪt/",
    "MySQL": "/mˈaɪ ˌɛs kjˈuː ˈɛl/",
    "macOS": "/mˈæk oʊ ˈɛs/",
    "PyTorch": "/pˈaɪtɔːɹʧ/",
    "NumPy": "/nˈʌmpaɪ/",
    "SciPy": "/sˈaɪpaɪ/",
    "FastAPI": "/fˈæst ˌeɪ pˈiː ˈaɪ/",
    "OAuth": "/ˈoʊɔːθ/",
    "JSON": "/ʤˈeɪsən/",
    "YAML": "/jˈæməl/",
    "TOML": "/tˈɑːməl/",
    "ASCII": "/ˈæski/",
    "GUI": "/ɡˈuːi/",
    "daemon": "/dˈiːmən/",
    "cache": "/kˈæʃ/",
    "caches": "/kˈæʃɪz/",
    "cached": "/kˈæʃt/",
    "tuple": "/tˈuːpəl/",
    "deque": "/dˈɛk/",
    "trie": "/tɹˈaɪ/",
    "regex": "/ɹˈɛɡɛks/",
    "sudo": "/sˈuːduː/",
    "chmod": "/ʧˈeɪnʤ mˈɑːd/",
    "LaTeX": "/lˈɑːtɛk/",
    "Archimedes": "/ˌɑːɹkɪmˈiːdiːz/",
    "Euler": "/ˈɔɪlɚ/",
    "Gauss": "/ɡˈaʊs/",
    "Fourier": "/fˈʊɹieɪ/",
    "Laplace": "/ləplˈɑːs/",
    "Poisson": "/pwɑːsˈɔ̃/",
    "Bernoulli": "/bɚnˈuːli/",
    "Riemann": "/ɹˈiːmɑːn/",
    "Lebesgue": "/ləbˈɛɡ/",

    # --- Science, Medicine & Culinary ---
    "epitome": "/ɪpˈɪtəmi/",
    "hyperbole": "/haɪpˈɜːɹbəli/",
    "mnemonic": "/nɪmˈɑːnɪk/",
    "archipelago": "/ˌɑːɹkɪpˈɛləɡoʊ/",
    "anemone": "/ənˈɛməni/",
    "quinoa": "/kˈiːnwɑː/",
    "acai": "/ˌɑːsaɪˈiː/",
    "acetaminophen": "/əsˌiːtəmˈɪnəfən/",
    "macabre": "/məkˈɑːbɹə/",
    "ubiquitous": "/juːbˈɪkwɪtəs/",

    # --- Tricky English & Loanwords ---
    "colonel": "/kˈɜːɹnəl/",
    "albeit": "/ɔːlbˈiːɪt/",
    "facade": "/fəsˈɑːd/",
    "clique": "/klˈiːk/",
    "niche": "/nˈiːʃ/",
    "segue": "/sˈɛɡweɪ/",
    "draught": "/dɹˈæft/",
    "indict": "/ɪndˈaɪt/",
    "subtle": "/sˈʌtəl/",
    "corps": "/kˈɔːɹ/",
    "bourgeois": "/bʊɹʒwˈɑː/",
    "rendezvous": "/ɹˈɑːndeɪvuː/",
    "schadenfreude": "/ʃˈɑːdənfɹɔɪdə/",
    "zeitgeist": "/zˈaɪtɡaɪst/",
    "chiaroscuro": "/kiˌɑːɹəskjˈʊɹoʊ/",
    "worcestershire": "/wˈʊstɚʃɚ/",

    # --- Philosophy, History & Literature ---
    "Nietzsche": "/nˈiːʧə/",
    "Goethe": "/ɡˈɜːtə/",
    "Camus": "/kæmˈuː/",
    "Dostoevsky": "/dˌɑːstɔɪˈɛfski/",
    "Kierkegaard": "/kˈɪɹkəɡɑːɹd/",
    "Schopenhauer": "/ʃˈoʊpənhaʊɚ/",
    "Heidegger": "/hˈaɪdɛɡɚ/",
    "Wittgenstein": "/vˈɪtɡənʃtaɪn/",
    "Foucault": "/fuːkˈoʊ/",
    "Bourdieu": "/bʊɹdjˈɜː/",
    "Derrida": "/dˌɛɹidˈɑː/",
    "Deleuze": "/dəlˈuːz/",
    "Descartes": "/deɪkˈɑːɹt/",
    "Rousseau": "/ɹuːsˈoʊ/",
    "Machiavelli": "/mˌɑːkiəvˈɛli/",
    "Spinoza": "/spɪnˈoʊzə/",
    "Confucius": "/kənfjˈuːʃəs/",
    "Laozi": "/lˈaʊdzə/",

    # --- Classical, Patristic & Biblical ---
    "Manasseh": "/mənˈæsə/",
    "Origen": "/ˈɔːɹɪʤən/",
    "Enoch": "/ˈiːnək/",
    "Enochic": "/inˈɑːkɪk/",
    "Enochian": "/inˈoʊkiən/",
    "Methuselah": "/məθˈuːzələ/",
    "Mahalalel": "/məhˈɑːləlɛl/",
    "Jared": "/ʤˈɛɹəd/",
    "Lamech": "/lˈeɪmɛk/",
    "Melchizedek": "/mɛlkˈɪzədɛk/",
    "Nebuchadnezzar": "/nˌɛbjʊkədnˈɛzɚ/",
    "Samyaza": "/ʃˌɛmihˈɑːzə/",
    "Shemihaza": "/ʃˌɛmihˈɑːzə/",
    "Semjaza": "/sɛmˈɑːzə/",
    "Azazel": "/əzˈeɪzəl/",
    "Phanuel": "/fˌænjuːˈɛl/",
    "Uriel": "/jˈʊɹiəl/",
    "Raphael": "/ɹˈæfeɪˌɛl/",
    "Baraqiel": "/bəɹˈɑːkiəl/",
    "Kokabiel": "/koʊkˈɑːbiəl/",
    "Armaros": "/ɑːɹmˈɑːɹoʊs/",
    "Asbeel": "/æsbˈiːəl/",
    "Danel": "/dɑːnˈɛl/",
    "Ezeqeel": "/ɛzˈɛkiəl/",
    "Sariel": "/sˈɛɹiəl/",
    "Remiel": "/ɹˈɛmiəl/",
    "Gadreel": "/ɡˈædɹiəl/",
    "Penemue": "/pənˈɛmjuː/",
    "Kasdeja": "/kæsdˈeɪə/",
    "Tertullian": "/tɚtˈʌliən/",
    "Eusebius": "/juːsˈiːbiəs/",
    "Irenaeus": "/ˌaɪɹənˈiːəs/",
    "Athanasius": "/ˌæθənˈeɪʃəs/",
    "Chrysostom": "/kɹˈɪsəstəm/",
    "Augustine": "/ˈɔːɡəstˌiːn/",
    "Polycarp": "/pˈɑːlikɑːɹp/",
    "Ignatius": "/ɪɡnˈeɪʃəs/",
    "Clement": "/klˈɛmənt/",
    "Marcion": "/mˈɑːɹʃiən/",
    "Diocletian": "/dˌaɪəkliːʃən/",
    "Pseudepigrapha": "/sˌuːdəpˈɪɡɹəfə/",
    "Pseudepigraphal": "/sˌuːdəpˈɪɡɹəfəl/",
    "Apocrypha": "/əpˈɑːkɹɪfə/",
    "Apocryphal": "/əpˈɑːkɹɪfəl/",
    "Septuagint": "/sˈɛptuːəʤɪnt/",
    "Qumran": "/kʊmɹˈɑːn/",
    "Ge'ez": "/ɡˈɛɛz/",
    "Geez": "/ɡˈɛɛz/",
    "Hasmonean": "/hˌæzmənˈiːən/",
    "Maccabees": "/mˈækəbiːz/",
    "Pharisees": "/fˈɛɹəsiːz/",
    "Sadducees": "/sˈæʤəsiːz/",
    "Essenes": "/ɛsˈiːnz/",
    "Zealots": "/zˈɛləts/",
    "Gnosticism": "/nˈɑːstəsɪzəm/",
    "Gnostic": "/nˈɑːstɪk/",
    "righteous": "/ˈɹaɪtʃəs/",
    "righteousness": "/ˈɹaɪtʃəsnəs/",
}


def is_ipa(value: str) -> bool:
    """Return True if value is explicitly /IPA/ delimited or contains IPA characters."""
    v = value.strip()
    if len(v) >= 2 and v.startswith("/") and v.endswith("/"):
        return True
    return any(ch in IPA_INDICATORS for ch in v)


def sanitize_ipa(ipa: str) -> str:
    """Strip slashes and filter to valid Kokoro vocabulary phonemes.
    Automatically maps Latin 'r' to English turned-r 'ɹ' to avoid harsh rolled R.
    """
    s = ipa.strip().strip("/")
    s = s.replace("r", "ɹ")
    return "".join(ch for ch in s if ch in KOKORO_VOCAB_CHARS)


def respelling_to_ipa(respelling: str) -> str:
    """Compile a human-readable respelling (e.g. 'muh-NASS-uh', 'en-jin-EKS')
    into clean Kokoro IPA without triggering espeak-ng acronym spelling.
    """
    raw = respelling.strip()
    if not raw:
        return ""
    if is_ipa(raw):
        return sanitize_ipa(raw)

    # Split into space-separated words, then hyphen-separated syllables
    word_ipas: List[str] = []
    for word in raw.split():
        syllables = [s for s in re.split(r"[-·]", word) if s]
        syl_ipas: List[str] = []
        for idx, syl in enumerate(syllables):
            letters = re.sub(r"[^a-zA-Z']", "", syl)
            if not letters:
                continue
            is_stressed = letters.isupper() and len(letters) >= 1 and (
                len(syllables) > 1 or len(letters) > 1
            )
            low = letters.lower()
            ipa_syl = _compile_syllable(low, stressed=is_stressed)
            if is_stressed:
                # Place primary stress mark before the first vowel if possible, else start
                m = re.search(r"[aeiouəɚɛɜɪʊʌɑɔæ]", ipa_syl)
                if m and m.start() > 0:
                    ipa_syl = ipa_syl[:m.start()] + "ˈ" + ipa_syl[m.start():]
                else:
                    ipa_syl = "ˈ" + ipa_syl
            elif idx == 0 and len(syllables) == 1:
                pass
            syl_ipas.append(ipa_syl)
        if syl_ipas:
            word_ipas.append("".join(syl_ipas))
    return sanitize_ipa(" ".join(word_ipas))


# Ordered digraph/trigraph rules for intuitive respelling -> IPA
_PHONETIC_RULES: List[Tuple[str, str]] = [
    ("tsh", "ʧ"),
    ("dzh", "ʤ"),
    ("eye", "aɪ"),
    ("igh", "aɪ"),
    ("ahy", "aɪ"),
    ("ye", "aɪ"),
    ("uy", "aɪ"),
    ("air", "ɛɹ"),
    ("ear", "ɪɹ"),
    ("oor", "ʊɹ"),
    ("yoo", "juː"),
    ("yur", "jʊɹ"),
    ("ahr", "ɑːɹ"),
    ("awr", "ɔːɹ"),
    ("oor", "ʊɹ"),
    ("sh", "ʃ"),
    ("zh", "ʒ"),
    ("ch", "ʧ"),
    ("th", "θ"),
    ("dh", "ð"),
    ("ng", "ŋ"),
    ("ah", "ɑː"),
    ("aw", "ɔː"),
    ("ay", "eɪ"),
    ("ee", "iː"),
    ("oo", "uː"),
    ("oh", "oʊ"),
    ("ow", "aʊ"),
    ("oy", "ɔɪ"),
    ("oi", "ɔɪ"),
    ("ur", "ɜːɹ"),
    ("er", "ɚ"),
    ("uh", "ə"),
    ("ih", "ɪ"),
    ("eh", "ɛ"),
    ("ae", "eɪ"),
    ("qu", "kw"),
    ("ks", "ks"),
]

_SINGLE_CHAR_MAP: Dict[str, str] = {
    "a": "æ",
    "b": "b",
    "c": "k",
    "d": "d",
    "e": "ɛ",
    "f": "f",
    "g": "ɡ",
    "h": "h",
    "i": "ɪ",
    "j": "ʤ",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "o": "ɑː",
    "p": "p",
    "q": "k",
    "r": "ɹ",
    "s": "s",
    "t": "t",
    "u": "ʌ",
    "v": "v",
    "w": "w",
    "x": "ks",
    "y": "j",
    "z": "z",
}


def _compile_syllable(low: str, stressed: bool) -> str:
    # Unstressed 'uh' -> schwa 'ə'; stressed 'uh' -> 'ʌ'
    out: List[str] = []
    i = 0
    n = len(low)
    while i < n:
        matched = False
        for pat, rep in _PHONETIC_RULES:
            if low.startswith(pat, i):
                if pat == "uh" and stressed:
                    out.append("ʌ")
                elif pat == "er" and stressed:
                    out.append("ɜːɹ")
                else:
                    out.append(rep)
                i += len(pat)
                matched = True
                break
        if not matched:
            ch = low[i]
            # Syllabic vowel 'y' at end of syllable or if no other vowels in syllable
            if ch == "y" and (i == n - 1 or not any(v in low for v in "aeiou")):
                out.append("aɪ")
            elif ch == "u" and not stressed:
                out.append("ə")
            else:
                out.append(_SINGLE_CHAR_MAP.get(ch, ch))
            i += 1
    out_str = "".join(out)
    # Collapse doubled English spelling consonants (e.g. 'NASS' -> 'næs')
    return re.sub(r'([bdfɡklmnpɹstvz])\1+', r'\1', out_str)


class SavedPronunciation(BaseModel):
    id: str = Field(default_factory=lambda: f"pron_{uuid.uuid4().hex[:8]}")
    word: str
    phonetic: str
    ipa: str
    book_id: Optional[str] = None
    book_title: Optional[str] = None
    created_at: float = Field(default_factory=time.time)


class LexiconManager:
    _instance: Optional["LexiconManager"] = None

    def __init__(self):
        self._default_lexicon: Dict[str, str] = dict(DEFAULT_LEXICON)
        self._saved_pronunciations: List[SavedPronunciation] = []
        self._pattern_cache: Dict[Optional[str], Optional[re.Pattern]] = {}
        self._lower_map_cache: Dict[Optional[str], Dict[str, str]] = {}
        self.load()

    @classmethod
    def get_instance(cls) -> "LexiconManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _invalidate_caches(self):
        self._pattern_cache.clear()
        self._lower_map_cache.clear()

    def _get_maps_for_book(self, book_id: Optional[str] = None) -> Tuple[Optional[re.Pattern], Dict[str, str]]:
        norm_bid = book_id.strip() if book_id and book_id.strip() not in ("", "global", "null", "undefined") else None
        cache_key = norm_bid

        if cache_key in self._pattern_cache and cache_key in self._lower_map_cache:
            return self._pattern_cache[cache_key], self._lower_map_cache[cache_key]

        lower_map: Dict[str, str] = {}
        # 1. Base DEFAULT_LEXICON
        for word, val in self._default_lexicon.items():
            lower_map[word.lower()] = respelling_to_ipa(val)

        # 2. Global saved overrides
        for p in self._saved_pronunciations:
            if not p.book_id or p.book_id in ("global", ""):
                lower_map[p.word.lower()] = p.ipa

        # 3. Book-specific saved overrides (highest priority)
        if norm_bid:
            for p in self._saved_pronunciations:
                if p.book_id == norm_bid:
                    lower_map[p.word.lower()] = p.ipa

        if lower_map:
            # Longest keys first so multi-word or longer derivatives match first
            keys = sorted(lower_map.keys(), key=len, reverse=True)
            joined = "|".join(re.escape(k) for k in keys)
            pattern = re.compile(rf"\b({joined})\b", re.IGNORECASE)
        else:
            pattern = None

        self._pattern_cache[cache_key] = pattern
        self._lower_map_cache[cache_key] = lower_map
        return pattern, lower_map

    def load(self):
        self._saved_pronunciations = []
        # 1. Load from SAVED_PRONUNCIATIONS_FILE
        if SAVED_PRONUNCIATIONS_FILE.exists():
            try:
                raw_data = json.loads(SAVED_PRONUNCIATIONS_FILE.read_text(encoding="utf-8"))
                if isinstance(raw_data, list):
                    for item in raw_data:
                        try:
                            self._saved_pronunciations.append(SavedPronunciation.model_validate(item))
                        except Exception:
                            pass
            except Exception as e:
                print(f"[Lexicon] Error loading {SAVED_PRONUNCIATIONS_FILE}: {e}")

        # 2. If no saved pronunciations yet, seed General Library overrides from data/lexicon.json
        if not self._saved_pronunciations and LEXICON_FILE.exists():
            try:
                data = json.loads(LEXICON_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for k, v in data.items():
                        ipa_val = respelling_to_ipa(v)
                        self._saved_pronunciations.append(
                            SavedPronunciation(
                                word=k,
                                phonetic=v,
                                ipa=ipa_val,
                                book_id="global",
                                book_title="General Library",
                            )
                        )
                if self._saved_pronunciations:
                    self.save()
            except Exception as e:
                print(f"[Lexicon] Error seeding from {LEXICON_FILE}: {e}")

        self._invalidate_caches()

    def save(self):
        try:
            data = [p.model_dump() for p in self._saved_pronunciations]
            SAVED_PRONUNCIATIONS_FILE.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[Lexicon] Error saving {SAVED_PRONUNCIATIONS_FILE}: {e}")

    def add_override(
        self,
        word: str,
        phonetic: str,
        book_id: Optional[str] = None,
        book_title: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> Dict:
        w = word.strip()
        p = phonetic.strip()
        if not w or not p:
            return {}

        # If scope is explicitly general or no book_id provided, treat as global
        if scope == "general" or not book_id:
            norm_bid = "global"
            b_title = "General Library"
        else:
            norm_bid = book_id.strip() if book_id.strip() not in ("", "global", "null", "undefined") else "global"
            b_title = book_title if norm_bid != "global" else "General Library"

        ipa_val = respelling_to_ipa(p)

        target = None
        for item in self._saved_pronunciations:
            item_bid = item.book_id if item.book_id not in ("", None) else "global"
            if item.word.lower() == w.lower() and item_bid == norm_bid:
                target = item
                break

        if target:
            target.word = w
            target.phonetic = p
            target.ipa = ipa_val
            if b_title:
                target.book_title = b_title
            target.created_at = time.time()
            res = target.model_dump()
        else:
            new_item = SavedPronunciation(
                word=w,
                phonetic=p,
                ipa=ipa_val,
                book_id=norm_bid,
                book_title=b_title,
                created_at=time.time(),
            )
            self._saved_pronunciations.append(new_item)
            res = new_item.model_dump()

        self._invalidate_caches()
        self.save()
        return res

    def pull_to_book(
        self,
        word: str,
        book_id: str,
        book_title: Optional[str] = None,
        phonetic: Optional[str] = None,
    ) -> Dict:
        """Pull a general override into this specific book, allowing book-level precedence."""
        w = word.strip().lower()
        general_entry = None
        for p in self._saved_pronunciations:
            if p.word.lower() == w and (not p.book_id or p.book_id in ("global", "")):
                general_entry = p
                break

        chosen_phonetic = phonetic.strip() if phonetic and phonetic.strip() else (
            general_entry.phonetic if general_entry else self._default_lexicon.get(word, word)
        )
        return self.add_override(
            word=word,
            phonetic=chosen_phonetic,
            book_id=book_id,
            book_title=book_title,
            scope="book",
        )

    def remove_override(
        self,
        word: str,
        book_id: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> int:
        w = word.strip().lower()
        norm_bid = book_id.strip() if book_id and book_id.strip() not in ("", "global", "null", "undefined") else None

        initial_count = len(self._saved_pronunciations)
        if scope == "general":
            self._saved_pronunciations = [
                p for p in self._saved_pronunciations
                if not (p.word.lower() == w and (not p.book_id or p.book_id in ("global", "")))
            ]
        elif scope == "book" and norm_bid:
            self._saved_pronunciations = [
                p for p in self._saved_pronunciations
                if not (p.word.lower() == w and p.book_id == norm_bid)
            ]
        elif norm_bid:
            self._saved_pronunciations = [
                p for p in self._saved_pronunciations
                if not (p.word.lower() == w and p.book_id == norm_bid)
            ]
        else:
            self._saved_pronunciations = [
                p for p in self._saved_pronunciations
                if p.word.lower() != w
            ]

        deleted_count = initial_count - len(self._saved_pronunciations)
        if deleted_count > 0:
            self._invalidate_caches()
            self.save()
        return deleted_count

    def get_lexicon_review(self, book_id: Optional[str] = None) -> Dict:
        """Return structured review of book-specific vs general overrides with precedence tracking."""
        norm_bid = book_id.strip() if book_id and book_id.strip() not in ("", "global", "null", "undefined") else None

        book_overrides = []
        general_overrides = []

        for p in self._saved_pronunciations:
            is_gen = not p.book_id or p.book_id in ("global", "")
            if is_gen:
                general_overrides.append(p.model_dump())
            elif norm_bid and p.book_id == norm_bid:
                book_overrides.append(p.model_dump())
            elif not norm_bid:
                book_overrides.append(p.model_dump())

        book_words = {b["word"].lower(): b for b in book_overrides}
        general_words = {g["word"].lower(): g for g in general_overrides}

        for b in book_overrides:
            b["overrides_general"] = b["word"].lower() in general_words
            if b["overrides_general"]:
                b["general_phonetic"] = general_words[b["word"].lower()]["phonetic"]
            b["is_current_book"] = True

        for g in general_overrides:
            g["overridden_by_book"] = g["word"].lower() in book_words
            if g["overridden_by_book"]:
                g["book_phonetic"] = book_words[g["word"].lower()]["phonetic"]
            g["is_current_book"] = False

        book_overrides.sort(key=lambda x: x["word"].lower())
        general_overrides.sort(key=lambda x: x["word"].lower())

        return {
            "book_id": norm_bid,
            "book_overrides": book_overrides,
            "general_overrides": general_overrides,
            "total_book": len(book_overrides),
            "total_general": len(general_overrides),
            "items": book_overrides + general_overrides,
        }

    def get_saved_overrides(self, book_id: Optional[str] = None) -> List[Dict]:
        """Return user-saved pronunciations filtered by book_id."""
        review = self.get_lexicon_review(book_id)
        if book_id and book_id != "all":
            # Book overrides first, then general overrides
            return review["book_overrides"] + review["general_overrides"]
        return review["items"]

        # Sort: Current book overrides first, then global, then alphabetical by word
        results.sort(key=lambda x: (0 if x.get("is_current_book") else 1, x["word"].lower()))
        return results

    def get_all(self) -> Dict[str, str]:
        """Return combined legacy dictionary of built-in + all overrides."""
        res = dict(self._default_lexicon)
        for p in self._saved_pronunciations:
            res[p.word] = p.phonetic
        return res

    def get_ipa(self, word: str, book_id: Optional[str] = None) -> Optional[str]:
        _, lower_map = self._get_maps_for_book(book_id)
        return lower_map.get(word.lower())

    def split_with_ipa(self, text: str, book_id: Optional[str] = None) -> List[Tuple[str, bool]]:
        """Split text into [(segment, is_ipa), ...] chunks using book-aware overrides."""
        if not text:
            return []

        pattern, lower_map = self._get_maps_for_book(book_id)
        if not pattern:
            return [(text, False)]

        segments: List[Tuple[str, bool]] = []
        last_idx = 0
        for m in pattern.finditer(text):
            if m.start() > last_idx:
                segments.append((text[last_idx:m.start()], False))
            ipa = lower_map.get(m.group(0).lower())
            if ipa:
                segments.append((ipa, True))
            else:
                segments.append((m.group(0), False))
            last_idx = m.end()
        if last_idx < len(text):
            segments.append((text[last_idx:], False))
        return segments

    def apply(self, text: str, book_id: Optional[str] = None) -> str:
        """Legacy plain-text replacement (kept for compatibility/inspection)."""
        if not text:
            return ""
        pattern, lower_map = self._get_maps_for_book(book_id)
        if not pattern:
            return text
        return pattern.sub(
            lambda m: lower_map.get(m.group(0).lower(), m.group(0)), text
        )
