"""Tests for the plaintext-key migration in services/ai_service."""

import json
from pathlib import Path
from unittest.mock import patch

import keyring
from keyring.errors import KeyringError

from services import ai_service


def _write_settings(tmp_path: Path, data: dict[str, str]) -> Path:
    path = tmp_path / ".oracletune_settings.json"
    path.write_text(json.dumps(data))
    return path


def test_migrates_keys_to_vault_and_purges_file(tmp_path: Path) -> None:
    path = _write_settings(
        tmp_path,
        {"anthropic_key": "sk-ant-123", "openai_key": "sk-oai-456", "model": "m"},
    )
    vault: dict[str, str] = {}
    with (
        patch.object(ai_service, "SETTINGS_PATH", path),
        patch.object(keyring, "get_password", side_effect=lambda s, n: vault.get(n)),
        patch.object(
            keyring,
            "set_password",
            side_effect=lambda s, n, v: vault.__setitem__(n, v),
        ),
    ):
        ai_service.migrate_plaintext_keys()

    assert vault == {"anthropic_key": "sk-ant-123", "openai_key": "sk-oai-456"}
    remaining = json.loads(path.read_text())
    assert "anthropic_key" not in remaining
    assert "openai_key" not in remaining
    assert remaining["model"] == "m"  # non-secret settings untouched


def test_legacy_api_key_field_becomes_anthropic_vault_entry(tmp_path: Path) -> None:
    path = _write_settings(tmp_path, {"api_key": "sk-ant-legacy"})
    vault: dict[str, str] = {}
    with (
        patch.object(ai_service, "SETTINGS_PATH", path),
        patch.object(keyring, "get_password", side_effect=lambda s, n: vault.get(n)),
        patch.object(
            keyring,
            "set_password",
            side_effect=lambda s, n, v: vault.__setitem__(n, v),
        ),
    ):
        ai_service.migrate_plaintext_keys()

    assert vault == {"anthropic_key": "sk-ant-legacy"}
    assert "api_key" not in json.loads(path.read_text())


def test_existing_vault_entry_wins_over_file_copy(tmp_path: Path) -> None:
    path = _write_settings(tmp_path, {"anthropic_key": "sk-ant-stale"})
    vault = {"anthropic_key": "sk-ant-current"}
    with (
        patch.object(ai_service, "SETTINGS_PATH", path),
        patch.object(keyring, "get_password", side_effect=lambda s, n: vault.get(n)),
        patch.object(
            keyring,
            "set_password",
            side_effect=lambda s, n, v: vault.__setitem__(n, v),
        ),
    ):
        ai_service.migrate_plaintext_keys()

    assert vault["anthropic_key"] == "sk-ant-current"  # not overwritten
    assert "anthropic_key" not in json.loads(path.read_text())  # still purged


def test_vault_failure_keeps_key_in_file(tmp_path: Path) -> None:
    path = _write_settings(tmp_path, {"anthropic_key": "sk-ant-123"})
    with (
        patch.object(ai_service, "SETTINGS_PATH", path),
        patch.object(keyring, "get_password", side_effect=KeyringError("locked")),
    ):
        ai_service.migrate_plaintext_keys()

    # Nothing verifiably reached the vault, so the file copy must survive.
    assert json.loads(path.read_text()) == {"anthropic_key": "sk-ant-123"}


def test_no_settings_file_is_a_noop(tmp_path: Path) -> None:
    with patch.object(ai_service, "SETTINGS_PATH", tmp_path / "missing.json"):
        ai_service.migrate_plaintext_keys()  # must not raise


# ── Recommendation-building helpers (extracted in the function rework) ───────


def _finding_dict(title: str) -> dict[str, str]:
    return {
        "severity": "HIGH",
        "category": "INDEX",
        "title": title,
        "description": "desc",
        "detail": "det",
    }


def test_action_rules_match_known_titles() -> None:
    assert "GATHER_TABLE_STATS" in ai_service._action_for_finding(
        _finding_dict("Full Table Scan Regression: EMP")
    )
    assert "USE_NL" in ai_service._action_for_finding(
        _finding_dict("Join Method Changed: HASH JOIN -> NESTED LOOPS")
    )
    assert "ORA-04031" in ai_service._action_for_finding(
        _finding_dict("New Oracle Error in Current Run: ORA-00942")
    )


def test_action_rules_fall_back_to_default() -> None:
    action = ai_service._action_for_finding(_finding_dict("Completely Novel Issue"))
    assert action == ai_service._DEFAULT_ACTION
    assert "SQL Tuning Advisor" in action


def test_build_context_renders_dataclasses() -> None:
    """Regression: plan/diff sections crashed on dataclass access before."""
    from core.models import DiffResult, PlanComparison

    plan = PlanComparison(
        baseline_nodes=[],
        current_nodes=[],
        index_changes=[{"index": "IX1", "change": "REMOVED", "detail": "IX1 gone"}],
        full_scan_regressions=[],
        join_method_changes=[],
        plan_shape_changed=True,
        stats={
            "baseline_total_cost": 10,
            "current_total_cost": 90,
            "cost_delta_pct": 800.0,
        },
    )
    diff = DiffResult(
        label="a.sql  vs  b.sql",
        baseline_text="x",
        current_text="y",
        baseline_diff_lines={},
        current_diff_lines={},
        structural_changes=[{"type": "HINT_REMOVED", "detail": "FULL(t)"}],
        stats={
            "lines_added": 1,
            "lines_removed": 2,
            "lines_changed": 3,
            "baseline_total_lines": 5,
            "current_total_lines": 5,
            "similarity_ratio": 42.0,
        },
    )
    ctx = ai_service._build_context(
        [_finding_dict("Cost Increased")], [diff], plan, {}, {}
    )
    assert "Baseline cost: 10" in ctx
    assert "Cost delta:    +800%" in ctx
    assert "IX1 gone" in ctx
    assert "a.sql  vs  b.sql" in ctx
    assert "Similarity: 42.0%" in ctx
    assert "HINT_REMOVED: FULL(t)" in ctx


def test_offline_with_findings_lists_actions_and_checks() -> None:
    rec = ai_service._offline([_finding_dict("Cost Increased by 800%")], [], None)
    assert rec["mode"] == "offline"
    assert "Recommended Actions" in rec["content"]
    assert "Standard Checks to Run" in rec["content"]
    assert rec["error"] is None


def test_offline_without_findings_is_clean_summary() -> None:
    rec = ai_service._offline([], [], None, error="[anthropic] boom")
    assert "No significant performance regressions" in rec["content"]
    assert rec["error"] == "[anthropic] boom"


def test_batch_prompt_orders_by_severity_and_caps() -> None:
    from core.models import Finding

    findings = [
        Finding(
            severity="LOW", category="X", title=f"low{i}", description="d", detail=""
        )
        for i in range(35)
    ] + [
        Finding(
            severity="CRITICAL",
            category="X",
            title="the-big-one",
            description="d",
            detail="",
        )
    ]
    prompt = ai_service._batch_prompt(findings)
    lines = prompt.split("\n")
    assert len(lines) == 31  # header + 30 findings cap
    assert "the-big-one" in lines[1]  # CRITICAL sorts first
