"""Phase 2와 같은 가상 HTTP 미리보기에 Phase 3 시간 필드를 추가한다."""

import sys

from preview_phase2_client import main

if __name__ == "__main__":
    sys.exit(main(timing=True))
