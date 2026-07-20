"""AWR Trend service — time-series per-exec metrics for a single SQL ID."""

from datetime import datetime

from services.db_service import OracleConnection, OracleRow

_SQL = """
SELECT s.end_interval_time,
       h.elapsed_time_delta,
       h.cpu_time_delta,
       h.buffer_gets_delta,
       h.disk_reads_delta,
       h.executions_delta
  FROM dba_hist_sqlstat h
  JOIN dba_hist_snapshot s
    ON h.snap_id         = s.snap_id
   AND h.dbid            = s.dbid
   AND h.instance_number = s.instance_number
 WHERE h.sql_id = :sql_id
   AND h.dbid   = (SELECT dbid FROM v$database)
   AND s.end_interval_time BETWEEN :start_time AND :end_time
   AND h.executions_delta > 0
 ORDER BY s.end_interval_time
"""


def fetch_awr_trend(
    conn: OracleConnection,
    sql_id: str,
    start_time: datetime,
    end_time: datetime,
) -> list[OracleRow]:
    """Return one dict per AWR snapshot with per-exec metrics computed."""
    rows = conn.execute_query(
        _SQL,
        {"sql_id": sql_id, "start_time": start_time, "end_time": end_time},
    )
    result = []
    for r in rows:
        execs = r["executions_delta"]
        result.append(
            {
                "snap_time": r["end_interval_time"],
                "elapsed_ms_per_exec": r["elapsed_time_delta"] / execs / 1000,
                "cpu_ms_per_exec": r["cpu_time_delta"] / execs / 1000,
                "buffer_gets_per_exec": r["buffer_gets_delta"] / execs,
                "disk_reads_per_exec": r["disk_reads_delta"] / execs,
                "executions": execs,
            }
        )
    return result
