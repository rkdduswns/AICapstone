"""Backend 없이 고정 응답으로 의미 검색 Client 화면을 확인한다."""

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel

from client.search_data_values import read_document_chunk
from client.semantic_search_widget import SemanticSearchInput, SemanticSearchWidget
from client.time_values import parse_timestamp
from shared.search_data import DocumentChunk

SAMPLE_QUERY = "작업 기록을 저장할 때 어떤 개인정보를 제외했지?"


def sample_chunks() -> list[DocumentChunk]:
    """고정 웹·PDF 응답을 실제 조각 및 출처 수신 검증에 통과시킨다."""
    times = {
        "started_at": "2026-11-06T09:00:00+09:00",
        "last_active_at": "2026-11-06T09:06:00+09:00",
        "captured_at": "2026-11-06T09:03:00+09:00",
        "content_truncated": False,
    }
    examples = [
        (
            "demo-web",
            "민감한 문자열과 차단한 프로그램에서 수집된 내용은 저장 대상에서 제외한다.",
            {
                "kind": "web", "application": "Google Chrome", "process_name": "chrome.exe",
                "window_title": "가상 웹 기록",
                "browser": {
                    "browser": "chrome", "page_title": "개인정보 보호 기준",
                    "url": "https://example.test/privacy/가상-자료",
                },
            },
        ),
        (
            "demo-pdf",
            "클립보드 기록은 설정에서 활성화할 수 있다.\n일시정지 중에는 새로 수집하지 않는다.",
            {
                "kind": "document", "application": "PDF 뷰어", "process_name": "pdfviewer.exe",
                "window_title": "개인정보 처리 안내.pdf",
                "started_at": "2026-11-06T10:04:00+09:00",
                "last_active_at": "2026-11-06T10:12:00+09:00",
                "captured_at": "2026-11-06T10:09:00+09:00",
                "document": {"file_path": r"C:\가상 자료\개인정보 처리 안내.pdf", "file_type": "pdf"},
            },
        ),
    ]
    return [
        read_document_chunk({
            "id": f"{context_id}-0", "context_id": context_id, "chunk_index": 0,
            "text": text, "source": {**times, **source},
        }, context_id)
        for context_id, text, source in examples
    ]


def _matches(request: SemanticSearchInput, chunk: DocumentChunk) -> bool:
    """고정 응답의 순서를 유지하며 미리보기의 선택 조건만 적용한다."""
    source = chunk.source
    source_types = {"all", source.kind}
    if source.document is not None:
        source_types.add(source.document.file_type)
    if request.source_type not in source_types:
        return False
    if request.process_name and request.process_name != source.process_name.casefold():
        return False
    active = parse_timestamp(source.last_active_at)
    return (
        (request.active_from is None or active >= parse_timestamp(request.active_from))
        and (request.active_before is None or active < parse_timestamp(request.active_before))
    )


def main() -> int:
    """선택한 가상 상태를 실행하고 요청 시 첫 결과 화면을 PNG로 남긴다."""
    parser = argparse.ArgumentParser(description="Phase 12 의미 검색 가상 미리보기")
    parser.add_argument("--state", choices=("ready", "empty", "error"), default="ready")
    parser.add_argument("--snapshot", type=Path)
    args = parser.parse_args()
    chunks = sample_chunks()

    def provider(request: SemanticSearchInput) -> list[DocumentChunk]:
        """질의와 무관한 고정 가상 조각으로 결과 표시와 선택 조건을 검증한다."""
        if args.state == "error":
            raise ValueError("가상 응답 오류")
        if args.state == "empty":
            return []
        return [chunk for chunk in chunks if _matches(request, chunk)]

    app = QApplication([sys.argv[0]])
    window = SemanticSearchWidget(provider)
    window.setWindowTitle("강써치 — Phase 12 의미 검색 미리보기")
    window.resize(820, 640)
    banner = QLabel("가상 미리보기 · 고정 예시에 선택 조건만 적용합니다.")
    window.layout().insertWidget(0, banner)
    window.query.setText(SAMPLE_QUERY)

    def snapshot() -> None:
        """선택한 가상 결과 상태를 화면에 표시해 캡처하고 종료한다."""
        window.search()
        saved = window.grab().save(str(args.snapshot), "PNG")
        app.exit(0 if saved else 1)

    window.show()
    if args.snapshot is not None:
        QTimer.singleShot(100, snapshot)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
