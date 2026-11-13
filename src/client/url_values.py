"""URL 입력과 서버 데이터의 형태만 검증한다. 실제 차단 여부는 Backend가 판단한다."""

from dataclasses import asdict

from shared.browser import MAX_BLOCKED_URLS, UrlBlockRule
from shared.browser_values import normalize_domain, normalize_http_url
from shared.browser_values import read_browser as read_browser


def normalize_rule(kind: str, value: str) -> UrlBlockRule:
    """한 규칙의 입력을 통일한다. prefix는 쿼리/fragment 없이 URL 시작 부분을 지정한다."""
    if kind not in ("domain", "exact", "prefix") or not isinstance(value, str):
        raise ValueError("차단 방식과 주소를 확인해 주세요.")
    value = value.strip()
    normalized = normalize_domain(value) if kind == "domain" else normalize_http_url(value)
    if kind == "prefix" and ("?" in normalized or "#" in normalized):
        raise ValueError("URL 시작 부분에는 ? 뒤의 쿼리나 # 뒤의 위치를 넣지 않습니다.")
    return UrlBlockRule(kind, normalized)


def normalize_rules(rules: list[UrlBlockRule]) -> list[UrlBlockRule]:
    """중복 제거와 정렬로 비교 가능한 목록을 만들며 최대 개수를 제한한다."""
    normalized = {normalize_rule(rule.kind, rule.value) for rule in rules}
    if len(normalized) > MAX_BLOCKED_URLS:
        raise ValueError(f"URL 차단 규칙은 최대 {MAX_BLOCKED_URLS}개입니다.")
    return sorted(normalized, key=lambda rule: (rule.kind, rule.value))


def read_url_rules(value: object) -> list[UrlBlockRule] | None:
    """구형 서버의 생략/null은 미지원이다. 지원 응답은 정규화된 목록이어야 한다."""
    if value is None:
        return None
    if not isinstance(value, list) or len(value) > MAX_BLOCKED_URLS:
        raise ValueError("Invalid URL rules")
    rules = []
    for row in value:
        if not isinstance(row, dict) or set(row) != {"kind", "value"}:
            raise ValueError("Invalid URL rule")
        rules.append(normalize_rule(row["kind"], row["value"]))
    rules = normalize_rules(rules)
    if [asdict(rule) for rule in rules] != value:
        raise ValueError("Noncanonical URL rules")
    return rules
