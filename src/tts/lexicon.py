"""Pronunciation Lexicon & Phonetic Override Engine.

Provides phonetic respellings for ancient, biblical, classical, and literary names
that standard TTS models stumble on (e.g. Manasseh, Origen, Tertullian, Watchers of Enoch).
Persists custom user overrides in data/lexicon.json.
"""
from pathlib import Path
import json
import re
from typing import Dict

from src.config import DATA_DIR

LEXICON_FILE = DATA_DIR / "lexicon.json"

# Core built-in literary, biblical, patristic, and classical pronunciation overrides
DEFAULT_LEXICON = {
    # Biblical & Enochic figures
    "Manasseh": "muh-NASS-uh",
    "Origen": "OR-ih-jen",
    "Enoch": "EE-nuk",
    "Enochic": "ee-NAH-kik",
    "Methuselah": "muh-THOO-zuh-luh",
    "Mahalalel": "muh-HAH-luh-lel",
    "Jared": "JAIR-ed",
    "Lamech": "LAY-mek",
    "Melchizedek": "mel-KIZZ-uh-dek",
    "Nebuchadnezzar": "neb-uh-kud-NEZ-er",
    "Samyaza": "shem-ee-HAH-zuh",
    "Shemihaza": "shem-ee-HAH-zuh",
    "Azazel": "uh-ZAY-zul",
    "Phanuel": "fan-yoo-EL",
    "Uriel": "YUR-ee-ul",
    "Raphael": "RAF-eye-el",
    "Baraqiel": "buh-RAH-kee-el",
    "Kokabiel": "koh-KAH-bee-el",
    "Armaros": "ar-MAH-rohs",
    "Asbeel": "as-BEE-el",
    "Danel": "dah-NEL",
    "Ezeqeel": "eh-ZEH-kee-el",

    # Church Fathers & Patristic Writers
    "Tertullian": "ter-TULL-ee-un",
    "Eusebius": "yoo-SEE-bee-us",
    "Irenaeus": "eye-ruh-NEE-us",
    "Athanasius": "ath-uh-NAY-shus",
    "Chrysostom": "KRISS-us-tum",
    "Augustine": "AW-gus-teen",
    "Polycarp": "PAH-lee-karp",
    "Ignatius": "ig-NAY-shus",
    "Clement": "KLEM-unt",
    "Marcion": "MAR-she-on",
    "Diocletian": "dye-uh-KLEE-shun",

    # Ancient Languages & Texts
    "Pseudepigrapha": "soo-duh-PIG-ruh-fuh",
    "Pseudepigraphal": "soo-duh-PIG-ruh-ful",
    "Apocrypha": "uh-PAHK-ruh-fuh",
    "Apocryphal": "uh-PAHK-ruh-ful",
    "Septuagint": "SEP-too-uh-jint",
    "Qumran": "koom-RAHN",
    "Ge'ez": "GEH-ez",
    "Geez": "GEH-ez",
    "Hasmonean": "haz-muh-NEE-un",
    "Maccabees": "MAK-uh-beez",
    "Pharisees": "FAIR-uh-seez",
    "Sadducees": "SAD-yoo-seez",
    "Essenes": "EH-seenz",
    "Zealots": "ZELL-uts",
    "Gnosticism": "NAH-stuh-siz-um",
    "Gnostic": "NAH-stik",

    # Philosophers & Authors
    "Nietzsche": "NEE-chuh",
    "Goethe": "GUR-tuh",
    "Camus": "kah-MOO",
    "Dostoevsky": "dahs-tuh-YEV-skee",
    "Kierkegaard": "KEER-kuh-gard",
    "Schopenhauer": "SHOH-pun-how-er",
    "Heidegger": "HY-deg-er",
    "Wittgenstein": "VIT-gun-shtine",
    "Foucault": "foo-KOH",
    "Bourdieu": "boor-DYUH",
    "Derrida": "deh-ree-DAH",
    "Deleuze": "duh-LUZ"
}

class LexiconManager:
    _instance = None

    def __init__(self):
        self.lexicon: Dict[str, str] = dict(DEFAULT_LEXICON)
        self.load()

    @classmethod
    def get_instance(cls) -> "LexiconManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load(self):
        if LEXICON_FILE.exists():
            try:
                data = json.loads(LEXICON_FILE.read_text(encoding="utf-8"))
                self.lexicon.update(data)
            except Exception as e:
                print(f"[Lexicon] Error loading {LEXICON_FILE}: {e}")
        else:
            self.save()

    def save(self):
        try:
            LEXICON_FILE.write_text(json.dumps(self.lexicon, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[Lexicon] Error saving {LEXICON_FILE}: {e}")

    def add_override(self, word: str, phonetic: str):
        self.lexicon[word.strip()] = phonetic.strip()
        self.save()

    def remove_override(self, word: str):
        if word in self.lexicon:
            del self.lexicon[word]
            self.save()

    def get_all(self) -> Dict[str, str]:
        return dict(self.lexicon)

    def apply(self, text: str) -> str:
        """Replace occurrences of words with their phonetic respellings."""
        if not text:
            return ""

        for word, phonetic in self.lexicon.items():
            # Match whole word, case-insensitive or exact
            pattern = re.compile(rf'\b{re.escape(word)}\b', re.IGNORECASE)
            text = pattern.sub(phonetic, text)

        return text
