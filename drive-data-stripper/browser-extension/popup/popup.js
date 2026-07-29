(function () {
  "use strict";

  var SETTINGS_KEY = "driveshield_settings";
  var MAPPING_PREFIX = "driveshield_mapping_";
  var CATEGORIES = window.DriveShieldDetect.DEFAULT_CATEGORIES;

  var enabledInput = document.getElementById("enabled");
  var categoriesFieldset = document.getElementById("categories");
  var customTermsInput = document.getElementById("custom-terms");
  var statusEl = document.getElementById("status");

  CATEGORIES.forEach(function (category) {
    var label = document.createElement("label");
    var checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = category;
    checkbox.className = "category-checkbox";
    label.appendChild(checkbox);
    label.appendChild(document.createTextNode(category));
    categoriesFieldset.appendChild(label);
  });

  function getSelectedCategories() {
    var boxes = document.querySelectorAll(".category-checkbox");
    var selected = [];
    boxes.forEach(function (box) {
      if (box.checked) selected.push(box.value);
    });
    // all checked (or none checked) both mean "scan everything"
    return selected.length === 0 || selected.length === CATEGORIES.length ? null : selected;
  }

  function applySettingsToForm(settings) {
    enabledInput.checked = settings.enabled !== false;
    var boxes = document.querySelectorAll(".category-checkbox");
    boxes.forEach(function (box) {
      box.checked = !settings.categories || settings.categories.indexOf(box.value) !== -1;
    });
    customTermsInput.value = (settings.customTerms || []).join(", ");
  }

  chrome.storage.local.get([SETTINGS_KEY], function (result) {
    applySettingsToForm(result[SETTINGS_KEY] || { enabled: true, categories: null, customTerms: [] });
  });

  document.getElementById("save").addEventListener("click", function () {
    var settings = {
      enabled: enabledInput.checked,
      categories: getSelectedCategories(),
      customTerms: customTermsInput.value
        .split(",")
        .map(function (t) { return t.trim(); })
        .filter(Boolean)
    };
    var record = {};
    record[SETTINGS_KEY] = settings;
    chrome.storage.local.set(record, function () {
      statusEl.textContent = "Saved.";
      setTimeout(function () { statusEl.textContent = ""; }, 1500);
    });
  });

  document.getElementById("clear-mapping").addEventListener("click", function () {
    chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
      if (!tabs[0] || !tabs[0].url) return;
      var hostname;
      try {
        hostname = new URL(tabs[0].url).hostname;
      } catch (e) {
        return;
      }
      chrome.storage.local.remove(MAPPING_PREFIX + hostname, function () {
        statusEl.textContent = "Cleared mapping for " + hostname + ".";
        setTimeout(function () { statusEl.textContent = ""; }, 2000);
      });
    });
  });
})();
