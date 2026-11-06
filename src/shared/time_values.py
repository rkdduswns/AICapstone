"""Client와 Backend가 저장 기록의 시각을 같은 규칙으로 검증한다."""

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
