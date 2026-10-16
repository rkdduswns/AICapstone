
"""Shared data contracts for current activity tracking."""

from dataclasses import dataclass
from typing import Literal

from shared.protocol import API_VERSION, SERVICE_NAME

ACTIVITY_PATH = "/activity/current"
ACTIVITY_HISTORY_PATH = "/activity/history"
BROWSER_SOURCE_PATH = "/browser/source"
BROWSER_CONTENT_PATH = "/browser/content"

CollectionStatus = Literal[
    "collecting",
    "no_active_window",
    "unsupported",
    "error",
    "paused",
    "blocked",
]


@dataclass(frozen=True)
class ActiveWindow:
    """Information about the currently active application window."""

    application: str
    process_name: str
    process_id: int
    window_title: str


@dataclass(frozen=True)
class ActivityTiming:
    """Accumulated active time for the current activity."""

    started_at: str
    active_duration_ms: int


@dataclass(frozen=True)
class CurrentActivity:
    """Current activity state returned by the backend."""

    collection_status: CollectionStatus
    window: ActiveWindow | None
    service: str = SERVICE_NAME
    api_version: int = API_VERSION
    timing: ActivityTiming | None = None


@dataclass(frozen=True)
class CurrentActivityResponse:
    """Standard success envelope for the current activity endpoint."""

    data: CurrentActivity
    ok: Literal[True] = True
    error: None = None


@dataclass(frozen=True)
class ActivityRecord:
    """One persisted activity session."""

    id: int
    application: str
    process_name: str
    process_id: int
    window_title: str
    started_at: str
    ended_at: str
    active_duration_ms: int


@dataclass(frozen=True)
class ClipboardRecord:
    """A sanitized clipboard snapshot associated with an activity."""

    id: int
    application: str
    activity_started_at: str
    captured_at: str
    content: str

@dataclass(frozen=True)
class BrowserSourceRecord:
    """A browser page source associated with its active tab."""

    id: int
    browser: str
    url: str
    page_title: str
    captured_at: str

@dataclass(frozen=True)
class BrowserContentRecord:
    """Text content associated with a captured browser page."""

    id: int
    browser_source_id: int
    content_text: str
    captured_at: str

@dataclass(frozen=True)
class DocumentRecord:
    """Persisted metadata and extracted text for a local document."""

    id: int
    file_path: str
    file_name: str
    file_type: str
    extracted_text: str
    captured_at: str