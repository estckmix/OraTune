"""SQL / PLSQL Parser"""

import re

from core.models import IndexHintRef, ParsedSql


def parse_sql_file(filepath: str) -> ParsedSql:
    """Parse a SQL or PLSQL file and return structured info"""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        return {"error": str(e), "content": "", "filepath": filepath}

    return {
        "filepath": filepath,
        "content": content,
        "statements": extract_statements(content),
        "hints": extract_hints(content),
        "indexes_referenced": extract_index_hints(content),
        "tables": extract_tables(content),
        "joins": extract_joins(content),
        "predicates": extract_predicates(content),
    }


def extract_statements(content: str) -> list[str]:
    """Split content into individual SQL statements"""
    # Split on semicolons but be smart about PL/SQL blocks
    statements = []
    current = []
    in_block = False
    block_depth = 0

    for line in content.split("\n"):
        stripped = line.strip().upper()

        if re.match(r"\b(BEGIN|DECLARE)\b", stripped):
            in_block = True
            block_depth += 1
        if re.match(r"\bEND\b", stripped):
            block_depth = max(0, block_depth - 1)
            if block_depth == 0:
                in_block = False

        current.append(line)

        if not in_block and ";" in line:
            stmt = "\n".join(current).strip()
            if stmt.replace(";", "").strip():
                statements.append(stmt)
            current = []

    if current:
        stmt = "\n".join(current).strip()
        if stmt.replace(";", "").strip():
            statements.append(stmt)

    return statements


def extract_hints(content: str) -> list[str]:
    """Extract Oracle optimizer hints /*+ ... */"""
    pattern = r"/\*\+(.*?)\*/"
    hints = re.findall(pattern, content, re.DOTALL)
    return [h.strip() for h in hints]


def extract_index_hints(content: str) -> list[IndexHintRef]:
    """Extract index references from hints and queries"""
    indexes: list[IndexHintRef] = []
    # From hints: INDEX(table index_name), NO_INDEX, INDEX_FFS
    hint_pattern = r"\b(?:INDEX|NO_INDEX|INDEX_FFS|INDEX_SS)\s*\(\s*(\w+)\s+(\w+)\s*\)"
    for m in re.finditer(hint_pattern, content, re.IGNORECASE):
        indexes.append({"table": m.group(1), "index": m.group(2), "source": "hint"})
    return indexes


def extract_tables(content: str) -> list[str]:
    """Extract table names from FROM and JOIN clauses"""
    tables = set()
    # FROM table_name [alias]
    pattern = r"\bFROM\s+([\w.]+)(?:\s+(?:AS\s+)?(\w+))?"
    for m in re.finditer(pattern, content, re.IGNORECASE):
        tables.add(m.group(1).upper())
    # JOIN table_name
    pattern2 = r"\bJOIN\s+([\w.]+)"
    for m in re.finditer(pattern2, content, re.IGNORECASE):
        tables.add(m.group(1).upper())
    return sorted(tables)


def extract_joins(content: str) -> list[str]:
    """Extract join types used"""
    join_types = []
    pattern = r"\b((?:LEFT|RIGHT|FULL|CROSS|INNER|OUTER)\s+(?:OUTER\s+)?JOIN|JOIN)\b"
    for m in re.finditer(pattern, content, re.IGNORECASE):
        join_types.append(m.group(1).upper().strip())
    return join_types


def extract_predicates(content: str) -> list[str]:
    """Extract WHERE clause predicates (simplified)"""
    predicates = []
    where_match = re.search(
        r"\bWHERE\b(.+?)(?:\bGROUP\b|\bORDER\b|\bHAVING\b|$)",
        content,
        re.IGNORECASE | re.DOTALL,
    )
    if where_match:
        where_clause = where_match.group(1)
        # Split on AND/OR
        parts = re.split(r"\bAND\b|\bOR\b", where_clause, flags=re.IGNORECASE)
        for p in parts:
            p = p.strip()
            if p and len(p) < 200:
                predicates.append(p)
    return predicates
