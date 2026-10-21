
"""Privacy controls for activity collection."""

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

SENSITIVE_PATTERNS = (
    re.compile(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?i)\b(access_token|refresh_token|token|api_key|password|secret)"
        r"\s*[=:]\s*[^&\s]+"
    ),
)


@dataclass
class PrivacyPolicy:
    """Control whether applications and window titles may be collected."""

    collection_paused: bool = False
    blocked_applications: set[str] = field(default_factory=set)
    redact_sensitive_titles: bool = True

    def is_blocked(self, application: str, process_name: str) -> bool:
        """Check blocked applications without case sensitivity."""
        blocked = {name.casefold() for name in self.blocked_applications}
        return (
            application.casefold() in blocked
            or process_name.casefold() in blocked
        )

    def sanitize_title(self, title: str) -> str:
        """Redact common sensitive values from a window title."""
        if not self.redact_sensitive_titles:
            return title

        result = title
        for pattern in SENSITIVE_PATTERNS:
            result = pattern.sub("[REDACTED]", result)
        return result

    def sanitize_browser_url(self, url: str) -> str:
        """Remove URL components that may expose private browsing information."""
        if not url or len(url) > 4096:
            raise ValueError("URL is empty or too long")

        try:
            parsed = urlsplit(url.strip())
            if parsed.scheme.lower() not in {"http", "https"}:
                raise ValueError("Only HTTP and HTTPS URLs are allowed")

            hostname = parsed.hostname
            if not hostname:
                raise ValueError("URL must include a hostname")

            port = parsed.port
        except ValueError as exc:
            raise ValueError("Invalid browser URL") from exc

        # Exclude URL credentials, query parameters, and fragments.
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"

        netloc = hostname
        if port is not None:
            netloc = f"{netloc}:{port}"

        sanitized = urlunsplit(
            (
                parsed.scheme.lower(),
                netloc,
                parsed.path,
                "",
                "",
            )
        )

        if self.contains_sensitive_data(sanitized):
            raise ValueError("URL contains potentially sensitive information")

        return sanitized
    
    def contains_sensitive_data(self, text: str) -> bool:
        """Check text for known sensitive-data patterns."""
        return any(pattern.search(text) for pattern in SENSITIVE_PATTERNS)