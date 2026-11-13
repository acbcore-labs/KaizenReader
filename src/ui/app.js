/**
 * KaizenReader Client Engine
 * Implements gapless sentence synthesis, bidirectional DOM highlighting,
 * click-to-seek, and unified state persistence.
 */

// Application State
const state = {
  currentBook: null,
  currentChapterIndex: 0,
  currentSentenceIndex: 0,
  isPlaying: false,
  voice: "af_bella",
  speed: 1.0,
  theme: "sepia",
  fontSize: 19,
  sentencesInChapter: [],
  audioPlayer: new Audio(),
  preloadedAudios: new Map(),
  ws: null,
};

// DOM Elements
const elements = {
  readerContent: document.getElementById("reader-content"),
  bookTitle: document.getElementById("current-book-title"),
  playPauseBtn: document.getElementById("play-pause-btn"),
  playIcon: document.getElementById("play-icon"),
  pauseIcon: document.getElementById("pause-icon"),
  prevBtn: document.getElementById("prev-sentence-btn"),
  nextBtn: document.getElementById("next-sentence-btn"),
  voiceSelect: document.getElementById("voice-select"),
  speedSelect: document.getElementById("speed-select"),
  themeSelect: document.getElementById("theme-select"),
  fontIncreaseBtn: document.getElementById("font-increase-btn"),
  fontDecreaseBtn: document.getElementById("font-decrease-btn"),
  posIndicator: document.getElementById("reading-position-indicator"),
  progressBarFill: document.getElementById("progress-bar-fill"),
  progressBarContainer: document.getElementById("progress-bar-container"),
  drawerOverlay: document.getElementById("drawer-overlay"),
  toggleDrawerBtn: document.getElementById("toggle-drawer-btn"),
  closeDrawerBtn: document.getElementById("close-drawer-btn"),
  libraryList: document.getElementById("library-list"),
  tocList: document.getElementById("toc-list"),
  dropzone: document.getElementById("dropzone"),
  fileInput: document.getElementById("file-input"),
  mobileBadge: document.getElementById("mobile-badge"),
  mobileUrlText: document.getElementById("mobile-url-text"),
  lexWordInput: document.getElementById("lex-word-input"),
  lexPhoneticInput: document.getElementById("lex-phonetic-input"),
  lexAddBtn: document.getElementById("lex-add-btn"),
  lexiconList: document.getElementById("lexicon-list"),
};

// Initialization
async function init() {
  loadSavedSettings();
  setupEventListeners();
  await fetchStatusAndVoices();
  await loadLexicon();
  await loadLibrary();
  connectWebSocket();
}

async function loadLexicon() {
  try {
    const res = await fetch("/api/lexicon");
    const data = await res.json();
    renderLexicon(data);
  } catch (err) {
    console.error("Error loading lexicon:", err);
  }
}

function renderLexicon(lexicon) {
  if (!elements.lexiconList) return;
  elements.lexiconList.innerHTML = "";
  for (const [word, phonetic] of Object.entries(lexicon)) {
    const chip = document.createElement("div");
    chip.className = "lex-chip";
    chip.innerHTML = `
      <span class="lex-chip-word">${word}</span>
      <span class="lex-chip-arrow">&rarr;</span>
      <span class="lex-chip-phonetic">${phonetic}</span>
      <span class="lex-chip-del" title="Delete override">&times;</span>
    `;
    chip.querySelector(".lex-chip-del").onclick = async (e) => {
      e.stopPropagation();
      await deleteLexiconWord(word);
    };
    elements.lexiconList.appendChild(chip);
  }
}

async function saveLexiconWord() {
  const word = elements.lexWordInput.value.trim();
  const phonetic = elements.lexPhoneticInput.value.trim();
  if (!word || !phonetic) return;

  try {
    await fetch("/api/lexicon", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ word, phonetic })
    });
    elements.lexWordInput.value = "";
    elements.lexPhoneticInput.value = "";
    await loadLexicon();
    // Refresh current chapter to update tts_text
    if (state.currentBook) await openBook(state.currentBook.id);
  } catch (err) {
    alert("Error saving pronunciation: " + err.message);
  }
}

async function deleteLexiconWord(word) {
  try {
    await fetch(`/api/lexicon/${encodeURIComponent(word)}`, {
      method: "DELETE"
    });
    await loadLexicon();
    if (state.currentBook) await openBook(state.currentBook.id);
  } catch (err) {
    alert("Error deleting pronunciation: " + err.message);
  }
}

function loadSavedSettings() {
  const savedVoice = localStorage.getItem("kaizen_voice");
  if (savedVoice) state.voice = savedVoice;

  const savedSpeed = localStorage.getItem("kaizen_speed");
  if (savedSpeed) state.speed = parseFloat(savedSpeed);

  const savedTheme = localStorage.getItem("kaizen_theme") || "sepia";
  state.theme = savedTheme;
  applyTheme(savedTheme);

  const savedFontSize = localStorage.getItem("kaizen_font_size");
  if (savedFontSize) {
    state.fontSize = parseInt(savedFontSize);
    document.documentElement.style.setProperty("--content-font-size", `${state.fontSize}px`);
  }
}

function applyTheme(theme) {
  state.theme = theme;
  document.documentElement.setAttribute("data-theme", theme);
  elements.themeSelect.value = theme;
  localStorage.setItem("kaizen_theme", theme);
}

async function fetchStatusAndVoices() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    if (data.companion_url) {
      elements.mobileUrlText.textContent = data.companion_url.replace("http://", "");
      elements.mobileBadge.onclick = () => {
        navigator.clipboard?.writeText(data.companion_url);
        elements.mobileUrlText.textContent = "Copied to clipboard!";
        setTimeout(() => {
          elements.mobileUrlText.textContent = data.companion_url.replace("http://", "");
        }, 2000);
      };
    }

    const voiceRes = await fetch("/api/voices");
    const voices = await voiceRes.json();
    populateVoiceSelect(voices);
  } catch (err) {
    console.error("Failed to load status/voices:", err);
  }
}

function populateVoiceSelect(voices) {
  elements.voiceSelect.innerHTML = "";
  // Group by category
  const groups = {};
  voices.forEach(v => {
    if (!groups[v.category]) groups[v.category] = [];
    groups[v.category].push(v);
  });

  for (const [catName, list] of Object.entries(groups)) {
    const optgroup = document.createElement("optgroup");
    optgroup.label = catName;
    list.forEach(v => {
      const opt = document.createElement("option");
      opt.value = v.id;
      opt.textContent = v.name;
      if (v.id === state.voice) opt.selected = true;
      optgroup.appendChild(opt);
    });
    elements.voiceSelect.appendChild(optgroup);
  }
}

let libraryRetryCount = 0;
async function loadLibrary() {
  try {
    const res = await fetch("/api/library");
    const books = await res.json();
    renderLibraryList(books);

    const savedBookId = localStorage.getItem("kaizen_book_id");
    let targetBook = books.find(b => b.id === savedBookId) || books[0];

    if (targetBook) {
      await openBook(targetBook.id);
    } else if (books.length === 0 && libraryRetryCount < 8) {
      libraryRetryCount++;
      elements.readerContent.innerHTML = `
        <div style="text-align:center; padding: 4rem 1rem;">
          <h2 style="font-family:var(--font-sans); font-size:1.2rem; margin-bottom:0.5rem;">Indexing Library...</h2>
          <p style="font-size:0.85rem; color:var(--text-muted);">Analyzing documents and optimizing pronunciation models on Apple Silicon M1...</p>
        </div>
      `;
      setTimeout(loadLibrary, 1000);
    } else {
      elements.readerContent.innerHTML = `
        <div style="text-align:center; padding: 4rem 1rem;">
          <h2 style="font-family:var(--font-sans); font-size:1.2rem; margin-bottom:0.5rem;">Library Ready</h2>
          <p style="font-size:0.85rem; color:var(--text-muted); margin-bottom:1rem;">Drop any book or document file (.epub, .pdf, .md, .docx, .txt) into the window to begin reading.</p>
        </div>
      `;
    }
  } catch (err) {
    console.error("Error loading library:", err);
  }
}

function renderLibraryList(books) {
  elements.libraryList.innerHTML = "";
  books.forEach(b => {
    const item = document.createElement("div");
    item.className = `library-item ${state.currentBook?.id === b.id ? "active" : ""}`;
    item.innerHTML = `
      <div>
        <div style="font-weight:600;">${b.title}</div>
        <div style="font-size:0.75rem; color:var(--text-muted);">${b.file_format.toUpperCase()} · ${b.chapters_count} chapters</div>
      </div>
      <span>→</span>
    `;
    item.onclick = () => {
      openBook(b.id);
      closeDrawer();
    };
    elements.libraryList.appendChild(item);
  });
}

async function openBook(bookId) {
  try {
    const res = await fetch(`/api/book/${bookId}`);
    const book = await res.json();
    state.currentBook = book;
    localStorage.setItem("kaizen_book_id", bookId);

    elements.bookTitle.textContent = `${book.title}`;
    renderTOC(book.chapters);

    // Restore saved chapter or first
    const savedChapter = parseInt(localStorage.getItem(`kaizen_chap_${bookId}`) || "0");
    state.currentChapterIndex = Math.min(savedChapter, book.chapters.length - 1);
    state.currentSentenceIndex = 0;

    renderCurrentChapter();
  } catch (err) {
    console.error("Error opening book:", err);
  }
}

function renderTOC(chapters) {
  elements.tocList.innerHTML = "";
  chapters.forEach((ch, idx) => {
    const item = document.createElement("div");
    item.className = `toc-item ${state.currentChapterIndex === idx ? "active" : ""}`;
    item.textContent = ch.title;
    item.onclick = () => {
      goToChapter(idx);
      closeDrawer();
    };
    elements.tocList.appendChild(item);
  });
}

function renderCurrentChapter() {
  if (!state.currentBook) return;
  const chapter = state.currentBook.chapters[state.currentChapterIndex];
  if (!chapter) return;

  // Flatten sentences for index lookup
  state.sentencesInChapter = [];
  let sCounter = 0;

  let html = `
    <div class="doc-chapter-header">
      <div class="doc-chapter-meta">${state.currentBook.title} · Chapter ${state.currentChapterIndex + 1} of ${state.currentBook.chapters.length}</div>
      <h1 class="doc-chapter-title">${chapter.title}</h1>
    </div>
  `;

  chapter.paragraphs.forEach(p => {
    let tagClass = "reader-paragraph";
    if (p.is_heading) tagClass = p.node_type === "h1" ? "reader-heading-1" : "reader-heading-2";
    else if (p.is_quote) tagClass = "reader-blockquote";
    else if (p.is_code) tagClass = "reader-code";

    let sentenceSpans = "";
    p.sentences.forEach(s => {
      const idxInChapter = sCounter++;
      state.sentencesInChapter.push({ ...s, chapterIndex: state.currentChapterIndex, indexInChapter: idxInChapter });

      sentenceSpans += `<span class="sentence-span" data-sidx="${idxInChapter}" id="span-${s.id}">${s.text} </span>`;
    });

    html += `<div class="${tagClass}">${sentenceSpans}</div>`;
  });

  elements.readerContent.innerHTML = html;

  // Attach click-to-speak listener
  elements.readerContent.querySelectorAll(".sentence-span").forEach(el => {
    el.onclick = (e) => {
      const idx = parseInt(el.getAttribute("data-sidx"));
      playSentenceAt(idx);
    };
  });

  updateProgressIndicator();
  updateTOCActiveItem();
}

function updateTOCActiveItem() {
  const items = elements.tocList.querySelectorAll(".toc-item");
  items.forEach((item, idx) => {
    if (idx === state.currentChapterIndex) item.classList.add("active");
    else item.classList.remove("active");
  });
}

function goToChapter(chapterIndex) {
  pauseAudio();
  state.currentChapterIndex = chapterIndex;
  state.currentSentenceIndex = 0;
  localStorage.setItem(`kaizen_chap_${state.currentBook.id}`, chapterIndex);
  renderCurrentChapter();
}

// ----------------- Playback & TTS Engine ----------------- //

function togglePlay() {
  if (state.isPlaying) {
    pauseAudio();
  } else {
    playSentenceAt(state.currentSentenceIndex);
  }
}

function pauseAudio() {
  state.isPlaying = false;
  state.audioPlayer.pause();
  elements.playIcon.style.display = "block";
  elements.pauseIcon.style.display = "none";
}

async function playSentenceAt(index) {
  if (!state.sentencesInChapter || state.sentencesInChapter.length === 0) return;

  // Boundary checks
  if (index >= state.sentencesInChapter.length) {
    // Next chapter
    if (state.currentChapterIndex < state.currentBook.chapters.length - 1) {
      goToChapter(state.currentChapterIndex + 1);
      playSentenceAt(0);
    } else {
      pauseAudio();
    }
    return;
  }

  if (index < 0) index = 0;

  state.currentSentenceIndex = index;
  state.isPlaying = true;
  elements.playIcon.style.display = "none";
  elements.pauseIcon.style.display = "block";

  const currentSentence = state.sentencesInChapter[index];

  // Update spotlight visual highlight
  highlightSentence(currentSentence.id);
  updateProgressIndicator();

  // If sentence has no tts_text (e.g. code block skipped in Smart Audio Mode), advance immediately
  if (!currentSentence.tts_text || !currentSentence.tts_text.trim()) {
    setTimeout(() => {
      if (state.isPlaying) playSentenceAt(index + 1);
    }, 400);
    return;
  }

  // Synthesize and play
  try {
    const audioUrl = `/api/tts/sentence?text=${encodeURIComponent(currentSentence.tts_text)}&voice=${state.voice}&speed=${state.speed}&sentence_id=${currentSentence.id}`;
    state.audioPlayer.src = audioUrl;
    state.audioPlayer.playbackRate = 1.0; // Speed is baked directly into Kokoro model synthesis

    state.audioPlayer.onended = () => {
      if (state.isPlaying) {
        playSentenceAt(state.currentSentenceIndex + 1);
      }
    };

    state.audioPlayer.onerror = (err) => {
      console.warn("Audio playback error, skipping to next sentence:", err);
      if (state.isPlaying) playSentenceAt(state.currentSentenceIndex + 1);
    };

    await state.audioPlayer.play();

    // Trigger lookahead pre-synthesis for upcoming sentences in background
    triggerLookahead(index + 1);

    // Broadcast sync to WebSocket
    broadcastPosition(currentSentence.id);

  } catch (err) {
    console.error("Playback error:", err);
  }
}

function highlightSentence(sentenceId) {
  document.querySelectorAll(".sentence-span.active-sentence").forEach(el => {
    el.classList.remove("active-sentence");
  });

  const targetSpan = document.getElementById(`span-${sentenceId}`);
  if (targetSpan) {
    targetSpan.classList.add("active-sentence");
    targetSpan.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function updateProgressIndicator() {
  const total = state.sentencesInChapter.length;
  const current = state.currentSentenceIndex + 1;
  elements.posIndicator.textContent = `${total > 0 ? current : 0} / ${total}`;

  const pct = total > 0 ? (current / total) * 100 : 0;
  elements.progressBarFill.style.width = `${pct}%`;
}

function triggerLookahead(startIndex) {
  const lookaheadItems = [];
  for (let i = startIndex; i < Math.min(startIndex + 4, state.sentencesInChapter.length); i++) {
    const s = state.sentencesInChapter[i];
    if (s.tts_text && s.tts_text.trim()) {
      lookaheadItems.push({ text: s.tts_text, voice: state.voice, speed: state.speed });
    }
  }

  if (lookaheadItems.length > 0) {
    fetch("/api/tts/lookahead", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: lookaheadItems })
    }).catch(() => {});
  }
}

// ----------------- WebSocket Synchronization ----------------- //

function connectWebSocket() {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${proto}//${window.location.host}/ws/sync`;
  
  try {
    state.ws = new WebSocket(wsUrl);
    state.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "remote_sync") {
          // If another device (e.g. mobile) tapped a sentence, synchronize position
          if (msg.book_id === state.currentBook?.id && msg.chapter_id === `ch_${state.currentChapterIndex}`) {
            const targetSentenceIdx = state.sentencesInChapter.findIndex(s => s.id === msg.sentence_id);
            if (targetSentenceIdx !== -1 && targetSentenceIdx !== state.currentSentenceIndex) {
              if (msg.is_playing) playSentenceAt(targetSentenceIdx);
              else {
                state.currentSentenceIndex = targetSentenceIdx;
                highlightSentence(msg.sentence_id);
                updateProgressIndicator();
              }
            }
          }
        }
      } catch (err) {}
    };
  } catch (err) {
    console.warn("WebSocket not available, running standalone mode.");
  }
}

function broadcastPosition(sentenceId) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify({
      action: "sync_position",
      book_id: state.currentBook?.id,
      chapter_id: `ch_${state.currentChapterIndex}`,
      sentence_id: sentenceId,
      is_playing: state.isPlaying
    }));
  }
}

// ----------------- Event Handlers & Shortcuts ----------------- //

function setupEventListeners() {
  // Play/Pause
  elements.playPauseBtn.onclick = togglePlay;

  // Prev/Next buttons
  elements.prevBtn.onclick = () => playSentenceAt(state.currentSentenceIndex - 1);
  elements.nextBtn.onclick = () => playSentenceAt(state.currentSentenceIndex + 1);

  // Voice selector
  elements.voiceSelect.onchange = (e) => {
    state.voice = e.target.value;
    localStorage.setItem("kaizen_voice", state.voice);
    if (state.isPlaying) playSentenceAt(state.currentSentenceIndex);
  };

  // Speed selector
  elements.speedSelect.onchange = (e) => {
    state.speed = parseFloat(e.target.value);
    localStorage.setItem("kaizen_speed", state.speed);
    if (state.isPlaying) playSentenceAt(state.currentSentenceIndex);
  };

  // Theme selector
  elements.themeSelect.onchange = (e) => {
    applyTheme(e.target.value);
  };

  // Font size buttons
  elements.fontIncreaseBtn.onclick = () => {
    state.fontSize = Math.min(state.fontSize + 1, 32);
    document.documentElement.style.setProperty("--content-font-size", `${state.fontSize}px`);
    localStorage.setItem("kaizen_font_size", state.fontSize);
  };

  elements.fontDecreaseBtn.onclick = () => {
    state.fontSize = Math.max(state.fontSize - 1, 14);
    document.documentElement.style.setProperty("--content-font-size", `${state.fontSize}px`);
    localStorage.setItem("kaizen_font_size", state.fontSize);
  };

  // Drawer
  elements.toggleDrawerBtn.onclick = openDrawer;
  elements.closeDrawerBtn.onclick = closeDrawer;
  elements.drawerOverlay.onclick = (e) => {
    if (e.target === elements.drawerOverlay) closeDrawer();
  };

  // Scrub Bar Click
  elements.progressBarContainer.onclick = (e) => {
    const rect = elements.progressBarContainer.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const targetIdx = Math.floor(ratio * state.sentencesInChapter.length);
    playSentenceAt(targetIdx);
  };

  // File Upload
  elements.dropzone.onclick = () => elements.fileInput.click();
  elements.fileInput.onchange = (e) => {
    if (e.target.files.length > 0) uploadFile(e.target.files[0]);
  };

  // Lexicon Save
  if (elements.lexAddBtn) {
    elements.lexAddBtn.onclick = saveLexiconWord;
    elements.lexPhoneticInput.onkeydown = (e) => {
      if (e.key === "Enter") saveLexiconWord();
    };
  }

  // Drag and drop
  window.addEventListener("dragover", (e) => {
    e.preventDefault();
    elements.dropzone.classList.add("dragover");
  });
  window.addEventListener("dragleave", (e) => {
    elements.dropzone.classList.remove("dragover");
  });
  window.addEventListener("drop", (e) => {
    e.preventDefault();
    elements.dropzone.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) {
      uploadFile(e.dataTransfer.files[0]);
    }
  });

  // Global Keyboard Shortcuts
  window.addEventListener("keydown", (e) => {
    // Ignore keystrokes inside text inputs
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)) return;

    if (e.code === "Space") {
      e.preventDefault();
      togglePlay();
    } else if (e.code === "ArrowLeft") {
      e.preventDefault();
      playSentenceAt(state.currentSentenceIndex - 1);
    } else if (e.code === "ArrowRight") {
      e.preventDefault();
      playSentenceAt(state.currentSentenceIndex + 1);
    } else if (e.code === "ArrowUp") {
      e.preventDefault();
      adjustSpeed(0.25);
    } else if (e.code === "ArrowDown") {
      e.preventDefault();
      adjustSpeed(-0.25);
    } else if (e.key === "m" || e.key === "M") {
      toggleDrawer();
    } else if (e.key === "t" || e.key === "T") {
      cycleTheme();
    }
  });
}

function adjustSpeed(delta) {
  const speeds = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5];
  let curIdx = speeds.indexOf(state.speed);
  if (curIdx === -1) curIdx = 1;
  const nextIdx = Math.max(0, Math.min(speeds.length - 1, curIdx + (delta > 0 ? 1 : -1)));
  state.speed = speeds[nextIdx];
  elements.speedSelect.value = state.speed.toString();
  localStorage.setItem("kaizen_speed", state.speed);
  if (state.isPlaying) playSentenceAt(state.currentSentenceIndex);
}

function cycleTheme() {
  const themes = ["sepia", "light", "dark", "eink"];
  const curIdx = themes.indexOf(state.theme);
  const nextTheme = themes[(curIdx + 1) % themes.length];
  applyTheme(nextTheme);
}

function openDrawer() {
  elements.drawerOverlay.classList.add("open");
}

function closeDrawer() {
  elements.drawerOverlay.classList.remove("open");
}

function toggleDrawer() {
  if (elements.drawerOverlay.classList.contains("open")) closeDrawer();
  else openDrawer();
}

async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  elements.dropzone.innerHTML = `<p>Uploading and analyzing <strong>${file.name}</strong>...</p>`;
  try {
    const res = await fetch("/api/upload", {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (data.success) {
      await loadLibrary();
      await openBook(data.document.id);
      closeDrawer();
    } else {
      alert("Failed to parse file: " + (data.detail || "Unknown error"));
    }
  } catch (err) {
    alert("Error uploading file: " + err.message);
  } finally {
    elements.dropzone.innerHTML = `
      <p><strong>Drop any file here</strong></p>
      <p style="font-size:0.75rem; margin-top:0.3rem;">.epub, .pdf, .md, .docx, .txt</p>
    `;
  }
}

// Start application
window.addEventListener("DOMContentLoaded", init);
