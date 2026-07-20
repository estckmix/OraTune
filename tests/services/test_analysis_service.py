"""Tests for the analysis pipeline and its extracted comparison helpers."""

from pathlib import Path

import pytest

from core.models import (
    DiffResult,
    Finding,
    IndexStat,
    ParsedDmp,
    PlanComparison,
    PlanNode,
    TableStat,
)
from services.analysis_service import (
    AnalysisWorker,
    _single_sided_plan,
    _sqlt_cf_changes,
    _sqlt_param_changes,
    _sqlt_table_stat_changes,
)


def test_single_sided_plan_is_empty_comparison() -> None:
    node: PlanNode = {
        "id": "0",
        "operation": "TABLE ACCESS FULL",
        "name": "EMP",
        "depth": 0,
        "rows": 10,
        "bytes": 100,
        "cost": 5,
    }
    pc = _single_sided_plan([node], [])
    assert isinstance(pc, PlanComparison)
    assert pc.baseline_nodes == [node]
    assert pc.current_nodes == []
    assert pc.plan_shape_changed is False
    assert pc.index_changes == []


def _sqlt(
    params: dict[str, str] | None = None,
    tables: list[TableStat] | None = None,
    indexes: list[IndexStat] | None = None,
) -> ParsedDmp:
    return {
        "filepath": "x.dmp",
        "dmp_type": "sqlt",
        "optimizer_params": params or {},
        "table_stats": tables or [],
        "index_stats": indexes or [],
    }


def test_sqlt_param_changes_reports_only_diffs() -> None:
    b = _sqlt(params={"optimizer_mode": "ALL_ROWS", "cursor_sharing": "EXACT"})
    c = _sqlt(params={"optimizer_mode": "FIRST_ROWS", "cursor_sharing": "EXACT"})
    changes = _sqlt_param_changes(b, c)
    assert changes == {
        "optimizer_mode": {"baseline": "ALL_ROWS", "current": "FIRST_ROWS"}
    }


def test_sqlt_table_stat_changes_over_20_percent_only() -> None:
    b = _sqlt(
        tables=[
            {"table": "EMP", "num_rows": 100, "blocks": 1, "last_analyzed": "x"},
            {"table": "DEPT", "num_rows": 100, "blocks": 1, "last_analyzed": "x"},
        ]
    )
    c = _sqlt(
        tables=[
            {"table": "EMP", "num_rows": 200, "blocks": 1, "last_analyzed": "x"},
            {"table": "DEPT", "num_rows": 110, "blocks": 1, "last_analyzed": "x"},
        ]
    )
    changes = _sqlt_table_stat_changes(b, c)
    assert len(changes) == 1
    assert changes[0]["table"] == "EMP"
    assert changes[0]["change_pct"] == 100.0


def test_sqlt_cf_changes_ignores_missing_values() -> None:
    b = _sqlt(indexes=[{"index": "IX1", "blevel": 1, "clustering_factor": 0}])
    c = _sqlt(indexes=[{"index": "IX1", "blevel": 1, "clustering_factor": 900}])
    assert _sqlt_cf_changes(b, c) == []  # zero baseline CF is skipped, not a crash


def test_run_analysis_offline_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Full file-mode pipeline with SQL diffs and offline recommendations.

    Regression test for the AttributeError crash in _build_context when
    DiffResult/PlanComparison dataclasses were accessed like dicts.
    """
    baseline = tmp_path / "job.sql"
    current = tmp_path / "job2.sql"
    baseline.write_text("SELECT /*+ INDEX(e emp_ix) */ * FROM emp e WHERE e.sal > 100;")
    current.write_text("SELECT * FROM emp e WHERE e.sal > 100 ORDER BY e.sal;")

    # keep the test off the real vault, env keys, settings file, and DB
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("services.ai_service.get_secret", lambda name: "")
    monkeypatch.setattr("services.ai_service.SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr("storage.database._DB_PATH", tmp_path / "sessions.db")

    worker = AnalysisWorker(
        {"sql": [str(baseline)]},
        {"sql": [str(current)]},
    )
    session = worker.run_analysis()

    assert len(session.diff_results) == 1
    assert isinstance(session.diff_results[0], DiffResult)
    assert session.plan_comparison is None
    # hint was removed -> findings engine must flag it
    assert any("Hint" in f.title for f in session.findings)
    assert all(isinstance(f, Finding) for f in session.findings)
    # offline recommendations generated without crashing on dataclasses
    assert session.recommendations["mode"] == "offline"
    assert "OraTune Analysis Report" in session.recommendations["content"]
