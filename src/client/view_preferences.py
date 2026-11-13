"""민감한 작업 자료와 분리해 창 위치·관리 크기·읽기 비율만 기억한다."""

from PySide6.QtCore import QPoint, QSettings, QSize

_PREFIX = "ui/v1"
_RATIO_KEYS = frozenset({"recent", "documents", "answer"})
_MAX_COORDINATE = 100_000


class ViewPreferences:
    """허용된 표시 값만 읽고 저장 실패는 선택적 UI 설정 실패로 처리한다."""

    def __init__(self, settings: QSettings | None = None) -> None:
        """테스트는 별도 INI를 주입하고 일반 실행은 제품 전용 설정 영역을 사용한다."""
        self._settings = settings if settings is not None else QSettings("GangSearch", "GangSearch")

    def _value(self, key: str) -> object:
        """읽기 오류나 손상된 설정 파일 때문에 Client 실행을 중단하지 않는다."""
        try:
            value = self._settings.value(key)
            return value if self._settings.status() == QSettings.Status.NoError else None
        except Exception:
            return None

    def _write(self, key: str, value: object) -> bool:
        """확인된 표시 값만 쓰고 동기화 실패를 호출자에게 반환한다."""
        try:
            self._settings.setValue(key, value)
            self._settings.sync()
            return self._settings.status() == QSettings.Status.NoError
        except Exception:
            return False

    @staticmethod
    def _position(value: object) -> QPoint | None:
        """음수 모니터 좌표를 허용하되 잘못된 타입과 비정상 좌표는 무시한다."""
        if (not isinstance(value, QPoint) or abs(value.x()) > _MAX_COORDINATE
                or abs(value.y()) > _MAX_COORDINATE):
            return None
        return QPoint(value)

    @staticmethod
    def _management_size(value: object) -> QSize | None:
        """관리 화면의 양수 크기를 제한하고 실제 화면 경계 맞춤은 창에 맡긴다."""
        if not isinstance(value, QSize) or value.width() <= 0 or value.height() <= 0:
            return None
        return QSize(min(4096, max(320, value.width())), min(2160, max(240, value.height())))

    def read_position(self) -> QPoint | None:
        """창 위치만 복원하며 모니터가 달라졌을 때의 배치는 호출자가 결정한다."""
        return self._position(self._value(f"{_PREFIX}/window_position"))

    def read_management_size(self) -> QSize | None:
        """검색 상태별 작은 크기와 분리한 관리 화면의 크기를 복원한다."""
        return self._management_size(self._value(f"{_PREFIX}/management_size"))

    def read_ratio(self, key: str) -> int | None:
        """허용된 읽기 영역의 첫 패널 비율만 복원하고 손상 값은 기본 배치를 쓰게 한다."""
        if not isinstance(key, str) or key not in _RATIO_KEYS:
            return None
        value = self._value(f"{_PREFIX}/ratios/{key}")
        # INI는 다시 열면 정수를 문자열로 읽을 수 있으므로 정규 십진수만 호환한다.
        if (isinstance(value, str) and len(value) == 2 and value.isascii()
                and value.isdecimal()):
            value = int(value)
        return value if type(value) is int and 10 <= value <= 90 else None

    def save_position(self, position: QPoint) -> bool:
        """위치만 저장하며 화면 내용·선택 작업·파일 경로를 받지 않는다."""
        value = self._position(position)
        return value is not None and self._write(f"{_PREFIX}/window_position", value)

    def save_management_size(self, size: QSize) -> bool:
        """관리 창의 크기만 저장하고 비정상 크기는 기존 설정을 건드리지 않는다."""
        value = self._management_size(size)
        return value is not None and self._write(f"{_PREFIX}/management_size", value)

    def save_ratio(self, key: str, sizes: list[int] | tuple[int, int]) -> bool:
        """펼친 두 패널의 비율만 저장하고 접힌 상태·임의 문자열은 저장하지 않는다."""
        if (not isinstance(key, str) or key not in _RATIO_KEYS
                or not isinstance(sizes, (list, tuple)) or len(sizes) != 2
                or any(type(size) is not int or not 0 < size <= 2**31 - 1 for size in sizes)):
            return False
        ratio = min(90, max(10, round(sizes[0] * 100 / sum(sizes))))
        return self._write(f"{_PREFIX}/ratios/{key}", ratio)
