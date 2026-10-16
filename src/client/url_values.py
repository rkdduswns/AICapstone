"""URL 입력과 서버 데이터의 형태만 검증한다. 실제 차단 여부는 Backend가 판단한다."""

import re
from dataclasses import asdict
from ipaddress import IPv6Address
from urllib.parse import urlsplit, urlunsplit

from shared.browser import MAX_BLOCKED_URLS, MAX_URL_LENGTH, BrowserPage, UrlBlockRule


def _domain(value: str) -> str:
    """한글 도메인을 IDNA로 통일하고 주소·포트·와일드카드가 섞인 입력을 거부한다."""
    try:
        domain = value.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise ValueError("올바른 도메인을 입력해 주세요. 예: example.com") from error
    if len(domain) > 253 or not all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in domain.split(".")
    ):
        raise ValueError("도메인만 입력해 주세요. 주소·포트·*는 포함하지 않습니다.")
    return domain


def _http_url(value: str) -> str:
    """HTTP(S) URL을 검사하고 스킴·호스트·기본 포트만 정규화한다.

    urlsplit은 검증기가 아니며 탭/개행을 지울 수 있어 원문을 먼저 검사한다.
    경로·쿼리·fragment의 대소문자와 percent encoding은 의미가 달라질 수 있으므로
    유지한다. 인증 정보가 있는 주소는 설정/화면으로 전달하지 않는다.
    """
    if (not value or len(value) > MAX_URL_LENGTH
            or any(char.isspace() or ord(char) < 32 or ord(char) == 127
                   or char in '\\<>"' for char in value)
            or re.search(r"%(?![0-9a-fA-F]{2})", value)):
        raise ValueError("공백·제어 문자 없는 올바른 URL을 입력해 주세요.")
    try:
        parts = urlsplit(value)
        host, port = parts.hostname, parts.port
        if (parts.scheme not in ("http", "https") or not host or parts.username is not None
                or parts.password is not None or port == 0 or parts.netloc.endswith(":")):
            raise ValueError("Invalid URL authority")
        # urlsplit은 IPv6 닫는 괄호 뒤의 임의 문자열을 hostname에서 버릴 수 있다.
        # 검사 없이 정규화하면 사용자가 입력한 주소가 다른 주소로 바뀌므로 거부한다.
        if parts.netloc.startswith("[") and not re.fullmatch(r"\[[^\]]+\](?::[0-9]+)?", parts.netloc):
            raise ValueError("Invalid bracketed authority")
        host = f"[{IPv6Address(host).compressed}]" if ":" in host else _domain(host)
    except ValueError as error:
        raise ValueError("인증 정보 없는 http:// 또는 https:// 주소를 입력해 주세요.") from error
    if port is not None and port != (80 if parts.scheme == "http" else 443):
        host += f":{port}"
    return urlunsplit((parts.scheme, host, parts.path or "/", parts.query, parts.fragment))


def normalize_rule(kind: str, value: str) -> UrlBlockRule:
    """한 규칙의 입력을 통일한다. prefix는 쿼리/fragment 없이 URL 시작 부분을 지정한다."""
    if kind not in ("domain", "exact", "prefix") or not isinstance(value, str):
        raise ValueError("차단 방식과 주소를 확인해 주세요.")
    value = value.strip()
    normalized = _domain(value) if kind == "domain" else _http_url(value)
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


def read_browser(value: object) -> BrowserPage | None:
    """선택적 브라우저 출처를 검사하되 화면에서는 서버가 보낸 원본 URL을 유지한다."""
    if value is None:
        return None
    if (not isinstance(value, dict) or value.get("browser") not in ("chrome", "edge")
            or not isinstance(value.get("page_title"), str) or "url" not in value):
        raise ValueError("Invalid browser source")
    url = value["url"]
    if url is not None:
        if not isinstance(url, str):
            raise ValueError("Invalid browser URL")
        _http_url(url)
    return BrowserPage(value["browser"], value["page_title"], url)
