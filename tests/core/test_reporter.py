"""Tests for the HTML report generator."""

from datetime import datetime
from pathlib import Path

from core.models import AnalysisSession, Finding
from core.reporter import _findings_html, generate_html_report


def _finding() -> Finding:
    return Finding(
        severity="HIGH",
        category="INDEX",
        title="Index No Longer Used: EMP_IX",
        description="The index vanished from the plan <script>",
        detail="detail text",
    )


def test_findings_html_renders_and_escapes() -> None:
    html_out = _findings_html([_finding()])
    assert "Index No Longer Used: EMP_IX" in html_out
    assert "&lt;script&gt;" in html_out  # description is escaped
    assert "#ff7b72" in html_out  # HIGH severity color


def test_findings_html_empty_is_empty_string() -> None:
    assert _findings_html([]) == ""


def test_generate_html_report_writes_full_page(tmp_path: Path) -> None:
    session = AnalysisSession(
        baseline_files=["a.sql"],
        current_files=["b.sql"],
        findings=[_finding()],
        diff_results=[],
        plan_comparison=None,
        awr_data={},
        dmp_context={},
        recommendations={"mode": "offline", "content": "Do the thing"},
        timestamp=datetime(2026, 7, 14, 12, 0, 0),
    )
    out = tmp_path / "report.html"
    generate_html_report(session, str(out))
    text = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in text
    assert "Index No Longer Used: EMP_IX" in text
    assert "Do the thing" in text
    assert "No findings detected" not in text
