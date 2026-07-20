import oracledb
import pytest
from unittest.mock import MagicMock, patch
from core.models import ConnectionProfile
from services.db_service import OracleConnection


def _direct() -> ConnectionProfile:
    return ConnectionProfile(
        name="test",
        connection_type="direct",
        host="localhost",
        port=1521,
        service="XE",
        username="scott",
        password="tiger",
    )


def _tns() -> ConnectionProfile:
    return ConnectionProfile(
        name="prod",
        connection_type="tns",
        alias="PRODDB",
        username="scott",
        password="tiger",
    )


def test_connect_direct_uses_host_port_service() -> None:
    conn = OracleConnection()
    with patch("services.db_service.oracledb.connect") as mock_connect:
        mock_connect.return_value = MagicMock()
        conn.connect(_direct())
        mock_connect.assert_called_once_with(
            user="scott", password="tiger", dsn="localhost:1521/XE"
        )


def test_connect_tns_uses_alias() -> None:
    conn = OracleConnection()
    with patch("services.db_service.oracledb.connect") as mock_connect:
        mock_connect.return_value = MagicMock()
        conn.connect(_tns())
        mock_connect.assert_called_once_with(
            user="scott", password="tiger", dsn="PRODDB"
        )


def test_execute_query_returns_list_of_dicts() -> None:
    conn = OracleConnection()
    mock_raw = MagicMock()
    mock_cur = MagicMock()
    mock_raw.cursor.return_value.__enter__ = lambda s: mock_cur
    mock_raw.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_cur.description = [("SQL_ID",), ("ELAPSED_TIME",)]
    mock_cur.fetchall.return_value = [("abc123", 1000), ("def456", 2000)]
    with patch("services.db_service.oracledb.connect", return_value=mock_raw):
        conn.connect(_direct())
    result = conn.execute_query("SELECT sql_id, elapsed_time FROM v$sql")
    assert result == [
        {"sql_id": "abc123", "elapsed_time": 1000},
        {"sql_id": "def456", "elapsed_time": 2000},
    ]


def test_execute_query_raises_when_not_connected() -> None:
    conn = OracleConnection()
    with pytest.raises(RuntimeError, match="Not connected"):
        conn.execute_query("SELECT 1 FROM dual")


def test_test_connection_returns_true_on_success() -> None:
    conn = OracleConnection()
    with patch("services.db_service.oracledb.connect") as mock_connect:
        mock_connect.return_value = MagicMock()
        ok, msg = conn.test_connection(_direct())
    assert ok is True
    assert "successful" in msg.lower()


def test_test_connection_returns_false_on_error() -> None:
    conn = OracleConnection()
    with patch(
        "services.db_service.oracledb.connect",
        side_effect=oracledb.DatabaseError("ORA-01017"),
    ):
        ok, msg = conn.test_connection(_direct())
    assert ok is False
    assert "ORA-01017" in msg


def test_disconnect_clears_profile() -> None:
    conn = OracleConnection()
    with patch("services.db_service.oracledb.connect", return_value=MagicMock()):
        conn.connect(_direct())
    assert conn.profile is not None
    conn.disconnect()
    assert conn.profile is None


def test_disconnect_raises_on_next_query() -> None:
    conn = OracleConnection()
    with patch("services.db_service.oracledb.connect", return_value=MagicMock()):
        conn.connect(_direct())
    conn.disconnect()
    with pytest.raises(RuntimeError):
        conn.execute_query("SELECT 1 FROM dual")


def test_get_db_version_returns_banner() -> None:
    conn = OracleConnection()
    mock_raw = MagicMock()
    mock_cur = MagicMock()
    mock_raw.cursor.return_value.__enter__ = lambda s: mock_cur
    mock_raw.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_cur.description = [("BANNER",)]
    mock_cur.fetchall.return_value = [("Oracle Database 19c Enterprise Edition",)]
    with patch("services.db_service.oracledb.connect", return_value=mock_raw):
        conn.connect(_direct())
    assert "Oracle" in conn.get_db_version()
