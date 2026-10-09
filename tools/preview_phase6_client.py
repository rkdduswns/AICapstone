"""가상 복사 항목과 클립보드 기록 설정 화면을 확인한다. OS 클립보드를 읽지 않는다."""

import sys

from preview_phase5_client import main

if __name__ == "__main__":
    sys.exit(main(clipboard=True))
