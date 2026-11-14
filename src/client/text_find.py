"""이미 받은 읽기 전용 본문 안에서만 문자열을 찾고 표시 위치를 이동한다."""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeySequence, QPalette, QShortcut, QTextCursor, QTextFormat
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QWidget,
)

from client.theme import set_role

_FIND_PROPERTY = int(QTextFormat.Property.UserProperty) + 104


class TextFindBar(QWidget):
    """본문을 고치거나 요청을 보내지 않는 접이식 찾기 바다. 검색어는 메모리에만 둔다."""

    def __init__(self, target: QPlainTextEdit, parent: QWidget | None = None, *,
                 shortcut_owner: QWidget | None = None) -> None:
        """소유 화면 안의 Ctrl+F를 받고 현재 보이는 본문 한 곳만 검색한다."""
        super().__init__(parent)
        self.target: QPlainTextEdit | None = None
        self._matches: list[tuple[int, int]] = []
        self._current = -1
        # 다른 강조 기능의 ExtraSelection을 지우지 않도록 이 바의 표시만 식별한다.
        self._selection_key = str(id(self))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.query = QLineEdit()
        self.query.setPlaceholderText("본문에서 찾기")
        self.query.setAccessibleName("현재 본문에서 찾을 내용")
        self.query.setClearButtonEnabled(True)
        self.query.setMinimumWidth(0)
        self.query.textChanged.connect(self._query_changed)
        self.query.installEventFilter(self)
        layout.addWidget(self.query, 1)
        self.result_label = QLabel("0/0")
        self.result_label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.result_label)
        self.previous_button = QPushButton("↑")
        self.next_button = QPushButton("↓")
        self.close_button = QPushButton("×")
        for button, name, hint, callback in (
            (self.previous_button, "이전 일치 항목", "이전 일치 항목 (Shift+Enter)", self.find_previous),
            (self.next_button, "다음 일치 항목", "다음 일치 항목 (Enter)", self.find_next),
            (self.close_button, "본문 찾기 닫기", "본문 찾기 닫기 (Esc)", self.close_find),
        ):
            button.setAccessibleName(name)
            button.setToolTip(hint)
            set_role(button, "quiet")
            button.clicked.connect(callback)
            layout.addWidget(button)
        # 같은 기록 화면의 상세 탭마다 단축키를 중복 설치하지 않는다.
        owner = shortcut_owner or parent or target
        self.find_shortcut = QShortcut(QKeySequence("Ctrl+F"), owner)
        self.find_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.find_shortcut.activated.connect(self.open)
        self.close_shortcut = QShortcut(QKeySequence("Esc"), owner)
        self.close_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.close_shortcut.activated.connect(self.close_find)
        self.close_shortcut.setEnabled(False)
        self.hide()
        self.set_target(target)

    def set_target(self, target: QPlainTextEdit | None) -> None:
        """상세 탭이 바뀌면 옛 본문의 찾기 표시만 지우고 새 본문으로 대상을 바꾼다."""
        if target is self.target:
            return
        if self.target is not None:
            self._remove_highlights()
            self.target.textChanged.disconnect(self._document_changed)
        self.target = target
        if target is not None:
            target.textChanged.connect(self._document_changed)
        self.query.setEnabled(target is not None)
        self._rebuild(move=False)

    def open(self) -> None:
        """명시적인 찾기 요청에만 바를 펼치고 검색 입력에 초점을 둔다."""
        if self.target is None or not self.target.isVisible():
            return
        self.show()
        self.close_shortcut.setEnabled(True)
        self._rebuild(move=True)
        self.query.setFocus()
        self.query.selectAll()

    def close_find(self) -> None:
        """찾기 강조를 해제하고 현재 본문으로 돌아가며 검색어는 실행 중에만 기억한다."""
        self.hide()
        self.close_shortcut.setEnabled(False)
        self._matches = []
        self._current = -1
        self._show_current(move=False)
        if self.target is not None and self.target.isVisible():
            self.target.setFocus()

    def eventFilter(self, watched, event) -> bool:
        """검색 입력의 Enter·Shift+Enter를 본문 수정 없이 다음·이전 이동으로 처리한다."""
        if (watched is self.query and event.type() == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.find_previous()
            else:
                self.find_next()
            return True
        return super().eventFilter(watched, event)

    def _query_changed(self, _text: str) -> None:
        """문자 그대로 대소문자를 구분하지 않고 현재 문서에서 처음부터 다시 찾는다."""
        self._rebuild(move=True)

    def _document_changed(self) -> None:
        """선택 변경·새 응답·오류로 본문이 교체되면 이전 일치 위치를 즉시 버린다."""
        self._rebuild(move=False)

    def _rebuild(self, *, move: bool) -> None:
        """Qt의 UTF-16 커서 좌표로 일치 목록을 만들어 이모지 앞뒤도 정확히 이동한다."""
        self._remove_highlights()
        self._matches = []
        self._current = -1
        if self.target is not None and not self.isHidden() and self.query.text():
            document = self.target.document()
            position = 0
            while True:
                cursor = document.find(self.query.text(), position)
                if cursor.isNull() or cursor.selectionEnd() <= position:
                    break
                self._matches.append((cursor.selectionStart(), cursor.selectionEnd()))
                position = cursor.selectionEnd()
            if self._matches:
                self._current = 0
        self._show_current(move=move)

    def find_next(self) -> None:
        """마지막 일치 항목 뒤에는 첫 항목으로 돌아간다."""
        self._navigate(1)

    def find_previous(self) -> None:
        """첫 일치 항목 앞에는 마지막 항목으로 돌아간다."""
        self._navigate(-1)

    def _navigate(self, step: int) -> None:
        """일치 항목이 있을 때만 현재 본문의 표시 위치를 이동한다."""
        if self._matches:
            self._current = (self._current + step) % len(self._matches)
            self._show_current(move=True)

    def _remove_highlights(self) -> None:
        """자신이 추가한 표시만 제거해 다른 기능이 쓰는 인용·선택 강조를 보존한다."""
        if self.target is not None:
            self.target.setExtraSelections([
                selection for selection in self.target.extraSelections()
                if selection.format.property(_FIND_PROPERTY) != self._selection_key
            ])

    def _show_current(self, *, move: bool) -> None:
        """현재 일치만 별도 강조하고 실제 텍스트나 문서 서식에는 쓰지 않는다."""
        self._remove_highlights()
        total = len(self._matches)
        self.result_label.setText(f"{self._current + 1}/{total}")
        self.result_label.setAccessibleName(
            f"일치 항목 {total}개 중 {self._current + 1}번째" if total else "일치 항목 없음")
        hint = "현재 받은 본문 안에서만 찾습니다. 대소문자는 구분하지 않습니다."
        if self.query.text() and not total:
            hint = "일치하는 내용이 없습니다. " + hint
        self.result_label.setToolTip(hint)
        self.previous_button.setEnabled(total > 0)
        self.next_button.setEnabled(total > 0)
        if total and self.target is not None:
            first, last = self._matches[self._current]
            cursor = QTextCursor(self.target.document())
            cursor.setPosition(first)
            cursor.setPosition(last, QTextCursor.MoveMode.KeepAnchor)
            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor
            selection.format.setProperty(_FIND_PROPERTY, self._selection_key)
            color = self.target.palette().color(QPalette.ColorRole.Highlight)
            color.setAlpha(100)
            selection.format.setBackground(color)
            self.target.setExtraSelections([*self.target.extraSelections(), selection])
            if move:
                self.target.setTextCursor(cursor)
                self.target.ensureCursorVisible()
