"""End-to-end proof-of-concept for the content script's actual DOM behavior.

This sandbox's Chromium runs under a managed-profile policy that disables
extension permissions outright ("Your parent has disabled extension
permissions" - confirmed via chrome://extensions), which blocks the normal
`--load-extension` content-script injection mechanism regardless of the
extension's own code. That's an environment lockdown, not a defect here,
and Chrome's declarative content_scripts matching itself is a well-tested
platform feature, not something this project needs to re-prove.

What *is* worth proving end-to-end is the extension's own logic: does
content-script.js, running unmodified in a real browser DOM against a real
page, actually intercept a send, detect matches, rewrite the composer, and
restore a token echoed back in a reply? This test answers that by loading
the real lib/detect.js and content/content-script.js files into a normal
page via a minimal chrome.storage/chrome.runtime shim (an in-memory stand-in
for the extension APIs) instead of the blocked extension loader. Every
assertion exercises the actual shipped files, not a reimplementation.

Run with: python3 tests/e2e_test.py
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
EXT_DIR = HERE.parent
MOCK_HTML = (HERE / "mock_chat_page.html").read_text()

TEST_EMAIL = "jane.doe@acme.com"
TEST_MESSAGE = f"Can you review this?\nContact: {TEST_EMAIL}"

CHROME_SHIM = """
window.chrome = {
  storage: {
    local: {
      _data: {},
      get: function (keys, cb) {
        var out = {};
        (Array.isArray(keys) ? keys : [keys]).forEach(function (k) {
          if (k in window.chrome.storage.local._data) out[k] = window.chrome.storage.local._data[k];
        });
        cb(out);
      },
      set: function (obj, cb) {
        Object.assign(window.chrome.storage.local._data, obj);
        if (cb) cb();
      },
      remove: function (key, cb) {
        delete window.chrome.storage.local._data[key];
        if (cb) cb();
      }
    },
    onChanged: { addListener: function () {} }
  },
  runtime: {
    sendMessage: function () {}
  }
};
"""


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/opt/pw-browsers/chromium", headless=True)
        page = browser.new_page()
        page.on("pageerror", lambda exc: fail(f"page error: {exc}"))

        page.set_content(MOCK_HTML)
        page.add_script_tag(content=CHROME_SHIM)
        page.add_script_tag(path=str(EXT_DIR / "lib" / "detect.js"))
        page.add_script_tag(path=str(EXT_DIR / "content" / "content-script.js"))
        page.wait_for_function("() => !!window.DriveShieldDetect", timeout=5000)

        # --- 1. sending sensitive text gets intercepted ---
        page.fill("#composer", TEST_MESSAGE)
        page.click("#send-btn")
        page.wait_for_selector(".driveshield-banner", timeout=5000)

        sent_entries = page.query_selector_all(".sent-entry")
        if sent_entries:
            fail("message reached the page's send handler before being reviewed")
        print("OK: send was intercepted, banner shown")

        chip_texts = [el.inner_text() for el in page.query_selector_all(".driveshield-chip")]
        if "email" not in chip_texts:
            fail(f"expected an 'email' chip in the banner, got {chip_texts}")
        print("OK: email match surfaced in the banner:", chip_texts)

        # --- 2. Scaffold rewrites the composer, then user sends again ---
        page.click(".driveshield-btn-primary")  # "Scaffold"
        page.wait_for_selector(".driveshield-banner", state="detached", timeout=5000)

        composer_value = page.eval_on_selector("#composer", "el => el.value")
        if TEST_EMAIL in composer_value:
            fail(f"composer still contains the raw email after scaffolding: {composer_value!r}")
        if "[[SCAFFOLD:email:" not in composer_value:
            fail(f"composer does not contain a scaffold token: {composer_value!r}")
        print("OK: composer rewritten to a scaffold token:", composer_value.replace("\n", " | "))

        page.click("#send-btn")
        page.wait_for_timeout(200)
        sent_entries = page.query_selector_all(".sent-entry")
        if len(sent_entries) != 1:
            fail(f"expected exactly one sent message after resend, got {len(sent_entries)}")
        sent_text = sent_entries[0].inner_text()
        if TEST_EMAIL in sent_text:
            fail("the raw email was actually sent - scaffolding failed silently")
        print("OK: sanitized message actually sent:", sent_text.replace("\n", " | "))

        # --- 3. simulated assistant reply echoes the token; restore it ---
        token = None
        for word in sent_text.split():
            if word.startswith("[[SCAFFOLD:"):
                token = word
        if not token:
            fail("could not find scaffold token in sent text to simulate a reply with")

        page.evaluate("(t) => window.__injectReply('Sure, will follow up with ' + t)", token)
        page.wait_for_selector(".driveshield-token", timeout=5000)
        token_el_text = page.inner_text(".driveshield-token")
        if token_el_text != token:
            fail(f"wrapped token text mismatch: {token_el_text!r} vs {token!r}")
        print("OK: token in simulated reply was detected and wrapped:", token_el_text)

        page.click(".driveshield-token")
        page.wait_for_timeout(150)
        restored_text = page.inner_text(".assistant-reply")
        if TEST_EMAIL not in restored_text:
            fail(f"click-to-restore did not recover the original email: {restored_text!r}")
        print("OK: click-to-restore recovered the original value:", restored_text)

        # --- 4. "Send anyway" bypasses without touching the text ---
        page.fill("#composer", TEST_MESSAGE)
        page.click("#send-btn")
        page.wait_for_selector(".driveshield-banner", timeout=5000)
        page.click(".driveshield-btn-ghost")  # "Send anyway" - replays the send itself
        page.wait_for_selector(".driveshield-banner", state="detached", timeout=5000)
        page.wait_for_timeout(200)
        sent_entries = page.query_selector_all(".sent-entry")
        if len(sent_entries) != 2 or TEST_EMAIL not in sent_entries[1].inner_text():
            fail("'Send anyway' should replay the original send with the unmodified text")
        print("OK: 'Send anyway' replays the original send with the text untouched")

        browser.close()

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
