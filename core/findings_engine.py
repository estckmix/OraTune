"""Rules-Based Findings Engine — produces typed Finding models from analysis data.

No PyQt6 imports. Pure Python.
"""

from __future__ import annotations

from core.models import (
    AwrComparison,
    DiffResult,
    Finding,
    ParsedDmp,
    PlanComparison,
)


def generate_findings(
    diff_results: list[DiffResult],
    plan_comparison: PlanComparison | None,
    awr_comparison: AwrComparison,
) -> list[Finding]:
    """
    Generate a list of Finding instances from all analysis data.
    Only adds findings when there are actual signals — returns [] when inputs are clean.
    """
    findings: list[Finding] = []

    # ── Plan-based findings ────────────────────────────────────────────────────
    if plan_comparison:
        findings.extend(_check_cost_increase(plan_comparison))
        findings.extend(_check_full_scan_regressions(plan_comparison))
        findings.extend(_check_index_changes(plan_comparison))
        findings.extend(_check_join_changes(plan_comparison))
        findings.extend(_check_sort_increase(plan_comparison))
        findings.extend(_check_plan_shape(plan_comparison))

    # ── SQL diff findings ──────────────────────────────────────────────────────
    for diff in diff_results:
        findings.extend(_check_sql_structural_changes(diff))
        findings.extend(_check_hint_changes(diff))

    # ── AWR/TKPROF findings ────────────────────────────────────────────────────
    if awr_comparison:
        findings.extend(_check_awr_regression(awr_comparison))

    # Sort by severity
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    findings.sort(key=lambda f: order.get(f.severity.upper(), 5))

    return findings


# ─── Plan Checks ──────────────────────────────────────────────────────────────


def _check_cost_increase(plan: PlanComparison) -> list[Finding]:
    findings: list[Finding] = []
    stats = plan.stats
    delta = stats.get("cost_delta_pct")
    b_cost = stats.get("baseline_total_cost")
    c_cost = stats.get("current_total_cost")

    if delta is None:
        return findings

    if delta >= 500:
        sev = "CRITICAL"
    elif delta >= 100:
        sev = "HIGH"
    elif delta >= 50:
        sev = "MEDIUM"
    elif delta >= 20:
        sev = "LOW"
    else:
        return findings

    findings.append(
        Finding(
            severity=sev,
            category="COST",
            title=f"Execution Plan Cost Increased by {delta:.0f}%",
            description=(
                f"The optimizer's estimated cost rose from {b_cost:,} to {c_cost:,}. "
                "This typically indicates stale statistics, a plan regression, or structural SQL changes."
            ),
            detail=f"Baseline cost: {b_cost}  →  Current cost: {c_cost}  ({delta:+.0f}%)",
        )
    )
    return findings


def _check_full_scan_regressions(plan: PlanComparison) -> list[Finding]:
    findings: list[Finding] = []
    for reg in plan.full_scan_regressions:
        findings.append(
            Finding(
                severity="HIGH",
                category="INDEX",
                title=f"Full Table Scan Regression: {reg['table']}",
                description=(
                    f"Table {reg['table']} was accessed via index in the baseline but now uses a full table scan. "
                    "Common causes: stale statistics, index becoming invisible or unusable, "
                    "bind variable peeking issue, or predicate change causing the optimizer to abandon the index."
                ),
                detail=reg["detail"],
            )
        )
    return findings


def _check_index_changes(plan: PlanComparison) -> list[Finding]:
    findings: list[Finding] = []
    for change in plan.index_changes:
        chg_type = change.get("change")
        if chg_type == "REMOVED":
            findings.append(
                Finding(
                    severity="HIGH",
                    category="INDEX",
                    title=f"Index No Longer Used: {change['index']}",
                    description=(
                        f"Index {change['index']} was used in the baseline plan but is absent from the current plan. "
                        "Possible causes: index rebuild changed clustering factor, statistics refresh, "
                        "predicate column data skew, or optimizer parameter change."
                    ),
                    detail=change["detail"],
                )
            )
        elif chg_type == "OPERATION_CHANGED":
            findings.append(
                Finding(
                    severity="MEDIUM",
                    category="INDEX",
                    title=f"Index Access Method Changed: {change['index']}",
                    description=(
                        f"The access method for index {change['index']} changed. "
                        "An INDEX RANGE SCAN to INDEX FULL SCAN regression is common after statistics staleness."
                    ),
                    detail=change["detail"],
                )
            )
    return findings


def _check_join_changes(plan: PlanComparison) -> list[Finding]:
    findings: list[Finding] = []
    for change in plan.join_method_changes:
        b = change.get("baseline_join", "")
        c = change.get("current_join", "")

        # NESTED LOOPS → HASH JOIN can be bad for OLTP
        if "NESTED LOOPS" in b and "HASH JOIN" in c:
            sev = "HIGH"
            desc = (
                "A join method changed from NESTED LOOPS to HASH JOIN. "
                "In OLTP workloads, this often indicates cardinality estimate deterioration. "
                "HASH JOINs require more memory and perform poorly on small result sets."
            )
        elif "HASH JOIN" in b and "NESTED LOOPS" in c:
            sev = "MEDIUM"
            desc = (
                "A join method changed from HASH JOIN to NESTED LOOPS. "
                "This may indicate improved cardinality estimates or could cause issues on larger sets."
            )
        else:
            sev = "MEDIUM"
            desc = f"Join method changed from {b} to {c}."

        findings.append(
            Finding(
                severity=sev,
                category="JOIN",
                title=f"Join Method Changed: {b} → {c}",
                description=desc,
                detail=change["detail"],
            )
        )
    return findings


def _check_sort_increase(plan: PlanComparison) -> list[Finding]:
    findings: list[Finding] = []
    for sort in plan.new_sort_operations:
        findings.append(
            Finding(
                severity="MEDIUM",
                category="SORT",
                title="Additional Sort Operations Detected",
                description=(
                    "The current plan contains more SORT operations than the baseline. "
                    "New sorts can indicate missing indexes, removed ORDER BY indexes, "
                    "or GROUP BY changes requiring additional passes over data."
                ),
                detail=sort["detail"],
            )
        )
    return findings


def _check_plan_shape(plan: PlanComparison) -> list[Finding]:
    if plan.plan_shape_changed:
        return [
            Finding(
                severity="HIGH",
                category="EXECUTION_PLAN",
                title="Execution Plan Shape Has Significantly Changed",
                description=(
                    "The overall structure of the execution plan is substantially different from the baseline. "
                    "A plan shape change is a strong indicator of a statistics-driven regression. "
                    "Run DBMS_STATS.GATHER_TABLE_STATS on involved tables and check for stale object statistics."
                ),
                detail="Plan operation sequence differs significantly from baseline",
            )
        ]
    return []


# ─── SQL Diff Checks ──────────────────────────────────────────────────────────


def _check_sql_structural_changes(diff: DiffResult) -> list[Finding]:
    findings: list[Finding] = []
    stats = diff.stats
    similarity = stats.get("similarity_ratio", 100)

    if similarity < 50:
        findings.append(
            Finding(
                severity="MEDIUM",
                category="SQL_CHANGE",
                title=f"Significant SQL Code Change Detected ({similarity}% similarity)",
                description=(
                    "The SQL code has changed substantially. Verify that intended changes did not "
                    "inadvertently affect selectivity, join order hints, or optimizer directives."
                ),
                detail=(
                    f"Lines added: {stats.get('lines_added', 0)}  "
                    f"Lines removed: {stats.get('lines_removed', 0)}  "
                    f"Lines changed: {stats.get('lines_changed', 0)}"
                ),
            )
        )

    for sc in diff.structural_changes:
        change_type = sc.get("type", "")
        if change_type == "TABLE_ADDED":
            findings.append(
                Finding(
                    severity="MEDIUM",
                    category="SQL_CHANGE",
                    title=f"New Table Added to Query: {sc['detail']}",
                    description="A new table join was introduced. Verify the join has appropriate indexes and statistics.",
                    detail=f"Table: {sc['detail']}",
                )
            )
        elif change_type == "TABLE_REMOVED":
            findings.append(
                Finding(
                    severity="LOW",
                    category="SQL_CHANGE",
                    title=f"Table Removed from Query: {sc['detail']}",
                    description="A table was removed from the query. Verify this was intentional.",
                    detail=f"Table: {sc['detail']}",
                )
            )

    return findings


def _check_hint_changes(diff: DiffResult) -> list[Finding]:
    findings: list[Finding] = []
    for sc in diff.structural_changes:
        change_type = sc.get("type", "")
        if change_type == "HINT_REMOVED":
            findings.append(
                Finding(
                    severity="HIGH",
                    category="SQL_CHANGE",
                    title="Optimizer Hint Removed",
                    description=(
                        "An optimizer hint was present in the baseline but is absent in the current code. "
                        "Hints are often added specifically to work around optimizer issues — "
                        "removing one may cause the optimizer to choose a suboptimal plan."
                    ),
                    detail=f"Removed hint: /*+ {sc['detail']} */",
                )
            )
        elif change_type == "HINT_ADDED":
            findings.append(
                Finding(
                    severity="INFO",
                    category="SQL_CHANGE",
                    title="Optimizer Hint Added",
                    description="A new optimizer hint was added. Verify it produces the intended behavior.",
                    detail=f"Added hint: /*+ {sc['detail']} */",
                )
            )
        elif change_type == "INDEX_HINT_REMOVED":
            findings.append(
                Finding(
                    severity="HIGH",
                    category="INDEX",
                    title=f"Index Hint Removed: {sc['detail']}",
                    description=(
                        "An explicit index hint was removed from the code. "
                        "This may cause the optimizer to choose a different (potentially slower) access path."
                    ),
                    detail=sc["detail"],
                )
            )

    return findings


# ─── AWR Checks ───────────────────────────────────────────────────────────────


def _check_awr_regression(awr: AwrComparison) -> list[Finding]:
    findings: list[Finding] = []

    b_elapsed = awr.get("baseline_elapsed")
    c_elapsed = awr.get("current_elapsed")

    if b_elapsed and c_elapsed:
        try:
            ratio = float(c_elapsed) / float(b_elapsed)
            if ratio >= 3:
                findings.append(
                    Finding(
                        severity="CRITICAL",
                        category="GENERAL",
                        title=f"Execution Time Increased {ratio:.1f}x",
                        description=(
                            f"AWR/TKPROF data shows execution time increased from {b_elapsed}s to {c_elapsed}s. "
                            f"This is a {ratio:.1f}x regression."
                        ),
                        detail=f"Baseline: {b_elapsed}s  →  Current: {c_elapsed}s",
                    )
                )
            elif ratio >= 1.5:
                findings.append(
                    Finding(
                        severity="HIGH",
                        category="GENERAL",
                        title=f"Execution Time Increased {ratio:.1f}x",
                        description=f"Execution time grew from {b_elapsed}s to {c_elapsed}s.",
                        detail=f"Baseline: {b_elapsed}s  →  Current: {c_elapsed}s",
                    )
                )
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    new_waits = awr.get("new_wait_events", [])
    for event in new_waits:
        findings.append(
            Finding(
                severity="MEDIUM",
                category="GENERAL",
                title=f"New Wait Event: {event}",
                description=f"Wait event '{event}' appears in the current run but not in the baseline.",
                detail=f"Event: {event}",
            )
        )

    return findings


# ─── DMP-specific Findings ────────────────────────────────────────────────────


def generate_dmp_findings(
    baseline_dmps: list[ParsedDmp], current_dmps: list[ParsedDmp]
) -> list[Finding]:
    """Generate Finding instances from parsed .dmp file comparisons."""
    findings: list[Finding] = []

    b_by_type = {d.get("dmp_type"): d for d in baseline_dmps}
    c_by_type = {d.get("dmp_type"): d for d in current_dmps}

    # ── SQLT findings ──────────────────────────────────────────────────────────
    if "sqlt" in b_by_type and "sqlt" in c_by_type:
        findings.extend(_sqlt_findings(b_by_type["sqlt"], c_by_type["sqlt"]))

    # ── ADR trace findings ─────────────────────────────────────────────────────
    if "adr_trace" in b_by_type and "adr_trace" in c_by_type:
        findings.extend(_adr_findings(b_by_type["adr_trace"], c_by_type["adr_trace"]))
    elif "adr_trace" in c_by_type:
        findings.extend(_adr_single_findings(c_by_type["adr_trace"]))

    # ── Spool findings ─────────────────────────────────────────────────────────
    if "spool" in b_by_type and "spool" in c_by_type:
        findings.extend(_spool_findings(b_by_type["spool"], c_by_type["spool"]))

    # ── Data Pump findings ─────────────────────────────────────────────────────
    if "datapump" in b_by_type and "datapump" in c_by_type:
        findings.extend(
            _datapump_findings(b_by_type["datapump"], c_by_type["datapump"])
        )

    return findings


def _sqlt_findings(b: ParsedDmp, c: ParsedDmp) -> list[Finding]:
    return (
        _sqlt_param_findings(b, c)
        + _sqlt_row_count_findings(b, c)
        + _sqlt_clustering_findings(b, c)
        + _sqlt_histogram_findings(b, c)
        + _sqlt_elapsed_findings(b, c)
    )


def _sqlt_param_findings(b: ParsedDmp, c: ParsedDmp) -> list[Finding]:
    """Optimizer parameter changes between runs."""
    findings: list[Finding] = []

    # Optimizer parameter changes
    b_params = b.get("optimizer_params", {})
    c_params = c.get("optimizer_params", {})
    for p in set(b_params) | set(c_params):
        bv = b_params.get(p)
        cv = c_params.get(p)
        if bv and cv and bv != cv:
            sev = (
                "HIGH"
                if p
                in (
                    "optimizer_mode",
                    "optimizer_features_enable",
                    "cursor_sharing",
                    "_optimizer_use_feedback",
                    "optimizer_adaptive_plans",
                )
                else "MEDIUM"
            )
            findings.append(
                Finding(
                    severity=sev,
                    category="GENERAL",
                    title=f"Optimizer Parameter Changed: {p}",
                    description=(
                        f"The optimizer parameter '{p}' changed between baseline and current runs. "
                        "Optimizer parameter changes can cause plan regressions even when SQL and statistics are identical."
                    ),
                    detail=f"Baseline: {bv}  →  Current: {cv}",
                )
            )
    return findings


def _sqlt_row_count_findings(b: ParsedDmp, c: ParsedDmp) -> list[Finding]:
    """NUM_ROWS drift — stale statistics indicator."""
    findings: list[Finding] = []

    # Table row count changes (stale stats indicator)
    b_tables = {t["table"]: t for t in b.get("table_stats", [])}
    c_tables = {t["table"]: t for t in c.get("table_stats", [])}
    for tname in set(b_tables) & set(c_tables):
        b_rows = b_tables[tname].get("num_rows", 0) or 0
        c_rows = c_tables[tname].get("num_rows", 0) or 0
        if b_rows and c_rows:
            try:
                ratio = abs(c_rows - b_rows) / b_rows
                if ratio > 0.50:
                    findings.append(
                        Finding(
                            severity="HIGH",
                            category="STATISTICS",
                            title=f"Large Row Count Change: {tname}",
                            description=(
                                f"Table {tname} shows a {ratio * 100:.0f}% change in NUM_ROWS between baseline and current. "
                                "This likely indicates stale statistics — the optimizer may be using an outdated row estimate, "
                                "causing it to choose a suboptimal plan."
                            ),
                            detail=f"Baseline NUM_ROWS: {b_rows:,}  →  Current NUM_ROWS: {c_rows:,}",
                        )
                    )
                elif ratio > 0.20:
                    findings.append(
                        Finding(
                            severity="MEDIUM",
                            category="STATISTICS",
                            title=f"Row Count Drift: {tname}",
                            description=(
                                f"Table {tname} NUM_ROWS changed by {ratio * 100:.0f}%. "
                                "Consider refreshing statistics if performance has degraded."
                            ),
                            detail=f"Baseline: {b_rows:,}  →  Current: {c_rows:,}",
                        )
                    )
            except ZeroDivisionError:
                pass
    return findings


def _sqlt_clustering_findings(b: ParsedDmp, c: ParsedDmp) -> list[Finding]:
    """Index clustering factor degradation."""
    findings: list[Finding] = []

    # Clustering factor changes
    b_idx = {i["index"]: i for i in b.get("index_stats", [])}
    c_idx = {i["index"]: i for i in c.get("index_stats", [])}
    for iname in set(b_idx) & set(c_idx):
        bcf = b_idx[iname].get("clustering_factor", 0) or 0
        ccf = c_idx[iname].get("clustering_factor", 0) or 0
        if bcf and ccf:
            try:
                ratio = (ccf - bcf) / bcf
                if ratio > 0.50:
                    findings.append(
                        Finding(
                            severity="HIGH",
                            category="INDEX",
                            title=f"Clustering Factor Degraded: {iname}",
                            description=(
                                f"Index {iname} clustering factor increased by {ratio * 100:.0f}%. "
                                "A high clustering factor makes the optimizer favor full table scans over index access. "
                                "This is often caused by heavy DML activity without reorganizing the underlying table."
                            ),
                            detail=f"Baseline CF: {bcf:,}  →  Current CF: {ccf:,}",
                        )
                    )
            except ZeroDivisionError:
                pass
    return findings


def _sqlt_histogram_findings(b: ParsedDmp, c: ParsedDmp) -> list[Finding]:
    """Histograms present in baseline but lost in current."""
    findings: list[Finding] = []

    # Lost histograms
    b_hist = {f"{h['table']}.{h['column']}" for h in b.get("histograms", [])}
    c_hist = {f"{h['table']}.{h['column']}" for h in c.get("histograms", [])}
    for col in b_hist - c_hist:
        findings.append(
            Finding(
                severity="MEDIUM",
                category="STATISTICS",
                title=f"Histogram Removed: {col}",
                description=(
                    f"A histogram on {col} existed in the baseline but is absent in the current run. "
                    "Histograms help the optimizer handle data skew. Losing one can cause cardinality misestimates "
                    "and plan regressions on columns with non-uniform data distribution."
                ),
                detail=f"Column: {col}",
            )
        )
    return findings


def _sqlt_elapsed_findings(b: ParsedDmp, c: ParsedDmp) -> list[Finding]:
    """Elapsed-time regression from SQLT execution stats."""
    findings: list[Finding] = []

    # Elapsed time regression from SQLT exec stats
    b_elapsed = b.get("exec_stats", {}).get("elapsed_time")
    c_elapsed = c.get("exec_stats", {}).get("elapsed_time")
    if b_elapsed and c_elapsed:
        try:
            ratio = float(c_elapsed) / float(b_elapsed)
            if ratio >= 2:
                findings.append(
                    Finding(
                        severity="HIGH" if ratio < 5 else "CRITICAL",
                        category="GENERAL",
                        title=f"Elapsed Time Regression: {ratio:.1f}x Slower (SQLT)",
                        description=f"SQLT execution stats show a {ratio:.1f}x increase in elapsed time.",
                        detail=f"Baseline: {b_elapsed}s  →  Current: {c_elapsed}s",
                    )
                )
        except (ValueError, ZeroDivisionError):
            pass
    return findings


def _adr_findings(b: ParsedDmp, c: ParsedDmp) -> list[Finding]:
    findings: list[Finding] = []

    b_errors = set(e[:10] for e in b.get("ora_errors", []))
    c_errors = set(e[:10] for e in c.get("ora_errors", []))
    for err in c_errors - b_errors:
        findings.append(
            Finding(
                severity="HIGH",
                category="GENERAL",
                title=f"New Oracle Error in Current Run: {err}",
                description=(
                    f"Error {err} appears in the current trace but not the baseline. "
                    "Oracle errors during execution can cause fallback plans, retries, or degraded performance."
                ),
                detail=f"Error: {err}",
            )
        )

    b_events = {e for e, _ in b.get("top_wait_events", [])}
    c_events = {e for e, _ in c.get("top_wait_events", [])}
    for ev in c_events - b_events:
        findings.append(
            Finding(
                severity="MEDIUM",
                category="GENERAL",
                title=f"New Wait Event in Current Trace: {ev}",
                description=(
                    f"Wait event '{ev}' appears in the current trace but was absent in the baseline. "
                    "New wait events often indicate resource contention, I/O issues, or locking problems."
                ),
                detail=f"Event: {ev}",
            )
        )

    b_ela = b.get("elapsed_time")
    c_ela = c.get("elapsed_time")
    if b_ela and c_ela:
        try:
            ratio = float(c_ela) / float(b_ela)
            if ratio >= 2:
                findings.append(
                    Finding(
                        severity="HIGH" if ratio < 5 else "CRITICAL",
                        category="GENERAL",
                        title=f"Trace Elapsed Time Regression: {ratio:.1f}x",
                        description=f"ADR trace shows elapsed time increased {ratio:.1f}x.",
                        detail=f"Baseline: {b_ela}s  →  Current: {c_ela}s",
                    )
                )
        except (ValueError, ZeroDivisionError):
            pass

    return findings


def _adr_single_findings(c: ParsedDmp) -> list[Finding]:
    """Check a single (current-only) ADR trace for critical issues."""
    findings: list[Finding] = []
    for err in c.get("ora_errors", [])[:5]:
        findings.append(
            Finding(
                severity="HIGH",
                category="GENERAL",
                title=f"Oracle Error Found in Trace: {err[:40]}",
                description="An ORA- error was found in the current trace file. This may be contributing to performance issues.",
                detail=err[:200],
            )
        )
    return findings


def _spool_findings(b: ParsedDmp, c: ParsedDmp) -> list[Finding]:
    findings: list[Finding] = []

    b_ela = b.get("total_elapsed")
    c_ela = c.get("total_elapsed")
    if b_ela and c_ela:
        try:
            ratio = float(c_ela) / float(b_ela)
            if ratio >= 1.5:
                findings.append(
                    Finding(
                        severity="HIGH" if ratio >= 3 else "MEDIUM",
                        category="GENERAL",
                        title=f"Spool Elapsed Time Regression: {ratio:.1f}x",
                        description=f"SQL*Plus timing shows execution is {ratio:.1f}x slower than the baseline.",
                        detail=f"Baseline: {b_ela:.1f}s  →  Current: {c_ela:.1f}s",
                    )
                )
        except (ValueError, ZeroDivisionError):
            pass

    b_auto = b.get("autotrace", {})
    c_auto = c.get("autotrace", {})
    for key in ["db_block_gets", "consistent_gets", "physical_reads"]:
        bv = b_auto.get(key, 0)
        cv = c_auto.get(key, 0)
        if bv and cv:
            try:
                ratio = cv / bv
                if ratio >= 2:
                    findings.append(
                        Finding(
                            severity="MEDIUM",
                            category="GENERAL",
                            title=f"Autotrace Metric Regressed: {key.replace('_', ' ').title()} +{ratio:.1f}x",
                            description=(
                                f"SQL*Plus AUTOTRACE shows '{key}' increased {ratio:.1f}x. "
                                "Increased logical reads often indicate a plan change causing more blocks to be visited."
                            ),
                            detail=f"Baseline: {bv:,}  →  Current: {cv:,}",
                        )
                    )
            except ZeroDivisionError:
                pass

    return findings


def _datapump_findings(b: ParsedDmp, c: ParsedDmp) -> list[Finding]:
    findings: list[Finding] = []

    b_ver = b.get("oracle_version")
    c_ver = c.get("oracle_version")
    if b_ver and c_ver and b_ver != c_ver:
        findings.append(
            Finding(
                severity="MEDIUM",
                category="GENERAL",
                title="Oracle Version Difference in Data Pump Exports",
                description=(
                    "The baseline and current Data Pump exports were created on different Oracle versions. "
                    "Version differences can affect optimizer behavior, available features, and execution plans."
                ),
                detail=f"Baseline version: {b_ver}  →  Current version: {c_ver}",
            )
        )

    b_tables = set(b.get("tables", []))
    c_tables = set(c.get("tables", []))
    for t in c_tables - b_tables:
        findings.append(
            Finding(
                severity="LOW",
                category="SQL_CHANGE",
                title=f"New Table in Current Export: {t}",
                description=f"Table '{t}' appears in the current Data Pump export but not the baseline.",
                detail=f"Table: {t}",
            )
        )
    for t in b_tables - c_tables:
        findings.append(
            Finding(
                severity="LOW",
                category="SQL_CHANGE",
                title=f"Table Removed from Export: {t}",
                description=f"Table '{t}' was in the baseline export but is absent from the current.",
                detail=f"Table: {t}",
            )
        )

    return findings
