"""SQL Plan Baseline service — wraps DBMS_SPM."""

from services.db_service import OracleConnection, OracleRow

_LIST_SQL = """
SELECT sql_handle,
       plan_name,
       SUBSTR(sql_text, 1, 200) AS sql_text,
       enabled,
       accepted,
       fixed,
       origin,
       created,
       last_modified
  FROM dba_sql_plan_baselines
 ORDER BY created DESC
"""


def list_baselines(conn: OracleConnection) -> list[OracleRow]:
    return conn.execute_query(_LIST_SQL)


def alter_baseline(
    conn: OracleConnection,
    sql_handle: str,
    plan_name: str,
    attribute: str,
    value: str,
) -> int:
    rows = conn.execute_query(
        "SELECT DBMS_SPM.ALTER_SQL_PLAN_BASELINE("
        "  sql_handle => :handle, plan_name => :plan,"
        "  attribute => :attr, value => :val) AS cnt FROM dual",
        {"handle": sql_handle, "plan": plan_name, "attr": attribute, "val": value},
    )
    return rows[0]["cnt"] if rows else 0


def drop_baseline(conn: OracleConnection, sql_handle: str, plan_name: str) -> int:
    rows = conn.execute_query(
        "SELECT DBMS_SPM.DROP_SQL_PLAN_BASELINE("
        "  sql_handle => :handle, plan_name => :plan) AS cnt FROM dual",
        {"handle": sql_handle, "plan": plan_name},
    )
    return rows[0]["cnt"] if rows else 0


def promote_from_cursor(conn: OracleConnection, sql_id: str) -> int:
    rows = conn.execute_query(
        "SELECT DBMS_SPM.LOAD_PLANS_FROM_CURSOR_CACHE(sql_id => :sql_id) AS cnt FROM dual",
        {"sql_id": sql_id},
    )
    return rows[0]["cnt"] if rows else 0
