"""Execution Plan Comparison Engine — pure Python, no PyQt6 imports."""

from core.models import (
    FullScanRegression,
    IndexChange,
    JoinMethodChange,
    OperationChange,
    PlanComparison,
    PlanCompStats,
    PlanNode,
    PlanSource,
    SortChange,
)


def compare_plans(
    baseline_plan: PlanSource, current_plan: PlanSource
) -> PlanComparison:
    """Compare two parsed execution plans and return structured comparison data."""
    b_nodes = baseline_plan.get("nodes", [])
    c_nodes = current_plan.get("nodes", [])

    baseline_cost = _total_cost(b_nodes)
    current_cost = _total_cost(c_nodes)

    if baseline_cost and current_cost:
        delta_pct = ((current_cost - baseline_cost) / baseline_cost) * 100
    else:
        delta_pct = None

    plan_shape_changed = _plan_shape_changed(b_nodes, c_nodes)
    operation_changes = _find_operation_changes(b_nodes, c_nodes)
    index_changes = _find_index_changes(b_nodes, c_nodes)
    full_scan_regressions = _find_full_scan_regressions(b_nodes, c_nodes)
    join_method_changes = _find_join_changes(b_nodes, c_nodes)
    new_sort_operations = _find_new_sorts(b_nodes, c_nodes)

    stats: PlanCompStats
    if baseline_cost is None and current_cost is None:
        stats = {}
    else:
        stats = {
            "baseline_total_cost": baseline_cost,
            "current_total_cost": current_cost,
            "cost_delta_pct": delta_pct,
        }

    return PlanComparison(
        baseline_nodes=b_nodes,
        current_nodes=c_nodes,
        index_changes=index_changes,
        full_scan_regressions=full_scan_regressions,
        join_method_changes=join_method_changes,
        plan_shape_changed=plan_shape_changed,
        stats=stats,
        operation_changes=operation_changes,
        new_sort_operations=new_sort_operations,
    )


def _node_name(node: PlanNode) -> str:
    """Return the node's object/table name, checking both 'name' and 'object_name' keys."""
    return node.get("name") or node.get("object_name") or ""


def _total_cost(nodes: list[PlanNode]) -> int | None:
    """Get total cost from root node (first node is SELECT STATEMENT)."""
    if not nodes:
        return None
    for n in nodes:
        if n.get("cost") is not None:
            return n["cost"]
    return None


def _plan_shape_changed(baseline: list[PlanNode], current: list[PlanNode]) -> bool:
    """Determine if the overall plan shape changed significantly."""
    if not baseline or not current:
        return False

    b_ops = [n.get("operation", "") for n in baseline]
    c_ops = [n.get("operation", "") for n in current]

    if len(b_ops) != len(c_ops):
        return True

    mismatches = sum(1 for a, b in zip(b_ops, c_ops) if a != b)
    return mismatches > max(1, len(b_ops) * 0.2)  # >20% different


def _find_operation_changes(
    baseline: list[PlanNode], current: list[PlanNode]
) -> list[OperationChange]:
    """Find operations that changed between plans."""
    changes: list[OperationChange] = []
    b_by_id = {n.get("id"): n for n in baseline}
    c_by_id = {n.get("id"): n for n in current}

    for node_id in set(b_by_id) | set(c_by_id):
        b_node = b_by_id.get(node_id)
        c_node = c_by_id.get(node_id)

        if b_node and c_node:
            if b_node.get("operation") != c_node.get("operation"):
                changes.append(
                    {
                        "id": node_id,
                        "baseline_op": b_node.get("operation"),
                        "current_op": c_node.get("operation"),
                        "baseline_cost": b_node.get("cost"),
                        "current_cost": c_node.get("cost"),
                    }
                )
        elif b_node and not c_node:
            changes.append(
                {
                    "id": node_id,
                    "baseline_op": b_node.get("operation"),
                    "current_op": None,
                    "type": "removed",
                }
            )
        elif c_node and not b_node:
            changes.append(
                {
                    "id": node_id,
                    "baseline_op": None,
                    "current_op": c_node.get("operation"),
                    "type": "added",
                }
            )

    return changes


def _find_index_changes(
    baseline: list[PlanNode], current: list[PlanNode]
) -> list[IndexChange]:
    """Detect indexes that appeared or disappeared in the plan."""
    changes: list[IndexChange] = []

    def index_ops(nodes: list[PlanNode]) -> dict[str, str]:
        return {
            _node_name(n): n.get("operation", "")
            for n in nodes
            if "INDEX" in n.get("operation", "").upper() and _node_name(n)
        }

    b_indexes = index_ops(baseline)
    c_indexes = index_ops(current)

    for idx_name in set(b_indexes) | set(c_indexes):
        b_op = b_indexes.get(idx_name)
        c_op = c_indexes.get(idx_name)

        if b_op and not c_op:
            changes.append(
                {
                    "index": idx_name,
                    "change": "REMOVED",
                    "baseline_op": b_op,
                    "detail": f"Index {idx_name} used in baseline ({b_op}) but NOT in current plan",
                }
            )
        elif c_op and not b_op:
            changes.append(
                {
                    "index": idx_name,
                    "change": "ADDED",
                    "current_op": c_op,
                    "detail": f"Index {idx_name} added in current plan ({c_op})",
                }
            )
        elif b_op and c_op and b_op != c_op:
            changes.append(
                {
                    "index": idx_name,
                    "change": "OPERATION_CHANGED",
                    "baseline_op": b_op,
                    "current_op": c_op,
                    "detail": f"Index {idx_name}: {b_op} → {c_op}",
                }
            )

    return changes


def _find_full_scan_regressions(
    baseline: list[PlanNode], current: list[PlanNode]
) -> list[FullScanRegression]:
    """Find tables that regressed from index access to full table scan.

    Detects two cases:
    1. A table that had a non-FULL TABLE ACCESS in baseline now has TABLE ACCESS FULL.
    2. A table that only appears as TABLE ACCESS FULL in current while baseline
       used an index operation (i.e. no TABLE ACCESS entry at all for that table).
    """
    regressions: list[FullScanRegression] = []

    def table_access(nodes: list[PlanNode]) -> dict[str, str]:
        result: dict[str, str] = {}
        for n in nodes:
            op = n.get("operation", "")
            name = _node_name(n)
            if name and "TABLE ACCESS" in op:
                result[name] = op
        return result

    def index_objects(nodes: list[PlanNode]) -> set[str]:
        return {
            _node_name(n)
            for n in nodes
            if "INDEX" in n.get("operation", "").upper() and _node_name(n)
        }

    b_access = table_access(baseline)
    c_access = table_access(current)
    b_index_names = index_objects(baseline)

    for table, c_op in c_access.items():
        if "FULL" not in c_op:
            continue
        b_op = b_access.get(table)
        if b_op and "FULL" not in b_op:
            # Was a non-full table access, now full
            regressions.append(
                {
                    "table": table,
                    "baseline_access": b_op,
                    "current_access": c_op,
                    "detail": f"Table {table}: regressed from {b_op} to {c_op}",
                }
            )
        elif not b_op and b_index_names:
            # New full scan where baseline had index access (no TABLE ACCESS entry at all)
            regressions.append(
                {
                    "table": table,
                    "baseline_access": "INDEX ACCESS",
                    "current_access": c_op,
                    "detail": f"Table {table}: new full scan (baseline used index access)",
                }
            )

    return regressions


def _find_join_changes(
    baseline: list[PlanNode], current: list[PlanNode]
) -> list[JoinMethodChange]:
    """Detect join method changes."""
    changes: list[JoinMethodChange] = []
    JOIN_OPS = {"HASH JOIN", "NESTED LOOPS", "MERGE JOIN", "NESTED LOOPS OUTER"}

    def join_ops(nodes: list[PlanNode]) -> list[str]:
        return [
            n.get("operation", "") for n in nodes if n.get("operation", "") in JOIN_OPS
        ]

    b_joins = join_ops(baseline)
    c_joins = join_ops(current)

    for i, (b, c) in enumerate(zip(b_joins, c_joins)):
        if b != c:
            changes.append(
                {
                    "position": i + 1,
                    "baseline_join": b,
                    "current_join": c,
                    "detail": f"Join #{i + 1}: {b} → {c}",
                }
            )

    return changes


def _find_new_sorts(
    baseline: list[PlanNode], current: list[PlanNode]
) -> list[SortChange]:
    """Find sort operations that appeared in current but not baseline."""
    new_sorts: list[SortChange] = []
    b_sorts = sum(1 for n in baseline if "SORT" in n.get("operation", "").upper())
    c_sorts = sum(1 for n in current if "SORT" in n.get("operation", "").upper())

    if c_sorts > b_sorts:
        new_sorts.append(
            {
                "baseline_sort_count": b_sorts,
                "current_sort_count": c_sorts,
                "detail": f"Sort operations increased from {b_sorts} to {c_sorts}",
            }
        )

    return new_sorts
