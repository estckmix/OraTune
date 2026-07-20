from unittest.mock import MagicMock
from services.scheduler_service import (
    list_jobs,
    list_run_history,
    run_job,
    stop_job,
    toggle_job,
)

_JOB = {
    "owner": "SYS",
    "job_name": "GATHER_STATS_JOB",
    "job_type": "PLSQL_BLOCK",
    "state": "SCHEDULED",
    "last_start_date": None,
    "next_run_date": "2026-05-10",
    "failure_count": 0,
    "enabled": "TRUE",
}


def test_list_jobs_returns_rows() -> None:
    conn = MagicMock()
    conn.execute_query.return_value = [_JOB]
    assert list_jobs(conn) == [_JOB]


def test_list_run_history_passes_filters() -> None:
    conn = MagicMock()
    conn.execute_query.return_value = []
    list_run_history(conn, job_name="MY_JOB", status="FAILED", limit=50)
    params = conn.execute_query.call_args[0][1]
    assert params["job_name"] == "MY_JOB"
    assert params["status"] == "FAILED"
    assert params["limit"] == 50


def test_run_job_calls_dbms_scheduler() -> None:
    conn = MagicMock()
    run_job(conn, "SYS", "MY_JOB")
    sql = conn.execute_ddl.call_args[0][0]
    assert "DBMS_SCHEDULER.RUN_JOB" in sql
    params = conn.execute_ddl.call_args[0][1]
    assert "SYS.MY_JOB" in params["job"]


def test_stop_job_calls_stop() -> None:
    conn = MagicMock()
    stop_job(conn, "HR", "SYNC_JOB")
    sql = conn.execute_ddl.call_args[0][0]
    assert "STOP_JOB" in sql


def test_toggle_job_enable() -> None:
    conn = MagicMock()
    toggle_job(conn, "HR", "SYNC_JOB", enable=True)
    sql = conn.execute_ddl.call_args[0][0]
    assert "ENABLE" in sql
    assert "DISABLE" not in sql


def test_toggle_job_disable() -> None:
    conn = MagicMock()
    toggle_job(conn, "HR", "SYNC_JOB", enable=False)
    sql = conn.execute_ddl.call_args[0][0]
    assert "DISABLE" in sql
