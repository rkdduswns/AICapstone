"""확인된 원본 출처를 사용자가 명시적으로 복사하거나 여는 작은 메뉴."""

import re
from pathlib import Path, PureWindowsPath

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMenu, QPushButton, QWidget

from client.document_values import read_document
from client.icons import apply_menu_icon
from client.theme import set_role
from shared.browser_values import normalize_http_url

_DEVICE_NAMES = frozenset({"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"})


def _document_path(value: object) -> str | None:
    """기존 문서 출처 검증을 재사용하고 Windows 장치 별칭은 열기 대상으로 받지 않는다."""
    if not isinstance(value, str):
        return None
    windows = PureWindowsPath(value)
    try:
        document = read_document({"file_path": value, "file_type": windows.suffix.lower()[1:]})
    except ValueError:
        return None
    # 확장자가 붙어도 CON.pdf 등은 일반 파일 대신 Windows 장치를 가리킬 수 있다.
    for part in windows.parts[1:]:
        name = part.split(".", 1)[0].rstrip(" ").upper()
        if name in _DEVICE_NAMES or re.fullmatch(r"(?:COM|LPT)[1-9¹²³]", name):
            return None
    return document.file_path


class SourceActionsButton(QPushButton):
    """원본 값만 메모리에 유지하며 선택 변경 시 이전 메뉴와 동작 대상을 함께 비운다."""

    message = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """출처별 동작을 한 단계 메뉴에 모으고 원본이 없으면 버튼을 비활성화한다."""
        super().__init__(parent)
        self._url: str | None = None
        self._file_path: str | None = None
        self.source_menu = QMenu(self)
        self.source_menu.setToolTipsVisible(True)
        self.open_url_action = self.source_menu.addAction("웹페이지 열기")
        self.copy_url_action = self.source_menu.addAction("URL 복사")
        self.separator = self.source_menu.addSeparator()
        self.open_file_action = self.source_menu.addAction("원본 파일 열기")
        self.open_folder_action = self.source_menu.addAction("폴더 열기")
        self.copy_path_action = self.source_menu.addAction("파일 경로 복사")
        self.open_url_action.triggered.connect(self._open_url)
        self.copy_url_action.triggered.connect(self._copy_url)
        self.open_file_action.triggered.connect(self._open_file)
        self.open_folder_action.triggered.connect(self._open_folder)
        self.copy_path_action.triggered.connect(self._copy_path)
        self.setMenu(self.source_menu)
        apply_menu_icon(self, "more", "원본 출처 열기·복사")
        set_role(self, "quiet")
        self.set_source()

    def set_source(self, url: str | None = None, file_path: str | None = None) -> None:
        """서버가 확인한 원본만 받으며 조회·선택 변경 자체로 파일이나 URL을 열지 않는다."""
        verified_url = None
        if isinstance(url, str):
            try:
                normalize_http_url(url)
            except ValueError:
                verified_url = None
            else:
                verified_url = url
        verified_path = _document_path(file_path)
        if (verified_url, verified_path) != (self._url, self._file_path):
            # 열린 메뉴의 대상이 폴링·선택 전환으로 다른 출처로 바뀌지 않도록 닫는다.
            self.source_menu.hide()
        self._url, self._file_path = verified_url, verified_path
        has_url, has_path = verified_url is not None, verified_path is not None
        local_path = has_path and self._is_local_path()
        for action in (self.open_url_action, self.copy_url_action):
            action.setVisible(has_url)
            action.setEnabled(has_url)
        for action in (self.open_file_action, self.open_folder_action, self.copy_path_action):
            action.setVisible(has_path)
            action.setEnabled(has_path)
        # UNC는 복사만 허용한다. 메뉴 표시·선택만으로 공유 서버에 접속하지 않는다.
        for action in (self.open_file_action, self.open_folder_action):
            action.setEnabled(local_path)
            action.setToolTip("네트워크 공유 경로는 복사해서 확인해 주세요." if has_path and not local_path else "")
        self.separator.setVisible(has_url and has_path)
        self.setEnabled(has_url or has_path)

    @property
    def url(self) -> str | None:
        """현재 검증된 원본 URL을 읽기 전용으로 제공한다."""
        return self._url

    @property
    def file_path(self) -> str | None:
        """현재 검증된 원본 문서 경로를 읽기 전용으로 제공한다."""
        return self._file_path

    def clear(self) -> None:
        """선택 해제·재조회·오류에서 이전 출처를 다시 열지 못하게 한다."""
        self.set_source()

    def _is_local_path(self) -> bool:
        """파일 시스템을 조회하지 않고 드라이브 절대 경로인지 판별한다."""
        return self._file_path is not None and bool(
            re.fullmatch(r"[A-Za-z]:", PureWindowsPath(self._file_path).drive)
        )

    def _copy_url(self) -> None:
        """현재 확인된 URL 원문만 명시적 복사 동작에서 클립보드에 쓴다."""
        if self._url is not None:
            QApplication.clipboard().setText(self._url)

    def _copy_path(self) -> None:
        """서버 사본이나 추정 경로를 만들지 않고 원본 경로 그대로 복사한다."""
        if self._file_path is not None:
            QApplication.clipboard().setText(self._file_path)

    def _open_url(self) -> None:
        """검증된 HTTP(S) 출처만 기본 브라우저로 열고 실패를 화면에 알린다."""
        if self._url is not None and not QDesktopServices.openUrl(QUrl(self._url)):
            self.message.emit("웹페이지를 열지 못했습니다. 기본 브라우저 설정을 확인해 주세요.")

    def _open_file(self) -> None:
        """사용자 동작 시에만 로컬 원본의 존재를 검사하며 본문을 읽거나 추출하지 않는다."""
        if not self._is_local_path():
            return
        path = Path(self._file_path)
        try:
            exists = path.is_file()
        except OSError:
            exists = False
        if not exists:
            self.message.emit("원본 파일을 찾을 수 없습니다. 파일이 이동·삭제됐거나 접근할 수 없는지 확인해 주세요.")
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(self._file_path)):
            self.message.emit("원본 파일을 열지 못했습니다. PDF·DOCX 기본 앱 설정을 확인해 주세요.")

    def _open_folder(self) -> None:
        """원본의 폴더만 열며 shell 명령이나 서버에 저장된 사본 경로를 실행하지 않는다."""
        if not self._is_local_path():
            return
        folder = Path(self._file_path).parent
        try:
            exists = folder.is_dir()
        except OSError:
            exists = False
        if not exists:
            self.message.emit("원본 폴더를 찾을 수 없습니다. 경로가 이동·삭제됐거나 접근할 수 없는지 확인해 주세요.")
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            self.message.emit("원본 폴더를 열지 못했습니다. Windows 파일 탐색기 설정을 확인해 주세요.")
