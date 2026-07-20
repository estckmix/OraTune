"""Tests for core/diff_engine.py"""

from core.diff_engine import compare_sql_files
from core.models import DiffResult, ParsedSql

_BASELINE: ParsedSql = {
    "filepath": "baseline.sql",
    "content": "SELECT /*+ INDEX(o IDX_ORDERS) */ *\nFROM orders o\nWHERE o.cust_id = :b1",
    "hints": ["INDEX(o IDX_ORDERS)"],
    "tables": ["orders"],
    "joins": [],
    "indexes_referenced": [{"table": "o", "index": "IDX_ORDERS", "source": "hint"}],
}

_CURRENT: ParsedSql = {
    "filepath": "current.sql",
    "content": "SELECT *\nFROM orders o\nWHERE o.cust_id = :b1",
    "hints": [],
    "tables": ["orders"],
    "joins": [],
    "indexes_referenced": [],
}

_IDENTICAL: ParsedSql = {
    "filepath": "same.sql",
    "content": "SELECT 1 FROM dual",
    "hints": [],
    "tables": ["dual"],
    "joins": [],
    "indexes_referenced": [],
}


def test_returns_list_of_diff_results() -> None:
    results = compare_sql_files({"sql": [_BASELINE]}, {"sql": [_CURRENT]})
    assert isinstance(results, list)
    assert len(results) == 1
    assert isinstance(results[0], DiffResult)


def test_diff_result_label_includes_filenames() -> None:
    results = compare_sql_files({"sql": [_BASELINE]}, {"sql": [_CURRENT]})
    assert "baseline.sql" in results[0].label
    assert "current.sql" in results[0].label


def test_removed_hint_detected() -> None:
    results = compare_sql_files({"sql": [_BASELINE]}, {"sql": [_CURRENT]})
    types = [c["type"] for c in results[0].structural_changes]
    assert "HINT_REMOVED" in types


def test_identical_files_similarity_100() -> None:
    results = compare_sql_files({"sql": [_IDENTICAL]}, {"sql": [_IDENTICAL]})
    assert results[0].stats["similarity_ratio"] == 100.0


def test_empty_inputs_returns_empty_list() -> None:
    results = compare_sql_files({}, {})
    assert results == []


def test_stats_keys_present() -> None:
    results = compare_sql_files({"sql": [_BASELINE]}, {"sql": [_CURRENT]})
    stats = results[0].stats
    for key in ("lines_added", "lines_removed", "lines_changed", "similarity_ratio"):
        assert key in stats
