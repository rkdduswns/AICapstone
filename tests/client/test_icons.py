"""아이콘 메뉴의 접근성과 배율·팔레트별 렌더링을 확인한다."""

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QMenu, QPushButton

from client.icons import apply_menu_icon
from client.theme import apply_client_style


@pytest.fixture(scope="module")
def app():
    """메뉴와 아이콘을 같은 Qt 애플리케이션에서 검증한다."""
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("kind", ["menu", "more"])
def test_icon_menu_retains_actions_and_accessible_label(app, kind):
    """문자 없는 작은 버튼에서도 기존 메뉴와 보조기술용 설명을 유지한다."""
    button = QPushButton("이전 메뉴")
    apply_client_style(button)
    menu = QMenu(button)
    action = menu.addAction("가상 동작")
    button.setMenu(menu)
    apply_menu_icon(button, kind, "화면과 설정 메뉴")
    assert button.text() == ""
    assert button.toolTip() == button.accessibleName() == "화면과 설정 메뉴"
    assert button.menu() is menu and menu.actions() == [action]
    assert not button.icon().isNull()
    assert button.size().width() >= 30 and button.size().height() >= 30
    button.close()


@pytest.mark.parametrize("kind", ["menu", "more"])
def test_icon_renders_at_requested_density_and_tracks_palette(app, kind):
    """이미 생성된 아이콘도 색상 변경과 비활성 상태·고해상도 요청을 반영한다."""
    original = app.palette()
    button = QPushButton()
    apply_menu_icon(button, kind, "가상 메뉴")
    try:
        for normal in (QColor(20, 30, 40), QColor(220, 230, 240)):
            palette = QPalette(original)
            disabled = QColor(90, 100, 110)
            palette.setColor(QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText, normal)
            palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled)
            app.setPalette(palette)
            for mode, expected in ((QIcon.Mode.Normal, normal), (QIcon.Mode.Disabled, disabled)):
                for density in (1.0, 1.5, 2.0):
                    pixmap = button.icon().pixmap(QSize(18, 18), density, mode, QIcon.State.Off)
                    assert not pixmap.isNull()
                    assert pixmap.devicePixelRatio() == density
                    assert pixmap.width() == pixmap.height() == round(18 * density)
                    image = pixmap.toImage()
                    colors = [image.pixelColor(x, y)
                              for y in range(image.height()) for x in range(image.width())]
                    # 얇은 선은 반투명 가장자리만 생길 수도 있어 색상 반올림을 함께 허용한다.
                    assert any(color.alpha() >= 128
                               and abs(color.red() - expected.red()) <= 2
                               and abs(color.green() - expected.green()) <= 2
                               and abs(color.blue() - expected.blue()) <= 2
                               for color in colors)
    finally:
        app.setPalette(original)
        button.close()
