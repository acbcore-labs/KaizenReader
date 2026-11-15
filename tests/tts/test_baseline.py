"""Baseline verification tests for Kokoro ONNX speech runtime."""
import io
import pytest
import soundfile as sf

from src.config import MODEL_PATH, VOICES_PATH, _FP16_MODEL
from src.tts.engine import TTSEngine


def test_baseline_artifact_paths():
    """Verify production FP16 ONNX model and voices binary are present."""
    assert MODEL_PATH.exists(), f"Model path {MODEL_PATH} does not exist"
    assert VOICES_PATH.exists(), f"Voices path {VOICES_PATH} does not exist"
    if _FP16_MODEL.exists():
        assert MODEL_PATH == _FP16_MODEL, "FP16 model must be preferred when present"


def test_baseline_engine_startup():
    """Verify engine initializes cleanly on CPUExecutionProvider."""
    engine = TTSEngine.get_instance()
    assert engine is not None
    assert engine.kokoro is not None
    voices = engine.get_available_voices()
    assert len(voices) > 0
    voice_ids = [v["id"] for v in voices]
    assert "af_bella" in voice_ids


def test_baseline_synthesis():
    """Verify speech synthesis outputs valid PCM WAV and timings."""
    engine = TTSEngine.get_instance()
    text = "Hello world."
    wav_bytes, duration, sample_rate, word_timings = engine.synthesize(text)

    assert len(wav_bytes) > 0
    assert duration > 0.0
    assert sample_rate == 24000

    # Parse WAV bytes with soundfile to verify headers
    buf = io.BytesIO(wav_bytes)
    data, sr = sf.read(buf)
    assert sr == 24000
    assert len(data) > 0

    # Verify timing structure
    assert isinstance(word_timings, list)
    assert len(word_timings) == 2  # "Hello", "world."
    for t in word_timings:
        assert "i" in t and "w" in t and "s" in t and "e" in t
        assert t["s"] <= t["e"]


def test_baseline_empty_or_whitespace_text():
    """Verify empty text produces silent fallback rather than crashing."""
    engine = TTSEngine.get_instance()
    wav_bytes, duration, sample_rate, word_timings = engine.synthesize("   ")
    assert len(wav_bytes) > 0
    assert duration > 0.0
    assert word_timings == []
