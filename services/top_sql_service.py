"""Top SQL service — AWR first, V$SQL fallback."""

import oracledb

from services.db_service import OracleConnection, OracleRow

_SORT_COLS = {
    "elapsed": "elapsed_total_sec",
    "cpu": "cpu_pct",
    "buffer_gets": "buffer_gets",
    "disk_reads": "disk_reads",
    "executions": "executions",
}
_HOURS = {"1h": 1, "6h": 6, "24h": 24, "7d": 168}

_AWR_SQL = """
SELECT s.sql_id,
       NVL(t.sql_text, s.sql_id) AS sql_text,
       ROUND(SUM(s.elapsed_time_delta) / 1e6, 2)        AS elapsed_total_sec,
       SUM(s.executions_delta)                           AS executions,
       CASE WHEN SUM(s.executions_delta) > 0
            THEN ROUND(SUM(s.elapsed_time_delta) /
                       SUM(s.executions_delta) / 1e6, 4)
            ELSE NULL END                                AS elapsed_per_exec_sec,
       ROUND(SUM(s.cpu_time_delta) /
             NULLIF(SUM(s.elapsed_time_delta), 0) * 100, 1) AS cpu_pct,
       SUM(s.buffer_gets_delta)                         AS buffer_gets,
       SUM(s.disk_reads_delta)                          AS disk_reads,
       MIN(s.module)                                    AS module
  FROM dba_hist_sqlstat s
  JOIN dba_hist_snapshot sn
    ON s.snap_id = sn.snap_id AND s.dbid = sn.dbid
  LEFT JOIN dba_hist_sqltext t
    ON s.sql_id = t.sql_id AND s.dbid = t.dbid
 WHERE sn.begin_interval_time >= SYSDATE - :hours / 24
   AND s.parsing_schema_id != 0
 GROUP BY s.sql_id, t.sql_text
 ORDER BY {sort_col} DESC NULLS LAST
 FETCH FIRST :limit ROWS ONLY
"""

_VSQL_SQL = """
SELECT sql_id,
       SUBSTR(sql_fulltext, 1, 4000)                    AS sql_text,
       ROUND(elapsed_time / 1e6, 2)                     AS elapsed_total_sec,
       executions,
       CASE WHEN executions > 0
            THEN ROUND(elapsed_time / executions / 1e6, 4)
            ELSE NULL END                               AS elapsed_per_exec_sec,
       ROUND(cpu_time / NULLIF(elapsed_time, 0) * 100, 1) AS cpu_pct,
       buffer_gets,
       disk_reads,
       module
  FROM v$sql
 WHERE executions > 0
   AND parsing_user_id != 0
 ORDER BY {sort_col} DESC NULLS LAST
 FETCH FIRST :limit ROWS ONLY
"""


def fetch_top_sql(
    conn: OracleConnection,
    sort_by: str = "elapsed",
    time_range: str = "24h",
    limit: int = 25,
) -> tuple[list[OracleRow], str]:
    """Return (rows, source) where source is 'awr' or 'vsql'."""
    sort_col = _SORT_COLS.get(sort_by, "elapsed_total_sec")
    hours = _HOURS.get(time_range, 24)
    try:
        rows = conn.execute_query(
            _AWR_SQL.format(sort_col=sort_col),
            {"hours": hours, "limit": limit},
        )
        return rows, "awr"
    except oracledb.Error:
        pass  # No AWR access (licensing/privileges) — fall back to V$SQL
    rows = conn.execute_query(
        _VSQL_SQL.format(sort_col=sort_col),
        {"limit": limit},
    )
    return rows, "vsql"
