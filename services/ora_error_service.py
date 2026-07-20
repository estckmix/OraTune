"""ORA- Error Reference service — loads bundled error data and provides search/lookup."""

import json
import sys
from pathlib import Path

import structlog

log = structlog.get_logger()


def _data_file() -> Path:
    # sys._MEIPASS is set by PyInstaller when running as a packaged binary
    if getattr(sys, "frozen", False):
        # sys._MEIPASS only exists in PyInstaller binaries, hence getattr
        base = Path(getattr(sys, "_MEIPASS"))
    else:
        base = Path(__file__).parent.parent
    return base / "data" / "ora_errors.json"


def _load() -> dict[str, dict[str, str]]:
    try:
        entries: dict[str, dict[str, str]] = json.loads(
            _data_file().read_text(encoding="utf-8")
        )
        return entries
    except FileNotFoundError:
        log.error("ora_error.data_file_missing", path=str(_data_file()))
        return {}


_ERRORS: dict[str, dict[str, str]] = _load()


def lookup(code: str) -> dict[str, str] | None:
    """Return the entry for an exact ORA- code (case-insensitive), or None if not found."""
    return _ERRORS.get(code.upper())


def search(query: str) -> list[dict[str, str]]:
    """Return entries matching query in code, message, or cause (case-insensitive).

    Returns all entries when query is empty or whitespace.
    Each result dict has a 'code' key added.
    """
    q = query.strip().lower()
    results: list[dict[str, str]] = []
    for code, entry in _ERRORS.items():
        if (
            not q
            or q in code.lower()
            or q in entry.get("message", "").lower()
            or q in entry.get("cause", "").lower()
        ):
            results.append({"code": code, **entry})
    return results
