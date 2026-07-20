"""Tests for core/plan_comparator.py"""

from core.plan_comparator import compare_plans
from core.models import PlanComparison, PlanNode, PlanSource


def _node(node_id: str, operation: str, cost: int, name: str = "") -> PlanNode:
    return {
        "id": node_id,
        "operation": operation,
        "name": name,
        "depth": 0,
        "rows": None,
        "bytes": None,
        "cost": cost,
    }


_B_PLAN: PlanSource = {
    "nodes": [
        _node("1", "SELECT STATEMENT", 10),
        _node("2", "INDEX RANGE SCAN", 5, name="IDX_ORDERS_CUST"),
    ]
}

_C_PLAN_FULL_SCAN: PlanSource = {
    "nodes": [
        _node("1", "SELECT STATEMENT", 500),
        _node("2", "TABLE ACCESS FULL", 490, name="ORDERS"),
    ]
}

_C_PLAN_SAME: PlanSource = {
    "nodes": [
        _node("1", "SELECT STATEMENT", 10),
        _node("2", "INDEX RANGE SCAN", 5, name="IDX_ORDERS_CUST"),
    ]
}


def test_returns_plan_comparison() -> None:
    result = compare_plans(_B_PLAN, _C_PLAN_FULL_SCAN)
    assert isinstance(result, PlanComparison)


def test_full_scan_regression_detected() -> None:
    result = compare_plans(_B_PLAN, _C_PLAN_FULL_SCAN)
    assert len(result.full_scan_regressions) >= 1


def test_cost_delta_computed() -> None:
    result = compare_plans(_B_PLAN, _C_PLAN_FULL_SCAN)
    delta = result.stats.get("cost_delta_pct")
    assert delta is not None
    assert delta > 0


def test_identical_plans_no_regressions() -> None:
    result = compare_plans(_B_PLAN, _C_PLAN_SAME)
    assert len(result.full_scan_regressions) == 0
    assert not result.plan_shape_changed


def test_empty_plans() -> None:
    result = compare_plans({"nodes": []}, {"nodes": []})
    assert isinstance(result, PlanComparison)
    assert result.stats == {} or result.stats.get("baseline_total_cost", 0) == 0
