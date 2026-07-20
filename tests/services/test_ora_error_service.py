from unittest.mock import patch
from services.ora_error_service import lookup, search

_MOCK = {
    "ORA-00001": {
        "message": "unique constraint violated",
        "cause": "duplicate key inserted",
        "action": "remove the unique restriction",
        "severity": "HIGH",
        "category": "Constraints",
    },
    "ORA-04031": {
        "message": "unable to allocate shared memory",
        "cause": "shared pool exhausted",
        "action": "increase SHARED_POOL_SIZE",
        "severity": "CRITICAL",
        "category": "Memory",
    },
}


def test_lookup_known_code() -> None:
    with patch("services.ora_error_service._ERRORS", _MOCK):
        result = lookup("ORA-00001")
    assert result is not None
    assert result["severity"] == "HIGH"
    assert "unique" in result["message"].lower()


def test_lookup_unknown_code() -> None:
    with patch("services.ora_error_service._ERRORS", _MOCK):
        result = lookup("ORA-99999")
    assert result is None


def test_search_by_code() -> None:
    with patch("services.ora_error_service._ERRORS", _MOCK):
        results = search("00001")
    codes = [r["code"] for r in results]
    assert "ORA-00001" in codes


def test_search_by_message_text() -> None:
    with patch("services.ora_error_service._ERRORS", _MOCK):
        results = search("unique")
    assert any("unique" in r["message"].lower() for r in results)
