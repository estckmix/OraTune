from unittest.mock import MagicMock

import oracledb

from services.top_sql_service import fetch_top_sql

_ROW = {
    "sql_id": "abc12345",
    "sql_text": "SELECT 1 FROM dual",
    "elapsed_total_sec": 10.5,
    "executions": 100,
    "elapsed_per_exec_sec": 0.105,
    "cpu_pct": 80.0,
    "buffer_gets": 5000,
    "disk_reads": 10,
    "module": "JDBC",
}


def test_fetch_top_sql_returns_awr_first() -> None:
    conn = MagicMock()
    conn.execute_query.return_value = [_ROW]
    rows, source = fetch_top_sql(conn)
    assert source == "awr"
    assert rows == [_ROW]


def test_fetch_top_sql_falls_back_to_vsql() -> None:
    conn = MagicMock()
    conn.execute_query.side_effect = [
        oracledb.Error("ORA-00942: table does not exist"),
        [_ROW],
    ]
    rows, source = fetch_top_sql(conn)
    assert source == "vsql"
    assert rows == [_ROW]


def test_fetch_top_sql_passes_limit() -> None:
    conn = MagicMock()
    conn.execute_query.return_value = []
    fetch_top_sql(conn, limit=50)
    params = conn.execute_query.call_args[0][1]
    assert params["limit"] == 50


def test_fetch_top_sql_time_range_maps_to_hours() -> None:
    conn = MagicMock()
    conn.execute_query.return_value = []
    fetch_top_sql(conn, time_range="7d")
    params = conn.execute_query.call_args[0][1]
    assert params["hours"] == 168


def test_fetch_top_sql_unknown_sort_defaults_to_elapsed() -> None:
    conn = MagicMock()
    conn.execute_query.return_value = []
    rows, source = fetch_top_sql(conn, sort_by="INVALID")
    assert source == "awr"
