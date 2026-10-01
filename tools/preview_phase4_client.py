"""가상 저장 기록을 HTTP로 제공하는 Phase 4 Client 미리보기. 실제 DB는 사용하지 않는다."""

import sys
from dataclasses import replace
from itertools import count

from preview_phase2_client import main

from shared.records import ContextRecord, RecentRecords, RecentRecordsResponse

SAMPLES = [
    ContextRecord("sample-word", "Microsoft Word", "WINWORD.EXE", "가상 캡스톤 보고서.docx",
                  "2026-10-01T09:00:00+09:00", "2026-10-01T09:40:00+09:00", 600000, 1),
    ContextRecord("sample-chrome", "Google Chrome", "chrome.exe", "가상 자료 — 작업 맥락 조사",
                  "2026-10-01T10:00:00+09:00", "2026-10-01T10:15:00+09:00", 65000, 3),
    ContextRecord("sample-code", "Visual Studio Code", "Code.exe", "가상 작업.py — ContextTrace",
                  "2026-10-01T10:05:00+09:00", "2026-10-01T10:20:00+09:00", 120000, 2),
]
UPDATES = count()


def recent_records() -> RecentRecordsResponse:
    """새로고침마다 가상 제목을 갱신해 같은 기록 ID의 교체를 확인할 수 있게 한다."""
    update = next(UPDATES) + 1
    records = [*SAMPLES[:-1], replace(SAMPLES[-1], window_title=f"가상 작업.py — 예시 갱신 {update}")]
    return RecentRecordsResponse(RecentRecords(records))


if __name__ == "__main__":
    sys.exit(main(timing=True, records_provider=recent_records))
