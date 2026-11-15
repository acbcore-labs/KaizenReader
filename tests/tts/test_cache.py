"""Unit tests for TTS in-memory caching and eviction mechanics."""
import pytest
from src.tts.engine import TTSEngine


def test_cache_hit_returns_identical_audio():
    """Verify synthesis of identical text hits the cache and returns exact audio bytes."""
    engine = TTSEngine.get_instance()
    engine.clear_cache()

    text = "Deterministic sentence for cache testing."
    wav1, dur1, sr1, timings1 = engine.synthesize(text)
    assert len(wav1) > 0

    # Second call should be served from memory cache
    wav2, dur2, sr2, timings2 = engine.synthesize(text)
    assert wav1 == wav2
    assert dur1 == dur2
    assert sr1 == sr2
    assert timings1 == timings2


def test_cache_key_differentiation():
    """Verify changing voice, speed, or prosody results in different cache entries."""
    engine = TTSEngine.get_instance()
    engine.clear_cache()

    text = "Testing cache key parameter sensitivity."
    wav1, _, _, _ = engine.synthesize(text, voice="af_bella", speed=1.0)
    wav2, _, _, _ = engine.synthesize(text, voice="af_bella", speed=1.2)
    # Different speeds produce different audio lengths/bytes
    assert wav1 != wav2


def test_cache_clear():
    """Verify clear_cache empties storage."""
    engine = TTSEngine.get_instance()
    engine.synthesize("Cache purge test sentence.")
    assert engine._cache_bytes > 0
    engine.clear_cache()
    assert len(engine._cache) == 0
    assert engine._cache_bytes == 0
