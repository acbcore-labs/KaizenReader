# Implementation Brief: KaizenReader M1 Speech-Runtime Optimization

## Objective
Optimize `acbcore-labs/KaizenReader` for responsive, high-quality, offline document narration on Apple Silicon, starting with the M1 MacBook Pro.

Keep Kokoro-82M as the production model during this work. Introduce interchangeable execution backends, repair source-to-speech alignment and scheduling weaknesses, and select the production backend using reproducible measurements on the actual target machine.

Investigate optimized Core ML and MLX implementations, but do not assume either is faster or functionally equivalent before testing. The previously identified implementations are research candidates, not approved dependencies or validated performance claims:
- [kokoro-mlx](https://github.com/gabrimatic/kokoro-mlx)
- [kokoro-coreml](https://huggingface.co/mattmireles/kokoro-coreml)

---

## Baseline Configuration (Preserved)
- **Model artifact**: FP16 ONNX (`kokoro-v1.0.fp16.onnx`, SHA256: `f3a290d384fbb27966d462905c71a46cef9e5fd00516b40df32a0b4afe77ac96`)
- **Inference threads**: 4 (`ONNX_INTRA_THREADS = 4`, `inter_op_num_threads = 1`)
- **Lookahead chunks**: 4 sentences (`LOOKAHEAD_CHUNKS = 4`)
- **Audio cache budget**: 32 MiB (`MAX_AUDIO_CACHE_BYTES = 33554432`)
- **Execution provider**: `CPUExecutionProvider`

---

## Non-negotiable Constraints
- Preserve existing document parsing, pronunciation overrides, voice selection, click-to-speak, playback speed, and LAN companion behavior.
- Preserve the current ONNX implementation as a working fallback.
- Do not require optional acceleration packages for the baseline installation.
- Do not introduce cloud inference or runtime network dependencies.
- Do not silently substitute another voice, language, or model.
- Do not claim GPU or Neural Engine execution merely because a framework supports it.
- Do not claim exact word alignment when timings are estimated.
- Do not replace inference errors with unexplained silence.
- Do not promote a new backend until correctness and sustained-playback tests pass.

---

## Roadmap

### 1. Establish a Reproducible Baseline
- Inspect current checkout, dependency versions, server endpoints, UI audio pipeline, and TTS call sites.
- Record hardware, OS, Python, ONNX Runtime, checksums, and thread settings in `docs/tts-baseline.md`.
- Build benchmark suite: `benchmarks/tts/corpus.jsonl`, `benchmarks/tts/run.py`, `benchmarks/tts/README.md`.
- Establish automated test suite in `tests/tts/`.
- Validate with a small initial benchmark run.

### 2. Separate Orchestration from Inference
- Keep `TTSEngine` as compatibility facade.
- Modularize into:
  - `src/tts/contracts.py`: Capabilities, SynthesisRequest, SynthesisResult.
  - `src/tts/frontend.py`: Text normalization, phonemization, lexicon overrides.
  - `src/tts/alignment.py`: Transformation trace and word/phoneme alignment.
  - `src/tts/scheduler.py`: Priority queue with generation epochs.
  - `src/tts/cache.py`: Strict byte-bounded multi-dimensional key cache.
  - `src/tts/backends/base.py`: Abstract base backend interface.
  - `src/tts/backends/onnx_backend.py`: Existing ONNX implementation behind backend interface.

### 3. Safe Backend Selection
- Configuration via `KAIZEN_TTS_BACKEND=onnx|mlx|coreml|auto`.
- Explicit modes fail actionably; auto selects validated compatible backends with graceful fallback.

### 4. Source-to-Speech Transformation Trace
- Replace proportional word mapping with an explicit transformation trace:
  `Document text spans` -> `normalized spoken tokens` -> `pronunciation/phoneme spans` -> `synthesized timing spans`.
- Handle many-to-many mappings (e.g. `$4,500.50` -> `four thousand five hundred dollars and fifty cents`).
- Fall back honestly to sentence highlighting when word-level mapping is unavailable or estimated.

### 5. Priority Scheduler
- Priority order:
  1. Current user-selected sentence (foreground)
  2. Next required playback chunk
  3. Speculative lookahead (background)
- Epoch-based preemption, cancellation tracking, and session isolation.

### 6. Correct & Bounded Caching
- Cache key includes: backend id/version, model checksum, voice id, effective language, phonemes/tokens, speed, prosody, and normalization/lexicon hash.
- Strict 32 MiB budget enforcement, thread-safe, deduplication of concurrent requests.

### 7. Accelerated Backends (Stage B & Stage C)
- Stage A: ONNX extraction and verification.
- Stage B: MLX experiment (optional import, evaluate API, license, pronunciation, timing).
- Stage C: Core ML experiment (audit precision, toolchain, persistent helper IPC, long-session stability).

### 8. Application-Level Benchmarking
- Measure cold load, normalization, inference, encoding, first audible audio, seek latency, real-time factor (RTF), memory, and underruns.

### 9. Tests and Promotion Gates
- Automated test coverage across all edge cases, cache isolation, rapid seeking, unicode offsets, and structured errors.
- Manual verification across sustained narration, max playback speed, companion sync, sleep/wake.

### 10. Documentation and Handoff
- Update README, publish benchmark report with raw data, state winner with reproducible commands.
