"""Analysis Service — QThread worker orchestrating all parsers and core engines.

Emits three signals:
  progress(str)           — status bar message
  finished(object)        — AnalysisSession on success
  error(str)              — traceback string on unhandled exception
"""

import traceback
from pathlib import Path
from typing import Callable, TypeVar, cast

import structlog
from PyQt6.QtCore import QThread, pyqtSignal

from core.models import (
    AdrComparison,
    AnalysisSession,
    AutotraceChange,
    AwrComparison,
    ClusteringFactorChange,
    DatapumpComparison,
    DmpComparison,
    Finding,
    IndexStat,
    ParamChange,
    ParsedAwr,
    ParsedDmp,
    ParsedPlan,
    ParsedSql,
    PlanComparison,
    PlanNode,
    SpoolComparison,
    SqltComparison,
    TableStat,
    TableStatChange,
)
from core import diff_engine, plan_comparator, findings_engine
from services import ai_service, session_service
from parsers.sql_parser import parse_sql_file
from parsers.xplan_parser import parse_xplan_file
from parsers.awr_parser import parse_awr_tkprof_file
from parsers.dmp_parser import parse_dmp_file, describe_dmp

log = structlog.get_logger()

_ParsedT = TypeVar("_ParsedT", ParsedSql, ParsedPlan, ParsedAwr, ParsedDmp)


def _single_sided_plan(
    b_nodes: list[PlanNode], c_nodes: list[PlanNode]
) -> PlanComparison:
    """PlanComparison shell when only one side has a plan — nothing to compare."""
    return PlanComparison(
        baseline_nodes=b_nodes,
        current_nodes=c_nodes,
        index_changes=[],
        full_scan_regressions=[],
        join_method_changes=[],
        plan_shape_changed=False,
        stats={},
    )


class AnalysisWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(object)  # emits AnalysisSession
    error = pyqtSignal(str)

    def __init__(
        self,
        baseline_files: dict[str, list[str]],
        current_files: dict[str, list[str]],
    ) -> None:
        super().__init__()
        self.baseline_files = baseline_files  # role -> [filepath, ...]
        self.current_files = current_files

    def run(self) -> None:
        try:
            session = self.run_analysis()
            self.finished.emit(session)
        except Exception:
            self.error.emit(traceback.format_exc())

    def run_analysis(self) -> AnalysisSession:
        """Run the full analysis pipeline synchronously and return the session."""
        # ── 1. Parse SQL ──────────────────────────────────────────────────────
        self.progress.emit("Parsing SQL/PLSQL files...")
        b_sql = self._parse_all(self.baseline_files.get("sql", []), parse_sql_file)
        c_sql = self._parse_all(self.current_files.get("sql", []), parse_sql_file)

        # ── 2. Diff ───────────────────────────────────────────────────────────
        self.progress.emit("Computing code diffs...")
        diff_results = diff_engine.compare_sql_files({"sql": b_sql}, {"sql": c_sql})

        # ── 3. Parse and compare plans ────────────────────────────────────────
        self.progress.emit("Parsing execution plans...")
        plan_comp = self._plan_stage()

        # ── 4. Parse AWR/TKPROF ───────────────────────────────────────────────
        self.progress.emit("Parsing AWR/TKPROF data...")
        awr_data = self._awr_stage()

        # ── 5. Parse DMP ──────────────────────────────────────────────────────
        self.progress.emit("Parsing .dmp files...")
        b_dmps = self._parse_all(self.baseline_files.get("dmp", []), parse_dmp_file)
        c_dmps = self._parse_all(self.current_files.get("dmp", []), parse_dmp_file)
        dmp_context = self._compare_dmps(b_dmps, c_dmps) if (b_dmps or c_dmps) else {}

        # If no xplan files, try to extract plans from dmp
        if plan_comp is None and dmp_context:
            plan_comp = self._extract_plans_from_dmps(b_dmps, c_dmps)

        # ── 6. Generate findings ──────────────────────────────────────────────
        self.progress.emit("Generating findings...")
        all_findings: list[Finding] = findings_engine.generate_findings(
            diff_results, plan_comp, awr_data
        )
        all_findings += findings_engine.generate_dmp_findings(b_dmps, c_dmps)

        # ── 7. AI recommendations ─────────────────────────────────────────────
        self.progress.emit("Generating recommendations...")
        recommendations = ai_service.generate_recommendations(
            all_findings, diff_results, plan_comp, awr_data, dmp_context
        )

        # ── 8. Build and save session ─────────────────────────────────────────
        self.progress.emit("Saving session...")
        session = AnalysisSession(
            baseline_files=[Path(f).name for f in self._all_paths(self.baseline_files)],
            current_files=[Path(f).name for f in self._all_paths(self.current_files)],
            findings=all_findings,
            diff_results=diff_results,
            plan_comparison=plan_comp,
            awr_data=awr_data,
            dmp_context=dmp_context,
            recommendations=recommendations,
        )
        session_service.save(session)
        self.progress.emit("Analysis complete")
        return session

    def _plan_stage(self) -> PlanComparison | None:
        """Parse xplan files and compare them; single-sided input gets a shell."""
        b_plans = self._parse_all(
            self.baseline_files.get("xplan", []), parse_xplan_file
        )
        c_plans = self._parse_all(self.current_files.get("xplan", []), parse_xplan_file)

        if b_plans and c_plans:
            self.progress.emit("Comparing execution plans...")
            return plan_comparator.compare_plans(b_plans[0], c_plans[0])
        if b_plans or c_plans:
            b_nodes = b_plans[0].get("nodes", []) if b_plans else []
            c_nodes = c_plans[0].get("nodes", []) if c_plans else []
            return _single_sided_plan(b_nodes, c_nodes)
        return None

    def _awr_stage(self) -> AwrComparison:
        """Parse AWR/TKPROF files on both sides and compare when both exist."""
        b_awr = self._parse_all(
            self.baseline_files.get("awr_tkprof", []), parse_awr_tkprof_file
        )
        c_awr = self._parse_all(
            self.current_files.get("awr_tkprof", []), parse_awr_tkprof_file
        )
        return self._compare_awr(b_awr[0], c_awr[0]) if b_awr and c_awr else {}

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _parse_all(
        self, filepaths: list[str], parser_fn: Callable[[str], _ParsedT]
    ) -> list[_ParsedT]:
        results: list[_ParsedT] = []
        for fp in filepaths:
            try:
                results.append(parser_fn(fp))
            except Exception as exc:
                # Parser boundary: any parse failure becomes an error entry the
                # UI can display instead of aborting the whole analysis run.
                # The marker matches the parsers' own failure contract —
                # consumers treat any payload carrying "error" as unusable.
                log.warning("analysis.parse_failed", filepath=fp, error=str(exc))
                results.append(cast(_ParsedT, {"error": str(exc), "filepath": fp}))
        return results

    def _all_paths(self, files_dict: dict[str, list[str]]) -> list[str]:
        paths: list[str] = []
        for v in files_dict.values():
            paths.extend(v)
        return paths

    def _compare_awr(
        self, baseline_awr: ParsedAwr, current_awr: ParsedAwr
    ) -> AwrComparison:
        """Compare AWR metrics between baseline and current"""
        comparison: AwrComparison = {}

        b_metrics = baseline_awr.get("metrics", {})
        c_metrics = current_awr.get("metrics", {})

        # Compare elapsed times — first metric present on both sides wins
        for b_val, c_val in (
            (b_metrics.get("db_time"), c_metrics.get("db_time")),
            (b_metrics.get("elapsed"), c_metrics.get("elapsed")),
            (b_metrics.get("db_time_mins"), c_metrics.get("db_time_mins")),
            (b_metrics.get("elapsed_mins"), c_metrics.get("elapsed_mins")),
        ):
            if b_val is not None and c_val is not None:
                comparison["baseline_elapsed"] = b_val
                comparison["current_elapsed"] = c_val
                break

        # New wait events
        b_events = {e.get("event", "") for e in b_metrics.get("top_wait_events", [])}
        c_events = {e.get("event", "") for e in c_metrics.get("top_wait_events", [])}
        new_events = c_events - b_events
        comparison["new_wait_events"] = list(new_events)

        # TKPROF comparison — sum elapsed over the ten most expensive blocks
        if baseline_awr.get("type") == "tkprof" and current_awr.get("type") == "tkprof":
            comparison["type"] = "tkprof"
            b_top = sorted(
                b_metrics.get("sql_blocks", []),
                key=lambda blk: blk.get("total_elapsed", 0.0),
                reverse=True,
            )[:10]
            c_top = sorted(
                c_metrics.get("sql_blocks", []),
                key=lambda blk: blk.get("total_elapsed", 0.0),
                reverse=True,
            )[:10]

            if b_top and c_top:
                b_total = sum(blk.get("total_elapsed", 0.0) for blk in b_top)
                c_total = sum(blk.get("total_elapsed", 0.0) for blk in c_top)
                comparison["baseline_elapsed"] = round(b_total, 2)
                comparison["current_elapsed"] = round(c_total, 2)

        return comparison

    def _compare_dmps(
        self, baseline_dmps: list[ParsedDmp], current_dmps: list[ParsedDmp]
    ) -> DmpComparison:
        """Produce a structured comparison summary for all dmp files."""
        comparison: DmpComparison = {
            "baseline_descriptions": [describe_dmp(d) for d in baseline_dmps],
            "current_descriptions": [describe_dmp(d) for d in current_dmps],
            "baseline_types": [d.get("dmp_type") for d in baseline_dmps],
            "current_types": [d.get("dmp_type") for d in current_dmps],
        }

        # Compare SQLT pairs — richest data source
        b_sqlt = [d for d in baseline_dmps if d.get("dmp_type") == "sqlt"]
        c_sqlt = [d for d in current_dmps if d.get("dmp_type") == "sqlt"]
        if b_sqlt and c_sqlt:
            comparison["sqlt"] = self._compare_sqlt(b_sqlt[0], c_sqlt[0])

        # Compare ADR trace pairs
        b_adr = [d for d in baseline_dmps if d.get("dmp_type") == "adr_trace"]
        c_adr = [d for d in current_dmps if d.get("dmp_type") == "adr_trace"]
        if b_adr and c_adr:
            comparison["adr"] = self._compare_adr(b_adr[0], c_adr[0])

        # Compare spool pairs
        b_spool = [d for d in baseline_dmps if d.get("dmp_type") == "spool"]
        c_spool = [d for d in current_dmps if d.get("dmp_type") == "spool"]
        if b_spool and c_spool:
            comparison["spool"] = self._compare_spool(b_spool[0], c_spool[0])

        # Data Pump: note schema/table differences
        b_dp = [d for d in baseline_dmps if d.get("dmp_type") == "datapump"]
        c_dp = [d for d in current_dmps if d.get("dmp_type") == "datapump"]
        if b_dp or c_dp:
            comparison["datapump"] = self._compare_datapump(
                b_dp[0] if b_dp else {}, c_dp[0] if c_dp else {}
            )

        return comparison

    def _compare_sqlt(self, b: ParsedDmp, c: ParsedDmp) -> SqltComparison:
        """Compare two SQLT dumps."""
        b_hist = {
            f"{h['table']}.{h['column']}": h["histogram_type"]
            for h in b.get("histograms", [])
        }
        c_hist = {
            f"{h['table']}.{h['column']}": h["histogram_type"]
            for h in c.get("histograms", [])
        }
        b_exec = b.get("exec_stats", {})
        c_exec = c.get("exec_stats", {})
        return {
            "optimizer_param_changes": _sqlt_param_changes(b, c),
            "table_stat_changes": _sqlt_table_stat_changes(b, c),
            "clustering_factor_changes": _sqlt_cf_changes(b, c),
            "histograms_added": [k for k in c_hist if k not in b_hist],
            "histograms_removed": [k for k in b_hist if k not in c_hist],
            "baseline_elapsed": b_exec.get("elapsed_time"),
            "current_elapsed": c_exec.get("elapsed_time"),
            "baseline_buffer_gets": b_exec.get("buffer_gets"),
            "current_buffer_gets": c_exec.get("buffer_gets"),
        }

    def _compare_adr(self, b: ParsedDmp, c: ParsedDmp) -> AdrComparison:
        """Compare two ADR trace dumps."""
        b_events = {e for e, _ in b.get("top_wait_events", [])}
        c_events = {e for e, _ in c.get("top_wait_events", [])}
        return {
            "new_wait_events": list(c_events - b_events),
            "resolved_wait_events": list(b_events - c_events),
            "baseline_elapsed": b.get("elapsed_time"),
            "current_elapsed": c.get("elapsed_time"),
            "new_ora_errors": [
                e for e in c.get("ora_errors", []) if e not in b.get("ora_errors", [])
            ],
        }

    def _compare_spool(self, b: ParsedDmp, c: ParsedDmp) -> SpoolComparison:
        """Compare two SQL*Plus spool dumps."""
        result: SpoolComparison = {
            "baseline_elapsed": b.get("total_elapsed"),
            "current_elapsed": c.get("total_elapsed"),
        }
        b_rows = sum(r["count"] for r in b.get("row_counts", []))
        c_rows = sum(r["count"] for r in c.get("row_counts", []))
        result["baseline_rows"] = b_rows
        result["current_rows"] = c_rows

        b_auto = b.get("autotrace", {})
        c_auto = c.get("autotrace", {})
        auto_changes: dict[str, AutotraceChange] = {}
        for key in set(b_auto) | set(c_auto):
            bv = b_auto.get(key, 0)
            cv = c_auto.get(key, 0)
            if bv and cv and abs(cv - bv) / max(bv, 1) > 0.25:
                auto_changes[key] = {"baseline": bv, "current": cv}
        result["autotrace_changes"] = auto_changes
        return result

    def _compare_datapump(self, b: ParsedDmp, c: ParsedDmp) -> DatapumpComparison:
        """Note schema/table differences between two Data Pump dumps."""
        b_tables = set(b.get("tables", []))
        c_tables = set(c.get("tables", []))
        b_schemas = set(b.get("schemas", []))
        c_schemas = set(c.get("schemas", []))
        return {
            "tables_added": sorted(c_tables - b_tables),
            "tables_removed": sorted(b_tables - c_tables),
            "schemas_added": sorted(c_schemas - b_schemas),
            "schemas_removed": sorted(b_schemas - c_schemas),
            "baseline_version": b.get("oracle_version"),
            "current_version": c.get("oracle_version"),
        }

    def _extract_plans_from_dmps(
        self, baseline_dmps: list[ParsedDmp], current_dmps: list[ParsedDmp]
    ) -> PlanComparison | None:
        """Pull embedded execution plans out of dmp files when no xplan files were provided."""
        b_nodes: list[PlanNode] = []
        c_nodes: list[PlanNode] = []

        for d in baseline_dmps:
            nodes = d.get("plan_nodes") or []
            if nodes:
                b_nodes = nodes
                break
            # SQLT has nested plans
            for plan in d.get("plans", []):
                if plan.get("nodes"):
                    b_nodes = plan["nodes"]
                    break

        for d in current_dmps:
            nodes = d.get("plan_nodes") or []
            if nodes:
                c_nodes = nodes
                break
            for plan in d.get("plans", []):
                if plan.get("nodes"):
                    c_nodes = plan["nodes"]
                    break

        if b_nodes and c_nodes:
            return plan_comparator.compare_plans({"nodes": b_nodes}, {"nodes": c_nodes})
        if b_nodes or c_nodes:
            return _single_sided_plan(b_nodes, c_nodes)
        return None


def _sqlt_param_changes(b: ParsedDmp, c: ParsedDmp) -> dict[str, ParamChange]:
    """Optimizer parameters that differ between the two SQLT dumps."""
    # Optimizer parameter changes
    b_params = b.get("optimizer_params", {})
    c_params = c.get("optimizer_params", {})
    param_changes: dict[str, ParamChange] = {}
    for p in set(b_params) | set(c_params):
        bv = b_params.get(p)
        cv = c_params.get(p)
        if bv != cv:
            param_changes[p] = {"baseline": bv, "current": cv}
    return param_changes


def _sqlt_table_stat_changes(b: ParsedDmp, c: ParsedDmp) -> list[TableStatChange]:
    """Tables whose NUM_ROWS drifted more than 20% between dumps."""
    # Table stats changes (num_rows)
    b_tables: dict[str, TableStat] = {t["table"]: t for t in b.get("table_stats", [])}
    c_tables: dict[str, TableStat] = {t["table"]: t for t in c.get("table_stats", [])}
    stat_changes: list[TableStatChange] = []
    for tname in set(b_tables) & set(c_tables):
        b_rows = b_tables[tname].get("num_rows", 0) or 0
        c_rows = c_tables[tname].get("num_rows", 0) or 0
        if b_rows and c_rows:
            try:
                ratio = abs(c_rows - b_rows) / b_rows
                if ratio > 0.20:
                    stat_changes.append(
                        {
                            "table": tname,
                            "baseline_rows": b_rows,
                            "current_rows": c_rows,
                            "change_pct": round(ratio * 100, 1),
                        }
                    )
            except ZeroDivisionError:
                pass
    return stat_changes


def _sqlt_cf_changes(b: ParsedDmp, c: ParsedDmp) -> list[ClusteringFactorChange]:
    """Indexes whose clustering factor moved more than 20% between dumps."""
    # Index clustering factor changes
    b_idx: dict[str, IndexStat] = {i["index"]: i for i in b.get("index_stats", [])}
    c_idx: dict[str, IndexStat] = {i["index"]: i for i in c.get("index_stats", [])}
    cf_changes: list[ClusteringFactorChange] = []
    for iname in set(b_idx) & set(c_idx):
        bcf = b_idx[iname].get("clustering_factor", 0) or 0
        ccf = c_idx[iname].get("clustering_factor", 0) or 0
        if bcf and ccf:
            try:
                ratio = abs(ccf - bcf) / bcf
                if ratio > 0.20:
                    cf_changes.append(
                        {
                            "index": iname,
                            "baseline_cf": bcf,
                            "current_cf": ccf,
                            "change_pct": round(ratio * 100, 1),
                        }
                    )
            except ZeroDivisionError:
                pass
    return cf_changes
