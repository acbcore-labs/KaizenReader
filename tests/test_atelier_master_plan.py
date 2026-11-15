"""Automated End-to-End Test Suite for KaizenReader Atelier & Acoustic Chronograph Edition.

Verifies all 4 phases of `docs/MASTER_PLAN_ATELIER_IOS.md` with zero extra third-party test
dependencies:
1. Local Root CA & SAN Leaf TLS Certificate Generation (`src/certs.py`).
2. Apple Neural & System TTS Engine + W3C SSML `<phoneme alphabet="ipa">` Bridge (`src/tts/apple_engine.py`).
3. Hardware `.m4a` AAC-LC Chapter Sprite Compiler (`afconvert`) & RMS Waveform Envelope (`src/tts/sprite_compiler.py`).
4. `.kzn` Sovereign Cartridge Export & Import Round-Trip Integrity.
5. FastAPI Server Route Handlers (`/api/status`, `/api/voices`, `/api/phonetics/inspect`,
   `/api/tts/apple-sentence`, `/api/book/{id}/pack-status`, `/api/book/{id}/chapter/{ch}/timings`,
   `/api/book/{id}/cartridge`, `/api/trust-profile`) and PWA/Atelier UI static assets.
"""
from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

from src.certs import ensure_local_tls_certs, get_tls_info
from src.config import ROOT_DIR
from src.parsers.base import Chapter, Document, ParagraphNode, SentenceNode
from src.server.app import (
    _loaded_documents,
    download_book_cartridge,
    download_local_ca_cert,
    get_book_pack_status,
    get_chapter_sprite_audio,
    get_chapter_sprite_timings,
    get_status,
    inspect_word_phonetics,
    list_voices,
    synthesize_apple_sentence_direct,
)
from src.tts.apple_engine import AppleTTSEngine, build_apple_speech_payload
from src.tts.sprite_compiler import (
    compile_chapter_sprite,
    export_kzn_cartridge,
    import_kzn_cartridge,
)


def _make_test_document() -> Document:
    s0 = SentenceNode(
        id="s_0_0_0",
        text="And Azazel taught men to make swords of iron in 1 Enoch 8:1.",
        skip_tts=False,
        char_start=0,
        char_end=60,
    )
    s1 = SentenceNode(
        id="s_0_0_1",
        text="Compare Origen and Chrysostom on chapter II.",
        skip_tts=False,
        char_start=61,
        char_end=105,
    )
    p0 = ParagraphNode(
        id="p_0_0",
        text=f"{s0.text} {s1.text}",
        node_type="p",
        is_heading=False,
        is_code=False,
        is_quote=False,
        sentences=[s0, s1],
    )
    ch0 = Chapter(
        id="ch_0",
        index=0,
        title="Chapter I: The Watchers",
        category="body",
        section_type="chapter",
        chapter_number=1,
        badge_label="Ch 1",
        paragraphs=[p0],
    )
    return Document(
        id="testdoc00123",
        title="Atelier Test Book",
        author="Josh Shay",
        file_format="MD",
        is_sample=False,
        chapters=[ch0],
        total_words=18,
        total_sentences=2,
        total_body_chapters=1,
        has_toc=False,
    )


def test_local_tls_certificate_generation():
    cert_path, key_path, ca_path = ensure_local_tls_certs()
    assert cert_path.exists()
    assert key_path.exists()
    assert ca_path.exists()
    assert "BEGIN CERTIFICATE" in ca_path.read_text(encoding="utf-8")
    info = get_tls_info(8977)
    assert info["has_ca"] is True
    assert info["https_url"].startswith("https://")


def test_apple_speech_ssml_and_synthesis():
    spoken, ssml = build_apple_speech_payload(
        "Manasseh and Chrysostom read 1 Enoch 8:1."
    )
    assert "First Enoch, chapter 8, verse 1" in spoken
    assert '<phoneme alphabet="ipa"' in ssml
    assert "mənˈæsə" in ssml

    apple_eng = AppleTTSEngine.get_instance()
    voices = apple_eng.get_available_voices()
    assert len(voices) >= 1
    assert voices[0]["id"].startswith("apple:")

    wav_bytes, dur, sr, timings = apple_eng.synthesize(
        "Hello from Apple Silicon.", voice=voices[0]["id"], speed=1.2
    )
    assert len(wav_bytes) > 100
    assert dur > 0.1
    assert sr == 24000
    assert len(timings) == 4
    assert timings[0]["w"] == "Hello"


def test_chapter_sprite_compiler_and_kzn_cartridge_roundtrip():
    doc = _make_test_document()
    audio_path, timings_path, timings_data = compile_chapter_sprite(
        doc, chapter_index=0, voice="apple:Samantha", speed=1.25, force_rebuild=True
    )
    assert audio_path.exists()
    assert timings_path.exists()
    assert audio_path.suffix in (".m4a", ".wav")
    assert timings_data["book_id"] == doc.id
    assert timings_data["total_duration"] > 0.2
    assert len(timings_data["rms_envelope"]) == 120
    assert len(timings_data["sentences"]) == 2
    assert timings_data["sentences"][1]["start"] >= timings_data["sentences"][0]["end"] - 0.01

    # Export .kzn Sovereign Cartridge with packed chapter sprite
    kzn_bytes = export_kzn_cartridge(
        doc,
        voice="apple:Samantha",
        speed=1.25,
        chapters_to_pack=[0],
        compile_missing=False,
        state_bookmark={"chapter_index": 0, "sentence_index": 1},
    )
    assert len(kzn_bytes) > 500
    with zipfile.ZipFile(BytesIO(kzn_bytes), "r") as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "ast.json" in names
        assert "lexicon_snapshot.json" in names
        assert any(n.startswith("sprites/ch_000") for n in names)

    # Import .kzn cartridge and verify restored Document & manifest
    restored_doc, manifest = import_kzn_cartridge(kzn_bytes)
    assert restored_doc.id == doc.id
    assert restored_doc.title == doc.title
    assert len(manifest["packed_chapters"]) == 1


def test_fastapi_atelier_route_handlers_and_pwa_assets():
    doc = _make_test_document()
    _loaded_documents[doc.id] = doc

    # 1. Status & Voices
    status_json = get_status()
    assert status_json["version"] == "3.0.0"
    assert any(e["id"] == "apple_ios_neural" for e in status_json["engines_available"])

    voices = list_voices(include_apple=True)
    assert any(v.get("engine") == "kokoro" for v in voices)
    assert any(v.get("engine") == "apple" for v in voices)

    # 2. Inline Phonetic Lens inspection endpoint
    lens_data = inspect_word_phonetics("Manasseh", context="King Manasseh reigned.")
    assert lens_data["word"] == "Manasseh"
    assert lens_data["has_override"] is True
    assert "mənˈæsə" in lens_data["kokoro_ipa"]
    assert len(lens_data["stress_variants"]) >= 2

    # 3. Apple Neural sentence endpoint
    res_apple = synthesize_apple_sentence_direct(text="Testing Apple voice.", speed=1.2)
    assert res_apple.headers["X-Engine-Used"] == "apple_mac_neural"
    assert len(res_apple.body) > 200

    # 4. Chapter Sprite, Timings, Pack Status & Cartridge endpoints
    timings_json = get_chapter_sprite_timings(
        book_id=doc.id, ch_idx=0, voice="apple:Samantha", speed=1.25
    )
    assert timings_json["chapter_index"] == 0
    assert len(timings_json["rms_envelope"]) == 120

    pack_status = get_book_pack_status(
        book_id=doc.id, voice="apple:Samantha", speed=1.25
    )
    assert pack_status["packed_chapters_count"] == 1
    assert pack_status["total_sprite_bytes"] > 100

    sprite_resp = get_chapter_sprite_audio(
        book_id=doc.id, ch_idx=0, voice="apple:Samantha", speed=1.25
    )
    assert Path(sprite_resp.path).exists()
    assert Path(sprite_resp.path).suffix in (".m4a", ".wav")

    cart_resp = download_book_cartridge(
        book_id=doc.id,
        voice="apple:Samantha",
        speed=1.25,
        chapters="0",
        compile_missing=False,
    )
    assert cart_resp.media_type == "application/zip"
    assert len(cart_resp.body) > 500

    ca_resp = download_local_ca_cert()
    assert Path(ca_resp.path).exists()

    # 5. Verify all PWA & Atelier UI static files exist and contain required components
    ui_dir = ROOT_DIR / "src" / "ui"
    for filename in (
        "manifest.webmanifest",
        "sw.js",
        "vault.js",
        "phonetics_client.js",
        "offline_parser.js",
        "index.html",
        "styles.css",
        "app.js",
    ):
        f_path = ui_dir / filename
        assert f_path.exists() and f_path.stat().st_size > 100, f"Missing {filename}"

    html_text = (ui_dir / "index.html").read_text(encoding="utf-8")
    assert 'id="kaizen-hardware-deck"' in html_text
    assert 'id="acoustic-ribbon"' in html_text
    assert 'id="phonetic-lens-popover"' in html_text
    assert 'id="atelier-console-sheet"' in html_text
    assert 'id="pocket-curtain-overlay"' in html_text

    css_text = (ui_dir / "styles.css").read_text(encoding="utf-8")
    assert '[data-theme="oled"]' in css_text
    assert "--safe-bottom" in css_text
