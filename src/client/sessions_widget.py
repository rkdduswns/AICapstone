"""실제 세션·타임라인 조회와 사용자 확인을 거친 기록 삭제 화면."""

import json

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from client.json_request import JsonRequest
from client.time_values import format_timestamp, parse_timestamp


def data_object(payload):
    """Phase 14의 실제 응답 형식을 검사한다. 없는 service 필드를 임시로 만들지 않는다."""
    body = json.loads(payload)
    if (not isinstance(body, dict) or body.get("ok") is not True or "error" not in body
            or body["error"] is not None or not isinstance(body.get("data"), dict)):
        raise ValueError("Invalid session response")
    return body["data"]


class SessionsWidget(QWidget):
    """세션 ID로 조회하며 Client에서 시간 간격을 추정해 그룹을 생성하지 않는다."""

    records_changed = Signal()

    def __init__(self, port, parent=None):
        """목록·상세·삭제 요청을 분리해 선택 전환 시 늦은 응답을 취소한다."""
        super().__init__(parent)
        self.connected = self.loaded = False
        self.session_id = None
        self.offset = 0
        self.has_more = False
        self.rows = []
        self.list_client, self.detail_client, self.delete_client = [JsonRequest(port, self) for _ in range(3)]
        self.list_client.received.connect(self._sessions)
        self.detail_client.received.connect(self._detail)
        self.delete_client.received.connect(self._deleted)
        for client in (self.list_client, self.detail_client, self.delete_client):
            client.failed.connect(lambda reason, status: self._error("세션 요청에 실패했습니다."))
        layout = QVBoxLayout(self)
        self.status = QLabel("연결 확인 후 세션을 조회할 수 있습니다.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.refresh_button = QPushButton("세션 새로고침")
        self.next_button = QPushButton("다음 작업 200건")
        self.delete_button = QPushButton("선택 작업 삭제")
        self.delete_all_button = QPushButton("전체 기록 삭제")
        for button in (self.refresh_button, self.next_button, self.delete_button, self.delete_all_button):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.sessions = QListWidget()
        self.activities = QListWidget()
        self.activities.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.materials = QPlainTextEdit()
        self.materials.setReadOnly(True)
        layout.addWidget(self.sessions, 1)
        layout.addWidget(self.activities, 2)
        layout.addWidget(self.materials, 1)
        self.refresh_button.clicked.connect(self.refresh)
        self.next_button.clicked.connect(self._next_page)
        self.delete_button.clicked.connect(self.delete_selected)
        self.delete_all_button.clicked.connect(self.delete_all)
        self.sessions.currentRowChanged.connect(self._select_session)
        self.set_connected(False)

    def set_connected(self, connected):
        """재연결 시 이전 서버의 선택·요청·표시를 비운다."""
        for client in (self.list_client, self.detail_client, self.delete_client):
            client.close()
        self.connected, self.loaded, self.session_id = connected, False, None
        self.sessions.clear()
        self.activities.clear()
        self.materials.clear()
        self.rows = []
        self.refresh_button.setEnabled(connected)
        self.delete_all_button.setEnabled(connected)
        self.delete_button.setEnabled(False)
        self.next_button.setEnabled(False)

    def load_if_needed(self):
        """탭 최초 진입에만 조회하고 이후 갱신은 명시적으로 실행한다."""
        if not self.loaded:
            self.refresh()

    def refresh(self):
        """현재 세션 목록을 실제 API에서 다시 받는다."""
        if self.connected and self.list_client.reply is None:
            self.detail_client.close()
            self.status.setText("세션 조회 중")
            self.list_client.get("/sessions?limit=50")

    def _sessions(self, payload):
        """실제 ID·시각·건수가 검증된 세션 목록만 표시한다."""
        try:
            rows = data_object(payload)["sessions"]
            if not isinstance(rows, list) or len(rows) > 50:
                raise ValueError("Invalid sessions")
            for row in rows:
                if type(row["id"]) is not int or row["id"] < 1 or type(row["activity_count"]) is not int:
                    raise ValueError("Invalid session ID")
                if parse_timestamp(row["ended_at"]) < parse_timestamp(row["started_at"]):
                    raise ValueError("Invalid session range")
        except (ValueError, KeyError, TypeError):
            self._error("세션 응답을 확인할 수 없습니다.")
            return
        self.rows, self.loaded = rows, True
        self.sessions.clear()
        self.activities.clear()
        self.materials.clear()
        for row in rows:
            self.sessions.addItem(f"#{row['id']} · {format_timestamp(row['started_at'])} · 작업 {row['activity_count']}건")
        self.status.setText(f"세션 {len(rows)}개")
        if rows:
            self.sessions.setCurrentRow(0)

    def _select_session(self, index):
        """선택된 실제 세션의 첫 페이지와 자료만 요청한다."""
        self.detail_client.close()
        self.activities.clear()
        self.materials.clear()
        self.delete_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.session_id = self.rows[index]["id"] if 0 <= index < len(self.rows) else None
        self.offset = 0
        if self.session_id is not None:
            self.detail_client.get(f"/sessions/{self.session_id}?limit=200&offset=0")

    def _detail(self, payload):
        """서버가 확인한 세션·페이지·타임라인과 실제 연결 자료를 표시한다."""
        try:
            data = data_object(payload)
            page = data["activities_pagination"]
            rows = data["activities"]
            if (type(data["session"]["id"]) is not int or data["session"]["id"] != self.session_id
                    or type(page["offset"]) is not int or page["offset"] != self.offset
                    or type(page["limit"]) is not int or page["limit"] != 200
                    or type(page["total"]) is not int or page["total"] < 0 or type(page["has_more"]) is not bool
                    or not isinstance(rows, list) or len(rows) > 200):
                raise ValueError("Unexpected session page")
            for row in rows:
                if type(row["id"]) is not int or row["id"] < 1 or not isinstance(row["window_title"], str):
                    raise ValueError("Invalid activity")
                parse_timestamp(row["started_at"])
                parse_timestamp(row["ended_at"])
            materials = data["materials"]
            lines = []
            for row in materials["documents"]:
                original = row.get("original_file_path")
                location = f"원본 · {original}" if original else f"Backend 파일 · {row['file_path']} (원본 경로 미확인)"
                lines.append(f"문서 · {row['file_name']}\n{location}")
            for row in materials["web_pages"]:
                lines.append(f"웹 · {row['page_title']}\n{row['url']}")
        except (ValueError, KeyError, TypeError):
            self._error("세션 상세를 확인할 수 없습니다.")
            return
        if self.offset == 0:
            self.activities.clear()
        for row in rows:
            self.activities.addItem(f"{format_timestamp(row['started_at'])} · {row['application']} · {row['window_title']}")
            self.activities.item(self.activities.count()-1).setData(Qt.ItemDataRole.UserRole, row["id"])
        self.materials.setPlainText("\n\n".join(lines) if lines else "연결된 자료가 없습니다.")
        self.has_more = page["has_more"]
        self.next_button.setEnabled(self.has_more)
        self.delete_button.setEnabled(self.activities.count() > 0)
        self.status.setText(f"작업 {self.activities.count()}/{page['total']}건")

    def _next_page(self):
        """서버의 has_more가 참일 때만 다음 페이지를 요청한다."""
        if self.has_more and self.detail_client.reply is None:
            self.offset += 200
            self.detail_client.get(f"/sessions/{self.session_id}?limit=200&offset={self.offset}")

    def delete_selected(self):
        """선택 ID를 사용자에게 확인한 후에만 삭제한다. 취소하면 요청하지 않는다."""
        item = self.activities.currentItem()
        if item is None or self.delete_client.reply is not None:
            return
        record_id = item.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "작업 삭제", f"작업 #{record_id}와 연결된 저장 자료를 삭제할까요?",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.delete_client.delete(f"/records/{record_id}")

    def delete_all(self):
        """수집 중 새 기록이 생성될 수 있음을 설명하고 전체 삭제 확인을 받는다."""
        if self.delete_client.reply is not None:
            return
        if QMessageBox.question(self, "전체 기록 삭제", "저장된 모든 기록과 검색 자료를 삭제할까요?\n수집 중이면 이후 새 기록이 생성됩니다.",
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.delete_client.delete("/records?confirm=true")

    def _deleted(self, payload):
        """서버의 삭제 성공을 확인한 뒤 다른 기록·검색 화면도 갱신한다."""
        try:
            data = data_object(payload)
            if data.get("deleted") is not True and not isinstance(data.get("deleted_counts"), dict):
                raise ValueError("Deletion not confirmed")
        except (ValueError, TypeError):
            self._error("삭제 결과를 확인할 수 없습니다. 새로고침해 주세요.")
            return
        self.records_changed.emit()
        self.refresh()

    def _error(self, message):
        """이전 상세를 현재 결과로 오인하지 않게 비운다."""
        self.activities.clear()
        self.materials.clear()
        self.delete_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.status.setText(message)
