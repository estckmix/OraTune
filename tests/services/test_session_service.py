"""Tests for storage/session_repo.py round-trip behaviour."""

from collections.abc import Iterator
from pathlib import Path

from services import session_service

import pytest

from core.models import AnalysisSession, Finding
from storage import session_repo


@pytest.fixture(autouse=True)
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Redirect the DB to a temp directory for each test."""
    db_dir = tmp_path / ".oratune"
    db_path = db_dir / "sessions.db"
    import storage.database as db_mod

    monkeypatch.setattr(db_mod, "_DB_PATH", db_path)
    yield


def _make_session() -> AnalysisSession:
    return AnalysisSession(
        baseline_files=["baseline.sql"],
        current_files=["current.sql"],
        findings=[
            Finding(
                severity="HIGH",
                category="Index",
                title="Index dropped",
                description="desc",
                detail="detail",
            )
        ],
        diff_results=[],
        plan_comparison=None,
        awr_data={},
        dmp_context={},
        recommendations={"mode": "offline", "content": "check stats"},
    )


def test_save_and_load_round_trip() -> None:
    session = _make_session()
    session_repo.save(session)
    loaded = session_repo.load(session.id)
    assert loaded is not None
    assert loaded.id == session.id
    assert loaded.baseline_files == ["baseline.sql"]
    assert len(loaded.findings) == 1
    assert loaded.findings[0].severity == "HIGH"
    assert loaded.findings[0].annotation == ""


def test_list_sessions_returns_rows() -> None:
    s1 = _make_session()
    s2 = _make_session()
    session_repo.save(s1)
    session_repo.save(s2)
    rows = session_repo.list_sessions()
    assert len(rows) == 2
    ids = {r["id"] for r in rows}
    assert s1.id in ids
    assert s2.id in ids


def test_load_returns_none_for_missing_id() -> None:
    result = session_repo.load("nonexistent-id")
    assert result is None


def test_annotation_persists() -> None:
    session = _make_session()
    session.findings[0].annotation = "root cause: stale stats"
    session_repo.save(session)
    loaded = session_repo.load(session.id)
    assert loaded is not None
    assert loaded.findings[0].annotation == "root cause: stale stats"


def test_save_overwrites_existing() -> None:
    session = _make_session()
    session_repo.save(session)
    session.findings[0].annotation = "updated"
    session_repo.save(session)
    loaded = session_repo.load(session.id)
    assert loaded is not None
    assert loaded.findings[0].annotation == "updated"
    assert len(session_repo.list_sessions()) == 1


def test_db_autocreates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import storage.database as db_mod

    new_path = tmp_path / "subdir" / "nested" / "sessions.db"
    monkeypatch.setattr(db_mod, "_DB_PATH", new_path)
    session_repo.save(_make_session())
    assert new_path.exists()


def test_service_save_and_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import storage.database as db_mod

    monkeypatch.setattr(db_mod, "_DB_PATH", tmp_path / ".oratune" / "sessions.db")
    session = _make_session()
    session_service.save(session)
    loaded = session_service.load(session.id)
    assert loaded is not None
    assert loaded.id == session.id


def test_service_returns_none_on_bad_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import storage.database as db_mod

    monkeypatch.setattr(db_mod, "_DB_PATH", tmp_path / ".oratune" / "sessions.db")
    assert session_service.load("bad-id") is None


def test_service_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import storage.database as db_mod

    monkeypatch.setattr(db_mod, "_DB_PATH", tmp_path / ".oratune" / "sessions.db")
    session_service.save(_make_session())
    session_service.save(_make_session())
    rows = session_service.list_sessions()
    assert len(rows) == 2
