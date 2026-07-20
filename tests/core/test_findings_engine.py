"""Tests for core/findings_engine.py"""

from core.findings_engine import generate_findings
from core.models import (
    DiffResult,
    Finding,
    FullScanRegression,
    IndexChange,
    JoinMethodChange,
    PlanCompStats,
    PlanComparison,
)


def _plan(
    cost_delta: int | None = None,
    full_scans: list[FullScanRegression] | None = None,
    index_changes: list[IndexChange] | None = None,
    join_changes: list[JoinMethodChange] | None = None,
) -> PlanComparison:
    stats: PlanCompStats = {}
    if cost_delta is not None:
        stats = {
            "baseline_total_cost": 100,
            "current_total_cost": 100 + cost_delta,
            "cost_delta_pct": cost_delta,
        }
    return PlanComparison(
        baseline_nodes=[],
        current_nodes=[],
        index_changes=index_changes or [],
        full_scan_regressions=full_scans or [],
        join_method_changes=join_changes or [],
        plan_shape_changed=False,
        stats=stats,
    )


def test_returns_list_of_findings() -> None:
    result = generate_findings([], _plan(), {})
    assert isinstance(result, list)


def test_all_findings_are_finding_instances() -> None:
    plan = _plan(cost_delta=200)
    result = generate_findings([], plan, {})
    assert all(isinstance(f, Finding) for f in result)


def test_high_cost_increase_generates_finding() -> None:
    plan = _plan(cost_delta=200)
    result = generate_findings([], plan, {})
    severities = [f.severity for f in result]
    assert "HIGH" in severities or "CRITICAL" in severities


def test_full_scan_regression_generates_high_finding() -> None:
    plan = _plan(
        full_scans=[
            {
                "table": "ORDERS",
                "baseline_access": "INDEX RANGE SCAN",
                "current_access": "TABLE ACCESS FULL",
                "detail": "INDEX→FULL",
            }
        ]
    )
    result = generate_findings([], plan, {})
    assert any(f.severity == "HIGH" for f in result)


def test_sorted_by_severity() -> None:
    plan = _plan(
        cost_delta=200,
        full_scans=[
            {
                "table": "T",
                "baseline_access": "INDEX RANGE SCAN",
                "current_access": "TABLE ACCESS FULL",
                "detail": "d",
            }
        ],
    )
    result = generate_findings([], plan, {})
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    ranks = [order[f.severity] for f in result]
    assert ranks == sorted(ranks)


def test_empty_inputs_returns_empty() -> None:
    result = generate_findings([], _plan(), {})
    assert result == []


def test_hint_removed_from_diff_generates_finding() -> None:
    diff = DiffResult(
        label="x vs y",
        baseline_text="",
        current_text="",
        baseline_diff_lines={},
        current_diff_lines={},
        structural_changes=[{"type": "HINT_REMOVED", "detail": "INDEX(o IDX_ORDERS)"}],
        stats={
            "lines_added": 0,
            "lines_removed": 0,
            "lines_changed": 0,
            "baseline_total_lines": 0,
            "current_total_lines": 0,
            "similarity_ratio": 0.0,
        },
    )
    result = generate_findings([diff], _plan(), {})
    assert any("Hint" in f.title or "hint" in f.title.lower() for f in result)
