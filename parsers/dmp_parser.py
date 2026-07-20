"""
Oracle .dmp File Parser

Handles four Oracle dump file types:
  1. Data Pump binary exports (expdp) — binary, string-extracted
  2. ADR trace/diagnostic dumps        — text
  3. SQL*Plus spool dumps              — text
  4. SQLT/SQLTXPLAIN dumps             — text, richest source
"""

import re
from pathlib import Path

from core.models import (
    BindVariable,
    ColumnStat,
    HistogramRef,
    IndexStat,
    ParsedDmp,
    PlanNode,
    RowCount,
    SqltPlan,
    TableStat,
    WaitEvent,
)


# ── Public entry point ────────────────────────────────────────────────────────


def parse_dmp_file(filepath: str) -> ParsedDmp:
    """Auto-detect dump type and parse accordingly."""
    try:
        # Read first 4 KB as bytes to detect binary vs text
        with open(filepath, "rb") as f:
            raw_bytes = f.read(4096)
    except OSError as e:
        return _error(filepath, str(e))

    dmp_type = _detect_type(filepath, raw_bytes)

    if dmp_type == "datapump":
        return _parse_datapump(filepath, raw_bytes)

    # Text-based files — read full content
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        return _error(filepath, str(e))

    if dmp_type == "sqlt":
        return _parse_sqlt(filepath, content)
    elif dmp_type == "adr_trace":
        return _parse_adr_trace(filepath, content)
    else:
        return _parse_spool(filepath, content)


# ── Type detection ────────────────────────────────────────────────────────────


def _detect_type(filepath: str, raw_bytes: bytes) -> str:
    """Identify which of the four dump types this file is."""

    # Data Pump: starts with binary magic bytes or "DMPF" header
    if raw_bytes[:4] in (b"DMPF", b"\x03\xf0\x00\x00") or _is_mostly_binary(raw_bytes):
        return "datapump"

    text_head = raw_bytes.decode("utf-8", errors="replace").upper()

    # SQLT: contains distinctive SQLT header markers
    if any(
        marker in text_head
        for marker in (
            "SQLTXPLAIN",
            "SQLT_",
            "SQLT REPORT",
            "SQLT MAIN",
            "S Q L T",
            "TOOL: SQLT",
        )
    ):
        return "sqlt"

    # ADR trace: Oracle trace file signatures
    if any(
        marker in text_head
        for marker in (
            "DUMP FILE",
            "ORACLE CORPORATION",
            "SYSTEM PARAMETERS",
            "*** SESSION ID",
            "*** CLIENT ID",
            "TRACE DUMP",
            "ORA-",
            "INCIDENT",
        )
    ):
        return "adr_trace"

    # Default: treat as SQL*Plus spool
    return "spool"


def _is_mostly_binary(data: bytes, threshold: float = 0.30) -> bool:
    """Return True if more than threshold fraction of bytes are non-printable."""
    if not data:
        return False
    non_printable = sum(1 for b in data if b < 9 or (13 < b < 32) or b > 126)
    return (non_printable / len(data)) > threshold


# ── Data Pump parser ──────────────────────────────────────────────────────────


def _parse_datapump(filepath: str, raw_bytes: bytes) -> ParsedDmp:
    """
    Data Pump .dmp files are proprietary binary.
    We extract printable strings to recover schema/table/index names,
    the export version, and character set info.
    """
    # Read more of the file for string extraction
    try:
        with open(filepath, "rb") as f:
            full_bytes = f.read(2 * 1024 * 1024)  # Read up to 2 MB
    except OSError:
        full_bytes = raw_bytes  # fall back to the 4 KB already read

    strings = _extract_strings(full_bytes, min_len=4)
    text_blob = "\n".join(strings)

    version = _dp_version(text_blob)
    charset = _dp_charset(text_blob)
    schemas = _dp_schemas(text_blob)

    # Table names
    tables = _extract_identifiers_near(
        text_blob, keywords=["TABLE", "TABLE_DATA"], min_len=2
    )

    # Index names
    indexes = _extract_identifiers_near(text_blob, keywords=["INDEX"], min_len=2)

    # Embedded SQL fragments
    sql_fragments = _extract_sql_fragments(text_blob)

    mode = _dp_export_mode(text_blob)

    file_size = Path(filepath).stat().st_size

    return {
        "filepath": filepath,
        "dmp_type": "datapump",
        "oracle_version": version,
        "charset": charset,
        "export_mode": mode,
        "schemas": sorted(schemas),
        "tables": sorted(tables)[:50],
        "indexes": sorted(indexes)[:50],
        "sql_fragments": sql_fragments[:20],
        "file_size_mb": round(file_size / 1_048_576, 2),
        "notes": [
            "Data Pump binary format — object names and SQL extracted via string analysis",
            "For full schema comparison, export DDL using: impdp ... SQLFILE=ddl_output.sql",
        ],
        "content": text_blob[:8000],  # For findings engine use
    }


def _dp_version(text_blob: str) -> str | None:
    m = re.search(r"(\d+\.\d+\.\d+\.\d+\.\d+)", text_blob)
    return m.group(1) if m else None


def _dp_charset(text_blob: str) -> str | None:
    m = re.search(
        r"(AL32UTF8|WE8MSWIN1252|UTF8|AL16UTF16|WE8ISO8859P1)", text_blob, re.IGNORECASE
    )
    return m.group(1) if m else None


def _dp_schemas(text_blob: str) -> set[str]:
    """ALL_CAPS identifiers appearing near SCHEMA or OWNER markers."""
    schemas = set()
    for m in re.finditer(
        r"(?:SCHEMA|OWNER)[=:\s]+([A-Z][A-Z0-9_$#]{1,30})", text_blob, re.IGNORECASE
    ):
        schemas.add(m.group(1).upper())
    return schemas


def _dp_export_mode(text_blob: str) -> str | None:
    for export_kw in ("FULL", "SCHEMA", "TABLE", "TABLESPACE"):
        if export_kw in text_blob.upper():
            return export_kw
    return None


def _extract_strings(data: bytes, min_len: int = 6) -> list[str]:
    """Extract printable ASCII strings from binary data."""
    strings = []
    current = []
    for byte in data:
        if 32 <= byte <= 126:
            current.append(chr(byte))
        else:
            if len(current) >= min_len:
                strings.append("".join(current))
            current = []
    if len(current) >= min_len:
        strings.append("".join(current))
    return strings


def _extract_identifiers_near(
    text: str, keywords: list[str], min_len: int = 3
) -> set[str]:
    """Extract Oracle identifiers appearing near given keywords."""
    identifiers = set()
    for kw in keywords:
        pattern = rf'\b{kw}\b["\s:=]*([A-Z][A-Z0-9_$#]{{{min_len},30}})'
        for m in re.finditer(pattern, text, re.IGNORECASE):
            val = m.group(1).upper()
            # Filter out Oracle reserved words and noise
            if val not in _ORACLE_RESERVED:
                identifiers.add(val)
    return identifiers


def _extract_sql_fragments(text: str) -> list[str]:
    """Pull out embedded SQL statement fragments."""
    fragments = []
    patterns = [
        r"(CREATE\s+(?:TABLE|INDEX|SEQUENCE|VIEW|PROCEDURE|FUNCTION|PACKAGE)[^\n]{10,200})",
        r"(ALTER\s+(?:TABLE|INDEX)[^\n]{10,150})",
        r"(SELECT\s+.{10,200}FROM\s+\w+)",
        r"(INSERT\s+INTO\s+\w+[^\n]{5,150})",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE | re.DOTALL):
            frag = " ".join(m.group(1).split())[:300]
            if frag not in fragments:
                fragments.append(frag)
    return fragments


# ── ADR Trace parser ──────────────────────────────────────────────────────────


def _parse_adr_trace(filepath: str, content: str) -> ParsedDmp:
    """Parse Oracle ADR diagnostic/trace dump files."""

    # Session info
    session_id = None
    sid_match = re.search(r"\*\*\*\s+SESSION ID:\((\d+\.\d+)\)", content)
    if sid_match:
        session_id = sid_match.group(1)

    # Timestamp
    timestamp = None
    ts_match = re.search(r"\*\*\*\s+(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2})", content)
    if ts_match:
        timestamp = ts_match.group(1)

    # ORA- errors
    ora_errors = []
    for m in re.finditer(r"(ORA-\d{4,6}[^\n]{0,200})", content):
        err = m.group(1).strip()
        if err not in ora_errors:
            ora_errors.append(err)

    wait_events, top_waits = _adr_wait_events(content)
    sql_fragments = _adr_sql_fragments(content)

    cpu_time, elapsed_time = _adr_timings(content)

    # Execution plan sections (traces often embed plans)
    plan_nodes = _extract_plan_from_trace(content)

    # Incident / crash info
    incidents = re.findall(r"Incident\s+(\d+)\s+created", content, re.IGNORECASE)

    return {
        "filepath": filepath,
        "dmp_type": "adr_trace",
        "session_id": session_id,
        "timestamp": timestamp,
        "ora_errors": ora_errors[:20],
        "top_wait_events": top_waits,
        "all_wait_events": wait_events[:100],
        "sql_fragments": sql_fragments,
        "cpu_time": cpu_time,
        "elapsed_time": elapsed_time,
        "plan_nodes": plan_nodes,
        "incidents": incidents,
        "content": content,
        "metrics": {
            "elapsed": elapsed_time,
            "cpu": cpu_time,
            "top_wait_events": [{"event": e, "elapsed_us": t} for e, t in top_waits],
            "ora_errors": ora_errors[:5],
        },
    }


def _adr_timings(content: str) -> tuple[str | None, str | None]:
    """(cpu_time, elapsed_time) as reported in the trace, if present."""
    cpu_m = re.search(r"cpu\s+time[:\s]+([\d.]+)", content, re.IGNORECASE)
    ela_m = re.search(r"elapsed\s+time[:\s]+([\d.]+)", content, re.IGNORECASE)
    return (
        cpu_m.group(1) if cpu_m else None,
        ela_m.group(1) if ela_m else None,
    )


def _adr_wait_events(
    content: str,
) -> tuple[list[WaitEvent], list[tuple[str, int]]]:
    """All wait events plus the top ten summed by elapsed time."""
    wait_events: list[WaitEvent] = []
    for m in re.finditer(
        r"wait\s+#\d+:\s+nam=\'([^\']+)\'.*?ela=\s*(\d+)", content, re.IGNORECASE
    ):
        wait_events.append(
            {
                "event": m.group(1),
                "elapsed_us": int(m.group(2)),
            }
        )

    wait_summary: dict[str, int] = {}
    for w in wait_events:
        ev = w["event"]
        wait_summary[ev] = wait_summary.get(ev, 0) + w["elapsed_us"]
    top_waits = sorted(wait_summary.items(), key=lambda x: x[1], reverse=True)[:10]
    return wait_events, top_waits


def _adr_sql_fragments(content: str) -> list[str]:
    """SQL statement fragments embedded in the trace."""
    sql_fragments: list[str] = []
    for m in re.finditer(
        r"(?:SQL:|sql_text=|PARSING IN CURSOR)[^\n]*\n((?:[ \t]+[^\n]+\n){1,20})",
        content,
        re.IGNORECASE,
    ):
        frag = m.group(1).strip()
        if frag and frag not in sql_fragments:
            sql_fragments.append(frag[:500])
    return sql_fragments


def _extract_plan_from_trace(content: str) -> list[PlanNode]:
    """Extract execution plan embedded in a trace file."""
    from parsers.xplan_parser import parse_plan_table

    # Trace files embed plans in same pipe-delimited format
    if "| Id |" in content or "|  Id  |" in content:
        return parse_plan_table(content)
    return []


# ── SQL*Plus Spool parser ─────────────────────────────────────────────────────


def _parse_spool(filepath: str, content: str) -> ParsedDmp:
    """Parse SQL*Plus spool output saved as .dmp."""

    sql_statements = _spool_sql_statements(content)

    # Timing info (SET TIMING ON)
    timings = []
    for m in re.finditer(r"Elapsed:\s*([\d:\.]+)", content, re.IGNORECASE):
        timings.append(m.group(1))

    # Row counts
    row_counts: list[RowCount] = []
    for m in re.finditer(
        r"(\d+)\s+rows?\s+(?:selected|updated|deleted|inserted|processed)",
        content,
        re.IGNORECASE,
    ):
        row_counts.append({"count": int(m.group(1)), "context": m.group(0)})

    # ORA- errors
    ora_errors = list(set(re.findall(r"ORA-\d{4,6}[^\n]{0,100}", content)))[:10]

    # Embedded execution plans
    plan_nodes = []
    if "| Id |" in content or "|  Id  |" in content:
        from parsers.xplan_parser import parse_plan_table

        plan_nodes = parse_plan_table(content)

    # Statistics (SET AUTOTRACE ON)
    autotrace = _parse_autotrace(content)

    total_elapsed = _spool_total_elapsed(timings)

    return {
        "filepath": filepath,
        "dmp_type": "spool",
        "sql_statements": sql_statements,
        "timings": timings,
        "total_elapsed": total_elapsed,
        "row_counts": row_counts,
        "ora_errors": ora_errors,
        "plan_nodes": plan_nodes,
        "autotrace": autotrace,
        "content": content,
        "metrics": {
            "elapsed": str(total_elapsed) if total_elapsed else None,
            "top_wait_events": [],
            "ora_errors": ora_errors[:3],
        },
    }


def _spool_sql_statements(content: str) -> list[str]:
    """SQL statements echoed by SET ECHO ON."""
    sql_statements: list[str] = []
    for m in re.finditer(
        r"(?:SQL>|sql>)\s*((?:SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|BEGIN|DECLARE)[^;]{5,2000};?)",
        content,
        re.IGNORECASE | re.DOTALL,
    ):
        stmt = " ".join(m.group(1).split())[:1000]
        if stmt not in sql_statements:
            sql_statements.append(stmt)
    return sql_statements


def _spool_total_elapsed(timings: list[str]) -> float | None:
    """Last SET TIMING value parsed as seconds (HH:MM:SS.ss or MM:SS.ss)."""
    if not timings:
        return None
    parts = timings[-1].split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
    except ValueError:
        pass
    return None


def _parse_autotrace(content: str) -> dict[str, int]:
    """Parse SET AUTOTRACE output block."""
    stats: dict[str, int] = {}
    autotrace_section = re.search(
        r"Statistics\s*-+\s*(.*?)(?=\n\n|\Z)", content, re.DOTALL | re.IGNORECASE
    )
    if autotrace_section:
        for line in autotrace_section.group(1).split("\n"):
            m = re.match(r"\s*(\d+)\s+(.+)", line.strip())
            if m:
                key = m.group(2).strip().lower().replace(" ", "_").replace("/", "_")
                stats[key] = int(m.group(1))
    return stats


# ── SQLT parser ───────────────────────────────────────────────────────────────


def _parse_sqlt(filepath: str, content: str) -> ParsedDmp:
    """
    Parse SQLT/SQLTXPLAIN diagnostic dump.
    SQLT is the richest source — contains plans, stats, histograms, object info.
    """

    sql_id = _sqlt_sql_id(content)

    # Execution plans (SQLT contains multiple plan variants)
    plans = _extract_sqlt_plans(content)

    # Object statistics
    table_stats = _extract_sqlt_table_stats(content)
    index_stats = _extract_sqlt_index_stats(content)
    column_stats = _extract_sqlt_column_stats(content)

    # Histograms
    histograms = _extract_sqlt_histograms(content)

    # Bind variables
    binds = _extract_sqlt_binds(content)

    # System stats
    system_stats = _extract_sqlt_system_stats(content)

    # Optimizer parameters
    optimizer_params = _extract_optimizer_params(content)

    sql_text = _sqlt_sql_text(content)

    # Plan environment differences
    env_diffs = _extract_sqlt_env_diffs(content)

    # Execution stats from SQLT
    exec_stats = _extract_sqlt_exec_stats(content)

    return {
        "filepath": filepath,
        "dmp_type": "sqlt",
        "sql_id": sql_id,
        "sql_text": sql_text,
        "plans": plans,
        "table_stats": table_stats,
        "index_stats": index_stats,
        "column_stats": column_stats,
        "histograms": histograms,
        "bind_variables": binds,
        "system_stats": system_stats,
        "optimizer_params": optimizer_params,
        "env_diffs": env_diffs,
        "exec_stats": exec_stats,
        "content": content,
        "metrics": {
            "elapsed": exec_stats.get("elapsed_time"),
            "top_wait_events": [],
            "sql_id": sql_id,
        },
    }


def _sqlt_sql_id(content: str) -> str | None:
    m = re.search(r"SQL_ID[:\s=]+([a-z0-9]{13})", content, re.IGNORECASE)
    return m.group(1) if m else None


def _sqlt_sql_text(content: str) -> str | None:
    m = re.search(
        r"SQL Text\s*[-=]+\s*(.*?)(?=\n[-=]{5}|\Z)", content, re.DOTALL | re.IGNORECASE
    )
    return m.group(1).strip()[:2000] if m else None


def _extract_sqlt_plans(content: str) -> list[SqltPlan]:
    """Extract all execution plan variants from SQLT output."""
    from parsers.xplan_parser import parse_plan_table

    plans: list[SqltPlan] = []

    # SQLT labels plan sections
    plan_sections = re.finditer(
        r"(?:Plan\s+Hash\s+Value|PLAN_HASH_VALUE)[:\s=]+(\d+)(.*?)(?=(?:Plan\s+Hash\s+Value|PLAN_HASH_VALUE)|\Z)",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    for m in plan_sections:
        phv = m.group(1)
        section = m.group(2)
        nodes = parse_plan_table(section)
        if nodes:
            plans.append({"plan_hash_value": phv, "nodes": nodes})

    # Fallback: just get whatever plan is in the content
    if not plans:
        nodes = parse_plan_table(content)
        if nodes:
            plans.append({"plan_hash_value": "unknown", "nodes": nodes})

    return plans


def _extract_sqlt_table_stats(content: str) -> list[TableStat]:
    """Extract table statistics from SQLT."""
    stats: list[TableStat] = []
    pattern = re.compile(
        r"(?:TABLE|table)\s+(\w+)\s*.*?NUM_ROWS[:\s=]+(\d+).*?BLOCKS[:\s=]+(\d+).*?LAST_ANALYZED[:\s=]+([^\n]+)",
        re.DOTALL,
    )
    for m in pattern.finditer(content):
        stats.append(
            {
                "table": m.group(1),
                "num_rows": int(m.group(2)),
                "blocks": int(m.group(3)),
                "last_analyzed": m.group(4).strip()[:30],
            }
        )
    # Also try tabular format
    for line in content.split("\n"):
        line_m = re.match(
            r"\s*(\w{3,30})\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d{2}-\w{3}-\d{2,4})", line
        )
        if line_m and not any(s["table"] == line_m.group(1) for s in stats):
            stats.append(
                {
                    "table": line_m.group(1),
                    "num_rows": int(line_m.group(2)),
                    "blocks": int(line_m.group(3)),
                    "last_analyzed": line_m.group(5),
                }
            )
    return stats[:30]


def _extract_sqlt_index_stats(content: str) -> list[IndexStat]:
    """Extract index statistics from SQLT."""
    stats: list[IndexStat] = []
    for m in re.finditer(
        r"INDEX\s+(\w+)\s+.*?BLEVEL[:\s=]+(\d+).*?CLUSTERING_FACTOR[:\s=]+(\d+)",
        content,
        re.IGNORECASE | re.DOTALL,
    ):
        stats.append(
            {
                "index": m.group(1),
                "blevel": int(m.group(2)),
                "clustering_factor": int(m.group(3)),
            }
        )
    return stats[:30]


def _extract_sqlt_column_stats(content: str) -> list[ColumnStat]:
    """Extract column statistics from SQLT."""
    stats: list[ColumnStat] = []
    for m in re.finditer(
        r"COLUMN\s+(\w+)\.(\w+)\s+.*?NUM_DISTINCT[:\s=]+(\d+).*?NUM_NULLS[:\s=]+(\d+)",
        content,
        re.IGNORECASE | re.DOTALL,
    ):
        stats.append(
            {
                "table": m.group(1),
                "column": m.group(2),
                "num_distinct": int(m.group(3)),
                "num_nulls": int(m.group(4)),
            }
        )
    return stats[:30]


def _extract_sqlt_histograms(content: str) -> list[HistogramRef]:
    """Detect columns with histograms — important for skew-related regressions."""
    histograms: list[HistogramRef] = []
    for m in re.finditer(
        r"(\w+)\.(\w+)\s+.*?HISTOGRAM[:\s=]+(FREQUENCY|HEIGHT\s+BALANCED|HYBRID|NONE)",
        content,
        re.IGNORECASE,
    ):
        htype = m.group(3).strip().upper()
        if htype != "NONE":
            histograms.append(
                {
                    "table": m.group(1),
                    "column": m.group(2),
                    "histogram_type": htype,
                }
            )
    return histograms[:20]


def _extract_sqlt_binds(content: str) -> list[BindVariable]:
    """Extract bind variable names and types."""
    binds: list[BindVariable] = []
    for m in re.finditer(
        r"(?:BIND|bind)[:\s]+:(\w+)\s+.*?(?:TYPE|type)[:\s=]+(\w+)",
        content,
        re.IGNORECASE,
    ):
        binds.append({"name": m.group(1), "type": m.group(2)})
    # Also look for bind peeking values
    for m in re.finditer(r":(\w+)\s*=\s*\'?([^\'\n,]{1,50})\'?", content):
        name = m.group(1)
        val = m.group(2).strip()
        if not any(b["name"] == name for b in binds):
            binds.append({"name": name, "peeked_value": val})
    return binds[:20]


def _extract_sqlt_system_stats(content: str) -> dict[str, str]:
    """Extract system statistics (CPUSPEED, MBRC, etc.)."""
    stats: dict[str, str] = {}
    for param in [
        "CPUSPEED",
        "CPUSPEEDNW",
        "IOSEEKTIM",
        "IOTFRSPEED",
        "MAXTHR",
        "MBRC",
        "MREADTIM",
        "SREADTIM",
    ]:
        m = re.search(rf"{param}[:\s=]+([\d.]+)", content, re.IGNORECASE)
        if m:
            stats[param.lower()] = m.group(1)
    return stats


def _extract_optimizer_params(content: str) -> dict[str, str]:
    """Extract key optimizer parameter values."""
    params: dict[str, str] = {}
    key_params = [
        "optimizer_mode",
        "optimizer_features_enable",
        "db_file_multiblock_read_count",
        "optimizer_index_cost_adj",
        "optimizer_index_caching",
        "optimizer_dynamic_sampling",
        "cursor_sharing",
        "optimizer_adaptive_plans",
        "optimizer_adaptive_statistics",
        "_optimizer_use_feedback",
        "pga_aggregate_target",
    ]
    for p in key_params:
        m = re.search(
            rf"\b{re.escape(p)}\b[:\s=]+([^\n,;]{{1,60}})", content, re.IGNORECASE
        )
        if m:
            params[p] = m.group(1).strip()
    return params


def _extract_sqlt_env_diffs(content: str) -> list[str]:
    """Extract environment differences SQLT flags between plan runs."""
    diffs = []
    diff_section = re.search(
        r"(?:Environment\s+Diff|Parameter\s+Change)(.*?)(?=\n[-=]{5}|\Z)",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    if diff_section:
        for line in diff_section.group(1).split("\n"):
            line = line.strip()
            if line and not line.startswith("-") and len(line) > 5:
                diffs.append(line)
    return diffs[:20]


def _extract_sqlt_exec_stats(content: str) -> dict[str, str]:
    """Extract execution statistics from SQLT."""
    stats: dict[str, str] = {}
    for label, key in [
        ("Elapsed Time", "elapsed_time"),
        ("CPU Time", "cpu_time"),
        ("Buffer Gets", "buffer_gets"),
        ("Physical Reads", "physical_reads"),
        ("Rows Processed", "rows_processed"),
        ("Executions", "executions"),
    ]:
        m = re.search(rf"{re.escape(label)}[:\s=]+([\d,.]+)", content, re.IGNORECASE)
        if m:
            stats[key] = m.group(1).replace(",", "")
    return stats


# ── Helpers ───────────────────────────────────────────────────────────────────


def _error(filepath: str, msg: str) -> ParsedDmp:
    return {"filepath": filepath, "dmp_type": "unknown", "error": msg, "content": ""}


def describe_dmp(parsed: ParsedDmp) -> str:
    """Return a short human-readable description of what was found in a dmp file."""
    t = parsed.get("dmp_type", "unknown")
    if t == "datapump":
        tables = len(parsed.get("tables", []))
        schemas = ", ".join(parsed.get("schemas", [])) or "unknown"
        return f"Data Pump export — schema(s): {schemas}, {tables} tables identified"
    elif t == "adr_trace":
        errors = len(parsed.get("ora_errors", []))
        waits = len(parsed.get("top_wait_events", []))
        return f"ADR Trace — {errors} ORA- error(s), {waits} wait event type(s)"
    elif t == "spool":
        stmts = len(parsed.get("sql_statements", []))
        return f"SQL*Plus Spool — {stmts} SQL statement(s) captured"
    elif t == "sqlt":
        sql_id = parsed.get("sql_id", "unknown")
        plans = len(parsed.get("plans", []))
        return f"SQLT Dump — SQL_ID: {sql_id}, {plans} plan variant(s)"
    return "Unknown dump type"


# Oracle reserved words to filter from identifier extraction
_ORACLE_RESERVED = {
    "SELECT",
    "FROM",
    "WHERE",
    "AND",
    "OR",
    "NOT",
    "IN",
    "IS",
    "NULL",
    "JOIN",
    "LEFT",
    "RIGHT",
    "INNER",
    "OUTER",
    "ON",
    "GROUP",
    "ORDER",
    "BY",
    "HAVING",
    "UNION",
    "ALL",
    "DISTINCT",
    "AS",
    "WITH",
    "CASE",
    "WHEN",
    "THEN",
    "ELSE",
    "END",
    "INSERT",
    "INTO",
    "VALUES",
    "UPDATE",
    "SET",
    "DELETE",
    "CREATE",
    "ALTER",
    "DROP",
    "TABLE",
    "INDEX",
    "VIEW",
    "SEQUENCE",
    "PROCEDURE",
    "FUNCTION",
    "PACKAGE",
    "BODY",
    "TRIGGER",
    "BEGIN",
    "DECLARE",
    "EXCEPTION",
    "RAISE",
    "RETURN",
    "TYPE",
    "CURSOR",
    "OPEN",
    "FETCH",
    "CLOSE",
    "LOOP",
    "FOR",
    "WHILE",
    "IF",
    "ELSIF",
    "COMMIT",
    "ROLLBACK",
    "SAVEPOINT",
    "GRANT",
    "REVOKE",
    "PUBLIC",
    "ROLE",
    "USER",
    "SCHEMA",
    "OWNER",
    "DATA",
    "FILE",
    "DUMP",
    "EXPORT",
    "IMPORT",
    "VERSION",
    "RELEASE",
    "OBJECT",
    "COLUMN",
    "ROWS",
    "BYTES",
    "COST",
    "TIME",
    "DATE",
    "NUMBER",
    "VARCHAR",
    "VARCHAR2",
    "CHAR",
    "CLOB",
    "BLOB",
    "RAW",
    "LONG",
    "FLOAT",
    "INTEGER",
    "BINARY",
    "TIMESTAMP",
    "INTERVAL",
    "BOOLEAN",
    "TRUE",
    "FALSE",
    "ROWNUM",
    "ROWID",
    "SYSDATE",
    "SYSTIMESTAMP",
    "DUAL",
    "LEVEL",
    "CONNECT",
    "PRIOR",
    "START",
    "NOCYCLE",
    "SIBLINGS",
    "ORACLE",
    "CORPORATION",
    "DMPF",
    "NONE",
    "FULL",
    "SCHEMA",
    "TABLESPACE",
    "NETWORK",
}
