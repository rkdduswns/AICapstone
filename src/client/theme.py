"""OS 글꼴과 색상 팔레트를 유지하며 Client의 정보·동작 우선순위를 통일한다."""

from PySide6.QtGui import QFont, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QWidget

_STYLE = """
QPushButton {
    padding: 4px 10px;
    min-height: 20px;
    border: 1px solid palette(mid);
    border-radius: 6px;
    background: palette(button);
    color: palette(button-text);
}
QPushButton:hover { background: palette(alternate-base); }
QPushButton:focus { border-color: palette(highlight); }
QPushButton:disabled { color: palette(mid); }
QPushButton[uiRole="primary"] {
    background: palette(highlight);
    border-color: palette(highlight);
    color: palette(highlighted-text);
    font-weight: 600;
}
QPushButton[uiRole="primary"]:focus { border-color: palette(window-text); }
QPushButton[uiRole="primary"]:disabled {
    background: palette(button);
    border-color: palette(mid);
    color: palette(mid);
}
QPushButton[uiRole="quiet"] {
    padding: 2px 6px;
    min-height: 18px;
    background: transparent;
    border-color: transparent;
}
QPushButton[uiRole="quiet"]:hover {
    background: palette(alternate-base);
    border-color: palette(mid);
}
QPushButton[uiRole="quiet"]:focus { border-color: palette(highlight); }
QPushButton[uiRole="quiet"]:checked {
    background: palette(alternate-base);
    border-color: palette(highlight);
}
QPushButton[menuControl="true"] { padding-right: 18px; }
QPushButton[iconOnly="true"] { padding: 4px; }
QPushButton[iconOnly="true"]::menu-indicator { image: none; width: 0px; height: 0px; }
QMenu {
    background: palette(base);
    color: palette(text);
    border: 1px solid palette(mid);
    padding: 4px;
}
QMenu::item { padding: 6px 24px 6px 28px; }
QMenu::item:selected { background: palette(highlight); color: palette(highlighted-text); }
QMenu::separator { height: 1px; background: palette(mid); margin: 4px 8px; }
QLineEdit, QComboBox {
    padding: 4px 6px;
    border: 1px solid palette(mid);
    border-radius: 5px;
    background: palette(base);
    color: palette(text);
}
QLineEdit:focus, QComboBox:focus { border-color: palette(highlight); }
QPlainTextEdit, QListWidget, QTableWidget, QTreeWidget {
    border: 1px solid palette(mid);
    border-radius: 6px;
    background: palette(base);
    color: palette(text);
}
QPlainTextEdit[uiRole="reading"] {
    border: 0px;
    padding: 2px;
}
QWidget[uiRole="card"] {
    background: palette(base);
    border: 1px solid palette(mid);
    border-radius: 8px;
}
QLabel[uiRole="heading"] { font-weight: 600; }
QLabel[uiRole="muted"] { color: palette(window-text); }
QGroupBox {
    margin-top: 9px;
    padding-top: 8px;
    border: 1px solid palette(mid);
    border-radius: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0px 5px;
    left: 8px;
}
"""


def apply_client_style(widget: QWidget) -> None:
    """해당 창에만 공통 규칙을 적용하고 다른 Qt 앱·미리보기의 전역 설정은 바꾸지 않는다."""
    font = QFont(widget.font())
    # 시스템 글꼴과 화면 배율을 따르되 작은 기본 글자만 최소 읽기 크기로 보완한다.
    if 0 < font.pointSizeF() < 9.5:
        font.setPointSizeF(9.5)
    widget.setFont(font)
    widget.setStyleSheet(_STYLE)


def set_role(widget: QWidget, role: str) -> None:
    """버튼·제목의 역할을 표시하고 이미 보이는 위젯에서도 스타일을 즉시 갱신한다."""
    widget.setProperty("uiRole", role)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.updateGeometry()
    widget.update()


def set_reading_text(widget: QPlainTextEdit, text: str) -> None:
    """원문·인용 위치를 유지하고 읽기 영역의 여백과 문단 간격만 조절한다."""
    widget.setPlainText(text)
    widget.document().setDocumentMargin(8)
    cursor = QTextCursor(widget.document())
    cursor.select(QTextCursor.SelectionType.Document)
    block = QTextBlockFormat()
    block.setLineHeight(125, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
    block.setBottomMargin(4)
    cursor.mergeBlockFormat(block)
    set_role(widget, "reading")
