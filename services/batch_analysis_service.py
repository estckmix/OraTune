"""Batch Analysis service — folder-based multi-pair analysis."""

import os
from pathlib import Path

import structlog
from PyQt6.QtCore import QThread, pyqtSignal

from core.models import Finding
from services.analysis_service import AnalysisWorker
from services import ai_service

log = structlog.get_logger()

_SQL_EXTS = {".sql", ".pls", ".pks", ".pkb", ".prc", ".fnc", ".trg"}
_PLAN_EXTS = {".xml"}
_AWR_EXTS = {".txt", ".lst", ".html", ".htm"}
_DMP_EXTS = {".dmp"}
_ALL_EXTS = _SQL_EXTS | _PLAN_EXTS | _AWR_EXTS | _DMP_EXTS


def _classify(filepath: str) -> str:
    ext = Path(filepath).suffix.lower()
    if ext in _SQL_EXTS:
        return "sql"
    if ext in _PLAN_EXTS:
        return "xplan"
    if ext in _AWR_EXTS:
        return "awr_tkprof"
    if ext in _DMP_EXTS:
        return "dmp"
    return "unknown"


def match_pairs(
    baseline_dir: str,
    current_dir: str,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Match files in two directories by exact filename.

    Returns (pairs, unmatched) where:
      pairs     — list of (baseline_path, current_path) tuples
      unmatched — filenames present in only one directory
    """
    b_files = {
        f for f in os.listdir(baseline_dir) if Path(f).suffix.lower() in _ALL_EXTS
    }
    c_files = {
        f for f in os.listdir(current_dir) if Path(f).suffix.lower() in _ALL_EXTS
    }
    matched = b_files & c_files
    # os.path.join kept deliberately: Path() normalizes separators, and callers
    # (and tests) compare these paths as exact strings.
    pairs = [
        (os.path.join(baseline_dir, f), os.path.join(current_dir, f))
        for f in sorted(matched)
    ]
    unmatched = sorted((b_files | c_files) - matched)
    return pairs, unmatched


class BatchWorker(QThread):
    """Processes each matched pair sequentially, emitting findings as they arrive."""

    pair_done = pyqtSignal(int, str, list)  # (index, filename, findings)
    pair_error = pyqtSignal(int, str, str)  # (index, filename, error_msg)
    batch_done = pyqtSignal(str)  # AI summary text or ""

    def __init__(self, pairs: list[tuple[str, str]]) -> None:
        super().__init__()
        self._pairs = pairs

    def run(self) -> None:
        all_findings: list[Finding] = []
        for i, (baseline_path, current_path) in enumerate(self._pairs):
            filename = Path(baseline_path).name
            try:
                role = _classify(baseline_path)
                worker = AnalysisWorker(
                    {role: [baseline_path]},
                    {role: [current_path]},
                )
                session = worker.run_analysis()
                all_findings.extend(session.findings)
                self.pair_done.emit(i, filename, session.findings)
            except Exception as exc:
                self.pair_error.emit(i, filename, str(exc))

        if ai_service.get_api_key():
            try:
                summary = ai_service.generate_batch_summary(all_findings)
            except Exception as exc:
                # AI summary is optional enrichment — a provider failure must
                # not sink the batch results that were already produced.
                log.warning("batch.ai_summary_failed", error=str(exc))
                summary = ""
        else:
            summary = ""
        self.batch_done.emit(summary)
