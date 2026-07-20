"""Statistics health check service."""

from dataclasses import dataclass

import oracledb
from services.db_service import OracleConnection


@dataclass
class StatsFinding:
    check: str  # stale | missing | locked | partition | system
    severity: str  # critical | warning
    owner: str
    object_name: str
    object_type: str  # TABLE | INDEX | PARTITION | SYSTEM
    detail: str


def run_health_check(conn: OracleConnection, schemas: list[str]) -> list[StatsFinding]:
    """Run all stats checks for the given schemas. Empty list = all accessible schemas."""
    values = [s.strip().upper() for s in schemas if s.strip()]
    # One bind placeholder per schema name — never interpolate user input into SQL
    placeholders = ", ".join(f":s{i}" for i in range(len(values)))
    params = {f"s{i}": v for i, v in enumerate(values)}

    def schema_filter(column: str) -> str:
        # No schemas requested → match all accessible schemas (no owner filter).
        # The column name is a hardcoded literal, never user input.
        return f"{column} IN ({placeholders})" if values else "1 = 1"

    findings: list[StatsFinding] = []
    findings += _check_stale(conn, schema_filter("owner"), params)
    findings += _check_missing(conn, schema_filter("owner"), params)
    findings += _check_locked(conn, schema_filter("owner"), params)
    findings += _check_partitions(conn, schema_filter("table_owner"), params)
    findings += _check_system_stats(conn)
    return findings


def _check_stale(
    conn: OracleConnection, schema_pred: str, params: dict[str, str]
) -> list[StatsFinding]:
    sql = f"""
        SELECT owner, table_name, last_analyzed, stale_stats
          FROM dba_tab_statistics
         WHERE {schema_pred}
           AND (stale_stats = 'YES' OR last_analyzed < SYSDATE - 30
                OR last_analyzed IS NULL)
         ORDER BY last_analyzed ASC NULLS FIRST
    """
    try:
        rows = conn.execute_query(sql, params)
        return [
            StatsFinding(
                check="stale",
                severity="critical" if r.get("last_analyzed") is None else "warning",
                owner=r["owner"],
                object_name=r["table_name"],
                object_type="TABLE",
                detail=f"Last analyzed: {r.get('last_analyzed', 'NEVER')} | Stale: {r.get('stale_stats')}",
            )
            for r in rows
        ]
    except (oracledb.Error, RuntimeError) as e:
        return [
            StatsFinding(
                "stale", "warning", "", "", "", f"Could not check stale stats: {e}"
            )
        ]


def _check_missing(
    conn: OracleConnection, schema_pred: str, params: dict[str, str]
) -> list[StatsFinding]:
    sql = f"""
        SELECT owner, table_name, num_rows, last_analyzed
          FROM dba_tables
         WHERE {schema_pred}
           AND num_rows IS NULL
         ORDER BY owner, table_name
    """
    try:
        rows = conn.execute_query(sql, params)
        return [
            StatsFinding(
                check="missing",
                severity="critical",
                owner=r["owner"],
                object_name=r["table_name"],
                object_type="TABLE",
                detail="No statistics gathered (NUM_ROWS is NULL)",
            )
            for r in rows
        ]
    except (oracledb.Error, RuntimeError) as e:
        return [
            StatsFinding(
                "missing", "warning", "", "", "", f"Could not check missing stats: {e}"
            )
        ]


def _check_locked(
    conn: OracleConnection, schema_pred: str, params: dict[str, str]
) -> list[StatsFinding]:
    sql = f"""
        SELECT owner, table_name, stattype_locked
          FROM dba_tab_statistics
         WHERE {schema_pred}
           AND stattype_locked IS NOT NULL
         ORDER BY owner, table_name
    """
    try:
        rows = conn.execute_query(sql, params)
        return [
            StatsFinding(
                check="locked",
                severity="warning",
                owner=r["owner"],
                object_name=r["table_name"],
                object_type="TABLE",
                detail=f"Stats locked: {r.get('stattype_locked')}",
            )
            for r in rows
        ]
    except (oracledb.Error, RuntimeError) as e:
        return [
            StatsFinding(
                "locked", "warning", "", "", "", f"Could not check locked stats: {e}"
            )
        ]


def _check_partitions(
    conn: OracleConnection, schema_pred: str, params: dict[str, str]
) -> list[StatsFinding]:
    sql = f"""
        SELECT table_owner, table_name, partition_name, last_analyzed
          FROM dba_tab_partitions
         WHERE {schema_pred}
           AND last_analyzed IS NULL
         ORDER BY table_owner, table_name
    """
    try:
        rows = conn.execute_query(sql, params)
        return [
            StatsFinding(
                check="partition",
                severity="warning",
                owner=r["table_owner"],
                object_name=f"{r['table_name']}.{r['partition_name']}",
                object_type="PARTITION",
                detail="Partition has no statistics",
            )
            for r in rows
        ]
    except (oracledb.Error, RuntimeError) as e:
        return [
            StatsFinding(
                "partition",
                "warning",
                "",
                "",
                "",
                f"Could not check partition stats: {e}",
            )
        ]


def _check_system_stats(conn: OracleConnection) -> list[StatsFinding]:
    sql = "SELECT pname, pval1, pval2 FROM sys.aux_stats$"
    try:
        rows = conn.execute_query(sql)
        has_cpu = any(r.get("pname") == "CPUSPEED" and r.get("pval1") for r in rows)
        if not has_cpu:
            return [
                StatsFinding(
                    check="system",
                    severity="warning",
                    owner="SYS",
                    object_name="AUX_STATS$",
                    object_type="SYSTEM",
                    detail="System statistics not gathered. Run DBMS_STATS.GATHER_SYSTEM_STATS.",
                )
            ]
        return []
    except (oracledb.Error, RuntimeError) as e:
        return [
            StatsFinding(
                "system", "warning", "", "", "", f"Could not check system stats: {e}"
            )
        ]
