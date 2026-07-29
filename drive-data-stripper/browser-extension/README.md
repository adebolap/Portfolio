# DriveShield (browser extension concept)

A Manifest V3 browser extension that intercepts sensitive text before it's
sent to an AI chat, and lets you strip it, scaffold it (reversible
placeholder tokens, restorable when a reply echoes them back), or send it
anyway. This is the browser-extension direction for `drive-data-stripper`:
the CLI/web tool requires remembering to run it first; this catches the
moment of risk directly where it happens.

**Interactive UX mockup** (what the intercept banner and restore flow look
like) is linked from the project history - see the CHANGELOG or ask for the
artifact link if you don't have it; the mockup isn't part of this repo since
it embeds ~470KB of base64 font data that doesn't belong in version control.

## Status: proof of concept, not published

This has not been submitted to the Chrome Web Store. It's built and tested
(see below) but distributed only as source - load it unpacked to try it.

## Scope (v1)

- **Text-paste interception only.** File uploads aren't intercepted - the
  Python tool's format handlers (Pillow, python-docx, pypdf, python-pptx)
  don't run in a browser. Porting those is a real future phase (WASM builds
  or pure-JS parsers per format), not attempted here.
- **Detection is 100% client-side.** `lib/detect.js` is a direct port of
  `drive_stripper/proprietary.py` (same regex patterns, same Luhn check for
  credit cards, same confidence levels) plus the scaffold token
  apply/restore logic from `scaffold.py`. No network calls, nothing leaves
  the browser - the mapping between a scaffold token and its real value
  lives only in `chrome.storage.local`, scoped per-site.
- **No metadata engine at all.** File metadata stripping (EXIF, docProps)
  needs the same Python libraries as above; there's nothing analogous here
  yet.
- **DOM-matching is heuristic and will need maintenance.** Finding "the
  compose box" and "the send control" on a real site is done via a generic
  fallback (any `<textarea>`/`contenteditable`, any button/role="button"
  whose label/testid/title contains "send") since there's no stable public
  API for this. Sites that change their markup, or editors that reject
  synthetic `input` events (a real risk for heavily-controlled React
  inputs), can defeat detection or the text-rewrite step silently. This is
  a named scope boundary, not a hidden bug.

## Load it

1. `chrome://extensions` → enable Developer mode → **Load unpacked** →
   select this `browser-extension/` folder.
2. Visit a matched site (chatgpt.com, chat.openai.com, claude.ai,
   gemini.google.com - edit `manifest.json`'s `content_scripts.matches` to
   add others).
3. Type or paste something containing an email/API key/etc. and try to
   send it.

## Architecture

```
manifest.json              MV3 manifest - minimal permissions ("storage" only)
lib/detect.js               ported detection + scaffold engine (no deps)
content/content-script.js   intercepts send, shows the banner, restores tokens
content/inject.css          banner/token/restore-button styling
popup/                      settings UI: categories, custom terms, enable toggle
background/service-worker.js  seeds default settings, sets the badge count
icons/                       generated via Pillow (see git history), teal shield mark
```

**Interception flow**: a capture-phase `keydown`(Enter) and `click` listener
on `document` watch for a send attempt. If the composer text has matches,
the event is prevented and a banner offers **Scaffold** / **Strip** / **Send
anyway**. Scaffold and Strip rewrite the composer text and deliberately do
*not* auto-resend - the user reviews the result and sends again explicitly.
**Send anyway** is different: it records a one-time bypass for that exact
`(element, text)` pair and replays the original event (a real `.click()` on
the button, or a synthetic Enter `keydown`), so the underlying site's send
logic actually runs - without that replay, the user would have to click
twice for no reason.

**Restore flow**: a `MutationObserver` watches the page for
`[[SCAFFOLD:label:n]]` tokens appearing anywhere (e.g. echoed back in a
reply), wraps each in a clickable span, and shows a floating "Restore N
values" button. Restoring is a simple text substitution from
`chrome.storage.local`, per-site.

## Tests

Two layers, both real - neither reimplements the logic to test it:

```bash
node --test tests/detect.test.js   # 12 parity tests: JS engine vs. the Python one
python3 tests/e2e_test.py          # DOM behavior test, see below
```

`e2e_test.py` loads the *actual* `lib/detect.js` and `content/content-script.js`
files into a real Chromium page (via Playwright) against a small mock chat
page (`tests/mock_chat_page.html`), with a minimal `chrome.storage`/`chrome.runtime`
shim standing in for the extension APIs. It drives the full loop: send
intercepted → scaffold → real resend → simulated reply echoes the token →
click-to-restore → "send anyway" replays the original send. All seven
checks currently pass.

**Why a shim instead of loading the real unpacked extension**: the sandbox
this was built in runs Chromium under a managed-profile policy that
disables extension permissions outright ("Your parent has disabled
extension permissions" - visible on `chrome://extensions`), which blocks
`--load-extension` content-script injection regardless of the extension's
own code. That's an environment lockdown, not a defect - Chrome's
declarative `content_scripts` matching is a well-tested platform feature,
not something this project needs to re-prove. What's actually worth testing
end-to-end is *this extension's own logic*, which the shim approach does
against the real files. On an unrestricted Chrome profile, `--load-extension`
works normally (that combination was verified separately: the service
worker registers correctly), and this test would fully exercise the
declarative injection path too, without needing the shim.

**A real bug this caught**: initial versions of `updateFloatingRestore()`
unconditionally wrote to the floating button's `textContent` on every call.
Since that call happens from inside the same `MutationObserver` callback
that watches the page for changes, this created an infinite mutation → scan
→ mutation loop that froze the tab the moment any DOM change occurred while
the restore button was visible - which is inevitable on a real chat page.
Fixed by disconnecting the observer around DriveShield's own writes
(`withObserverPaused` in `content-script.js`). Left here as a reminder that
"looked right in the mockup" and "survives a real event loop" are different
bars.

## Known limitations (being upfront)

- No file-upload interception (see Scope above).
- No entropy-based or ML/NER detection - same ceiling as the Python tool:
  regex catches known *shapes*, not context-dependent secrets or plain
  names/addresses. See the project discussion on reliability for what
  layering on top of this would take (entropy checks, local NER, org
  policy, network-level DLP) - this extension is one layer, not a complete
  answer.
- Not published to any extension store; no auto-update mechanism.
- DOM-matching heuristics will drift as target sites change their markup.
