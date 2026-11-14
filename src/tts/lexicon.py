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
from typing import Dict, List, Tuple

from src.config import DATA_DIR

LEXICON_FILE = DATA_DIR / "lexicon.json"

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
}


def is_ipa(value: str) -> bool:
    """Return True if value is explicitly /IPA/ delimited or contains IPA characters."""
    v = value.strip()
    if len(v) >= 2 and v.startswith("/") and v.endswith("/"):
        return True
    return any(ch in IPA_INDICATORS for ch in v)


def sanitize_ipa(ipa: str) -> str:
    """Strip slashes and filter to valid Kokoro vocabulary phonemes."""
    s = ipa.strip().strip("/")
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
            if ch == "u" and not stressed:
                out.append("ə")
            else:
                out.append(_SINGLE_CHAR_MAP.get(ch, ch))
            i += 1
    out_str = "".join(out)
    # Collapse doubled English spelling consonants (e.g. 'NASS' -> 'næs')
    return re.sub(r'([bdfɡklmnpɹstvz])\1+', r'\1', out_str)


class LexiconManager:
    _instance = None

    def __init__(self):
        self.lexicon: Dict[str, str] = dict(DEFAULT_LEXICON)
        self._compiled_cache: Dict[str, str] = {}
        self._pattern: re.Pattern | None = None
        self.load()

    @classmethod
    def get_instance(cls) -> "LexiconManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _rebuild_index(self):
        self._compiled_cache = {}
        self._lower_map: Dict[str, str] = {}
        for word, val in self.lexicon.items():
            ipa = respelling_to_ipa(val)
            self._compiled_cache[word] = ipa
            self._lower_map[word.lower()] = ipa

        if self.lexicon:
            # Longest keys first so multi-word or longer derivatives match first
            keys = sorted(self.lexicon.keys(), key=len, reverse=True)
            joined = "|".join(re.escape(k) for k in keys)
            self._pattern = re.compile(rf"\b({joined})\b", re.IGNORECASE)
        else:
            self._pattern = None

    def load(self):
        if LEXICON_FILE.exists():
            try:
                data = json.loads(LEXICON_FILE.read_text(encoding="utf-8"))
                # Merge user overrides; prefer DEFAULT_LEXICON IPA over legacy
                # all-caps respellings for built-in words while keeping user custom words
                for k, v in data.items():
                    if k in DEFAULT_LEXICON and not is_ipa(v):
                        # Upgrade legacy respelling for built-in key to verified IPA
                        continue
                    self.lexicon[k] = v
            except Exception as e:
                print(f"[Lexicon] Error loading {LEXICON_FILE}: {e}")
        self._rebuild_index()
        self.save()

    def save(self):
        try:
            LEXICON_FILE.write_text(
                json.dumps(self.lexicon, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[Lexicon] Error saving {LEXICON_FILE}: {e}")

    def add_override(self, word: str, phonetic: str):
        w = word.strip()
        p = phonetic.strip()
        if not w or not p:
            return
        self.lexicon[w] = p
        self._rebuild_index()
        self.save()

    def remove_override(self, word: str):
        if word in self.lexicon:
            del self.lexicon[word]
            self._rebuild_index()
            self.save()

    def get_all(self) -> Dict[str, str]:
        return dict(self.lexicon)

    def get_ipa(self, word: str) -> str | None:
        return self._lower_map.get(word.lower())

    def split_with_ipa(self, text: str) -> List[Tuple[str, bool]]:
        """Split text into [(segment, is_ipa), ...] chunks.

        Non-lexicon segments stay as plain English text for espeak-ng, while
        lexicon-matched terms become exact IPA phoneme strings.
        """
        if not text or not self._pattern:
            return [(text, False)] if text else []

        segments: List[Tuple[str, bool]] = []
        last_idx = 0
        for m in self._pattern.finditer(text):
            if m.start() > last_idx:
                segments.append((text[last_idx:m.start()], False))
            ipa = self._lower_map.get(m.group(0).lower())
            if ipa:
                segments.append((ipa, True))
            else:
                segments.append((m.group(0), False))
            last_idx = m.end()
        if last_idx < len(text):
            segments.append((text[last_idx:], False))
        return segments

    def apply(self, text: str) -> str:
        """Legacy plain-text replacement (kept for compatibility/inspection)."""
        if not text or not self._pattern:
            return text or ""
        return self._pattern.sub(
            lambda m: self._lower_map.get(m.group(0).lower(), m.group(0)), text
        )
