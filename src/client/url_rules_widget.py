"""URL 규칙의 편집 초안과 서버 적용값을 분리한다. 네트워크 요청은 부모가 담당한다."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from client.theme import set_role
from client.url_values import normalize_rule, normalize_rules
from shared.browser import UrlBlockRule

KINDS = {"domain": "도메인", "exact": "전체 URL", "prefix": "URL 시작 부분"}


class UrlRulesWidget(QWidget):
    """명시적 적용 전에는 서버에 쓰지 않으며 폴링·재연결에도 미적용 초안을 보존한다."""

    apply_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        """차단 방식 선택, 주소 입력, 목록 확인과 적용을 한 화면에 배치한다."""
        super().__init__(parent)
        self.draft: list[UrlBlockRule] = []
        self.applied: list[UrlBlockRule] = []
        self.dirty = False
        self.editable = False
        self._confirmed = self._supported = False
        layout = QVBoxLayout(self)
        self.status = QLabel("서버 설정 확인 필요")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.availability_message = QLabel()
        self.availability_message.setTextFormat(Qt.TextFormat.PlainText)
        self.availability_message.setWordWrap(True)
        self.availability_message.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred,
        )
        layout.addWidget(self.availability_message)
        # 기존 탭·편집 위젯은 유지하고 지원이 확인됐을 때만 편집 영역을 펼친다.
        self.editor_panel = QWidget()
        editor_layout = QVBoxLayout(self.editor_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        self.kind = QComboBox()
        for key, label in KINDS.items():
            self.kind.addItem(label, key)
        self.value = QLineEdit()
        self.value.setAccessibleName("차단할 도메인 또는 URL")
        self.value.textChanged.connect(self._show_availability)
        self.add_button = QPushButton("목록에 추가")
        self.add_button.clicked.connect(self._add)
        self.value.returnPressed.connect(self._add)
        entry = QHBoxLayout()
        entry.addWidget(self.kind)
        entry.addWidget(self.value, 1)
        entry.addWidget(self.add_button)
        editor_layout.addLayout(entry)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        editor_layout.addWidget(self.hint)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["차단 방식", "주소"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.itemSelectionChanged.connect(self._controls)
        editor_layout.addWidget(self.table, 1)
        self.validation = QLabel()
        self.validation.setTextFormat(Qt.TextFormat.PlainText)
        self.validation.setWordWrap(True)
        editor_layout.addWidget(self.validation)
        self.remove_button = QPushButton("초안에서 제거")
        self.reset_button = QPushButton("확인된 목록으로 되돌리기")
        self.reset_button.setToolTip("목록과 입력만 확인된 값으로 되돌립니다. 서버에는 요청하지 않습니다.")
        self.apply_button = QPushButton("URL 차단 목록 적용")
        self.remove_button.clicked.connect(self._remove)
        self.reset_button.clicked.connect(self._reset)
        self.apply_button.clicked.connect(self._apply)
        buttons = QHBoxLayout()
        for button in (self.remove_button, self.reset_button, self.apply_button):
            buttons.addWidget(button)
        editor_layout.addLayout(buttons)
        layout.addWidget(self.editor_panel, 1)
        self._unavailable_space = QWidget()
        self._unavailable_space.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self._unavailable_space, 1)
        set_role(self.apply_button, "primary")
        for button in (self.add_button, self.remove_button, self.reset_button):
            set_role(button, "quiet")
        self._kind_changed()
        self._show_availability()
        self._controls()

    def show_rules(self, rules: list[UrlBlockRule] | None, operation: str) -> None:
        """확인된 서버 목록을 수신한다. 다른 설정을 바꿀 때 URL 초안은 덮어쓰지 않는다."""
        # 미지원 None은 빈 목록 확인이 아니다. 전체 해제 초안과 마지막 비교 기준도 보존한다.
        if rules is None:
            return
        self.applied = list(rules)
        if not self.dirty or operation == "urls":
            self.draft = list(rules)
            self._render()
        self.dirty = self.draft != self.applied

    def set_availability(self, confirmed: bool, supported: bool) -> None:
        """알 수 없는 상태·미지원·쓰기 중에는 적용을 잠그되 사용자의 입력은 지우지 않는다."""
        self._confirmed, self._supported = confirmed, supported
        self.editable = confirmed and supported
        self._show_availability()
        self._controls()

    def _show_availability(self, _text: str = "") -> None:
        """확인 전과 확인된 미지원을 구분하고 숨겨진 미적용 입력의 존재만 안내한다."""
        if self._confirmed and self._supported:
            message = "목록을 편집한 뒤 적용을 눌러야 서버 설정에 반영됩니다."
        elif self._confirmed:
            message = "현재 연결한 서버에서는 URL 차단 기능을 사용할 수 없습니다."
        else:
            message = "서버 설정이 미확인 상태입니다. 연결 또는 보호 상태를 확인해 주세요."
        pending = self.dirty or bool(self.value.text().strip())
        if pending and not self.editable:
            message += " 미적용 목록과 입력은 이 화면에 유지됩니다."
        self.availability_message.setText(message)
        self.editor_panel.setVisible(self.editable)
        self._unavailable_space.setVisible(not self.editable)
        state = (f"서버 URL 차단 규칙 {len(self.applied)}개" if self.editable else
                 "URL 차단 기능 미지원" if self._confirmed else "서버 설정 확인 필요")
        if self.dirty and self.editable:
            added = sum(rule not in self.applied for rule in self.draft)
            removed = sum(rule not in self.draft for rule in self.applied)
            prefix = f"미적용 목록 있음 · 추가 {added}개 · 제외 {removed}개 · "
        else:
            prefix = "미적용 목록 있음 · " if self.dirty else ""
        if self.value.text().strip():
            prefix += "목록에 추가하지 않은 입력 있음 · "
        self.status.setText(prefix + state)

    def _kind_changed(self) -> None:
        """차단 범위를 입력 전에 설명해 전체 도메인과 특정 페이지를 구분하도록 돕는다."""
        kind = self.kind.currentData()
        examples = {"domain": "example.com", "exact": "https://example.com/private/page",
                    "prefix": "https://example.com/private/"}
        hints = {"domain": "해당 도메인과 하위 도메인을 포함합니다.",
                 "exact": "주소 전체가 같은 페이지만 지정합니다. ?와 # 뒤의 값도 구분합니다.",
                 "prefix": "입력한 주소로 시작하는 페이지를 지정합니다. 폴더 범위는 /로 끝내세요."}
        self.value.setPlaceholderText(examples[kind])
        self.hint.setText(hints[kind])

    def _add(self) -> None:
        """입력을 검증한 뒤 초안에만 추가한다. 추가 버튼 자체는 차단 적용이 아니다."""
        if not self.editable:
            return
        try:
            rule = normalize_rule(self.kind.currentData(), self.value.text())
            self.draft = normalize_rules([*self.draft, rule])
        except ValueError as error:
            self.validation.setText(str(error))
            return
        self.value.clear()
        self.validation.clear()
        self._draft_changed()

    def _remove(self) -> None:
        """선택 규칙을 초안에서만 삭제한다. 마지막 규칙도 적용을 눌러야 서버에서 해제된다."""
        row = self.table.currentRow()
        if self.editable and 0 <= row < len(self.draft):
            del self.draft[row]
            self._draft_changed()

    def _reset(self) -> None:
        """서버의 최근 확인값으로 초안을 복원하고 입력란을 비운다. 쓰기 요청은 없다."""
        if self.editable:
            self.draft = list(self.applied)
            self.value.clear()
            self.validation.clear()
            self._draft_changed()

    def _apply(self) -> None:
        """입력란에 남은 주소를 누락한 채 저장하지 않도록 먼저 목록 추가를 안내한다."""
        if self.editable and self.dirty:
            if self.value.text().strip():
                self.validation.setText("입력 중인 주소를 목록에 추가하거나 지운 뒤 적용해 주세요.")
                return
            self.apply_requested.emit(list(self.draft))

    def _draft_changed(self) -> None:
        """초안 변경 뒤 서버와의 차이·표·버튼을 함께 갱신한다."""
        self.dirty = self.draft != self.applied
        self._render()
        self.set_availability(True, True)

    def _render(self) -> None:
        """규칙을 일반 텍스트 표로 재배치한다. 긴 주소는 열 안에서 잘리고 툴팁으로 확인한다."""
        self.table.setRowCount(len(self.draft))
        for row, rule in enumerate(self.draft):
            for column, text in enumerate((KINDS[rule.kind], rule.value)):
                item = QTableWidgetItem(text)
                # URL 검증에서 <, >를 거부하므로 주소가 툴팁 HTML로 해석되지 않는다.
                item.setToolTip(text)
                self.table.setItem(row, column, item)

    def _controls(self) -> None:
        """표 선택과 서버 확인 상태를 조합해 가능한 편집만 노출한다."""
        for widget in (self.kind, self.value, self.add_button):
            widget.setEnabled(self.editable)
        self.remove_button.setEnabled(self.editable and 0 <= self.table.currentRow() < len(self.draft))
        self.apply_button.setEnabled(self.editable and self.dirty)
        self.reset_button.setEnabled(self.editable)
