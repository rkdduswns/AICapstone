"""URL 차단 판정이 아닌 입력 계약을 검사한다. 주소는 모두 가상 값이다."""

from dataclasses import asdict

import pytest

from client.url_values import normalize_rule, normalize_rules, read_url_rules
from shared.browser import UrlBlockRule


def test_url_normalization_preserves_path_query_and_fragment():
    """호스트 표기 차이만 통일하고 페이지를 구분하는 원문 부분은 유지한다."""
    rule = normalize_rule("exact", " HTTPS://EXAMPLE.COM:443/Path?q=Ab%20C#Top ")
    assert rule.value == "https://example.com/Path?q=Ab%20C#Top"
    assert normalize_rule("prefix", "http://example.com:80").value == "http://example.com/"
    assert normalize_rule("exact", "https://[::1]:8765/").value == "https://[::1]:8765/"
    assert normalize_rule("domain", " 예시.한국 ").value == "xn--vv4b11d.xn--3e0b707e"


@pytest.mark.parametrize("kind,value", [
    ("regex", ".*"), ("domain", "https://example.com"), ("domain", "*.example.com"),
    ("domain", "example.com:80"), ("domain", "bad..example.com"), ("domain", "-bad.com"),
    ("exact", "javascript:alert(1)"), ("exact", "file:///private"),
    ("exact", "https://user:password@example.com/"), ("exact", "https://example.com:65536/"),
    ("exact", "https://example.com:0/"), ("exact", "https://example.com:/"),
    ("exact", "https://exam\nple.com/"), ("exact", "https://example.com/with space"),
    ("exact", "https://example.com\\private"), ("exact", "https://example.com/%xx"),
    ("exact", "https://[bad/"), ("exact", "https://example.com/" + "a" * 8192),
    ("exact", "https://[::1]unexpected/path"),
    ("prefix", "https://example.com/?q=private"), ("prefix", "https://example.com/#private"),
])
def test_ambiguous_or_unsupported_rule_rejected(kind, value):
    """암묵적인 입력 수정으로 차단 범위가 달라지는 주소와 미지원 방식을 거부한다."""
    with pytest.raises(ValueError):
        normalize_rule(kind, value)


def test_rule_list_canonicalization_and_limit():
    """중복 입력은 하나로 합치고 서버 응답의 비정규 목록은 오류로 처리한다."""
    rule = UrlBlockRule("domain", "example.com")
    assert normalize_rules([rule, UrlBlockRule("domain", "EXAMPLE.COM")]) == [rule]
    assert read_url_rules([asdict(rule)]) == [rule]
    assert read_url_rules(None) is None and read_url_rules([]) == []
    for value in ([asdict(rule)] * 2, [{"kind": "domain", "value": "EXAMPLE.COM"}],
                  [{"kind": "domain"}], [1], {}, [{"kind": [], "value": "a"}]):
        with pytest.raises(ValueError):
            read_url_rules(value)
    with pytest.raises(ValueError):
        normalize_rules([UrlBlockRule("domain", f"site{i}.example.com") for i in range(101)])
