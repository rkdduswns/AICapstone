"""가상 응답으로 소형 검색 창의 전환을 검증한다."""

import argparse
import sys
from pathlib import Path

from preview_phase12_client import SAMPLE_QUERY, sample_chunks
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from client.compact_search_window import CompactAnswer, CompactSearchWindow


def main() -> int:
    """실제 검색 연결 없이 답변과 오류 상태를 재현하고 PNG 저장을 지원한다."""
    parser = argparse.ArgumentParser(description="ContextTrace 소형 검색 창 가상 미리보기")
    parser.add_argument("--state", choices=("answer", "empty", "insufficient", "error"),
                        default="answer")
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--font-file", type=Path, help="오프스크린 검증에 사용할 로컬 글꼴 파일")
    parser.add_argument("--view", choices=("compact", "summary", "detail"), default="summary",
                        help="PNG 저장 시 열어 둘 화면")
    parser.add_argument("--evidence-view", choices=("collapsed", "expanded", "source"),
                        default="collapsed", help="상세 PNG의 근거·출처 정보 펼침 상태")
    args = parser.parse_args()
    app = QApplication([sys.argv[0]])
    if args.font_file is not None:
        # 화면 없는 환경에서도 지정한 실제 글꼴로만 미리보기를 검증한다. 일반 Client 설정은 바꾸지 않는다.
        font_id = QFontDatabase.addApplicationFont(str(args.font_file))
        families = QFontDatabase.applicationFontFamilies(font_id)
        if not families:
            parser.error("지정한 글꼴 파일을 읽을 수 없습니다.")
        app.setFont(QFont(families[0], 10))
    window = CompactSearchWindow()
    window.setWindowTitle("ContextTrace — 소형 검색 창 · 가상 응답")
    chunks = tuple(sample_chunks())
    response = {
        "answer": CompactAnswer(
            "answer",
            "개인정보 보호 기준과 PDF 안내에서 확인했습니다.\n"
            "• 민감한 내용과 차단한 프로그램의 기록은 수집 대상에서 제외합니다.\n"
            "• 일시정지 중에는 새 기록을 수집하지 않습니다.",
            "웹의 개인정보 보호 기준에 따르면 민감한 문자열과 차단한 프로그램에서 수집된 내용은 "
            "저장 대상에서 제외합니다. [1]\n\n"
            "PDF 안내에는 클립보드 수집을 설정에서 활성화할 수 있고 일시정지 중에는 "
            "새 기록을 수집하지 않는다고 명시돼 있습니다. [2]",
            chunks,
        ),
        "empty": CompactAnswer("empty"),
        "insufficient": CompactAnswer("insufficient", evidence=chunks[:1]),
        "error": CompactAnswer("error"),
    }[args.state]
    timer = QTimer(window)
    timer.setSingleShot(True)
    pending: int | None = None

    def request(request_id: int, _query: str) -> None:
        """같은 고정 응답을 짧게 지연해 검색 중 상태를 확인할 수 있게 한다."""
        nonlocal pending
        pending = request_id
        timer.start(400)

    def cancel(request_id: int) -> None:
        """창 종료와 입력 편집 때 미완료 가상 요청을 정리한다."""
        nonlocal pending
        if pending == request_id:
            pending = None
            timer.stop()

    def snapshot() -> None:
        """현재 화면을 PNG에 저장하고 종료한다."""
        app.exit(0 if window.grab().save(str(args.snapshot), "PNG") else 1)

    def deliver() -> None:
        """현재 요청의 응답을 전달하고 캡처 모드라면 원하는 패널을 연다."""
        nonlocal pending
        if pending is None:
            return
        request_id, pending = pending, None
        window.receive_result(request_id, response)
        if args.snapshot is not None:
            if args.view == "detail":
                if response.status == "answer":
                    window.detail_button.click()
                elif response.status == "insufficient":
                    window.evidence_button.click()
                if args.evidence_view != "collapsed" and response.evidence:
                    window.evidence_toggle.setChecked(True)
                    window.source_details_button.setChecked(args.evidence_view == "source")
            QTimer.singleShot(50, snapshot)

    window.search_requested.connect(request)
    window.search_cancelled.connect(cancel)
    timer.timeout.connect(deliver)
    window.show()
    if args.snapshot is not None:
        if args.view == "compact":
            QTimer.singleShot(50, snapshot)
        else:
            window.query.setText(SAMPLE_QUERY)
            QTimer.singleShot(50, window.submit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
