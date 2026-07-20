"""Report service — wraps core/reporter for UI use."""

import structlog

from core.models import AnalysisSession
from core import reporter

log = structlog.get_logger()


def export_html(session: AnalysisSession, output_path: str) -> bool:
    """
    Generate an HTML report for the session at output_path.
    Returns True on success, False on error (error logged to stderr).
    """
    try:
        reporter.generate_html_report(session, output_path)
        return True
    except Exception as exc:
        log.error("report.export_failed", output_path=output_path, error=str(exc))
        return False
