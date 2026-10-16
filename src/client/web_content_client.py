"""저장 웹 본문을 작업 ID로 조회한다. 외부 웹사이트에 접근하거나 페이지를 수집하지 않는다."""

import json
from urllib.parse import quote

from PySide6.QtCore import QObject, Signal

from client.json_request import JsonRequest
from client.time_values import parse_timestamp
from client.url_values import read_browser
from shared.browser import BrowserPage
from shared.protocol import API_VERSION, DEFAULT_PORT, SERVICE_NAME
from shared.web_content import (
    MAX_WEB_CONTENT_LENGTH,
    RECORD_WEB_CONTENT_PATH,
    RecordWebContent,
    WebContent,
)


class WebSourceChangedError(ValueError):
    """목록 조회 후 같은 작업의 브라우저/URL이 바뀌어 출처를 다시 확인해야 하는 경우."""


def read_record_web_content(payload: bytes, record_id: str, page: BrowserPage) -> RecordWebContent:
    """응답 형태·작업 ID·페이지 출처를 모두 검사한 뒤 표시 가능한 본문만 반환한다.

    작업 ID가 같아도 탭 이동으로 URL이 바뀔 수 있다. 목록에서 선택한 브라우저/URL과
    본문의 출처를 함께 비교해 이전 페이지의 제목 아래 다른 페이지의 내용을 보여주지 않는다.
    페이지 제목은 같은 URL에서도 바뀔 수 있으므로 수집 시점의 제목을 별도로 표시한다.
    """
    body = json.loads(payload)
    if (not isinstance(body, dict) or body.get("ok") is not True
            or "error" not in body or body["error"] is not None):
        raise ValueError("Invalid web content envelope")
    data = body.get("data")
    if (not isinstance(data, dict) or data.get("service") != SERVICE_NAME
            or type(data.get("api_version")) is not int or data["api_version"] != API_VERSION
            or data.get("record_id") != record_id or "content" not in data):
        raise ValueError("Incompatible web content response")
    content = data["content"]
    if content is None:
        return RecordWebContent(record_id, None)
    if not isinstance(content, dict):
        raise ValueError("Invalid web content")
    source = read_browser(content.get("page"))
    if source is None or source.url is None:
        raise ValueError("Missing web page source")
    if (source.browser, source.url) != (page.browser, page.url):
        raise WebSourceChangedError("Web page source changed")
    text, truncated = content.get("text"), content.get("truncated")
    if (not isinstance(text, str) or not text.strip() or len(text) > MAX_WEB_CONTENT_LENGTH
            or type(truncated) is not bool):
        raise ValueError("Invalid web content text")
    parse_timestamp(content.get("captured_at"))
    return RecordWebContent(record_id, WebContent(source, content["captured_at"], text, truncated))


class WebContentClient(JsonRequest):
    """단일 상세 요청을 유지하고 선택 전환 시 이전 요청과 비교 기준을 함께 제거한다."""

    content_received = Signal(object)
    content_failed = Signal(str)

    def __init__(self, port: int = DEFAULT_PORT, parent: QObject | None = None) -> None:
        """공통 HTTP 계층의 timeout/취소를 재사용하고 웹 본문 검증만 추가한다."""
        super().__init__(port, parent)
        self.record_id: str | None = None
        self.page: BrowserPage | None = None
        self.received.connect(self._received)
        self.failed.connect(self._failed)

    def fetch(self, record_id: str, page: BrowserPage) -> None:
        """출처 URL을 네트워크 목적지로 쓰지 않고 loopback에 인코딩한 작업 ID만 보낸다."""
        self.close()
        self.record_id, self.page = record_id, page
        self.get(f"{RECORD_WEB_CONTENT_PATH}?record_id={quote(record_id, safe='')}")

    def _received(self, payload: bytes) -> None:
        """취소된 요청은 무시하고 출처 변경과 일반 계약 오류를 구분해 안내한다."""
        if self.record_id is None or self.page is None:
            return
        try:
            result = read_record_web_content(payload, self.record_id, self.page)
        except WebSourceChangedError:
            self.content_failed.emit("페이지 출처가 변경되었습니다. 최근 기록을 새로고침해 주세요.")
            return
        except (ValueError, UnicodeDecodeError):
            self._failed("content_type", 0)
            return
        self.content_received.emit(result)

    def _failed(self, reason: str, status: int) -> None:
        """서버 오류 본문을 노출하지 않고 조회 불가·거부·시간 초과를 구분한다."""
        if reason == "http" and status == 404:
            message = "조회 불가 — 기능 미지원 또는 삭제된 기록입니다. 최근 기록을 새로고침해 주세요."
        elif reason == "http" and status == 403:
            message = "웹 본문 조회가 허용되지 않았습니다. 개인정보 설정을 확인해 주세요."
        else:
            message = {
                "timeout": "웹 본문 조회 시간 초과 — 다시 확인해 주세요.",
                "http": "웹 본문 조회 실패 — 서버 오류입니다.",
                "network": "연결 안 됨 — Backend 실행 후 다시 확인해 주세요.",
                "content_type": "호환되지 않는 웹 본문 응답 — 다시 확인해 주세요.",
            }[reason]
        self.content_failed.emit(message)

    def close(self) -> None:
        """선택 해제/재연결/종료 시 늦은 응답이 이전 출처와 본문을 복원하지 못하게 한다."""
        super().close()
        self.record_id, self.page = None, None
