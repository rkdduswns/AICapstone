"""Phase 14 work-session and record-management API contracts."""

# A session continues when the inactivity gap is at most 30 minutes.
SESSION_GAP_SECONDS = 30 * 60

SESSIONS_PATH = "/sessions"
SESSION_DETAIL_PATH = "/sessions/{session_id}"
SESSION_MATERIALS_PATH = "/sessions/{session_id}/materials"
ACTIVITY_RECORD_DELETE_PATH = "/records/{record_id}"
ALL_RECORDS_DELETE_PATH = "/records"
DOCUMENT_RECORD_DELETE_PATH = "/documents/{document_id}"
BROWSER_SOURCE_DELETE_PATH = "/browser/source/{browser_source_id}"
BROWSER_CONTENT_DELETE_PATH = "/browser/content/{content_id}"
