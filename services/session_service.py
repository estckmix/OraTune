"""Session service — thin wrapper over storage/session_repo for use by UI and analysis service."""

import structlog

from core.models import AnalysisSession
from storage import session_repo

log = structlog.get_logger()


def save(session: AnalysisSession) -> None:
    """Save session to SQLite. Logs to stderr on failure — never raises."""
    try:
        session_repo.save(session)
    except Exception as exc:
        log.error("session.save_failed", error=str(exc))


def load(session_id: str) -> AnalysisSession | None:
    """Load a full session by id. Returns None if not found or on error."""
    try:
        return session_repo.load(session_id)
    except Exception as exc:
        log.error("session.load_failed", session_id=session_id, error=str(exc))
        return None


def list_sessions() -> list[dict[str, str]]:
    """Return lightweight session rows for sidebar. Returns [] on error."""
    try:
        return session_repo.list_sessions()
    except Exception as exc:
        log.error("session.list_failed", error=str(exc))
        return []


def delete(session_id: str) -> None:
    """Delete a session. Logs to stderr on failure — never raises."""
    try:
        session_repo.delete(session_id)
    except Exception as exc:
        log.error("session.delete_failed", session_id=session_id, error=str(exc))
