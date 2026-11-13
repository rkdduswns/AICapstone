"""창의 글꼴 최소 크기와 현재 모니터 경계를 반영한다."""

from PySide6.QtCore import QSize
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
