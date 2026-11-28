"""문서 본문은 검색창의 크기에 영향을 주지 않는 독립된 읽기 창에 표시한다."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QPlainTextEdit, QPushButton, QVBoxLayout


def add_document_reader(owner, layout):
    """문서 선택은 창을 열지 않으며 사용자가 원할 때만 저장한 텍스트를 보여준다."""
    dialog = QDialog(owner)
    dialog.setWindowTitle("강써치 — 문서 본문")
    dialog.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
    dialog.resize(720, 560)
    text = QPlainTextEdit(dialog)
    text.setReadOnly(True)
    QVBoxLayout(dialog).addWidget(text)
    button = QPushButton("문서 본문을 별도 창에서 보기")
    button.setEnabled(False)
    def update_button():
        """선택 해제나 삭제 뒤 기존 본문이 빈 창으로 남지 않게 한다."""
        available = not text.document().isEmpty()
        button.setEnabled(available)
        if not available:
            dialog.hide()
    text.textChanged.connect(update_button)
    button.clicked.connect(dialog.show)
    layout.addWidget(button)
    return text
