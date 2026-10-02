"""현재 작업과 저장 기록에서 동일하게 사용하는 시각 검증 및 표시."""

import re
from datetime import datetime


def parse_timestamp(value: object) -> datetime:
    """시간대 없는 값을 추측하지 않고 PC 현지 시각으로 표시 가능한 순간만 허용한다."""
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value,
    ):
        raise ValueError("Invalid timestamp")
    offset = value[-6:]
    if not value.endswith("Z") and (int(offset[1:3]) > 23 or int(offset[4:]) > 59):
        raise ValueError("Invalid timezone offset")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        parsed.astimezone()
    except (OverflowError, OSError) as error:
        raise ValueError("Timestamp cannot be displayed locally") from error
    return parsed


def format_timestamp(value: str) -> str:
    """PC 현지 시각과 UTC 오프셋을 함께 표시한다."""
    return parse_timestamp(value).astimezone().isoformat(sep=" ", timespec="seconds")


def format_duration(milliseconds: int) -> str:
    """서버 누적 밀리초의 초 미만을 버리고 24시간 이후에도 시간을 누적 표시한다."""
    hours, remainder = divmod(milliseconds // 1000, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
