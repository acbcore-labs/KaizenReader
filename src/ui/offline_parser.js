/**
 * KaizenReader Autonomous Offline Document & `.kzn` Cartridge Parser.
 *
 * Allows the iPhone 16e to ingest `.kzn` Sovereign Cartridges as well as raw
 * `.txt`, `.md`, `.html`, and `.epub` files directly from the iOS Files app
 * with ZERO server or internet connectivity.
 */
(function (global) {
  "use strict";

  const PROTECTED_ABBRS = new Set([
    "mr", "mrs", "ms", "dr", "prof", "rev", "gen", "col", "capt", "lt", "sgt", "st", "mt", "jr", "sr",
    "ch", "chap", "sec", "vol", "vols", "bk", "pt", "fig", "figs", "eq", "fn", "app", "no", "nos", "p", "pp",
    "cf", "ca", "c", "ed", "eds", "ibid", "viz", "al", "eg", "ie", "etc", "vs", "v", "inc", "ltd",
  ]);

  async function sha256Hex12(buffer) {
    if (global.crypto && global.crypto.subtle) {
      const hashBuf = await global.crypto.subtle.digest("SHA-256", buffer);
      const arr = Array.from(new Uint8Array(hashBuf));
      return arr.map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 12);
    }
    // Deterministic FNV-1a fallback when SubtleCrypto is unavailable on non-HTTPS origin
    const bytes = new Uint8Array(buffer);
    let h1 = 0x811c9dc5;
    let h2 = 0x01000193;
    for (let i = 0; i < bytes.length; i++) {
      h1 ^= bytes[i];
      h1 = Math.imul(h1, 0x01000193) >>> 0;
      h2 ^= bytes[bytes.length - 1 - i];
      h2 = Math.imul(h2, 0x01000193) >>> 0;
    }
    return (h1.toString(16).padStart(8, "0") + h2.toString(16).padStart(8, "0")).slice(0, 12);
  }

  function splitIntoSentences(text) {
    if (!text) return [];
    const sentences = [];
    const n = text.length;
    let start = 0;
    let depth = 0;

    for (let i = 0; i < n; i++) {
      const ch = text[i];
      if ("([{".includes(ch)) depth++;
      else if (")]}".includes(ch)) depth = Math.max(0, depth - 1);

      if (depth === 0 && ".!?".includes(ch)) {
        if (ch === "." && ((i + 1 < n && text[i + 1] === ".") || (i > 0 && text[i - 1] === "."))) {
          continue;
        }
        let isAbbr = false;
        const prefix = text.slice(0, i + 1);
        const m = prefix.match(/([a-zA-Z]+)\.$/);
        if (m) {
          const w = m[1].toLowerCase();
          if (w.length === 1 || PROTECTED_ABBRS.has(w)) isAbbr = true;
        }
        if (!isAbbr && ch === "." && i + 1 < n && /\d/.test(text[i + 1])) {
          isAbbr = true;
        }
        if (!isAbbr) {
          let endPunc = i + 1;
          while (endPunc < n && `"'”’)]}`.includes(text[endPunc])) endPunc++;
          if (endPunc >= n || /\s/.test(text[endPunc])) {
            const rawS = text.slice(start, endPunc).trim();
            if (rawS) {
              const sStart = text.indexOf(rawS, start);
              sentences.push([rawS, sStart, sStart + rawS.length]);
            }
            start = endPunc;
            i = endPunc - 1;
          }
        }
      }
    }
    if (start < n) {
      const rem = text.slice(start).trim();
      if (rem) {
        const sStart = text.indexOf(rem, start);
        sentences.push([rem, sStart, sStart + rem.length]);
      }
    }
    return sentences;
  }

  function buildParagraphNode(rawText, chIdx, pIdx, forcedType = null) {
    let text = (rawText || "").trim();
    if (!text) return null;

    let nodeType = forcedType || "p";
    let isHeading = false;
    let isQuote = false;
    let isCode = false;

    if (!forcedType) {
      if (text.startsWith("# ")) {
        nodeType = "h1";
        isHeading = true;
        text = text.slice(2).trim();
      } else if (text.startsWith("## ")) {
        nodeType = "h2";
        isHeading = true;
        text = text.slice(3).trim();
      } else if (text.startsWith("### ")) {
        nodeType = "h3";
        isHeading = true;
        text = text.slice(4).trim();
      } else if (text.startsWith("> ")) {
        nodeType = "blockquote";
        isQuote = true;
        text = text.replace(/^>\s?/gm, "").trim();
      } else if (text.startsWith("```")) {
        nodeType = "code";
        isCode = true;
        text = text.replace(/^```[^\n]*\n?|\n?```$/g, "").trim();
      }
    } else {
      isHeading = ["h1", "h2", "h3", "h4"].includes(nodeType);
      isQuote = nodeType === "blockquote";
      isCode = nodeType === "code";
    }

    const sTuples = isCode ? [[text, 0, text.length]] : splitIntoSentences(text);
    const sentences = sTuples.map(([sText, cStart, cEnd], sIdx) => ({
      id: `s_${chIdx}_${pIdx}_${sIdx}`,
      text: sText,
      skip_tts: isCode,
      char_start: cStart,
      char_end: cEnd,
    }));

    return {
      id: `p_${chIdx}_${pIdx}`,
      text,
      node_type: nodeType,
      is_heading: isHeading,
      is_code: isCode,
      is_quote: isQuote,
      sentences,
    };
  }

  async function parseTextOrMarkdownOffline(file) {
    const buffer = await file.arrayBuffer();
    const docId = await sha256Hex12(buffer);
    const raw = new TextDecoder("utf-8").decode(buffer);
    const title = file.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");
    const ext = (file.name.split(".").pop() || "txt").toUpperCase();

    // Split into chapters on Markdown `# ` or `Chapter X` headings
    const lines = raw.replace(/\r\n/g, "\n").split("\n");
    const rawChapters = [];
    let curTitle = "Chapter 1";
    let curBlocks = [];

    for (const line of lines) {
      const hMatch = line.match(/^(?:#\s+(.+)|(Chapter\s+\d+.*))$/i);
      if (hMatch && curBlocks.join("\n").trim().length > 250) {
        rawChapters.push({ title: curTitle, body: curBlocks.join("\n") });
        curTitle = (hMatch[1] || hMatch[2]).trim();
        curBlocks = [line];
      } else {
        if (curBlocks.length === 0 && hMatch) {
          curTitle = (hMatch[1] || hMatch[2]).trim();
        }
        curBlocks.push(line);
      }
    }
    if (curBlocks.join("\n").trim()) {
      rawChapters.push({ title: curTitle, body: curBlocks.join("\n") });
    }

    let totalWords = 0;
    let totalSentences = 0;
    const chapters = rawChapters.map((rc, chIdx) => {
      const blocks = rc.body.split(/\n\s*\n/).map((b) => b.trim()).filter(Boolean);
      const paragraphs = [];
      blocks.forEach((b, pIdx) => {
        const pNode = buildParagraphNode(b, chIdx, pIdx);
        if (pNode && pNode.sentences.length) {
          paragraphs.push(pNode);
          totalWords += pNode.text.split(/\s+/).filter(Boolean).length;
          totalSentences += pNode.sentences.length;
        }
      });
      return {
        id: `ch_${chIdx}`,
        index: chIdx,
        title: rc.title || `Chapter ${chIdx + 1}`,
        category: "body",
        section_type: "chapter",
        chapter_number: chIdx + 1,
        badge_label: `Ch ${chIdx + 1}`,
        paragraphs,
      };
    });

    return {
      id: docId,
      title,
      author: "Local Offline Import",
      file_format: ext,
      is_sample: false,
      created_at: Date.now() / 1000,
      chapters,
      total_words: totalWords,
      total_sentences: totalSentences,
      total_body_chapters: chapters.length,
      has_toc: false,
    };
  }

  // Minimal zero-dependency ZIP Central Directory reader for `.kzn` and `.epub`
  async function readZipEntries(arrayBuffer) {
    const view = new DataView(arrayBuffer);
    const bytes = new Uint8Array(arrayBuffer);
    let eocdOffset = -1;
    for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65557); i--) {
      if (view.getUint32(i, true) === 0x06054b50) {
        eocdOffset = i;
        break;
      }
    }
    if (eocdOffset === -1) throw new Error("Not a valid ZIP/.kzn/.epub container");

    const cdCount = view.getUint16(eocdOffset + 10, true);
    const cdOffset = view.getUint32(eocdOffset + 16, true);
    const entries = new Map();

    let ptr = cdOffset;
    const decoder = new TextDecoder("utf-8");
    for (let i = 0; i < cdCount; i++) {
      if (view.getUint32(ptr, true) !== 0x02014b50) break;
      const method = view.getUint16(ptr + 10, true);
      const compSize = view.getUint32(ptr + 20, true);
      const uncompSize = view.getUint32(ptr + 24, true);
      const nameLen = view.getUint16(ptr + 28, true);
      const extraLen = view.getUint16(ptr + 30, true);
      const commentLen = view.getUint16(ptr + 32, true);
      const localHeaderOffset = view.getUint32(ptr + 42, true);
      const name = decoder.decode(bytes.subarray(ptr + 46, ptr + 46 + nameLen));

      entries.set(name, {
        name,
        method,
        compSize,
        uncompSize,
        localHeaderOffset,
        async extractBytes() {
          const lNameLen = view.getUint16(localHeaderOffset + 26, true);
          const lExtraLen = view.getUint16(localHeaderOffset + 28, true);
          const dataStart = localHeaderOffset + 30 + lNameLen + lExtraLen;
          const slice = bytes.subarray(dataStart, dataStart + compSize);
          if (method === 0) {
            return slice;
          }
          if (method === 8 && typeof DecompressionStream !== "undefined") {
            const ds = new DecompressionStream("deflate-raw");
            const writer = ds.writable.getWriter();
            writer.write(slice);
            writer.close();
            const resp = new Response(ds.readable);
            return new Uint8Array(await resp.arrayBuffer());
          }
          throw new Error(`Unsupported ZIP compression method ${method}`);
        },
        async extractText() {
          const raw = await this.extractBytes();
          return decoder.decode(raw);
        },
      });

      ptr += 46 + nameLen + extraLen + commentLen;
    }
    return entries;
  }

  async function unpackKznCartridgeClient(fileOrBuffer) {
    const buf = fileOrBuffer instanceof ArrayBuffer ? fileOrBuffer : await fileOrBuffer.arrayBuffer();
    const entries = await readZipEntries(buf);
    if (!entries.has("manifest.json") || !entries.has("ast.json")) {
      throw new Error("Invalid .kzn cartridge: missing manifest.json or ast.json");
    }

    const manifest = JSON.parse(await entries.get("manifest.json").extractText());
    const ast = JSON.parse(await entries.get("ast.json").extractText());
    const lexicon = entries.has("lexicon_snapshot.json")
      ? JSON.parse(await entries.get("lexicon_snapshot.json").extractText())
      : {};
    const bookmark = entries.has("state_bookmark.json")
      ? JSON.parse(await entries.get("state_bookmark.json").extractText())
      : null;

    const sprites = [];
    for (const chMeta of manifest.packed_chapters || []) {
      const audioEntry = entries.get(chMeta.audio_file);
      const timingsEntry = entries.get(chMeta.timings_file);
      if (audioEntry && timingsEntry) {
        const audioBytes = await audioEntry.extractBytes();
        const timingsJson = JSON.parse(await timingsEntry.extractText());
        const mime = chMeta.audio_file.endsWith(".m4a") ? "audio/mp4" : "audio/wav";
        sprites.push({
          chapter_index: chMeta.chapter_index,
          audioBlob: new Blob([audioBytes], { type: mime }),
          timings: timingsJson,
          byteSize: audioBytes.byteLength,
        });
      }
    }

    return { manifest, ast, lexicon, bookmark, sprites };
  }

  async function parseEpubOffline(file) {
    const buf = await file.arrayBuffer();
    const docId = await sha256Hex12(buf);
    const entries = await readZipEntries(buf);
    const domParser = new DOMParser();

    let opfPath = "content.opf";
    if (entries.has("META-INF/container.xml")) {
      const containerXml = await entries.get("META-INF/container.xml").extractText();
      const cDoc = domParser.parseFromString(containerXml, "application/xml");
      const rootfile = cDoc.querySelector("rootfile");
      if (rootfile && rootfile.getAttribute("full-path")) {
        opfPath = rootfile.getAttribute("full-path");
      }
    }

    if (!entries.has(opfPath)) {
      for (const k of entries.keys()) {
        if (k.endsWith(".opf")) {
          opfPath = k;
          break;
        }
      }
    }

    const opfDir = opfPath.includes("/") ? opfPath.slice(0, opfPath.lastIndexOf("/") + 1) : "";
    const opfXml = await entries.get(opfPath).extractText();
    const opfDoc = domParser.parseFromString(opfXml, "application/xml");

    const titleEl = opfDoc.querySelector("title, dc\\:title");
    const creatorEl = opfDoc.querySelector("creator, dc\\:creator");
    const bookTitle = (titleEl && titleEl.textContent.trim()) || file.name.replace(/\.epub$/i, "");
    const bookAuthor = (creatorEl && creatorEl.textContent.trim()) || "Unknown Author";

    const manifestMap = new Map();
    opfDoc.querySelectorAll("manifest > item").forEach((it) => {
      manifestMap.set(it.getAttribute("id"), it.getAttribute("href"));
    });

    const spineIds = [];
    opfDoc.querySelectorAll("spine > itemref").forEach((ref) => {
      spineIds.push(ref.getAttribute("idref"));
    });

    const chapters = [];
    let totalWords = 0;
    let totalSentences = 0;

    for (const idref of spineIds) {
      const href = manifestMap.get(idref);
      if (!href) continue;
      const fullPath = opfDir + decodeURIComponent(href.split("#")[0]);
      const entry = entries.get(fullPath) || entries.get(href);
      if (!entry) continue;

      const htmlStr = await entry.extractText();
      const hDoc = domParser.parseFromString(htmlStr, "text/html");
      const chIdx = chapters.length;
      const hEl = hDoc.querySelector("h1, h2, h3, title");
      const chTitle = (hEl && hEl.textContent.trim()) || `Chapter ${chIdx + 1}`;

      const paragraphs = [];
      const blocks = hDoc.querySelectorAll("h1, h2, h3, h4, p, blockquote, pre, li");
      blocks.forEach((bEl, pIdx) => {
        const tag = bEl.tagName.toLowerCase();
        const text = (bEl.textContent || "").replace(/\s+/g, " ").trim();
        if (!text || text.length < 2) return;
        const nodeType = ["h1", "h2", "h3", "h4", "blockquote"].includes(tag)
          ? tag
          : tag === "pre"
          ? "code"
          : "p";
        const pNode = buildParagraphNode(text, chIdx, pIdx, nodeType);
        if (pNode && pNode.sentences.length) {
          paragraphs.push(pNode);
          totalWords += text.split(/\s+/).filter(Boolean).length;
          totalSentences += pNode.sentences.length;
        }
      });

      if (paragraphs.length > 0) {
        chapters.push({
          id: `ch_${chIdx}`,
          index: chIdx,
          title: chTitle,
          category: "body",
          section_type: "chapter",
          chapter_number: chIdx + 1,
          badge_label: `Ch ${chIdx + 1}`,
          paragraphs,
        });
      }
    }

    return {
      id: docId,
      title: bookTitle,
      author: bookAuthor,
      file_format: "EPUB",
      is_sample: false,
      created_at: Date.now() / 1000,
      chapters,
      total_words: totalWords,
      total_sentences: totalSentences,
      total_body_chapters: chapters.length,
      has_toc: false,
    };
  }

  async function parseLocalFile(file) {
    const name = (file.name || "").toLowerCase();
    if (name.endsWith(".kzn")) {
      return { type: "cartridge", data: await unpackKznCartridgeClient(file) };
    }
    if (name.endsWith(".epub")) {
      return { type: "document", data: await parseEpubOffline(file) };
    }
    return { type: "document", data: await parseTextOrMarkdownOffline(file) };
  }

  global.KaizenOfflineParser = {
    parseLocalFile,
    unpackKznCartridgeClient,
    splitIntoSentences,
  };
})(window);
