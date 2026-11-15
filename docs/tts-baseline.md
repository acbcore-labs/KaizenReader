# KaizenReader Baseline TTS Measurement Report

**Date**: 2026-11-14  
**Git Branch**: `optimize_speech_runtime`  
**Git Commit**: `7da1cd9`  
**Working Tree**: Clean  

---

## 1. System & Environment Specifications

| Parameter | Recorded Value |
|---|---|
| **Machine / SoC** | Apple M1 Pro (arm64) |
| **Unified Memory** | 16.0 GB (17,179,869,184 bytes) |
| **macOS Version** | macOS 26.6.2 (Darwin Kernel 25.6.0, Build 25G83) |
| **Python Runtime** | CPython 3.12.16 (64-bit Mach-O arm64) |
| **ONNX Runtime Version** | 1.32.0 |
| **Active Execution Provider** | `CPUExecutionProvider` |
| **Available Providers** | `CoreMLExecutionProvider`, `AzureExecutionProvider`, `CPUExecutionProvider` |
| **Active Model Artifact** | `kokoro-v1.0.fp16.onnx` (156 MB, preferred) |
| **Model SHA256** | `f3a290d384fbb27966d462905c71a46cef9e5fd00516b40df32a0b4afe77ac96` |
| **Voices Artifact** | `voices-v1.0.bin` (27 MB) |
| **Voices SHA256** | `bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d` |
| **Thread Configuration** | `intra_op_num_threads = 4`, `inter_op_num_threads = 1` |
| **Memory Settings** | `enable_cpu_mem_arena = False`, `enable_mem_pattern = True` |
| **Audio Cache Budget** | 32 MiB (`MAX_AUDIO_CACHE_BYTES = 33554432`) |
| **Lookahead Chunks** | 4 chunks (`LOOKAHEAD_CHUNKS = 4`) |

---

## 2. Reproducible Baseline Metrics

Measurements captured using `benchmarks/tts/run.py` against `benchmarks/tts/corpus.jsonl` (34 test cases across 8 functional categories):

| Metric | Measured Baseline (ONNX FP16 CPU) | Measurement Boundary |
|---|---|---|
| **Cold Model Load Time** | **0.5451 s** | From process start / session init to `Kokoro.from_session()` ready |
| **Normalization / First Call** | **0.7923 s** (cold espeak load) | First-call shared library initialization |
| **Normalization / Warm Call** | **0.0006 s – 0.0013 s** | Regex expansion & espeak-ng IPA phonemization |
| **Inference RTF (Overall)** | **0.2778** | Direct model synthesis seconds / generated audio seconds (lower is better) |
| **Times Real-Time (Overall)** | **3.60x** | `1.0 / RTF` (higher is better) |
| **Total Audio Generated** | **215.96 s** | 32 uncached test sentences |
| **Total Inference Time** | **59.99 s** | Cumulative `kokoro.create_timed` execution |
| **Latency p50 (E2E)** | **1.7379 s** | Median end-to-end time to generate a complete audio chunk |
| **Latency p95 (E2E)** | **3.9597 s** | 95th percentile latency (complex / multi-clause sentences) |
| **Seek Preemption Latency** | **3.1569 s** | Foreground user click latency while 4 lookahead sentences are queued |
| **In-Memory Cache Hit Latency** | **0.56 ms** | Retrieval from 32 MiB in-memory cache ring |
| **Process Max RSS** | **1,659.7 MiB** (~1.62 GB) | Peak resident set size during sustained narration |

---

## 3. Detailed Per-Category Breakdown

| Category | Example Audio Duration | Normalization | Inference Time | RTF | Times Real-Time |
|---|---|---|---|---|---|
| **Short (<3 words)** | 1.694 s | 0.4 ms | 0.6245 s | 0.3691 | 2.71x |
| **Medium (~15 words)** | 6.964 s | 0.8 ms | 1.9110 s | 0.2747 | 3.64x |
| **Long (~35+ words)** | 14.004 s | 1.2 ms | 3.7012 s | 0.2645 | 3.78x |
| **Continuous Narration** | 17.119 s | 1.3 ms | 4.4403 s | 0.2596 | 3.85x |
| **Headings (h1/h2 pauses)** | 3.861 s | 0.6 ms | 1.1714 s | 0.3037 | 3.29x |
| **Currency ($4,500.50)** | 8.191 s | 0.8 ms | 2.2539 s | 0.2754 | 3.63x |
| **Lexicon Terms (Nginx, K8s)** | 10.121 s | 0.7 ms | 2.6987 s | 0.2668 | 3.75x |
| **Homographs (read / tear)** | 5.152 s | 0.6 ms | 1.4748 s | 0.2865 | 3.49x |

---

## 4. Key Bottlenecks Identified

1. **Lookahead Inference Lock Contention (`seek_latency = 3.16s`)**:
   In `TTSEngine`, background lookahead runs in a background thread that holds `_infer_lock`. When a user clicks or seeks, the foreground `synthesize` call increments `_epoch`, but must block on `_infer_lock` until the active background sentence inference finishes. This creates an unacceptably high p95 seek latency (~3.16 seconds).

2. **Proportional Timing Heuristic**:
   In `_align_timings_to_words`, Kokoro's raw phoneme timings are mapped to display words by proportional index grouping:
   `g_idx = min(n_groups - 1, int(idx * n_groups / n_words))`
   When a single token expands into multiple spoken words (such as `$4,500.50` expanding to 9 words), word boundaries lose correspondence with source text character ranges.

3. **In-Flight Cancellation Absence**:
   Monolithic `kokoro.create_timed` calls cannot be interrupted mid-inference. Lookahead items must be bounded and prioritized so background speculation never delays foreground playback.

4. **Incomplete Cache Keys**:
   The existing cache key hashes only `voice:speed:prosody:phonemes`. It omits the model checksum, backend implementation, and lexicon dictionary version.
