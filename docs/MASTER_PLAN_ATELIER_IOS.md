# KaizenReader — Master Architectural & UI/UX Blueprint
## The "Atelier & Acoustic Chronograph" Edition for MacBook Pro M1 & iPhone 16e

**Date**: 2026-11-15  
**Target Hardware**: Apple MacBook Pro M1 (16 GB UMA, Foundry) + Apple iPhone 16e (A18 SoC, 8 GB RAM, Super Retina XDR OLED, Autonomous Field Deck)  
**Companion Specifications**: [`docs/tts-baseline.md`](./tts-baseline.md) · [`docs/tts-m1-optimization-brief.md`](./tts-m1-optimization-brief.md)

---

## 1. Executive Summary & Core Engineering Mandate

KaizenReader is engineered around three non-negotiable pillars defined in [`README.md`](../README.md):
1. **Mechanical Sympathy**: Aligning every data structure, audio buffer, and compute kernel with Apple Silicon hardware (M1 Unified Memory + A18 Hardware Media DSP & 16-Core Neural Engine).
2. **Semantic Rigor**: Preserving hierarchical Document AST nodes (`Document` -> `Chapter` -> `ParagraphNode` -> `SentenceNode` in [`src/parsers/base.py`](../src/parsers/base.py)), context-gated normalization ([`src/tts/normalizer.py`](../src/tts/normalizer.py)), and deterministic IPA lexicon overrides ([`src/tts/lexicon.py`](../src/tts/lexicon.py)).
3. **The Third Door Choice**: Rejecting both bloated Electron wrappers and sterile, fragile web toys in favor of an ultra-responsive, self-contained **Sovereign Reading Instrument**.

### Real-World Operational Constraints (Off-Grid Field Reliability)
- **Intermittent Mac & Wi-Fi Access**: Development and heavy batch synthesis happen during charging sessions at libraries or coffee shops on the MacBook Pro M1.
- **100% Autonomous iPhone 16e Operation**: Once away from the library, the MacBook Pro M1 is powered off and packed away, and the iPhone 16e operates with **zero cellular data and zero Wi-Fi**.
- **Zero Expiration Timers**: Never relies on 7-day expiring free Xcode sideload certificates.
- **Extreme Battery Stewardship**: Sips **~1.2%-1.8% battery per hour** with the screen locked (via hardware AAC-LC decoding or ANE speech synthesis) and minimizes display power when reading via a true zero-nit `#000000` OLED surface.
- **Aesthetic & Functional Mastery**: Rejects both generic AI dark-slate templates and sterile over-minimalism. The reading canvas remains serene and typographically authoritative, while interactive surfaces feel like a **Leica M11 / Nagra IV-S / Swiss Chronograph**—featuring exposed structural hairlines, tactile vernier dials, real-time acoustic telemetry, an inline IPA phonetic lens, and a multi-engine voice selector comparing **Kokoro-82M Studio** and **Apple Neural / Siri Natural TTS**.

---

## 2. Forensic Post-Mortem: Why Naive Mobile PWA Approaches Fail on iOS

| Failure Point | Root Cause in Codebase & iOS WebKit | Architectural Resolution in This Master Plan |
|---|---|---|
| **1. Insecure Origin Kills Service Workers** | WebKit disables `navigator.serviceWorker` on plain `http://<LAN_IP>:8977` (only `https://` or `http://localhost` are Secure Contexts). Public library Wi-Fi also enforces **AP Client Isolation**. | **Tri-Channel Zero-Cost Transport**: (a) Local Root CA + SAN TLS (`--https`) over USB-C cable or Mac-to-iPhone ad-hoc Wi-Fi; (b) Network-free **`.kzn` Sovereign Cartridge** files transferred via AirDrop or USB Files app; (c) Optional static HTTPS PWA shell seed. |
| **2. Raw 24 kHz PCM WAV Storage Bloat** | [`src/tts/engine.py`](../src/tts/engine.py) (`sf.write(..., format="WAV", subtype="PCM_16")`) outputs `48 KB/s` (`~172.8 MB/hr`). A 10-hour book is **1.73 GB** and ~8,000 separate IndexedDB blobs. | **Batched Chapter Audio Sprites (`.m4a` AAC-LC 48 kbps)**: Compresses 24 kHz mono speech via macOS native `/usr/bin/afconvert` at an **8.0:1 ratio** (`~21.6 MB/hr`) with transparent vocal fidelity (`MOS 4.6` preserved). |
| **3. iOS Lock-Screen Suspension Between Sentences** | [`src/ui/app.js`](../src/ui/app.js) (`playSentenceAt`) decodes each sentence via `AudioContext.decodeAudioData` and chains `src.onended`. When locked, iOS freezes `requestAnimationFrame` (`0 Hz`) and suspends WebContent during async sentence transitions. | **Continuous Hardware `<audio>` Sprite Deck**: An entire chapter plays as **one continuous `.m4a` hardware stream** on the A18 Media DSP. The CPU can sleep for 45+ minutes while audio plays seamlessly through lock screen and AirPods Pro 2. |
| **4. Kokoro OOV Cultural & Historical Pronunciation Gaps** | [`src/tts/engine.py`](../src/tts/engine.py) relies on `espeak-ng` C rule tables (`self.kokoro.tokenizer.phonemize`). Unlisted Semitic, Hellenistic, Patristic, or polyglot proper nouns fall back to flat letter-to-sound rules. | **Quad-Engine Speech Router + Apple Neural TTS**: Integrates Apple's on-device Neural TTS (trained on massive multi-lingual proper-noun corpora) + W3C SSML `<phoneme>` injection + A/B pronunciation auditioning. |
| **5. Naive `window.speechSynthesis` Loses Word Sync** | Calling `speechSynthesis.speak()` on raw paragraphs drops utterances >250 chars on iOS lock screen and breaks `.word-token` karaoke spotlighting. | **Boundary-Mapped Neural Utterance Driver**: Runs sentence-chunked utterances through `normalize_text_for_tts`, injects lexicon IPA/aliases, and binds `utterance.onboundary` (`event.charIndex`) to exact `.word-token` DOM spans at 60fps. |

---

## 3. Quad-Engine Speech Architecture: Kokoro-82M + Apple Neural TTS

### 3.1 Why Apple Neural / Siri Natural TTS Complements Kokoro-82M
In [`src/tts/engine.py`](../src/tts/engine.py), Kokoro-82M achieves studio timbre (`4.6 MOS`), but its frontend phonemizer (`espeak-ng`) is rule-based. When reading texts dense with:
- **Ancient Near Eastern, Biblical, & Patristic Names** (*Mahalalel, Hegesippus, Symmachus, Theodotion, Qumran, Mashal, Chokhmah*)
- **Classical Greek, Latin, & Philosophical Terms** (*Apokatastasis, Ousia, Hypostasis, Perichoresis, Weltanschauung*)
- **Historical & Geopolitical Proper Nouns** (*French, German, Russian, Arabic, and Mandarin names embedded in English prose*)
- **Sentence-Level Homographs** (*tear, bow, row, wind, lead, bass*)

Apple's on-device **Neural / Siri Natural TTS** engine (`AVSpeechSynthesizer` on iOS 18 and macOS Sequoia+) uses a contextual transformer G2P model running on the **16-core Apple Neural Engine (ANE)** that:
1. Resolves homographs using bidirectional sentence attention.
2. Recognizes tens of thousands of historical, biblical, classical, and international proper nouns out-of-the-box with natural stress contours.
3. Supports **W3C SSML (`<speak>`, `<phoneme alphabet="ipa" ph="...">`, `<sub alias="...">`, `<prosody>`)** so every entry in [`src/tts/lexicon.py`](../src/tts/lexicon.py) (`DEFAULT_LEXICON` + custom user overrides) works across **both** Kokoro-82M and Apple Neural voices.

### 3.2 The Four Selectable Speech Engines
1. **`KOKORO_VAULT` (`[A18 HW SPRITE]`)**: Plays pre-packed Kokoro-82M `.m4a` chapter sprites from iPhone IndexedDB via `<audio>` hardware decoder. 100% offline, ~1.2% battery/hr, exact phoneme word timings.
2. **`APPLE_NEURAL_LIVE` (`[ANE ON-DEVICE]`)**: Drives iPhone 16e / macOS on-device Neural voices (Ava/Allison/Evan Premium + Siri Natural) via SSML & Web Speech API with `onboundary` word spotlighting. 100% offline, 0 MB cache needed, superior out-of-the-box cultural/historical name G2P.
3. **`APPLE_NEURAL_SPRITE` (`[M1 -> .M4A]`)**: Synthesizes chapters on Mac via PyObjC `AVFAudio` / `say` using macOS Natural/Premium voices + word boundary callbacks, packed into `.m4a` / `.kzn` sprites for lock-screen hardware playback.
4. **`KOKORO_LIVE` (`[M1 STREAM]`)**: Real-time FP16 sentence streaming from the M1 daemon while on USB-C / local Wi-Fi, auto-caching into the Vault.

---

## 4. The Sovereign Vault & `.kzn` Cartridge Specification

### 4.1 Chapter Audio Sprite Compiler (`src/tts/sprite_compiler.py`)
Each chapter is compiled into a deterministic **Chapter Sprite Pair**:
- **`ch_{idx:03d}.m4a`**: Stitched 24 kHz mono PCM arrays with node-specific prosodic pauses (`0.42s` for `h1`-`h4`, `0.34s` for `blockquote`, `0.24s` for `p`), encoded via `/usr/bin/afconvert -f m4af -d aac -b 48000 -r 24000`.
- **`ch_{idx:03d}.timings.json`**: Compact tabular index mapping every sentence and `[word_index, start_sec, end_sec]` tuple for $O(\log N)$ binary search during playback.

### 4.2 The `.kzn` Sovereign Cartridge Format
A standard ZIP archive packaging a book for zero-network transfer via AirDrop, USB-C Finder File Sharing, or the iOS Files app:
- `manifest.json` (version, book metadata, voice, engine, SHA256)
- `ast.json` (full `Document` AST)
- `lexicon_snapshot.json` (active pronunciation overrides)
- `state_bookmark.json` (current chapter, sentence, and notes)
- `sprites/ch_XXX.m4a` + `sprites/ch_XXX.timings.json`

### 4.3 Client-Side IndexedDB Sovereign Vault (`src/ui/vault.js`)
Database `kaizen_sovereign_vault_v1` with object stores:
- `books_meta` (`keyPath: "id"`)
- `books_ast` (`keyPath: "id"`)
- `chapter_sprites` (`keyPath: "sprite_key"`)
- `user_state_sync` (`keyPath: "key"`)

---

## 5. Bespoke UI/UX Specification: "Atelier & Acoustic Chronograph"

### 5.1 Five Curated Material Themes (`src/ui/styles.css`)
- **Warm Vellum (`sepia`)**: `#fbf7ee` canvas · `#f2eadb` surface · `#a85d26` burnt sienna accent.
- **Swiss Atelier (`light`)**: `#fafaf9` canvas · `#f0f0ee` surface · `#1d4ed8` cobalt accent.
- **Carbon Studio (`dark`)**: `#111215` canvas · `#1a1c21` surface · `#f59e0b` tube amber accent.
- **Obsidian Phosphor (`oled` — iPhone 16e Super Retina XDR)**: `#000000` true zero-nit black canvas · `#12100e` obsidian surface · `#28231d` 1px brass hairline · `#d8cfc2` warm parchment text · `#e5a93c` Leica phosphor accent.
- **E-Ink Folio (`eink`)**: `#f4f4f4` canvas · `#000000` high-contrast ink.

### 5.2 Signature Interactive Surfaces
1. **60fps Acoustic Cadence Ribbon (`<canvas id="acoustic-ribbon">`)**: Real-time vocal RMS waveform + structural AST pins (`H1`/`H2` markers, blockquote spans) + touch-scrub magnifier loupe.
2. **Atelier Console Bottom Sheet**: Quad-Engine selector bar, Horological Vernier Speed Dial (`0.75x`-`2.50x`) with **Smart Study Cadence** (auto `-12%` speed on blockquotes/headings), and Typographic Caliper.
3. **Floating Inline Phonetic & IPA Lens**: Anchored word inspector with interactive syllable stress pills (`ˈ`/`ˌ`), live IPA preview, and 1-tap **A/B Audition (`[ 🔊 Kokoro ]` vs. `[  Apple Neural ]`)**.
4. **Tactile Cartridge Vault Bay**: Visual chapter-segment matrix per book with 1-tap **"Pack Next 3 Chapters"**, **"Pack Full Book"**, and **"Export/Import `.kzn` Cartridge"**.
5. **Swiss Night Chronograph Pocket Curtain**: Zero-nit `#000000` touch-lock screen with circular chapter progress dial, live sentence ticker, hardware engine telemetry badge, and slide-to-unlock track.

---

## 6. Phased Implementation Roadmap

1. **Phase 1 — Backend Sprite Compiler, Apple Neural Bridge, & `.kzn` API**:
   - Build `src/tts/sprite_compiler.py`, `src/tts/apple_engine.py`, `src/certs.py`, and new routes in `src/server/app.py`.
2. **Phase 2 — Sovereign IndexedDB Vault, Service Worker, & Local AST Parser**:
   - Build `src/ui/manifest.webmanifest`, `src/ui/sw.js`, `src/ui/vault.js`, `src/ui/phonetics_client.js`, and `src/ui/offline_parser.js`.
3. **Phase 3 — Quad-Engine Audio Router & Atelier Chronograph UI/UX**:
   - Upgrade `src/ui/index.html`, `src/ui/styles.css`, and `src/ui/app.js` with the Hardware Sprite `<audio>` deck, Apple Neural Live SSML/boundary driver, Smart Resume, Acoustic Cadence Ribbon, Inline Phonetic Lens, and Obsidian Phosphor OLED theme.
4. **Phase 4 — Verification & Benchmark Gate**:
   - Run automated tests (`pytest`) verifying `.m4a` sprite generation, `.kzn` round-trip integrity, Apple Neural synthesis, and timing alignment.
