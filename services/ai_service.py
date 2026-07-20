"""AI Service — Multi-provider router for tuning recommendations.

Supported providers:
  anthropic  — Claude (Anthropic API)
  openai     — ChatGPT (OpenAI API)
  azure      — Azure OpenAI (Microsoft)
  copilot    — GitHub Copilot API
"""

import importlib.util
import json
import os
from pathlib import Path
from typing import TypedDict

import keyring
import structlog
from keyring.errors import KeyringError

from core.models import (
    AwrComparison,
    DiffResult,
    DmpComparison,
    Finding,
    PlanComparison,
    Recommendation,
)

log = structlog.get_logger()

# Shared with ui/dialogs — single source of truth for the settings file
# location and the OS credential-store service name.
KEYRING_SERVICE = "OraTune"
SETTINGS_PATH = Path.home() / ".oracletune_settings.json"


def get_secret(name: str) -> str:
    """Read an API key from the OS secure credential store; '' if unavailable."""
    try:
        return keyring.get_password(KEYRING_SERVICE, name) or ""
    except KeyringError:
        return ""


# ── Settings loader (no UI dependency) ───────────────────────────────────────


class LastConnection(TypedDict, total=False):
    """Remembered connection profile — never contains the password."""

    connection_type: str
    host: str
    port: int
    service: str
    alias: str
    username: str


class Settings(TypedDict, total=False):
    """Shape of ~/.oracletune_settings.json. Secrets never live here."""

    active_provider: str
    anthropic_model: str
    model: str  # legacy mirror of anthropic_model
    openai_model: str
    azure_endpoint: str
    azure_deployment: str
    azure_api_version: str
    copilot_model: str
    auto_analyze: bool
    last_connection: LastConnection


def _load_settings() -> Settings:
    if SETTINGS_PATH.exists():
        try:
            loaded: Settings = json.loads(SETTINGS_PATH.read_text())
            return loaded
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _get_active_provider(s: Settings) -> str:
    return s.get("active_provider", "anthropic")


# ── Plaintext-key migration (SOC 2 CC6.1) ─────────────────────────────────────

# Older versions stored API keys directly in the settings JSON. Legacy field
# "api_key" was the original Anthropic key. Map: settings field -> vault name.
_LEGACY_KEY_FIELDS = {
    "anthropic_key": "anthropic_key",
    "api_key": "anthropic_key",
    "openai_key": "openai_key",
    "azure_key": "azure_key",
    "copilot_key": "copilot_key",
}


def migrate_plaintext_keys() -> None:
    """One-time startup migration: move API keys out of the plaintext settings
    file into the OS credential store, then purge them from the file.

    A field is removed from the file only once the vault verifiably holds a
    key for it, so a locked or missing credential store never loses a key.
    An existing vault entry always wins over the file copy.
    """
    if not SETTINGS_PATH.exists():
        return
    try:
        settings = json.loads(SETTINGS_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return

    purged = []
    for field, vault_name in _LEGACY_KEY_FIELDS.items():
        value = settings.get(field, "")
        if not value:
            settings.pop(field, None)  # drop empty leftovers too
            continue
        try:
            if not keyring.get_password(KEYRING_SERVICE, vault_name):
                keyring.set_password(KEYRING_SERVICE, vault_name, value)
            settings.pop(field)
            purged.append(field)
        except KeyringError as exc:
            log.error("secrets.migration_failed", field=field, error=str(exc))

    if purged:
        try:
            SETTINGS_PATH.write_text(json.dumps(settings, indent=2))
        except OSError as exc:
            log.error("secrets.migration_write_failed", error=str(exc))
            return
        log.info("secrets.migrated_to_credential_store", fields=purged)


# ── Provider availability checks ─────────────────────────────────────────────


def _anthropic_available() -> bool:
    return importlib.util.find_spec("anthropic") is not None


def _openai_available() -> bool:
    return importlib.util.find_spec("openai") is not None


# ── Public helpers used by main_window for status indicator ──────────────────


def get_api_key() -> str:
    """Returns the API key for the active provider, or '' if none set.

    Mirrors the key resolution used by the _call_* provider functions:
    OS credential store first, then environment variable.
    """
    s = _load_settings()
    provider = _get_active_provider(s)
    if provider == "anthropic":
        return get_secret("anthropic_key") or os.environ.get("ANTHROPIC_API_KEY", "")
    if provider == "openai":
        return get_secret("openai_key") or os.environ.get("OPENAI_API_KEY", "")
    if provider == "azure":
        return get_secret("azure_key") or os.environ.get("AZURE_OPENAI_API_KEY", "")
    if provider == "copilot":
        return get_secret("copilot_key") or os.environ.get("GITHUB_COPILOT_TOKEN", "")
    return ""


def get_active_provider_label() -> str:
    """Returns a display label for the active provider."""
    s = _load_settings()
    provider = _get_active_provider(s)
    labels = {
        "anthropic": "CLAUDE",
        "openai": "OPENAI",
        "azure": "AZURE",
        "copilot": "COPILOT",
    }
    return labels.get(provider, provider.upper())


# ── Main entry point ──────────────────────────────────────────────────────────


def generate_recommendations(
    findings: list[Finding],
    diff_results: list[DiffResult],
    plan_comparison: PlanComparison | None,
    awr_data: AwrComparison,
    dmp_context: DmpComparison | None = None,
) -> Recommendation:
    """
    Route to the appropriate AI provider and generate tuning recommendations.
    Falls back to offline rules engine if no key is configured or library unavailable.
    """
    # Serialize findings for the prompt context
    findings_dicts: list[dict[str, str]] = [
        {
            "severity": f.severity,
            "category": f.category,
            "title": f.title,
            "description": f.description,
            "detail": f.detail,
        }
        for f in findings
    ]

    s = _load_settings()
    provider = _get_active_provider(s)
    context = _build_context(
        findings_dicts, diff_results, plan_comparison, awr_data, dmp_context or {}
    )

    try:
        if provider == "anthropic":
            return _call_anthropic(
                s, context, findings_dicts, diff_results, plan_comparison
            )
        elif provider == "openai":
            return _call_openai(s, context)
        elif provider == "azure":
            return _call_azure(s, context)
        elif provider == "copilot":
            return _call_copilot(s, context)
        else:
            return _offline(findings_dicts, diff_results, plan_comparison, dmp_context)
    except Exception as e:
        result = _offline(findings_dicts, diff_results, plan_comparison, dmp_context)
        result["error"] = f"[{provider}] {str(e)}"
        return result


# ── Batch summary ─────────────────────────────────────────────────────────────


def _batch_prompt(findings: list[Finding]) -> str:
    """Prompt for the batch summary — the 30 highest-severity findings."""
    _order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
    top = sorted(findings, key=lambda f: _order.get(f.severity, 5))[:30]

    lines = [
        "Batch Oracle SQL analysis — multiple pairs analyzed. "
        "Summarize the most critical patterns in 2-3 paragraphs and give the top 3 recommendations:"
    ]
    for f in top:
        lines.append(f"[{f.severity}] {f.title}: {f.description}")
    return "\n".join(lines)


def _batch_summary_openai_family(s: Settings, provider: str, context: str) -> str:
    """Batch summary via the OpenAI-compatible providers; '' when unusable."""
    if not _openai_available():
        return ""
    from openai import OpenAI, AzureOpenAI

    if provider == "azure":
        key = get_secret("azure_key") or os.environ.get("AZURE_OPENAI_API_KEY", "")
        oai_client: OpenAI | AzureOpenAI = AzureOpenAI(
            api_key=key,
            azure_endpoint=s.get("azure_endpoint", "").rstrip("/"),
            api_version=s.get("azure_api_version", "2024-02-01"),
        )
        model = s.get("azure_deployment", "")
    elif provider == "copilot":
        key = get_secret("copilot_key") or os.environ.get("GITHUB_COPILOT_TOKEN", "")
        oai_client = OpenAI(api_key=key, base_url="https://api.githubcopilot.com")
        model = s.get("copilot_model", "gpt-4o")
    else:
        key = get_secret("openai_key") or os.environ.get("OPENAI_API_KEY", "")
        oai_client = OpenAI(api_key=key)
        model = s.get("openai_model", "gpt-4o")
    if not key:
        return ""
    oai_resp = oai_client.chat.completions.create(
        model=model,
        max_tokens=600,
        messages=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": context},
        ],
    )
    return oai_resp.choices[0].message.content or ""


def generate_batch_summary(findings: list[Finding]) -> str:
    """Return a brief AI summary paragraph for batch findings.

    Caps at the 30 highest-severity findings to keep the prompt short.
    Returns '' if no findings, no key, or on any error.
    """
    if not findings:
        return ""

    context = _batch_prompt(findings)
    s = _load_settings()
    provider = _get_active_provider(s)

    try:
        if provider == "anthropic":
            key = get_secret("anthropic_key") or os.environ.get("ANTHROPIC_API_KEY")
            if not key or not _anthropic_available():
                return ""
            import anthropic

            model = s.get("anthropic_model", "claude-sonnet-4-6")
            client = anthropic.Anthropic(api_key=key)
            resp = client.messages.create(
                model=model,
                max_tokens=600,
                system=_system_prompt(),
                messages=[{"role": "user", "content": context}],
            )
            return _first_text(resp.content)

        if provider in ("openai", "azure", "copilot"):
            return _batch_summary_openai_family(s, provider, context)
    except Exception as exc:
        # Provider boundary: batch summary is optional enrichment — any SDK or
        # network failure degrades to no summary, per the documented contract.
        log.warning("ai.batch_summary_failed", error=str(exc))
        return ""

    return ""


# ── Provider implementations ──────────────────────────────────────────────────


def _first_text(blocks: object) -> str:
    """Return the text of the first TextBlock in an Anthropic response."""
    from anthropic.types import TextBlock

    if isinstance(blocks, list):
        for block in blocks:
            if isinstance(block, TextBlock):
                return block.text
    return ""


def _call_anthropic(
    s: Settings,
    context: str,
    findings: list[dict[str, str]],
    diff_results: list[DiffResult],
    plan_comparison: PlanComparison | None,
) -> Recommendation:
    key = get_secret("anthropic_key") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return _offline(findings, diff_results, plan_comparison)
    if not _anthropic_available():
        return _offline(
            findings,
            diff_results,
            plan_comparison,
            error="anthropic package not installed — run: pip install anthropic",
        )

    import anthropic

    model = s.get("anthropic_model", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=key)

    response = client.messages.create(
        model=model,
        max_tokens=2000,
        system=_system_prompt(),
        messages=[{"role": "user", "content": context}],
    )
    return {
        "mode": "ai",
        "provider": "Claude (Anthropic)",
        "model": model,
        "content": _first_text(response.content),
        "error": None,
    }


def _call_openai(s: Settings, context: str) -> Recommendation:
    key = get_secret("openai_key") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("No OpenAI API key configured")
    if not _openai_available():
        raise ImportError("openai package not installed — run: pip install openai")

    from openai import OpenAI

    model = s.get("openai_model", "gpt-4o")
    client = OpenAI(api_key=key)

    response = client.chat.completions.create(
        model=model,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": context},
        ],
    )
    return {
        "mode": "ai",
        "provider": "ChatGPT (OpenAI)",
        "model": model,
        "content": response.choices[0].message.content or "",
        "error": None,
    }


def _call_azure(s: Settings, context: str) -> Recommendation:
    key = get_secret("azure_key") or os.environ.get("AZURE_OPENAI_API_KEY")
    endpoint = s.get("azure_endpoint", "").rstrip("/")
    deployment = s.get("azure_deployment", "")
    api_ver = s.get("azure_api_version", "2024-02-01")

    if not all([key, endpoint, deployment]):
        raise ValueError("Azure OpenAI requires endpoint, API key, and deployment name")
    if not _openai_available():
        raise ImportError("openai package not installed — run: pip install openai")

    from openai import AzureOpenAI

    client = AzureOpenAI(
        api_key=key,
        azure_endpoint=endpoint,
        api_version=api_ver,
    )

    response = client.chat.completions.create(
        model=deployment,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": context},
        ],
    )
    return {
        "mode": "ai",
        "provider": "Azure OpenAI",
        "model": deployment,
        "content": response.choices[0].message.content or "",
        "error": None,
    }


def _call_copilot(s: Settings, context: str) -> Recommendation:
    key = get_secret("copilot_key") or os.environ.get("GITHUB_COPILOT_TOKEN")
    model = s.get("copilot_model", "gpt-4o")

    if not key:
        raise ValueError("No GitHub Copilot token configured")
    if not _openai_available():
        raise ImportError("openai package not installed — run: pip install openai")

    from openai import OpenAI

    client = OpenAI(
        api_key=key,
        base_url="https://api.githubcopilot.com",
    )

    response = client.chat.completions.create(
        model=model,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": context},
        ],
    )
    return {
        "mode": "ai",
        "provider": "GitHub Copilot",
        "model": model,
        "content": response.choices[0].message.content or "",
        "error": None,
    }


# ── Shared system prompt ──────────────────────────────────────────────────────


def _system_prompt() -> str:
    return (
        "You are an expert Oracle Database Performance Engineer with 20+ years of experience "
        "in SQL tuning, execution plan analysis, AWR interpretation, and Oracle internals.\n\n"
        "You are analyzing a performance regression where a SQL job that ran smoothly for over "
        "a year has started running slower. You have been given structured findings from automated "
        "analysis, SQL/PLSQL code diff information, execution plan comparison data, AWR/TKPROF "
        "metrics, and Oracle dump file analysis where available.\n\n"
        "Your job is to:\n"
        "1. Explain WHY each issue is likely causing the slowdown — not just what changed\n"
        "2. Provide specific, actionable tuning recommendations with Oracle syntax where applicable\n"
        "3. Prioritize by impact — address the most critical issues first\n"
        "4. Include specific Oracle commands, hints, or DBMS_* calls where appropriate\n"
        "5. Flag if statistics gathering, plan regression, or parameter change is the likely root cause\n\n"
        "Format your response in Markdown with:\n"
        "- ## Summary (2-3 sentence executive summary)\n"
        "- ## Root Cause Analysis (explain the WHY)\n"
        "- ## Recommendations (numbered, prioritized by impact, with Oracle SQL/commands)\n"
        "- ## Preventive Measures (how to stop this recurring)\n\n"
        "Be specific and technical — the reader is a senior Oracle DBA."
    )


# ── Context builder ───────────────────────────────────────────────────────────


def _findings_context(findings: list[dict[str, str]]) -> list[str]:
    parts = ["### AUTOMATED FINDINGS"]
    for f in findings[:15]:
        parts.append(
            f"[{f.get('severity', '?')}] {f.get('category', '?')}: {f.get('title', '')}\n"
            f"  {f.get('description', '')}\n"
            f"  Detail: {f.get('detail', '')}"
        )
    return parts


def _plan_context(plan_comparison: PlanComparison) -> list[str]:
    # Dataclass attribute access; the old dict-style .get() calls crashed
    # with AttributeError whenever this section ran.
    stats = plan_comparison.stats
    parts = ["\n### EXECUTION PLAN COMPARISON"]
    parts.append(f"Baseline cost: {stats.get('baseline_total_cost', 'N/A')}")
    parts.append(f"Current cost:  {stats.get('current_total_cost', 'N/A')}")
    delta = stats.get("cost_delta_pct")
    if delta is not None:
        parts.append(f"Cost delta:    {delta:+.0f}%")
    parts.append(f"Plan shape changed: {plan_comparison.plan_shape_changed}")
    for ic in plan_comparison.index_changes:
        parts.append(f"  Index: {ic.get('detail', '')}")
    for r in plan_comparison.full_scan_regressions:
        parts.append(f"  Full scan regression: {r['detail']}")
    for jc in plan_comparison.join_method_changes:
        parts.append(f"  Join change: {jc['detail']}")
    return parts


def _diff_context(diff_results: list[DiffResult]) -> list[str]:
    parts = ["\n### SQL CODE CHANGES"]
    for diff in diff_results:
        diff_stats = diff.stats
        parts.append(f"File: {diff.label}")
        parts.append(f"  Similarity: {diff_stats['similarity_ratio']}%")
        parts.append(
            f"  Lines added: {diff_stats['lines_added']}, "
            f"removed: {diff_stats['lines_removed']}, "
            f"changed: {diff_stats['lines_changed']}"
        )
        for sc in diff.structural_changes:
            parts.append(f"  {sc['type']}: {sc['detail']}")
    return parts


def _dmp_context_section(dmp_context: DmpComparison) -> list[str]:
    parts = ["\n### DUMP FILE ANALYSIS (.dmp)"]

    sqlt = dmp_context.get("sqlt", {})
    if sqlt:
        parts.append("SQLT Comparison:")
        for param, vals in sqlt.get("optimizer_param_changes", {}).items():
            parts.append(
                f"  Optimizer param changed: {param}  baseline={vals.get('baseline')}  current={vals.get('current')}"
            )
        for t in sqlt.get("table_stat_changes", []):
            parts.append(
                f"  Table stat change: {t['table']}  rows {t['baseline_rows']:,} -> {t['current_rows']:,}  ({t['change_pct']}%)"
            )
        for i in sqlt.get("clustering_factor_changes", []):
            parts.append(
                f"  Clustering factor: {i['index']}  CF {i['baseline_cf']:,} -> {i['current_cf']:,}  ({i['change_pct']}%)"
            )
        for col in sqlt.get("histograms_removed", []):
            parts.append(f"  Histogram removed: {col}")

    adr = dmp_context.get("adr", {})
    if adr:
        parts.append("ADR Trace Comparison:")
        for ev in adr.get("new_wait_events", []):
            parts.append(f"  New wait event: {ev}")
        for err in adr.get("new_ora_errors", []):
            parts.append(f"  New ORA- error: {err}")

    spool = dmp_context.get("spool", {})
    if spool:
        b_ela = spool.get("baseline_elapsed")
        c_ela = spool.get("current_elapsed")
        if b_ela and c_ela:
            parts.append(f"SQL*Plus Spool: elapsed {b_ela}s -> {c_ela}s")
        for metric, auto_vals in spool.get("autotrace_changes", {}).items():
            parts.append(
                f"  Autotrace {metric}: {auto_vals['baseline']} -> "
                f"{auto_vals['current']}"
            )

    dp = dmp_context.get("datapump", {})
    if dp and dp.get("baseline_version") != dp.get("current_version"):
        parts.append(
            f"Data Pump: Oracle version {dp.get('baseline_version')} -> {dp.get('current_version')}"
        )

    return parts


def _build_context(
    findings: list[dict[str, str]],
    diff_results: list[DiffResult],
    plan_comparison: PlanComparison | None,
    awr_data: AwrComparison,
    dmp_context: DmpComparison,
) -> str:
    parts = [
        "Please analyze this Oracle SQL performance regression and provide expert tuning recommendations:\n"
    ]
    if findings:
        parts += _findings_context(findings)
    if plan_comparison:
        parts += _plan_context(plan_comparison)
    if diff_results:
        parts += _diff_context(diff_results)
    if awr_data:
        parts.append("\n### AWR/TKPROF DATA")
        parts.append(json.dumps(awr_data, indent=2, default=str)[:1000])
    if dmp_context:
        parts += _dmp_context_section(dmp_context)
    return "\n".join(parts)


# ── Offline fallback ──────────────────────────────────────────────────────────


_STANDARD_CHECKS = [
    "- Check for stale statistics: `SELECT table_name, last_analyzed, num_rows FROM user_tables WHERE last_analyzed < SYSDATE - 30;`",
    "- Check for unusable indexes: `SELECT index_name, status FROM user_indexes WHERE status != 'VALID';`",
    "- Gather schema statistics: `EXEC DBMS_STATS.GATHER_SCHEMA_STATS(ownname => 'YOUR_SCHEMA', cascade => TRUE);`",
    "- Review SQL Plan Baselines: `SELECT * FROM dba_sql_plan_baselines WHERE sql_text LIKE '%your_table%';`",
    "- Check optimizer parameters: `SELECT name, value FROM v$parameter WHERE name LIKE '%optimizer%';`",
]


def _offline_actions(findings: list[dict[str, str]]) -> list[str]:
    """Numbered recommended-action sections for each actionable finding."""
    sections = ["## Recommended Actions\n"]
    rec_num = 1
    for finding in findings:
        action = _action_for_finding(finding)
        if action:
            sev = finding.get("severity", "INFO")
            title = finding.get("title", "")
            desc = finding.get("description", "")
            sections.append(f"### {rec_num}. [{sev}] {title}\n")
            sections.append(f"{desc}\n")
            sections.append(f"**Recommended Action:**\n{action}\n")
            rec_num += 1
    return sections


def _offline(
    findings: list[dict[str, str]],
    diff_results: list[DiffResult],
    plan_comparison: PlanComparison | None,
    dmp_context: DmpComparison | None = None,
    error: str | None = None,
) -> Recommendation:
    """Rules-based recommendations — no API required."""
    sections: list[str] = []
    sections.append("# OraTune Analysis Report\n")
    sections.append(
        "*Running in offline mode — configure an AI provider in Settings to enable AI-powered analysis.*\n"
    )
    sections.append("---\n")

    if not findings:
        sections.append("## Summary\n")
        sections.append("No significant performance regressions were detected.\n")
        return {
            "mode": "offline",
            "provider": "Offline",
            "content": "\n".join(sections),
            "error": error,
        }

    counts: dict[str, int] = {}
    for f in findings:
        sev_key = f.get("severity", "INFO")
        counts[sev_key] = counts.get(sev_key, 0) + 1

    sections.append("## Summary\n")
    summary_parts = [
        f"{counts[level]} {level}"
        for level in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
        if counts.get(level)
    ]
    sections.append(f"Analysis identified: {', '.join(summary_parts)} findings.\n")

    sections += _offline_actions(findings)
    sections.append("---\n")
    sections.append("## Standard Checks to Run\n")
    sections += _STANDARD_CHECKS

    return {
        "mode": "offline",
        "provider": "Offline",
        "content": "\n".join(sections),
        "error": error,
    }


# Recommended actions keyed by finding-title keywords; first match wins.
_ACTION_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("Full Table Scan", "Full Scan Regression"),
        (
            "1. Gather fresh statistics on the affected table:\n"
            "   ```sql\n"
            "   EXEC DBMS_STATS.GATHER_TABLE_STATS(\n"
            "       ownname => 'SCHEMA', tabname => 'TABLE_NAME',\n"
            "       cascade => TRUE, method_opt => 'FOR ALL COLUMNS SIZE AUTO'\n"
            "   );\n"
            "   ```\n"
            "2. Check if the index is valid: `SELECT status FROM user_indexes WHERE index_name = 'INDEX_NAME';`\n"
            "3. Consider an index hint as a temporary measure: `/*+ INDEX(alias INDEX_NAME) */`"
        ),
    ),
    (
        ("Index No Longer Used",),
        (
            "1. Verify index status: `SELECT index_name, status, visibility FROM user_indexes WHERE index_name = 'INDEX_NAME';`\n"
            "2. Gather index statistics: `EXEC DBMS_STATS.GATHER_INDEX_STATS(ownname => 'SCHEMA', indname => 'INDEX_NAME');`\n"
            "3. Check if a recent rebuild changed the clustering factor.\n"
            "4. Consider locking statistics: `EXEC DBMS_STATS.LOCK_TABLE_STATS('SCHEMA', 'TABLE_NAME');`"
        ),
    ),
    (
        ("Clustering Factor",),
        (
            "1. Assess severity:\n"
            "   ```sql\n"
            "   SELECT index_name, clustering_factor, t.num_rows,\n"
            "          ROUND(i.clustering_factor / t.num_rows * 100, 1) pct\n"
            "   FROM   user_indexes i JOIN user_tables t USING (table_name)\n"
            "   WHERE  index_name = 'INDEX_NAME';\n"
            "   ```\n"
            "2. If CF >> NUM_ROWS, consider table reorganization (DBMS_REDEFINITION or MOVE).\n"
            "3. Short-term: force index with hint: `/*+ INDEX(alias INDEX_NAME) */`"
        ),
    ),
    (
        ("Histogram Removed",),
        (
            "1. Re-create the histogram:\n"
            "   ```sql\n"
            "   EXEC DBMS_STATS.GATHER_TABLE_STATS(\n"
            "       ownname => 'SCHEMA', tabname => 'TABLE_NAME',\n"
            "       method_opt => 'FOR COLUMNS SIZE AUTO COLUMN_NAME'\n"
            "   );\n"
            "   ```\n"
            "2. Verify: `SELECT column_name, histogram, num_buckets FROM user_tab_col_statistics WHERE table_name = 'TABLE_NAME';`\n"
            "3. Lock to prevent removal: `EXEC DBMS_STATS.LOCK_TABLE_STATS('SCHEMA', 'TABLE_NAME');`"
        ),
    ),
    (
        ("Row Count", "Stat"),
        (
            "1. Gather fresh statistics:\n"
            "   ```sql\n"
            "   EXEC DBMS_STATS.GATHER_TABLE_STATS(\n"
            "       ownname => 'SCHEMA', tabname => 'TABLE_NAME',\n"
            "       estimate_percent => DBMS_STATS.AUTO_SAMPLE_SIZE,\n"
            "       method_opt => 'FOR ALL COLUMNS SIZE AUTO', cascade => TRUE\n"
            "   );\n"
            "   ```\n"
            "2. Check last analyzed: `SELECT table_name, num_rows, last_analyzed FROM user_tables WHERE table_name = 'TABLE_NAME';`"
        ),
    ),
    (
        ("Cost Increased",),
        (
            "1. Gather fresh statistics on all tables in the query.\n"
            "2. Check SQL Plan Baselines:\n"
            "   ```sql\n"
            "   SELECT sql_id, plan_name, enabled, accepted, fixed\n"
            "   FROM   dba_sql_plan_baselines WHERE sql_text LIKE '%relevant_table%';\n"
            "   ```\n"
            "3. Run SQL Tuning Advisor: `EXEC DBMS_SQLTUNE.CREATE_TUNING_TASK(sql_id => 'SQL_ID');`"
        ),
    ),
    (
        ("Join Method Changed",),
        (
            "1. Gather statistics on all joined tables.\n"
            "2. For NESTED LOOPS preference: `/*+ USE_NL(table1 table2) */`\n"
            "3. Check for extended statistics on join columns."
        ),
    ),
    (
        ("Hint Removed", "Index Hint Removed"),
        (
            "1. Restore the removed hint to confirm it resolves the regression.\n"
            "2. Use SQL Plan Management as a maintainable long-term alternative to hints."
        ),
    ),
    (
        ("Plan Shape",),
        (
            "1. Run DBMS_STATS with CASCADE => TRUE on all involved tables.\n"
            "2. Pin the baseline plan using SPM:\n"
            "   ```sql\n"
            "   DECLARE l_plans PLS_INTEGER;\n"
            "   BEGIN\n"
            "     l_plans := DBMS_SPM.LOAD_PLANS_FROM_CURSOR_CACHE(sql_id => 'BASELINE_SQL_ID');\n"
            "   END;\n"
            "   ```\n"
            "3. Check recent optimizer parameter changes: `SELECT name, value FROM v$parameter WHERE name LIKE '%optimizer%';`"
        ),
    ),
    (
        ("Optimizer Parameter Changed",),
        (
            "1. Verify if the change was intentional: `SELECT name, value FROM v$parameter WHERE name = 'PARAM_NAME';`\n"
            "2. Restore at session or system level:\n"
            "   ```sql\n"
            "   ALTER SESSION SET optimizer_mode = 'ALL_ROWS';\n"
            "   ALTER SYSTEM  SET optimizer_mode = 'ALL_ROWS';\n"
            "   ```\n"
            "3. For hidden parameters (prefixed _), consult Oracle Support before changing."
        ),
    ),
    (
        ("Wait Event",),
        (
            "1. Profile wait events: `SELECT event, total_waits, time_waited FROM v$session_event WHERE sid = SYS_CONTEXT('USERENV','SID');`\n"
            "2. For I/O waits: review tablespace I/O stats and storage.\n"
            "3. For locking waits: query v$lock and v$session for blocking sessions.\n"
            "4. For buffer busy waits: consider increasing buffer cache or reviewing hot blocks."
        ),
    ),
    (
        ("Oracle Error", "ORA-"),
        (
            "1. Look up the ORA- error in Oracle documentation.\n"
            "2. Check alert log: `SELECT originating_timestamp, message_text FROM v$diag_alert_ext WHERE message_text LIKE '%ORA-%' ORDER BY 1 DESC FETCH FIRST 20 ROWS ONLY;`\n"
            "3. ORA-04031 (shared pool): increase shared_pool_size.\n"
            "4. ORA-01555 (snapshot too old): increase undo_retention.\n"
            "5. ORA-00054 (resource busy): investigate locking and DML contention."
        ),
    ),
)

_DEFAULT_ACTION = (
    "1. Review the finding detail and compare against the baseline.\n"
    "2. Gather fresh statistics on involved objects.\n"
    "3. Consider SQL Tuning Advisor for automated recommendations."
)


def _action_for_finding(finding: dict[str, str]) -> str:
    """Return the canned action whose keywords match the finding title."""
    title = finding.get("title", "")
    for keywords, action in _ACTION_RULES:
        if any(k in title for k in keywords):
            return action
    return _DEFAULT_ACTION
