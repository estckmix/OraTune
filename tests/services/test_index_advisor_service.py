from unittest.mock import MagicMock
from services.index_advisor_service import (
    fetch_unused_indexes,
    fetch_missing_index_candidates,
)

_UNUSED_ROW = {
    "owner": "MYAPP",
    "index_name": "IDX_ORDERS_STATUS",
    "table_name": "ORDERS",
    "index_type": "NORMAL",
    "uniqueness": "NONUNIQUE",
    "last_used": None,
    "total_access_count": 0,
}

_MISSING_ROW = {
    "schema_name": "MYAPP",
    "table_name": "ORDERS",
    "num_rows": 500_000,
    "sql_id": "abc123",
    "elapsed_total_sec": 45.7,
    "filter_predicates": '"MYAPP"."ORDERS"."STATUS"=:1',
}


def test_fetch_unused_indexes_happy_path() -> None:
    conn = MagicMock()
    conn.execute_query.return_value = [_UNUSED_ROW, _UNUSED_ROW]
    rows = fetch_unused_indexes(conn, days=30)
    assert len(rows) == 2
    assert rows[0]["index_name"] == "IDX_ORDERS_STATUS"
    assert conn.execute_query.call_args[0][1]["days"] == 30


def test_fetch_unused_indexes_empty() -> None:
    conn = MagicMock()
    conn.execute_query.return_value = []
    assert fetch_unused_indexes(conn) == []


def test_fetch_missing_index_candidates_happy_path() -> None:
    conn = MagicMock()
    conn.execute_query.return_value = [_MISSING_ROW, _MISSING_ROW]
    rows = fetch_missing_index_candidates(conn, min_rows=10_000, limit=25)
    assert len(rows) == 2
    assert rows[0]["table_name"] == "ORDERS"
    params = conn.execute_query.call_args[0][1]
    assert params["min_rows"] == 10_000
    assert params["limit"] == 25


def test_fetch_missing_index_candidates_empty() -> None:
    conn = MagicMock()
    conn.execute_query.return_value = []
    assert fetch_missing_index_candidates(conn) == []
