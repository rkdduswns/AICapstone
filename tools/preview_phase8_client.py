"""저장 웹 본문 확인 화면의 가상 미리보기. 브라우저 수집이나 실제 저장은 수행하지 않는다."""

import sys

from preview_phase5_client import main

if __name__ == "__main__":
    sys.exit(main(clipboard=True, browser=True, web_content=True))
