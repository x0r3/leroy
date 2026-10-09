# Aktuelle NAS-Abnahme

Aktuelle Einordnung und nächster Plan vom 9. Oktober: [status.md](status.md).
Die Detailbelege unter `test-results/` sind lokal erhalten und vom Git-Repository
ausgeschlossen. Die Matrix hält insbesondere den ersten vollständigen
Gruppenvergleich fest; spätere Proben werden darunter eingeordnet.

Controller und CI-Worker bleiben auf dem NAS. Antares ist als Artefakt ausgenommen.
Der zusätzliche lokale Linux-Testpool ist gestoppt; automatischer Wiederanlauf ist aus.
Jenkins und produktive Anwendungen wurden durch diese Abnahme nicht umgestellt.

Die Matrix unterscheidet erfolgreiche Aufgaben, belegte Verhaltensunterschiede und fehlgeschlagene Prüfungen.
Die Vergleichsquellen sind eingefroren. Inzwischen neuere Produktionscommits sind damit nicht unter Leroy abgenommen.
Historische Anwendungspatches gelten nicht als Voraussetzung für Leroy.

| Pipeline | Stand | Nachweis |
| --- | --- | --- |
| antares-ci | Ausgenommen | [Beleg](../test-results/nas-parity/followup/production-source-review/nas-only-scope.json) |
| gitea-bootstrap-repo | Vergleichsstand: Szenario erfolgreich | [Beleg](../test-results/nas-parity/aligned/gitea-bootstrap-repo/comparison.json) |
| graphato-bootstrap-host | Vergleichsstand: Szenario erfolgreich | [Beleg](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/current-source-analysis.json) |
| graphato-ci | Vergleichsstand: Szenario erfolgreich | [Beleg](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/current-source-analysis.json) |
| graphato-postdeploy-quality | Ausführungsabweichung offen | [Beleg](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/scenarios/root-private-existing-host/analysis.json) |
| graphato-postdeploy-web | Gleicher Anwendungsfehler | [Beleg](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/scenarios/root-private-existing-host/analysis.json) |
| graphato-release-acceptance | Ausführungsabweichung offen | [Beleg](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/scenarios/root-private-existing-host/analysis.json) |
| home-lab-ci | Vergleichsstand: Szenario erfolgreich | [Beleg](../test-results/nas-parity/followup/home-lab-build/comparison.json) |
| music-library-sync-smartphone | Vergleichsstand: Szenario erfolgreich | [Beleg](../test-results/nas-parity/aligned/music-library-sync-smartphone/comparison.json) |
| nikicas-hub-bootstrap-host | Validierte Leroy-Erweiterung | [Beleg](../test-results/nas-parity/aligned/nikicas-hub-bootstrap-host/comparison.json) |
| nikicas-hub-ci | Vergleichsstand: Szenario erfolgreich | [Beleg](../test-results/nas-parity/aligned/nikicas-hub-ci/comparison.json) |
| nikicas-hub-deploy | Validierte Leroy-Erweiterung | [Beleg](../test-results/nas-parity/aligned/nikicas-hub-deploy/comparison.json) |
| paperless-ngx-bootstrap-rules | Vergleichsstand: Szenario erfolgreich | [Beleg](../test-results/nas-parity/aligned/paperless-ngx-bootstrap-rules/comparison.json) |

Der vollständige zusätzliche Graphato-Gruppenvergleich ist abgeschlossen. Jenkins: 20/21 Webgruppen, 8/8 Qualitätsgruppen; Leroy: 20/21 Webgruppen, 7/8 Qualitätsgruppen.
Spätere vollständige Rust-Vergleichsläufe bestehen unter beiden Engines; der
zusätzliche vollständige Leroy-Release-Lauf besteht alle acht Qualitätsgruppen.
Die frühere Ausführungsabweichung ist damit noch nicht ursächlich erklärt.
Die Original-Release-Abnahme bleibt am Browser-Soak rot; der vollständige
Vergleich ist nicht gleichwertig abgenommen.
Die fehlgeschlagenen Gruppen bleiben rot; Betriebsprüfungen und Einzelproben ersetzen diese Anwendungsläufe nicht.

Die abschließenden Image-, Neustart- und Sicherungsprüfungen des eigenen NAS-Teststacks bestehen. Ihre Abnahme gilt für die CI-Infrastruktur; die Anwendungsergebnisse oben bleiben bestehen.

## Bewertungsgrenzen

- Home-Lab: echte Builds und Pushes; Image-Inhalte und Konfiguration sind verglichen, keine Byteidentität der Image-Dateien behauptet.
- Nikicas-Hub: Leroy korrigiert Persistenzrechte und wartet auf einen gesunden Dienst. Der gleiche Jenkins-Szenariolauf meldete Erfolg, obwohl die Anwendung ungesund war.
- Graphato: explizit eingefrorener Master `0ad540dd578033d45e4d0c25d89fbe57b32102a4` ist ohne Anwendungspatches auf jeweils frischem Ziel geprüft. Der frühere grüne Kandidat `9968c226f943` ersetzt diesen Nachweis nicht.
- Graphato-Prüfgruppen: zusätzliches Szenario mit einem bereits vorhandenen privaten Steuerverzeichnis. Beide Engines erhalten dieselbe eingefrorene Anwendung und denselben VM-Snapshot. Der gesonderte Fehler bei der frischen Installation bleibt dokumentiert.
- Antares: keine erfolgreiche NAS-Ausführung behauptet. Seine bisherigen Quell-, Patch- und Ausführungsbelege bleiben erhalten.

Die vollständige Produktionsfreigabe bleibt offen. Der geprüfte Master gilt nur für diesen Commit. Produktionsziele, Zugangsdaten und Trigger sind vor der freigegebenen Umschaltung einzurichten. Details: [NAS-Vergleich](nas-parity.md).
