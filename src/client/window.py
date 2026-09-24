"""Phase 1 connection status window."""

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from client.backend_client import BackendClient
from shared.protocol import DEFAULT_PORT


class MainWindow(QWidget):
    def __init__(self, port: int = DEFAULT_PORT) -> None:
        super().__init__()
        self.setWindowTitle("ContextTrace — 연결 상태")
        self.resize(520, 180)
        self.status = QLabel("미확인")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.checked_at = QLabel("마지막 확인: 없음")
        self.button = QPushButton("연결 확인")
        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.checked_at)
        layout.addWidget(self.button)
        self.backend = BackendClient(port, self)
        self.backend.result.connect(self._show_result)
        self.button.clicked.connect(self.check)

    def check(self) -> None:
        if self.backend.reply is not None:
            return
        self.status.setText("연결 중")
        self.button.setEnabled(False)
        self.backend.check()

    def _show_result(self, message: str) -> None:
        self.status.setText(message)
        self.checked_at.setText("마지막 확인: " + QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss"))
        self.button.setEnabled(True)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.backend.close()
        super().closeEvent(event)
