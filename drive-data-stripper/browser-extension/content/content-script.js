/**
 * Intercepts a chat site's "send" action, scans the composer text with
 * DriveShieldDetect (lib/detect.js, loaded before this file), and offers
 * Strip / Scaffold / Send anyway before anything leaves the compose box.
 *
 * Also watches the page for rendered scaffold tokens (a reply that echoed
 * one back) and offers an inline restore using the mapping saved for this
 * site - all via chrome.storage.local, never sent anywhere.
 *
 * Known fragility (see README): finding the "composer" and "send button"
 * is heuristic. Sites that change their DOM, or that use custom editors
 * hostile to synthetic `input` events, can defeat detection or the
 * text-rewrite step. This is a v1 scope boundary, not a hidden bug.
 */
(function () {
  "use strict";

  var D = window.DriveShieldDetect;
  if (!D) return;

  var SETTINGS_KEY = "driveshield_settings";
  var MAPPING_PREFIX = "driveshield_mapping_";
  var TOKEN_RE = /\[\[SCAFFOLD:[^:\]]+:\d+\]\]/g;

  var settings = { enabled: true, categories: null, customTerms: [] };
  var mapping = {};
  var mappingOffset = 0;
  var currentBanner = null;

  function mappingKey() {
    return MAPPING_PREFIX + location.hostname;
  }

  function loadState(cb) {
    chrome.storage.local.get([SETTINGS_KEY, mappingKey()], function (result) {
      if (result[SETTINGS_KEY]) settings = result[SETTINGS_KEY];
      if (result[mappingKey()]) {
        mapping = result[mappingKey()].mapping || {};
        mappingOffset = result[mappingKey()].offset || 0;
      }
      if (cb) cb();
    });
  }

  function persistMapping() {
    var record = {};
    record[mappingKey()] = { mapping: mapping, offset: mappingOffset };
    chrome.storage.local.set(record);
  }

  chrome.storage.onChanged.addListener(function (changes, area) {
    if (area === "local" && changes[SETTINGS_KEY]) {
      settings = changes[SETTINGS_KEY].newValue || settings;
    }
  });

  // ---------- reading/writing the composer ----------

  function isComposer(el) {
    if (!el || !el.tagName) return false;
    if (el.tagName === "TEXTAREA") return true;
    if (el.isContentEditable) return true;
    return false;
  }

  function getText(el) {
    if (el.tagName === "TEXTAREA") return el.value;
    return el.innerText || "";
  }

  function setText(el, text) {
    if (el.tagName === "TEXTAREA") {
      var setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
      setter.call(el, text);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      el.innerText = text;
      el.dispatchEvent(new InputEvent("input", { bubbles: true, data: text }));
    }
  }

  function looksLikeSendControl(el) {
    if (!el) return false;
    var label = (
      (el.getAttribute && (el.getAttribute("aria-label") || el.getAttribute("data-testid") || el.title)) || ""
    ).toLowerCase();
    if (label.indexOf("send") !== -1) return true;
    if (el.type === "submit") return true;
    return false;
  }

  function findComposerNear(el) {
    var container = el.closest("form") || el.closest("[class]") || document.body;
    return container.querySelector("textarea, [contenteditable='true']");
  }

  // ---------- intercept banner ----------

  function removeBanner() {
    if (currentBanner) {
      currentBanner.remove();
      currentBanner = null;
    }
  }

  function showBanner(target, matches, replay) {
    removeBanner();
    var categories = [];
    matches.forEach(function (m) {
      if (categories.indexOf(m.label) === -1) categories.push(m.label);
    });

    var banner = document.createElement("div");
    banner.className = "driveshield-banner";

    var head = document.createElement("div");
    head.className = "driveshield-head";
    head.innerHTML =
      '<span class="driveshield-badge">DriveShield</span><strong>Found ' +
      matches.length +
      (matches.length === 1 ? " item" : " items") +
      " before you send</strong>";
    banner.appendChild(head);

    var chips = document.createElement("div");
    chips.className = "driveshield-chips";
    categories.forEach(function (c) {
      var chip = document.createElement("span");
      chip.className = "driveshield-chip";
      chip.textContent = c;
      chips.appendChild(chip);
    });
    banner.appendChild(chips);

    var actions = document.createElement("div");
    actions.className = "driveshield-actions";
    actions.appendChild(makeButton("Scaffold", "driveshield-btn-primary", function () {
      applyAction("scaffold", target, matches, replay);
    }));
    actions.appendChild(makeButton("Strip", "driveshield-btn-secondary", function () {
      applyAction("strip", target, matches, replay);
    }));
    actions.appendChild(makeButton("Send anyway", "driveshield-btn-ghost", function () {
      applyAction("send", target, matches, replay);
    }));
    banner.appendChild(actions);

    target.insertAdjacentElement("beforebegin", banner);
    currentBanner = banner;
  }

  function makeButton(label, cls, onClick) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "driveshield-btn " + cls;
    btn.textContent = label;
    btn.addEventListener("click", onClick);
    return btn;
  }

  // The one message explicitly waved through by "Send anyway", checked by
  // exact target + text so the replayed event isn't intercepted again.
  var bypass = null;

  function applyAction(action, target, matches, replay) {
    if (action === "strip") {
      setText(target, D.redact(getText(target), matches));
      removeBanner();
    } else if (action === "scaffold") {
      var result = D.applyScaffold(getText(target), matches, mappingOffset);
      setText(target, result.text);
      Object.keys(result.mapping).forEach(function (k) {
        mapping[k] = result.mapping[k];
      });
      mappingOffset = result.nextOffset;
      persistMapping();
      removeBanner();
      // Strip/scaffold deliberately do NOT replay the send: the user
      // reviews the rewritten text and sends again explicitly.
    } else if (action === "send") {
      bypass = { target: target, text: getText(target) };
      removeBanner();
      replay();
    }
  }

  // ---------- intercepting the send action ----------

  function maybeIntercept(evt, target, replay) {
    if (!settings.enabled || !isComposer(target)) return;
    var text = getText(target);
    if (!text || !text.trim()) return;
    if (bypass && bypass.target === target && bypass.text === text) {
      bypass = null;
      return; // this exact message was already approved via "Send anyway"
    }
    var matches = D.detect(text, settings.categories, settings.customTerms);
    if (matches.length === 0) return;
    evt.preventDefault();
    evt.stopImmediatePropagation();
    showBanner(target, matches, replay);
    chrome.runtime.sendMessage({ type: "driveshield-matches", count: matches.length });
  }

  document.addEventListener(
    "keydown",
    function (evt) {
      if (evt.key !== "Enter" || evt.shiftKey || evt.isComposing) return;
      if (!isComposer(evt.target)) return;
      var composer = evt.target;
      maybeIntercept(evt, composer, function replayEnter() {
        composer.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
      });
    },
    true
  );

  document.addEventListener(
    "click",
    function (evt) {
      var control = evt.target.closest("button, [role='button']");
      if (!control || !looksLikeSendControl(control)) return;
      var target = findComposerNear(control);
      if (!target) return;
      maybeIntercept(evt, target, function replayClick() {
        control.click();
      });
    },
    true
  );

  // ---------- restoring scaffold tokens rendered in a reply ----------

  var floatingRestore = null;

  function wrapTokensInTextNode(node) {
    var text = node.nodeValue;
    TOKEN_RE.lastIndex = 0;
    if (!TOKEN_RE.test(text)) return;
    TOKEN_RE.lastIndex = 0;

    var frag = document.createDocumentFragment();
    var last = 0;
    var m;
    while ((m = TOKEN_RE.exec(text)) !== null) {
      frag.appendChild(document.createTextNode(text.slice(last, m.index)));
      var span = document.createElement("span");
      span.className = "driveshield-token";
      span.textContent = m[0];
      span.title = "Click to restore this value (DriveShield)";
      span.dataset.token = m[0];
      frag.appendChild(span);
      last = m.index + m[0].length;
    }
    frag.appendChild(document.createTextNode(text.slice(last)));
    node.parentNode.replaceChild(frag, node);
  }

  // scanForTokens both reads and writes the observed subtree (wrapping
  // tokens, adding/removing the floating button). Without disconnecting
  // first, those writes would themselves fire the observer and loop
  // forever - every DriveShield-caused mutation must happen with the
  // observer paused.
  function withObserverPaused(fn) {
    observer.disconnect();
    try {
      fn();
    } finally {
      observer.observe(document.body, { childList: true, subtree: true });
    }
  }

  function scanForTokens(root) {
    withObserverPaused(function () {
      var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode: function (node) {
          if (!node.nodeValue || node.nodeValue.indexOf("[[SCAFFOLD:") === -1) {
            return NodeFilter.FILTER_REJECT;
          }
          if (node.parentElement && node.parentElement.closest(".driveshield-banner, .driveshield-token")) {
            return NodeFilter.FILTER_REJECT;
          }
          return NodeFilter.FILTER_ACCEPT;
        }
      });
      var hits = [];
      var n;
      while ((n = walker.nextNode())) hits.push(n);
      hits.forEach(wrapTokensInTextNode);
      updateFloatingRestore();
    });
  }

  function updateFloatingRestore() {
    var remaining = document.querySelectorAll(".driveshield-token:not(.driveshield-restored)");
    if (remaining.length === 0) {
      if (floatingRestore) {
        floatingRestore.remove();
        floatingRestore = null;
      }
      return;
    }
    if (!floatingRestore) {
      floatingRestore = document.createElement("button");
      floatingRestore.type = "button";
      floatingRestore.className = "driveshield-restore-all";
      floatingRestore.addEventListener("click", function () {
        withObserverPaused(function () {
          document.querySelectorAll(".driveshield-token:not(.driveshield-restored)").forEach(restoreToken);
        });
        updateFloatingRestore();
      });
      document.body.appendChild(floatingRestore);
    }
    var label = "Restore " + remaining.length + (remaining.length === 1 ? " value" : " values") + " (DriveShield)";
    if (floatingRestore.textContent !== label) floatingRestore.textContent = label;
  }

  function restoreToken(tokenEl) {
    var token = tokenEl.dataset.token;
    if (mapping[token] === undefined) return;
    tokenEl.textContent = mapping[token];
    tokenEl.classList.add("driveshield-restored");
    tokenEl.removeAttribute("title");
  }

  document.addEventListener("click", function (evt) {
    var tok = evt.target.closest(".driveshield-token");
    if (tok) {
      withObserverPaused(function () {
        restoreToken(tok);
      });
      updateFloatingRestore();
    }
  });

  var observer = new MutationObserver(function (mutations) {
    for (var i = 0; i < mutations.length; i++) {
      if (mutations[i].addedNodes.length) {
        scanForTokens(document.body);
        return;
      }
    }
  });

  loadState(function () {
    observer.observe(document.body, { childList: true, subtree: true });
    scanForTokens(document.body);
  });
})();
