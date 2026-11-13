"""현재 지원하는 개인정보 설정의 저장 규격과 공통 입력 검증을 정의한다."""

from pydantic import BaseModel, ConfigDict, field_validator

from shared.privacy import MAX_BLOCKED_PROCESSES


def normalize_blocked_processes(names: list[str]) -> list[str]:
    """API와 저장 설정에 같은 실행 파일 이름 검사를 적용하고 정규형을 반환한다."""
    normalized = set()
    for name in names:
        name = name.strip().lower()
        if (not name.endswith(".exe") or not name[:-4].strip() or len(name) > 255
                or any(c in '<>:"/\\|?*' or ord(c) < 32 for c in name)):
            raise ValueError("실행 파일 이름을 입력해 주세요.")
        normalized.add(name)
    if len(normalized) > MAX_BLOCKED_PROCESSES:
        raise ValueError("차단 프로그램 개수를 초과했습니다.")
    return sorted(normalized)


class StoredPrivacySettings(BaseModel):
    """필수 세 필드를 엄격하게 읽어 손상된 저장 값을 기본 수집 허용으로 바꾸지 않는다."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    paused: bool
    blocked_processes: list[str]
    clipboard_enabled: bool

    @field_validator("blocked_processes")
    @classmethod
    def normalize(cls, names: list[str]) -> list[str]:
        """차단 목록의 API 정규형을 저장과 복원에도 유지한다."""
        return normalize_blocked_processes(names)
