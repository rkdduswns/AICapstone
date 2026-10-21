import {capturePage} from "./capture.mjs";

const port = document.getElementById("port");
const token = document.getElementById("token");
const status = document.getElementById("status");
const save = document.getElementById("save");
const capture = document.getElementById("capture");

/** 로컬 확장 저장소만 사용하며 웹사이트나 동기화 저장소에 토큰을 전달하지 않는다. */
const settings = await chrome.storage.local.get({port: 8765, token: ""});
port.value = settings.port;
token.value = settings.token;
save.addEventListener("click", async () => {
  const value = Number(port.value);
  if (!Number.isInteger(value) || value < 1 || value > 65535 || !token.value.trim()) {
    status.textContent = "올바른 포트와 토큰을 입력해 주세요.";
    return;
  }
  await chrome.storage.local.set({port: value, token: token.value.trim()});
  status.textContent = "연결 설정을 저장했습니다.";
});
capture.addEventListener("click", async () => {
  capture.disabled = save.disabled = true;
  status.textContent = "페이지를 연결하는 중입니다.";
  try {
    const saved = await chrome.storage.local.get({port: 8765, token: ""});
    const browser = /Edg\//.test(navigator.userAgent) ? "edge" : "chrome";
    const result = await capturePage(chrome, saved, fetch, browser);
    status.textContent = `작업 #${result.recordId}에 ${result.hasText ? "출처와 본문" : "출처"}을 연결했습니다. 최근 기록을 새로고침해 주세요.`;
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : "연결을 완료하지 못했습니다.";
  } finally {
    capture.disabled = save.disabled = false;
  }
});
