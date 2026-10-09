"""가상 브라우저 출처와 URL 설정을 표시한다. 확장 프로그램/실제 URL 차단을 실행하지 않는다."""

import sys

from preview_phase5_client import main

if __name__ == "__main__":
    sys.exit(main(clipboard=True, browser=True))
