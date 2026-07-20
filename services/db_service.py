"""Oracle DB connection service — wraps python-oracledb. No PyQt6 here."""

from typing import Any

import oracledb

from core.models import ConnectionProfile

# A fetched row: column values are whatever the driver returns (str, int,
# float, datetime, LOB-read str, None) — genuinely dynamic, hence Any.
# Bind params are equally driver-dynamic in the other direction.
OracleRow = dict[str, Any]

# Use thick mode when Oracle Client is available — avoids the Python
# cryptography package dependency and respects server-side sqlnet.ora settings.
try:
    oracledb.init_oracle_client()
except oracledb.Error:
    pass  # Oracle Client not installed; thin mode will be used instead


class OracleConnection:
    def __init__(self) -> None:
        self._conn: oracledb.Connection | None = None
        self._profile: ConnectionProfile | None = None

    def connect(self, profile: ConnectionProfile) -> None:
        """Connect using profile. Raises on failure."""
        self._profile = profile
        dsn = (
            f"{profile.host}:{profile.port}/{profile.service}"
            if profile.connection_type == "direct"
            else profile.alias
        )
        self._conn = oracledb.connect(
            user=profile.username, password=profile.password, dsn=dsn
        )

    def test_connection(self, profile: ConnectionProfile) -> tuple[bool, str]:
        """Test credentials without changing current connection state."""
        try:
            dsn = (
                f"{profile.host}:{profile.port}/{profile.service}"
                if profile.connection_type == "direct"
                else profile.alias
            )
            c = oracledb.connect(
                user=profile.username, password=profile.password, dsn=dsn
            )
            c.close()
            return True, "Connection successful"
        except oracledb.Error as e:
            return False, str(e)

    def execute_query(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> list[OracleRow]:
        """Run a SELECT and return rows as list of dicts (lowercase column names)."""
        if self._conn is None:
            raise RuntimeError("Not connected")
        with self._conn.cursor() as cur:
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            cols = [d[0].lower() for d in cur.description]
            result: list[OracleRow] = []
            for row in cur.fetchall():
                result.append(
                    {
                        c: (v.read() if isinstance(v, oracledb.LOB) else v)
                        for c, v in zip(cols, row)
                    }
                )
            return result

    def execute_for_plan(self, sql: str) -> None:
        """Execute a SELECT with gather_plan_statistics; fetches one row to activate cursor stats."""
        if self._conn is None:
            raise RuntimeError("Not connected")
        with self._conn.cursor() as cur:
            cur.execute(sql)
            cur.fetchone()

    def execute_ddl(self, sql: str, params: dict[str, Any] | None = None) -> None:
        """Run a PL/SQL block or DDL (non-SELECT)."""
        if self._conn is None:
            raise RuntimeError("Not connected")
        with self._conn.cursor() as cur:
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
        self._conn.commit()

    def get_db_version(self) -> str:
        rows = self.execute_query("SELECT banner FROM v$version WHERE ROWNUM = 1")
        return rows[0].get("banner", "Unknown") if rows else "Unknown"

    @property
    def is_connected(self) -> bool:
        if self._conn is None:
            return False
        try:
            self._conn.ping()
            return True
        except oracledb.Error:
            return False

    def disconnect(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except oracledb.Error:
                pass  # already closed or connection lost — disconnect is best-effort
            self._conn = None
            self._profile = None

    @property
    def profile(self) -> ConnectionProfile | None:
        return self._profile
