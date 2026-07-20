"""AWR and TKPROF Report Parser"""

import re

from core.models import (
    AwrMetrics,
    ParsedAwr,
    TkprofBlock,
    TkprofCallStats,
    TopSqlRef,
    WaitEvent,
)


def parse_awr_tkprof_file(filepath: str) -> ParsedAwr:
    """Auto-detect and parse AWR HTML, AWR text, or TKPROF output"""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        return {"error": str(e), "type": "unknown", "metrics": {}}

    # Detect format
    if "<html" in content.lower() or "<HTML" in content:
        return _parse_awr_html(content, filepath)
    elif "TKPROF" in content.upper() or "call     count" in content.lower():
        return _parse_tkprof(content, filepath)
    else:
        return _parse_awr_text(content, filepath)


# ─── AWR HTML Parser ──────────────────────────────────────────────────────────


def _parse_awr_html(content: str, filepath: str) -> ParsedAwr:
    """Parse AWR HTML report"""
    metrics: AwrMetrics = {}

    # Extract key metrics using regex on HTML content
    # DB Time
    db_time = re.search(
        r"DB Time.*?(\d+[\d,.]+)\s*\(mins?\)", content, re.IGNORECASE | re.DOTALL
    )
    if db_time:
        metrics["db_time_mins"] = db_time.group(1)

    # Elapsed time
    elapsed = re.search(
        r"Elapsed.*?(\d+[\d,.]+)\s*\(mins?\)", content, re.IGNORECASE | re.DOTALL
    )
    if elapsed:
        metrics["elapsed_mins"] = elapsed.group(1)

    # Top wait events - look for common patterns in AWR HTML
    wait_events: list[WaitEvent] = []
    wait_pattern = re.findall(
        r"<td[^>]*>([^<]*(?:wait|latch|buffer|log|I/O)[^<]*)</td>\s*<td[^>]*>(\d+[\d,.]*)</td>",
        content,
        re.IGNORECASE,
    )
    for event, count in wait_pattern[:10]:
        wait_events.append({"event": event.strip(), "waits": count.strip()})

    metrics["top_wait_events"] = wait_events

    # SQL ordered by elapsed time
    top_sql = _extract_top_sql_html(content)
    metrics["top_sql"] = top_sql

    # Instance stats
    metrics.update(_extract_instance_stats_html(content))

    return {
        "filepath": filepath,
        "type": "awr_html",
        "metrics": metrics,
        "raw_length": len(content),
    }


def _extract_top_sql_html(content: str) -> list[TopSqlRef]:
    """Extract top SQL statements from AWR HTML"""
    top_sql: list[TopSqlRef] = []
    # Look for SQL ID patterns
    sql_pattern = re.findall(
        r"(\b[a-z0-9]{13}\b).*?Elapsed.*?(\d+[\d,.]+)",
        content,
        re.IGNORECASE | re.DOTALL,
    )
    for sql_id, elapsed in sql_pattern[:10]:
        top_sql.append({"sql_id": sql_id, "elapsed": elapsed})
    return top_sql


def _stat_after(label: str, content: str) -> str | None:
    """Find the first numeric value following a stat label."""
    m = re.search(rf"{label}.*?(\d[\d,.]+)", content, re.IGNORECASE)
    return m.group(1) if m else None


def _extract_instance_stats_html(content: str) -> AwrMetrics:
    """Extract instance-level stats from AWR HTML"""
    stats: AwrMetrics = {}
    if (v := _stat_after("buffer gets", content)) is not None:
        stats["buffer_gets"] = v
    if (v := _stat_after("physical reads", content)) is not None:
        stats["physical_reads"] = v
    if (v := _stat_after("parse count", content)) is not None:
        stats["parse_count"] = v
    if (v := _stat_after("execute count", content)) is not None:
        stats["execute_count"] = v
    return stats


# ─── AWR Text Parser ──────────────────────────────────────────────────────────


def _parse_awr_text(content: str, filepath: str) -> ParsedAwr:
    """Parse AWR text report"""
    metrics: AwrMetrics = {}

    # DB Time / CPU Time
    def seconds_stat(label: str) -> str | None:
        m = re.search(
            rf"{re.escape(label)}[:\s]+([\d.]+)\s*\(s\)", content, re.IGNORECASE
        )
        return m.group(1) if m else None

    if (v := seconds_stat("DB Time")) is not None:
        metrics["db_time"] = v
    if (v := seconds_stat("Elapsed")) is not None:
        metrics["elapsed"] = v
    if (v := seconds_stat("DB CPU")) is not None:
        metrics["db_cpu"] = v

    # Top 5 timed events
    metrics["top_wait_events"] = _parse_top_events(content)

    # SQL stats
    metrics["top_sql_elapsed"] = _parse_top_sql_text(content)

    # Load profile
    metrics["load_profile"] = _parse_load_profile(content)

    return {
        "filepath": filepath,
        "type": "awr_text",
        "metrics": metrics,
    }


def _parse_top_events(content: str) -> list[WaitEvent]:
    """Parse Top 5 Timed Events section"""
    events: list[WaitEvent] = []
    section = re.search(
        r"Top \d+ Timed.*?\n-+\n(.*?)(?=\n\n|\Z)", content, re.DOTALL | re.IGNORECASE
    )
    if section:
        for line in section.group(1).split("\n")[:10]:
            parts = line.split()
            if len(parts) >= 4:
                events.append(
                    {
                        "event": " ".join(parts[:-3]),
                        "waits": parts[-3] if parts[-3].isdigit() else "",
                        "time_s": parts[-2] if "." in parts[-2] else "",
                        "pct": parts[-1],
                    }
                )
    return events


def _parse_top_sql_text(content: str) -> list[TopSqlRef]:
    """Parse SQL ordered by elapsed time from text AWR"""
    sql_list: list[TopSqlRef] = []
    section = re.search(
        r"SQL ordered by Elapsed Time.*?\n-+\n(.*?)(?=SQL ordered|\Z)",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    if section:
        sql_id_pattern = re.findall(r"([a-z0-9]{13})", section.group(1), re.IGNORECASE)
        for sql_id in sql_id_pattern[:10]:
            sql_list.append({"sql_id": sql_id})
    return sql_list


def _parse_load_profile(content: str) -> dict[str, str]:
    """Parse Load Profile section"""
    profile: dict[str, str] = {}
    section = re.search(
        r"Load Profile.*?\n-+\n(.*?)(?=\n\n|\Z)", content, re.DOTALL | re.IGNORECASE
    )
    if section:
        patterns = {
            "db_time_per_sec": r"DB Time\(s\)[:\s]+([\d.]+)",
            "logical_reads": r"Logical reads[:\s]+([\d,.]+)",
            "block_changes": r"Block changes[:\s]+([\d,.]+)",
            "physical_reads": r"Physical reads[:\s]+([\d,.]+)",
        }
        text = section.group(1)
        for key, pat in patterns.items():
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                profile[key] = m.group(1)
    return profile


# ─── TKPROF Parser ────────────────────────────────────────────────────────────


def _parse_tkprof(content: str, filepath: str) -> ParsedAwr:
    """Parse TKPROF output"""
    metrics: AwrMetrics = {}
    sql_blocks: list[TkprofBlock] = []

    # Split into SQL blocks
    # Each block starts with the SQL text and contains call stats
    blocks = re.split(r"\*{5,}", content)

    for block in blocks:
        if "call     count" in block.lower():
            sql_block = _parse_tkprof_block(block)
            if sql_block:
                sql_blocks.append(sql_block)

    metrics["sql_blocks"] = sql_blocks
    metrics["total_sql_count"] = len(sql_blocks)

    # Find most expensive SQL
    if sql_blocks:
        most_expensive = sorted(
            sql_blocks, key=lambda x: x.get("total_elapsed", 0), reverse=True
        )
        metrics["top_sql"] = most_expensive[:10]

    return {
        "filepath": filepath,
        "type": "tkprof",
        "metrics": metrics,
    }


def _parse_tkprof_block(block: str) -> TkprofBlock | None:
    """Parse a single TKPROF SQL block"""
    result: TkprofBlock = {}

    # Extract SQL text (everything before "call     count")
    sql_match = re.search(r"^(.*?)(?=call\s+count)", block, re.DOTALL | re.IGNORECASE)
    if sql_match:
        result["sql_text"] = sql_match.group(1).strip()[:500]

    # Parse call stats table
    # call     count       cpu    elapsed       disk      query    current        rows
    call_pattern = re.findall(
        r"(Parse|Execute|Fetch)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)",
        block,
        re.IGNORECASE,
    )

    total_elapsed = 0.0
    total_cpu = 0.0
    total_disk = 0
    total_query = 0
    total_rows = 0

    for call_type, count, cpu, elapsed, disk, query, current, rows in call_pattern:
        call_stats: TkprofCallStats = {
            "count": int(count),
            "cpu": float(cpu),
            "elapsed": float(elapsed),
            "disk": int(disk),
            "query": int(query),
            "rows": int(rows),
        }
        call_key = call_type.lower()
        if call_key == "parse":
            result["parse"] = call_stats
        elif call_key == "execute":
            result["execute"] = call_stats
        elif call_key == "fetch":
            result["fetch"] = call_stats
        total_elapsed += float(elapsed)
        total_cpu += float(cpu)
        total_disk += int(disk)
        total_query += int(query)
        total_rows += int(rows)

    if not call_pattern:
        return None

    result["total_elapsed"] = total_elapsed
    result["total_cpu"] = total_cpu
    result["total_disk_reads"] = total_disk
    result["total_logical_reads"] = total_query
    result["total_rows"] = total_rows

    # Extract Rows processed
    rows_m = re.search(r"(\d+)\s+rows\s+processed", block, re.IGNORECASE)
    if rows_m:
        result["rows_processed"] = int(rows_m.group(1))

    return result
