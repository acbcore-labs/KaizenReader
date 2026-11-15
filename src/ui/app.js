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

function ensureAudioContext() {
  if (!state.audioCtx) {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    state.audioCtx = new AudioCtx();
  }
  if (state.audioCtx.state === "suspended") {
    state.audioCtx.resume();
  }
  return state.audioCtx;
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
  try {
    const res = await fetch("/api/state");
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
  try {
    const [userRes, usersRes, memRes] = await Promise.all([
      fetch("/api/user/current"),
      fetch("/api/users"),
      fetch("/api/user/memory"),
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
    console.warn("Error fetching user data:", err);
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
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    if (data.companion_url) {
      elements.mobileUrlText.textContent = data.companion_url.replace("http://", "");
      elements.mobileBadge.onclick = () => {
        navigator.clipboard?.writeText(data.companion_url);
        elements.mobileUrlText.textContent = "Copied!";
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
  const speeds = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5];
  let curIdx = speeds.indexOf(state.speed);
  if (curIdx === -1) curIdx = 1;
  const nextIdx = Math.max(0, Math.min(speeds.length - 1, curIdx + (delta > 0 ? 1 : -1)));
  state.speed = speeds[nextIdx];
  state.prefetchCache.clear();
  elements.speedSelect.value = state.speed.toString();
  localStorage.setItem("kaizen_speed", state.speed);
  updateProgressIndicator();
  if (state.isPlaying) playSentenceAt(state.currentSentenceIndex);
}

function cycleTheme() {
  const themes = ["sepia", "light", "dark", "eink"];
  const curIdx = themes.indexOf(state.theme);
  applyTheme(themes[(curIdx + 1) % themes.length]);
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

  elements.dropzone.innerHTML = `<p>Uploading and analyzing <strong>${escapeHtml(file.name)}</strong>...</p>`;
  try {
    const res = await fetch("/api/upload", { method: "POST", body: formData });
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

window.addEventListener("DOMContentLoaded", init);
