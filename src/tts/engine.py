"""Mechanical Sympathy Kokoro TTS Engine.

Runs directly on Apple Silicon M1 via ONNX Runtime (using CoreML or Accelerate NEON).
Features zero-disk I/O in-memory streaming, audio cache, and background lookahead.
"""
import io
import time
import hashlib
import threading
from typing import Dict, List, Optional, Tuple
from collections import OrderedDict

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

from src.config import MODEL_PATH, VOICES_PATH, DEFAULT_VOICE, DEFAULT_SPEED, DEFAULT_LANG
from src.tts.normalizer import normalize_text_for_tts

class TTSEngine:
    _instance: Optional["TTSEngine"] = None
    _lock = threading.Lock()

    def __init__(self, model_path: str = str(MODEL_PATH), voices_path: str = str(VOICES_PATH)):
        self.model_path = model_path
        self.voices_path = voices_path
        self.kokoro: Optional[Kokoro] = None
        self._init_lock = threading.Lock()
        
        # In-memory LRU cache for synthesized sentence WAV bytes (zero disk I/O)
        self._cache: OrderedDict[str, Tuple[bytes, float, int]] = OrderedDict()
        self._cache_capacity = 300  # ~30-50MB of uncompressed audio in memory
        self._cache_lock = threading.Lock()

        # Lookahead synthesis queue
        self._lookahead_thread: Optional[threading.Thread] = None
        self._lookahead_queue: List[Tuple[str, str, float]] = []
        self._lookahead_lock = threading.Lock()
        self._stop_lookahead = False

        self._ensure_loaded()

    @classmethod
    def get_instance(cls) -> "TTSEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _ensure_loaded(self):
        with self._init_lock:
            if self.kokoro is None:
                t0 = time.perf_counter()
                self.kokoro = Kokoro(self.model_path, self.voices_path)
                load_time = time.perf_counter() - t0
                print(f"[TTSEngine] Kokoro loaded in {load_time:.2f}s on Apple Silicon M1.")

    def get_available_voices(self) -> List[Dict[str, str]]:
        """Return structured voice list with clean display names and accents."""
        self._ensure_loaded()
        assert self.kokoro is not None
        raw_voices = sorted(self.kokoro.get_voices())
        
        voice_meta = []
        for v in raw_voices:
            # Voice prefixes: af = American Female, am = American Male, bf = British Female, bm = British Male
            category = "Other"
            gender = "Neutral"
            accent = "General"
            
            if v.startswith("af_"):
                category = "American Female"
                gender = "Female"
                accent = "American"
            elif v.startswith("am_"):
                category = "American Male"
                gender = "Male"
                accent = "American"
            elif v.startswith("bf_"):
                category = "British Female"
                gender = "Female"
                accent = "British"
            elif v.startswith("bm_"):
                category = "British Male"
                gender = "Male"
                accent = "British"
            elif v.startswith("ef_") or v.startswith("em_"):
                category = "Spanish"
                accent = "Spanish"
            elif v.startswith("ff_"):
                category = "French"
                accent = "French"
            elif v.startswith("if_") or v.startswith("im_"):
                category = "Italian"
                accent = "Italian"
            elif v.startswith("jf_") or v.startswith("jm_"):
                category = "Japanese"
                accent = "Japanese"
            elif v.startswith("zf_") or v.startswith("zm_"):
                category = "Mandarin"
                accent = "Mandarin"

            name_part = v.split("_", 1)[1].capitalize() if "_" in v else v
            display_name = f"{name_part} ({category})"
            
            voice_meta.append({
                "id": v,
                "name": display_name,
                "category": category,
                "gender": gender,
                "accent": accent,
            })
        return voice_meta

    def _make_cache_key(self, text: str, voice: str, speed: float) -> str:
        h = hashlib.sha256()
        h.update(f"{voice}:{speed:.2f}:{text}".encode("utf-8"))
        return h.hexdigest()

    def synthesize(
        self,
        text: str,
        voice: str = DEFAULT_VOICE,
        speed: float = DEFAULT_SPEED,
        lang: str = DEFAULT_LANG
    ) -> Tuple[bytes, float, int]:
        """Synthesize text to in-memory WAV audio bytes, duration in seconds, and sample rate."""
        if not text or not text.strip():
            # Return silent WAV
            return self._create_silent_wav(0.1)

        norm_text = normalize_text_for_tts(text)
        if not norm_text:
            return self._create_silent_wav(0.1)

        cache_key = self._make_cache_key(norm_text, voice, speed)
        
        # Check cache
        with self._cache_lock:
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)
                return self._cache[cache_key]

        self._ensure_loaded()
        assert self.kokoro is not None

        with self._init_lock:
            try:
                samples, sample_rate = self.kokoro.create(
                    norm_text,
                    voice=voice,
                    speed=speed,
                    lang=lang
                )
            except Exception as e:
                print(f"[TTSEngine] Error synthesizing '{norm_text[:30]}...': {e}")
                # Fallback to silent buffer
                return self._create_silent_wav(0.2)

        duration = float(len(samples)) / float(sample_rate)
        
        # In-memory WAV encoding
        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format="WAV", subtype="PCM_16")
        wav_bytes = buf.getvalue()

        # Update cache
        with self._cache_lock:
            self._cache[cache_key] = (wav_bytes, duration, sample_rate)
            if len(self._cache) > self._cache_capacity:
                self._cache.popitem(last=False)

        return wav_bytes, duration, sample_rate

    def _create_silent_wav(self, duration: float = 0.1, sample_rate: int = 24000) -> Tuple[bytes, float, int]:
        samples = np.zeros(int(sample_rate * duration), dtype=np.float32)
        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format="WAV", subtype="PCM_16")
        return buf.getvalue(), duration, sample_rate

    def queue_lookahead(self, items: List[Tuple[str, str, float]]):
        """Queue sentences to synthesize ahead in a background thread."""
        with self._lookahead_lock:
            self._lookahead_queue = list(items)
            if self._lookahead_thread is None or not self._lookahead_thread.is_alive():
                self._stop_lookahead = False
                self._lookahead_thread = threading.Thread(target=self._run_lookahead, daemon=True)
                self._lookahead_thread.start()

    def clear_lookahead(self):
        with self._lookahead_lock:
            self._lookahead_queue.clear()
            self._stop_lookahead = True

    def _run_lookahead(self):
        while True:
            item = None
            with self._lookahead_lock:
                if self._stop_lookahead or not self._lookahead_queue:
                    break
                item = self._lookahead_queue.pop(0)

            if item:
                text, voice, speed = item
                norm_text = normalize_text_for_tts(text)
                cache_key = self._make_cache_key(norm_text, voice, speed)
                
                # Only synthesize if not already in cache
                already_cached = False
                with self._cache_lock:
                    already_cached = cache_key in self._cache
                
                if not already_cached:
                    try:
                        self.synthesize(text, voice, speed)
                    except Exception:
                        pass
            
            # Cooperative yield to prevent thermal buildup
            time.sleep(0.01)
