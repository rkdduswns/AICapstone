"""Client 테스트 사이에 Qt 창·지연 삭제·Python 순환 참조를 명시적으로 정리한다."""

import gc
import os
import sys

import pytest

if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication


@pytest.fixture(autouse=True)
def cleanup_qt_windows():
    """이전 창의 지연 정리가 다음 테스트의 Qt 콜백 도중 실행되지 않도록 경계를 둔다.

    close만 호출한 테스트의 숨은 창도 삭제한다. 실제 창 종료/요청 취소 동작은
    테스트 본문에서 먼저 검증하고, 모든 fixture 종료 후 소유 객체를 정리한다.
    """
    yield
    app = QApplication.instance()
    if app is not None:
        for window in app.topLevelWidgets():
            window.close()
            window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    gc.collect()
