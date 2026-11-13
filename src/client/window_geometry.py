"""창의 글꼴 최소 크기와 현재 모니터 경계를 반영한다."""

from PySide6.QtCore import QPoint, QSize
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget


def fit_window(window: QWidget, target: QSize) -> None:
    """화면 모드 전환 시 좌상단을 유지하고 창 테두리까지 화면 안에 맞춘다."""
    if window.isMaximized() or window.isMinimized():
        return
    window.layout().activate()
    size = target.expandedTo(window.minimumSizeHint())
    screen = window.screen()
    if screen is None:
        window.resize(size)
        return
    bounds = screen.availableGeometry()
    previous_frame = window.frameGeometry()
    frame_margin = previous_frame.size() - window.size()
    window.resize(size.boundedTo((bounds.size() - frame_margin).expandedTo(QSize(1, 1))))
    frame = window.frameGeometry()
    x = max(bounds.left(), min(previous_frame.left(), bounds.right() - frame.width() + 1))
    y = max(bounds.top(), min(previous_frame.top(), bounds.bottom() - frame.height() + 1))
    if (frame.left(), frame.top()) != (x, y):
        window.move(x, y)


def restore_position(window: QWidget, position: QPoint) -> None:
    """저장 위치의 모니터를 찾고 사라진 모니터의 좌표는 현재 화면 안으로 옮긴다."""
    screen = QGuiApplication.screenAt(position) or window.screen()
    if screen is None:
        return
    bounds = screen.availableGeometry()
    # 복원 대상 모니터가 더 작거나 배율이 다르면 위치뿐 아니라 창 크기도 맞춘다.
    margin = window.frameGeometry().size() - window.size()
    window.resize(window.size().boundedTo((bounds.size() - margin).expandedTo(QSize(1, 1))))
    frame = window.frameGeometry()
    x = max(bounds.left(), min(position.x(), bounds.right() - frame.width() + 1))
    y = max(bounds.top(), min(position.y(), bounds.bottom() - frame.height() + 1))
    window.move(x, y)
