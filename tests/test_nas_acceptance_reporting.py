"""A completed differing comparison must remain visible in the acceptance matrix."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def report(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    helper = importlib.import_module("summarize_nas_acceptance_scope")
    return helper.prepared_comparison_lines


def evidence(quality=(8, 7), web=(20, 20), *, success=False, matching=False):
    return {
        "all_required_groups_executed_both": True,
        "no_migration_execution_difference_observed": matching,
        "workload_success_both": success,
        "suites": {
            suite: {"engines": {
                engine: {"passed_groups": count, "checks_executed": total}
                for engine, count in zip(("jenkins", "leroy"), counts, strict=True)}}
            for suite, counts, total in (("web", web, 21), ("quality", quality, 8))},
    }


def test_completed_engine_difference_is_reported_without_equivalence(report):
    text = "\n".join(report(evidence()))
    assert "Jenkins: 20/21 Webgruppen, 8/8 Qualitätsgruppen" in text
    assert "Leroy: 20/21 Webgruppen, 7/8 Qualitätsgruppen" in text
    assert "Ausführungsabweichung bleibt offen" in text
    assert "nicht gleichwertig abgenommen" in text
    assert "ersetzen diese Anwendungsläufe nicht" in text


def test_matching_failures_are_not_successful_acceptance(report):
    text = "\n".join(report(evidence(quality=(7, 7), matching=True)))
    assert "Leroy: 20/21 Webgruppen, 7/8 Qualitätsgruppen" in text
    assert "fehlgeschlagenen Gruppen bleiben rot" in text
    assert "unter beiden Engines erfolgreich" not in text


def test_incomplete_comparison_has_no_completion_claim(report):
    value = evidence()
    value["all_required_groups_executed_both"] = False
    assert report(value) == []


def test_only_matching_green_workloads_get_success_statement(report):
    text = "\n".join(report(evidence(quality=(8, 8), web=(21, 21), success=True, matching=True)))
    assert "unter beiden Engines erfolgreich" in text
    with pytest.raises(AssertionError):
        report(evidence(quality=(8, 8), web=(21, 21), success=True))
