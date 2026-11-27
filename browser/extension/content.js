(() => {
  "use strict";

  // Never read form controls, editable elements, password fields, or input values.
  const collectVisibleText = () => {
    if (document.visibilityState !== "visible") return "";
    const body = document.body;
    if (!body) return "";
    const clone = body.cloneNode(true);
    clone.querySelectorAll(
      "script, style, noscript, input, textarea, select, button, " +
      "[contenteditable='true'], [role='textbox'], [autocomplete='current-password'], " +
      "[type='password']"
    ).forEach((element) => element.remove());
    return (clone.innerText || clone.textContent || "").replace(/\s+/g, " ").trim().slice(0, 100000);
  };

  const sendSnapshot = () => {
    const text = collectVisibleText();
    if (!text) return;
    chrome.runtime.sendMessage({
      type: "capture_page",
      url: location.href,
      page_title: document.title || "Untitled page",
      content_text: text
    });
  };

  sendSnapshot();
})();
