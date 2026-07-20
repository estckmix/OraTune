"""Index Advisor service — unused indexes and missing index candidates."""

from services.db_service import OracleConnection, OracleRow

_UNUSED_SQL = """
SELECT i.owner,
       i.index_name,
       i.table_name,
       i.index_type,
       i.uniqueness,
       u.last_used,
       COALESCE(u.total_access_count, 0) AS total_access_count
  FROM dba_indexes i
  LEFT JOIN dba_index_usage u
    ON u.owner = i.owner
   AND u.name  = i.index_name
 WHERE (u.last_used IS NULL OR u.last_used < SYSDATE - :days)
   AND i.owner NOT IN ('SYS','SYSTEM','DBSNMP','OUTLN','MDSYS',
                       'XDB','CTXSYS','WMSYS','ORDSYS','OLAPSYS')
 ORDER BY u.last_used NULLS FIRST, i.owner, i.index_name
"""

_MISSING_SQL = """
SELECT p.object_owner                              AS schema_name,
       p.object_name                               AS table_name,
       t.num_rows,
       p.sql_id,
       ROUND(SUM(s.elapsed_time_delta) / 1e6, 2)  AS elapsed_total_sec,
       MIN(p.filter_predicates)                    AS filter_predicates
  FROM dba_hist_sql_plan p
  JOIN dba_hist_sqlstat s
    ON s.sql_id          = p.sql_id
   AND s.plan_hash_value = p.plan_hash_value
   AND s.dbid            = p.dbid
  JOIN dba_tables t
    ON t.owner      = p.object_owner
   AND t.table_name = p.object_name
 WHERE p.operation  = 'TABLE ACCESS'
   AND p.options    = 'FULL'
   AND p.dbid       = (SELECT dbid FROM v$database)
   AND p.object_owner NOT IN ('SYS','SYSTEM','DBSNMP','OUTLN','MDSYS',
                               'XDB','CTXSYS','WMSYS','ORDSYS','OLAPSYS')
   AND COALESCE(t.num_rows, 0) >= :min_rows
 GROUP BY p.object_owner, p.object_name, t.num_rows, p.sql_id
 ORDER BY elapsed_total_sec DESC NULLS LAST
 FETCH FIRST :limit ROWS ONLY
"""


def fetch_unused_indexes(conn: OracleConnection, days: int = 30) -> list[OracleRow]:
    """Return indexes not accessed within the last `days` days."""
    return conn.execute_query(_UNUSED_SQL, {"days": days})


def fetch_missing_index_candidates(
    conn: OracleConnection,
    min_rows: int = 10_000,
    limit: int = 25,
) -> list[OracleRow]:
    """Return large tables with full scans in AWR, ranked by elapsed time."""
    return conn.execute_query(_MISSING_SQL, {"min_rows": min_rows, "limit": limit})
