import oracledb
from unittest.mock import MagicMock
from services.stats_service import run_health_check


def _conn(*side_effects: object) -> MagicMock:
    """Return a mock conn whose execute_query calls return values in order."""
    c = MagicMock()
    c.execute_query.side_effect = list(side_effects)
    return c


def _empty_conn() -> MagicMock:
    return _conn([], [], [], [], [])


def test_returns_list() -> None:
    findings = run_health_check(_empty_conn(), ["HR"])
    assert isinstance(findings, list)


def test_stale_stats_detected() -> None:
    stale_row = {
        "owner": "HR",
        "table_name": "EMPLOYEES",
        "last_analyzed": None,
        "stale_stats": "YES",
    }
    conn = _conn([stale_row], [], [], [], [])
    findings = run_health_check(conn, ["HR"])
    stale = [f for f in findings if f.check == "stale"]
    assert len(stale) == 1
    assert stale[0].severity == "critical"
    assert stale[0].owner == "HR"
    assert stale[0].object_name == "EMPLOYEES"


def test_missing_stats_detected() -> None:
    missing_row = {
        "owner": "HR",
        "table_name": "JOBS",
        "num_rows": None,
        "last_analyzed": None,
    }
    conn = _conn([], [missing_row], [], [], [])
    findings = run_health_check(conn, ["HR"])
    missing = [f for f in findings if f.check == "missing"]
    assert len(missing) == 1
    assert missing[0].severity == "critical"


def test_locked_stats_detected() -> None:
    locked_row = {"owner": "HR", "table_name": "DEPTS", "stattype_locked": "ALL"}
    conn = _conn([], [], [locked_row], [], [])
    findings = run_health_check(conn, ["HR"])
    locked = [f for f in findings if f.check == "locked"]
    assert len(locked) == 1
    assert locked[0].severity == "warning"


def test_system_stats_not_gathered() -> None:
    sys_row = {"pname": "SREADTIM", "pval1": None, "pval2": None}
    conn = _conn([], [], [], [], [sys_row])
    findings = run_health_check(conn, ["HR"])
    sys_f = [f for f in findings if f.check == "system"]
    assert len(sys_f) == 1
    assert "DBMS_STATS" in sys_f[0].detail


def test_empty_schemas_drops_owner_filter() -> None:
    conn = _conn([], [], [], [], [])
    run_health_check(conn, [])
    sql, params = conn.execute_query.call_args_list[0][0]
    assert "1 = 1" in sql
    assert "IN (" not in sql
    assert params == {}


def test_named_schemas_bind_each_value() -> None:
    conn = _conn([], [], [], [], [])
    run_health_check(conn, ["HR", "SALES"])
    sql, params = conn.execute_query.call_args_list[0][0]
    assert "owner IN (:s0, :s1)" in sql
    assert params == {"s0": "HR", "s1": "SALES"}


def test_query_error_produces_warning_finding() -> None:
    conn = MagicMock()
    conn.execute_query.side_effect = oracledb.DatabaseError("ORA-00942")
    findings = run_health_check(conn, ["HR"])
    assert len(findings) > 0
    assert all(f.severity in ("warning", "critical") for f in findings)
