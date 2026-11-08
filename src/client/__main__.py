"""검색 중심 창에서 데스크톱 Client를 실행한다."""

import argparse
import sys

from PySide6.QtWidgets import QApplication

from client.application_window import ApplicationWindow
from shared.protocol import DEFAULT_PORT


def main() -> int:
    parser = argparse.ArgumentParser(description="ContextTrace desktop client")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be an integer from 1 to 65535")
    app = QApplication([sys.argv[0]])
    window = ApplicationWindow(args.port)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
