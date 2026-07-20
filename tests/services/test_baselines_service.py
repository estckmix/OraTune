from unittest.mock import MagicMock
from services.baselines_service import (
    list_baselines,
    alter_baseline,
    drop_baseline,
    promote_from_cursor,
)

_ROW = {
    "sql_handle": "SYS_SQL_abc",
    "plan_name": "SQL_PLAN_abc_1",
    "sql_text": "SELECT 1 FROM dual",
    "enabled": "YES",
    "accepted": "YES",
    "fixed": "NO",
    "origin": "MANUAL-LOAD",
    "created": "2026-01-01",
    "last_modified": "2026-01-01",
}


def test_list_baselines_returns_rows() -> None:
    conn = MagicMock()
    conn.execute_query.return_value = [_ROW]
    assert list_baselines(conn) == [_ROW]


def test_alter_baseline_calls_dbms_spm() -> None:
    conn = MagicMock()
    conn.execute_query.return_value = [{"cnt": 1}]
    result = alter_baseline(conn, "SYS_SQL_abc", "SQL_PLAN_1", "enabled", "NO")
    assert result == 1
    sql = conn.execute_query.call_args[0][0]
    assert "DBMS_SPM.ALTER_SQL_PLAN_BASELINE" in sql


def test_drop_baseline_returns_count() -> None:
    conn = MagicMock()
    conn.execute_query.return_value = [{"cnt": 1}]
    result = drop_baseline(conn, "SYS_SQL_abc", "SQL_PLAN_1")
    assert result == 1
    sql = conn.execute_query.call_args[0][0]
    assert "DROP_SQL_PLAN_BASELINE" in sql


def test_promote_from_cursor_returns_count() -> None:
    conn = MagicMock()
    conn.execute_query.return_value = [{"cnt": 2}]
    result = promote_from_cursor(conn, "abc12345")
    assert result == 2
    sql = conn.execute_query.call_args[0][0]
    assert "LOAD_PLANS_FROM_CURSOR_CACHE" in sql


def test_alter_baseline_returns_zero_on_empty() -> None:
    conn = MagicMock()
    conn.execute_query.return_value = []
    assert alter_baseline(conn, "h", "p", "enabled", "YES") == 0
