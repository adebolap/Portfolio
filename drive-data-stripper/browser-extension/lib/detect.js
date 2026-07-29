/**
 * Client-side port of drive_stripper/proprietary.py and scaffold.py.
 *
 * Runs entirely inside the content script - no network calls, nothing
 * leaves the browser. Kept dependency-free (no bundler) so it can be loaded
 * directly as a classic content script.
 */
(function (global) {
  "use strict";

  var BUILTIN_PATTERNS = {
    email: /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g,
    aws_access_key: /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g,
    generic_api_key: /\b(?:sk|pk|rk|api|key)[-_][A-Za-z0-9]{16,}\b/gi,
    bearer_token: /\bBearer\s+[A-Za-z0-9._-]{20,}\b/g,
    private_key_block: /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g,
    ipv4: /\b(?:\d{1,3}\.){3}\d{1,3}\b/g,
    phone: /\b\+?\d[\d\s().-]{7,}\d\b/g,
    credit_card: /\b\d(?:[ -]?\d){12,15}\b/g,
    // last, so it only ever wins ties on spans nothing more specific claimed
    high_entropy_secret: /\b[A-Za-z0-9+/_-]{20,}\b/g
  };

  var DEFAULT_CATEGORIES = Object.keys(BUILTIN_PATTERNS);

  var HEX_CHARS = "0123456789abcdefABCDEF";
  // Tuned against real token shapes (GitHub/Slack/Stripe-style secrets score
  // ~5.0-5.3, hex secrets/git SHAs ~3.5-3.9) vs. common false positives
  // (camelCase/snake_case identifiers ~3.8-4.0, UUIDs without dashes ~3.25).
  // Entropy can't distinguish a real secret from a git SHA or session ID -
  // both are just random-looking strings - hence "medium" confidence rather
  // than redacting with the same certainty as an email or AWS key.
  var HEX_ENTROPY_THRESHOLD = 3.4;
  var GENERAL_ENTROPY_THRESHOLD = 4.2;

  function shannonEntropy(s) {
    if (!s) return 0;
    var counts = {};
    for (var i = 0; i < s.length; i++) counts[s[i]] = (counts[s[i]] || 0) + 1;
    var length = s.length;
    var entropy = 0;
    Object.keys(counts).forEach(function (ch) {
      var p = counts[ch] / length;
      entropy -= p * (Math.log(p) / Math.LN2);
    });
    return entropy;
  }

  function isHighEntropySecret(value) {
    var isHex = true;
    for (var i = 0; i < value.length; i++) {
      if (HEX_CHARS.indexOf(value[i]) === -1) {
        isHex = false;
        break;
      }
    }
    var threshold = isHex ? HEX_ENTROPY_THRESHOLD : GENERAL_ENTROPY_THRESHOLD;
    return shannonEntropy(value) >= threshold;
  }

  function luhnValid(digits) {
    if (!/^\d+$/.test(digits)) return false;
    var total = 0;
    var reversed = digits.split("").reverse();
    for (var i = 0; i < reversed.length; i++) {
      var d = parseInt(reversed[i], 10);
      if (i % 2 === 1) {
        d *= 2;
        if (d > 9) d -= 9;
      }
      total += d;
    }
    return total % 10 === 0;
  }

  function customTermPattern(term) {
    var escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp(escaped, "gi");
  }

  /**
   * @param {string} text
   * @param {string[]|null} categories - restrict to these built-in labels; null = all
   * @param {string[]} customTerms - literal, case-insensitive terms
   * @returns {Array<{label:string,start:number,end:number,value:string,confidence:string}>}
   */
  function detect(text, categories, customTerms) {
    var active = {};
    Object.keys(BUILTIN_PATTERNS).forEach(function (label) {
      if (!categories || categories.indexOf(label) !== -1) {
        active[label] = BUILTIN_PATTERNS[label];
      }
    });
    (customTerms || []).forEach(function (term) {
      term = term.trim();
      if (term) active["custom_term:" + term] = customTermPattern(term);
    });

    var matches = [];
    Object.keys(active).forEach(function (label) {
      var pattern = new RegExp(active[label].source, active[label].flags);
      var m;
      while ((m = pattern.exec(text)) !== null) {
        var value = m[0];
        if (m.index === pattern.lastIndex) pattern.lastIndex++; // guard zero-width matches
        if (label === "credit_card") {
          var digits = value.replace(/[ -]/g, "");
          if (digits.length < 13 || !luhnValid(digits)) continue;
        } else if (label === "high_entropy_secret" && !isHighEntropySecret(value)) {
          continue;
        }
        var confidence = label === "phone" || label === "high_entropy_secret" ? "medium" : "high";
        matches.push({ label: label, start: m.index, end: m.index + value.length, value: value, confidence: confidence });
      }
    });

    matches.sort(function (a, b) { return a.start - b.start; });
    return dropOverlaps(matches);
  }

  function dropOverlaps(matches) {
    var sorted = matches.slice().sort(function (a, b) {
      if (a.start !== b.start) return a.start - b.start;
      return (b.end - b.start) - (a.end - a.start);
    });
    var kept = [];
    var lastEnd = -1;
    sorted.forEach(function (m) {
      if (m.start >= lastEnd) {
        kept.push(m);
        lastEnd = m.end;
      }
    });
    return kept;
  }

  function replaceSpans(text, matches, makeReplacement) {
    var sorted = matches.slice().sort(function (a, b) { return a.start - b.start; });
    var out = [];
    var cursor = 0;
    sorted.forEach(function (m, i) {
      out.push(text.slice(cursor, m.start));
      out.push(makeReplacement(m, i));
      cursor = m.end;
    });
    out.push(text.slice(cursor));
    return out.join("");
  }

  function redact(text, matches) {
    return replaceSpans(text, matches, function () { return "[REDACTED]"; });
  }

  var TOKEN_RE = /\[\[SCAFFOLD:[^:\]]+:\d+\]\]/g;

  function applyScaffold(text, matches, indexOffset) {
    indexOffset = indexOffset || 0;
    var mapping = {};
    var scaffolded = replaceSpans(text, matches, function (m, i) {
      var token = "[[SCAFFOLD:" + m.label + ":" + (indexOffset + i) + "]]";
      mapping[token] = m.value;
      return token;
    });
    return { text: scaffolded, mapping: mapping, nextOffset: indexOffset + matches.length };
  }

  function restore(text, mapping) {
    var restored = text;
    Object.keys(mapping).forEach(function (token) {
      restored = restored.split(token).join(mapping[token]);
    });
    return restored;
  }

  function findRemainingTokens(text) {
    return text.match(TOKEN_RE) || [];
  }

  global.DriveShieldDetect = {
    DEFAULT_CATEGORIES: DEFAULT_CATEGORIES,
    detect: detect,
    redact: redact,
    applyScaffold: applyScaffold,
    restore: restore,
    findRemainingTokens: findRemainingTokens,
    luhnValid: luhnValid,
    shannonEntropy: shannonEntropy,
    isHighEntropySecret: isHighEntropySecret
  };
})(typeof window !== "undefined" ? window : globalThis);
