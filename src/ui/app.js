/**
 * KaizenReader Client Engine v2
 * Gapless Web Audio API playback, phoneme-timed word spotlighting,
 * double-buffered sentence prefetch, selection-to-lexicon, and state sync.
 */

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
  serverPositions: {},
  serverLastBookId: null,
  libraryBooks: [],
  // Dynamic Chapter & TOC Navigation State
  isTOCPinned: localStorage.getItem("kaizen_toc_pinned") === "true",
  quickNavOpen: false,
  zenRailOpen: false,
  chapterMetadata: [],
  quickNavSelectedIndex: -1,
  // User Profile, Memory & Notes State
  currentUser: null,
  allUsers: [],
  userMemory: null,
  userNotes: [],
  userModalOpen: false,
  // Web Audio gapless engine
  audioCtx: null,
  currentSource: null,
  playStartTime: 0,
  playbackRate: 1.0,
  activeTimings: [],
  rafId: null,
  playToken: 0,
  prefetchCache: new Map(), // key -> Promise<{buffer, timings, duration}>
  ws: null,
};

const elements = {
  readerContent: document.getElementById("reader-content"),
  bookTitle: document.getElementById("header-toc-title") || document.getElementById("current-book-title"),
  playPauseBtn: document.getElementById("play-pause-btn"),
  playIcon: document.getElementById("play-icon"),
  pauseIcon: document.getElementById("pause-icon"),
  prevBtn: document.getElementById("prev-sentence-btn"),
  nextBtn: document.getElementById("next-sentence-btn"),
  prevChapterBtn: document.getElementById("prev-chapter-btn"),
  nextChapterBtn: document.getElementById("next-chapter-btn"),
  voiceSelect: document.getElementById("voice-select"),
  speedSelect: document.getElementById("speed-select"),
  themeSelect: document.getElementById("theme-select"),
  fontIncreaseBtn: document.getElementById("font-increase-btn"),
  fontDecreaseBtn: document.getElementById("font-decrease-btn"),
  posIndicator: document.getElementById("reading-position-indicator"),
  etaIndicator: document.getElementById("reading-eta-indicator"),
  progressBarFill: document.getElementById("progress-bar-fill"),
  progressBarContainer: document.getElementById("progress-bar-container"),
  progressHoverTooltip: document.getElementById("progress-hover-tooltip"),
  drawerOverlay: document.getElementById("drawer-overlay"),
  toggleDrawerBtn: document.getElementById("toggle-drawer-btn"),
  closeDrawerBtn: document.getElementById("close-drawer-btn"),
  userLibraryList: document.getElementById("user-library-list"),
  userBooksCount: document.getElementById("user-books-count"),
  sampleBooksSection: document.getElementById("sample-books-section"),
  sampleBooksToggle: document.getElementById("sample-books-toggle"),
  sampleToggleChevron: document.getElementById("sample-toggle-chevron"),
  sampleLibraryList: document.getElementById("sample-library-list"),
  tocList: document.getElementById("toc-list"),
  tocFilterInput: document.getElementById("toc-filter-input"),
  dropzone: document.getElementById("dropzone"),
  fileInput: document.getElementById("file-input"),
  mobileBadge: document.getElementById("mobile-badge"),
  mobileUrlText: document.getElementById("mobile-url-text"),
  lexWordInput: document.getElementById("lex-word-input"),
  lexPhoneticInput: document.getElementById("lex-phonetic-input"),
  lexAddBtn: document.getElementById("lex-add-btn"),
  lexTestBtn: document.getElementById("lex-test-btn"),
  lexiconList: document.getElementById("lexicon-list"),
  searchToggleBtn: document.getElementById("search-toggle-btn"),
  searchBarPanel: document.getElementById("search-bar-panel"),
  bookSearchInput: document.getElementById("book-search-input"),
  bookSearchClose: document.getElementById("book-search-close"),
  bookSearchResults: document.getElementById("book-search-results"),
  teachSelectionBtn: document.getElementById("teach-selection-btn"),
  // New Ambient & Interactive TOC Elements
  headerTocPill: document.getElementById("header-toc-pill"),
  headerTocBadge: document.getElementById("header-toc-badge"),
  headerTocTitle: document.getElementById("header-toc-title"),
  headerTocPct: document.getElementById("header-toc-pct"),
  quickNavBackdrop: document.getElementById("quick-nav-backdrop"),
  quickNavHud: document.getElementById("quick-nav-hud"),
  quickNavInput: document.getElementById("quick-nav-input"),
  bookSpineBar: document.getElementById("book-spine-bar"),
  spineBookTitle: document.getElementById("spine-book-title"),
  spineStats: document.getElementById("spine-stats"),
  spineTooltip: document.getElementById("spine-tooltip"),
  quickNavList: document.getElementById("quick-nav-list"),
  quickNavJumpCurrentBtn: document.getElementById("quick-nav-jump-current-btn"),
  zenTocTrigger: document.getElementById("zen-toc-trigger"),
  zenTriggerBadge: document.getElementById("zen-trigger-badge"),
  zenTocRail: document.getElementById("zen-toc-rail"),
  zenRailCount: document.getElementById("zen-rail-count"),
  zenRailPinBtn: document.getElementById("zen-rail-pin-btn"),
  zenPinLabel: document.getElementById("zen-pin-label"),
  zenRailCloseBtn: document.getElementById("zen-rail-close-btn"),
  zenRailFilter: document.getElementById("zen-rail-filter"),
  zenRailList: document.getElementById("zen-rail-list"),
  zenCurrentLocationBtn: document.getElementById("zen-current-location-btn"),
  // User Profile, Memory & Cache Modal Elements
  userProfileBtn: document.getElementById("user-profile-btn"),
  headerUserAvatar: document.getElementById("header-user-avatar"),
  headerUserName: document.getElementById("header-user-name"),
  userModalBackdrop: document.getElementById("user-modal-backdrop"),
  userModal: document.getElementById("user-modal"),
  closeUserModalBtn: document.getElementById("close-user-modal-btn"),
  modalUserAvatar: document.getElementById("modal-user-avatar"),
  modalUserName: document.getElementById("modal-user-name"),
  modalUserHandle: document.getElementById("modal-user-handle"),
  userSwitcherList: document.getElementById("user-switcher-list"),
  addUserToggleBtn: document.getElementById("add-user-toggle-btn"),
  createUserForm: document.getElementById("create-user-form"),
  newUsernameInput: document.getElementById("new-username-input"),
  newUserAvatarSelect: document.getElementById("new-user-avatar-select"),
  cancelCreateUserBtn: document.getElementById("cancel-create-user-btn"),
  saveCreateUserBtn: document.getElementById("save-create-user-btn"),
  statReadingStreak: document.getElementById("stat-reading-streak"),
  statWordsRead: document.getElementById("stat-words-read"),
  statListenTime: document.getElementById("stat-listen-time"),
  statBooksCount: document.getElementById("stat-books-count"),
  clearMemoryBtn: document.getElementById("clear-memory-btn"),
  clearMemoryFeedback: document.getElementById("clear-memory-feedback"),
  cacheStatusText: document.getElementById("cache-status-text"),
  quickNoteInput: document.getElementById("quick-note-input"),
  addQuickNoteBtn: document.getElementById("add-quick-note-btn"),
  userNotesList: document.getElementById("user-notes-list"),
};

async function fetchWithTimeout(url, options = {}, timeoutMs = 1200) {
  if (navigator.onLine === false) {
    throw new Error("Offline");
  }
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(id);
    return res;
  } catch (e) {
    clearTimeout(id);
    throw e;
  }
}

function ensureAudioContext() {
  if (!state.audioCtx) {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    state.audioCtx = new AudioCtx();
  }
  if (state.audioCtx.state === "suspended") {
    state.audioCtx.resume().catch(() => {});
  }
  return state.audioCtx;
}

function primeAudioEnginesOnGesture() {
  try {
    ensureAudioContext();
  } catch (e) {}

  try {
    const hwDeck = document.getElementById("kaizen-hardware-deck");
    if (hwDeck) {
      if (!hwDeck.src && !hwDeck.currentSrc) {
        hwDeck.src = "data:audio/wav;base64,UklGRigAAABXQVZlZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQQAAAAAAA==";
        hwDeck.load();
      }
      const p = hwDeck.play();
      if (p && typeof p.then === "function") {
        p.then(() => {
          if (hwDeck.src && hwDeck.src.startsWith("data:")) {
            hwDeck.pause();
          }
        }).catch(() => {});
      }
    }
  } catch (e) {}
}

async function init() {
  loadSavedSettings();
  setupEventListeners();
  setupMediaSession();
  applyTOCPinState();
  setupZenAutoDim();
  setupProgressScrubberTooltip();
  await fetchUserData();
  await fetchServerState();
  await fetchStatusAndVoices();
  await loadLexicon();
  await loadLibrary();
  connectWebSocket();
}

async function fetchServerState() {
  if (navigator.onLine === false) return;
  try {
    const res = await fetchWithTimeout("/api/state", {}, 1000);
    if (!res.ok) return;
    const data = await res.json();
    state.serverPositions = data.positions || {};
    state.serverLastBookId = data.last_book_id || null;
    if (data.last_book_id) {
      localStorage.setItem("kaizen_book_id", data.last_book_id);
    }
  } catch (err) {}
}

function persistReadingState() {
  if (!state.currentBook) return;
  const bookId = state.currentBook.id;
  localStorage.setItem("kaizen_book_id", bookId);
  localStorage.setItem(`kaizen_chap_${bookId}`, String(state.currentChapterIndex));
  localStorage.setItem(`kaizen_sent_${bookId}`, String(state.currentSentenceIndex));

  fetch("/api/state", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      book_id: bookId,
      chapter_index: state.currentChapterIndex,
      sentence_index: state.currentSentenceIndex,
    }),
  }).catch(() => {});
}

// ----------------- Lexicon & Audition ----------------- //

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
      <span class="lex-chip-word"></span>
      <span class="lex-chip-arrow">&rarr;</span>
      <span class="lex-chip-phonetic"></span>
      <span class="lex-chip-del" title="Delete override">&times;</span>
    `;
    chip.querySelector(".lex-chip-word").textContent = word;
    chip.querySelector(".lex-chip-phonetic").textContent = phonetic;
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
      body: JSON.stringify({ word, phonetic }),
    });
    state.prefetchCache.clear();
    elements.lexWordInput.value = "";
    elements.lexPhoneticInput.value = "";
    await loadLexicon();
  } catch (err) {
    alert("Error saving pronunciation: " + err.message);
  }
}

async function testLexiconWord() {
  const word = elements.lexWordInput.value.trim();
  const phonetic = elements.lexPhoneticInput.value.trim();
  if (!word && !phonetic) return;

  const ctx = ensureAudioContext();
  const sampleText = phonetic ? (phonetic.startsWith("/") ? phonetic : `/${phonetic}/`) : word;
  // If user typed a respelling, save-less preview via server lexicon or raw text
  const queryText = phonetic && !phonetic.includes("/") ? word : sampleText;
  if (word && phonetic) {
    await fetch("/api/lexicon", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ word, phonetic }),
    });
    state.prefetchCache.clear();
    await loadLexicon();
  }
  try {
    const url = `/api/tts/sentence?text=${encodeURIComponent(word || queryText)}&voice=${state.voice}&speed=1.0`;
    const res = await fetch(url);
    const buf = await ctx.decodeAudioData(await res.arrayBuffer());
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    src.start(0);
  } catch (err) {
    console.error("Audition error:", err);
  }
}

async function deleteLexiconWord(word) {
  try {
    await fetch(`/api/lexicon/${encodeURIComponent(word)}`, { method: "DELETE" });
    state.prefetchCache.clear();
    await loadLexicon();
  } catch (err) {
    alert("Error deleting pronunciation: " + err.message);
  }
}

// ----------------- User Profile, Reading Memory & Notes ----------------- //

let pendingStatsWords = 0;
let pendingStatsSeconds = 0;
let statsSyncTimer = null;

function recordReadingStats(words, seconds) {
  pendingStatsWords += words;
  pendingStatsSeconds += seconds;

  if (!statsSyncTimer) {
    statsSyncTimer = setTimeout(flushReadingStats, 15000);
  }
}

async function flushReadingStats() {
  clearTimeout(statsSyncTimer);
  statsSyncTimer = null;
  if (pendingStatsWords === 0 && pendingStatsSeconds === 0) return;

  const words = pendingStatsWords;
  const seconds = pendingStatsSeconds;
  pendingStatsWords = 0;
  pendingStatsSeconds = 0;

  try {
    const res = await fetch("/api/user/stats", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        words_read: words,
        seconds_listened: seconds,
        book_id: state.currentBook?.id,
      }),
    });
    if (res.ok) {
      const updatedMem = await res.json();
      state.userMemory = updatedMem;
      updateMemoryStatsDisplay();
    }
  } catch (err) {}
}

async function fetchUserData() {
  if (navigator.onLine === false) return;
  try {
    const [userRes, usersRes, memRes] = await Promise.all([
      fetchWithTimeout("/api/user/current", {}, 1000),
      fetchWithTimeout("/api/users", {}, 1000),
      fetchWithTimeout("/api/user/memory", {}, 1000),
    ]);

    if (userRes.ok) {
      const data = await userRes.json();
      state.currentUser = data.user || data;
      if (data.memory) state.userMemory = data.memory;
      if (elements.headerUserAvatar) elements.headerUserAvatar.textContent = state.currentUser.avatar || "👤";
      if (elements.headerUserName) elements.headerUserName.textContent = state.currentUser.username || "User";
      if (state.currentUser.theme && !localStorage.getItem("kaizen_theme")) {
        applyTheme(state.currentUser.theme);
      }
    }

    if (usersRes.ok) {
      state.allUsers = await usersRes.json();
    }

    if (memRes.ok) {
      state.userMemory = await memRes.json();
      updateMemoryStatsDisplay();
    }

    await fetchNotes();
  } catch (err) {
    console.warn("Offline or unreachable user data:", err);
  }
}

async function openUserModal() {
  state.userModalOpen = true;
  if (elements.userModalBackdrop) elements.userModalBackdrop.style.display = "block";
  if (elements.userModal) elements.userModal.style.display = "flex";
  await fetchUserData();
  renderUserModal();
}

function closeUserModal() {
  state.userModalOpen = false;
  if (elements.userModalBackdrop) elements.userModalBackdrop.style.display = "none";
  if (elements.userModal) elements.userModal.style.display = "none";
  if (elements.createUserForm) elements.createUserForm.style.display = "none";
}

function toggleUserModal() {
  if (state.userModalOpen) {
    closeUserModal();
  } else {
    openUserModal();
  }
}

function renderUserModal() {
  const user = state.currentUser;
  if (!user) return;

  if (elements.modalUserAvatar) elements.modalUserAvatar.textContent = user.avatar || "👤";
  if (elements.modalUserName) elements.modalUserName.textContent = user.display_name || user.username;
  if (elements.modalUserHandle) elements.modalUserHandle.textContent = `@${user.username} · Active Profile`;

  if (elements.userSwitcherList) {
    elements.userSwitcherList.innerHTML = "";
    (state.allUsers || []).forEach((u) => {
      const chip = document.createElement("button");
      const isActive = u.id === user.id;
      chip.className = `user-chip ${isActive ? "active" : ""}`;
      chip.innerHTML = `<span>${u.avatar || "👤"}</span><span>${escapeHtml(u.username)}</span>${isActive ? '<span style="font-size:0.65rem; opacity:0.8;">(Active)</span>' : ""}`;
      chip.onclick = () => switchUser(u.id);
      elements.userSwitcherList.appendChild(chip);
    });
  }

  updateMemoryStatsDisplay();
  renderNotesList();
}

function updateMemoryStatsDisplay() {
  const mem = state.userMemory;
  if (!mem) return;

  if (elements.statReadingStreak) {
    elements.statReadingStreak.textContent = `${mem.reading_streak_days || 1} day${(mem.reading_streak_days || 1) === 1 ? "" : "s"}`;
  }
  if (elements.statWordsRead) {
    elements.statWordsRead.textContent = (mem.total_words_read || 0).toLocaleString();
  }
  if (elements.statListenTime) {
    const mins = Math.round((mem.total_seconds_listened || 0) / 60);
    elements.statListenTime.textContent = mins >= 60 ? `${(mins / 60).toFixed(1)}h` : `${mins}m`;
  }
  if (elements.statBooksCount) {
    const count = (mem.books_started || []).length;
    elements.statBooksCount.textContent = count.toString();
  }
}

async function switchUser(userId) {
  if (state.currentUser?.id === userId) return;
  try {
    const res = await fetch("/api/user/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
    });
    if (res.ok) {
      pauseAudio();
      state.prefetchCache.clear();
      await fetchUserData();
      await fetchServerState();
      await loadLibrary();
      renderUserModal();
    }
  } catch (err) {
    alert("Error switching profile: " + err.message);
  }
}

function toggleCreateUserForm(show) {
  if (!elements.createUserForm) return;
  const isCurrentlyShown = elements.createUserForm.style.display !== "none";
  const target = typeof show === "boolean" ? show : !isCurrentlyShown;
  elements.createUserForm.style.display = target ? "block" : "none";
  if (target && elements.newUsernameInput) {
    elements.newUsernameInput.value = "";
    elements.newUsernameInput.focus();
  }
}

async function submitCreateUser() {
  const username = elements.newUsernameInput?.value.trim();
  const avatar = elements.newUserAvatarSelect?.value || "👤";
  if (!username) {
    alert("Please enter a username or display name.");
    return;
  }

  try {
    const res = await fetch("/api/user/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, avatar, voice: state.voice, speed: state.speed, theme: state.theme }),
    });
    if (res.ok) {
      toggleCreateUserForm(false);
      await fetchUserData();
      await fetchServerState();
      await loadLibrary();
      renderUserModal();
    }
  } catch (err) {
    alert("Error creating user: " + err.message);
  }
}

async function handleClearMemory() {
  if (elements.clearMemoryBtn) {
    elements.clearMemoryBtn.disabled = true;
    elements.clearMemoryBtn.style.opacity = "0.6";
  }
  if (elements.cacheStatusText) elements.cacheStatusText.textContent = "Clearing...";

  try {
    const res = await fetch("/api/memory/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clear_ast: false }),
    });
    const data = await res.json();
    state.prefetchCache.clear();

    if (elements.clearMemoryFeedback) {
      elements.clearMemoryFeedback.style.display = "inline";
      elements.clearMemoryFeedback.textContent = `✓ Cleared ${data.audio_cache_files_cleared || 0} audio caches & freed RAM!`;
      setTimeout(() => {
        if (elements.clearMemoryFeedback) elements.clearMemoryFeedback.style.display = "none";
      }, 4000);
    }
    if (elements.cacheStatusText) elements.cacheStatusText.textContent = "Cache Cleared";
  } catch (err) {
    alert("Error clearing memory: " + err.message);
  } finally {
    if (elements.clearMemoryBtn) {
      elements.clearMemoryBtn.disabled = false;
      elements.clearMemoryBtn.style.opacity = "1";
    }
  }
}

async function fetchNotes() {
  try {
    const bookParam = state.currentBook ? `?book_id=${state.currentBook.id}` : "";
    const res = await fetch(`/api/notes${bookParam}`);
    if (res.ok) {
      state.userNotes = await res.json();
      renderNotesList();
    }
  } catch (err) {}
}

function renderNotesList() {
  if (!elements.userNotesList) return;
  elements.userNotesList.innerHTML = "";
  if (!state.userNotes || state.userNotes.length === 0) {
    elements.userNotesList.innerHTML = `
      <div style="font-size:0.75rem; color:var(--text-muted); text-align:center; padding:0.75rem;">
        No notes recorded yet. Add quick thoughts or annotations while listening!
      </div>
    `;
    return;
  }

  state.userNotes.forEach((n) => {
    const card = document.createElement("div");
    card.className = "user-note-card";
    const dateStr = new Date(n.created_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    card.innerHTML = `
      <div class="user-note-card-top">
        <span>Ch ${n.chapter_index + 1} · Sentence ${n.sentence_index + 1} (${dateStr})</span>
        <button class="user-note-del-btn" title="Delete note">&times;</button>
      </div>
      <div style="font-style:italic; font-size:0.75rem; color:var(--text-muted); line-height:1.3;">
        "${escapeHtml(n.sentence_text ? (n.sentence_text.slice(0, 70) + (n.sentence_text.length > 70 ? '...' : '')) : '')}"
      </div>
      <div style="font-weight:600; color:var(--text-main); margin-top:0.15rem;">
        ${escapeHtml(n.note_text)}
      </div>
    `;
    const del = card.querySelector(".user-note-del-btn");
    if (del) {
      del.onclick = async () => {
        await deleteNote(n.id);
      };
    }
    elements.userNotesList.appendChild(card);
  });
}

async function handleAddNote() {
  const noteText = elements.quickNoteInput?.value.trim();
  if (!noteText) return;

  const currentSentence = state.sentencesInChapter[state.currentSentenceIndex];
  const payload = {
    book_id: state.currentBook ? state.currentBook.id : "scratchpad",
    chapter_index: state.currentChapterIndex,
    sentence_index: state.currentSentenceIndex,
    sentence_text: currentSentence ? currentSentence.text : "",
    note_text: noteText,
  };

  try {
    const res = await fetch("/api/notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      elements.quickNoteInput.value = "";
      await fetchNotes();
    }
  } catch (err) {
    alert("Error saving note: " + err.message);
  }
}

async function deleteNote(noteId) {
  try {
    const res = await fetch(`/api/notes/${noteId}`, { method: "DELETE" });
    if (res.ok) {
      await fetchNotes();
    }
  } catch (err) {}
}


// ----------------- Settings & Voices ----------------- //

function loadSavedSettings() {
  const savedVoice = localStorage.getItem("kaizen_voice");
  if (savedVoice) state.voice = savedVoice;

  const savedSpeed = localStorage.getItem("kaizen_speed");
  if (savedSpeed) {
    state.speed = parseFloat(savedSpeed);
    elements.speedSelect.value = savedSpeed;
  }

  const savedTheme = localStorage.getItem("kaizen_theme") || "sepia";
  applyTheme(savedTheme);

  const savedFontSize = localStorage.getItem("kaizen_font_size");
  if (savedFontSize) {
    state.fontSize = parseInt(savedFontSize, 10);
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
  if (navigator.onLine === false) return;
  try {
    const res = await fetchWithTimeout("/api/status", {}, 1000);
    if (res.ok) {
      const data = await res.json();
      if (data.companion_url && elements.mobileUrlText) {
        elements.mobileUrlText.textContent = data.companion_url.replace("http://", "");
        elements.mobileBadge.onclick = () => {
          navigator.clipboard?.writeText(data.companion_url);
          elements.mobileUrlText.textContent = "Copied!";
          setTimeout(() => {
            elements.mobileUrlText.textContent = data.companion_url.replace("http://", "");
          }, 2000);
        };
      }
    }

    const voiceRes = await fetchWithTimeout("/api/voices", {}, 1000);
    if (voiceRes.ok) {
      const voices = await voiceRes.json();
      populateVoiceSelect(voices);
    }
  } catch (err) {
    console.warn("Failed to load status/voices (offline):", err);
  }
}

function populateVoiceSelect(voices) {
  elements.voiceSelect.innerHTML = "";
  const groups = {};
  voices.forEach((v) => {
    if (!groups[v.category]) groups[v.category] = [];
    groups[v.category].push(v);
  });

  for (const [catName, list] of Object.entries(groups)) {
    const optgroup = document.createElement("optgroup");
    optgroup.label = catName;
    list.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v.id;
      opt.textContent = v.name;
      if (v.id === state.voice) opt.selected = true;
      optgroup.appendChild(opt);
    });
    elements.voiceSelect.appendChild(optgroup);
  }
}

// ----------------- Library & Rendering ----------------- //

let libraryRetryCount = 0;
async function loadLibrary() {
  try {
    const res = await fetch("/api/library");
    const books = await res.json();
    state.libraryBooks = books;
    renderLibraryList(books);

    const userBooks = books.filter((b) => !b.is_sample);
    const sampleBooks = books.filter((b) => b.is_sample);

    // Prioritize active reading book and uploaded user books:
    let targetBook = null;
    const serverBookId = state.serverLastBookId;
    const localBookId = localStorage.getItem("kaizen_book_id");

    if (serverBookId && books.some((b) => b.id === serverBookId)) {
      targetBook = books.find((b) => b.id === serverBookId);
    } else if (localBookId && books.some((b) => b.id === localBookId)) {
      const localBook = books.find((b) => b.id === localBookId);
      if (!localBook.is_sample || userBooks.length === 0) {
        targetBook = localBook;
      }
    }

    // If still no target, pick the first user book!
    if (!targetBook && userBooks.length > 0) {
      targetBook = userBooks[0];
    } else if (!targetBook && sampleBooks.length > 0) {
      targetBook = sampleBooks[0];
    }

    if (targetBook) {
      await openBook(targetBook.id);
    } else if (books.length === 0 && libraryRetryCount < 8) {
      libraryRetryCount++;
      elements.readerContent.innerHTML = `
        <div style="text-align:center; padding: 4rem 1rem;">
          <h2 style="font-family:var(--font-sans); font-size:1.2rem; margin-bottom:0.5rem;">Indexing Library...</h2>
          <p style="font-size:0.85rem; color:var(--text-muted);">Parsing documents and loading Kokoro FP16 on Apple Silicon M1...</p>
        </div>
      `;
      setTimeout(loadLibrary, 1000);
    } else {
      elements.readerContent.innerHTML = `
        <div style="text-align:center; padding: 4rem 1rem;">
          <h2 style="font-family:var(--font-sans); font-size:1.2rem; margin-bottom:0.5rem;">Library Ready</h2>
          <p style="font-size:0.85rem; color:var(--text-muted);">Drop any .epub, .pdf, .md, .docx, or .txt file to begin.</p>
        </div>
      `;
    }
  } catch (err) {
    console.error("Error loading library:", err);
  }
}

function renderLibraryList(books) {
  if (!elements.userLibraryList) return;
  elements.userLibraryList.innerHTML = "";

  const userBooks = books.filter((b) => !b.is_sample);
  const sampleBooks = books.filter((b) => b.is_sample);

  if (elements.userBooksCount) {
    elements.userBooksCount.textContent = `${userBooks.length} book${userBooks.length === 1 ? "" : "s"}`;
  }

  // Render User Books
  if (userBooks.length === 0) {
    elements.userLibraryList.innerHTML = `
      <div class="library-empty-state">
        <p><strong>Your library is empty.</strong></p>
        <p style="margin-top:0.25rem;">Drop any .epub, .pdf, .md, or .docx file above to add books and track your reading.</p>
      </div>
    `;
  } else {
    userBooks.forEach((b) => {
      const card = createLibraryCard(b);
      elements.userLibraryList.appendChild(card);
    });
  }

  // Render Sample / Demo Books
  if (elements.sampleBooksSection && elements.sampleLibraryList) {
    if (sampleBooks.length > 0) {
      elements.sampleBooksSection.style.display = "block";
      elements.sampleLibraryList.innerHTML = "";
      sampleBooks.forEach((b) => {
        const card = createLibraryCard(b);
        elements.sampleLibraryList.appendChild(card);
      });

      // Expand samples only if user library is empty, otherwise keep collapsed
      const shouldShowSamples = userBooks.length === 0;
      elements.sampleLibraryList.style.display = shouldShowSamples ? "block" : "none";
      if (elements.sampleToggleChevron) {
        elements.sampleToggleChevron.textContent = shouldShowSamples ? "▴" : "▾";
      }

      elements.sampleBooksToggle.onclick = () => {
        const isHidden = elements.sampleLibraryList.style.display === "none";
        elements.sampleLibraryList.style.display = isHidden ? "block" : "none";
        if (elements.sampleToggleChevron) {
          elements.sampleToggleChevron.textContent = isHidden ? "▴" : "▾";
        }
      };
    } else {
      elements.sampleBooksSection.style.display = "none";
    }
  }
}

function createLibraryCard(b) {
  const card = document.createElement("div");
  const isActive = state.currentBook?.id === b.id;
  card.className = `library-card ${isActive ? "active" : ""}`;

  const pct = b.progress_pct || 0;
  const progressHtml = pct > 0
    ? `
      <div style="font-size:0.7rem; color:var(--accent-color); font-weight:600; margin-top:0.15rem;">
        Ch ${(b.last_chapter_index || 0) + 1} of ${b.chapters_count} · ${pct}% read
      </div>
      <div class="library-card-progress">
        <div class="library-card-progress-fill" style="width: ${pct}%;"></div>
      </div>
    `
    : "";

  const wordsFormatted = b.total_words ? `${b.total_words.toLocaleString()} words` : "";

  card.innerHTML = `
    <div class="library-card-top">
      <span class="library-card-title">${escapeHtml(b.title)}</span>
      ${
        !b.is_sample
          ? `<button class="library-card-delete" title="Remove from library">&times;</button>`
          : `<span class="library-card-format" style="opacity:0.6;">DEMO</span>`
      }
    </div>
    <div class="library-card-meta">
      <span class="library-card-format">${b.file_format}</span>
      <span>${b.chapters_count} chapters ${wordsFormatted ? `· ${wordsFormatted}` : ""}</span>
    </div>
    ${progressHtml}
  `;

  card.onclick = (e) => {
    if (e.target.classList.contains("library-card-delete")) return;
    openBook(b.id);
    closeDrawer();
  };

  const delBtn = card.querySelector(".library-card-delete");
  if (delBtn) {
    delBtn.onclick = async (e) => {
      e.stopPropagation();
      await deleteBook(b.id, b.title);
    };
  }

  return card;
}

async function deleteBook(bookId, bookTitle) {
  if (!confirm(`Are you sure you want to remove "${bookTitle || "this book"}" from your library?`)) return;
  try {
    const res = await fetch(`/api/book/${bookId}`, { method: "DELETE" });
    const data = await res.json();
    if (data.success) {
      if (state.currentBook?.id === bookId) {
        state.currentBook = null;
        localStorage.removeItem("kaizen_book_id");
      }
      await loadLibrary();
    }
  } catch (err) {
    alert("Error removing book: " + err.message);
  }
}

async function openBook(bookId) {
  try {
    const res = await fetch(`/api/book/${bookId}`);
    const book = await res.json();
    state.currentBook = book;
    localStorage.setItem("kaizen_book_id", bookId);

    if (elements.bookTitle) {
      elements.bookTitle.textContent = book.title;
    }
    document.title = `${book.title} — KaizenReader`;
    if (elements.spineBookTitle) {
      elements.spineBookTitle.textContent = book.title;
    }

    computeAllChaptersMetadata(book);
    renderTOC(book.chapters);
    renderQuickNavHUD();
    renderZenRail();
    if (state.libraryBooks) {
      renderLibraryList(state.libraryBooks);
    }

    // Determine saved position: server state is canonical!
    const serverPos = state.serverPositions ? state.serverPositions[bookId] : null;
    let savedChapter = 0;
    let savedSentence = 0;

    if (serverPos && typeof serverPos.chapter_index === "number") {
      savedChapter = serverPos.chapter_index;
      savedSentence = serverPos.sentence_index || 0;
    } else {
      const localChap = localStorage.getItem(`kaizen_chap_${bookId}`);
      const localSent = localStorage.getItem(`kaizen_sent_${bookId}`);
      if (localChap !== null) savedChapter = parseInt(localChap, 10) || 0;
      if (localSent !== null) savedSentence = parseInt(localSent, 10) || 0;
    }

    state.currentChapterIndex = Math.max(0, Math.min(savedChapter, book.chapters.length - 1));
    renderCurrentChapter();
    state.currentSentenceIndex = Math.max(
      0,
      Math.min(savedSentence, Math.max(0, state.sentencesInChapter.length - 1))
    );
    if (state.sentencesInChapter[state.currentSentenceIndex]) {
      highlightSentence(state.sentencesInChapter[state.currentSentenceIndex].id);
      updateProgressIndicator();
    }
    updateHeaderTOC();
  } catch (err) {
    console.error("Error opening book:", err);
  }
}

function computeAllChaptersMetadata(book) {
  if (!book || !book.chapters) return;
  state.chapterMetadata = book.chapters.map((ch, idx) => {
    let wordCount = 0;
    let sentenceCount = 0;
    const headings = [];
    let sCounter = 0;

    const isTOC = Boolean(ch.is_toc || ch.section_type === "toc" || (ch.title && /table\s+of\s+contents|contents/i.test(ch.title)));
    const isFrontMatter = Boolean(ch.is_front_matter || ch.category === "front_matter" || isTOC);
    const isBackMatter = Boolean(ch.is_back_matter || ch.category === "back_matter");

    ch.paragraphs.forEach((p) => {
      const pWords = p.text ? p.text.split(/\s+/).filter(Boolean).length : 0;
      wordCount += pWords;
      const pSentences = p.sentences ? p.sentences.length : 0;

      // Only gather genuine subheadings for non-TOC, non-titlepage chapters to avoid clutter
      if (!isTOC && ch.section_type !== "title_page" && (p.is_heading || ["h1", "h2", "h3", "h4"].includes(p.node_type))) {
        const hText = p.text.trim();
        const chTitle = (ch.title || "").trim();
        const partTitle = (ch.part_title || "").trim();
        // Skip headings that duplicate the chapter title or part title
        if (
          hText.toLowerCase() !== chTitle.toLowerCase() &&
          (!partTitle || hText.toLowerCase() !== partTitle.toLowerCase()) &&
          !chTitle.toLowerCase().startsWith(hText.toLowerCase())
        ) {
          headings.push({
            text: hText,
            nodeType: p.node_type || "h2",
            paragraphId: p.id,
            firstSentenceIndex: sCounter,
          });
        }
      }

      sCounter += pSentences;
      sentenceCount += pSentences;
    });

    const speed = state.speed || 1.0;
    const estimatedMinutes = Math.max(1, Math.round(wordCount / Math.max(1, 160 * speed)));

    let badgeLabel = ch.badge_label;
    if (!badgeLabel) {
      if (isTOC) badgeLabel = "TOC";
      else if (ch.section_type === "index" || /index/i.test(ch.title)) badgeLabel = "Index";
      else if (isFrontMatter) badgeLabel = "Front";
      else if (isBackMatter) badgeLabel = "App";
      else if (ch.chapter_number) badgeLabel = `Ch ${ch.chapter_number}`;
      else badgeLabel = `Ch ${idx + 1}`;
    }

    return {
      chapterIndex: idx,
      title: ch.title || (isTOC ? "Table of Contents" : `Chapter ${idx + 1}`),
      category: ch.category || (isTOC ? "front_matter" : (isBackMatter ? "back_matter" : "body")),
      sectionType: ch.section_type || (isTOC ? "toc" : "chapter"),
      chapterNumber: ch.chapter_number || null,
      partTitle: ch.part_title || null,
      isTOC,
      isFrontMatter,
      isBackMatter,
      badgeLabel,
      wordCount,
      sentenceCount,
      estimatedMinutes,
      headings,
    };
  });
}

function updateHeaderTOC() {
  if (!state.currentBook) return;
  const meta = state.chapterMetadata[state.currentChapterIndex];
  const bodyChapters = state.chapterMetadata.filter((m) => m.category === "body" && m.sectionType !== "part");
  const totalBody = state.currentBook.total_body_chapters || bodyChapters.length || state.currentBook.chapters.length;
  const totalCh = state.currentBook.chapters.length;
  const currentPct = state.sentencesInChapter.length > 0
    ? Math.round(((state.currentSentenceIndex + 1) / state.sentencesInChapter.length) * 100)
    : 0;

  let badgeText = `Ch ${state.currentChapterIndex + 1}`;
  if (meta) {
    if (meta.isTOC) {
      badgeText = "TOC";
    } else if (meta.sectionType === "index") {
      badgeText = "Index";
    } else if (meta.chapterNumber) {
      badgeText = `Ch ${meta.chapterNumber} of ${totalBody}`;
    } else if (meta.badgeLabel) {
      badgeText = meta.badgeLabel;
    }
  }

  if (elements.headerTocBadge) {
    elements.headerTocBadge.textContent = badgeText;
  }
  if (elements.headerTocTitle) {
    elements.headerTocTitle.textContent = meta ? meta.title : (state.currentBook.title || "Reading");
  }
  if (elements.headerTocPct) {
    elements.headerTocPct.textContent = `${currentPct}%`;
  }
  if (elements.zenTriggerBadge) {
    if (meta && meta.chapterNumber) {
      elements.zenTriggerBadge.textContent = `${meta.chapterNumber}/${totalBody}`;
    } else if (meta && meta.isTOC) {
      elements.zenTriggerBadge.textContent = "TOC";
    } else if (meta && meta.badgeLabel) {
      elements.zenTriggerBadge.textContent = meta.badgeLabel;
    } else {
      elements.zenTriggerBadge.textContent = `${state.currentChapterIndex + 1}/${totalCh}`;
    }
  }
}

function renderBookSpine() {
  if (!elements.bookSpineBar || !state.currentBook || !state.chapterMetadata.length) return;
  elements.bookSpineBar.innerHTML = "";

  const totalWords = state.chapterMetadata.reduce((acc, m) => acc + m.wordCount, 0) || 1;
  const bodyChapters = state.chapterMetadata.filter((m) => m.category === "body" && m.sectionType !== "part");
  const totalBody = state.currentBook.total_body_chapters || bodyChapters.length;

  if (elements.spineBookTitle) {
    elements.spineBookTitle.textContent = state.currentBook.title;
  }
  if (elements.spineStats) {
    const statsText = totalBody > 0 && totalBody !== state.chapterMetadata.length
      ? `${totalBody} chapters · ${state.chapterMetadata.length} sections · ${totalWords.toLocaleString()} words`
      : `${state.chapterMetadata.length} chapters · ${totalWords.toLocaleString()} words`;
    elements.spineStats.textContent = statsText;
  }

  state.chapterMetadata.forEach((meta, idx) => {
    const seg = document.createElement("div");
    seg.className = `spine-segment ${meta.category || "body"}`;
    const flexVal = Math.max(0.5, (meta.wordCount / totalWords) * 100);
    seg.style.flex = `${flexVal} 0 auto`;

    if (idx === state.currentChapterIndex) {
      seg.classList.add("active");
    } else if (idx < state.currentChapterIndex) {
      seg.classList.add("completed");
    }

    seg.onmouseenter = (e) => {
      if (!elements.spineTooltip) return;
      const rect = seg.getBoundingClientRect();
      const parentRect = elements.bookSpineBar.getBoundingClientRect();
      let label = meta.title;
      if (meta.isTOC) label = `Table of Contents`;
      else if (meta.chapterNumber) label = `Ch ${meta.chapterNumber}: ${meta.title}`;
      elements.spineTooltip.textContent = `${label} (${meta.wordCount} words · ~${meta.estimatedMinutes}m)`;
      elements.spineTooltip.style.display = "block";
      elements.spineTooltip.style.left = `${Math.max(10, Math.min(parentRect.width - 10, rect.left - parentRect.left + rect.width / 2))}px`;
    };

    seg.onmouseleave = () => {
      if (elements.spineTooltip) elements.spineTooltip.style.display = "none";
    };

    seg.onclick = (e) => {
      e.stopPropagation();
      goToChapter(idx);
      closeQuickNav();
    };

    elements.bookSpineBar.appendChild(seg);
  });
}

function renderQuickNavHUD(filter = "") {
  if (!elements.quickNavList || !state.currentBook) return;
  elements.quickNavList.innerHTML = "";
  const q = filter.trim().toLowerCase();

  renderBookSpine();

  let renderedCount = 0;
  let lastCategory = null;
  let lastPartTitle = null;

  state.chapterMetadata.forEach((meta, idx) => {
    const titleMatches = !q || meta.title.toLowerCase().includes(q);
    const matchingHeadings = q ? meta.headings.filter((h) => h.text.toLowerCase().includes(q)) : meta.headings;

    if (q && !titleMatches && matchingHeadings.length === 0) return;

    renderedCount++;

    // Render category section header if not filtering
    if (!q && meta.category !== lastCategory) {
      lastCategory = meta.category;
      const catHeader = document.createElement("div");
      catHeader.className = "quick-nav-category-header";
      let catTitle = "Main Content";
      if (meta.category === "front_matter") catTitle = "Front Matter";
      else if (meta.category === "body") catTitle = "Chapters & Sections";
      else if (meta.category === "back_matter") catTitle = "Back Matter & Index";
      catHeader.innerHTML = `<span>${catTitle}</span>`;
      elements.quickNavList.appendChild(catHeader);
    }

    if (!q && meta.partTitle && meta.partTitle !== lastPartTitle && meta.sectionType !== "part") {
      lastPartTitle = meta.partTitle;
      const partHeader = document.createElement("div");
      partHeader.className = "quick-nav-part-header";
      partHeader.innerHTML = `<span>${escapeHtml(meta.partTitle)}</span>`;
      elements.quickNavList.appendChild(partHeader);
    }

    const isCurrent = idx === state.currentChapterIndex;
    let pct = 0;
    if (idx < state.currentChapterIndex) pct = 100;
    else if (idx === state.currentChapterIndex) {
      pct = state.sentencesInChapter.length > 0
        ? Math.round(((state.currentSentenceIndex + 1) / state.sentencesInChapter.length) * 100)
        : 0;
    }

    const item = document.createElement("div");
    item.className = `quick-nav-item ${isCurrent ? "active" : ""}`;
    item.dataset.chapterIdx = idx;

    let subheadingsHtml = "";
    if (matchingHeadings.length > 0) {
      const listItems = matchingHeadings
        .map(
          (h) => `
        <div class="quick-nav-subheading-item" data-ch="${idx}" data-sent="${h.firstSentenceIndex}" data-para="${h.paragraphId}">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="9 18 15 12 9 6"></polyline>
          </svg>
          <span>${escapeHtml(h.text)}</span>
        </div>
      `
        )
        .join("");
      subheadingsHtml = `<div class="quick-nav-subheadings">${listItems}</div>`;
    }

    let badgeClass = meta.isTOC ? "toc" : (meta.sectionType === "index" ? "index" : (meta.category || "body"));

    item.innerHTML = `
      <div class="quick-nav-item-main">
        <div class="quick-nav-title-group">
          <span class="quick-nav-badge ${badgeClass}">${escapeHtml(meta.badgeLabel)}</span>
          <span class="quick-nav-item-title">${escapeHtml(meta.title)}</span>
        </div>
        <div class="quick-nav-meta">
          <span>~${meta.estimatedMinutes} min</span>
          <div class="quick-nav-ch-progress-bar">
            <div class="quick-nav-ch-progress-fill" style="width: ${pct}%;"></div>
          </div>
          <span style="font-family:var(--font-mono); font-size:0.7rem; width:28px; text-align:right;">${pct}%</span>
        </div>
      </div>
      ${subheadingsHtml}
    `;

    item.querySelector(".quick-nav-item-main").onclick = () => {
      goToChapter(idx);
      closeQuickNav();
    };

    item.querySelectorAll(".quick-nav-subheading-item").forEach((subEl) => {
      subEl.onclick = (e) => {
        e.stopPropagation();
        const chIdx = parseInt(subEl.dataset.ch, 10);
        const sentIdx = parseInt(subEl.dataset.sent, 10);
        const paraId = subEl.dataset.para;
        goToChapter(chIdx, sentIdx);
        closeQuickNav();
        setTimeout(() => {
          const targetPara = document.getElementById(`para-${paraId}`);
          if (targetPara) targetPara.scrollIntoView({ behavior: "smooth", block: "center" });
        }, 120);
      };
    });

    elements.quickNavList.appendChild(item);
  });

  if (renderedCount === 0) {
    elements.quickNavList.innerHTML = `
      <div style="text-align:center; padding:2rem 1rem; color:var(--text-muted); font-size:0.85rem;">
        No chapters or sections match "<strong>${escapeHtml(filter)}</strong>"
      </div>
    `;
  }
}

function renderZenRail(filter = "") {
  if (!elements.zenRailList || !state.currentBook) return;
  elements.zenRailList.innerHTML = "";
  const q = filter.trim().toLowerCase();

  const bodyChapters = state.chapterMetadata.filter((m) => m.category === "body" && m.sectionType !== "part");
  const totalBody = state.currentBook.total_body_chapters || bodyChapters.length;

  if (elements.zenRailCount) {
    if (totalBody > 0 && totalBody !== state.chapterMetadata.length) {
      elements.zenRailCount.textContent = `${totalBody} chapters · ${state.chapterMetadata.length} sections`;
    } else {
      elements.zenRailCount.textContent = `${state.chapterMetadata.length} chapters`;
    }
  }

  let lastCategory = null;
  let lastPartTitle = null;

  state.chapterMetadata.forEach((meta, idx) => {
    const titleMatches = !q || meta.title.toLowerCase().includes(q);
    const matchingHeadings = q ? meta.headings.filter((h) => h.text.toLowerCase().includes(q)) : meta.headings;

    if (q && !titleMatches && matchingHeadings.length === 0) return;

    // Render category section header if not filtering
    if (!q && meta.category !== lastCategory) {
      lastCategory = meta.category;
      const catHeader = document.createElement("div");
      catHeader.className = "zen-rail-category-header";
      let catTitle = "Main Content";
      if (meta.category === "front_matter") catTitle = "Front Matter";
      else if (meta.category === "body") catTitle = "Chapters & Sections";
      else if (meta.category === "back_matter") catTitle = "Back Matter & Index";
      catHeader.innerHTML = `<span>${catTitle}</span>`;
      elements.zenRailList.appendChild(catHeader);
    }

    // Render part header if new part
    if (!q && meta.partTitle && meta.partTitle !== lastPartTitle && meta.sectionType !== "part") {
      lastPartTitle = meta.partTitle;
      const partHeader = document.createElement("div");
      partHeader.className = "zen-rail-part-header";
      partHeader.innerHTML = `<span>${escapeHtml(meta.partTitle)}</span>`;
      elements.zenRailList.appendChild(partHeader);
    }

    const isCurrent = idx === state.currentChapterIndex;
    let pct = 0;
    if (idx < state.currentChapterIndex) pct = 100;
    else if (idx === state.currentChapterIndex) {
      pct = state.sentencesInChapter.length > 0
        ? Math.round(((state.currentSentenceIndex + 1) / state.sentencesInChapter.length) * 100)
        : 0;
    }

    const card = document.createElement("div");
    card.className = `zen-chapter-card ${isCurrent ? "active" : ""} ${meta.category || ""}`;
    card.id = `zen-ch-${idx}`;

    let badgeClass = "zen-badge-chap";
    if (meta.isTOC) badgeClass = "zen-badge-toc";
    else if (meta.sectionType === "index") badgeClass = "zen-badge-index";
    else if (meta.category === "front_matter") badgeClass = "zen-badge-front";
    else if (meta.category === "back_matter") badgeClass = "zen-badge-back";

    let displayTitle = meta.title;
    if (meta.isTOC) {
      displayTitle = "Table of Contents";
    }

    let subheadingsHtml = "";
    if (matchingHeadings.length > 0) {
      const listItems = matchingHeadings
        .map(
          (h) => `
        <div class="zen-subheading-item" data-ch="${idx}" data-sent="${h.firstSentenceIndex}" data-para="${h.paragraphId}">
          ${escapeHtml(h.text)}
        </div>
      `
        )
        .join("");
      subheadingsHtml = `<div class="zen-subheadings-group">${listItems}</div>`;
    }

    card.innerHTML = `
      <div class="zen-chapter-card-top">
        <div class="zen-chapter-card-title-wrap">
          <span class="zen-badge ${badgeClass}">${escapeHtml(meta.badgeLabel)}</span>
          <span class="zen-chapter-card-title" title="${escapeHtml(meta.title)}">${escapeHtml(displayTitle)}</span>
        </div>
        <span class="zen-chapter-card-pct">${pct}%</span>
      </div>
      <div class="zen-chapter-card-progress">
        <div class="zen-chapter-card-fill" style="width: ${pct}%;"></div>
      </div>
      ${subheadingsHtml}
    `;

    card.querySelector(".zen-chapter-card-top").onclick = () => {
      goToChapter(idx);
      if (!state.isTOCPinned) closeZenRail();
    };

    card.querySelectorAll(".zen-subheading-item").forEach((subEl) => {
      subEl.onclick = (e) => {
        e.stopPropagation();
        const chIdx = parseInt(subEl.dataset.ch, 10);
        const sentIdx = parseInt(subEl.dataset.sent, 10);
        const paraId = subEl.dataset.para;
        goToChapter(chIdx, sentIdx);
        if (!state.isTOCPinned) closeZenRail();
        setTimeout(() => {
          const targetPara = document.getElementById(`para-${paraId}`);
          if (targetPara) targetPara.scrollIntoView({ behavior: "smooth", block: "center" });
        }, 120);
      };
    });

    elements.zenRailList.appendChild(card);
  });
}

function openQuickNav() {
  state.quickNavOpen = true;
  state.quickNavSelectedIndex = -1;
  if (elements.headerTocPill) elements.headerTocPill.classList.add("active");
  if (elements.quickNavBackdrop) elements.quickNavBackdrop.style.display = "block";
  if (elements.quickNavHud) elements.quickNavHud.style.display = "flex";
  if (elements.quickNavInput) {
    elements.quickNavInput.value = "";
    renderQuickNavHUD("");
    setTimeout(() => elements.quickNavInput.focus(), 60);
  }
}

function closeQuickNav() {
  state.quickNavOpen = false;
  state.quickNavSelectedIndex = -1;
  if (elements.headerTocPill) elements.headerTocPill.classList.remove("active");
  if (elements.quickNavBackdrop) elements.quickNavBackdrop.style.display = "none";
  if (elements.quickNavHud) elements.quickNavHud.style.display = "none";
}

function toggleQuickNav() {
  if (state.quickNavOpen) closeQuickNav();
  else openQuickNav();
}

function openZenRail() {
  state.zenRailOpen = true;
  if (elements.zenTocRail) elements.zenTocRail.classList.add("open");
  renderZenRail(elements.zenRailFilter ? elements.zenRailFilter.value : "");
  setTimeout(() => {
    const activeCard = document.getElementById(`zen-ch-${state.currentChapterIndex}`);
    if (activeCard) activeCard.scrollIntoView({ behavior: "smooth", block: "center" });
  }, 100);
}

function closeZenRail() {
  if (state.isTOCPinned) return;
  state.zenRailOpen = false;
  if (elements.zenTocRail) elements.zenTocRail.classList.remove("open");
}

function toggleZenRailPin() {
  state.isTOCPinned = !state.isTOCPinned;
  localStorage.setItem("kaizen_toc_pinned", String(state.isTOCPinned));
  applyTOCPinState();
}

function applyTOCPinState() {
  const container = document.getElementById("app-container");
  if (state.isTOCPinned) {
    container?.classList.add("toc-pinned");
    if (elements.zenRailPinBtn) elements.zenRailPinBtn.classList.add("active");
    if (elements.zenPinLabel) elements.zenPinLabel.textContent = "Pinned";
    openZenRail();
  } else {
    container?.classList.remove("toc-pinned");
    if (elements.zenRailPinBtn) elements.zenRailPinBtn.classList.remove("active");
    if (elements.zenPinLabel) elements.zenPinLabel.textContent = "Pin";
    closeZenRail();
  }
}

function prevChapter() {
  if (state.currentChapterIndex > 0) {
    goToChapter(state.currentChapterIndex - 1, 0);
  }
}

function nextChapter() {
  if (state.currentBook && state.currentChapterIndex < state.currentBook.chapters.length - 1) {
    goToChapter(state.currentChapterIndex + 1, 0);
  }
}

let scrollDimTimer = null;
function setupZenAutoDim() {
  const readerMain = elements.readerContent?.parentElement?.parentElement || document.getElementById("reader-main");
  if (!readerMain) return;

  readerMain.addEventListener("scroll", () => {
    if (elements.zenTocTrigger) elements.zenTocTrigger.classList.add("dimmed");
    clearTimeout(scrollDimTimer);
    scrollDimTimer = setTimeout(() => {
      if (elements.zenTocTrigger) elements.zenTocTrigger.classList.remove("dimmed");
    }, 1200);
  });

  window.addEventListener("mousemove", (e) => {
    if (e.clientX < 160 && elements.zenTocTrigger) {
      elements.zenTocTrigger.classList.remove("dimmed");
    }
  });
}

function setupProgressScrubberTooltip() {
  if (!elements.progressBarContainer || !elements.progressHoverTooltip) return;

  elements.progressBarContainer.addEventListener("mousemove", (e) => {
    if (!state.sentencesInChapter || state.sentencesInChapter.length === 0) return;
    const rect = elements.progressBarContainer.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const targetIdx = Math.floor(ratio * state.sentencesInChapter.length);
    const targetSentence = state.sentencesInChapter[Math.min(targetIdx, state.sentencesInChapter.length - 1)];
    const pct = Math.round(ratio * 100);

    const snippet = targetSentence && targetSentence.text
      ? targetSentence.text.slice(0, 48) + (targetSentence.text.length > 48 ? "..." : "")
      : "";

    elements.progressHoverTooltip.textContent = `${pct}% · ${snippet}`;
    elements.progressHoverTooltip.style.display = "block";
    elements.progressHoverTooltip.style.left = `${e.clientX - rect.left}px`;
  });

  elements.progressBarContainer.addEventListener("mouseleave", () => {
    elements.progressHoverTooltip.style.display = "none";
  });
}

function renderTOC(chapters, filter = "") {
  elements.tocList.innerHTML = "";
  const q = filter.trim().toLowerCase();
  chapters.forEach((ch, idx) => {
    if (q && !ch.title.toLowerCase().includes(q)) return;
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

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function findTargetChapterForTOCLine(lineText) {
  if (!state.chapterMetadata) return -1;
  const lower = lineText.toLowerCase();

  // 1. Try matching chapter number and optional book number
  const chMatch = lower.match(/\b(?:ch(?:apter)?\.?)\s*(\d+)/);
  const bookMatch = lower.match(/\b(?:book|part)\s*(\d+)/);

  if (chMatch) {
    const cNum = parseInt(chMatch[1], 10);
    const bNum = bookMatch ? parseInt(bookMatch[1], 10) : null;
    for (let i = 0; i < state.chapterMetadata.length; i++) {
      const m = state.chapterMetadata[i];
      if (m.isTOC) continue;
      if (bNum && !m.title.toLowerCase().includes(`book ${bNum}`)) continue;
      if (m.chapterNumber === cNum || m.title.toLowerCase().includes(`chapter ${cNum}`)) {
        return i;
      }
    }
  }

  // 2. Try matching back matter keywords (e.g. "Giants", "Solomon", "Dead Sea", "Index", "References")
  for (let i = 0; i < state.chapterMetadata.length; i++) {
    const m = state.chapterMetadata[i];
    if (m.isTOC) continue;
    const mLower = m.title.toLowerCase();
    if (lower.includes("giant") && mLower.includes("giant")) return i;
    if (lower.includes("solomon") && mLower.includes("solomon")) return i;
    if (lower.includes("references") && mLower.includes("references")) return i;
    if (lower.includes("dead sea") && mLower.includes("dead sea")) return i;
    if (lower.includes("index") && mLower.includes("index")) return i;
    if (lower.includes("introduction") && mLower.includes("introduction")) return i;
  }

  return -1;
}

function renderCurrentChapter() {
  if (!state.currentBook) return;
  const chapter = state.currentBook.chapters[state.currentChapterIndex];
  if (!chapter) return;

  const meta = state.chapterMetadata[state.currentChapterIndex] || {};
  const isTOC = Boolean(meta.isTOC || chapter.is_toc || chapter.section_type === "toc");
  const isIndex = Boolean(meta.sectionType === "index" || chapter.section_type === "index");
  const bodyChapters = state.chapterMetadata.filter((m) => m.category === "body" && m.sectionType !== "part");
  const totalBody = state.currentBook.total_body_chapters || bodyChapters.length || state.currentBook.chapters.length;

  state.sentencesInChapter = [];
  let sCounter = 0;

  let headerSubtitle = escapeHtml(state.currentBook.title);
  if (meta.chapterNumber) {
    headerSubtitle += ` · Chapter ${meta.chapterNumber} of ${totalBody}`;
    if (meta.partTitle) {
      headerSubtitle += ` (${escapeHtml(meta.partTitle)})`;
    }
  } else if (isTOC) {
    headerSubtitle += ` · Table of Contents`;
  } else if (isIndex) {
    headerSubtitle += ` · Back Matter · Index`;
  } else if (meta.category === "front_matter") {
    headerSubtitle += ` · Front Matter`;
  } else if (meta.category === "back_matter") {
    headerSubtitle += ` · Back Matter`;
  } else if (meta.sectionType === "part") {
    headerSubtitle += ` · Part Overview`;
  }

  let html = `
    <div class="doc-chapter-header">
      <div class="doc-chapter-meta">${headerSubtitle}</div>
      <h1 class="doc-chapter-title">${escapeHtml(isTOC ? "Table of Contents" : chapter.title)}</h1>
    </div>
  `;

  chapter.paragraphs.forEach((p) => {
    let tagClass = "reader-paragraph";
    if (p.is_heading) tagClass = p.node_type === "h1" ? "reader-heading-1" : "reader-heading-2";
    else if (p.is_quote) tagClass = "reader-blockquote";
    else if (p.is_code) tagClass = "reader-code";

    let sentenceSpans = "";
    p.sentences.forEach((s) => {
      const idxInChapter = sCounter++;
      state.sentencesInChapter.push({
        ...s,
        nodeType: p.node_type || "p",
        chapterIndex: state.currentChapterIndex,
        indexInChapter: idxInChapter,
      });

      const words = s.text.split(/\s+/).filter(Boolean);
      const wordHtml = p.is_code
        ? escapeHtml(s.text)
        : words.map((w, wIdx) => `<span class="word-token" data-widx="${wIdx}">${escapeHtml(w)}</span>`).join(" ");

      sentenceSpans += `<span class="sentence-span" data-sidx="${idxInChapter}" id="span-${s.id}">${wordHtml} </span>`;
    });

    let jumpBtn = "";
    if (isTOC) {
      const targetCh = findTargetChapterForTOCLine(p.text);
      if (targetCh !== -1 && targetCh !== state.currentChapterIndex) {
        jumpBtn = `<button class="toc-interactive-jump" data-target-ch="${targetCh}" title="Jump directly to this chapter in the reader">Jump →</button>`;
      }
    }

    html += `<div class="${tagClass}" id="para-${p.id}">${sentenceSpans}${jumpBtn}</div>`;
  });

  elements.readerContent.innerHTML = html;

  elements.readerContent.querySelectorAll(".sentence-span").forEach((el) => {
    el.onclick = () => {
      const sel = window.getSelection();
      if (sel && sel.toString().trim().length > 0) return;
      const idx = parseInt(el.getAttribute("data-sidx"), 10);
      playSentenceAt(idx);
    };
  });

  elements.readerContent.querySelectorAll(".toc-interactive-jump").forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const targetIdx = parseInt(btn.dataset.targetCh, 10);
      if (!isNaN(targetIdx)) {
        goToChapter(targetIdx);
      }
    };
  });

  updateProgressIndicator();
  updateTOCActiveItem();
  updateHeaderTOC();
  renderBookSpine();
}

function updateTOCActiveItem() {
  const items = elements.tocList.querySelectorAll(".toc-item");
  items.forEach((item, idx) => {
    if (idx === state.currentChapterIndex) item.classList.add("active");
    else item.classList.remove("active");
  });
  const zenCards = document.querySelectorAll(".zen-chapter-card");
  zenCards.forEach((card, idx) => {
    if (idx === state.currentChapterIndex) card.classList.add("active");
    else card.classList.remove("active");
  });
  const quickItems = document.querySelectorAll(".quick-nav-item");
  quickItems.forEach((qi) => {
    const chIdx = parseInt(qi.dataset.chapterIdx, 10);
    if (chIdx === state.currentChapterIndex) qi.classList.add("active");
    else qi.classList.remove("active");
  });
}

function goToChapter(chapterIndex, sentenceIndex = 0) {
  if (!state.currentBook) return;
  pauseAudio();
  state.currentChapterIndex = Math.max(0, Math.min(chapterIndex, state.currentBook.chapters.length - 1));
  state.currentSentenceIndex = sentenceIndex;
  renderCurrentChapter();
  persistReadingState();
  if (state.sentencesInChapter[state.currentSentenceIndex]) {
    highlightSentence(state.sentencesInChapter[state.currentSentenceIndex].id);
  }
}

// ----------------- Gapless Web Audio Playback ----------------- //

function stopCurrentSource() {
  if (state.rafId) {
    cancelAnimationFrame(state.rafId);
    state.rafId = null;
  }
  if (state.currentSource) {
    try {
      state.currentSource.onended = null;
      state.currentSource.stop();
    } catch (e) {}
    state.currentSource = null;
  }
  document.querySelectorAll(".word-token.active-word").forEach((el) => {
    el.classList.remove("active-word");
  });
}

function togglePlay() {
  primeAudioEnginesOnGesture();
  if (state.isPlaying) pauseAudio();
  else playSentenceAt(state.currentSentenceIndex);
}

function pauseAudio() {
  state.playToken++;
  state.isPlaying = false;
  stopCurrentSource();
  elements.playIcon.style.display = "block";
  elements.pauseIcon.style.display = "none";
  if ("mediaSession" in navigator) navigator.mediaSession.playbackState = "paused";
}

function prefetchKey(s) {
  return `${state.voice}|${state.speed}|${s.id}|${s.text}`;
}

function fetchSentenceAudio(sentence) {
  const key = prefetchKey(sentence);
  if (state.prefetchCache.has(key)) {
    return state.prefetchCache.get(key);
  }
  const ctx = ensureAudioContext();
  const modelSpeed = Math.min(2.0, state.speed);
  const url = `/api/tts/sentence?text=${encodeURIComponent(sentence.text)}&voice=${encodeURIComponent(state.voice)}&speed=${modelSpeed}&sentence_id=${encodeURIComponent(sentence.id)}&node_type=${encodeURIComponent(sentence.nodeType || "p")}`;

  const promise = fetch(url)
    .then(async (res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      let timings = [];
      try {
        timings = JSON.parse(res.headers.get("X-Word-Timings") || "[]");
      } catch (e) {}
      const arr = await res.arrayBuffer();
      const buffer = await ctx.decodeAudioData(arr);
      return { buffer, timings, duration: buffer.duration };
    })
    .catch((err) => {
      state.prefetchCache.delete(key);
      throw err;
    });

  state.prefetchCache.set(key, promise);
  if (state.prefetchCache.size > 12) {
    const oldest = state.prefetchCache.keys().next().value;
    state.prefetchCache.delete(oldest);
  }
  return promise;
}

async function playSentenceAt(index) {
  if (!state.sentencesInChapter || state.sentencesInChapter.length === 0) return;

  if (index >= state.sentencesInChapter.length) {
    if (state.currentChapterIndex < state.currentBook.chapters.length - 1) {
      goToChapter(state.currentChapterIndex + 1, 0);
      playSentenceAt(0);
    } else {
      pauseAudio();
    }
    return;
  }
  if (index < 0) index = 0;

  const myToken = ++state.playToken;
  stopCurrentSource();
  ensureAudioContext();

  state.currentSentenceIndex = index;
  state.isPlaying = true;
  elements.playIcon.style.display = "none";
  elements.pauseIcon.style.display = "block";
  if ("mediaSession" in navigator) {
    navigator.mediaSession.playbackState = "playing";
    updateMediaSessionMetadata();
  }

  const currentSentence = state.sentencesInChapter[index];
  highlightSentence(currentSentence.id);
  updateProgressIndicator();
  persistReadingState();

  if (currentSentence.skip_tts || !currentSentence.text.trim()) {
    setTimeout(() => {
      if (state.isPlaying && state.playToken === myToken) {
        playSentenceAt(index + 1);
      }
    }, 300);
    return;
  }

  // Trigger server lookahead & browser buffer prefetch immediately
  triggerLookahead(index + 1);
  if (index + 1 < state.sentencesInChapter.length && !state.sentencesInChapter[index + 1].skip_tts) {
    fetchSentenceAudio(state.sentencesInChapter[index + 1]).catch(() => {});
  }

  try {
    const { buffer, timings } = await fetchSentenceAudio(currentSentence);
    if (!state.isPlaying || state.playToken !== myToken) return;

    const ctx = state.audioCtx;
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    const rate = state.speed > 2.0 ? state.speed / 2.0 : 1.0;
    src.playbackRate.value = rate;
    src.connect(ctx.destination);

    state.currentSource = src;
    state.playbackRate = rate;
    state.playStartTime = ctx.currentTime;
    state.activeTimings = timings;

    src.onended = () => {
      // Record reading stats for user memory bank
      const wordsInSentence = currentSentence.text ? currentSentence.text.split(/\s+/).filter(Boolean).length : 0;
      const durationSeconds = buffer.duration / rate;
      recordReadingStats(wordsInSentence, durationSeconds);

      if (state.isPlaying && state.playToken === myToken) {
        playSentenceAt(index + 1);
      }
    };

    src.start(0);
    startWordSyncLoop(currentSentence.id, myToken);
    broadcastPosition(currentSentence.id);
  } catch (err) {
    console.warn("Playback error, advancing:", err);
    if (state.isPlaying && state.playToken === myToken) {
      playSentenceAt(index + 1);
    }
  }
}

function startWordSyncLoop(sentenceId, myToken) {
  const span = document.getElementById(`span-${sentenceId}`);
  if (!span || !state.activeTimings || state.activeTimings.length === 0) return;

  const wordEls = span.querySelectorAll(".word-token");
  let lastWordIdx = -1;

  function tick() {
    if (!state.isPlaying || state.playToken !== myToken) return;
    const elapsed = (state.audioCtx.currentTime - state.playStartTime) * state.playbackRate;

    let activeIdx = -1;
    for (let i = 0; i < state.activeTimings.length; i++) {
      const t = state.activeTimings[i];
      if (elapsed >= t.s && elapsed <= t.e + 0.08) {
        activeIdx = t.i;
        break;
      }
    }

    if (activeIdx !== lastWordIdx) {
      if (lastWordIdx >= 0 && wordEls[lastWordIdx]) {
        wordEls[lastWordIdx].classList.remove("active-word");
      }
      if (activeIdx >= 0 && wordEls[activeIdx]) {
        wordEls[activeIdx].classList.add("active-word");
      }
      lastWordIdx = activeIdx;
    }
    state.rafId = requestAnimationFrame(tick);
  }

  state.rafId = requestAnimationFrame(tick);
}

function highlightSentence(sentenceId) {
  document.querySelectorAll(".sentence-span.active-sentence").forEach((el) => {
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

  // Estimate remaining chapter time (~160 WPM at 1.0x)
  if (total > 0 && elements.etaIndicator) {
    let remainingWords = 0;
    for (let i = state.currentSentenceIndex; i < total; i++) {
      remainingWords += state.sentencesInChapter[i].text.split(/\s+/).length;
    }
    const mins = Math.max(1, Math.round(remainingWords / (165 * state.speed)));
    elements.etaIndicator.textContent = `· ~${mins}m left`;
  }

  const pct = total > 0 ? (current / total) * 100 : 0;
  elements.progressBarFill.style.width = `${pct}%`;
  updateHeaderTOC();
}

function triggerLookahead(startIndex) {
  const lookaheadItems = [];
  const modelSpeed = Math.min(2.0, state.speed);
  for (let i = startIndex; i < Math.min(startIndex + 4, state.sentencesInChapter.length); i++) {
    const s = state.sentencesInChapter[i];
    if (!s.skip_tts && s.text.trim()) {
      lookaheadItems.push({
        text: s.text,
        voice: state.voice,
        speed: modelSpeed,
        node_type: s.nodeType || "p",
      });
    }
  }

  if (lookaheadItems.length > 0) {
    fetch("/api/tts/lookahead", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: lookaheadItems }),
    }).catch(() => {});
  }
}

// ----------------- Media Session & WebSocket ----------------- //

function setupMediaSession() {
  if (!("mediaSession" in navigator)) return;
  navigator.mediaSession.setActionHandler("play", () => togglePlay());
  navigator.mediaSession.setActionHandler("pause", () => pauseAudio());
  navigator.mediaSession.setActionHandler("previoustrack", () => playSentenceAt(state.currentSentenceIndex - 1));
  navigator.mediaSession.setActionHandler("nexttrack", () => playSentenceAt(state.currentSentenceIndex + 1));
}

function updateMediaSessionMetadata() {
  if (!("mediaSession" in navigator) || !state.currentBook) return;
  const ch = state.currentBook.chapters[state.currentChapterIndex];
  navigator.mediaSession.metadata = new MediaMetadata({
    title: ch ? ch.title : state.currentBook.title,
    artist: state.currentBook.author || "KaizenReader",
    album: state.currentBook.title,
  });
}

function connectWebSocket() {
  if (navigator.onLine === false) return;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${proto}//${window.location.host}/ws/sync`;
  try {
    state.ws = new WebSocket(wsUrl);
    state.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "remote_sync") {
          if (msg.book_id === state.currentBook?.id && msg.chapter_id === `ch_${state.currentChapterIndex}`) {
            const idx = state.sentencesInChapter.findIndex((s) => s.id === msg.sentence_id);
            if (idx !== -1 && idx !== state.currentSentenceIndex) {
              if (msg.is_playing) playSentenceAt(idx);
              else {
                state.currentSentenceIndex = idx;
                highlightSentence(msg.sentence_id);
                updateProgressIndicator();
              }
            }
          }
        }
      } catch (err) {}
    };
  } catch (err) {}
}

function broadcastPosition(sentenceId) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify({
      action: "sync_position",
      book_id: state.currentBook?.id,
      chapter_id: `ch_${state.currentChapterIndex}`,
      sentence_id: sentenceId,
      is_playing: state.isPlaying,
    }));
  }
}

// ----------------- Search & Selection Popover ----------------- //

async function runBookSearch() {
  const q = elements.bookSearchInput.value.trim();
  if (!state.currentBook || q.length < 2) {
    elements.bookSearchResults.innerHTML = "";
    return;
  }
  try {
    const res = await fetch(`/api/book/${state.currentBook.id}/search?q=${encodeURIComponent(q)}`);
    const matches = await res.json();
    elements.bookSearchResults.innerHTML = "";
    if (matches.length === 0) {
      elements.bookSearchResults.innerHTML = `<div style="font-size:0.8rem; color:var(--text-muted); padding:0.4rem;">No matches found.</div>`;
      return;
    }
    matches.forEach((m) => {
      const div = document.createElement("div");
      div.className = "search-result-item";
      div.innerHTML = `<div style="font-weight:600; font-size:0.72rem; color:var(--accent-color);">${escapeHtml(m.chapter_title)}</div><div>${escapeHtml(m.text)}</div>`;
      div.onclick = () => {
        if (state.currentChapterIndex !== m.chapter_index) {
          goToChapter(m.chapter_index, m.sentence_index);
        }
        elements.searchBarPanel.style.display = "none";
        playSentenceAt(m.sentence_index);
      };
      elements.bookSearchResults.appendChild(div);
    });
  } catch (err) {}
}

// ----------------- Event Handlers & Shortcuts ----------------- //

function setupEventListeners() {
  elements.playPauseBtn.onclick = togglePlay;
  elements.prevBtn.onclick = () => playSentenceAt(state.currentSentenceIndex - 1);
  elements.nextBtn.onclick = () => playSentenceAt(state.currentSentenceIndex + 1);

  elements.voiceSelect.onchange = (e) => {
    state.voice = e.target.value;
    state.prefetchCache.clear();
    localStorage.setItem("kaizen_voice", state.voice);
    if (state.isPlaying) playSentenceAt(state.currentSentenceIndex);
  };

  elements.speedSelect.onchange = (e) => {
    state.speed = parseFloat(e.target.value);
    state.prefetchCache.clear();
    localStorage.setItem("kaizen_speed", state.speed);
    updateProgressIndicator();
    if (state.isPlaying) playSentenceAt(state.currentSentenceIndex);
  };

  elements.themeSelect.onchange = (e) => applyTheme(e.target.value);

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

  elements.toggleDrawerBtn.onclick = openDrawer;
  elements.closeDrawerBtn.onclick = closeDrawer;
  elements.drawerOverlay.onclick = (e) => {
    if (e.target === elements.drawerOverlay) closeDrawer();
  };

  if (elements.tocFilterInput) {
    elements.tocFilterInput.oninput = (e) => {
      if (state.currentBook) renderTOC(state.currentBook.chapters, e.target.value);
    };
  }

  elements.progressBarContainer.onclick = (e) => {
    const rect = elements.progressBarContainer.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const targetIdx = Math.floor(ratio * state.sentencesInChapter.length);
    playSentenceAt(targetIdx);
  };

  elements.dropzone.onclick = () => elements.fileInput.click();
  elements.fileInput.onchange = (e) => {
    if (e.target.files.length > 0) uploadFile(e.target.files[0]);
  };

  if (elements.lexAddBtn) {
    elements.lexAddBtn.onclick = saveLexiconWord;
    elements.lexPhoneticInput.onkeydown = (e) => {
      if (e.key === "Enter") saveLexiconWord();
    };
  }
  if (elements.lexTestBtn) {
    elements.lexTestBtn.onclick = testLexiconWord;
  }

  // Header Chapter Pill & Quick-Nav
  if (elements.headerTocPill) {
    elements.headerTocPill.onclick = toggleQuickNav;
  }
  if (elements.quickNavBackdrop) {
    elements.quickNavBackdrop.onclick = closeQuickNav;
  }
  if (elements.quickNavInput) {
    elements.quickNavInput.oninput = (e) => {
      renderQuickNavHUD(e.target.value);
    };
    elements.quickNavInput.onkeydown = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        closeQuickNav();
        return;
      }
      const items = elements.quickNavList ? elements.quickNavList.querySelectorAll(".quick-nav-item") : [];
      if (!items.length) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        state.quickNavSelectedIndex = Math.min(state.quickNavSelectedIndex + 1, items.length - 1);
        items.forEach((it, idx) => {
          if (idx === state.quickNavSelectedIndex) {
            it.classList.add("keyboard-selected");
            it.scrollIntoView({ behavior: "smooth", block: "nearest" });
          } else {
            it.classList.remove("keyboard-selected");
          }
        });
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        state.quickNavSelectedIndex = Math.max(state.quickNavSelectedIndex - 1, 0);
        items.forEach((it, idx) => {
          if (idx === state.quickNavSelectedIndex) {
            it.classList.add("keyboard-selected");
            it.scrollIntoView({ behavior: "smooth", block: "nearest" });
          } else {
            it.classList.remove("keyboard-selected");
          }
        });
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (state.quickNavSelectedIndex >= 0 && items[state.quickNavSelectedIndex]) {
          const mainPart = items[state.quickNavSelectedIndex].querySelector(".quick-nav-item-main");
          if (mainPart) mainPart.click();
        } else if (items.length > 0) {
          const mainPart = items[0].querySelector(".quick-nav-item-main");
          if (mainPart) mainPart.click();
        }
      }
    };
  }
  if (elements.quickNavJumpCurrentBtn) {
    elements.quickNavJumpCurrentBtn.onclick = () => {
      closeQuickNav();
      const currentSentence = state.sentencesInChapter[state.currentSentenceIndex];
      if (currentSentence) {
        highlightSentence(currentSentence.id);
      }
    };
  }

  // Zen Edge Rail
  if (elements.zenTocTrigger) {
    elements.zenTocTrigger.onclick = openZenRail;
  }
  if (elements.zenRailPinBtn) {
    elements.zenRailPinBtn.onclick = toggleZenRailPin;
  }
  if (elements.zenRailCloseBtn) {
    elements.zenRailCloseBtn.onclick = closeZenRail;
  }
  if (elements.zenRailFilter) {
    elements.zenRailFilter.oninput = (e) => {
      renderZenRail(e.target.value);
    };
  }
  if (elements.zenCurrentLocationBtn) {
    elements.zenCurrentLocationBtn.onclick = () => {
      if (!state.isTOCPinned) closeZenRail();
      const currentSentence = state.sentencesInChapter[state.currentSentenceIndex];
      if (currentSentence) {
        highlightSentence(currentSentence.id);
      }
    };
  }

  // Chapter steppers in bottom player bar
  if (elements.prevChapterBtn) {
    elements.prevChapterBtn.onclick = prevChapter;
  }
  if (elements.nextChapterBtn) {
    elements.nextChapterBtn.onclick = nextChapter;
  }

  // User Profile, Memory & Cache Modal Listeners
  if (elements.userProfileBtn) {
    elements.userProfileBtn.onclick = toggleUserModal;
  }
  if (elements.closeUserModalBtn) {
    elements.closeUserModalBtn.onclick = closeUserModal;
  }
  if (elements.userModalBackdrop) {
    elements.userModalBackdrop.onclick = closeUserModal;
  }
  if (elements.addUserToggleBtn) {
    elements.addUserToggleBtn.onclick = () => toggleCreateUserForm();
  }
  if (elements.cancelCreateUserBtn) {
    elements.cancelCreateUserBtn.onclick = () => toggleCreateUserForm(false);
  }
  if (elements.saveCreateUserBtn) {
    elements.saveCreateUserBtn.onclick = submitCreateUser;
  }
  if (elements.clearMemoryBtn) {
    elements.clearMemoryBtn.onclick = handleClearMemory;
  }
  if (elements.addQuickNoteBtn) {
    elements.addQuickNoteBtn.onclick = handleAddNote;
  }
  if (elements.quickNoteInput) {
    elements.quickNoteInput.onkeydown = (e) => {
      if (e.key === "Enter") handleAddNote();
    };
  }

  if (elements.searchToggleBtn) {
    elements.searchToggleBtn.onclick = () => {
      const visible = elements.searchBarPanel.style.display !== "none";
      elements.searchBarPanel.style.display = visible ? "none" : "flex";
      if (!visible) elements.bookSearchInput.focus();
    };
  }
  if (elements.bookSearchClose) {
    elements.bookSearchClose.onclick = () => {
      elements.searchBarPanel.style.display = "none";
    };
  }
  if (elements.bookSearchInput) {
    let searchTimer = null;
    elements.bookSearchInput.oninput = () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(runBookSearch, 200);
    };
  }

  // Selection-to-Lexicon floating button
  document.addEventListener("mouseup", (e) => {
    if (e.target === elements.teachSelectionBtn) return;
    const sel = window.getSelection();
    const text = sel ? sel.toString().trim() : "";
    if (text && text.length >= 2 && text.length <= 36 && !text.includes("\n") && elements.readerContent.contains(sel.anchorNode)) {
      const rect = sel.getRangeAt(0).getBoundingClientRect();
      elements.teachSelectionBtn.style.left = `${Math.max(12, rect.left)}px`;
      elements.teachSelectionBtn.style.top = `${Math.max(60, rect.top - 34)}px`;
      elements.teachSelectionBtn.style.display = "block";
      elements.teachSelectionBtn.onclick = () => {
        elements.teachSelectionBtn.style.display = "none";
        elements.lexWordInput.value = text.replace(/^[.,!?;:"'()]+|[.,!?;:"'()]+$/g, "");
        openDrawer();
        setTimeout(() => elements.lexPhoneticInput.focus(), 150);
      };
    } else {
      elements.teachSelectionBtn.style.display = "none";
    }
  });

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
    if (e.dataTransfer.files.length > 0) uploadFile(e.dataTransfer.files[0]);
  });

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (state.userModalOpen) {
        e.preventDefault();
        closeUserModal();
        return;
      }
      if (state.quickNavOpen) {
        e.preventDefault();
        closeQuickNav();
        return;
      }
      if (state.zenRailOpen && !state.isTOCPinned) {
        e.preventDefault();
        closeZenRail();
        return;
      }
      if (elements.searchBarPanel && elements.searchBarPanel.style.display !== "none") {
        e.preventDefault();
        elements.searchBarPanel.style.display = "none";
        return;
      }
    }

    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") {
      e.preventDefault();
      toggleQuickNav();
      return;
    }

    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "f") {
      e.preventDefault();
      elements.searchBarPanel.style.display = "flex";
      elements.bookSearchInput.focus();
      return;
    }

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
    } else if (e.code === "BracketLeft" || e.key === "[") {
      e.preventDefault();
      prevChapter();
    } else if (e.code === "BracketRight" || e.key === "]") {
      e.preventDefault();
      nextChapter();
    } else if (e.code === "ArrowUp") {
      e.preventDefault();
      adjustSpeed(0.25);
    } else if (e.code === "ArrowDown") {
      e.preventDefault();
      adjustSpeed(-0.25);
    } else if (e.key === "j" || e.key === "J") {
      e.preventDefault();
      toggleQuickNav();
    } else if (e.key === "u" || e.key === "U") {
      e.preventDefault();
      toggleUserModal();
    } else if (e.key === "m" || e.key === "M") {
      toggleDrawer();
    } else if (e.key === "t" || e.key === "T") {
      cycleTheme();
    } else if (e.key === "/") {
      e.preventDefault();
      elements.searchBarPanel.style.display = "flex";
      elements.bookSearchInput.focus();
    }
  });
}

function adjustSpeed(delta) {
  const speeds = [0.75, 0.9, 1.0, 1.15, 1.25, 1.5, 1.75, 2.0, 2.5];
  let curIdx = speeds.indexOf(state.speed);
  if (curIdx === -1) curIdx = 2;
  const nextIdx = Math.max(0, Math.min(speeds.length - 1, curIdx + (delta > 0 ? 1 : -1)));
  setPlaybackSpeed(speeds[nextIdx]);
}

function cycleTheme() {
  const themes = ["sepia", "light", "dark", "oled", "eink"];
  const curIdx = themes.indexOf(state.theme);
  applyTheme(themes[(curIdx + 1) % themes.length]);
  syncAtelierUIState();
}

function openDrawer() {
  elements.drawerOverlay.classList.add("open");
  refreshVaultTelemetryUI();
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

  elements.dropzone.innerHTML = `<p>Analyzing &amp; ingesting <strong>${escapeHtml(file.name)}</strong>...</p>`;
  try {
    const res = await fetch("/api/upload", { method: "POST", body: formData });
    const data = await res.json();
    if (data.success) {
      if (file.name.toLowerCase().endsWith(".kzn") && window.KaizenOfflineParser && window.KaizenVault) {
        const unpacked = await window.KaizenOfflineParser.unpackKznCartridgeClient(file);
        await window.KaizenVault.importUnpackedCartridgeToVault(unpacked);
      }
      await loadLibrary();
      await openBook(data.document.id);
      closeDrawer();
      return;
    }
    throw new Error(data.detail || "Server upload rejected");
  } catch (err) {
    if (window.KaizenOfflineParser && window.KaizenVault) {
      try {
        const parsed = await window.KaizenOfflineParser.parseLocalFile(file);
        let docAst = null;
        if (parsed.type === "cartridge") {
          docAst = await window.KaizenVault.importUnpackedCartridgeToVault(parsed.data);
        } else {
          docAst = parsed.data;
          await window.KaizenVault.saveBookAstToVault(docAst);
        }
        await loadLibrary();
        await openBook(docAst.id);
        closeDrawer();
        return;
      } catch (offlineErr) {
        alert("Offline parser error: " + offlineErr.message);
      }
    } else {
      alert("Error uploading file: " + err.message);
    }
  } finally {
    elements.dropzone.innerHTML = `
      <p><strong>Drop Book or .kzn Cartridge</strong></p>
      <p style="font-size:0.75rem; margin-top:0.3rem;">.kzn, .epub, .pdf, .md, .docx, .txt (Works Offline)</p>
    `;
  }
}

// ==========================================================================
// Atelier & Acoustic Chronograph Quad-Engine Extensions
// ==========================================================================

state.engineMode = localStorage.getItem("kaizen_engine_mode") || "kokoro_auto";
state.smartCadence = localStorage.getItem("kaizen_smart_cadence") !== "false";
state.smartResume = localStorage.getItem("kaizen_smart_resume") !== "false";
state.lastPauseTimestamp = 0;
state.lexiconMap = {};
state.activeSprite = null;
state.pocketCurtainOpen = false;

const _origLoadLexicon = loadLexicon;
loadLexicon = async function () {
  if (navigator.onLine !== false) {
    try {
      const res = await fetchWithTimeout("/api/lexicon", {}, 1000);
      if (res.ok) {
        const data = await res.json();
        state.lexiconMap = data || {};
        if (window.KaizenVault) {
          window.KaizenVault.putSyncItem("lexicon", state.lexiconMap).catch(() => {});
        }
        renderLexicon(state.lexiconMap);
        return;
      }
    } catch (err) {}
  }
  if (window.KaizenVault) {
    const cachedLex = await window.KaizenVault.getSyncItem("lexicon");
    if (cachedLex) {
      state.lexiconMap = cachedLex;
      renderLexicon(cachedLex);
    }
  }
};

const _origLoadLibrary = loadLibrary;
loadLibrary = async function () {
  let loadedOnline = false;
  if (navigator.onLine !== false) {
    try {
      const res = await fetchWithTimeout(`/api/library?voice=${encodeURIComponent(state.voice)}&speed=${encodeURIComponent(state.speed)}`, {}, 1200);
      if (res.ok) {
        const books = await res.json();
        state.libraryBooks = books;
        renderLibraryList(books);
        const target = books.find((b) => b.id === (state.serverLastBookId || localStorage.getItem("kaizen_book_id"))) || books[0];
        if (target) await openBook(target.id);
        loadedOnline = true;
      }
    } catch (err) {}
  }

  if (!loadedOnline && window.KaizenVault) {
    const vaultBooks = await window.KaizenVault.listVaultBooks();
    if (vaultBooks && vaultBooks.length > 0) {
      state.libraryBooks = vaultBooks;
      renderLibraryList(vaultBooks);
      const localId = localStorage.getItem("kaizen_book_id");
      const target = vaultBooks.find((b) => b.id === localId) || vaultBooks[0];
      if (target) await openBook(target.id);
    }
  }
  refreshVaultTelemetryUI();
};

const _origOpenBook = openBook;
openBook = async function (bookId) {
  if (navigator.onLine !== false) {
    try {
      const res = await fetchWithTimeout(`/api/book/${bookId}`, {}, 1200);
      if (res.ok) {
        const book = await res.json();
        if (window.KaizenVault) {
          window.KaizenVault.saveBookAstToVault(book).catch(() => {});
        }
        await applyOpenedBook(book);
        return;
      }
    } catch (err) {}
  }

  if (window.KaizenVault) {
    const cachedBook = await window.KaizenVault.getBookAstFromVault(bookId);
    if (cachedBook) {
      await applyOpenedBook(cachedBook);
      return;
    }
  }
  console.error("Could not open book (offline and not in Vault):", bookId);
};

async function applyOpenedBook(book) {
  state.currentBook = book;
  localStorage.setItem("kaizen_book_id", book.id);
  if (elements.bookTitle) elements.bookTitle.textContent = book.title;
  document.title = `${book.title} — KaizenReader Atelier`;
  if (elements.spineBookTitle) elements.spineBookTitle.textContent = book.title;

  computeAllChaptersMetadata(book);
  renderTOC(book.chapters);
  renderQuickNavHUD();
  renderZenRail();
  if (state.libraryBooks) renderLibraryList(state.libraryBooks);

  const serverPos = state.serverPositions ? state.serverPositions[book.id] : null;
  let savedChapter = 0;
  let savedSentence = 0;
  if (serverPos && typeof serverPos.chapter_index === "number") {
    savedChapter = serverPos.chapter_index;
    savedSentence = serverPos.sentence_index || 0;
  } else {
    savedChapter = parseInt(localStorage.getItem(`kaizen_chap_${book.id}`) || "0", 10) || 0;
    savedSentence = parseInt(localStorage.getItem(`kaizen_sent_${book.id}`) || "0", 10) || 0;
  }

  state.currentChapterIndex = Math.max(0, Math.min(savedChapter, book.chapters.length - 1));
  renderCurrentChapter();
  state.currentSentenceIndex = Math.max(0, Math.min(savedSentence, Math.max(0, state.sentencesInChapter.length - 1)));
  if (state.sentencesInChapter[state.currentSentenceIndex]) {
    highlightSentence(state.sentencesInChapter[state.currentSentenceIndex].id);
    updateProgressIndicator();
  }
  updateHeaderTOC();
  await refreshVaultTelemetryUI();
  drawAcousticRibbon();
}

const _origStopCurrentSource = stopCurrentSource;
stopCurrentSource = function () {
  _origStopCurrentSource();
  const hwDeck = document.getElementById("kaizen-hardware-deck");
  if (hwDeck && !hwDeck.paused) {
    hwDeck.pause();
  }
  if ("speechSynthesis" in window) {
    try {
      window.speechSynthesis.cancel();
    } catch (e) {}
  }
};

const _origPauseAudio = pauseAudio;
pauseAudio = function () {
  state.lastPauseTimestamp = Date.now();
  _origPauseAudio();
  drawAcousticRibbon();
};

function getEffectiveSentenceSpeed(sentence) {
  let spd = state.speed || 1.0;
  if (state.smartCadence && sentence) {
    const nt = sentence.nodeType || "p";
    if (nt === "blockquote" || ["h1", "h2", "h3", "h4"].includes(nt)) {
      spd = Math.max(0.65, +(spd * 0.88).toFixed(2));
    }
  }
  return spd;
}

playSentenceAt = async function (index) {
  if (!state.sentencesInChapter || state.sentencesInChapter.length === 0) return;

  primeAudioEnginesOnGesture();

  if (
    !state.isPlaying &&
    state.smartResume &&
    state.lastPauseTimestamp > 0 &&
    Date.now() - state.lastPauseTimestamp > 180000 &&
    index === state.currentSentenceIndex &&
    index > 0
  ) {
    index = Math.max(0, index - 1);
  }
  state.lastPauseTimestamp = 0;

  if (index >= state.sentencesInChapter.length) {
    if (state.currentChapterIndex < state.currentBook.chapters.length - 1) {
      goToChapter(state.currentChapterIndex + 1, 0);
      playSentenceAt(0);
    } else {
      pauseAudio();
    }
    return;
  }
  if (index < 0) index = 0;

  const myToken = ++state.playToken;
  stopCurrentSource();

  state.currentSentenceIndex = index;
  state.isPlaying = true;
  elements.playIcon.style.display = "none";
  elements.pauseIcon.style.display = "block";
  if ("mediaSession" in navigator) {
    navigator.mediaSession.playbackState = "playing";
    updateMediaSessionMetadata();
  }

  const currentSentence = state.sentencesInChapter[index];
  highlightSentence(currentSentence.id);
  updateProgressIndicator();
  persistReadingState();
  updateChronographReadout();
  drawAcousticRibbon();

  if (currentSentence.skip_tts || !currentSentence.text.trim()) {
    setTimeout(() => {
      if (state.isPlaying && state.playToken === myToken) playSentenceAt(index + 1);
    }, 250);
    return;
  }

  if (state.engineMode === "apple_ios_neural") {
    updateEngineTelemetryBadge("apple_ios_neural");
    playViaAppleWebSpeech(currentSentence, index, myToken);
    return;
  }

  if (window.KaizenVault && state.currentBook) {
    try {
      const spriteRecord = await window.KaizenVault.getChapterSpriteFromVault(
        state.currentBook.id,
        state.currentChapterIndex,
        state.voice,
        state.speed
      );
      if (spriteRecord && spriteRecord.audioBlob && spriteRecord.timings) {
        if (!state.isPlaying || state.playToken !== myToken) return;
        updateEngineTelemetryBadge("kokoro_vault");
        const played = await playViaHardwareSpriteDeck(spriteRecord, index, myToken);
        if (played !== false) {
          return;
        }
        console.warn("Hardware sprite deck could not play; engaging Web Audio / Speech fallback.");
      }
    } catch (vaultErr) {
      console.warn("Vault sprite lookup error:", vaultErr);
    }
  }

  // If offline and no sprite was playable in Vault, immediately fallback to on-device speech
  if (navigator.onLine === false) {
    console.info("Device offline with no sprite available; engaging On-Device Apple Neural Live fallback.");
    updateEngineTelemetryBadge("apple_ios_neural");
    playViaAppleWebSpeech(currentSentence, index, myToken);
    return;
  }

  ensureAudioContext();
  const effectiveVoice =
    state.engineMode === "apple_mac_neural" && !state.voice.startsWith("apple:")
      ? "apple:Samantha"
      : state.voice;

  try {
    const effSpeed = getEffectiveSentenceSpeed(currentSentence);
    const modelSpeed = Math.min(2.0, effSpeed);
    const url = `/api/tts/sentence?text=${encodeURIComponent(currentSentence.text)}&voice=${encodeURIComponent(effectiveVoice)}&speed=${modelSpeed}&sentence_id=${encodeURIComponent(currentSentence.id)}&node_type=${encodeURIComponent(currentSentence.nodeType || "p")}&engine_mode=${encodeURIComponent(state.engineMode)}`;

    if (state.engineMode === "kokoro_auto") {
      triggerLookahead(index + 1);
    }

    const res = await fetchWithTimeout(url, {}, 1800);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    let timings = [];
    try {
      timings = JSON.parse(res.headers.get("X-Word-Timings") || "[]");
    } catch (e) {}
    const arr = await res.arrayBuffer();
    const buffer = await state.audioCtx.decodeAudioData(arr);

    if (!state.isPlaying || state.playToken !== myToken) return;
    updateEngineTelemetryBadge(state.engineMode === "apple_mac_neural" ? "apple_mac_neural" : "kokoro_live");

    const ctx = state.audioCtx;
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    const rate = effSpeed > 2.0 ? effSpeed / 2.0 : 1.0;
    src.playbackRate.value = rate;
    src.connect(ctx.destination);

    state.currentSource = src;
    state.playbackRate = rate;
    state.playStartTime = ctx.currentTime;
    state.activeTimings = timings;

    src.onended = () => {
      const wordsInSentence = currentSentence.text ? currentSentence.text.split(/\s+/).filter(Boolean).length : 0;
      recordReadingStats(wordsInSentence, buffer.duration / rate);
      if (state.isPlaying && state.playToken === myToken) {
        playSentenceAt(index + 1);
      }
    };

    src.start(0);
    startWordSyncLoop(currentSentence.id, myToken);
    broadcastPosition(currentSentence.id);
  } catch (err) {
    console.info("Mac server offline or unreachable; engaging On-Device Apple Neural Live fallback:", err);
    updateEngineTelemetryBadge("apple_ios_neural");
    playViaAppleWebSpeech(currentSentence, index, myToken);
  }
};

async function playViaHardwareSpriteDeck(spriteRecord, sentenceIndex, myToken) {
  const hwDeck = document.getElementById("kaizen-hardware-deck");
  if (!hwDeck) {
    return await playViaWebAudioSprite(spriteRecord, sentenceIndex, myToken);
  }

  const spriteKey = spriteRecord.sprite_key;
  if (!state.activeSprite || state.activeSprite.spriteKey !== spriteKey) {
    if (state.activeSprite && state.activeSprite.blobUrl) {
      URL.revokeObjectURL(state.activeSprite.blobUrl);
    }
    let blob = spriteRecord.audioBlob;
    if (blob instanceof Blob) {
      if (!blob.type || blob.type === "application/octet-stream") {
        blob = new Blob([blob], { type: "audio/mp4" });
      }
    } else if (blob && (blob instanceof ArrayBuffer || blob.buffer)) {
      blob = new Blob([blob], { type: "audio/mp4" });
    }
    const blobUrl = URL.createObjectURL(blob);

    hwDeck.innerHTML = "";
    const source = document.createElement("source");
    source.src = blobUrl;
    source.type = blob.type || "audio/mp4";
    hwDeck.appendChild(source);
    hwDeck.src = blobUrl;
    hwDeck.load();

    state.activeSprite = {
      spriteKey,
      blobUrl,
      timings: spriteRecord.timings,
    };
  }

  const timings = state.activeSprite.timings;
  const sentEntry = (timings.sentences || [])[sentenceIndex];
  if (!sentEntry) {
    playSentenceAt(sentenceIndex + 1);
    return true;
  }

  const baseSpriteSpeed = Number(timings.speed || 1.0);
  const currentSentence = state.sentencesInChapter[sentenceIndex];
  const targetSpeed = getEffectiveSentenceSpeed(currentSentence);
  hwDeck.playbackRate = Math.max(0.5, Math.min(2.5, targetSpeed / baseSpriteSpeed));

  const targetTime = Math.max(0, sentEntry.start || 0);
  const applySeek = () => {
    try {
      if (Math.abs(hwDeck.currentTime - targetTime) > 0.15) {
        hwDeck.currentTime = targetTime;
      }
    } catch (e) {
      console.warn("Could not seek hwDeck:", e);
    }
  };

  if (hwDeck.readyState >= 1) {
    applySeek();
  } else {
    hwDeck.addEventListener("loadedmetadata", applySeek, { once: true });
    hwDeck.addEventListener("canplay", applySeek, { once: true });
  }

  hwDeck.onended = () => {
    if (state.isPlaying && state.playToken === myToken) {
      if (state.currentChapterIndex < state.currentBook.chapters.length - 1) {
        goToChapter(state.currentChapterIndex + 1, 0);
        playSentenceAt(0);
      } else {
        pauseAudio();
      }
    }
  };

  try {
    await hwDeck.play();
  } catch (e) {
    console.warn("hwDeck.play() prevented or failed, engaging Web Audio sprite fallback:", e);
    return await playViaWebAudioSprite(spriteRecord, sentenceIndex, myToken);
  }

  function syncSpriteLoop() {
    if (!state.isPlaying || state.playToken !== myToken) return;
    if (hwDeck.paused) {
      state.rafId = requestAnimationFrame(syncSpriteLoop);
      return;
    }
    const tNow = hwDeck.currentTime;
    const sents = timings.sentences || [];

    let lo = 0;
    let hi = sents.length - 1;
    let foundIdx = state.currentSentenceIndex;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const s = sents[mid];
      if (tNow < s.start) hi = mid - 1;
      else if (tNow > s.end) lo = mid + 1;
      else {
        foundIdx = mid;
        break;
      }
    }

    if (foundIdx !== state.currentSentenceIndex && state.sentencesInChapter[foundIdx]) {
      const prevWords = (state.sentencesInChapter[state.currentSentenceIndex]?.text || "").split(/\s+/).filter(Boolean).length;
      recordReadingStats(prevWords, 2.5);
      state.currentSentenceIndex = foundIdx;
      const newSent = state.sentencesInChapter[foundIdx];
      highlightSentence(newSent.id);
      updateProgressIndicator();
      persistReadingState();
      updateChronographReadout();
      drawAcousticRibbon();
    }

    if (document.visibilityState !== "hidden") {
      const activeSentMeta = sents[state.currentSentenceIndex];
      const activeDomSent = state.sentencesInChapter[state.currentSentenceIndex];
      if (activeSentMeta && activeDomSent) {
        const span = document.getElementById(`span-${activeDomSent.id}`);
        if (span) {
          const wordEls = span.querySelectorAll(".word-token");
          let activeWordIdx = -1;
          for (const tuple of activeSentMeta.words || []) {
            if (tNow >= tuple[1] && tNow <= tuple[2] + 0.06) {
              activeWordIdx = tuple[0];
              break;
            }
          }
          wordEls.forEach((el, idx) => {
            if (idx === activeWordIdx) el.classList.add("active-word");
            else el.classList.remove("active-word");
          });
        }
      }
    }

    state.rafId = requestAnimationFrame(syncSpriteLoop);
  }

  state.rafId = requestAnimationFrame(syncSpriteLoop);

  hwDeck.ontimeupdate = () => {
    if (!state.isPlaying || state.playToken !== myToken) return;
    const tNow = hwDeck.currentTime;
    const sents = timings.sentences || [];
    let lo = 0, hi = sents.length - 1, foundIdx = state.currentSentenceIndex;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const s = sents[mid];
      if (tNow < s.start) hi = mid - 1;
      else if (tNow > s.end) lo = mid + 1;
      else { foundIdx = mid; break; }
    }
    if (foundIdx !== state.currentSentenceIndex && state.sentencesInChapter[foundIdx]) {
      state.currentSentenceIndex = foundIdx;
      const newSent = state.sentencesInChapter[foundIdx];
      highlightSentence(newSent.id);
      updateProgressIndicator();
      persistReadingState();
      updateChronographReadout();
    }
  };

  return true;
}

async function playViaWebAudioSprite(spriteRecord, sentenceIndex, myToken) {
  try {
    ensureAudioContext();
    const ctx = state.audioCtx;
    if (!ctx) throw new Error("No AudioContext available");

    const timings = spriteRecord.timings;
    const sentEntry = (timings.sentences || [])[sentenceIndex];
    if (!sentEntry) {
      playSentenceAt(sentenceIndex + 1);
      return true;
    }

    let buffer = spriteRecord._decodedAudioBuffer;
    if (!buffer) {
      let blob = spriteRecord.audioBlob;
      const arr = blob instanceof ArrayBuffer ? blob : await blob.arrayBuffer();
      buffer = await ctx.decodeAudioData(arr.slice(0));
      spriteRecord._decodedAudioBuffer = buffer;
    }

    if (!state.isPlaying || state.playToken !== myToken) return false;

    const currentSentence = state.sentencesInChapter[sentenceIndex];
    const baseSpeed = Number(timings.speed || 1.0);
    const targetSpeed = getEffectiveSentenceSpeed(currentSentence);
    const rate = Math.max(0.5, Math.min(2.5, targetSpeed / baseSpeed));

    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.playbackRate.value = rate;
    src.connect(ctx.destination);

    state.currentSource = src;
    state.playbackRate = rate;
    state.playStartTime = ctx.currentTime;

    const compactWords = sentEntry.words || [];
    state.activeTimings = compactWords.map((w) => ({
      i: w[0],
      s: Math.max(0, w[1] - sentEntry.start),
      e: Math.max(0, w[2] - sentEntry.start),
    }));

    const offset = Math.max(0, sentEntry.start);
    const duration = Math.max(0.1, (sentEntry.end - sentEntry.start) / rate);

    src.onended = () => {
      const words = (currentSentence.text || "").split(/\s+/).filter(Boolean).length;
      recordReadingStats(words, duration);
      if (state.isPlaying && state.playToken === myToken) {
        playSentenceAt(sentenceIndex + 1);
      }
    };

    src.start(0, offset, duration);
    startWordSyncLoop(currentSentence.id, myToken);
    broadcastPosition(currentSentence.id);
    return true;
  } catch (err) {
    console.warn("Web Audio sprite decode/play failed:", err);
    return false;
  }
}

function playViaAppleWebSpeech(sentence, index, myToken) {
  if (!("speechSynthesis" in window)) {
    setTimeout(() => {
      if (state.isPlaying && state.playToken === myToken) playSentenceAt(index + 1);
    }, 500);
    return;
  }

  try {
    if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
      window.speechSynthesis.cancel();
    }
  } catch (e) {}

  const normalized = window.KaizenPhonetics
    ? window.KaizenPhonetics.normalizeTextForTts(sentence.text, state.lexiconMap)
    : sentence.text;

  const utt = new SpeechSynthesisUtterance(normalized);
  utt.rate = Math.max(0.5, Math.min(2.2, getEffectiveSentenceSpeed(sentence)));

  const voices = window.speechSynthesis.getVoices() || [];
  const enVoices = voices.filter((v) => v.lang && v.lang.toLowerCase().startsWith("en"));
  const localEnVoices = enVoices.filter((v) => v.localService);
  const candidateVoices = localEnVoices.length > 0 ? localEnVoices : enVoices;
  const preferred =
    candidateVoices.find((v) => /premium|enhanced|natural|siri|ava|allison|evan|samantha/i.test(v.name)) ||
    candidateVoices[0];
  if (preferred) utt.voice = preferred;

  const span = document.getElementById(`span-${sentence.id}`);
  const wordEls = span ? Array.from(span.querySelectorAll(".word-token")) : [];
  const rawWords = sentence.text.split(/\s+/).filter(Boolean);

  utt.onboundary = (e) => {
    if (!state.isPlaying || state.playToken !== myToken) return;
    if (e.name === "word" && wordEls.length > 0) {
      const ratio = Math.max(0, Math.min(0.99, (e.charIndex || 0) / Math.max(1, normalized.length)));
      const wIdx = Math.min(wordEls.length - 1, Math.floor(ratio * rawWords.length));
      wordEls.forEach((el, i) => {
        if (i === wIdx) el.classList.add("active-word");
        else el.classList.remove("active-word");
      });
    }
  };

  utt.onend = () => {
    wordEls.forEach((el) => el.classList.remove("active-word"));
    recordReadingStats(rawWords.length, Math.max(1, rawWords.length / 2.8));
    if (state.isPlaying && state.playToken === myToken) {
      playSentenceAt(index + 1);
    }
  };

  utt.onerror = (e) => {
    console.warn("speechSynthesis utterance error:", e);
    if (state.isPlaying && state.playToken === myToken) {
      playSentenceAt(index + 1);
    }
  };

  setTimeout(() => {
    try {
      window.speechSynthesis.speak(utt);
    } catch (e) {
      console.warn("speechSynthesis.speak failed:", e);
      if (state.isPlaying && state.playToken === myToken) {
        setTimeout(() => playSentenceAt(index + 1), 600);
      }
    }
  }, 10);
}

function drawAcousticRibbon() {
  const canvas = document.getElementById("acoustic-ribbon");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const w = Math.max(160, rect.width || 320);
  const h = 28;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  ctx.save();
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);

  const total = Math.max(1, state.sentencesInChapter.length);
  const progressRatio = (state.currentSentenceIndex + 1) / total;
  const styles = getComputedStyle(document.documentElement);
  const accent = styles.getPropertyValue("--accent-color").trim() || "#a85d26";
  const muted = styles.getPropertyValue("--text-muted").trim() || "#736b60";

  const numBars = 72;
  const barGap = w / numBars;
  const envelope = state.activeSprite?.timings?.rms_envelope || null;

  for (let i = 0; i < numBars; i++) {
    const ratio = i / numBars;
    const sIdx = Math.min(total - 1, Math.floor(ratio * total));
    const sent = state.sentencesInChapter[sIdx];
    let amp = 0.28;
    if (envelope && envelope.length > 0) {
      const eIdx = Math.min(envelope.length - 1, Math.floor(ratio * envelope.length));
      amp = envelope[eIdx];
    } else if (sent && sent.text) {
      const lenFactor = Math.min(1.0, sent.text.length / 140);
      amp = 0.22 + 0.65 * Math.abs(Math.sin(i * 0.63 + lenFactor * 3.1));
    }

    const isHeading = sent && ["h1", "h2", "h3"].includes(sent.nodeType);
    const barH = isHeading ? h - 4 : Math.max(4, Math.round(amp * (h - 6)));
    const x = i * barGap + 1;
    const y = (h - barH) / 2;

    if (ratio <= progressRatio) {
      ctx.fillStyle = accent;
      ctx.globalAlpha = isHeading ? 1.0 : 0.88;
    } else {
      ctx.fillStyle = isHeading ? accent : muted;
      ctx.globalAlpha = isHeading ? 0.55 : 0.3;
    }
    ctx.fillRect(x, y, Math.max(1.5, barGap - 1.6), barH);
  }

  ctx.restore();
  updateEditorialFolioBar();
}

function updateEditorialFolioBar() {
  const leftEl = document.getElementById("folio-left-label");
  const rightEl = document.getElementById("folio-right-telemetry");
  if (!state.currentBook) return;
  const chMeta = state.chapterMetadata[state.currentChapterIndex];
  if (leftEl) {
    leftEl.textContent = `${state.currentBook.title.slice(0, 34)} · ${chMeta ? chMeta.badgeLabel : `CH ${state.currentChapterIndex + 1}`}`;
  }
  if (rightEl) {
    const wpm = Math.round(165 * (state.speed || 1.0));
    const modeTag =
      state.engineMode === "apple_ios_neural"
        ? " ANE NEURAL"
        : state.engineMode === "apple_mac_neural"
        ? " MAC STUDIO"
        : "KOKORO STUDIO";
    rightEl.textContent = `${wpm} WPM · ${modeTag}${state.smartCadence ? " · SMART CADENCE" : ""}`;
  }
}

function updateEngineTelemetryBadge(activeMode) {
  const dot = document.getElementById("engine-status-dot");
  const label = document.getElementById("engine-mode-label");
  const sheetBadge = document.getElementById("atelier-active-engine-badge");
  if (!label) return;

  if (activeMode === "kokoro_vault") {
    label.textContent = "KOKORO · VAULT";
    dot?.classList.remove("apple-mode");
    dot?.classList.add("vault-mode");
    if (sheetBadge) sheetBadge.textContent = "Playing .m4a Hardware Sprite";
  } else if (activeMode === "apple_ios_neural") {
    label.textContent = " APPLE · ANE";
    dot?.classList.remove("vault-mode");
    dot?.classList.add("apple-mode");
    if (sheetBadge) sheetBadge.textContent = "On-Device Apple Neural Active";
  } else if (activeMode === "apple_mac_neural") {
    label.textContent = " APPLE · M1";
    dot?.classList.remove("vault-mode");
    dot?.classList.add("apple-mode");
    if (sheetBadge) sheetBadge.textContent = "macOS Apple Neural Stream";
  } else {
    label.textContent = "KOKORO · M1";
    dot?.classList.remove("apple-mode", "vault-mode");
    if (sheetBadge) sheetBadge.textContent = "Kokoro-82M FP16 Stream";
  }
}

async function openPhoneticLens(rawWord, contextText, anchorRect) {
  const popover = document.getElementById("phonetic-lens-popover");
  if (!popover) return;
  const cleanWord = rawWord.replace(/^[.,!?;:"'()[\]]+|[.,!?;:"'()[\]]+$/g, "").trim();
  if (!cleanWord) return;

  const wordEl = document.getElementById("lens-target-word");
  const ipaEl = document.getElementById("lens-compiled-ipa");
  const inputEl = document.getElementById("lens-phonetic-input");
  const badgeEl = document.getElementById("lens-override-badge");
  const pillsRow = document.getElementById("lens-stress-pills");

  wordEl.textContent = cleanWord;
  const existingOverride = state.lexiconMap[cleanWord] || state.lexiconMap[cleanWord.toLowerCase()] || "";
  inputEl.value = existingOverride;
  badgeEl.textContent = existingOverride ? "Custom Override" : "Auto G2P";

  const topY = Math.max(66, Math.min(window.innerHeight - 280, (anchorRect?.bottom || 160) + 8));
  const leftX = Math.max(12, Math.min(window.innerWidth - 352, anchorRect?.left || 24));
  popover.style.top = `${topY}px`;
  popover.style.left = `${leftX}px`;
  popover.style.display = "block";

  let inspectData = null;
  try {
    const res = await fetch(`/api/phonetics/inspect?word=${encodeURIComponent(cleanWord)}&context=${encodeURIComponent(contextText || cleanWord)}`);
    if (res.ok) inspectData = await res.json();
  } catch (e) {}

  if (!inspectData && window.KaizenPhonetics) {
    const compiled = window.KaizenPhonetics.respellingToIpa(existingOverride || cleanWord);
    inspectData = {
      word: cleanWord,
      kokoro_ipa: `/${compiled}/`,
      stress_variants: window.KaizenPhonetics.buildStressVariants(cleanWord),
    };
  }

  if (inspectData) {
    ipaEl.textContent = inspectData.kokoro_ipa || "/—/";
    pillsRow.innerHTML = "";
    (inspectData.stress_variants || []).forEach((v) => {
      const btn = document.createElement("button");
      btn.className = "stress-syl-pill";
      btn.textContent = v.respelling;
      btn.onclick = () => {
        pillsRow.querySelectorAll(".stress-syl-pill").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        inputEl.value = v.respelling;
        ipaEl.textContent = v.ipa;
      };
      pillsRow.appendChild(btn);
    });
  }

  inputEl.oninput = () => {
    if (window.KaizenPhonetics) {
      const c = window.KaizenPhonetics.respellingToIpa(inputEl.value.trim() || cleanWord);
      ipaEl.textContent = c ? `/${c}/` : "/—/";
    }
  };

  document.getElementById("lens-hear-kokoro-btn").onclick = async () => {
    const ph = inputEl.value.trim();
    const previewText = ph
      ? window.KaizenPhonetics
        ? `/${window.KaizenPhonetics.respellingToIpa(ph)}/`
        : ph
      : cleanWord;
    try {
      const ctx = ensureAudioContext();
      const res = await fetch(`/api/tts/sentence?text=${encodeURIComponent(previewText)}&voice=${encodeURIComponent(state.voice.startsWith("apple:") ? "af_bella" : state.voice)}&speed=1.0`);
      const buf = await ctx.decodeAudioData(await res.arrayBuffer());
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(ctx.destination);
      src.start(0);
    } catch (e) {
      alert("Kokoro live audition requires Mac connection or cached sprite.");
    }
  };

  document.getElementById("lens-hear-apple-btn").onclick = async () => {
    const ph = inputEl.value.trim();
    try {
      const ctx = ensureAudioContext();
      const res = await fetch(`/api/tts/apple-sentence?text=${encodeURIComponent(ph || cleanWord)}&speed=1.0`);
      if (res.ok) {
        const buf = await ctx.decodeAudioData(await res.arrayBuffer());
        const src = ctx.createBufferSource();
        src.buffer = buf;
        src.connect(ctx.destination);
        src.start(0);
        return;
      }
    } catch (e) {}
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utt = new SpeechSynthesisUtterance(ph || cleanWord);
      window.speechSynthesis.speak(utt);
    }
  };

  document.getElementById("lens-save-btn").onclick = async () => {
    const phoneticVal = inputEl.value.trim();
    if (!phoneticVal) return;
    state.lexiconMap[cleanWord] = phoneticVal;
    if (window.KaizenVault) {
      await window.KaizenVault.putSyncItem("lexicon", state.lexiconMap);
    }
    try {
      await fetch("/api/lexicon", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ word: cleanWord, phonetic: phoneticVal }),
      });
    } catch (e) {}
    state.prefetchCache.clear();
    await loadLexicon();
    badgeEl.textContent = "Saved!";
    setTimeout(() => {
      popover.style.display = "none";
    }, 500);
  };
}

function setPlaybackSpeed(newSpeed) {
  state.speed = parseFloat(newSpeed);
  state.prefetchCache.clear();
  if (elements.speedSelect) elements.speedSelect.value = String(state.speed);
  localStorage.setItem("kaizen_speed", String(state.speed));
  syncAtelierUIState();
  updateProgressIndicator();
  updateChronographReadout();
  if (state.isPlaying) playSentenceAt(state.currentSentenceIndex);
}

function setEngineMode(mode) {
  state.engineMode = mode;
  localStorage.setItem("kaizen_engine_mode", mode);
  updateEngineTelemetryBadge(mode);
  syncAtelierUIState();
  updateEditorialFolioBar();
  if (state.isPlaying) playSentenceAt(state.currentSentenceIndex);
}

function syncAtelierUIState() {
  const wpm = Math.round(165 * (state.speed || 1.0));
  const speedReadout = document.getElementById("vernier-speed-readout");
  if (speedReadout) speedReadout.textContent = `${state.speed.toFixed(2)}× · ~${wpm} WPM`;

  document.querySelectorAll("#vernier-speed-strip .vernier-tick-btn").forEach((btn) => {
    const s = parseFloat(btn.dataset.speed);
    if (Math.abs(s - state.speed) < 0.02) btn.classList.add("active");
    else btn.classList.remove("active");
  });

  document.querySelectorAll(".engine-option-card").forEach((card) => {
    if (card.dataset.engine === state.engineMode) card.classList.add("active");
    else card.classList.remove("active");
  });

  document.querySelectorAll("#atelier-theme-swatches .theme-swatch-card").forEach((sw) => {
    if (sw.dataset.themeVal === state.theme) sw.classList.add("active");
    else sw.classList.remove("active");
  });

  const fontReadout = document.getElementById("sheet-font-readout");
  if (fontReadout) fontReadout.textContent = `${state.fontSize}px`;
}

async function refreshVaultTelemetryUI() {
  if (!window.KaizenVault) return;
  const stats = await window.KaizenVault.getVaultStats();
  const mb = (stats.spritesTotalBytes / (1024 * 1024)).toFixed(1);
  const badge = document.getElementById("vault-storage-badge");
  if (badge) {
    badge.textContent = `${stats.spritesCachedCount} Sprites · ${mb} MB in Vault`;
  }
  const drawerStat = document.getElementById("drawer-vault-stat");
  if (drawerStat) {
    drawerStat.textContent = `${stats.spritesCachedCount} ch · ${mb} MB`;
  }

  const matrix = document.getElementById("vault-chapter-matrix");
  if (matrix && state.currentBook) {
    const bookSprites = await window.KaizenVault.getBookSpritesMeta(state.currentBook.id);
    const packedSet = new Set(bookSprites.map((s) => s.chapter_index));
    matrix.innerHTML = "";
    state.currentBook.chapters.forEach((ch, idx) => {
      const cell = document.createElement("div");
      cell.className = `vault-matrix-cell ${packedSet.has(idx) ? "packed" : ""} ${idx === state.currentChapterIndex ? "current" : ""}`;
      cell.textContent = String(idx + 1);
      cell.title = `Ch ${idx + 1}: ${ch.title} (${packedSet.has(idx) ? "Cached in iPhone Vault" : "Not packed yet"})`;
      cell.onclick = () => goToChapter(idx, 0);
      matrix.appendChild(cell);
    });
  }
}

async function triggerVaultPack(chapterIndices) {
  if (!state.currentBook || !window.KaizenVault) return;
  const wrap = document.getElementById("vault-pack-progress-wrap");
  const statusText = document.getElementById("vault-pack-status-text");
  const pctText = document.getElementById("vault-pack-pct-text");
  const fill = document.getElementById("vault-pack-progress-fill");

  if (wrap) wrap.style.display = "flex";
  let wakeLock = null;
  try {
    if (navigator.wakeLock?.request) {
      wakeLock = await navigator.wakeLock.request("screen").catch(() => null);
    }
    await window.KaizenVault.packChaptersFromFoundry(
      state.currentBook,
      chapterIndices,
      state.voice,
      state.speed,
      (prog) => {
        const pct = Math.round((prog.completedChapters / Math.max(1, prog.totalChapters)) * 100);
        if (statusText) statusText.textContent = prog.message;
        if (pctText) pctText.textContent = `${pct}%`;
        if (fill) fill.style.width = `${pct}%`;
        if (prog.phase === "cached") {
          refreshVaultTelemetryUI().catch(() => {});
        }
      }
    );
    await refreshVaultTelemetryUI();
  } catch (err) {
    if (statusText) statusText.textContent = `Pack error: ${err.message}`;
  } finally {
    if (wakeLock) wakeLock.release().catch(() => {});
  }
}

function updateChronographReadout() {
  if (!state.pocketCurtainOpen) return;
  const chCode = document.getElementById("chrono-chapter-code");
  const sentCounter = document.getElementById("chrono-sentence-counter");
  const speedTag = document.getElementById("chrono-speed-tag");
  const liveSent = document.getElementById("chrono-live-sentence");
  const ring = document.getElementById("chrono-progress-ring");

  const total = Math.max(1, state.sentencesInChapter.length);
  const cur = state.currentSentenceIndex + 1;
  if (chCode) chCode.textContent = `CH ${String(state.currentChapterIndex + 1).padStart(2, "0")}`;
  if (sentCounter) sentCounter.textContent = `${String(cur).padStart(3, "0")} / ${String(total).padStart(3, "0")}`;
  if (speedTag) speedTag.textContent = `${state.speed.toFixed(2)}×`;

  const sObj = state.sentencesInChapter[state.currentSentenceIndex];
  if (liveSent && sObj) liveSent.textContent = sObj.text;

  if (ring) {
    const circumference = 527.78;
    const offset = circumference * (1 - cur / total);
    ring.style.strokeDashoffset = String(offset.toFixed(2));
  }
}

function setupAtelierExtensions() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
  if (window.KaizenVault) {
    window.KaizenVault.requestPersistentStorage().then(() => refreshVaultTelemetryUI());
  }

  const sheet = document.getElementById("atelier-console-sheet");
  const backdrop = document.getElementById("atelier-sheet-backdrop");
  const openSheet = () => {
    syncAtelierUIState();
    refreshVaultTelemetryUI();
    if (backdrop) backdrop.style.display = "block";
    if (sheet) sheet.style.display = "flex";
  };
  const closeSheet = () => {
    if (backdrop) backdrop.style.display = "none";
    if (sheet) sheet.style.display = "none";
  };

  document.getElementById("atelier-sheet-btn")?.addEventListener("click", openSheet);
  document.getElementById("engine-mode-pill")?.addEventListener("click", openSheet);
  document.getElementById("drawer-open-atelier-btn")?.addEventListener("click", () => {
    closeDrawer();
    openSheet();
  });
  document.getElementById("close-atelier-sheet-btn")?.addEventListener("click", closeSheet);
  backdrop?.addEventListener("click", closeSheet);

  document.querySelectorAll(".engine-option-card").forEach((card) => {
    card.addEventListener("click", () => setEngineMode(card.dataset.engine));
  });

  document.querySelectorAll("#vernier-speed-strip .vernier-tick-btn").forEach((btn) => {
    btn.addEventListener("click", () => setPlaybackSpeed(parseFloat(btn.dataset.speed)));
  });

  const cadenceBox = document.getElementById("smart-cadence-toggle");
  if (cadenceBox) {
    cadenceBox.checked = state.smartCadence;
    cadenceBox.onchange = () => {
      state.smartCadence = cadenceBox.checked;
      localStorage.setItem("kaizen_smart_cadence", String(state.smartCadence));
      updateEditorialFolioBar();
    };
  }
  const resumeBox = document.getElementById("smart-resume-toggle");
  if (resumeBox) {
    resumeBox.checked = state.smartResume;
    resumeBox.onchange = () => {
      state.smartResume = resumeBox.checked;
      localStorage.setItem("kaizen_smart_resume", String(state.smartResume));
    };
  }

  document.querySelectorAll("#atelier-theme-swatches .theme-swatch-card").forEach((sw) => {
    sw.addEventListener("click", () => {
      applyTheme(sw.dataset.themeVal);
      syncAtelierUIState();
      drawAcousticRibbon();
    });
  });

  document.getElementById("sheet-font-inc")?.addEventListener("click", () => {
    elements.fontIncreaseBtn?.click();
    syncAtelierUIState();
  });
  document.getElementById("sheet-font-dec")?.addEventListener("click", () => {
    elements.fontDecreaseBtn?.click();
    syncAtelierUIState();
  });

  document.getElementById("pack-current-ch-btn")?.addEventListener("click", () => {
    triggerVaultPack([state.currentChapterIndex]);
  });
  document.getElementById("drawer-pack-ch-btn")?.addEventListener("click", () => {
    closeDrawer();
    openSheet();
    triggerVaultPack([state.currentChapterIndex]);
  });
  document.getElementById("pack-next3-ch-btn")?.addEventListener("click", () => {
    if (!state.currentBook) return;
    const indices = [];
    for (let i = state.currentChapterIndex; i < Math.min(state.currentBook.chapters.length, state.currentChapterIndex + 3); i++) {
      indices.push(i);
    }
    triggerVaultPack(indices);
  });
  document.getElementById("pack-all-ch-btn")?.addEventListener("click", () => {
    if (!state.currentBook) return;
    triggerVaultPack(state.currentBook.chapters.map((_, idx) => idx));
  });
  document.getElementById("export-kzn-btn")?.addEventListener("click", () => {
    if (!state.currentBook) return;
    const url = `/api/book/${state.currentBook.id}/cartridge?voice=${encodeURIComponent(state.voice)}&speed=${encodeURIComponent(state.speed)}`;
    window.open(url, "_blank");
  });
  document.getElementById("import-kzn-btn")?.addEventListener("click", () => {
    closeSheet();
    elements.fileInput?.click();
  });

  document.getElementById("lens-close-btn")?.addEventListener("click", () => {
    const pop = document.getElementById("phonetic-lens-popover");
    if (pop) pop.style.display = "none";
  });

  const handleSelectionForLens = () => {
    const sel = window.getSelection();
    const text = sel ? sel.toString().trim() : "";
    if (text && text.length >= 2 && text.length <= 36 && !text.includes("\n") && elements.readerContent.contains(sel.anchorNode)) {
      const rect = sel.getRangeAt(0).getBoundingClientRect();
      const contextSent = state.sentencesInChapter[state.currentSentenceIndex]?.text || text;
      elements.teachSelectionBtn.style.left = `${Math.max(12, Math.min(window.innerWidth - 150, rect.left))}px`;
      elements.teachSelectionBtn.style.top = `${Math.max(60, rect.top - 36)}px`;
      elements.teachSelectionBtn.style.display = "block";
      elements.teachSelectionBtn.onclick = () => {
        elements.teachSelectionBtn.style.display = "none";
        openPhoneticLens(text, contextSent, rect);
      };
    }
  };
  document.addEventListener("mouseup", handleSelectionForLens);
  document.addEventListener("touchend", () => setTimeout(handleSelectionForLens, 160));

  const curtain = document.getElementById("pocket-curtain-overlay");
  document.getElementById("pocket-curtain-btn")?.addEventListener("click", () => {
    state.pocketCurtainOpen = true;
    if (curtain) curtain.style.display = "flex";
    updateChronographReadout();
  });
  document.getElementById("chrono-unlock-btn")?.addEventListener("click", () => {
    state.pocketCurtainOpen = false;
    if (curtain) curtain.style.display = "none";
  });
  document.getElementById("chrono-play-btn")?.addEventListener("click", togglePlay);
  document.getElementById("chrono-prev-btn")?.addEventListener("click", () => playSentenceAt(state.currentSentenceIndex - 1));
  document.getElementById("chrono-next-btn")?.addEventListener("click", () => playSentenceAt(state.currentSentenceIndex + 1));

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && state.currentBook) {
      const s = state.sentencesInChapter[state.currentSentenceIndex];
      if (s) highlightSentence(s.id);
      drawAcousticRibbon();
    }
  });

  window.addEventListener("resize", drawAcousticRibbon);
  updateEngineTelemetryBadge(state.engineMode);
  syncAtelierUIState();
  setupGoogleDriveLocker();
  setTimeout(drawAcousticRibbon, 400);
}

function setupGoogleDriveLocker() {
  if (!window.KaizenGDrive) return;
  const clientIdInput = document.getElementById("gdrive-client-id-input");
  const connectBtn = document.getElementById("gdrive-connect-btn");
  const statusBadge = document.getElementById("gdrive-status-badge");
  const actionsRow = document.getElementById("gdrive-actions-row");
  const refreshBtn = document.getElementById("gdrive-refresh-btn");
  const pushBtn = document.getElementById("gdrive-push-btn");
  const atelierPushBtn = document.getElementById("push-gdrive-kzn-btn");
  const filesList = document.getElementById("gdrive-files-list");

  const updateDriveUIState = () => {
    const connected = window.KaizenGDrive.isConnected();
    if (statusBadge) statusBadge.textContent = connected ? "Connected" : "Disconnected";
    if (connectBtn) connectBtn.textContent = connected ? "Disconnect" : "Connect";
    if (actionsRow) actionsRow.style.display = connected ? "flex" : "none";
    if (filesList) filesList.style.display = connected ? "flex" : "none";
  };

  window.KaizenGDrive.syncConfigFromServer().then((cfg) => {
    const cid = window.KaizenGDrive.getSavedClientId() || cfg?.client_id || "";
    if (clientIdInput && cid) {
      clientIdInput.value = cid;
      window.KaizenGDrive.loadGisScript?.().catch(() => {});
    }
  });
  clientIdInput?.addEventListener("focus", () => {
    window.KaizenGDrive.loadGisScript?.().catch(() => {});
  });

  const renderDriveFiles = async () => {
    if (!filesList || !window.KaizenGDrive.isConnected()) return;
    filesList.innerHTML = `<div class="gdrive-file-sub" style="padding:0.4rem;">Scanning Google Drive...</div>`;
    try {
      const files = await window.KaizenGDrive.listDriveLibraryFiles(false);
      filesList.innerHTML = "";
      if (!files.length) {
        filesList.innerHTML = `<div class="gdrive-file-sub" style="padding:0.4rem;">No .kzn, .epub, .pdf, .md, or .docx files found in Drive.</div>`;
        return;
      }
      files.forEach((f) => {
        const row = document.createElement("div");
        row.className = "gdrive-file-row";
        const sizeMb = f.size ? `${(Number(f.size) / (1024 * 1024)).toFixed(1)} MB` : "Drive File";
        const isKzn = (f.name || "").toLowerCase().endsWith(".kzn");
        row.innerHTML = `
          <div class="gdrive-file-meta">
            <span class="gdrive-file-name" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>
            <span class="gdrive-file-sub">${isKzn ? "Sovereign Cartridge" : "Document"} · ${sizeMb}</span>
          </div>
          <button class="icon-btn" style="font-size:0.7rem; white-space:nowrap;">⬇ Pull</button>
        `;
        const pullBtn = row.querySelector("button");
        pullBtn.onclick = async () => {
          pullBtn.disabled = true;
          pullBtn.textContent = "Pulling...";
          try {
            const blob = await window.KaizenGDrive.downloadFileAsBlob(f.id);
            const fileObj = new File([blob], f.name, { type: f.mimeType || "application/octet-stream" });
            await uploadFile(fileObj);
            pullBtn.textContent = "✓ Loaded";
          } catch (err) {
            alert("Drive download error: " + err.message);
            pullBtn.textContent = "⬇ Pull";
          } finally {
            pullBtn.disabled = false;
          }
        };
        filesList.appendChild(row);
      });
    } catch (err) {
      filesList.innerHTML = `<div class="gdrive-file-sub" style="padding:0.4rem; color:#dc2626;">${escapeHtml(err.message)}</div>`;
    }
  };

  const pushCurrentCartridgeToDrive = async (triggerBtn) => {
    if (!state.currentBook) {
      alert("Open a book first before pushing a .kzn cartridge.");
      return;
    }
    const origText = triggerBtn ? triggerBtn.textContent : "";
    try {
      if (!window.KaizenGDrive.isConnected()) {
        await window.KaizenGDrive.connect(clientIdInput?.value || "");
        updateDriveUIState();
      }
      if (triggerBtn) {
        triggerBtn.disabled = true;
        triggerBtn.textContent = "Packing & Pushing...";
      }
      const res = await fetch(
        `/api/book/${state.currentBook.id}/cartridge?voice=${encodeURIComponent(state.voice)}&speed=${encodeURIComponent(state.speed)}`
      );
      if (!res.ok) throw new Error(`Cartridge export failed (${res.status})`);
      const blob = await res.blob();
      const safeTitle = (state.currentBook.title || "KaizenBook").replace(/[^a-zA-Z0-9_-]+/g, "_").slice(0, 48);
      const filename = `${safeTitle}_${state.currentBook.id}.kzn`;
      await window.KaizenGDrive.uploadCartridgeToDrive(filename, blob, "KaizenReader");
      if (triggerBtn) triggerBtn.textContent = "✓ Pushed to Drive!";
      await renderDriveFiles();
      setTimeout(() => {
        if (triggerBtn) triggerBtn.textContent = origText;
      }, 2500);
    } catch (err) {
      alert("Google Drive push error: " + err.message);
      if (triggerBtn) triggerBtn.textContent = origText;
    } finally {
      if (triggerBtn) triggerBtn.disabled = false;
    }
  };

  if (connectBtn) {
    connectBtn.onclick = async () => {
      if (window.KaizenGDrive.isConnected()) {
        window.KaizenGDrive.disconnect();
        updateDriveUIState();
        return;
      }
      try {
        connectBtn.disabled = true;
        connectBtn.textContent = "Connecting...";
        await window.KaizenGDrive.connect(clientIdInput?.value || "");
        updateDriveUIState();
        await renderDriveFiles();
      } catch (err) {
        alert(err.message);
      } finally {
        connectBtn.disabled = false;
        updateDriveUIState();
      }
    };
  }

  refreshBtn?.addEventListener("click", renderDriveFiles);
  pushBtn?.addEventListener("click", () => pushCurrentCartridgeToDrive(pushBtn));
  atelierPushBtn?.addEventListener("click", () => pushCurrentCartridgeToDrive(atelierPushBtn));
  updateDriveUIState();
}

window.addEventListener("DOMContentLoaded", async () => {
  await init();
  setupAtelierExtensions();
});
