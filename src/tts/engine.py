"""Mechanical Sympathy Kokoro TTS Engine.

Runs on Apple Silicon M1 via ONNX Runtime with FP16 weights, bounded arena
memory, single-pass hybrid IPA phonemization, phoneme-level word timings,
and a preemptible priority queue so user clicks never wait behind lookahead.
"""
from __future__ import annotations

import hashlib
import io
import re
import threading
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

import numpy as np
import onnxruntime as rt
import soundfile as sf
from kokoro_onnx import Kokoro

from src.config import (
    DEFAULT_LANG,
    DEFAULT_SPEED,
    DEFAULT_VOICE,
    MAX_AUDIO_CACHE_BYTES,
    MODEL_PATH,
    ONNX_INTRA_THREADS,
    VOICES_PATH,
)
from src.tts.lexicon import LexiconManager, sanitize_ipa
from src.tts.normalizer import normalize_text_for_tts

# Regex to split out inline /IPA/ markers emitted by disambiguate_homographs()
_INLINE_IPA_RE = re.compile(r"/([^/\s]+)/")


class TTSEngine:
    _instance: Optional["TTSEngine"] = None
    _lock = threading.Lock()

    def __init__(self, model_path: str = str(MODEL_PATH), voices_path: str = str(VOICES_PATH)):
        self.model_path = model_path
        self.voices_path = voices_path
        self.kokoro: Optional[Kokoro] = None
        self._init_lock = threading.Lock()
        self._infer_lock = threading.Lock()

        # Byte-bounded in-memory LRU cache: key -> (wav_bytes, duration, sample_rate, word_timings)
        self._cache: OrderedDict[str, Tuple[bytes, float, int, List[Dict[str, float | str]]]] = OrderedDict()
        self._cache_bytes = 0
        self._cache_lock = threading.Lock()

        # Preemptible lookahead queue using generation epoch
        self._lookahead_thread: Optional[threading.Thread] = None
        self._lookahead_queue: List[Tuple[str, str, float, str]] = []
        self._lookahead_lock = threading.Lock()
        self._epoch = 0

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
                opts = rt.SessionOptions()
                opts.enable_cpu_mem_arena = False
                opts.enable_mem_pattern = True
                opts.intra_op_num_threads = ONNX_INTRA_THREADS
                opts.inter_op_num_threads = 1
                opts.log_severity_level = 3
                session = rt.InferenceSession(
                    self.model_path,
                    sess_options=opts,
                    providers=["CPUExecutionProvider"],
                )
                self.kokoro = Kokoro.from_session(session, self.voices_path)
                load_time = time.perf_counter() - t0
                print(f"[TTSEngine] Kokoro ({MODEL_PATH.name}) loaded in {load_time:.2f}s.")

    def get_available_voices(self) -> List[Dict[str, str]]:
        """Return structured voice list with clean display names and accents."""
        self._ensure_loaded()
        assert self.kokoro is not None
        raw_voices = sorted(self.kokoro.get_voices())

        voice_meta = []
        for v in raw_voices:
            category = "Other"
            gender = "Neutral"
            accent = "General"

            if v.startswith("af_"):
                category, gender, accent = "American Female", "Female", "American"
            elif v.startswith("am_"):
                category, gender, accent = "American Male", "Male", "American"
            elif v.startswith("bf_"):
                category, gender, accent = "British Female", "Female", "British"
            elif v.startswith("bm_"):
                category, gender, accent = "British Male", "Male", "British"
            elif v.startswith("ef_") or v.startswith("em_"):
                category, accent = "Spanish", "Spanish"
                gender = "Female" if v.startswith("ef_") else "Male"
            elif v.startswith("ff_"):
                category, gender, accent = "French", "Female", "French"
            elif v.startswith("if_") or v.startswith("im_"):
                category, accent = "Italian", "Italian"
                gender = "Female" if v.startswith("if_") else "Male"
            elif v.startswith("jf_") or v.startswith("jm_"):
                category, accent = "Japanese", "Japanese"
                gender = "Female" if v.startswith("jf_") else "Male"
            elif v.startswith("zf_") or v.startswith("zm_"):
                category, accent = "Mandarin", "Mandarin"
                gender = "Female" if v.startswith("zf_") else "Male"
            elif v.startswith("pf_") or v.startswith("pm_"):
                category, accent = "Portuguese", "Portuguese"
                gender = "Female" if v.startswith("pf_") else "Male"
            elif v.startswith("hf_") or v.startswith("hm_"):
                category, accent = "Hindi", "Hindi"
                gender = "Female" if v.startswith("hf_") else "Male"

            name_part = v.split("_", 1)[1].capitalize() if "_" in v else v
            voice_meta.append({
                "id": v,
                "name": f"{name_part} ({category})",
                "category": category,
                "gender": gender,
                "accent": accent,
            })
        return voice_meta

    def _voice_lang(self, voice: str) -> str:
        """Infer Kokoro phonemizer language code from voice prefix."""
        if voice.startswith(("bf_", "bm_")):
            return "en-gb"
        return DEFAULT_LANG

    def build_phonemes(
        self,
        raw_text: str,
        lang: str = DEFAULT_LANG,
        book_id: Optional[str] = None,
    ) -> Tuple[str, List[Tuple[str, str]]]:
        """Single-pass normalization + hybrid IPA phonemization.

        Returns (full_phoneme_string, [(display_word, phoneme_chunk), ...])
        so we can align phoneme timings back to words without losing accuracy.
        """
        self._ensure_loaded()
        assert self.kokoro is not None

        norm_text = normalize_text_for_tts(raw_text)
        if not norm_text:
            return "", []

        lex = LexiconManager.get_instance()
        # First split on inline /IPA/ homograph markers, then on lexicon terms
        tokens_with_ipa: List[Tuple[str, bool]] = []
        last = 0
        for m in _INLINE_IPA_RE.finditer(norm_text):
            if m.start() > last:
                tokens_with_ipa.extend(lex.split_with_ipa(norm_text[last:m.start()], book_id=book_id))
            ipa = sanitize_ipa(m.group(1))
            if ipa:
                tokens_with_ipa.append((ipa, True))
            last = m.end()
        if last < len(norm_text):
            tokens_with_ipa.extend(lex.split_with_ipa(norm_text[last:], book_id=book_id))

        phoneme_parts: List[str] = []
        for seg, is_ipa_seg in tokens_with_ipa:
            if not seg:
                continue
            if is_ipa_seg:
                phoneme_parts.append(seg)
            else:
                # Preserve leading/trailing whitespace around espeak phonemization
                lead = " " if seg[0].isspace() else ""
                trail = " " if seg[-1].isspace() and len(seg) > 1 else ""
                stripped = seg.strip()
                if not stripped:
                    phoneme_parts.append(" ")
                    continue
                ph = self.kokoro.tokenizer.phonemize(stripped, lang=lang)
                if ph:
                    phoneme_parts.append(f"{lead}{ph}{trail}")
                else:
                    # Punctuation-only segment (e.g. ",", ".", "—")
                    valid_punc = "".join(c for c in stripped if c in self.kokoro.tokenizer.vocab)
                    if valid_punc:
                        phoneme_parts.append(f"{lead}{valid_punc}{trail}")

        combined = " ".join("".join(phoneme_parts).split())
        # Filter strictly to Kokoro vocab
        combined = "".join(c for c in combined if c in self.kokoro.tokenizer.vocab).strip()
        return combined, []

    def _make_cache_key(self, phonemes: str, voice: str, model_speed: float, prosody: str) -> str:
        h = hashlib.sha256()
        h.update(f"{voice}:{model_speed:.2f}:{prosody}:{phonemes}".encode("utf-8"))
        return h.hexdigest()

    def _prosody_pauses(self, node_type: str) -> Tuple[float, float]:
        """Return (sentence_pause, clause_pause) tailored to AST node type."""
        if node_type in ("h1", "h2", "h3", "h4"):
            return 0.42, 0.14
        if node_type == "blockquote":
            return 0.34, 0.13
        return 0.24, 0.10

    def synthesize(
        self,
        text: str,
        voice: str = DEFAULT_VOICE,
        speed: float = DEFAULT_SPEED,
        lang: Optional[str] = None,
        node_type: str = "p",
        is_preempt: bool = True,
        book_id: Optional[str] = None,
    ) -> Tuple[bytes, float, int, List[Dict[str, float | str]]]:
        """Synthesize text to in-memory WAV audio bytes, duration, sample rate, and word timings."""
        if is_preempt:
            self._epoch += 1  # Preempt any pending lookahead work

        if not text or not text.strip():
            wav, dur, sr = self._create_silent_wav(0.1)
            return wav, dur, sr, []

        resolved_lang = lang or self._voice_lang(voice)
        phonemes, _ = self.build_phonemes(text, lang=resolved_lang, book_id=book_id)
        if not phonemes:
            wav, dur, sr = self._create_silent_wav(0.1)
            return wav, dur, sr, []

        # Kokoro ONNX strictly requires speed in [0.5, 2.0]; clamp here,
        # and client applies any >2.0x multiplier via pitch-preserved playbackRate.
        model_speed = max(0.5, min(2.0, float(speed)))
        cache_key = self._make_cache_key(phonemes, voice, model_speed, node_type)

        with self._cache_lock:
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)
                return self._cache[cache_key]

        self._ensure_loaded()
        assert self.kokoro is not None

        sent_pause, clause_pause = self._prosody_pauses(node_type)

        with self._infer_lock:
            try:
                samples, sample_rate, raw_timings = self.kokoro.create_timed(
                    phonemes,
                    voice=voice,
                    speed=model_speed,
                    lang=resolved_lang,
                    is_phonemes=True,
                    sentence_pause=sent_pause,
                    clause_pause=clause_pause,
                )
            except Exception as e:
                print(f"[TTSEngine] Error synthesizing '{text[:40]}...': {e}")
                wav, dur, sr = self._create_silent_wav(0.2)
                return wav, dur, sr, []

        duration = float(len(samples)) / float(sample_rate)
        word_timings = self._align_timings_to_words(text, raw_timings, duration)

        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format="WAV", subtype="PCM_16")
        wav_bytes = buf.getvalue()

        self._cache_put(cache_key, (wav_bytes, duration, sample_rate, word_timings))
        return wav_bytes, duration, sample_rate, word_timings

    def _align_timings_to_words(
        self, raw_text: str, raw_timings: list, total_duration: float
    ) -> List[Dict[str, float | str]]:
        """Map Kokoro phoneme Timing objects to display word indices for smooth karaoke sync."""
        words = raw_text.split()
        if not words or not raw_timings:
            return []

        # Group phoneme timings into spoken word chunks split on space tokens
        groups: List[Tuple[float, float]] = []
        cur_start: Optional[float] = None
        cur_end: float = 0.0
        for t in raw_timings:
            if t.phoneme.isspace():
                if cur_start is not None:
                    groups.append((cur_start, cur_end))
                    cur_start = None
            else:
                if cur_start is None:
                    cur_start = float(t.start)
                cur_end = float(t.end)
        if cur_start is not None:
            groups.append((cur_start, cur_end))

        if not groups:
            return []

        # Proportionally map display words to spoken timing groups
        n_words = len(words)
        n_groups = len(groups)
        result: List[Dict[str, float | str]] = []
        for idx, w in enumerate(words):
            g_idx = min(n_groups - 1, int(idx * n_groups / n_words))
            start_t, end_t = groups[g_idx]
            result.append({
                "i": idx,
                "w": w,
                "s": round(start_t, 3),
                "e": round(min(total_duration, max(end_t, start_t + 0.04)), 3),
            })
        return result

    def _cache_put(self, key: str, value: Tuple[bytes, float, int, List[Dict[str, float | str]]]):
        item_bytes = len(value[0])
        with self._cache_lock:
            if key in self._cache:
                old_bytes = len(self._cache[key][0])
                self._cache_bytes -= old_bytes
                del self._cache[key]
            self._cache[key] = value
            self._cache_bytes += item_bytes
            while self._cache_bytes > MAX_AUDIO_CACHE_BYTES and len(self._cache) > 1:
                _, evicted = self._cache.popitem(last=False)
                self._cache_bytes -= len(evicted[0])

    def clear_cache(self):
        with self._cache_lock:
            self._cache.clear()
            self._cache_bytes = 0

    def _create_silent_wav(self, duration: float = 0.1, sample_rate: int = 24000) -> Tuple[bytes, float, int]:
        samples = np.zeros(int(sample_rate * duration), dtype=np.float32)
        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format="WAV", subtype="PCM_16")
        return buf.getvalue(), duration, sample_rate

    def queue_lookahead(self, items: List[Tuple[str, str, float, str] | Tuple[str, str, float, str, Optional[str]]]):
        """Queue upcoming sentences for background synthesis; preempted by user clicks."""
        with self._lookahead_lock:
            my_epoch = self._epoch
            self._lookahead_queue = list(items)
            if self._lookahead_thread is None or not self._lookahead_thread.is_alive():
                self._lookahead_thread = threading.Thread(
                    target=self._run_lookahead, args=(my_epoch,), daemon=True
                )
                self._lookahead_thread.start()

    def _run_lookahead(self, start_epoch: int):
        while True:
            if self._epoch != start_epoch:
                # A newer user click or seek preempted this lookahead batch
                break
            with self._lookahead_lock:
                if not self._lookahead_queue:
                    break
                item = self._lookahead_queue.pop(0)

            if len(item) == 5:
                text, voice, speed, node_type, book_id = item
            else:
                text, voice, speed, node_type = item
                book_id = None
            try:
                self.synthesize(text, voice=voice, speed=speed, node_type=node_type, is_preempt=False, book_id=book_id)
            except Exception:
                pass
            time.sleep(0.015)
