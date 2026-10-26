import test from "node:test";
import assert from "node:assert/strict";
import {capturePage} from "../../src/browser/extension/capture.mjs";

/** 개인 데이터 없이 브라우저 API와 네트워크 경계만 가상화한다. */
function fixture() {
  const calls = [];
  let tab = {id: 7, url: "https://example.test/a", title: "가상 페이지"};
  const state = {process: "chrome.exe", recordId: "12", paused: false, fail: 0, scriptReads: 0};
  const api = {
    tabs: {query: async () => [tab]},
    scripting: {executeScript: async () => {
      state.scriptReads++;
      return [{result: {url: tab.url, title: tab.title, text: "가상 본문"}}];
    }},
  };
  const fetcher = async (url, options) => {
    calls.push({url, options});
    if (state.fail) return {ok: false, status: state.fail};
    const data = url.endsWith("/activity/current") ? {
      collection_status: state.paused ? "paused" : "collecting", record_id: state.recordId,
      window: {process_name: state.process},
    } : url.endsWith("/browser/source") ? {id: 3, activity_record_id: 12} : {id: 9};
    return {ok: true, json: async () => ({ok: true, data, error: null})};
  };
  return {api, calls, state, fetcher, setTab: value => {tab = value;}};
}
const settings = {port: 8765, token: "synthetic-token"};

test("명시적 작업 ID로 출처와 본문을 고정된 loopback에 보낸다", async () => {
  const f = fixture();
  assert.deepEqual(await capturePage(f.api, settings, f.fetcher), {recordId: "12", hasText: true});
  assert.equal(f.calls.length, 3);
  assert.equal(JSON.parse(f.calls[1].options.body).record_id, "12");
  assert.ok(f.calls.every(call => call.url.startsWith("http://127.0.0.1:8765/")));
  assert.ok(f.calls.every(call => call.options.redirect === "error"));
});
test("일시정지 상태는 페이지 본문을 읽기 전에 중단한다", async () => {
  const f = fixture(); f.state.paused = true;
  await assert.rejects(capturePage(f.api, settings, f.fetcher), /일시정지/);
  assert.equal(f.state.scriptReads, 0);
});
test("현재 프로세스가 다른 앱이면 연결하지 않는다", async () => {
  const f = fixture(); f.state.process = "word.exe";
  await assert.rejects(capturePage(f.api, settings, f.fetcher), /활성 브라우저/);
  assert.equal(f.calls.length, 1);
});
test("Edge 프로세스와 브라우저 종류를 함께 전달한다", async () => {
  const f = fixture(); f.state.process = "msedge.exe";
  await capturePage(f.api, settings, f.fetcher, "edge");
  assert.equal(JSON.parse(f.calls[1].options.body).browser, "edge");
});
test("본문을 읽는 동안 탭이 바뀌면 출처를 저장하지 않는다", async () => {
  const f = fixture();
  f.api.scripting.executeScript = async () => {
    f.setTab({id: 8, url: "https://example.test/b"});
    return [{result: {url: "https://example.test/a", title: "가상 페이지", text: "본문"}}];
  };
  await assert.rejects(capturePage(f.api, settings, f.fetcher), /이동/);
  assert.equal(f.calls.length, 1);
});
test("로컬 파일과 내부 페이지는 네트워크 요청 전에 거부한다", async () => {
  const f = fixture(); f.setTab({id: 1, url: "file:///C:/private/report.pdf"});
  await assert.rejects(capturePage(f.api, settings, f.fetcher), /일반 웹페이지/);
  assert.equal(f.calls.length, 0);
});
test("잘못된 토큰과 활성 작업 변경은 오류로 안내한다", async () => {
  for (const code of [401, 409]) {
    const f = fixture(); f.state.fail = code;
    await assert.rejects(capturePage(f.api, settings, f.fetcher), /토큰|활성 작업/);
  }
});
test("잘못된 포트는 연결을 만들지 않는다", async () => {
  const f = fixture();
  await assert.rejects(capturePage(f.api, {...settings, port: "8765/other"}, f.fetcher), /포트/);
  assert.equal(f.calls.length, 0);
});
