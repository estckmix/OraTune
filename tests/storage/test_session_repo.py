"""Round-trip tests for AnalysisSession (de)serialization."""

import json
from datetime import datetime

from core.models import AnalysisSession, DiffResult, Finding
from storage.session_repo import _from_dict, _to_dict


def _session() -> AnalysisSession:
    return AnalysisSession(
        baseline_files=["a.sql"],
        current_files=["b.sql"],
        findings=[
            Finding(
                severity="HIGH",
                category="Execution Plan",
                title="t",
                description="d",
                detail="x",
            )
        ],
        diff_results=[
            DiffResult(
                label="a.sql  vs  b.sql",
                baseline_text="select 1",
                current_text="select 2",
                baseline_diff_lines={1: "change"},
                current_diff_lines={1: "change", 3: "add"},
                structural_changes=[{"type": "HINT_ADDED", "detail": "FULL(t)"}],
                stats={
                    "lines_added": 1,
                    "lines_removed": 0,
                    "lines_changed": 1,
                    "baseline_total_lines": 1,
                    "current_total_lines": 1,
                    "similarity_ratio": 50.0,
                },
            )
        ],
        plan_comparison=None,
        awr_data={},
        dmp_context={},
        recommendations={"mode": "offline"},
        timestamp=datetime(2026, 7, 13, 12, 0, 0),
    )


def test_json_roundtrip_restores_int_diff_line_keys() -> None:
    # Simulate the exact save path: dataclass -> dict -> JSON -> dict -> dataclass
    stored = json.loads(json.dumps(_to_dict(_session())))
    loaded = _from_dict(stored)

    diff = loaded.diff_results[0]
    assert diff.baseline_diff_lines == {1: "change"}
    assert diff.current_diff_lines == {1: "change", 3: "add"}
    assert all(isinstance(k, int) for k in diff.current_diff_lines)


def test_roundtrip_preserves_findings_and_metadata() -> None:
    original = _session()
    loaded = _from_dict(json.loads(json.dumps(_to_dict(original))))

    assert loaded.id == original.id
    assert loaded.timestamp == original.timestamp
    assert loaded.findings[0].severity == "HIGH"
    assert loaded.findings[0].title == "t"
    assert loaded.diff_results[0].label == "a.sql  vs  b.sql"
    assert loaded.plan_comparison is None
