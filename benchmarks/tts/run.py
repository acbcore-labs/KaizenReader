#!/usr/bin/env python3
"""KaizenReader TTS Reproducible Benchmark Harness.

Measures cold load, normalization, inference, encoding, RTF, memory, and cache
performance on Apple Silicon across a deterministic test corpus.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import onnxruntime as rt
import soundfile as sf

from src.config import (
    MODEL_PATH,
    VOICES_PATH,
    ONNX_INTRA_THREADS,
    MAX_AUDIO_CACHE_BYTES,
    DEFAULT_VOICE,
    DEFAULT_SPEED,
    DEFAULT_LANG,
    _FP16_MODEL,
    _FP32_MODEL,
)
from src.tts.engine import TTSEngine
from src.tts.normalizer import normalize_text_for_tts


def get_rss_bytes() -> int:
    """Return max RSS in bytes (macOS returns bytes)."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def get_system_metadata() -> Dict[str, Any]:
    """Capture hardware, OS, and runtime metadata."""
    chip = "Unknown"
    mem_size = "Unknown"
    try:
        chip = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
    except Exception:
        chip = platform.processor()
    try:
        mem_bytes = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip())
        mem_size = f"{mem_bytes / (1024**3):.1f} GB"
    except Exception:
        pass

    return {
        "machine": platform.machine(),
        "processor": chip,
        "unified_memory": mem_size,
        "system": platform.system(),
        "os_version": platform.mac_ver()[0] if hasattr(platform, "mac_ver") else platform.version(),
        "python_version": platform.python_version(),
        "python_arch": platform.architecture()[0],
        "onnxruntime_version": rt.__version__,
        "ort_available_providers": rt.get_available_providers(),
        "active_model": MODEL_PATH.name,
        "model_fp16": _FP16_MODEL.exists(),
        "threads": ONNX_INTRA_THREADS,
        "cache_budget_bytes": MAX_AUDIO_CACHE_BYTES,
    }


def load_corpus(corpus_path: Path, quick: bool = False, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    items = []
    with open(corpus_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    if quick:
        return items[:5]
    if limit:
        return items[:limit]
    return items


def run_benchmarks(
    corpus_path: Path,
    quick: bool = False,
    limit: Optional[int] = None,
    runs: int = 1,
    output_path: Optional[Path] = None,
) -> Dict[str, Any]:
    print("=" * 70)
    print(" KaizenReader M1 TTS Benchmark Suite")
    print("=" * 70)

    metadata = get_system_metadata()
    print(f"Hardware:    {metadata['processor']} ({metadata['unified_memory']})")
    print(f"OS:          macOS {metadata['os_version']} | Python {metadata['python_version']} ({metadata['python_arch']})")
    print(f"Engine:      ONNX Runtime {metadata['onnxruntime_version']} (threads={metadata['threads']})")
    print(f"Model:       {metadata['active_model']} (FP16={metadata['model_fp16']})")
    print(f"Cache Limit: {metadata['cache_budget_bytes'] / (1024*1024):.0f} MiB")
    print("-" * 70)

    # 1. Cold Load Measurement
    print("\n[Phase 1] Measuring cold load...")
    t_cold_start = time.perf_counter()
    engine = TTSEngine()
    cold_load_sec = time.perf_counter() - t_cold_start
    rss_after_load = get_rss_bytes()
    print(f"  Cold initialization: {cold_load_sec:.4f}s | RSS: {rss_after_load / (1024*1024):.1f} MiB")

    corpus = load_corpus(corpus_path, quick=quick, limit=limit)
    print(f"\n[Phase 2] Executing corpus ({len(corpus)} items, runs={runs})...\n")

    results: List[Dict[str, Any]] = []
    uncached_latencies: List[float] = []
    uncached_rtfs: List[float] = []
    total_audio_sec = 0.0
    total_infer_sec = 0.0
    cache_hits = 0
    cache_misses = 0

    header_fmt = "{:<16} {:<10} {:>8} {:>9} {:>9} {:>8} {:>7}"
    row_fmt = "{:<16} {:<10} {:>8.3f}s {:>8.4f}s {:>8.4f}s {:>8.4f} {:>6.2f}x"
    print(header_fmt.format("ID", "Category", "AudioDur", "NormTime", "InferTime", "RTF", "RealTime"))
    print("-" * 74)

    for item in corpus:
        item_id = item["id"]
        category = item.get("category", "general")
        text = item["text"]
        voice = item.get("voice", DEFAULT_VOICE)
        speed = float(item.get("speed", DEFAULT_SPEED))
        node_type = item.get("node_type", "p")

        # Skip code blocks under smart audio mode if designated
        if node_type == "code" and item.get("category") == "suppression":
            results.append({
                "id": item_id,
                "category": category,
                "skipped": True,
                "reason": "code_block_suppression",
            })
            print(f"{item_id:<16} {category:<10} (SKIPPED: code block suppression)")
            continue

        resolved_lang = engine._voice_lang(voice)

        # Measurement boundaries:
        # Stage 1: Normalization & Phonemization
        t_norm_0 = time.perf_counter()
        phonemes, _ = engine.build_phonemes(text, lang=resolved_lang)
        t_norm = time.perf_counter() - t_norm_0

        model_speed = max(0.5, min(2.0, float(speed)))
        cache_key = engine._make_cache_key(phonemes, voice, model_speed, node_type)

        is_cached = False
        with engine._cache_lock:
            if cache_key in engine._cache:
                is_cached = True

        if is_cached:
            cache_hits += 1
            t_cache_0 = time.perf_counter()
            wav_bytes, dur, sr, timings = engine.synthesize(
                text, voice=voice, speed=speed, node_type=node_type, is_preempt=False
            )
            t_hit = time.perf_counter() - t_cache_0
            results.append({
                "id": item_id,
                "category": category,
                "cached": True,
                "audio_duration_sec": dur,
                "cache_hit_latency_sec": t_hit,
                "timings_count": len(timings),
            })
            print(f"{item_id:<16} {category:<10} {dur:>8.3f}s (CACHE HIT in {t_hit*1000:>6.2f}ms)")
            continue

        cache_misses += 1
        sent_pause, clause_pause = engine._prosody_pauses(node_type)

        # Stage 2: Direct Model Inference
        t_infer_0 = time.perf_counter()
        with engine._infer_lock:
            samples, sample_rate, raw_timings = engine.kokoro.create_timed(
                phonemes,
                voice=voice,
                speed=model_speed,
                lang=resolved_lang,
                is_phonemes=True,
                sentence_pause=sent_pause,
                clause_pause=clause_pause,
            )
        t_infer = time.perf_counter() - t_infer_0

        # Stage 3: Encoding & Alignment
        t_enc_0 = time.perf_counter()
        dur = float(len(samples)) / float(sample_rate)
        timings = engine._align_timings_to_words(text, raw_timings, dur)
        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format="WAV", subtype="PCM_16")
        wav_bytes = buf.getvalue()
        t_enc = time.perf_counter() - t_enc_0

        engine._cache_put(cache_key, (wav_bytes, dur, sample_rate, timings))

        e2e_latency = t_norm + t_infer + t_enc
        rtf = e2e_latency / dur if dur > 0 else 0.0
        times_real_time = (1.0 / rtf) if rtf > 0 else 0.0

        uncached_latencies.append(e2e_latency)
        uncached_rtfs.append(rtf)
        total_audio_sec += dur
        total_infer_sec += t_infer

        results.append({
            "id": item_id,
            "category": category,
            "cached": False,
            "audio_duration_sec": round(dur, 4),
            "norm_time_sec": round(t_norm, 5),
            "infer_time_sec": round(t_infer, 5),
            "encode_time_sec": round(t_enc, 5),
            "e2e_latency_sec": round(e2e_latency, 5),
            "rtf": round(rtf, 4),
            "times_real_time": round(times_real_time, 2),
            "timings_count": len(timings),
            "timing_quality": "estimated_proportional",
            "sample_rate": sample_rate,
            "wav_bytes": len(wav_bytes),
        })

        print(row_fmt.format(item_id, category, dur, t_norm, t_infer, rtf, times_real_time))

    # Phase 3: Seek Responsiveness Simulation
    print("\n[Phase 3] Measuring seek preemption latency...")
    engine.clear_cache()
    # Queue 4 lookahead items in background
    lookahead_items = [
        ("Speculative background sentence number one being synthesized ahead.", DEFAULT_VOICE, 1.0, "p"),
        ("Speculative background sentence number two queued in priority ring.", DEFAULT_VOICE, 1.0, "p"),
        ("Speculative background sentence number three awaiting processor slot.", DEFAULT_VOICE, 1.0, "p"),
        ("Speculative background sentence number four completing lookahead block.", DEFAULT_VOICE, 1.0, "p"),
    ]
    engine.queue_lookahead(lookahead_items)
    # Brief sleep to let lookahead thread acquire work
    time.sleep(0.05)

    seek_target = "Emergency foreground user click jumped straight to this new sentence."
    t_seek_0 = time.perf_counter()
    seek_wav, seek_dur, seek_sr, seek_timings = engine.synthesize(seek_target, is_preempt=True)
    seek_latency = time.perf_counter() - t_seek_0
    print(f"  Foreground seek latency under active lookahead: {seek_latency:.4f}s (Audio dur: {seek_dur:.2f}s)")

    # Aggregates
    p50_latency = float(np.percentile(uncached_latencies, 50)) if uncached_latencies else 0.0
    p95_latency = float(np.percentile(uncached_latencies, 95)) if uncached_latencies else 0.0
    mean_rtf = float(np.mean(uncached_rtfs)) if uncached_rtfs else 0.0
    overall_rtf = total_infer_sec / total_audio_sec if total_audio_sec > 0 else 0.0
    overall_x_rt = (1.0 / overall_rtf) if overall_rtf > 0 else 0.0
    final_rss = get_rss_bytes()

    summary = {
        "metadata": metadata,
        "cold_load_sec": round(cold_load_sec, 4),
        "total_uncached_items": len(uncached_latencies),
        "total_audio_sec": round(total_audio_sec, 3),
        "total_infer_sec": round(total_infer_sec, 3),
        "overall_rtf": round(overall_rtf, 4),
        "overall_times_real_time": round(overall_x_rt, 2),
        "mean_e2e_rtf": round(mean_rtf, 4),
        "latency_p50_sec": round(p50_latency, 4),
        "latency_p95_sec": round(p95_latency, 4),
        "seek_latency_under_lookahead_sec": round(seek_latency, 4),
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "rss_init_mib": round(rss_after_load / (1024 * 1024), 2),
        "rss_final_mib": round(final_rss / (1024 * 1024), 2),
        "results": results,
    }

    print("\n" + "=" * 70)
    print(" Benchmark Summary")
    print("=" * 70)
    print(f"  Cold Load Time:         {cold_load_sec:.4f} s")
    print(f"  Uncached Sentences:     {len(uncached_latencies)}")
    print(f"  Total Audio Generated:  {total_audio_sec:.2f} s")
    print(f"  Overall RTF (Inference):{overall_rtf:.4f} ({overall_x_rt:.2f}x real-time)")
    print(f"  Latency p50:            {p50_latency:.4f} s")
    print(f"  Latency p95:            {p95_latency:.4f} s")
    print(f"  Seek Latency (lookahead):{seek_latency:.4f} s")
    print(f"  Cache Hits / Misses:    {cache_hits} / {cache_misses}")
    print(f"  Process Max RSS:        {final_rss / (1024*1024):.1f} MiB")
    print("=" * 70 + "\n")

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"Saved machine-readable benchmark results to {output_path}")

    return summary


def main():
    parser = argparse.ArgumentParser(description="KaizenReader TTS Baseline & Benchmark Harness")
    parser.add_argument("--corpus", type=Path, default=PROJECT_ROOT / "benchmarks" / "tts" / "corpus.jsonl")
    parser.add_argument("--quick", action="store_true", help="Run initial 5 items to validate instrumentation")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of corpus items")
    parser.add_argument("--runs", type=int, default=1, help="Repetitions per item")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "benchmarks" / "tts" / "results_baseline_onnx.json")
    args = parser.parse_args()

    run_benchmarks(
        corpus_path=args.corpus,
        quick=args.quick,
        limit=args.limit,
        runs=args.runs,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
