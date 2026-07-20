"""CRUD operations for AnalysisSession persistence."""

import dataclasses
import json
from typing import Any
from datetime import datetime

from core.models import AnalysisSession, Finding, DiffResult, PlanComparison
from storage.database import get_connection


# ── Public API ────────────────────────────────────────────────────────────────


def save(session: AnalysisSession) -> None:
    summary = _build_summary(session.findings)
    conn = get_connection()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO sessions
               (id, timestamp, summary, baseline_files, current_files, results_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                session.id,
                session.timestamp.isoformat(),
                summary,
                json.dumps(session.baseline_files),
                json.dumps(session.current_files),
                json.dumps(_to_dict(session)),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_sessions() -> list[dict[str, str]]:
    """Return lightweight session rows for sidebar display (no results_json)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, timestamp, summary, baseline_files "
            "FROM sessions ORDER BY timestamp DESC LIMIT 100"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def load(session_id: str) -> AnalysisSession | None:
    """Deserialise a full AnalysisSession by id. Returns None if not found."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT results_json FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return _from_dict(json.loads(row["results_json"]))


def delete(session_id: str) -> None:
    conn = get_connection()
    try:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()


# ── Serialisation helpers ─────────────────────────────────────────────────────


def _build_summary(findings: list[Finding]) -> str:
    counts: dict[str, int] = {}
    for f in findings:
        sev = f.severity if isinstance(f, Finding) else f.get("severity", "INFO")
        counts[sev] = counts.get(sev, 0) + 1
    total = sum(counts.values())
    parts = [
        f"{counts[s]} {s}"
        for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
        if counts.get(s)
    ]
    if not parts:
        return "No findings"
    return f"{total} finding{'s' if total != 1 else ''} — {' · '.join(parts)}"


def _to_dict(obj: object) -> object:
    """Recursively convert dataclasses and datetimes to JSON-serialisable types."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


def _from_dict(d: dict[str, Any]) -> AnalysisSession:
    findings = [Finding(**f) for f in d.get("findings", [])]
    diff_results = []
    for dr in d.get("diff_results", []):
        # JSON turns the int line-number keys into strings; convert back so
        # diff highlighting works on sessions loaded from the database.
        for key in ("baseline_diff_lines", "current_diff_lines"):
            dr[key] = {int(line): tag for line, tag in dr.get(key, {}).items()}
        diff_results.append(DiffResult(**dr))
    pc = d.get("plan_comparison")
    plan_comparison = PlanComparison(**pc) if pc else None
    return AnalysisSession(
        id=d["id"],
        timestamp=datetime.fromisoformat(d["timestamp"]),
        baseline_files=d.get("baseline_files", []),
        current_files=d.get("current_files", []),
        findings=findings,
        diff_results=diff_results,
        plan_comparison=plan_comparison,
        awr_data=d.get("awr_data", {}),
        dmp_context=d.get("dmp_context", {}),
        recommendations=d.get("recommendations", {}),
    )
