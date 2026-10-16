"""파일 출처와 저장 문서 본문의 가상 미리보기. 실제 로컬 파일을 열거나 추출하지 않는다."""

import sys

from preview_phase5_client import main

if __name__ == "__main__":
    sys.exit(main(clipboard=True, browser=True, web_content=True, document_content=True))
