"""받은 본문 안의 찾기·이동이 원문과 다른 강조·상세 선택을 바꾸지 않는지 검증한다."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from client.text_find import TextFindBar


@pytest.fixture(scope="module")
def app():
    """네트워크나 사용자 설정 없이 같은 이벤트 루프에서 찾기 조작을 확인한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


@pytest.fixture
def reader(app):
    """본문 밖에 초점을 둔 상태에서도 소유 화면의 단축키를 시험할 수 있게 한다."""
    window = QWidget()
    layout = QVBoxLayout(window)
    button = QPushButton("목록에 초점")
    layout.addWidget(button)
    text = QPlainTextEdit()
    text.setReadOnly(True)
    bar = TextFindBar(text, window, shortcut_owner=window)
    layout.addWidget(bar)
    layout.addWidget(text)
    window.resize(380, 400)
    window.show()
    window.activateWindow()
    app.processEvents()
    yield window, text, bar, button
    window.close()


def test_find_is_hidden_until_requested_and_keeps_readonly_plain_text(reader):
    """문자 그대로 찾으면서 HTML·정규식 모양 입력과 원문 문서의 변경 여부를 보존한다."""
    _, text, bar, _ = reader
    original = "<b>한글</b> [.*] 첫째\n둘째 [.*]"
    text.setPlainText(original)
    text.document().setModified(False)
    assert bar.isHidden()
    bar.open()
    bar.query.setText("[.*]")
    assert bar.result_label.text() == "1/2"
    assert text.textCursor().selectedText() == "[.*]"
    assert text.toPlainText() == original
    assert text.isReadOnly() and not text.document().isModified()


def test_unicode_cursor_offsets_and_case_insensitive_navigation_wrap(reader):
    """보조 평면 이모지 앞뒤의 UTF-16 위치와 한글·영문 대소문자 검색을 함께 확인한다."""
    _, text, bar, _ = reader
    text.setPlainText("😀한글 Needle 뒤\n한글 NEEDLE 😀한글")
    bar.open()
    bar.query.setText("한글")
    assert text.textCursor().selectionStart() == 2
    assert text.textCursor().selectedText() == "한글"
    assert bar.result_label.text() == "1/3"
    bar.find_previous()
    assert bar.result_label.text() == "3/3"
    assert text.textCursor().selectedText() == "한글"
    bar.find_next()
    assert bar.result_label.text() == "1/3"
    bar.query.setText("needle")
    assert bar.result_label.text() == "1/2"
    bar.find_next()
    assert text.textCursor().selectedText() == "NEEDLE"
    assert bar.result_label.text() == "2/2"
    bar.find_next()
    assert bar.result_label.text() == "1/2"


def test_empty_and_missing_query_do_not_move_cursor_or_leave_old_highlights(reader):
    """빈 검색어나 0건에서 이동을 잠그고 이전 찾기 표시를 남기지 않는다."""
    _, text, bar, _ = reader
    text.setPlainText("본문 한글")
    bar.open()
    bar.query.setText("한글")
    assert len(text.extraSelections()) == 1
    bar.query.setText("없음")
    position = text.textCursor().position()
    assert bar.result_label.text() == "0/0" and not text.extraSelections()
    assert not bar.next_button.isEnabled() and not bar.previous_button.isEnabled()
    bar.find_next()
    bar.find_previous()
    assert text.textCursor().position() == position
    bar.query.clear()
    assert bar.result_label.text() == "0/0"


def test_body_replacement_and_clear_rebuild_matches_without_reusing_old_positions(reader):
    """새 응답·조회 실패로 본문이 바뀌면 옛 좌표가 새 자료에 적용되지 않는다."""
    _, text, bar, _ = reader
    text.setPlainText("첫 본문 한글 한글")
    bar.open()
    bar.query.setText("한글")
    bar.find_next()
    assert bar.result_label.text() == "2/2"
    text.setPlainText("새 한글")
    assert bar.result_label.text() == "1/1"
    assert text.extraSelections()[0].cursor.selectedText() == "한글"
    text.clear()
    assert bar.result_label.text() == "0/0" and not text.extraSelections()
    assert bar.query.text() == "한글"
    assert not bar.next_button.isEnabled()


def test_switch_target_clears_old_find_marks_and_searches_only_new_body(app, reader):
    """한 화면의 상세 탭 전환은 검색어만 유지하고 이전 본문과 새 본문을 섞지 않는다."""
    window, first, bar, _ = reader
    second = QPlainTextEdit(window)
    second.setReadOnly(True)
    window.layout().addWidget(second)
    first.setPlainText("한글 한글")
    second.setPlainText("다른 본문 한글")
    bar.open()
    bar.query.setText("한글")
    assert bar.result_label.text() == "1/2"
    bar.set_target(second)
    app.processEvents()
    assert not first.extraSelections()
    assert bar.result_label.text() == "1/1"
    assert second.extraSelections()[0].cursor.selectedText() == "한글"
    bar.set_target(None)
    assert not second.extraSelections() and not bar.query.isEnabled()
    assert bar.result_label.text() == "0/0"


def test_existing_extra_selection_survives_find_next_clear_and_close(reader):
    """인용 등 다른 기능의 강조는 찾기 표시 추가·갱신·닫기에 영향을 받지 않는다."""
    _, text, bar, _ = reader
    text.setPlainText("기존 강조 한글 한글")
    selection = QTextEdit.ExtraSelection()
    selection.cursor = QTextCursor(text.document())
    selection.cursor.setPosition(0)
    selection.cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
    selection.format.setFontUnderline(True)
    text.setExtraSelections([selection])
    bar.open()
    bar.query.setText("한글")
    bar.find_next()
    assert len(text.extraSelections()) == 2
    bar.query.clear()
    assert len(text.extraSelections()) == 1
    assert text.extraSelections()[0].format.fontUnderline()
    bar.query.setText("한글")
    bar.close_find()
    assert len(text.extraSelections()) == 1
    assert text.extraSelections()[0].cursor.selectedText() == "기존 강조"


def test_shortcuts_from_sibling_and_enter_shift_enter_escape_restore_focus(app, reader):
    """목록 초점의 Ctrl+F와 검색 입력의 이동·닫기가 소유 화면 밖으로 전파되지 않는다."""
    _, text, bar, button = reader
    text.setPlainText("한글 한글")
    button.setFocus()
    app.processEvents()
    QTest.keyClick(button, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert not bar.isHidden() and bar.query.hasFocus()
    QTest.keyClicks(bar.query, "a")
    bar.query.setText("한글")
    QTest.keyClick(bar.query, Qt.Key.Key_Return)
    assert bar.result_label.text() == "2/2"
    QTest.keyClick(bar.query, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert bar.result_label.text() == "1/2"
    QTest.keyClick(bar.query, Qt.Key.Key_Escape)
    app.processEvents()
    assert bar.isHidden() and text.hasFocus()
    assert bar.query.text() == "한글" and not text.extraSelections()
    assert not bar.close_shortcut.isEnabled()


def test_escape_from_body_closes_open_find_before_owner_navigation(app, reader):
    """본문으로 초점을 옮긴 뒤에도 Esc는 열린 찾기부터 닫고 상위 화면으로 전달되지 않는다."""
    _, text, bar, _ = reader
    text.setPlainText("한글")
    bar.open()
    bar.query.setText("한글")
    text.setFocus()
    app.processEvents()
    QTest.keyClick(text, Qt.Key.Key_Escape)
    app.processEvents()
    assert bar.isHidden() and text.hasFocus()
    assert not text.extraSelections()


def test_hidden_body_is_not_opened_or_searched_by_find_shortcut(reader):
    """표시되지 않는 상세 본문을 찾기 요청 때문에 노출하거나 선택하지 않는다."""
    _, text, bar, _ = reader
    text.setPlainText("숨은 자료")
    text.hide()
    bar.open()
    assert bar.isHidden() and not text.extraSelections()
