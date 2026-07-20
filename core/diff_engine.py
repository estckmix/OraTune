"""SQL Diff Engine — returns typed DiffResult models."""

import difflib
from pathlib import Path

from core.models import DiffResult, ParsedSql, StructuralChange


def compare_sql_files(
    baseline_files: dict[str, list[ParsedSql]],
    current_files: dict[str, list[ParsedSql]],
) -> list[DiffResult]:
    """
    Compare paired SQL files from baseline_files and current_files dicts.
    baseline_files / current_files: {"sql": [parsed_dict, ...], ...}
    Pairing: by filename first, then by position.
    Returns list[DiffResult].
    """
    b_list = baseline_files.get("sql", [])
    c_list = current_files.get("sql", [])
    pairs = _pair(b_list, c_list)
    return [_diff_pair(b, c) for b, c in pairs]


def _pair(
    b_list: list[ParsedSql], c_list: list[ParsedSql]
) -> list[tuple[ParsedSql, ParsedSql]]:
    if not b_list or not c_list:
        return []
    if len(b_list) == 1 and len(c_list) == 1:
        return [(b_list[0], c_list[0])]

    b_by_name = {Path(p.get("filepath", "")).name: p for p in b_list}
    c_by_name = {Path(p.get("filepath", "")).name: p for p in c_list}

    pairs: list[tuple[ParsedSql, ParsedSql]] = []
    matched: set[str] = set()
    for name, b in b_by_name.items():
        if name in c_by_name:
            pairs.append((b, c_by_name[name]))
            matched.add(name)

    b_unmatched = [p for p in b_list if Path(p.get("filepath", "")).name not in matched]
    c_unmatched = [p for p in c_list if Path(p.get("filepath", "")).name not in matched]
    pairs.extend(zip(b_unmatched, c_unmatched))
    return pairs


def _diff_pair(b_parsed: ParsedSql, c_parsed: ParsedSql) -> DiffResult:
    b_text = b_parsed.get("content", "")
    c_text = c_parsed.get("content", "")
    b_lines = b_text.splitlines()
    c_lines = c_text.splitlines()

    matcher = difflib.SequenceMatcher(None, b_lines, c_lines, autojunk=False)

    b_diff: dict[int, str] = {}
    c_diff: dict[int, str] = {}
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "delete":
            for ln in range(i1 + 1, i2 + 1):
                b_diff[ln] = "remove"
        elif op == "insert":
            for ln in range(j1 + 1, j2 + 1):
                c_diff[ln] = "add"
        elif op == "replace":
            for ln in range(i1 + 1, i2 + 1):
                b_diff[ln] = "change"
            for ln in range(j1 + 1, j2 + 1):
                c_diff[ln] = "change"

    b_path = b_parsed.get("filepath", "baseline")
    c_path = c_parsed.get("filepath", "current")

    added = sum(1 for t in c_diff.values() if t == "add")
    removed = sum(1 for t in b_diff.values() if t == "remove")
    changed = sum(1 for t in b_diff.values() if t == "change")

    return DiffResult(
        label=f"{Path(b_path).name}  vs  {Path(c_path).name}",
        baseline_text=b_text,
        current_text=c_text,
        baseline_diff_lines=b_diff,
        current_diff_lines=c_diff,
        structural_changes=_structural_changes(b_parsed, c_parsed),
        stats={
            "lines_added": added,
            "lines_removed": removed,
            "lines_changed": changed,
            "baseline_total_lines": len(b_lines),
            "current_total_lines": len(c_lines),
            "similarity_ratio": round(matcher.ratio() * 100, 1),
        },
    )


def _structural_changes(b: ParsedSql, c: ParsedSql) -> list[StructuralChange]:
    changes: list[StructuralChange] = []
    b_hints = set(b.get("hints", []))
    c_hints = set(c.get("hints", []))
    for h in b_hints - c_hints:
        changes.append({"type": "HINT_REMOVED", "detail": h})
    for h in c_hints - b_hints:
        changes.append({"type": "HINT_ADDED", "detail": h})

    b_tables = set(b.get("tables", []))
    c_tables = set(c.get("tables", []))
    for t in c_tables - b_tables:
        changes.append({"type": "TABLE_ADDED", "detail": t})
    for t in b_tables - c_tables:
        changes.append({"type": "TABLE_REMOVED", "detail": t})

    b_joins = sorted(b.get("joins", []))
    c_joins = sorted(c.get("joins", []))
    if b_joins != c_joins:
        changes.append(
            {
                "type": "JOIN_CHANGE",
                "detail": f"Baseline: {b_joins} -> Current: {c_joins}",
            }
        )

    b_idx = {f"{i['table']}.{i['index']}" for i in b.get("indexes_referenced", [])}
    c_idx = {f"{i['table']}.{i['index']}" for i in c.get("indexes_referenced", [])}
    for i in b_idx - c_idx:
        changes.append({"type": "INDEX_HINT_REMOVED", "detail": i})
    for i in c_idx - b_idx:
        changes.append({"type": "INDEX_HINT_ADDED", "detail": i})

    return changes
