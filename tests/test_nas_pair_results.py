"""Partial upstream output cannot turn a failed NAS comparison into acceptance."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def parser(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("complete_nas_antares_tmpfs_pair")


def test_failed_integration_keeps_passed_failed_and_skipped_counts(parser):
    rows = parser.observed_test_results(" Tests 636 passed (636)\n Tests 1 failed | 66 passed | 35 skipped (102)\n")
    assert rows == [{"total": 636, "passed": 636}, {"total": 102, "failed": 1, "passed": 66, "skipped": 35}]


def test_absent_browser_summary_is_incomplete(parser):
    assert parser.browser_summary("Test interrupted before results") == {"complete": False}


def test_truncated_browser_summary_is_incomplete(parser):
    assert parser.browser_summary("  23 passed\n  3 skipped\n") == {"complete": False, "passed": 23, "skipped": 3}


def test_complete_failed_browser_summary_retains_failures(parser):
    assert parser.browser_summary("  24 passed\n  3 skipped\n  2 failed\n") == {
        "complete": True, "passed": 24, "skipped": 3, "failed": 2,
    }
