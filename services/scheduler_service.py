"""DBMS_SCHEDULER monitoring service."""

from services.db_service import OracleConnection, OracleRow

_JOBS_SQL = """
SELECT owner, job_name, job_type, state,
       last_start_date, next_run_date, failure_count, enabled
  FROM dba_scheduler_jobs
 ORDER BY owner, job_name
"""

_HISTORY_SQL = """
SELECT owner, job_name, status, actual_start_date,
       run_duration, "ERROR#" AS error_code, additional_info AS error_message
  FROM dba_scheduler_job_run_details
 WHERE (:job_name IS NULL OR job_name = :job_name)
   AND (:status IS NULL OR status = :status)
 ORDER BY actual_start_date DESC
 FETCH FIRST :limit ROWS ONLY
"""

_PROGRAMS_SQL = """
SELECT owner, program_name, program_type, enabled
  FROM dba_scheduler_programs
 ORDER BY owner, program_name
"""

_SCHEDULES_SQL = """
SELECT owner, schedule_name, repeat_interval, start_date, end_date
  FROM dba_scheduler_schedules
 ORDER BY owner, schedule_name
"""


def list_jobs(conn: OracleConnection) -> list[OracleRow]:
    return conn.execute_query(_JOBS_SQL)


def list_run_history(
    conn: OracleConnection,
    job_name: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[OracleRow]:
    return conn.execute_query(
        _HISTORY_SQL,
        {
            "job_name": job_name,
            "status": status,
            "limit": limit,
        },
    )


def run_job(conn: OracleConnection, owner: str, job_name: str) -> None:
    conn.execute_ddl(
        "BEGIN DBMS_SCHEDULER.RUN_JOB(job_name => :job, use_current_session => FALSE); END;",
        {"job": f"{owner}.{job_name}"},
    )


def stop_job(conn: OracleConnection, owner: str, job_name: str) -> None:
    conn.execute_ddl(
        "BEGIN DBMS_SCHEDULER.STOP_JOB(job_name => :job, force => FALSE); END;",
        {"job": f"{owner}.{job_name}"},
    )


def toggle_job(conn: OracleConnection, owner: str, job_name: str, enable: bool) -> None:
    proc = "ENABLE" if enable else "DISABLE"
    conn.execute_ddl(
        f"BEGIN DBMS_SCHEDULER.{proc}(name => :job); END;",
        {"job": f"{owner}.{job_name}"},
    )


def list_programs(conn: OracleConnection) -> list[OracleRow]:
    return conn.execute_query(_PROGRAMS_SQL)


def list_schedules(conn: OracleConnection) -> list[OracleRow]:
    return conn.execute_query(_SCHEDULES_SQL)
