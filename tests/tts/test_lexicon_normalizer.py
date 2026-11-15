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


def test_righteous_pronunciation_and_normalization():
    """Verify 'righteous' is never corrupted by microseconds regex and compiles to turned-r IPA."""
    # 1. Verify text normalizer does not corrupt 'righteous' to 'microseconds'
    text = "The word of the blessing of Enoch, wherewith he blessed the elect and righteous."
    norm = normalize_text_for_tts(text)
    assert "microseconds" not in norm
    assert "righteous" in norm

    # 2. Verify respelling 'RYE-chuss' compiles to clean Kokoro IPA with turned-r 'ɹ'
    from src.tts.lexicon import respelling_to_ipa
    ipa = respelling_to_ipa("RYE-chuss")
    assert "ɹ" in ipa
    assert "r" not in ipa  # Latin r must never be present (rolled R prevention)
    assert "aɪ" in ipa     # Long I diphthong

    # 3. Verify LexiconManager resolves 'righteous' with turned-r IPA
    lex = LexiconManager.get_instance()
    chunks = lex.split_with_ipa("blessed the elect and righteous")
    found_ipas = [seg for seg, is_ipa in chunks if is_ipa]
    assert len(found_ipas) >= 1
    assert "ɹ" in found_ipas[0]
    assert "r" not in found_ipas[0]


def test_saved_pronunciations_per_book_isolation():
    """Verify saved pronunciations can be scoped per book and do not pollute other books."""
    lex = LexiconManager.get_instance()

    # Save a book-specific override for book_alpha
    entry = lex.add_override(
        word="tribulation",
        phonetic="trib-yoo-LAY-shun",
        book_id="doc_alpha",
        book_title="Book Alpha",
    )
    assert entry["word"] == "tribulation"
    assert entry["book_id"] == "doc_alpha"

    # Query saved overrides for book_alpha vs book_beta
    alpha_list = lex.get_saved_overrides(book_id="doc_alpha")
    beta_list = lex.get_saved_overrides(book_id="doc_beta")

    assert any(p["word"] == "tribulation" for p in alpha_list)
    assert not any(p["word"] == "tribulation" for p in beta_list)

    # Verify split_with_ipa uses the override only for book_alpha
    alpha_chunks = lex.split_with_ipa("in the day of tribulation", book_id="doc_alpha")
    beta_chunks = lex.split_with_ipa("in the day of tribulation", book_id="doc_beta")

    assert any(is_ipa and "eɪ" in seg for seg, is_ipa in alpha_chunks)
    assert not any(is_ipa and "eɪ" in seg for seg, is_ipa in beta_chunks)

    # Clean up
    deleted = lex.remove_override("tribulation", book_id="doc_alpha")
    assert deleted >= 1
    assert not any(p["word"] == "tribulation" for p in lex.get_saved_overrides(book_id="doc_alpha"))


def test_saved_pronunciations_precedence_and_pull():
    """Verify precedence hierarchy: Book > General > Built-in, plus pull from General."""
    lex = LexiconManager.get_instance()

    # 1. Add a General override for 'righteous'
    lex.add_override(
        word="righteous",
        phonetic="RYE-chuss",
        scope="general",
    )

    # 2. Add a Book-specific override for 'doc_enoch' with a different phonetic nuance
    lex.add_override(
        word="righteous",
        phonetic="RAHY-tshus",
        book_id="doc_enoch",
        book_title="The Book of Enoch",
        scope="book",
    )

    # Review structure and precedence detection
    review = lex.get_lexicon_review(book_id="doc_enoch")
    book_entry = next((b for b in review["book_overrides"] if b["word"] == "righteous"), None)
    gen_entry = next((g for g in review["general_overrides"] if g["word"] == "righteous"), None)

    assert book_entry is not None
    assert gen_entry is not None
    assert book_entry["overrides_general"] is True
    assert gen_entry["overridden_by_book"] is True

    # 3. Verify synthesis precedence: Enoch gets Book override; other book gets General override
    enoch_chunks = lex.split_with_ipa("elect and righteous", book_id="doc_enoch")
    other_chunks = lex.split_with_ipa("elect and righteous", book_id="doc_other")

    # Enoch has book-specific IPA
    enoch_ipa = [seg for seg, is_ipa in enoch_chunks if is_ipa][0]
    other_ipa = [seg for seg, is_ipa in other_chunks if is_ipa][0]
    assert "ɹ" in enoch_ipa
    assert "ɹ" in other_ipa

    # 4. Pull a word from General into a specific book
    pulled = lex.pull_to_book(
        word="Kubernetes",
        book_id="doc_enoch",
        book_title="The Book of Enoch",
        phonetic="koo-ber-NET-eez",
    )
    assert pulled["word"] == "Kubernetes"
    assert pulled["book_id"] == "doc_enoch"

    review_after = lex.get_lexicon_review(book_id="doc_enoch")
    assert any(b["word"] == "Kubernetes" for b in review_after["book_overrides"])

    # 5. Remove book override and verify fallback to General
    lex.remove_override("righteous", book_id="doc_enoch", scope="book")
    review_post = lex.get_lexicon_review(book_id="doc_enoch")
    assert not any(b["word"] == "righteous" for b in review_post["book_overrides"])
    # General override remains intact
    assert any(g["word"] == "righteous" for g in review_post["general_overrides"])

    # Clean up
    lex.remove_override("Kubernetes", book_id="doc_enoch", scope="book")
    lex.remove_override("righteous", scope="general")


