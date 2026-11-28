import {linkActiveSource} from "./automatic.mjs";

/** 브라우저 이벤트가 겹치면 마지막 활성 탭을 한 번 더 확인한다. 실패한 전송은 쌓지 않는다. */
let running = false, changed = false;
async function update() {
  changed = true;
  if (running) return;
  running = true;
  try {
    do {
      changed = false;
      await linkActiveSource(chrome, /Edg\//.test(navigator.userAgent) ? "edge" : "chrome").catch(() => {});
    } while (changed);
  } finally { running = false; }
}
chrome.tabs.onActivated.addListener(update);
chrome.tabs.onUpdated.addListener((_id, change, tab) => {
  if (tab.active && change.status === "complete") update();
});
chrome.windows.onFocusChanged.addListener(update);
chrome.storage.onChanged.addListener(update);
