"""Generate the current twelve-pipeline matrix without promoting historic candidates."""

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone

from nas_ssh import ROOT
from stage_nas_production_graphato import COMMIT


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def prepared_comparison_lines(prepared):
    """Report each engine's actual outcomes, including completed differing runs."""
    if not prepared or not prepared.get("all_required_groups_executed_both"):
        return []
    outcomes = []
    for engine, name in (("jenkins", "Jenkins"), ("leroy", "Leroy")):
        values = []
        for suite, label in (("web", "Webgruppen"), ("quality", "Qualitätsgruppen")):
            result = prepared["suites"][suite]["engines"][engine]
            assert 0 <= result["passed_groups"] <= result["checks_executed"]
            values.append(f"{result['passed_groups']}/{result['checks_executed']} {label}")
        outcomes.append(name + ": " + ", ".join(values))
    lines = ["", "Der vollständige zusätzliche Graphato-Gruppenvergleich ist abgeschlossen. "
             + "; ".join(outcomes) + "."]
    if not prepared["no_migration_execution_difference_observed"]:
        lines.append("Eine Ausführungsabweichung bleibt offen; der vollständige Vergleich ist nicht gleichwertig abgenommen.")
    if not prepared["workload_success_both"]:
        lines.append("Die fehlgeschlagenen Gruppen bleiben rot; Betriebsprüfungen und Einzelproben ersetzen diese Anwendungsläufe nicht.")
    else:
        assert prepared["no_migration_execution_difference_observed"]
        lines.append("Die zusätzlichen Release-Läufe mit allen erforderlichen Prüfgruppen sind unter beiden Engines erfolgreich.")
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graphato-commit", help="Completed frozen-master comparison to use explicitly")
    args = parser.parse_args()
    commit = args.graphato_commit or COMMIT
    assert re.fullmatch(r"[a-f0-9]{40}", commit)
    base = ROOT / "test-results/nas-parity/followup"
    review = read(base / "production-source-review/review.json")
    scope = read(base / "production-source-review/nas-only-scope.json")
    assert scope["user_authorized_exclusion"] and scope["included_pipeline_count"] == 12
    assert scope["optional_local_linux_pool_stopped"] and scope["optional_local_linux_pool_auto_restart_disabled"]
    current = base / "candidates/graphato" / commit
    frozen_master = bool(args.graphato_commit)
    if frozen_master:
        frozen = read(current / "frozen-master.json")
        complete = read(current / "master-acceptance-complete.json")
        assert frozen["commit"] == complete["commit"] == commit
        assert not frozen["application_patches_applied"] and not complete["application_patches_applied"]
    analysis = read(current / "current-source-analysis.json") if (current / "current-source-analysis.json").exists() else None
    if analysis is None and (current / "current-source-outcomes.json").exists():
        analysis = read(current / "current-source-outcomes.json")
    prepared_path = current / "scenarios/root-private-existing-host/analysis.json"
    prepared = read(prepared_path) if prepared_path.exists() else None
    if prepared:
        assert prepared["commit"] == commit and prepared["same_active_build_both"]
        assert prepared["same_prepared_host_snapshot_both"] and not prepared["application_patches_applied"]
    rows = []
    for reviewed in review["pipelines"]:
        name = reviewed["pipeline"]
        row = {"pipeline": name, "included": reviewed["included_in_nas_acceptance"],
               "production_commit": reviewed["production_commit"],
               "supporting_application_commit": reviewed.get("supporting_application_commit"),
               "application_patches_applied": False, "workload_success_both": False}
        if not row["included"]:
            row.update(state="excluded_by_user", note="Antares-Artefakt gemäß Nutzerentscheidung ausgenommen; Definition und Ergebnisse erhalten.",
                       evidence="test-results/nas-parity/followup/production-source-review/nas-only-scope.json")
        elif name.startswith("graphato-"):
            if name == "graphato-bootstrap-host":
                row["source_audit_supporting_application_commit"] = row["supporting_application_commit"]
                row["supporting_application_commit"] = commit
            pair_path = current / name / "pair.json"
            pair = read(pair_path) if pair_path.exists() else {}
            row.update(state="current_source_comparison_pending", note="Unveränderter Produktionsstand wird auf dem NAS verglichen.",
                       evidence=pair_path.relative_to(ROOT).as_posix(),
                       jenkins_build=pair.get("jenkins", {}).get("number"),
                       jenkins_result=pair.get("jenkins", {}).get("result"),
                       leroy_run=pair.get("leroy_run"), leroy_status=pair.get("leroy_status"))
            source_commit = pair.get("commit", row["production_commit"] if name == "graphato-bootstrap-host" else commit)
            row.update(comparison_commit=source_commit, graphato_application_commit=commit,
                       comparison_source_kind="frozen_master_revision" if frozen_master and name != "graphato-bootstrap-host" else "observed_production_revision",
                       graphato_application_source_kind="frozen_master_revision" if frozen_master else "observed_production_revision",
                       production_commit_matches_comparison=row["production_commit"] == source_commit)
            if frozen_master:
                row["note"] = "Explizit eingefrorener Master wird unverändert auf dem NAS verglichen."
            if analysis and name in analysis["pipelines"]:
                result = analysis["pipelines"][name]
                row.update(result)
                filename = "current-source-outcomes.json" if analysis.get("receipt_and_failure_analysis_pending") else "current-source-analysis.json"
                row["evidence"] = (current / filename).relative_to(ROOT).as_posix()
            if prepared and name in prepared["pipelines"]:
                row["fresh_target_result"] = {**row, "scope": "Separate fresh installation per engine"}
                row.update(prepared["pipelines"][name])
                row["evidence"] = prepared_path.relative_to(ROOT).as_posix()
                row["comparison_scenario"] = "root-private-existing-host"
        elif name == "home-lab-ci":
            path = base / "home-lab-build/comparison.json"
            result = read(path)
            assert result["commit"] == row["production_commit"] and not result["application_patches_applied"]
            assert result["real_build_and_push_both"] and result["workload_success_both"]
            row.update(state="validated_current_source_scenario", workload_success_both=True,
                       jenkins_build=result["jenkins"]["number"], leroy_run=result["leroy_run"],
                       evidence=path.relative_to(ROOT).as_posix(),
                       note="Tatsächlicher Build/Push und Laufzeitinhalte beider Images stimmen überein; Zeitstempel und Python-Bytecode ausgenommen.")
        else:
            result = reviewed["historical_comparison_evidence"]
            assert reviewed["same_source_historical_comparison"] and not result["application_patches_applied"]
            row.update(jenkins_build=result["jenkins_build"], leroy_run=result["leroy_run"],
                       evidence="test-results/nas-parity/aligned/" + name + "/comparison.json")
            if result.get("complete_pipeline_parity") and result.get("workload_success"):
                row.update(state="validated_current_source_scenario", workload_success_both=True,
                           note="Gleiche aktuelle Quellen/Skripte; ursprünglicher isolierter NAS-Szenarionachweis weiterhin gültig.")
            else:
                assert result.get("leroy_runtime_correction_validated")
                assert result["jenkins_job_success_but_application_unhealthy"] and result["leroy_application_healthy"]
                row.update(state="validated_leroy_behavior_difference",
                           note="Gleiches Image/Compose: Jenkins meldet Erfolg bei ungesunder Anwendung; Leroy korrigiert UID-Rechte und prüft Health. Keine strikte Verhaltensgleichheit.")
        rows.append(row)
    included = [row for row in rows if row["included"]]
    assert len(included) == 12 and len(rows) == 13
    counts = dict(Counter(row["state"] for row in included))
    record = {"at": datetime.now(timezone.utc).isoformat(), "topology": scope["deployment_topology"],
              "included_pipeline_count": 12, "excluded": ["antares-ci"], "pipelines": rows,
              "included_states": counts, "all_included_tasks_successful_both": all(row["workload_success_both"] for row in included),
              "production_modified": False, "production_cutover": False, "production_replacement_ready": False,
              "graphato_comparison_commit": commit, "comparison_sources_frozen": True,
              "newer_revision_workload_parity_claimed": False,
              "scope": "Original sources frozen at the source audit, compared on isolated NAS workloads; later production revisions are separate"}
    if frozen_master:
        record["scope"] = "Explicit frozen Graphato master plus retained source-audit comparisons for other pipelines; no production cutover"
        operations = current / "final-operations-acceptance.json"
        record["final_operations_acceptance"] = {
            "passed": read(operations)["passed"] if operations.exists() else False,
            "acceptance_scope": read(operations).get("acceptance_scope") if operations.exists() else None,
            "evidence": operations.relative_to(ROOT).as_posix() if operations.exists() else None,
        }
        previous = current / "acceptance-before-frozen-master"
        previous.mkdir(exist_ok=True)
        for source in (base / "nas-acceptance-matrix.json", ROOT / "docs/nas-acceptance.md"):
            destination = previous / source.name
            if source.exists() and not destination.exists():
                destination.write_bytes(source.read_bytes())
    lines = ["# Aktuelle NAS-Abnahme", "", "Controller und CI-Worker bleiben auf dem NAS. Antares ist als Artefakt ausgenommen.",
             "Der zusätzliche lokale Linux-Testpool ist gestoppt; automatischer Wiederanlauf ist aus.",
             "Jenkins und produktive Anwendungen wurden durch diese Abnahme nicht umgestellt.", "", "Die Matrix unterscheidet erfolgreiche Aufgaben, belegte Verhaltensunterschiede und fehlgeschlagene Prüfungen.",
             "Die Vergleichsquellen sind eingefroren. Inzwischen neuere Produktionscommits sind damit nicht unter Leroy abgenommen.",
             "Historische Anwendungspatches gelten nicht als Voraussetzung für Leroy.", "", "| Pipeline | Stand | Nachweis |", "| --- | --- | --- |"]
    labels = {"excluded_by_user": "Ausgenommen", "current_source_comparison_pending": "Vergleich läuft/offen",
              "validated_current_source_scenario": "Vergleichsstand: Szenario erfolgreich",
              "validated_leroy_behavior_difference": "Validierte Leroy-Erweiterung",
              "matching_application_failure": "Gleicher Anwendungsfehler",
              "matching_failed_checks": "Gleiche fehlgeschlagene Gruppen; Ursachenprüfung offen",
              "matching_downstream_failure": "Gleiche Weitergabe der Kindlauf-Fehler",
              "completed_execution_pending_analysis": "Läufe abgeschlossen; Ergebnisprüfung offen",
              "failed_execution_pending_analysis": "Läufe fehlgeschlagen; Ursachenprüfung offen",
              "not_executed_after_ci_failure": "Nach fehlgeschlagenem CI nicht ausgeführt",
              "execution_difference": "Ausführungsabweichung offen"}
    for row in rows:
        lines.append("| " + row["pipeline"] + " | " + labels.get(row["state"], row["state"]) + " | [Beleg](../" + row["evidence"] + ") |")
    lines += prepared_comparison_lines(prepared)
    if frozen_master and operations.exists():
        result = read(operations)
        assert result["passed"] and result["acceptance_scope"]["production_replacement_ready"] is False
        lines += ["", "Die abschließenden Image-, Neustart- und Sicherungsprüfungen des eigenen NAS-Teststacks bestehen. "
                  "Ihre Abnahme gilt für die CI-Infrastruktur; die Anwendungsergebnisse oben bleiben bestehen."]
    lines += ["", "## Bewertungsgrenzen", "",
              "- Home-Lab: echte Builds und Pushes; Image-Inhalte und Konfiguration sind verglichen, keine Byteidentität der Image-Dateien behauptet.",
              "- Nikicas-Hub: Leroy korrigiert Persistenzrechte und wartet auf einen gesunden Dienst. Der gleiche Jenkins-Szenariolauf meldete Erfolg, obwohl die Anwendung ungesund war.",
              "- Graphato: " + ("explizit eingefrorener Master" if frozen_master else "ursprünglicher Produktionscommit") + " `" + commit + "` ist ohne Anwendungspatches auf jeweils frischem Ziel geprüft. Der frühere grüne Kandidat `9968c226f943` ersetzt diesen Nachweis nicht.",
              *(["- Graphato-Prüfgruppen: zusätzliches Szenario mit einem bereits vorhandenen privaten Steuerverzeichnis. Beide Engines erhalten dieselbe eingefrorene Anwendung und denselben VM-Snapshot. Der gesonderte Fehler bei der frischen Installation bleibt dokumentiert."] if prepared else []),
              "- Antares: keine erfolgreiche NAS-Ausführung behauptet. Seine bisherigen Quell-, Patch- und Ausführungsbelege bleiben erhalten.",
              "", "Die vollständige Produktionsfreigabe bleibt offen. "
              + ("Der geprüfte Master gilt nur für diesen Commit. Produktionsziele, Zugangsdaten und Trigger sind vor der freigegebenen Umschaltung einzurichten."
                 if frozen_master else "Dazu gehören die Abnahme neuerer Quellen und die Bewertung der belegten Verhaltensunterschiede.")
              + " Details: [NAS-Vergleich](nas-parity.md).", ""]
    (base / "nas-acceptance-matrix.json").write_text(json.dumps(record, indent=2) + "\n")
    (ROOT / "docs/nas-acceptance.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"included": 12, "excluded": "antares-ci", "states": counts, "production_replacement_ready": False}))


if __name__ == "__main__":
    main()
