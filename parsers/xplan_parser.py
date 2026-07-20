"""DBMS_XPLAN Execution Plan Parser"""

import re

from core.models import ParsedPlan, PlanNode, PlanStats


def parse_xplan_file(filepath: str) -> ParsedPlan:
    """Parse a DBMS_XPLAN output file"""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        return {"error": str(e), "nodes": [], "raw": ""}

    nodes = parse_plan_table(content)
    predicate_info = extract_predicate_info(content)
    notes = extract_notes(content)
    stats = extract_plan_stats(content)

    return {
        "raw": content,
        "nodes": nodes,
        "predicate_info": predicate_info,
        "notes": notes,
        "stats": stats,
    }


def parse_plan_table(content: str) -> list[PlanNode]:
    """
    Parse the plan table from DBMS_XPLAN output.
    Handles both the standard pipe-delimited format and text format.
    """
    nodes = []

    # Try pipe-delimited format first:
    # | Id | Operation | Name | Rows | Bytes | Cost (%CPU) | Time |
    pipe_header = re.search(
        r"\|\s*Id\s*\|\s*Operation\s*\|\s*Name\s*\|\s*Rows\s*\|\s*Bytes\s*\|\s*Cost.*?\|",
        content,
        re.IGNORECASE,
    )

    if pipe_header:
        nodes = _parse_pipe_format(content, pipe_header.start())
    else:
        # Try simplified format without Name column
        pipe_header2 = re.search(
            r"\|\s*Id\s*\|\s*Operation\s*\|", content, re.IGNORECASE
        )
        if pipe_header2:
            nodes = _parse_pipe_format(content, pipe_header2.start())

    return nodes


def _parse_pipe_format(content: str, start_pos: int) -> list[PlanNode]:
    """Parse pipe-delimited plan table"""
    nodes: list[PlanNode] = []
    lines = content[start_pos:].split("\n")
    header_found = False
    post_header_sep_seen = False
    node_id = 0

    for line in lines:
        line = line.rstrip()

        # Skip separator lines
        if re.match(r"^[-|+]+$", line.strip()):
            if not header_found:
                continue  # separator before header
            if not post_header_sep_seen:
                post_header_sep_seen = True  # skip the separator right after the header
                continue
            break  # closing separator — end of table

        if not line.startswith("|"):
            if header_found and line.strip():
                break
            continue

        # Split preserving raw values for depth detection; keep all columns, index by position
        raw_col_parts = [p for p in line.split("|")]
        # Stripped parts for value extraction
        parts = [p.strip() for p in line.split("|")]
        parts = [p for p in parts if p]  # Remove empty

        if not parts:
            continue

        # Detect header row
        if re.match(r"Id", parts[0], re.IGNORECASE):
            header_found = True
            continue

        if not header_found:
            continue

        node = _row_to_node(parts, raw_col_parts, node_id)
        if node is not None:
            nodes.append(node)
            node_id += 1

    return nodes


def _row_to_node(
    parts: list[str], raw_col_parts: list[str], node_id: int
) -> PlanNode | None:
    """Build a PlanNode from one pipe-delimited plan-table row.

    Depth comes from the leading whitespace of the raw Operation column:
    Oracle adds one space of padding plus one space per depth level.
    """
    try:
        row_id_digits = re.sub(r"[^0-9]", "", parts[0])
        row_id = int(row_id_digits) if row_id_digits else node_id

        # raw_col_parts: ['', ' id ', ' operation   ', ...]
        operation_raw = raw_col_parts[2] if len(raw_col_parts) > 2 else ""
        leading = len(operation_raw) - len(operation_raw.lstrip())
        depth = max(0, leading - 1)

        name = parts[2] if len(parts) > 2 else ""
        return {
            "id": str(row_id),
            "operation": operation_raw.strip().upper(),
            "name": name.strip(),
            "depth": depth,
            "rows": _parse_num(parts[3]) if len(parts) > 3 else None,
            "bytes": _parse_num(parts[4]) if len(parts) > 4 else None,
            "cost": _parse_cost(parts[5] if len(parts) > 5 else ""),
        }
    except (IndexError, ValueError):
        return None


def _parse_num(s: str) -> int | None:
    """Parse a number that may include K/M suffixes"""
    s = s.strip()
    if not s or s == "-":
        return None
    s = re.sub(r"\(.*?\)", "", s).strip()
    try:
        if s.endswith("K"):
            return int(float(s[:-1]) * 1000)
        if s.endswith("M"):
            return int(float(s[:-1]) * 1_000_000)
        return int(s.replace(",", ""))
    except ValueError:
        return None


def _parse_cost(s: str) -> int | None:
    """Parse cost field which may look like '1234 (10)'"""
    s = s.strip()
    m = re.match(r"(\d+)", s)
    if m:
        return int(m.group(1))
    return None


def extract_predicate_info(content: str) -> list[str]:
    """Extract Predicate Information section"""
    predicates = []
    pred_section = re.search(
        r"Predicate Information.*?(?=\n\n|\Z)", content, re.DOTALL | re.IGNORECASE
    )
    if pred_section:
        for line in pred_section.group(0).split("\n")[1:]:
            line = line.strip()
            if line and not line.startswith("-"):
                predicates.append(line)
    return predicates


def extract_notes(content: str) -> list[str]:
    """Extract Note section from plan"""
    notes = []
    note_section = re.search(
        r"^Note\s*\n-+\n(.*?)(?=\n\n|\Z)",
        content,
        re.DOTALL | re.MULTILINE | re.IGNORECASE,
    )
    if note_section:
        for line in note_section.group(1).split("\n"):
            line = line.strip()
            if line.startswith("-"):
                notes.append(line[1:].strip())
            elif line:
                notes.append(line)
    return notes


def parse_xplan_rows(rows: list[dict[str, object]]) -> list[PlanNode]:
    """Parse DBMS_XPLAN.DISPLAY* output from live DB query results.

    Each row is a dict with key 'plan_table_output' (case-insensitive).
    Returns plan nodes in the same format as parse_plan_table().
    """
    lines = []
    for r in rows:
        val = r.get("plan_table_output") or r.get("PLAN_TABLE_OUTPUT") or ""
        lines.append(str(val))
    content = "\n".join(lines)
    return parse_plan_table(content)


def extract_plan_stats(content: str) -> PlanStats:
    """Extract statistics if available (from GATHER_PLAN_STATISTICS)"""
    stats: PlanStats = {}
    # Look for execution stats at bottom
    elapsed_match = re.search(r"Elapsed:\s*([\d:\.]+)", content, re.IGNORECASE)
    if elapsed_match:
        stats["elapsed"] = elapsed_match.group(1)

    rows_match = re.search(r"(\d+)\s+rows\s+processed", content, re.IGNORECASE)
    if rows_match:
        stats["rows_processed"] = int(rows_match.group(1))

    return stats
