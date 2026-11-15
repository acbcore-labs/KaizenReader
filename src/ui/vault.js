/**
 * KaizenReader Sovereign IndexedDB Vault (`kaizen_sovereign_vault_v1`).
 *
 * Manages persistent on-device storage on the iPhone 16e and Mac:
 * - `books_meta`: Library index with per-chapter offline sprite status.
 * - `books_ast`: Complete Document AST JSON so books open in <15ms with zero Wi-Fi.
 * - `chapter_sprites`: Hardware-decoded `.m4a` AAC-LC audio Blobs + binary-searchable word timings.
 * - `user_state_sync`: Offline reading bookmarks, notes, and lexicon overrides with dirty-sync queue.
 */
(function (global) {
  "use strict";

  const DB_NAME = "kaizen_sovereign_vault_v1";
  const DB_VERSION = 1;

  let _dbPromise = null;

  function openVaultDB() {
    if (_dbPromise) return _dbPromise;
    _dbPromise = new Promise((resolve, reject) => {
      if (!global.indexedDB) {
        reject(new Error("IndexedDB not supported in this browser context"));
        return;
      }
      const req = global.indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains("books_meta")) {
          db.createObjectStore("books_meta", { keyPath: "id" });
        }
        if (!db.objectStoreNames.contains("books_ast")) {
          db.createObjectStore("books_ast", { keyPath: "id" });
        }
        if (!db.objectStoreNames.contains("chapter_sprites")) {
          const store = db.createObjectStore("chapter_sprites", { keyPath: "sprite_key" });
          store.createIndex("by_book", "book_id", { unique: false });
        }
        if (!db.objectStoreNames.contains("user_state_sync")) {
          db.createObjectStore("user_state_sync", { keyPath: "key" });
        }
      };
      req.onsuccess = (e) => resolve(e.target.result);
      req.onerror = (e) => reject(e.target.error);
    });
    return _dbPromise;
  }

  async function requestPersistentStorage() {
    let persisted = false;
    let quotaBytes = 0;
    let usageBytes = 0;
    try {
      if (navigator.storage && navigator.storage.persist) {
        persisted = await navigator.storage.persist();
      }
      if (navigator.storage && navigator.storage.estimate) {
        const est = await navigator.storage.estimate();
        quotaBytes = est.quota || 0;
        usageBytes = est.usage || 0;
      }
    } catch (e) {}
    return { persisted, quotaBytes, usageBytes };
  }

  function makeSpriteKey(bookId, chapterIndex, voice = "af_bella", speed = 1.0) {
    const normSpeed = Number(speed || 1.0).toFixed(2);
    return `${bookId}:${chapterIndex}:${voice}:${normSpeed}`;
  }

  async function putStore(storeName, value) {
    const db = await openVaultDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, "readwrite");
      tx.objectStore(storeName).put(value);
      tx.oncomplete = () => resolve(true);
      tx.onerror = (e) => reject(e.target.error);
    });
  }

  async function getStore(storeName, key) {
    const db = await openVaultDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, "readonly");
      const req = tx.objectStore(storeName).get(key);
      req.onsuccess = () => resolve(req.result || null);
      req.onerror = (e) => reject(e.target.error);
    });
  }

  async function getAllStore(storeName) {
    const db = await openVaultDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, "readonly");
      const req = tx.objectStore(storeName).getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = (e) => reject(e.target.error);
    });
  }

  async function deleteStoreKey(storeName, key) {
    const db = await openVaultDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, "readwrite");
      tx.objectStore(storeName).delete(key);
      tx.oncomplete = () => resolve(true);
      tx.onerror = (e) => reject(e.target.error);
    });
  }

  async function saveBookAstToVault(bookAst) {
    if (!bookAst || !bookAst.id) return;
    await putStore("books_ast", bookAst);
    const existingMeta = (await getStore("books_meta", bookAst.id)) || {};
    const meta = {
      id: bookAst.id,
      title: bookAst.title,
      author: bookAst.author || "Unknown",
      file_format: bookAst.file_format || "BOOK",
      chapters_count: (bookAst.chapters || []).length,
      total_words: bookAst.total_words || 0,
      total_sentences: bookAst.total_sentences || 0,
      is_sample: Boolean(bookAst.is_sample),
      packed_chapters: existingMeta.packed_chapters || [],
      vault_bytes: existingMeta.vault_bytes || 0,
      updated_at: Date.now() / 1000,
    };
    await putStore("books_meta", meta);
    return meta;
  }

  async function getBookAstFromVault(bookId) {
    return getStore("books_ast", bookId);
  }

  async function listVaultBooks() {
    return getAllStore("books_meta");
  }

  async function saveChapterSpriteToVault(bookId, chapterIndex, voice, speed, audioBlob, timings) {
    const sprite_key = makeSpriteKey(bookId, chapterIndex, voice, speed);
    const record = {
      sprite_key,
      book_id: bookId,
      chapter_index: chapterIndex,
      voice,
      speed: Number(speed || 1.0),
      audioBlob,
      timings,
      byteSize: audioBlob ? audioBlob.size : 0,
      createdAt: Date.now(),
    };
    await putStore("chapter_sprites", record);

    // Update book_meta packed_chapters list and total byte footprint
    const meta = await getStore("books_meta", bookId);
    if (meta) {
      const set = new Set(meta.packed_chapters || []);
      set.add(chapterIndex);
      meta.packed_chapters = Array.from(set).sort((a, b) => a - b);
      const allSprites = await getBookSpritesMeta(bookId);
      meta.vault_bytes = allSprites.reduce((acc, s) => acc + (s.byteSize || 0), 0);
      await putStore("books_meta", meta);
    }
    return record;
  }

  async function getChapterSpriteFromVault(bookId, chapterIndex, voice, speed) {
    const exactKey = makeSpriteKey(bookId, chapterIndex, voice, speed);
    const exact = await getStore("chapter_sprites", exactKey);
    if (exact) return exact;

    // Fallback: if offline and user changed speed or voice, find any packed sprite for this book + chapter
    const db = await openVaultDB();
    return new Promise((resolve) => {
      const tx = db.transaction("chapter_sprites", "readonly");
      const idx = tx.objectStore("chapter_sprites").index("by_book");
      const req = idx.getAll(bookId);
      req.onsuccess = () => {
        const matches = (req.result || []).filter((r) => r.chapter_index === chapterIndex);
        resolve(matches[0] || null);
      };
      req.onerror = () => resolve(null);
    });
  }

  async function getBookSpritesMeta(bookId) {
    const db = await openVaultDB();
    return new Promise((resolve) => {
      const tx = db.transaction("chapter_sprites", "readonly");
      const idx = tx.objectStore("chapter_sprites").index("by_book");
      const req = idx.getAll(bookId);
      req.onsuccess = () => {
        const list = (req.result || []).map((r) => ({
          sprite_key: r.sprite_key,
          chapter_index: r.chapter_index,
          voice: r.voice,
          speed: r.speed,
          byteSize: r.byteSize || 0,
          createdAt: r.createdAt,
        }));
        resolve(list);
      };
      req.onerror = () => resolve([]);
    });
  }

  async function removeBookFromVault(bookId) {
    await deleteStoreKey("books_meta", bookId);
    await deleteStoreKey("books_ast", bookId);
    const sprites = await getBookSpritesMeta(bookId);
    for (const s of sprites) {
      await deleteStoreKey("chapter_sprites", s.sprite_key);
    }
  }

  async function getVaultStats() {
    const est = await requestPersistentStorage();
    const books = await getAllStore("books_meta");
    const db = await openVaultDB();
    const spriteSummary = await new Promise((resolve) => {
      const tx = db.transaction("chapter_sprites", "readonly");
      const req = tx.objectStore("chapter_sprites").getAll();
      req.onsuccess = () => {
        const all = req.result || [];
        const bytes = all.reduce((acc, r) => acc + (r.byteSize || 0), 0);
        resolve({ count: all.length, bytes });
      };
      req.onerror = () => resolve({ count: 0, bytes: 0 });
    });

    return {
      persisted: est.persisted,
      quotaBytes: est.quotaBytes,
      usageBytes: est.usageBytes,
      booksCachedCount: books.length,
      spritesCachedCount: spriteSummary.count,
      spritesTotalBytes: spriteSummary.bytes,
    };
  }

  /**
   * Pack one or more chapters from the Mac Foundry into the local IndexedDB Sovereign Vault.
   */
  async function packChaptersFromFoundry(bookAst, chapterIndices, voice, speed, onProgress) {
    if (!bookAst || !bookAst.id) throw new Error("No active book loaded");
    await saveBookAstToVault(bookAst);

    const total = chapterIndices.length;
    let completed = 0;

    for (const chIdx of chapterIndices) {
      const exactKey = makeSpriteKey(bookAst.id, chIdx, voice, speed);
      const existing = await getStore("chapter_sprites", exactKey);
      if (existing && existing.audioBlob && existing.timings) {
        completed++;
        if (onProgress) {
          onProgress({
            phase: "cached",
            chapterIndex: chIdx,
            completedChapters: completed,
            totalChapters: total,
            byteSize: existing.byteSize || 0,
            message: `Ch ${chIdx + 1} already in Vault`,
          });
        }
        continue;
      }

      if (onProgress) {
        onProgress({
          phase: "synthesizing",
          chapterIndex: chIdx,
          completedChapters: completed,
          totalChapters: total,
          message: `Compiling Ch ${chIdx + 1} (.m4a AAC Sprite)...`,
        });
      }

      const qs = `voice=${encodeURIComponent(voice)}&speed=${encodeURIComponent(speed)}`;
      const timingsRes = await fetch(`/api/book/${bookAst.id}/chapter/${chIdx}/timings?${qs}`);
      if (!timingsRes.ok) {
        throw new Error(`Failed to compile Ch ${chIdx + 1} timings (HTTP ${timingsRes.status})`);
      }
      const timings = await timingsRes.json();

      const audioRes = await fetch(`/api/book/${bookAst.id}/chapter/${chIdx}/sprite?${qs}`);
      if (!audioRes.ok) {
        throw new Error(`Failed to download Ch ${chIdx + 1} sprite (HTTP ${audioRes.status})`);
      }
      const audioBlob = await audioRes.blob();
      await saveChapterSpriteToVault(bookAst.id, chIdx, voice, speed, audioBlob, timings);

      completed++;
      if (onProgress) {
        onProgress({
          phase: "cached",
          chapterIndex: chIdx,
          completedChapters: completed,
          totalChapters: total,
          rtf: timings.realtime_factor_x || 5.0,
          byteSize: audioBlob.size,
          message: `Locked Ch ${chIdx + 1} in Vault (${(audioBlob.size / (1024 * 1024)).toFixed(1)} MB)`,
        });
      }
    }
    return getVaultStats();
  }

  /**
   * Import a unpacked `.kzn` cartridge object (from `KaizenOfflineParser.unpackKznCartridgeClient`)
   * directly into the local IndexedDB Sovereign Vault.
   */
  async function importUnpackedCartridgeToVault(unpacked) {
    const { manifest, ast, lexicon, bookmark, sprites } = unpacked;
    await saveBookAstToVault(ast);
    const voice = manifest.voice || "af_bella";
    const speed = manifest.speed || 1.0;

    for (const sp of sprites || []) {
      await saveChapterSpriteToVault(
        ast.id,
        sp.chapter_index,
        voice,
        speed,
        sp.audioBlob,
        sp.timings
      );
    }

    if (lexicon && Object.keys(lexicon).length > 0) {
      const existingLex = (await getStore("user_state_sync", "lexicon"))?.value || {};
      await putStore("user_state_sync", {
        key: "lexicon",
        value: { ...existingLex, ...lexicon },
      });
    }

    if (bookmark && bookmark.position) {
      localStorage.setItem(`kaizen_chap_${ast.id}`, String(bookmark.position.chapter_index || 0));
      localStorage.setItem(`kaizen_sent_${ast.id}`, String(bookmark.position.sentence_index || 0));
    }

    return ast;
  }

  global.KaizenVault = {
    openVaultDB,
    requestPersistentStorage,
    makeSpriteKey,
    saveBookAstToVault,
    getBookAstFromVault,
    listVaultBooks,
    saveChapterSpriteToVault,
    getChapterSpriteFromVault,
    getBookSpritesMeta,
    removeBookFromVault,
    getVaultStats,
    packChaptersFromFoundry,
    importUnpackedCartridgeToVault,
    putSyncItem: (key, value) => putStore("user_state_sync", { key, value }),
    getSyncItem: async (key) => (await getStore("user_state_sync", key))?.value || null,
  };
})(window);
