"""현재 작업과 저장 기록에서 동일하게 사용하는 시각 검증 및 표시."""

from shared.time_values import parse_timestamp as parse_timestamp


def format_timestamp(value: str) -> str:
    """PC 현지 시각과 UTC 오프셋을 함께 표시한다."""
    return parse_timestamp(value).astimezone().isoformat(sep=" ", timespec="seconds")


def format_duration(milliseconds: int) -> str:
    """서버 누적 밀리초의 초 미만을 버리고 24시간 이후에도 시간을 누적 표시한다."""
    hours, remainder = divmod(milliseconds // 1000, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
