# OraTune

**Oracle SQL/PLSQL Performance Regression Analysis Tool**

Authored by David Radoicic

Compares baseline and current SQL code, execution plans, AWR/TKPROF reports, and Oracle dump files
to identify performance regressions and provide expert tuning recommendations.

***

## Features

* **Side-by-side SQL/PLSQL diff** — syntax-highlighted, line-level comparison with structural change detection
* **Execution plan comparison** — operation-by-operation diff with cost/cardinality analysis and full-scan regression flagging
* **Index change detection** — flags indexes that appeared, disappeared, changed access method, or degraded in clustering factor
* **AWR/TKPROF parsing** — extracts and compares key performance metrics, wait events, and top SQL
* **Oracle dump file analysis (.dmp)** — supports all four Oracle dump types (see below)
* **Batch Analysis** — point two folders (baseline and current) at each other and analyze all matched file pairs in sequence; results table with severity summary and per-pair drill-down log
* **ORA- Error Reference** — searchable offline reference for 225+ Oracle error codes with cause, action, and severity; accessible via **Tools → ORA- Error Reference** (`Ctrl+Shift+O`) or by clicking any ORA- code that appears in the Findings tab
* **Live DB mode** — connect directly to an Oracle database and run:
  * **Explain Plan** — paste SQL, view formatted execution plan
  * **Top SQL** — session-level top SQL by elapsed time with plan drill-down
  * **AWR Trends** — historical metric trends from DBA_HIST_SYSMETRIC_SUMMARY
  * **Index Advisor** — missing-index recommendations from DBA_ADVISOR_RECOMMENDATIONS
  * **Stats Health** — stale-statistics report from DBA_TAB_STATISTICS
  * **Plan Baselines** — SQL Plan Management baselines from DBA_SQL_PLAN_BASELINES
  * **Scheduler** — DBMS_SCHEDULER job status from DBA_SCHEDULER_JOBS
* **Multi-provider AI recommendations engine:**
  * **Offline mode** — rules-based findings with Oracle-specific remediation commands
  * **Claude (Anthropic)** — deep Oracle expertise, root-cause analysis
  * **ChatGPT (OpenAI)** — GPT-4o / GPT-4 via OpenAI API
  * **Azure OpenAI** — enterprise GPT-4 via your Azure deployment
  * **GitHub Copilot** — via GitHub personal access token
* **HTML report export**

***

## Supported File Types

### SQL & PL/SQL

| Extension | Type                  |
| --------- | --------------------- |
| `.sql`    | Plain SQL             |
| `.pls`    | PL/SQL source         |
| `.pks`    | Package specification |
| `.pkb`    | Package body          |
| `.prc`    | Stored procedure      |
| `.fnc`    | Function              |
| `.trg`    | Trigger               |

### Performance & Diagnostic Reports

| Extension      | Type                                      |
| -------------- | ----------------------------------------- |
| `.txt` `.lst`  | AWR text report or TKPROF listing         |
| `.html` `.htm` | AWR HTML report (from EM / Cloud Control) |
| `.xml`         | DBMS\_XPLAN XML export                    |

### Oracle Dump Files (.dmp)

The tool auto-detects which of the four Oracle dump formats was uploaded and extracts accordingly:

| Dump Type                       | Detection                                 | What Is Extracted                                                                                                                           |
| ------------------------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **Data Pump export** (`expdp`)  | Binary magic bytes                        | Schema/table/index names, Oracle version, character set, embedded SQL fragments via string extraction                                       |
| **ADR trace / diagnostic dump** | `SESSION ID`, `ORA-`, `DUMP FILE` markers | ORA- errors, wait events with elapsed time, embedded execution plans, CPU and elapsed timing                                                |
| **SQL\*Plus spool**             | Default text fallback                     | SQL statements, `SET TIMING` elapsed times, row counts, full `SET AUTOTRACE` statistics                                                     |
| **SQLT / SQLTXPLAIN dump**      | `SQLTXPLAIN` / `TOOL: SQLT` markers       | Optimizer parameters, table and index statistics, clustering factors, histograms, bind variables, system statistics, multiple plan variants |

> **Note on Data Pump files:** Data Pump `.dmp` files are proprietary binary format. Object names and SQL are
> recovered via string extraction. For a full DDL comparison, export DDL separately using:
>
> ```SQL
> impdp userid=/ directory=DATA_PUMP_DIR dumpfile=export.dmp sqlfile=ddl_output.sql
> ```

***

## What .dmp Files Feed Into Findings

| Source          | Condition                                | Severity        |
| --------------- | ---------------------------------------- | --------------- |
| SQLT            | Optimizer parameter changed between runs | HIGH / MEDIUM   |
| SQLT            | Table NUM\_ROWS drifted >20%             | MEDIUM          |
| SQLT            | Table NUM\_ROWS drifted >50%             | HIGH            |
| SQLT            | Index clustering factor degraded >50%    | HIGH            |
| SQLT            | Histogram removed from a column          | MEDIUM          |
| SQLT            | Elapsed time regression 2x or more       | HIGH / CRITICAL |
| ADR Trace       | New ORA- error in current run            | HIGH            |
| ADR Trace       | New wait event in current run            | MEDIUM          |
| ADR Trace       | Elapsed time regression 2x or more       | HIGH / CRITICAL |
| SQL\*Plus Spool | Elapsed time regression 1.5x or more     | MEDIUM / HIGH   |
| SQL\*Plus Spool | Autotrace metric regression 2x or more   | MEDIUM          |
| Data Pump       | Oracle version mismatch between exports  | MEDIUM          |
| Data Pump       | Tables added or removed                  | LOW             |

***

## Installation (Windows)

OraTune is installed via a standard Windows installer (`OraTune_Setup.exe`).

**To get the installer, send the source zip to your Windows machine and follow the
steps in the "Building the Installer" section below. The resulting** **`OraTune_Setup.exe`
can then be shared and run on any Windows 10/11 machine.**

### Running the Installer

Double-click `OraTune_Setup.exe` and follow the wizard:

* Choose an install folder (default: `C:\Program Files\OraTune`)
* Optionally add a Desktop shortcut
* Click Install — no administrator rights required

OraTune will appear in your Start Menu under the OraTune group.

### Uninstalling

1. Open **Settings → Apps**
2. Search for **OraTune** and click **Uninstall**

During uninstall you will be asked whether to also delete your saved settings file
(`.oracletune_settings.json`, which holds your preferences and non-secret provider
settings). Choose **Yes** for a complete removal.

> **API keys are not stored in that file.** They are held in the Windows Credential
> Manager under the service name **OraTune**. To remove them, open *Credential Manager
> → Windows Credentials* and delete the `OraTune` entries.

***

## Building the Installer (Windows — One-Time Setup)

> This step is done once on a Windows machine to produce `OraTune_Setup.exe`,
> which can then be distributed to everyone else.

**Prerequisites — install these two free tools first:**

| Tool         | Download                  | Purpose                        |
| ------------ | ------------------------- | ------------------------------ |
| Python 3.11+ | python.org                | Runs OraTune and PyInstaller   |
| Inno Setup 6 | jrsoftware.org/isinfo.php | Compiles the Windows installer |

> When installing Python, check **"Add Python to PATH"**.

**Step 1 — Build the executable**

Open a Command Prompt in the `ora_tune\` folder and run:

```
pip install -r requirements.txt
pip install pyinstaller
pyinstaller OraTune.spec
```

This produces `dist\OraTune.exe` (80–130 MB, takes 3–5 minutes).

> The `OraTune.spec` file bundles the ORA- error database (`data\ora_errors.json`)
> automatically. Do not use the raw `pyinstaller` flags — use the spec file.

**Step 2 — Build the installer**

`OraTune_Installer.iss` already ships in the `ora_tune\` folder. Open it in Inno Setup Compiler
and press **F9** to compile. It installs `dist\OraTune.exe` plus the icon, creates Start Menu and
optional Desktop shortcuts, and prompts on uninstall to delete `.oracletune_settings.json`.

This produces `installer_output\OraTune_Setup.exe` — the file to distribute.

***

## AI-Powered Mode (Optional)

OraTune works fully offline with its built-in rules engine. To enable AI-powered recommendations,
configure a provider in **Tools → Settings**.

| Provider               | Where to get credentials                         | Notes                                   |
| ---------------------- | ------------------------------------------------ | --------------------------------------- |
| **Claude (Anthropic)** | console.anthropic.com                            | Best Oracle reasoning; recommended      |
| **ChatGPT (OpenAI)**   | platform.openai.com                              | GPT-4o / GPT-4                          |
| **Azure OpenAI**       | Azure portal                                     | Requires endpoint URL + deployment name |
| **GitHub Copilot**     | github.com → Settings → Developer settings → PAT | Requires active Copilot subscription    |

API keys are stored in the **Windows Credential Manager** (service name **OraTune**), never in a
plaintext file, and are transmitted only to the respective provider's API endpoint. Non-secret
preferences (selected provider, model names, Azure endpoint and deployment) are stored in
`C:\Users\YourName\.oracletune_settings.json`. Settings files written by older versions that still
contain a plaintext key are migrated to the credential store — and the plaintext copy removed — the
next time you save settings.

***

## Usage

### Single-Pair Analysis

1. **Upload Baseline files** — drag & drop or click Browse in the left (green) panel
2. **Upload Current / Degraded files** — drag & drop or click Browse in the right (red) panel
3. **Click ANALYZE** — all engines run in a background thread
4. **Review results** across the four tabs:
   * **Code Diff** — syntax-highlighted side-by-side SQL comparison
   * **Execution Plans** — plan tree comparison with cost highlighting
   * **Findings** — severity-sorted cards (CRITICAL to INFO); click any **ORA-XXXXX** code to open the error reference
   * **Recommendations** — actionable Oracle tuning steps; AI-enhanced when a provider is configured
5. **Export Report** — File → Export Report saves a self-contained HTML summary

### Batch Analysis

1. Switch to the **Batch** tab (top of the window)
2. Set **Baseline Folder** — the folder containing your baseline files
3. Set **Current Folder** — the folder containing your current/degraded files
4. Click **Run Batch** — OraTune pairs files by name across the two folders and runs them sequentially
5. Results appear in the table — each row shows a file pair and the highest severity finding
6. Click any row to see the full findings log for that pair in the detail panel below

### ORA- Error Reference

Open via **Tools → ORA- Error Reference** (`Ctrl+Shift+O`) at any time, or click any
**ORA-XXXXX** link in the Findings tab to jump directly to that error code.

The reference covers 225+ Oracle errors with cause, action, and severity rating. Use the
search box to filter by code, message text, or keyword.

### Live DB Mode

1. Switch to the **Live DB** tab (top of the window)
2. Click **Connect** and enter your Oracle connection details
3. Use the sub-tabs to run live queries:
   * **Explain Plan** — paste any SQL and click Explain to see the execution plan
   * **Top SQL** — fetch current top SQL by elapsed time; click a row to drill into its plan
   * **AWR Trends** — select a metric and date range to plot historical trend data
   * **Index Advisor** — view missing-index recommendations from the Oracle advisor
   * **Stats Health** — view tables with stale or missing optimizer statistics
   * **Plan Baselines** — browse SQL Plan Management baselines
   * **Scheduler** — monitor DBMS_Scheduler job status

***

## Tips for Best Results

* Upload **matching files** on each side — baseline SQL with current SQL, baseline plan with current plan
* For TKPROF: use the raw `.lst` or `.txt` output from the `tkprof` utility
* For AWR: both HTML (from EM/Cloud Control) and plain text formats are supported
* For execution plans:
  ```SQL
  SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(sql_id => 'YOUR_SQL_ID', format => 'ALL ALLSTATS LAST'));
  ```
* For ADR traces: rename the `.trc` file to `.dmp` before uploading
* Multiple SQL files can be uploaded at once — paired by filename, then by position
* For Batch Analysis: name files consistently across folders (e.g. `report_q1.sql` in both) so they pair correctly

***

## Project Structure

```
ora_tune/
├── main.py
├── requirements.txt
├── mypy.ini
├── OraTune.spec              ← PyInstaller spec (bundles ora_errors.json)
├── OraTune_Installer.iss     ← Inno Setup script (see "Building the Installer")
├── README.md
├── assets/
│   ├── icon.ico
│   ├── Logo.png
│   └── Logo_black_bck.jpg
├── data/
│   └── ora_errors.json       ← ORA- error reference database (225+ entries)
├── docs/
│   └── OraTune_Technical_Reference_Manual.docx
├── ui/
│   ├── main_window.py
│   ├── app_theme.py
│   ├── dialogs/
│   │   ├── annotation_dialog.py
│   │   ├── connection_dialog.py
│   │   ├── ora_error_dialog.py
│   │   └── settings_dialog.py
│   └── widgets/
│       ├── batch_panel.py
│       ├── diff_view.py
│       ├── findings_view.py
│       ├── plan_view.py
│       ├── recommendations_view.py
│       ├── session_panel.py
│       ├── upload_panel.py
│       └── live/
│           ├── awr_trend_tab.py
│           ├── baselines_tab.py
│           ├── connection_tab.py
│           ├── explain_plan_tab.py
│           ├── index_advisor_tab.py
│           ├── scheduler_tab.py
│           ├── stats_health_tab.py
│           └── top_sql_tab.py
├── core/
│   ├── models.py
│   ├── diff_engine.py
│   ├── findings_engine.py
│   ├── plan_comparator.py
│   └── reporter.py
├── parsers/
│   ├── sql_parser.py
│   ├── xplan_parser.py
│   ├── awr_parser.py
│   └── dmp_parser.py
├── services/
│   ├── ai_service.py
│   ├── analysis_service.py
│   ├── awr_trend_service.py
│   ├── baselines_service.py
│   ├── batch_analysis_service.py
│   ├── db_service.py
│   ├── index_advisor_service.py
│   ├── ora_error_service.py
│   ├── report_service.py
│   ├── scheduler_service.py
│   ├── session_service.py
│   ├── stats_service.py
│   └── top_sql_service.py
├── storage/
│   ├── database.py
│   └── session_repo.py
└── tests/                    ← pytest suite
    ├── core/
    │   ├── test_connection_profile.py
    │   ├── test_diff_engine.py
    │   ├── test_findings_engine.py
    │   ├── test_plan_comparator.py
    │   └── test_reporter.py
    ├── parsers/
    │   └── test_xplan_parser.py
    ├── services/
    │   ├── test_ai_service.py
    │   ├── test_analysis_service.py
    │   ├── test_awr_trend_service.py
    │   ├── test_baselines_service.py
    │   ├── test_batch_analysis_service.py
    │   ├── test_db_service.py
    │   ├── test_index_advisor_service.py
    │   ├── test_ora_error_service.py
    │   ├── test_scheduler_service.py
    │   ├── test_session_service.py
    │   ├── test_stats_service.py
    │   └── test_top_sql_service.py
    └── storage/
        └── test_session_repo.py
```

***

## Version History

| Version | Changes                                                                                                                                                                                  |
| ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2.2.1   | Security and code-quality hardening: API keys moved from the settings file to the OS credential store (`keyring`); all schema-name inputs in the Stats Health queries parameterized; HTML report output HTML-escaped; structured logging via `structlog`; empty schema selection in Stats Health now scans all accessible schemas; removal of dead and duplicate modules. |
| 2.2     | **Batch Analysis** — multi-pair folder-level analysis with severity summary table. **ORA- Error Reference** — searchable offline database of 225+ Oracle errors; clickable from Findings. |
| 2.1     | **Live DB** — AWR Trends, Index Advisor, Stats Health, Plan Baselines, Scheduler tabs. Full Oracle advisor and SPM integration.                                                           |
| 2.0     | Full rework: PyQt6, session management sidebar, Live DB mode (Explain Plan, Top SQL), dark theme, multi-provider AI (Claude, OpenAI, Azure, Copilot).                                    |
| 1.2     | Multi-provider AI support: ChatGPT (OpenAI), Azure OpenAI, GitHub Copilot alongside Claude. Provider selector in Settings.                                                               |
| 1.1     | Added `.dmp` file support: Data Pump, ADR trace, SQL\*Plus spool, SQLT/SQLTXPLAIN. DMP-specific findings.                                                                                |
| 1.0     | Initial release: SQL/PLSQL diff, DBMS\_XPLAN comparison, AWR/TKPROF parsing, hybrid AI/offline recommendations, HTML export.                                                            |
