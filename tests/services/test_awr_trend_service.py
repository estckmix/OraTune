import pytest
from datetime import datetime
from unittest.mock import MagicMock
from services.awr_trend_service import fetch_awr_trend

_START = datetime(2026, 5, 1)
_END = datetime(2026, 5, 9)

_RAW_ROW = {
    "end_interval_time": datetime(2026, 5, 9, 14, 0),
    "elapsed_time_delta": 2_000_000,  # microseconds → 2 seconds
    "cpu_time_delta": 1_500_000,
    "buffer_gets_delta": 9000,
    "disk_reads_delta": 50,
    "executions_delta": 10,
}


def test_happy_path() -> None:
    conn = MagicMock()
    conn.execute_query.return_value = [_RAW_ROW, _RAW_ROW, _RAW_ROW]
    rows = fetch_awr_trend(conn, "abc123", _START, _END)
    assert len(rows) == 3
    r = rows[0]
    assert r["elapsed_ms_per_exec"] == pytest.approx(200.0)  # 2_000_000 / 10 / 1000
    assert r["cpu_ms_per_exec"] == pytest.approx(150.0)
    assert r["buffer_gets_per_exec"] == pytest.approx(900.0)
    assert r["disk_reads_per_exec"] == pytest.approx(5.0)
    assert r["executions"] == 10
    assert r["snap_time"] == datetime(2026, 5, 9, 14, 0)


def test_empty_result() -> None:
    conn = MagicMock()
    conn.execute_query.return_value = []
    rows = fetch_awr_trend(conn, "abc123", _START, _END)
    assert rows == []


def test_single_execution() -> None:
    conn = MagicMock()
    raw = {**_RAW_ROW, "executions_delta": 1}
    conn.execute_query.return_value = [raw]
    rows = fetch_awr_trend(conn, "abc123", _START, _END)
    assert rows[0]["elapsed_ms_per_exec"] == pytest.approx(
        2000.0
    )  # 2_000_000 / 1 / 1000
    assert rows[0]["buffer_gets_per_exec"] == pytest.approx(9000.0)
