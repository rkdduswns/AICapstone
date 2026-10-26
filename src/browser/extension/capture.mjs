/** 현재 페이지를 명시적인 작업 ID에 연결한다. 토큰·본문을 로그에 남기지 않는다. */
export async function capturePage(api, settings, fetcher = fetch, browser = "chrome") {
  const port = Number(settings.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535 || !settings.token?.trim()) {
    throw new Error("Backend 포트와 연결 토큰을 먼저 저장해 주세요.");
  }
  const base = `http://127.0.0.1:${port}`;
  /** 요청 목적지는 고정 loopback 경로이며 응답의 URL을 네트워크 목적지로 쓰지 않는다. */
  async function request(path, payload) {
    const response = await fetcher(base + path, {
      method: payload ? "POST" : "GET",
      redirect: "error",
      signal: AbortSignal.timeout(10000),
      headers: {"Content-Type": "application/json", Authorization: `Bearer ${settings.token}`},
      ...(payload ? {body: JSON.stringify(payload)} : {}),
    });
    if (!response.ok) {
      throw new Error(({
        401: "연결 토큰을 확인해 주세요.",
        403: "일시정지 또는 개인정보 보호 정책으로 저장이 거부됐습니다.",
        409: "활성 작업이 바뀌었습니다. 원래 브라우저 창에서 다시 연결해 주세요.",
        503: "Backend에 브라우저 연결 토큰이 설정되지 않았습니다.",
      })[response.status] || "Backend 요청에 실패했습니다.");
    }
    const body = await response.json();
    if (body.ok !== true || body.error !== null || !body.data) {
      throw new Error("호환되지 않는 Backend 응답입니다.");
    }
    return body.data;
  }
  const [tab] = await api.tabs.query({active: true, currentWindow: true});
  if (!tab?.id || !/^https?:\/\//i.test(tab.url || "")) {
    throw new Error("일반 웹페이지에서 실행해 주세요. 내부 페이지·로컬 파일은 수집하지 않습니다.");
  }
  const activity = await request("/activity/current");
  const process = browser === "edge" ? "msedge.exe" : "chrome.exe";
  if (activity.collection_status !== "collecting" || activity.window?.process_name?.toLowerCase() !== process
      || !/^[1-9]\d*$/.test(activity.record_id || "")) {
    throw new Error("현재 활성 브라우저 작업을 확인할 수 없습니다. 일시정지·차단 상태를 확인해 주세요.");
  }
  const [{result: snapshot} = {}] = await api.scripting.executeScript({
    target: {tabId: tab.id},
    // 주입 함수는 외부 변수에 의존하지 않고 같은 DOM 순간의 제목·URL·본문을 반환한다.
    func: () => ({url: location.href, title: document.title,
      text: (document.querySelector("main, article")?.innerText || document.body?.innerText || "")
        .slice(0, 100000)}),
  });
  const [current] = await api.tabs.query({active: true, currentWindow: true});
  if (!snapshot || current?.id !== tab.id || snapshot.url !== tab.url || current.url !== tab.url) {
    throw new Error("페이지가 이동했습니다. 새 페이지에서 다시 연결해 주세요.");
  }
  const source = await request("/browser/source", {
    browser, url: snapshot.url, page_title: (snapshot.title || tab.title || "웹페이지").slice(0, 500),
    record_id: activity.record_id,
  });
  if (!Number.isSafeInteger(source.id) || source.id < 1 || !source.activity_record_id) {
    throw new Error("출처 연결 결과를 확인할 수 없습니다. 최근 기록을 새로고침해 주세요.");
  }
  if (snapshot.text?.trim()) {
    try {
      await request("/browser/content", {browser_source_id: source.id, content_text: snapshot.text});
    } catch (error) {
      throw new Error(`출처는 연결됐지만 본문은 저장하지 못했습니다. ${error.message}`);
    }
  }
  return {recordId: String(source.activity_record_id), hasText: Boolean(snapshot.text?.trim())};
}
