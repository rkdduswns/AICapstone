"""글자 대신 쓰는 메뉴 아이콘을 현재 팔레트와 표시 크기에 맞춰 그린다."""

from typing import Literal

from PySide6.QtCore import QLineF, QPointF, QRect, QSize, Qt
from PySide6.QtGui import QIcon, QIconEngine, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QPushButton

MenuIconKind = Literal["menu", "more"]


class _MenuIconEngine(QIconEngine):
    """고정 이미지 파일 없이 메뉴와 추가 동작의 단순한 모양을 그린다."""

    def __init__(self, kind: MenuIconKind) -> None:
        """아이콘 종류만 보관하고 색상은 그리는 시점의 운영체제 팔레트를 사용한다."""
        super().__init__()
        self.kind = kind

    def clone(self) -> QIconEngine:
        """Qt가 아이콘을 복사할 때도 같은 벡터 그리기 규칙을 유지한다."""
        return _MenuIconEngine(self.kind)

    def paint(self, painter: QPainter, rect: QRect, mode: QIcon.Mode, state: QIcon.State) -> None:
        """실제 아이콘 영역에 비례해 그려 배율을 바꿔도 가장자리가 뭉개지지 않게 한다."""
        palette = QApplication.palette()
        group = QPalette.ColorGroup.Disabled if mode == QIcon.Mode.Disabled else QPalette.ColorGroup.Active
        role = (QPalette.ColorRole.HighlightedText if mode == QIcon.Mode.Selected
                else QPalette.ColorRole.ButtonText)
        color = palette.color(group, role)
        side = min(rect.width(), rect.height())
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(rect.x() + (rect.width() - side) / 2,
                          rect.y() + (rect.height() - side) / 2)
        painter.scale(side / 18, side / 18)
        if self.kind == "menu":
            painter.setPen(QPen(color, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for y in (5, 9, 13):
                painter.drawLine(QLineF(4, y, 14, y))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            for y in (4.5, 9, 13.5):
                painter.drawEllipse(QPointF(9, y), 1.4, 1.4)
        painter.restore()

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        """Qt가 요청한 해상도로 직접 그려 고해상도 화면에서도 작은 원본을 확대하지 않는다."""
        if size.isEmpty():
            return QPixmap()
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        try:
            self.paint(painter, QRect(0, 0, size.width(), size.height()), mode, state)
        finally:
            painter.end()
        return pixmap


def apply_menu_icon(button: QPushButton, kind: MenuIconKind, label: str) -> None:
    """메뉴 연결은 유지하며 아이콘·툴팁·보조기술 이름을 가진 작은 버튼으로 바꾼다."""
    if kind not in ("menu", "more"):
        raise ValueError("Unsupported menu icon")
    button.setText("")
    button.setIcon(QIcon(_MenuIconEngine(kind)))
    button.setIconSize(QSize(18, 18))
    button.setFixedSize(32, 30)
    button.setToolTip(label)
    button.setAccessibleName(label)
    button.setProperty("iconOnly", True)
    style = button.style()
    style.unpolish(button)
    style.polish(button)
    button.updateGeometry()
    button.update()
