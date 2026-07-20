"""Core data models — shared shapes passed between all layers.

No PyQt6 imports here. Dataclasses for the aggregate objects; TypedDicts for
the JSON-shaped payloads produced by parsers and comparison engines. TypedDicts
are plain dicts at runtime, so serialization to results_json and all existing
.get() consumers are unaffected — they exist for mypy shape checking.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import NotRequired, TypedDict

# ── Parser payloads: SQL ──────────────────────────────────────────────────────


class IndexHintRef(TypedDict):
    """An index referenced by an optimizer hint."""

    table: str
    index: str
    source: str


class ParsedSql(TypedDict):
    """Output of parsers.sql_parser.parse_sql_file."""

    filepath: str
    content: str
    statements: NotRequired[list[str]]
    hints: NotRequired[list[str]]
    indexes_referenced: NotRequired[list[IndexHintRef]]
    tables: NotRequired[list[str]]
    joins: NotRequired[list[str]]
    predicates: NotRequired[list[str]]
    error: NotRequired[str]


# ── Parser payloads: execution plans ─────────────────────────────────────────


class PlanNode(TypedDict):
    """One row of a DBMS_XPLAN-style plan table."""

    id: str
    operation: str
    name: str
    depth: int
    rows: int | None
    bytes: int | None
    cost: int | None
    # Live-DB plan rows may carry the object name under this key instead.
    object_name: NotRequired[str]


class PlanStats(TypedDict, total=False):
    elapsed: str
    rows_processed: int


class ParsedPlan(TypedDict):
    """Output of parsers.xplan_parser.parse_xplan_file."""

    raw: str
    nodes: list[PlanNode]
    predicate_info: NotRequired[list[str]]
    notes: NotRequired[list[str]]
    stats: NotRequired[PlanStats]
    error: NotRequired[str]


# ── Parser payloads: AWR / TKPROF ────────────────────────────────────────────


class WaitEvent(TypedDict, total=False):
    """A wait-event entry; key set varies by source format."""

    event: str
    waits: str
    time_s: str
    pct: str
    elapsed_us: int


class TkprofCallStats(TypedDict):
    count: int
    cpu: float
    elapsed: float
    disk: int
    query: int
    rows: int


class TkprofBlock(TypedDict, total=False):
    """One SQL block from TKPROF output."""

    sql_text: str
    parse: TkprofCallStats
    execute: TkprofCallStats
    fetch: TkprofCallStats
    total_elapsed: float
    total_cpu: float
    total_disk_reads: int
    total_logical_reads: int
    total_rows: int
    rows_processed: int


class TopSqlRef(TypedDict, total=False):
    sql_id: str
    elapsed: str


class AwrMetrics(TypedDict, total=False):
    """Metrics dict shared by AWR/TKPROF parsing and dmp mini-metrics.

    All keys optional; which appear depends on the source format.
    """

    db_time_mins: str
    elapsed_mins: str
    db_time: str
    elapsed: str | None
    db_cpu: str
    cpu: str | None
    top_wait_events: list[WaitEvent]
    top_sql: list[TopSqlRef] | list[TkprofBlock]
    top_sql_elapsed: list[TopSqlRef]
    load_profile: dict[str, str]
    buffer_gets: str
    physical_reads: str
    parse_count: str
    execute_count: str
    sql_blocks: list[TkprofBlock]
    total_sql_count: int
    ora_errors: list[str]
    sql_id: str | None


class ParsedAwr(TypedDict):
    """Output of parsers.awr_parser.parse_awr_tkprof_file."""

    type: str  # "awr_html" | "awr_text" | "tkprof" | "unknown"
    metrics: AwrMetrics
    filepath: NotRequired[str]
    raw_length: NotRequired[int]
    error: NotRequired[str]


# ── Parser payloads: .dmp dumps ──────────────────────────────────────────────


class SqltPlan(TypedDict):
    plan_hash_value: str
    nodes: list[PlanNode]


class TableStat(TypedDict, total=False):
    table: str
    num_rows: int
    blocks: int
    last_analyzed: str


class IndexStat(TypedDict):
    index: str
    blevel: int
    clustering_factor: int


class ColumnStat(TypedDict):
    table: str
    column: str
    num_distinct: int
    num_nulls: int


class HistogramRef(TypedDict):
    table: str
    column: str
    histogram_type: str


class BindVariable(TypedDict, total=False):
    name: str
    type: str
    peeked_value: str


class RowCount(TypedDict):
    count: int
    context: str


class ParsedDmp(TypedDict, total=False):
    """Output of parsers.dmp_parser.parse_dmp_file.

    One flat shape for all four dump variants (datapump / adr_trace / spool /
    sqlt), discriminated at runtime by dmp_type. filepath, dmp_type and
    content are always present.
    """

    filepath: str
    dmp_type: str
    content: str
    error: str
    metrics: AwrMetrics
    # datapump
    oracle_version: str | None
    charset: str | None
    export_mode: str | None
    schemas: list[str]
    tables: list[str]
    indexes: list[str]
    sql_fragments: list[str]
    file_size_mb: float
    notes: list[str]
    # adr_trace
    session_id: str | None
    timestamp: str | None
    ora_errors: list[str]
    top_wait_events: list[tuple[str, int]]
    all_wait_events: list[WaitEvent]
    cpu_time: str | None
    elapsed_time: str | None
    plan_nodes: list[PlanNode]
    incidents: list[str]
    # spool
    sql_statements: list[str]
    timings: list[str]
    total_elapsed: float | None
    row_counts: list[RowCount]
    autotrace: dict[str, int]
    # sqlt
    sql_id: str | None
    sql_text: str | None
    plans: list[SqltPlan]
    table_stats: list[TableStat]
    index_stats: list[IndexStat]
    column_stats: list[ColumnStat]
    histograms: list[HistogramRef]
    bind_variables: list[BindVariable]
    system_stats: dict[str, str]
    optimizer_params: dict[str, str]
    env_diffs: list[str]
    exec_stats: dict[str, str]


# ── Diff engine payloads ─────────────────────────────────────────────────────


class StructuralChange(TypedDict):
    type: str  # HINT_ADDED, TABLE_REMOVED, JOIN_CHANGE, INDEX_HINT_ADDED, ...
    detail: str


class DiffStats(TypedDict):
    lines_added: int
    lines_removed: int
    lines_changed: int
    baseline_total_lines: int
    current_total_lines: int
    similarity_ratio: float


# ── Plan comparison payloads ─────────────────────────────────────────────────


class OperationChange(TypedDict, total=False):
    id: str | None
    baseline_op: str | None
    current_op: str | None
    baseline_cost: int | None
    current_cost: int | None
    type: str  # "added" | "removed" when one side is missing


class IndexChange(TypedDict, total=False):
    index: str
    change: str  # REMOVED | ADDED | OPERATION_CHANGED
    baseline_op: str
    current_op: str
    detail: str


class FullScanRegression(TypedDict):
    table: str
    baseline_access: str
    current_access: str
    detail: str


class JoinMethodChange(TypedDict):
    position: int
    baseline_join: str
    current_join: str
    detail: str


class SortChange(TypedDict):
    baseline_sort_count: int
    current_sort_count: int
    detail: str


class PlanCompStats(TypedDict, total=False):
    baseline_total_cost: int | None
    current_total_cost: int | None
    cost_delta_pct: float | None


# ── Cross-file comparison payloads (built by analysis_service) ──────────────


class PlanSource(TypedDict):
    """Minimal shape plan comparison needs — anything carrying plan nodes."""

    nodes: list[PlanNode]


class AwrComparison(TypedDict, total=False):
    baseline_elapsed: str | float
    current_elapsed: str | float
    new_wait_events: list[str]
    type: str


class ParamChange(TypedDict):
    baseline: str | None
    current: str | None


class TableStatChange(TypedDict):
    table: str
    baseline_rows: int
    current_rows: int
    change_pct: float


class ClusteringFactorChange(TypedDict):
    index: str
    baseline_cf: int
    current_cf: int
    change_pct: float


class SqltComparison(TypedDict, total=False):
    optimizer_param_changes: dict[str, ParamChange]
    table_stat_changes: list[TableStatChange]
    clustering_factor_changes: list[ClusteringFactorChange]
    histograms_added: list[str]
    histograms_removed: list[str]
    baseline_elapsed: str | None
    current_elapsed: str | None
    baseline_buffer_gets: str | None
    current_buffer_gets: str | None


class AdrComparison(TypedDict):
    new_wait_events: list[str]
    resolved_wait_events: list[str]
    baseline_elapsed: str | None
    current_elapsed: str | None
    new_ora_errors: list[str]


class AutotraceChange(TypedDict):
    baseline: int
    current: int


class SpoolComparison(TypedDict, total=False):
    baseline_elapsed: float | None
    current_elapsed: float | None
    baseline_rows: int
    current_rows: int
    autotrace_changes: dict[str, AutotraceChange]


class DatapumpComparison(TypedDict):
    tables_added: list[str]
    tables_removed: list[str]
    schemas_added: list[str]
    schemas_removed: list[str]
    baseline_version: str | None
    current_version: str | None


class DmpComparison(TypedDict, total=False):
    baseline_descriptions: list[str]
    current_descriptions: list[str]
    baseline_types: list[str | None]
    current_types: list[str | None]
    sqlt: SqltComparison
    adr: AdrComparison
    spool: SpoolComparison
    datapump: DatapumpComparison


# ── Session-level payloads ───────────────────────────────────────────────────


class Recommendation(TypedDict, total=False):
    """AI/offline recommendation result carried on AnalysisSession."""

    mode: str  # "ai" | "offline"
    provider: str
    model: str
    content: str
    error: str | None


# ── Aggregate dataclasses ────────────────────────────────────────────────────


@dataclass
class ConnectionProfile:
    name: str
    connection_type: str  # "direct" or "tns"
    host: str = ""
    port: int = 1521
    service: str = ""
    alias: str = ""
    username: str = ""
    password: str = ""


@dataclass
class Finding:
    severity: str  # CRITICAL / HIGH / MEDIUM / LOW / INFO
    # Execution Plan, Index, Statistics, Wait Event, etc.
    category: str
    title: str
    description: str
    detail: str  # machine-readable extra context
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    annotation: str = ""  # user note, persisted with session


@dataclass
class DiffResult:
    label: str  # "baseline.sql  vs  current.sql"
    baseline_text: str
    current_text: str
    # {line_num: tag} — tag is "remove" or "change"
    baseline_diff_lines: dict[int, str]
    # {line_num: tag} — tag is "add" or "change"
    current_diff_lines: dict[int, str]
    structural_changes: list[StructuralChange]
    stats: DiffStats


@dataclass
class PlanComparison:
    baseline_nodes: list[PlanNode]
    current_nodes: list[PlanNode]
    index_changes: list[IndexChange]
    full_scan_regressions: list[FullScanRegression]
    join_method_changes: list[JoinMethodChange]
    plan_shape_changed: bool
    stats: PlanCompStats
    operation_changes: list[OperationChange] = field(default_factory=list)
    new_sort_operations: list[SortChange] = field(default_factory=list)


@dataclass
class AnalysisSession:
    baseline_files: list[str]
    current_files: list[str]
    findings: list[Finding]
    diff_results: list[DiffResult]
    plan_comparison: PlanComparison | None
    awr_data: AwrComparison
    dmp_context: DmpComparison
    recommendations: Recommendation
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
