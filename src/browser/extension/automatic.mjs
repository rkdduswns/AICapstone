/** 허용한 사이트의 활성 페이지에서 URL·제목만 연결한다. 페이지 본문에는 접근하지 않는다. */
export async function linkActiveSource(api, browser, fetcher = fetch) {
  async function active() {
    const win = await api.windows.getLastFocused();
    if (!win.focused || win.incognito) return;
    const [tab] = await api.tabs.query({windowId: win.id, active: true});
    if (!tab?.url || tab.incognito || tab.status !== "complete") return;
    const url = new URL(tab.url);
    if (!["https:", "http:"].includes(url.protocol)) return;
    const {autoSites = []} = await api.storage.local.get("autoSites");
    if (!autoSites.includes(url.origin) || !await api.permissions.contains({origins: [url.protocol + "//" + url.hostname + "/*"]})) return;
    return tab;
  }
  const tab = await active();
  if (!tab) return;
  const {port, token} = await api.storage.local.get({port: 8765, token: ""});
  if (!Number.isInteger(port) || port < 1 || port > 65535 || !token) return;
  const base = "http://127.0.0.1:" + port;
  const options = {redirect: "error", signal: AbortSignal.timeout(8000), cache: "no-store",
    headers: {Authorization: "Bearer " + token, "Content-Type": "application/json"}};
  const reply = await fetcher(base + "/activity/current", options);
  if (!reply.ok) return;
  const {data, ok} = await reply.json();
  if (!ok || data?.collection_status !== "collecting" || !/^[1-9]\d*$/.test(data.record_id)
      || data.window?.process_name?.toLowerCase() !== (browser === "edge" ? "msedge.exe" : "chrome.exe")) return;
  const current = await active();
  if (current?.id !== tab.id || current?.url !== tab.url) return;
  await fetcher(base + "/browser/source", {...options, method: "POST", body: JSON.stringify({
    browser, record_id: data.record_id, url: tab.url, page_title: (current.title || "웹페이지").slice(0, 500)})});
}
