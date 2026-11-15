"""Apple Neural & System TTS Engine Bridge (`AVSpeechSynthesizer` / `say` + W3C SSML/IPA).

Provides a native Apple Silicon speech synthesis path alongside Kokoro-82M:
1. Enumerates installed macOS voices (`say -v '?'`) and ranks Neural/Premium/Enhanced voices.
2. Applies KaizenReader's semantic normalizer (`normalize_text_for_tts`) and `LexiconManager`
   overrides—preserving natural surface words for Apple's G2P while injecting W3C SSML
   `<phoneme alphabet="ipa">` tags (and substituting custom user respellings when provided).
3. Synthesizes 24 kHz mono PCM WAV audio in-memory (using macOS `/usr/bin/say` + `soundfile`)
   and computes word-level timing spans for 60fps karaoke spotlighting and `.m4a` chapter sprites.
"""
from __future__ import annotations

import hashlib
import io
import re
import subprocess
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape as xml_escape

import numpy as np
import soundfile as sf

from src.config import DEFAULT_SPEED, MAX_AUDIO_CACHE_BYTES
from src.tts.lexicon import DEFAULT_LEXICON, LexiconManager, is_ipa, sanitize_ipa
from src.tts.normalizer import normalize_text_for_tts

_INLINE_IPA_RE = re.compile(r"/([^/\s]+)/")

PREFERRED_APPLE_VOICES = [
    "Ava",
    "Samantha",
    "Allison",
    "Alex",
    "Evan",
    "Nathan",
    "Zoe",
    "Nicky",
    "Daniel",
    "Oliver",
    "Serena",
    "Karen",
    "Moira",
    "Rishi",
    "Tessa",
]


def ipa_to_readable_hint(ipa: str) -> str:
    """Convert IPA string into a natural phonetic respelling fallback for non-SSML voices."""
    s = ipa.strip("/")
    replacements = [
        ("ʃ", "sh"),
        ("ʒ", "zh"),
        ("ʧ", "ch"),
        ("ʤ", "j"),
        ("θ", "th"),
        ("ð", "th"),
        ("ŋ", "ng"),
        ("ɑːɹ", "ahr"),
        ("ɔːɹ", "or"),
        ("ɜːɹ", "ur"),
        ("ɑː", "ah"),
        ("ɔː", "aw"),
        ("iː", "ee"),
        ("uː", "oo"),
        ("eɪ", "ay"),
        ("aɪ", "eye"),
        ("ɔɪ", "oy"),
        ("oʊ", "oh"),
        ("aʊ", "ow"),
        ("ɛ", "eh"),
        ("ɪ", "ih"),
        ("æ", "a"),
        ("ʌ", "uh"),
        ("ə", "uh"),
        ("ɚ", "er"),
        ("ɹ", "r"),
        ("ɡ", "g"),
        ("ˈ", ""),
        ("ˌ", ""),
        ("ː", ""),
    ]
    for k, v in replacements:
        s = s.replace(k, v)
    return re.sub(r"[^a-zA-Z\s'-]", "", s).strip() or ipa.strip("/")


def build_apple_speech_payload(raw_text: str) -> Tuple[str, str]:
    """Build both `(spoken_normalized_text, ssml_document)` with Lexicon IPA overrides injected.

    - Preserves natural surface spellings in `spoken_text` for built-in words (`DEFAULT_LEXICON`)
      so Apple's transformer G2P pronounces `"Manasseh"`, `"Chrysostom"`, and `"First Enoch"`
      naturally, while substituting user-defined custom respellings (e.g. `muh-NASS-uh`).
    - Emits full W3C SSML `<phoneme alphabet="ipa" ph="...">word</phoneme>` in `ssml_text`.
    """
    norm_text = normalize_text_for_tts(raw_text)
    if not norm_text:
        return "", "<speak></speak>"

    # Replace inline homograph /IPA/ markers with readable surface words for plain `say`
    homograph_surface_map = {
        "ɹˈɛd": "red",
        "lˈaɪv": "live",
        "lˈɛd": "led",
        "wˈaɪnd": "wind",
        "maɪnjˈuːt": "my-newt",
        "ɹˈɛzəmeɪ": "rez-oo-may",
    }

    lex = LexiconManager.get_instance()
    raw_lex = lex.get_all()

    spoken_parts: List[str] = []
    ssml_parts: List[str] = ["<speak>"]

    def _process_plain_segment(segment_str: str):
        if not segment_str:
            return
        if not lex._pattern:
            spoken_parts.append(segment_str)
            ssml_parts.append(xml_escape(segment_str))
            return

        last_idx = 0
        for m in lex._pattern.finditer(segment_str):
            if m.start() > last_idx:
                chunk = segment_str[last_idx:m.start()]
                spoken_parts.append(chunk)
                ssml_parts.append(xml_escape(chunk))

            matched_word = m.group(0)
            ipa_val = lex.get_ipa(matched_word)
            user_raw = raw_lex.get(matched_word) or raw_lex.get(matched_word.lower())
            # If user entered a custom respelling (not built-in IPA), use the readable respelling
            if user_raw and matched_word not in DEFAULT_LEXICON and not is_ipa(user_raw):
                spoken_surface = user_raw.replace("-", " ").replace("·", " ").lower()
            else:
                spoken_surface = matched_word

            spoken_parts.append(spoken_surface)
            if ipa_val:
                safe_ph = xml_escape(ipa_val, {'"': "&quot;"})
                ssml_parts.append(
                    f'<phoneme alphabet="ipa" ph="{safe_ph}">{xml_escape(matched_word)}</phoneme>'
                )
            else:
                ssml_parts.append(xml_escape(matched_word))
            last_idx = m.end()

        if last_idx < len(segment_str):
            tail = segment_str[last_idx:]
            spoken_parts.append(tail)
            ssml_parts.append(xml_escape(tail))

    last = 0
    for m in _INLINE_IPA_RE.finditer(norm_text):
        if m.start() > last:
            _process_plain_segment(norm_text[last:m.start()])
        ipa = sanitize_ipa(m.group(1))
        surf = homograph_surface_map.get(ipa, ipa_to_readable_hint(ipa))
        spoken_parts.append(surf)
        safe_ph = xml_escape(ipa, {'"': "&quot;"})
        ssml_parts.append(f'<phoneme alphabet="ipa" ph="{safe_ph}">{xml_escape(surf)}</phoneme>')
        last = m.end()

    if last < len(norm_text):
        _process_plain_segment(norm_text[last:])

    ssml_parts.append("</speak>")
    spoken_out = re.sub(r"\s+", " ", "".join(spoken_parts)).strip()
    ssml_out = "".join(ssml_parts)
    return spoken_out, ssml_out


class AppleTTSEngine:
    """macOS Apple Neural & System Voice Synthesizer with LRU cache and word timing estimation."""

    _instance: Optional["AppleTTSEngine"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._voices_cache: Optional[List[Dict[str, str]]] = None
        self._cache: OrderedDict[str, Tuple[bytes, float, int, List[Dict[str, float | str]]]] = OrderedDict()
        self._cache_bytes = 0
        self._cache_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "AppleTTSEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def get_available_voices(self) -> List[Dict[str, str]]:
        """Discover installed macOS voices via `/usr/bin/say -v ?` and format for UI."""
        if self._voices_cache is not None:
            return self._voices_cache

        voices: List[Dict[str, str]] = []
        try:
            proc = subprocess.run(
                ["/usr/bin/say", "-v", "?"],
                capture_output=True,
                text=True,
                timeout=4.0,
                check=False,
            )
            line_re = re.compile(r"^(.+?)\s+([a-z]{2}_[A-Z]{2}|[a-z]{2}-[A-Z]{2})\s+#\s*(.*)$")
            for raw_line in proc.stdout.splitlines():
                m = line_re.match(raw_line.strip())
                if not m:
                    continue
                v_name = m.group(1).strip()
                locale = m.group(2).strip().replace("_", "-")
                if not locale.startswith("en-"):
                    continue
                is_preferred = any(v_name.startswith(p) for p in PREFERRED_APPLE_VOICES)
                tier = "Apple Neural / Enhanced" if ("Premium" in v_name or "Enhanced" in v_name or is_preferred) else "Apple System"
                accent = "British" if "GB" in locale else ("Australian" if "AU" in locale else ("Irish" if "IE" in locale else "American"))
                voices.append(
                    {
                        "id": f"apple:{v_name}",
                        "raw_name": v_name,
                        "name": f" {v_name} ({accent} · {tier})",
                        "category": f"Apple Neural & System ({accent})",
                        "locale": locale,
                        "engine": "apple",
                        "priority": "0" if is_preferred else "1",
                    }
                )
        except Exception:
            pass

        if not voices:
            voices.append(
                {
                    "id": "apple:Samantha",
                    "raw_name": "Samantha",
                    "name": " Samantha (American · Apple Neural)",
                    "category": "Apple Neural & System (American)",
                    "locale": "en-US",
                    "engine": "apple",
                    "priority": "0",
                }
            )

        voices.sort(key=lambda v: (v["priority"], v["name"]))
        self._voices_cache = voices
        return voices

    def _resolve_voice_name(self, voice_id: str) -> str:
        clean = voice_id.replace("apple:", "").strip()
        avail = self.get_available_voices()
        exact = [v["raw_name"] for v in avail if v["raw_name"].lower() == clean.lower()]
        if exact:
            return exact[0]
        return avail[0]["raw_name"] if avail else "Samantha"

    def synthesize(
        self,
        text: str,
        voice: str = "apple:Samantha",
        speed: float = DEFAULT_SPEED,
        node_type: str = "p",
    ) -> Tuple[bytes, float, int, List[Dict[str, float | str]]]:
        """Synthesize sentence via macOS Apple speech engine into 24 kHz mono WAV + word timings."""
        spoken_text, _ = build_apple_speech_payload(text)
        if not spoken_text:
            return self._silent_wav(0.12)

        resolved_voice = self._resolve_voice_name(voice)
        clamped_speed = max(0.5, min(2.5, float(speed)))
        wpm = int(round(178 * clamped_speed))

        cache_key = hashlib.sha256(
            f"apple:{resolved_voice}:{wpm}:{node_type}:{spoken_text}".encode("utf-8")
        ).hexdigest()

        with self._cache_lock:
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)
                return self._cache[cache_key]

        target_sr = 24000
        samples = np.zeros(0, dtype=np.float32)
        with tempfile.TemporaryDirectory(prefix="kaizen_apple_tts_") as tmpdir:
            out_wav = Path(tmpdir) / "utt.wav"
            cmd = [
                "/usr/bin/say",
                "-v",
                resolved_voice,
                "-r",
                str(wpm),
                "-o",
                str(out_wav),
                "--data-format=LEI16@24000",
                spoken_text,
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=15.0)
                read_samples, sr = sf.read(str(out_wav), dtype="float32")
                if read_samples.ndim > 1:
                    read_samples = read_samples.mean(axis=1)
                samples = read_samples
                target_sr = int(sr)
            except Exception:
                samples = np.zeros(0, dtype=np.float32)

        # If macOS `say` returned 0 samples (e.g. headless/sandboxed environment without
        # com.apple.speech.synthesis Mach IPC or undownloaded voice pack), seamlessly
        # synthesize using the matched Kokoro-82M voice on the normalized Apple payload.
        if len(samples) < 240:
            from src.tts.engine import TTSEngine

            kokoro_voice = "bm_daniel" if resolved_voice in ("Daniel", "Oliver") else (
                "am_michael" if resolved_voice in ("Alex", "Evan", "Nathan", "Fred", "Albert") else "af_bella"
            )
            wav_bytes, total_duration, target_sr, word_timings = TTSEngine.get_instance().synthesize(
                text,
                voice=kokoro_voice,
                speed=clamped_speed,
                node_type=node_type,
                is_preempt=False,
            )
            self._cache_put(cache_key, (wav_bytes, total_duration, target_sr, word_timings))
            return wav_bytes, total_duration, target_sr, word_timings

        pause_sec = 0.36 if node_type in ("h1", "h2", "h3", "h4") else (0.28 if node_type == "blockquote" else 0.18)
        speech_dur = float(len(samples)) / float(target_sr)
        pad_samples = np.zeros(int(target_sr * pause_sec), dtype=np.float32)
        full_samples = np.concatenate([samples, pad_samples])
        total_duration = float(len(full_samples)) / float(target_sr)

        word_timings = self._estimate_word_timings(text, speech_dur, total_duration)

        buf = io.BytesIO()
        sf.write(buf, full_samples, target_sr, format="WAV", subtype="PCM_16")
        wav_bytes = buf.getvalue()

        self._cache_put(cache_key, (wav_bytes, total_duration, target_sr, word_timings))
        return wav_bytes, total_duration, target_sr, word_timings

    def _estimate_word_timings(
        self, raw_text: str, speech_duration: float, total_duration: float
    ) -> List[Dict[str, float | str]]:
        words = raw_text.split()
        if not words or speech_duration <= 0.02:
            return []

        weights: List[float] = []
        for w in words:
            base = max(1.5, float(len(w.strip(".,!?;:\"'()[]"))))
            if w.endswith((",", ";", ":", "—")):
                base += 2.2
            elif w.endswith((".", "!", "?")):
                base += 3.0
            weights.append(base)

        total_w = sum(weights) or 1.0
        effective_span = max(0.05, min(speech_duration, total_duration - 0.05))
        cursor = 0.0
        timings: List[Dict[str, float | str]] = []
        for idx, (w, wt) in enumerate(zip(words, weights)):
            span = (wt / total_w) * effective_span
            start_t = cursor
            end_t = min(total_duration, cursor + max(0.04, span))
            timings.append(
                {
                    "i": idx,
                    "w": w,
                    "s": round(start_t, 3),
                    "e": round(end_t, 3),
                }
            )
            cursor += span
        return timings

    def _cache_put(self, key: str, value: Tuple[bytes, float, int, List[Dict[str, float | str]]]):
        item_bytes = len(value[0])
        with self._cache_lock:
            if key in self._cache:
                self._cache_bytes -= len(self._cache[key][0])
                del self._cache[key]
            self._cache[key] = value
            self._cache_bytes += item_bytes
            while self._cache_bytes > (MAX_AUDIO_CACHE_BYTES // 2) and len(self._cache) > 1:
                _, evicted = self._cache.popitem(last=False)
                self._cache_bytes -= len(evicted[0])

    def _silent_wav(
        self, duration: float = 0.12, sample_rate: int = 24000
    ) -> Tuple[bytes, float, int, List[Dict[str, float | str]]]:
        samples = np.zeros(int(sample_rate * duration), dtype=np.float32)
        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format="WAV", subtype="PCM_16")
        return buf.getvalue(), duration, sample_rate, []
