/**
 * Minimal MV3 service worker: seeds default settings on install, and shows
 * a badge count of matches caught on the active tab. No network access, no
 * persistent state beyond chrome.storage.
 */

const DEFAULT_SETTINGS = {
  enabled: true,
  categories: null, // null = all built-in categories
  customTerms: []
};

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(["driveshield_settings"], (result) => {
    if (!result.driveshield_settings) {
      chrome.storage.local.set({ driveshield_settings: DEFAULT_SETTINGS });
    }
  });
});

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message && message.type === "driveshield-matches" && sender.tab && sender.tab.id != null) {
    chrome.action.setBadgeText({ tabId: sender.tab.id, text: String(message.count) });
    chrome.action.setBadgeBackgroundColor({ tabId: sender.tab.id, color: "#1B6F63" });
  }
});
