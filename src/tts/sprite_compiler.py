"""Chapter Audio Sprite Compiler & `.kzn` Sovereign Cartridge Engine.

Compiles an entire book chapter into:
1. `ch_{idx:03d}.m4a` (hardware-decoded AAC-LC @ 48 kbps via macOS `/usr/bin/afconvert`,
   achieving an 8.0x size reduction over raw 24 kHz PCM WAV while preserving vocal clarity).
2. `ch_{idx:03d}.timings.json` (sentence spans, compact `[word_idx, start, end]` tuples for
   O(log N) binary-search word spotlighting, and 120-bin RMS acoustic energy envelope for
   the 60fps Acoustic Cadence Ribbon).
3. `<BookTitle>_<book_id>.kzn` Sovereign Cartridge ZIP archives for zero-network AirDrop /
   USB-C / iOS Files app transfer.
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import soundfile as sf

from src.config import CACHE_DIR, DEFAULT_SPEED, DEFAULT_VOICE
from src.parsers.base import Chapter, Document
from src.tts.apple_engine import AppleTTSEngine
from src.tts.engine import TTSEngine
from src.tts.lexicon import LexiconManager

SPRITE_CACHE_DIR = CACHE_DIR / "sprites"
SPRITE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_COMPILE_LOCKS_GUARD = threading.Lock()
_COMPILE_LOCKS: Dict[str, threading.Lock] = {}


def _get_compile_lock(prefix: str) -> threading.Lock:
    with _COMPILE_LOCKS_GUARD:
        lock = _COMPILE_LOCKS.get(prefix)
        if lock is None:
            lock = threading.Lock()
            _COMPILE_LOCKS[prefix] = lock
        return lock


def _sprite_cache_prefix(book_id: str, chapter_index: int, voice: str, speed: float) -> str:
    lex_items = sorted(LexiconManager.get_instance().get_all().items())
    lex_hash = hashlib.sha256(json.dumps(lex_items, ensure_ascii=False).encode("utf-8")).hexdigest()[:8]
    safe_voice = voice.replace(":", "_").replace(" ", "_")
    return f"{book_id}_ch{chapter_index:03d}_{safe_voice}_s{speed:.2f}_{lex_hash}"


def get_cached_sprite_paths(
    book_id: str, chapter_index: int, voice: str = DEFAULT_VOICE, speed: float = DEFAULT_SPEED
) -> Tuple[Path, Path]:
    """Return (audio_path, timings_path) in SPRITE_CACHE_DIR."""
    prefix = _sprite_cache_prefix(book_id, chapter_index, voice, speed)
    m4a_path = SPRITE_CACHE_DIR / f"{prefix}.m4a"
    wav_fallback_path = SPRITE_CACHE_DIR / f"{prefix}.wav"
    timings_path = SPRITE_CACHE_DIR / f"{prefix}.timings.json"
    if m4a_path.exists():
        return m4a_path, timings_path
    if wav_fallback_path.exists():
        return wav_fallback_path, timings_path
    return m4a_path, timings_path


def get_book_packed_chapters(
    doc: Document, voice: str = DEFAULT_VOICE, speed: float = DEFAULT_SPEED
) -> List[Dict[str, int | float | str | bool]]:
    """Inspect SPRITE_CACHE_DIR and return packing telemetry for each chapter in `doc`."""
    status_list: List[Dict[str, int | float | str | bool]] = []
    for ch in doc.chapters:
        audio_p, timings_p = get_cached_sprite_paths(doc.id, ch.index, voice, speed)
        is_packed = audio_p.exists() and timings_p.exists()
        size_bytes = audio_p.stat().st_size if is_packed else 0
        status_list.append(
            {
                "chapter_index": ch.index,
                "title": ch.title,
                "packed": is_packed,
                "size_bytes": size_bytes,
                "format": audio_p.suffix.lstrip(".") if is_packed else "m4a",
            }
        )
    return status_list


def _compute_rms_envelope(samples: np.ndarray, num_bins: int = 120) -> List[float]:
    """Compute a normalized [0.08..1.0] RMS energy profile for the 60fps Acoustic Cadence Ribbon."""
    if len(samples) == 0:
        return [0.15] * num_bins
    chunk_size = max(1, len(samples) // num_bins)
    rms_vals: List[float] = []
    for i in range(num_bins):
        start = i * chunk_size
        end = min(len(samples), start + chunk_size)
        if start >= len(samples):
            rms_vals.append(0.1)
            continue
        seg = samples[start:end]
        val = float(np.sqrt(np.mean(np.square(seg))))
        rms_vals.append(val)
    peak = max(rms_vals) if rms_vals else 1.0
    if peak <= 1e-6:
        return [0.15] * num_bins
    return [round(max(0.08, min(1.0, v / peak)), 3) for v in rms_vals]


def compile_chapter_sprite(
    doc: Document,
    chapter_index: int,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
    progress_cb: Optional[Callable[[int, int, float], None]] = None,
    force_rebuild: bool = False,
) -> Tuple[Path, Path, Dict]:
    """Synthesize and stitch all sentences in a chapter into a compressed `.m4a` sprite + timings JSON."""
    if chapter_index < 0 or chapter_index >= len(doc.chapters):
        raise ValueError(f"Invalid chapter_index {chapter_index} for book {doc.id}")

    prefix = _sprite_cache_prefix(doc.id, chapter_index, voice, speed)
    with _get_compile_lock(prefix):
        return _compile_chapter_sprite_locked(
            doc=doc,
            chapter_index=chapter_index,
            voice=voice,
            speed=speed,
            progress_cb=progress_cb,
            force_rebuild=force_rebuild,
        )


def _compile_chapter_sprite_locked(
    doc: Document,
    chapter_index: int,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
    progress_cb: Optional[Callable[[int, int, float], None]] = None,
    force_rebuild: bool = False,
) -> Tuple[Path, Path, Dict]:
    audio_path, timings_path = get_cached_sprite_paths(doc.id, chapter_index, voice, speed)
    if not force_rebuild and audio_path.exists() and timings_path.exists():
        timings_data = json.loads(timings_path.read_text(encoding="utf-8"))
        return audio_path, timings_path, timings_data
    print(f"[SpriteCompiler] Compiling {doc.id} ch_{chapter_index:03d} ({voice} @ {speed}x)...")

    chapter: Chapter = doc.chapters[chapter_index]
    is_apple = voice.startswith("apple:")
    kokoro_engine = None if is_apple else TTSEngine.get_instance()
    apple_engine = AppleTTSEngine.get_instance() if is_apple else None

    # Gather all sentences in chapter order with their paragraph metadata
    flat_sentences = []
    s_counter = 0
    for p_idx, p in enumerate(chapter.paragraphs):
        for s in p.sentences:
            flat_sentences.append(
                {
                    "sidx": s_counter,
                    "id": s.id,
                    "text": s.text,
                    "skip_tts": bool(s.skip_tts or p.is_code),
                    "node_type": p.node_type or "p",
                    "is_heading": bool(p.is_heading),
                    "is_quote": bool(p.is_quote),
                    "paragraph_id": p.id,
                    "paragraph_index": p_idx,
                }
            )
            s_counter += 1

    total_sents = len(flat_sentences)
    pcm_chunks: List[np.ndarray] = []
    sample_rate = 24000
    cursor_sec = 0.0
    sentence_timings: List[Dict] = []
    structural_markers: List[Dict] = []
    seen_paragraphs = set()

    t0 = time.perf_counter()

    for idx, item in enumerate(flat_sentences):
        s_text = item["text"].strip()
        if item["skip_tts"] or not s_text:
            # Record a minimal 0.15s silent slot so sentence index alignment stays 1:1
            pad_dur = 0.15
            pad_pcm = np.zeros(int(sample_rate * pad_dur), dtype=np.float32)
            pcm_chunks.append(pad_pcm)
            sentence_timings.append(
                {
                    "sidx": item["sidx"],
                    "id": item["id"],
                    "start": round(cursor_sec, 3),
                    "end": round(cursor_sec + pad_dur, 3),
                    "node_type": item["node_type"],
                    "words": [],
                }
            )
            cursor_sec += pad_dur
            continue

        if is_apple:
            assert apple_engine is not None
            wav_bytes, dur, sr, w_timings = apple_engine.synthesize(
                s_text, voice=voice, speed=speed, node_type=item["node_type"]
            )
        else:
            assert kokoro_engine is not None
            wav_bytes, dur, sr, w_timings = kokoro_engine.synthesize(
                s_text,
                voice=voice,
                speed=min(2.0, float(speed)),
                node_type=item["node_type"],
                is_preempt=False,
            )

        sample_rate = int(sr)
        samples, _ = sf.read(io.BytesIO(wav_bytes), dtype="float32")
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        actual_dur = float(len(samples)) / float(sample_rate)
        pcm_chunks.append(samples)

        # Record structural marker on first sentence of headings or blockquotes
        if item["paragraph_id"] not in seen_paragraphs:
            seen_paragraphs.add(item["paragraph_id"])
            if item["is_heading"] or item["is_quote"] or item["sidx"] == 0:
                structural_markers.append(
                    {
                        "sidx": item["sidx"],
                        "time": round(cursor_sec, 3),
                        "kind": "heading" if item["is_heading"] else ("quote" if item["is_quote"] else "paragraph"),
                        "node_type": item["node_type"],
                        "label": s_text[:48],
                    }
                )

        # Offset word timings to chapter-relative seconds in compact [w_idx, start, end] format
        compact_words: List[List[float | int]] = []
        for wt in w_timings:
            w_idx = int(wt.get("i", 0))
            w_s = round(cursor_sec + float(wt.get("s", 0.0)), 3)
            w_e = round(cursor_sec + float(wt.get("e", 0.0)), 3)
            compact_words.append([w_idx, w_s, w_e])

        sentence_timings.append(
            {
                "sidx": item["sidx"],
                "id": item["id"],
                "start": round(cursor_sec, 3),
                "end": round(cursor_sec + actual_dur, 3),
                "node_type": item["node_type"],
                "words": compact_words,
            }
        )
        cursor_sec += actual_dur

        if progress_cb is not None:
            elapsed = max(0.001, time.perf_counter() - t0)
            rtf_x = cursor_sec / elapsed
            progress_cb(idx + 1, total_sents, rtf_x)

    if pcm_chunks:
        full_pcm = np.concatenate(pcm_chunks)
    else:
        full_pcm = np.zeros(int(sample_rate * 0.25), dtype=np.float32)

    total_duration = float(len(full_pcm)) / float(sample_rate)
    rms_envelope = _compute_rms_envelope(full_pcm, num_bins=120)

    prefix = _sprite_cache_prefix(doc.id, chapter_index, voice, speed)
    final_m4a_path = SPRITE_CACHE_DIR / f"{prefix}.m4a"
    final_wav_path = SPRITE_CACHE_DIR / f"{prefix}.wav"
    final_timings_path = SPRITE_CACHE_DIR / f"{prefix}.timings.json"

    # Encode via macOS native AudioToolbox `/usr/bin/afconvert` into AAC-LC .m4a (48 kbps)
    encoded_path = final_m4a_path
    with tempfile.TemporaryDirectory(prefix="kaizen_sprite_") as tmpdir:
        raw_wav = Path(tmpdir) / "chapter_raw.wav"
        tmp_m4a = Path(tmpdir) / "chapter_out.m4a"
        sf.write(str(raw_wav), full_pcm, sample_rate, format="WAV", subtype="PCM_16")

        afconvert_bin = Path("/usr/bin/afconvert")
        if afconvert_bin.exists():
            try:
                subprocess.run(
                    [
                        str(afconvert_bin),
                        "-f",
                        "m4af",
                        "-d",
                        "aac",
                        "-b",
                        "48000",
                        str(raw_wav),
                        str(tmp_m4a),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=60.0,
                )
                shutil.move(str(tmp_m4a), str(final_m4a_path))
                encoded_path = final_m4a_path
            except Exception:
                shutil.move(str(raw_wav), str(final_wav_path))
                encoded_path = final_wav_path
        else:
            shutil.move(str(raw_wav), str(final_wav_path))
            encoded_path = final_wav_path

    compile_elapsed = max(0.001, time.perf_counter() - t0)
    timings_payload = {
        "version": "1.0",
        "book_id": doc.id,
        "book_title": doc.title,
        "chapter_index": chapter_index,
        "chapter_title": chapter.title,
        "engine": "apple_neural" if is_apple else "kokoro_fp16",
        "voice": voice,
        "speed": speed,
        "sample_rate": sample_rate,
        "audio_format": encoded_path.suffix.lstrip("."),
        "audio_byte_size": encoded_path.stat().st_size,
        "total_duration": round(total_duration, 3),
        "compile_seconds": round(compile_elapsed, 3),
        "realtime_factor_x": round(total_duration / compile_elapsed, 2),
        "rms_envelope": rms_envelope,
        "structural_markers": structural_markers,
        "sentences": sentence_timings,
    }

    final_timings_path.write_text(
        json.dumps(timings_payload, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    return encoded_path, final_timings_path, timings_payload


def export_kzn_cartridge(
    doc: Document,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
    chapters_to_pack: Optional[List[int]] = None,
    compile_missing: bool = False,
    state_bookmark: Optional[Dict] = None,
    notes: Optional[List[Dict]] = None,
) -> bytes:
    """Package a `Document` AST, lexicon overrides, and chapter sprites into a `.kzn` ZIP cartridge."""
    buf = io.BytesIO()
    lexicon_snapshot = LexiconManager.get_instance().get_all()

    packed_chapters_meta: List[Dict] = []
    target_indices = (
        chapters_to_pack if chapters_to_pack is not None else [ch.index for ch in doc.chapters]
    )

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. Full Document AST
        ast_dict = doc.model_dump()
        zf.writestr("ast.json", json.dumps(ast_dict, ensure_ascii=False))

        # 2. Lexicon snapshot & reading state bookmark
        zf.writestr("lexicon_snapshot.json", json.dumps(lexicon_snapshot, indent=2, ensure_ascii=False))
        zf.writestr(
            "state_bookmark.json",
            json.dumps(
                {
                    "book_id": doc.id,
                    "position": state_bookmark or {"chapter_index": 0, "sentence_index": 0},
                    "notes": notes or [],
                    "exported_at": time.time(),
                },
                indent=2,
            ),
        )

        # 3. Include existing (or freshly compiled) chapter sprites
        for ch_idx in target_indices:
            if ch_idx < 0 or ch_idx >= len(doc.chapters):
                continue
            audio_p, timings_p = get_cached_sprite_paths(doc.id, ch_idx, voice, speed)
            if not (audio_p.exists() and timings_p.exists()) and compile_missing:
                audio_p, timings_p, _ = compile_chapter_sprite(doc, ch_idx, voice=voice, speed=speed)

            if audio_p.exists() and timings_p.exists():
                ext = audio_p.suffix
                arc_audio = f"sprites/ch_{ch_idx:03d}{ext}"
                arc_timings = f"sprites/ch_{ch_idx:03d}.timings.json"
                zf.write(audio_p, arcname=arc_audio, compress_type=zipfile.ZIP_STORED)
                zf.write(timings_p, arcname=arc_timings, compress_type=zipfile.ZIP_DEFLATED)
                packed_chapters_meta.append(
                    {
                        "chapter_index": ch_idx,
                        "audio_file": arc_audio,
                        "timings_file": arc_timings,
                        "size_bytes": audio_p.stat().st_size,
                    }
                )

        # 4. Cartridge Manifest
        manifest = {
            "cartridge_format": "kaizen.sovereign.cartridge.v1",
            "book_id": doc.id,
            "title": doc.title,
            "author": doc.author,
            "file_format": doc.file_format,
            "chapters_count": len(doc.chapters),
            "total_words": doc.total_words,
            "total_sentences": doc.total_sentences,
            "voice": voice,
            "speed": speed,
            "packed_chapters": packed_chapters_meta,
            "created_at": time.time(),
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

    return buf.getvalue()


def import_kzn_cartridge(cartridge_bytes: bytes) -> Tuple[Document, Dict]:
    """Unpack a `.kzn` cartridge ZIP archive, restore its AST, lexicon, and sprites, and return `(Document, manifest)`."""
    with zipfile.ZipFile(io.BytesIO(cartridge_bytes), mode="r") as zf:
        names = set(zf.namelist())
        if "manifest.json" not in names or "ast.json" not in names:
            raise ValueError("Invalid .kzn cartridge: missing manifest.json or ast.json")

        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        ast_data = json.loads(zf.read("ast.json").decode("utf-8"))
        doc = Document(**ast_data)

        # Merge bundled lexicon overrides
        if "lexicon_snapshot.json" in names:
            lex_data = json.loads(zf.read("lexicon_snapshot.json").decode("utf-8"))
            lex = LexiconManager.get_instance()
            for w, ph in lex_data.items():
                if w not in lex.lexicon:
                    lex.add_override(w, ph)

        # Extract any bundled chapter sprites into SPRITE_CACHE_DIR
        voice = manifest.get("voice", DEFAULT_VOICE)
        speed = float(manifest.get("speed", DEFAULT_SPEED))
        for item in manifest.get("packed_chapters", []):
            ch_idx = int(item["chapter_index"])
            arc_audio = item.get("audio_file")
            arc_timings = item.get("timings_file")
            if arc_audio in names and arc_timings in names:
                prefix = _sprite_cache_prefix(doc.id, ch_idx, voice, speed)
                ext = Path(arc_audio).suffix or ".m4a"
                dest_audio = SPRITE_CACHE_DIR / f"{prefix}{ext}"
                dest_timings = SPRITE_CACHE_DIR / f"{prefix}.timings.json"
                dest_audio.write_bytes(zf.read(arc_audio))
                dest_timings.write_bytes(zf.read(arc_timings))

        return doc, manifest
