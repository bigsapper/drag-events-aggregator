"""Tests for crawl runtime metrics helpers."""

import json
import sys
from unittest.mock import patch

import crawl


def test_format_duration_handles_seconds_minutes_and_hours():
    assert crawl.format_duration(12) == "12s"
    assert crawl.format_duration(75) == "1m 15s"
    assert crawl.format_duration(3661) == "1h 1m 1s"


def test_summarize_metrics_uses_successful_runs_for_timing():
    summary = crawl.summarize_metrics([
        {"status": "success", "elapsed_seconds": 10},
        {"status": "error", "elapsed_seconds": 999},
        {"status": "success", "elapsed_seconds": 20},
    ])

    assert summary["recorded_runs"] == 3
    assert summary["successful_runs"] == 2
    assert summary["average_seconds"] == 15.0
    assert summary["median_seconds"] == 15.0
    assert summary["min_seconds"] == 10
    assert summary["max_seconds"] == 20
    assert summary["p95_seconds"] == 20


def test_summarize_metrics_without_successful_durations_returns_basic_summary():
    entries = [{"status": "error", "elapsed_seconds": "n/a"}]
    summary = crawl.summarize_metrics(entries)

    assert summary["recorded_runs"] == 1
    assert summary["successful_runs"] == 0
    assert summary["last_run"] == entries[-1]
    assert "average_seconds" not in summary


def test_load_metric_entries_handles_missing_file_and_blank_lines(tmp_path):
    missing = tmp_path / "missing.jsonl"
    assert crawl.load_metric_entries(missing) == []

    metrics_log = tmp_path / "crawl_metrics.jsonl"
    metrics_log.write_text('\n{"run_id":"run-1","status":"success","elapsed_seconds":10}\n\n')
    entries = crawl.load_metric_entries(metrics_log)

    assert len(entries) == 1
    assert entries[0]["run_id"] == "run-1"


def test_record_run_metrics_appends_jsonl_and_updates_summary(tmp_path):
    metrics_log = tmp_path / "crawl_metrics.jsonl"
    summary_file = tmp_path / "crawl_metrics_summary.json"

    first = {
        "run_id": "run-1",
        "started_at": "2026-04-01T00:00:00+00:00",
        "finished_at": "2026-04-01T00:01:00+00:00",
        "status": "success",
        "elapsed_seconds": 60,
    }
    second = {
        "run_id": "run-2",
        "started_at": "2026-04-02T00:00:00+00:00",
        "finished_at": "2026-04-02T00:02:00+00:00",
        "status": "success",
        "elapsed_seconds": 120,
    }

    crawl.record_run_metrics(first, metrics_log=metrics_log, summary_file=summary_file)
    summary = crawl.record_run_metrics(second, metrics_log=metrics_log, summary_file=summary_file)

    lines = metrics_log.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["run_id"] == "run-1"
    assert json.loads(lines[1])["run_id"] == "run-2"

    written_summary = json.loads(summary_file.read_text())
    assert summary == written_summary
    assert summary["recorded_runs"] == 2
    assert summary["successful_runs"] == 2
    assert summary["average_seconds"] == 90.0
    assert summary["last_run"]["run_id"] == "run-2"


def test_log_error_writes_context_details_and_message(tmp_path):
    error_log = tmp_path / "crawl_errors.log"

    with patch("crawl.should_log_errors", return_value=True):
        crawl.log_error(
            "fetch_page",
            RuntimeError("boom"),
            error_log=error_log,
            details={"url": "http://example.com"},
        )

    content = error_log.read_text()
    assert "fetch_page" in content
    assert "boom" in content
    assert "url: http://example.com" in content


def test_log_error_uses_default_error_log_path_when_not_provided(tmp_path):
    default_log = tmp_path / "default.log"

    with patch("crawl.should_log_errors", return_value=True), \
         patch("crawl.get_error_log_path", return_value=default_log):
        crawl.log_error("fetch_page", RuntimeError("boom"))

    assert default_log.exists()
    assert "fetch_page" in default_log.read_text()


def test_log_error_can_include_traceback_without_trailing_newline(tmp_path):
    error_log = tmp_path / "crawl_errors.log"

    try:
        raise RuntimeError("boom")
    except RuntimeError as exc:
        with patch("crawl.should_log_errors", return_value=True), \
             patch("crawl.traceback.format_exc", return_value="TRACE"):
            crawl.log_error("fetch_page", exc, error_log=error_log, include_traceback=True)

    content = error_log.read_text()
    assert "TRACE\n" in content


def test_log_error_skips_logging_under_pytest(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_crawl_metrics.py::test")
    error_log = tmp_path / "crawl_errors.log"

    crawl.log_error("fetch_page", RuntimeError("boom"), error_log=error_log)

    assert not error_log.exists()


def test_log_error_skips_manual_test_flyer_errors(tmp_path):
    error_log = tmp_path / "crawl_errors.log"

    with patch.dict("crawl.os.environ", {}, clear=False):
        crawl.log_error(
            "run_extraction.process_flyer",
            RuntimeError("boom"),
            error_log=error_log,
            details={"flyer_path": "tests/test-flyers/bad-boys-mayhem.jpg"},
        )

    assert not error_log.exists()


def test_get_error_log_path_uses_production_path(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert crawl.get_error_log_path() == crawl.ERROR_LOG


def test_main_skips_runtime_metric_recording_under_pytest(monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_crawl_metrics.py::test")

    with patch.object(sys, "argv", ["crawl.py"]), \
         patch("crawl.json.loads", return_value=[]), \
         patch("crawl.run_extraction", return_value={}), \
         patch("crawl.save_state"), \
         patch("crawl.time.sleep"), \
         patch("crawl.record_run_metrics") as mock_record:
        crawl.main()

    mock_record.assert_not_called()


def test_should_record_runtime_metrics_reflects_pytest_env(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert crawl.should_record_runtime_metrics() is True

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_crawl_metrics.py::test")
    assert crawl.should_record_runtime_metrics() is False


def test_should_log_errors_reflects_pytest_and_test_flyers(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert crawl.should_log_errors() is True
    assert crawl.should_log_errors({"flyer_path": "/tmp/flyer.jpg"}) is True
    assert crawl.should_log_errors({"flyer_path": "tests/test-flyers/sample.jpg"}) is False

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_crawl_metrics.py::test")
    assert crawl.should_log_errors({"flyer_path": "/tmp/flyer.jpg"}) is False


def test_main_metrics_mode_prints_summary_and_returns(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with patch.object(sys, "argv", ["crawl.py", "--metrics"]), \
         patch("crawl.load_metric_entries", return_value=[{"status": "success", "elapsed_seconds": 10}]) as mock_load, \
         patch("crawl.print_metrics_summary") as mock_print:
        crawl.main()

    mock_load.assert_called_once()
    mock_print.assert_called_once()


def test_print_metrics_summary_outputs_full_stats(capsys):
    crawl.print_metrics_summary({
        "recorded_runs": 3,
        "successful_runs": 2,
        "average_seconds": 125,
        "median_seconds": 120,
        "min_seconds": 60,
        "max_seconds": 180,
        "p95_seconds": 180,
        "last_run": {
            "status": "success",
            "started_at": "2026-04-01T00:00:00+00:00",
            "elapsed_seconds": 180,
        },
    })

    out = capsys.readouterr().out
    assert "Crawl metrics summary" in out
    assert "recorded runs:   3" in out
    assert "successful runs: 2" in out
    assert "average runtime: 2m 5s" in out
    assert "median runtime:  2m 0s" in out
    assert "min runtime:     1m 0s" in out
    assert "max runtime:     3m 0s" in out
    assert "p95 runtime:     3m 0s" in out
    assert "last run:        success at 2026-04-01T00:00:00+00:00 (3m 0s)" in out


def test_print_metrics_summary_omits_optional_sections_when_missing(capsys):
    crawl.print_metrics_summary({
        "recorded_runs": 1,
        "successful_runs": 0,
        "last_run": None,
    })

    out = capsys.readouterr().out
    assert "Crawl metrics summary" in out
    assert "average runtime" not in out
    assert "last run:" not in out


def test_print_metrics_summary_handles_empty_history(capsys):
    crawl.print_metrics_summary({})

    out = capsys.readouterr().out
    assert "No crawl metrics recorded yet." in out


def test_main_records_metrics_outside_pytest_when_extraction_returns_non_dict(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with patch.object(sys, "argv", ["crawl.py"]), \
         patch("crawl.json.loads", return_value=[]), \
         patch("crawl.run_extraction", return_value="not-a-dict"), \
         patch("crawl.save_state"), \
         patch("crawl.time.sleep"), \
         patch("crawl.record_run_metrics", return_value={"average_seconds": 10, "median_seconds": 10}) as mock_record:
        crawl.main()

    recorded = mock_record.call_args[0][0]
    assert recorded["extraction"] == {}


def test_main_logs_and_reraises_top_level_error_outside_pytest(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with patch.object(sys, "argv", ["crawl.py"]), \
         patch("crawl.load_state", side_effect=RuntimeError("boom")), \
         patch("crawl.log_error") as mock_log, \
         patch("crawl.record_run_metrics", return_value={}) as mock_record, \
         patch("crawl.time.sleep"):
        try:
            crawl.main()
        except RuntimeError as exc:
            assert str(exc) == "boom"
        else:
            raise AssertionError("crawl.main() did not re-raise the top-level error")

    mock_log.assert_called_once()
    recorded = mock_record.call_args[0][0]
    assert recorded["status"] == "error"
    assert recorded["error"] == "boom"
