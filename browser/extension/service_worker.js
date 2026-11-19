"use strict";

const NATIVE_HOST = "com.contexttrace.auth";
const API_BASE = "http://127.0.0.1:8765";
const MAX_CAPTURED_URL_LENGTH = 4096;
const MAX_CAPTURED_TITLE_LENGTH = 500;
const MAX_CAPTURED_TEXT_LENGTH = 100000;
const recentCaptures = new Map();

function getToken() {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendNativeMessage(NATIVE_HOST, { type: "get_token" }, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error("ContextTrace native host is not available"));
        return;
      }
      if (!response || response.ok !== true || typeof response.token !== "string") {
        reject(new Error("ContextTrace authentication is unavailable"));
        return;
      }
      resolve(response.token);
    });
  });
}

async function apiPost(path, payload, token) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  if (!response.ok) throw new Error(`ContextTrace API returned ${response.status}`);
  return response.json();
}

async function capturePage(message, sender) {
  if (!sender.tab || !sender.tab.active && sender.tab.active !== undefined) return;
  if (typeof message.url !== "string" || message.url.length > MAX_CAPTURED_URL_LENGTH) return;
  if (typeof message.page_title !== "string" || typeof message.content_text !== "string") return;
  if (!/^https?:\/\//i.test(message.url)) return;

  const tabId = sender.tab.id;
  const signature = `${message.url}\n${message.page_title}\n${message.content_text.length}`;
  if (recentCaptures.get(tabId) === signature) return;
  recentCaptures.set(tabId, signature);

  const token = await getToken();
  const source = await apiPost("/browser/source", {
    browser: "chrome",
    url: message.url,
    page_title: message.page_title.slice(0, MAX_CAPTURED_TITLE_LENGTH)
  }, token);
  const sourceId = source?.data?.id;
  if (!Number.isInteger(sourceId)) throw new Error("Invalid source response");

  const content = message.content_text.slice(0, MAX_CAPTURED_TEXT_LENGTH);
  await apiPost("/browser/content", {
    browser_source_id: sourceId,
    content_text: content
  }, token);
}

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message?.type !== "capture_page") return;
  capturePage(message, sender).catch(() => {
    // Do not log page contents, URLs, or credentials.
  });
});

chrome.runtime.onInstalled.addListener(() => {
  // Trigger a connection check; no token is displayed or stored in extension storage.
  getToken().catch(() => {});
});
