/**
 * KaizenReader Client-Side Semantic Normalizer, IPA Compiler & W3C SSML Bridge.
 *
 * Mirrors `src/tts/normalizer.py` and `src/tts/lexicon.py` 1:1 in browser JS so that:
 * 1. On-device Apple Neural Live TTS (`window.speechSynthesis`) receives the exact same
 *    Roman numeral, currency, biblical citation, unit, and homograph disambiguation
 *    even when 100% offline with the Mac powered off.
 * 2. The Floating Inline Phonetic & IPA Lens can compile respellings (`muh-NASS-uh` -> `/mənˈæsə/`),
 *    generate syllable stress pills, and build W3C SSML `<phoneme alphabet="ipa">` payloads locally.
 */
(function (global) {
  "use strict";

  const ROMAN_MAP = {
    I: "1", II: "2", III: "3", IV: "4", V: "5",
    VI: "6", VII: "7", VIII: "8", IX: "9", X: "10",
    XI: "11", XII: "12", XIII: "13", XIV: "14", XV: "15",
    XVI: "16", XVII: "17", XVIII: "18", XIX: "19", XX: "20",
    XXI: "21", XXII: "22", XXIII: "23", XXIV: "24", XXV: "25",
    XXX: "30", XL: "40", L: "50", LX: "60", LXX: "70", LXXX: "80", XC: "90", C: "100",
  };

  const ORDINALS = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth",
    6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth",
    11: "eleventh", 12: "twelfth", 13: "thirteenth", 14: "fourteenth",
    15: "fifteenth", 16: "sixteenth", 17: "seventeenth", 18: "eighteenth",
    19: "nineteenth", 20: "twentieth",
  };

  const PHONETIC_RULES = [
    ["tsh", "ʧ"], ["dzh", "ʤ"], ["eye", "aɪ"], ["igh", "aɪ"],
    ["air", "ɛɹ"], ["ear", "ɪɹ"], ["oor", "ʊɹ"], ["yoo", "juː"],
    ["yur", "jʊɹ"], ["ahr", "ɑːɹ"], ["awr", "ɔːɹ"], ["sh", "ʃ"],
    ["zh", "ʒ"], ["ch", "ʧ"], ["th", "θ"], ["dh", "ð"], ["ng", "ŋ"],
    ["ah", "ɑː"], ["aw", "ɔː"], ["ay", "eɪ"], ["ee", "iː"], ["oo", "uː"],
    ["oh", "oʊ"], ["ow", "aʊ"], ["oy", "ɔɪ"], ["oi", "ɔɪ"], ["ur", "ɜːɹ"],
    ["er", "ɚ"], ["uh", "ə"], ["ih", "ɪ"], ["eh", "ɛ"], ["ae", "eɪ"],
    ["qu", "kw"], ["ks", "ks"],
  ];

  const SINGLE_CHAR_MAP = {
    a: "æ", b: "b", c: "k", d: "d", e: "ɛ", f: "f", g: "ɡ", h: "h",
    i: "ɪ", j: "ʤ", k: "k", l: "l", m: "m", n: "n", o: "ɑː", p: "p",
    q: "k", r: "ɹ", s: "s", t: "t", u: "ʌ", v: "v", w: "w", x: "ks",
    y: "j", z: "z",
  };

  const IPA_INDICATORS = new Set(Array.from("əɚɛɜɪʊʌɑɔæθðʃʒʧʤŋɹɡˈˌːɐɒɨɯɲɳɸɻɽɾʁʂʈʋʎʒʔʝβχ"));

  function isIpa(val) {
    const v = (val || "").trim();
    if (v.length >= 2 && v.startsWith("/") && v.endsWith("/")) return true;
    for (const ch of v) {
      if (IPA_INDICATORS.has(ch)) return true;
    }
    return false;
  }

  function sanitizeIpa(ipa) {
    return (ipa || "").trim().replace(/^\/+|\/+$/g, "").replace(/r/g, "ɹ");
  }

  function compileSyllable(low, stressed) {
    const out = [];
    let i = 0;
    const n = low.length;
    while (i < n) {
      let matched = false;
      for (const [pat, rep] of PHONETIC_RULES) {
        if (low.startsWith(pat, i)) {
          if (pat === "uh" && stressed) out.push("ʌ");
          else if (pat === "er" && stressed) out.push("ɜːɹ");
          else out.push(rep);
          i += pat.length;
          matched = true;
          break;
        }
      }
      if (!matched) {
        const ch = low[i];
        if (ch === "u" && !stressed) out.push("ə");
        else out.push(SINGLE_CHAR_MAP[ch] || ch);
        i += 1;
      }
    }
    return out.join("").replace(/([bdfɡklmnpɹstvz])\1+/g, "$1");
  }

  function respellingToIpa(respelling) {
    const raw = (respelling || "").trim();
    if (!raw) return "";
    if (isIpa(raw)) return sanitizeIpa(raw);

    const wordIpas = [];
    for (const word of raw.split(/\s+/)) {
      const syllables = word.split(/[-·]/).filter(Boolean);
      const sylIpas = [];
      syllables.forEach((syl) => {
        const letters = syl.replace(/[^a-zA-Z']/g, "");
        if (!letters) return;
        const isStressed =
          letters === letters.toUpperCase() &&
          letters.length >= 1 &&
          (syllables.length > 1 || letters.length > 1);
        let ipaSyl = compileSyllable(letters.toLowerCase(), isStressed);
        if (isStressed) {
          const m = ipaSyl.match(/[aeiouəɚɛɜɪʊʌɑɔæ]/);
          if (m && m.index > 0) {
            ipaSyl = ipaSyl.slice(0, m.index) + "ˈ" + ipaSyl.slice(m.index);
          } else {
            ipaSyl = "ˈ" + ipaSyl;
          }
        }
        sylIpas.push(ipaSyl);
      });
      if (sylIpas.length) wordIpas.push(sylIpas.join(""));
    }
    return sanitizeIpa(wordIpas.join(" "));
  }

  function ipaToReadableRespelling(ipa) {
    let s = (ipa || "").replace(/^\/+|\/+$/g, "");
    const map = [
      ["ʃ", "sh"], ["ʒ", "zh"], ["ʧ", "ch"], ["ʤ", "j"], ["θ", "th"], ["ð", "th"],
      ["ŋ", "ng"], ["ɑːɹ", "ahr"], ["ɔːɹ", "or"], ["ɜːɹ", "ur"], ["ɑː", "ah"],
      ["ɔː", "aw"], ["iː", "ee"], ["uː", "oo"], ["eɪ", "ay"], ["aɪ", "eye"],
      ["ɔɪ", "oy"], ["oʊ", "oh"], ["aʊ", "ow"], ["ɛ", "eh"], ["ɪ", "ih"],
      ["æ", "a"], ["ʌ", "uh"], ["ə", "uh"], ["ɚ", "er"], ["ɹ", "r"], ["ɡ", "g"],
      ["ˈ", ""], ["ˌ", ""], ["ː", ""],
    ];
    for (const [k, v] of map) {
      s = s.split(k).join(v);
    }
    return s.replace(/[^a-zA-Z\s'-]/g, "").trim() || ipa.replace(/^\/+|\/+$/g, "");
  }

  function splitWordIntoSyllables(word) {
    const clean = (word || "").replace(/[^a-zA-Z]/g, "");
    if (clean.length <= 3) return [clean || word];
    const m = clean.match(/[^aeiouyAEIOUY]*[aeiouyAEIOUY]+(?:[^aeiouyAEIOUY](?=[aeiouyAEIOUY])|[^aeiouyAEIOUY]*$)/g);
    return m && m.length ? m : [clean];
  }

  function buildStressVariants(word) {
    const syllables = splitWordIntoSyllables(word);
    return syllables.map((_, idx) => {
      const respelling = syllables
        .map((s, i) => (i === idx ? s.toUpperCase() : s.toLowerCase()))
        .join("-");
      const ipa = respellingToIpa(respelling);
      return {
        stressed_index: idx,
        respelling,
        ipa: ipa ? `/${ipa}/` : "",
      };
    });
  }

  function normalizeTextForTts(rawText, lexiconMap = {}) {
    if (!rawText) return "";
    let text = rawText;

    // 1. Unhyphenate broken line wraps & strip footnote brackets
    text = text.replace(/(\b[a-zA-Z]{2,})-\s*\n\s*([a-zA-Z]{2,}\b)/g, "$1$2");
    text = text.replace(/\[\s*\d+(?:\s*,\s*\d+)*\s*\]/g, "");

    // 2. Structural Roman numerals & monarchs
    text = text.replace(
      /\b(Chapter|Section|Book|Part|Volume|Act|Scene|Ch|Chap|Sec|Pt|Vol)\.?\s+([IVXLCDM]+)\b/gi,
      (_, prefix, r) => `${prefix} ${ROMAN_MAP[r.toUpperCase()] || r}`
    );
    text = text.replace(
      /\b(Henry|Louis|Charles|George|Edward|Richard|Philip|James|William|Elizabeth)\s+(II|III|IV|V|VI|VII|VIII|IX|X|XI|XII|XIII|XIV|XV|XVI)\b/g,
      (m, name, r) => {
        const n = ROMAN_MAP[r.toUpperCase()];
        return n ? `${name} the ${ORDINALS[parseInt(n, 10)] || n}` : m;
      }
    );

    // 3. Numbered Biblical / Classical books & chapter:verse citations
    const bookOrdinals = { "1": "First", "2": "Second", "3": "Third" };
    text = text.replace(
      /\b([123])\s+(Enoch|Baruch|Maccabees|Kings|Chronicles|Samuel|Corinthians|Thessalonians|Timothy|Peter|John|Esdras)\b/g,
      (_, num, bk) => `${bookOrdinals[num]} ${bk}`
    );
    text = text.replace(
      /\b(Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Psalm|Psalms|Proverbs|Isaiah|Jeremiah|Matthew|Mark|Luke|John|Romans|Corinthians|Galatians|Ephesians|Philippians|Colossians|Thessalonians|Timothy|Titus|Hebrews|James|Peter|Revelation|Enoch|Baruch|Maccabees)\s+(\d+)[:.](\d+)\b/g,
      "$1, chapter $2, verse $3"
    );

    // 4. Units, percentages, and abbreviations
    text = text.replace(/(\d+(?:\.\d+)?)\s*%/g, "$1 percent");
    text = text.replace(/\b(\d+(?:\.\d+)?)\s*GB\/s\b/g, "$1 gigabytes per second");
    text = text.replace(/\b(\d+(?:\.\d+)?)\s*MB\/s\b/g, "$1 megabytes per second");
    text = text.replace(/\bDr\./g, "Doctor");
    text = text.replace(/\bMr\./g, "Mister");
    text = text.replace(/\bMrs\./g, "Missus");
    text = text.replace(/\bProf\./g, "Professor");
    text = text.replace(/\bSt\.\s+(?=[A-Z])/g, "Saint ");
    text = text.replace(/\be\.g\.?/gi, "for example,");
    text = text.replace(/\bi\.e\.?/gi, "that is,");
    text = text.replace(/\bcf\./gi, "compare");

    // 5. Apply custom lexicon overrides as natural readable hints for Web Speech API
    const keys = Object.keys(lexiconMap).sort((a, b) => b.length - a.length);
    for (const k of keys) {
      const val = lexiconMap[k];
      if (!val) continue;
      const hint = isIpa(val) ? ipaToReadableRespelling(val) : val.replace(/[-·]/g, " ").toLowerCase();
      const escaped = k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      text = text.replace(new RegExp(`\\b${escaped}\\b`, "gi"), hint);
    }

    return text.replace(/\s+/g, " ").trim();
  }

  global.KaizenPhonetics = {
    isIpa,
    sanitizeIpa,
    respellingToIpa,
    ipaToReadableRespelling,
    splitWordIntoSyllables,
    buildStressVariants,
    normalizeTextForTts,
  };
})(window);
