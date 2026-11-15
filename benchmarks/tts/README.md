# KaizenReader TTS Benchmark Suite

This benchmark suite measures the speech synthesis runtime of KaizenReader on Apple Silicon (M1 Pro) with Kokoro-82M. It isolates cold start from warm inference, tracks real-time factors (RTF), memory usage, cache hit performance, and seek latency under background lookahead.

## Corpus

The benchmark corpus is located at `corpus.jsonl`. It includes 34 deterministic test cases covering:
1. **Sentence length**: Short (<3 words), medium (~15 words), and long complex clauses (~35+ words).
2. **Structural semantics**: Headers (`h1`, `h2`), blockquotes (`blockquote`), and lists (`li`) with prosody pauses.
3. **Numbers & symbols**: Currencies (`$4,500.50`, `£250.00`, `€1,200`), dates, timestamps, physical units (`km/h`, `kW`, `GB`), and abbreviations (`e.g.`, `i.e.`, `etc.`).
4. **Lexicon & technical terminology**: Custom pronunciations (`Nginx`, `Kubernetes`, `PostgreSQL`, `FastAPI`, `PyTorch`, `NumPy`, `deque`, `trie`) and historical names (`Euler`, `Gauss`, `Laplace`, `Nietzsche`, `Kierkegaard`).
5. **Contextual homographs**: `read` (past/present), `tear` (noun/verb), `lead` (verb/noun).
6. **Punctuation density**: Ellipses, em-dashes, semicolons, nested quotes, parentheses.
7. **Cache behavior**: Cold vs repeated queries, cache hit latency, and byte accounting.
8. **Smart audio suppression**: Code blocks and footnote citations (`[1]`, `(3)`).
9. **Seek preemption**: Foreground latency when seeking during active lookahead queues.

## Metrics & Boundaries

- **Cold Load Time**: Timestamp difference between process start and model session readiness.
- **Normalization Time**: Text expansion, regex normalization, and phonemization latency.
- **Inference Time**: Direct model execution (`create_timed` / ONNX runtime session).
- **Encoding & Alignment**: WAV PCM serialization and word/phoneme alignment calculation.
- **Real-Time Factor (RTF)**: `Synthesis Time / Generated Audio Duration`. Lower is better (e.g., 0.28 means 1 second of audio takes 0.28 seconds to generate).
- **Times Real-Time**: `1.0 / RTF`. Higher is better (e.g., 3.5x real time).
- **Seek Preemption Latency**: Elapsed time from a user seek action to audible audio readiness while 4 speculative lookahead sentences are in-flight.
- **Memory Footprint**: Process resident set size (`ru_maxrss`).

## Usage

```bash
# Validate instrumentation with first 5 sentences
.venv/bin/python benchmarks/tts/run.py --quick

# Run complete 34-item benchmark
.venv/bin/python benchmarks/tts/run.py

# Custom output file
.venv/bin/python benchmarks/tts/run.py --output benchmarks/tts/results_my_run.json
```
