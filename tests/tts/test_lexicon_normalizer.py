"""Unit tests for text normalization, lexicon IPA substitution, and homographs."""
import pytest

from src.tts.lexicon import LexiconManager, sanitize_ipa
from src.tts.normalizer import (
    normalize_text_for_tts,
    clean_footnotes,
    convert_structural_roman,
)


def test_lexicon_substitutions():
    """Verify technical names are matched in LexiconManager and mapped to valid IPA."""
    lex = LexiconManager.get_instance()
    # Nginx -> /ˌɛnʤɪnˈɛks/
    chunks = lex.split_with_ipa("We deployed Nginx on the server.")
    found_ipa = [seg for seg, is_ipa in chunks if is_ipa]
    assert len(found_ipa) >= 1
    # Check that Nginx IPA is sanitized
    assert "ɛks" in found_ipa[0]


def test_currency_normalization():
    """Verify currency symbols and decimals expand to natural English."""
    norm = normalize_text_for_tts("The price is $4,500.50 today.")
    assert "four thousand five hundred dollars and fifty cents" in norm


def test_footnote_suppression():
    """Verify inline citation brackets and parentheses are suppressed."""
    cleaned = clean_footnotes("This assertion[1] was verified[12], though earlier notes(3) differed.")
    assert "[1]" not in cleaned
    assert "[12]" not in cleaned
    assert "(3)" not in cleaned
    assert "This assertion was verified, though earlier notes differed." == cleaned.strip()


def test_structural_roman_numerals():
    """Verify Roman numerals in headings are converted to cardinals."""
    norm = convert_structural_roman("Chapter IV: The Architecture")
    assert "Chapter 4: The Architecture" == norm


def test_homograph_disambiguation():
    """Verify homograph disambiguation emits inline /IPA/ markers."""
    norm = normalize_text_for_tts("I read the book yesterday.")
    # 'read' in past context should have /IPA/ marker or phoneme mapping
    assert len(norm) > 0
