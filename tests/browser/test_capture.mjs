import test from "node:test";
import assert from "node:assert/strict";
import {runInNewContext} from "node:vm";
import {capturePage} from "../../src/browser/extension/capture.mjs";

/** 개인 데이터 없이 브라우저 API와 네트워크 경계만 가상화한다. */
function fixture() {
  const calls = [];
  let tab = {id: 7, url: "https://example.test/a", title: "가상 페이지"};
  const state = {process: "chrome.exe", recordId: "12", paused: false, fail: 0, scriptReads: 0,
    pageText: "가상 본문", denyContent: false, deniedBodyReads: 0, failPath: "",
    source: {id: 3, activity_record_id: 12}, content: {id: 9, browser_source_id: 3}};
  const api = {
    tabs: {query: async () => [tab]},
    scripting: {executeScript: async ({func}) => {
      state.scriptReads++;
      // Chrome처럼 별도 실행 문맥에서 주입 함수를 실행한다.
      const result = runInNewContext(`(${func})()`, {
        location: {href: tab.url},
        document: {title: tab.title, querySelector: () => ({innerText: state.pageText})},
      });
      return [{result}];
    }},
  };
  const fetcher = async (url, options) => {
    calls.push({url, options});
    if (state.fail && (!state.failPath || url.endsWith(state.failPath))) {
      return {ok: false, status: state.fail, json: async () => {
        state.deniedBodyReads++;
        return {ok: true, data: state.content, error: null};
      }};
    }
    if (state.denyContent && url.endsWith("/browser/content")) {
      return {ok: false, status: 403, json: async () => {
        state.deniedBodyReads++;
        return {ok: true, data: {id: 9}, error: null};
      }};
    }
    const data = url.endsWith("/activity/current") ? {
      collection_status: state.paused ? "paused" : "collecting", record_id: state.recordId,
      window: {process_name: state.process},
    } : url.endsWith("/browser/source") ? state.source : state.content;
    return {ok: true, json: async () => ({ok: true, data, error: null})};
  };
  return {api, calls, state, fetcher, setTab: value => {tab = value;}};
}
const settings = {port: 8765, token: "synthetic-token"};

test("명시적 작업 ID로 출처와 본문을 고정된 loopback에 보낸다", async () => {
  const f = fixture();
  assert.deepEqual(await capturePage(f.api, settings, f.fetcher),
    {recordId: "12", hasText: true, truncated: false});
  assert.equal(f.calls.length, 3);
  assert.equal(JSON.parse(f.calls[1].options.body).record_id, "12");
  assert.deepEqual(JSON.parse(f.calls[2].options.body),
    {browser_source_id: 3, content_text: "가상 본문", truncated: false});
  assert.ok(f.calls.every(call => call.url.startsWith("http://127.0.0.1:8765/")));
  assert.ok(f.calls.every(call => call.options.redirect === "error"));
});
test("본문이 한도에 맞으면 전체로 전송한다", async () => {
  const f = fixture(); f.state.pageText = "가".repeat(100000);
  assert.equal((await capturePage(f.api, settings, f.fetcher)).truncated, false);
  assert.equal(JSON.parse(f.calls[2].options.body).truncated, false);
});
test("한도보다 긴 본문을 표시하고 경계의 문자는 쪼개지 않는다", async () => {
  for (const tail of ["나다", "🙂"]) {
    const f = fixture();
    const prefix = "가".repeat(99999);
    f.state.pageText = prefix + tail;
    const result = await capturePage(f.api, settings, f.fetcher);
    const payload = JSON.parse(f.calls[2].options.body);
    assert.equal(result.truncated, true);
    assert.equal(payload.truncated, true);
    assert.equal(payload.content_text, tail === "🙂" ? prefix : prefix + "나");
  }
});
test("출처 연결 이후 본문 403은 응답 본문을 읽지 않고 저장 거부로 알린다", async () => {
  const f = fixture();
  f.state.pageText = "가".repeat(100001);
  f.state.denyContent = true;
  await assert.rejects(capturePage(f.api, settings, f.fetcher),
    /출처는 연결됐지만 본문은 저장하지 못했습니다.*개인정보 보호 정책/);
  assert.equal(f.calls.length, 3);
  assert.equal(f.state.deniedBodyReads, 0);
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

test("출처 응답의 실제 작업 ID는 정규형 문자열 또는 안전한 양수만 허용한다", async () => {
  // SQLite 상한은 문자열로 받아 정밀도를 잃지 않고 그대로 표시한다.
  for (const id of [1, Number.MAX_SAFE_INTEGER, "1", "9007199254740992", "9223372036854775807"]) {
    const f = fixture(); f.state.source.activity_record_id = id;
    const result = await capturePage(f.api, settings, f.fetcher);
    assert.equal(result.recordId, String(id));
    assert.equal(f.calls.length, 3);
  }
});

test("URL 이동으로 서버가 새 작업을 만들면 최종 연결 ID를 받아들인다", async () => {
  const f = fixture(); f.state.source.activity_record_id = "13";
  const result = await capturePage(f.api, settings, f.fetcher);
  assert.equal(JSON.parse(f.calls[1].options.body).record_id, "12");
  assert.equal(result.recordId, "13");
  assert.equal(JSON.parse(f.calls[2].options.body).browser_source_id, 3);
});

test("잘못되거나 빠진 연결 작업 ID는 본문 전송 전에 거부한다", async () => {
  for (const id of [undefined, null, false, true, 0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1,
    "", "0", "-1", "01", " 12", "12 ", "1e2", "not-a-record", "１２", "9223372036854775808",
    "100000000000000000000", {}, []]) {
    const f = fixture(); f.state.source.activity_record_id = id;
    await assert.rejects(capturePage(f.api, settings, f.fetcher), /출처 연결 결과를 확인할 수 없습니다/);
    assert.equal(f.calls.length, 2, `잘못된 작업 ID: ${String(id)}`);
    assert.ok(f.calls.every(call => !call.url.endsWith("/browser/content")));
  }
});

test("활성 작업 ID가 손상됐으면 페이지 본문을 읽기 전에 중단한다", async () => {
  for (const id of [undefined, null, true, 0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1,
    "01", "1e2", "9223372036854775808", {}, []]) {
    const f = fixture(); f.state.recordId = id;
    await assert.rejects(capturePage(f.api, settings, f.fetcher), /활성 브라우저 작업/);
    assert.equal(f.state.scriptReads, 0);
    assert.equal(f.calls.length, 1);
  }
});

test("잘못되거나 빠진 출처 ID는 본문 전송 전에 거부한다", async () => {
  for (const id of [undefined, null, false, true, 0, -1, 1.5, "3", Number.MAX_SAFE_INTEGER + 1]) {
    const f = fixture(); f.state.source.id = id;
    await assert.rejects(capturePage(f.api, settings, f.fetcher), /출처 연결 결과를 확인할 수 없습니다/);
    assert.equal(f.calls.length, 2);
  }
});

test("본문 저장 응답의 ID가 잘못되면 저장 여부 확인을 안내하고 다시 전송하지 않는다", async () => {
  for (const id of [undefined, null, false, true, 0, -1, 1.5, "9", Number.MAX_SAFE_INTEGER + 1]) {
    const f = fixture(); f.state.content.id = id;
    await assert.rejects(capturePage(f.api, settings, f.fetcher), /출처는 연결됐지만 본문 저장 결과를 확인할 수 없습니다/);
    assert.equal(f.calls.length, 3);
  }
});

test("본문 응답은 요청한 출처 ID에 연결된 경우에만 저장 성공으로 처리한다", async () => {
  for (const id of [undefined, null, false, true, 0, -1, "3", 4]) {
    const f = fixture(); f.state.content.browser_source_id = id;
    await assert.rejects(capturePage(f.api, settings, f.fetcher), /본문 저장 결과를 확인할 수 없습니다/);
    assert.equal(f.calls.length, 3);
  }
});

test("손상되거나 유실된 본문 응답은 미저장으로 단정하지 않고 확인을 안내한다", async () => {
  // POST 이후 연결 단절이나 JSON 손상은 서버가 이미 저장했을 가능성이 있다.
  for (const failure of ["network", "json", null, {}, {ok: true, error: null, data: null}]) {
    const f = fixture();
    const fetcher = async (url, options) => {
      if (!url.endsWith("/browser/content")) return f.fetcher(url, options);
      f.calls.push({url, options});
      if (failure === "network") throw new TypeError("synthetic disconnect");
      return {ok: true, json: async () => {
        if (failure === "json") throw new SyntaxError("synthetic invalid JSON");
        return failure;
      }};
    };
    await assert.rejects(capturePage(f.api, settings, fetcher), error => {
      assert.match(error.message, /출처는 연결됐지만 본문 저장 결과를 확인할 수 없습니다/);
      assert.doesNotMatch(error.message, /저장하지 못했습니다|synthetic/);
      return true;
    });
    assert.equal(f.calls.length, 3);
  }
});

test("출처와 본문 API의 실패 상태는 성공 모양 JSON을 읽지 않고 중단한다", async () => {
  for (const path of ["/browser/source", "/browser/content"]) {
    for (const [code, message] of [[401, /연결 토큰/], [403, /개인정보 보호 정책/],
      [409, /활성 작업/], [503, /토큰이 설정되지 않았습니다/]]) {
      const f = fixture(); f.state.fail = code; f.state.failPath = path;
      await assert.rejects(capturePage(f.api, settings, f.fetcher), message);
      assert.equal(f.state.deniedBodyReads, 0);
      assert.equal(f.calls.length, path === "/browser/source" ? 2 : 3);
      assert.ok(f.calls.every(call => call.options.headers.Authorization === "Bearer synthetic-token"));
    }
  }
});
