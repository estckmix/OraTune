"""HTML Report Generator — core layer, no PyQt6 imports."""

import html
from datetime import datetime

from core.models import AnalysisSession, Finding, PlanCompStats


_SEVERITY_COLORS = {
    "CRITICAL": "#f85149",
    "HIGH": "#ff7b72",
    "MEDIUM": "#e3b341",
    "LOW": "#79c0ff",
    "INFO": "#8b949e",
}


def _findings_html(findings: list[Finding]) -> str:
    """Render each finding as a colored card."""
    rendered = ""
    for f in findings:
        sev = f.severity
        color = _SEVERITY_COLORS.get(sev, "#8b949e")
        rendered += f"""
        <div style="border-left: 4px solid {color}; background: #1c2128; padding: 12px 16px; margin-bottom: 10px; border-radius: 4px;">
            <span style="color:{color}; font-weight:bold; font-size:11px;">[{html.escape(sev)}] {html.escape(f.category)}</span>
            <h4 style="color:#e6edf3; margin:4px 0;">{html.escape(f.title)}</h4>
            <p style="color:#8b949e; margin:4px 0; font-size:13px;">{html.escape(f.description)}</p>
            <code style="color:#e3b341; font-size:11px;">{html.escape(f.detail)}</code>
        </div>"""
    return rendered


def generate_html_report(session: AnalysisSession, output_path: str) -> None:
    """Generate a self-contained HTML report from an AnalysisSession."""
    findings = session.findings
    plan_comparison = session.plan_comparison
    recommendations = session.recommendations

    plan_stats: PlanCompStats = plan_comparison.stats if plan_comparison else {}
    findings_html = _findings_html(findings)

    report = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>OraTune Analysis Report</title>
<style>
    body {{ background: #0d1117; color: #e6edf3; font-family: 'Consolas', monospace; margin: 0; padding: 24px; }}
    h1 {{ color: #58a6ff; letter-spacing: 3px; }}
    h2 {{ color: #79c0ff; border-bottom: 1px solid #30363d; padding-bottom: 8px; }}
    .stat-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }}
    .stat {{ background: #161b22; border: 1px solid #30363d; padding: 12px; border-radius: 6px; text-align: center; }}
    .stat-val {{ font-size: 24px; font-weight: bold; color: #58a6ff; }}
    .stat-lbl {{ font-size: 10px; color: #8b949e; letter-spacing: 1px; margin-top: 4px; }}
    pre {{ background: #161b22; padding: 16px; border-radius: 6px; white-space: pre-wrap; font-size: 12px; line-height: 1.6; }}
</style>
</head>
<body>
<h1>⬡ OraTune Analysis Report</h1>
<p style="color:#8b949e;">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>

<div class="stat-grid">
    <div class="stat">
        <div class="stat-val">{len(findings)}</div>
        <div class="stat-lbl">TOTAL FINDINGS</div>
    </div>
    <div class="stat">
        <div class="stat-val" style="color:#f85149">{sum(1 for f in findings if f.severity in ["CRITICAL", "HIGH"])}</div>
        <div class="stat-lbl">CRITICAL / HIGH</div>
    </div>
    <div class="stat">
        <div class="stat-val">{plan_stats.get("baseline_total_cost", "—")}</div>
        <div class="stat-lbl">BASELINE COST</div>
    </div>
    <div class="stat">
        <div class="stat-val" style="color:#f85149">{plan_stats.get("current_total_cost", "—")}</div>
        <div class="stat-lbl">CURRENT COST</div>
    </div>
</div>

<h2>Findings</h2>
{findings_html if findings_html else '<p style="color:#484f58;">No findings detected.</p>'}

<h2>Recommendations</h2>
<pre>{html.escape(recommendations.get("content", "No recommendations generated."))}</pre>

</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as out:
        out.write(report)
