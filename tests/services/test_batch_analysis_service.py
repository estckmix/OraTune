from services.batch_analysis_service import BatchWorker
from unittest.mock import MagicMock
import os
from unittest.mock import patch
from services.batch_analysis_service import match_pairs


def test_match_pairs_happy_path() -> None:
    side = {
        "/base": ["order_query.xml", "customer_rpt.sql", "inv_search.xml"],
        "/curr": ["order_query.xml", "customer_rpt.sql", "inv_search.xml"],
    }
    with patch(
        "services.batch_analysis_service.os.listdir", side_effect=lambda d: side[d]
    ):
        pairs, unmatched = match_pairs("/base", "/curr")
    assert len(pairs) == 3
    assert unmatched == []
    assert pairs[0] == (
        os.path.join("/base", "customer_rpt.sql"),
        os.path.join("/curr", "customer_rpt.sql"),
    )


def test_match_pairs_unmatched() -> None:
    side = {
        "/base": ["order_query.xml", "customer_rpt.sql", "extra_file.xml"],
        "/curr": ["order_query.xml", "customer_rpt.sql"],
    }
    with patch(
        "services.batch_analysis_service.os.listdir", side_effect=lambda d: side[d]
    ):
        pairs, unmatched = match_pairs("/base", "/curr")
    assert len(pairs) == 2
    assert "extra_file.xml" in unmatched


def test_match_pairs_empty_folders() -> None:
    with patch("services.batch_analysis_service.os.listdir", return_value=[]):
        pairs, unmatched = match_pairs("/base", "/curr")
    assert pairs == []
    assert unmatched == []


def test_batch_worker_emits_empty_summary_when_no_api_key() -> None:
    mock_session = MagicMock()
    mock_session.findings = []
    with (
        patch(
            "services.batch_analysis_service.ai_service.get_api_key", return_value=""
        ),
        patch("services.batch_analysis_service.AnalysisWorker") as MockWorker,
    ):
        MockWorker.return_value.run_analysis.return_value = mock_session
        worker = BatchWorker([("/fake/b.xml", "/fake/c.xml")])
        summaries = []
        worker.batch_done.connect(lambda s: summaries.append(s))
        worker.run()
    assert summaries == [""]
