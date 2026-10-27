# Aktuelle NAS-Abnahme

**26. Oktober 2026: NAS-Abnahme beendet und Jenkins-Ablöse verschoben.**
Der produktive Jenkins und alle sieben NAS-Anwendungen laufen regulär;
der isolierte Leroy-Testbetrieb ist gestoppt. Maßgeblich sind der
[gesicherte Zwischenstand](checkpoint-2026-10-26.md) und [status.md](status.md).
Die Detailbelege unter `test-results/` sind lokal erhalten und vom Git-Repository
ausgeschlossen. Die Matrix hält insbesondere den ersten vollständigen
Gruppenvergleich fest; spätere Proben werden darunter eingeordnet.

Im historischen NAS-Vergleich liefen Controller und CI-Worker auf dem NAS.
Antares war dort als Artefakt ausgenommen. Eine spätere Abnahme benötigt den
neuen Build-Server und einen neu festgelegten Ausführungsplan.
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
Die damalige Original-Release-Abnahme bleibt am Browser-Soak rot; der damalige vollständige
Vergleich ist nicht gleichwertig abgenommen.
Die fehlgeschlagenen Gruppen bleiben rot; Betriebsprüfungen und Einzelproben ersetzen diese Anwendungsläufe nicht.

Am 11. Oktober ist der Runtime-Import repariert und der gemeinsame Original-
Browser-Worker auf dem NAS geprüft. Zwei zusätzliche Original-Soak-Serien im
isolierten NAS-Testdaemon sind abgeschlossen: Die erste enthält je einen Erfolg
und Fehler unter Jenkins und Leroy; die fortgesetzte Folge Jenkins/Leroy/Leroy/
Jenkins besteht alle vier ausgeführten Fälle mit unveränderten Quellen, Tests,
Images und Grenzwerten. Sämtliche Cleanups und ruhigen produktiven Jenkins-
Fenster sind bestätigt. Ein separater Fixture-Start-Race bleibt erhalten und
zählt nicht als ausgeführter Soak. Die HTTP-Spuren bleiben wegen Paketverlusten
für vollständige Rate-Limit-Aussagen unqualifiziert. Diese Diagnosefälle ersetzen
die vollständigen Web-/Release-Gruppen der Matrix nicht.
[Original-Soak-Vergleich und Bewertungsgrenzen](nas-parity.md).

Die abschließenden Image-, Neustart- und Sicherungsprüfungen des eigenen NAS-Teststacks bestehen. Ihre Abnahme gilt für die CI-Infrastruktur; die Anwendungsergebnisse oben bleiben bestehen.

## Vollständige Originalläufe vom 12. Oktober

Der eingefrorene Commit `0ad540dd578033d45e4d0c25d89fbe57b32102a4` und seine
Originalquellen, Tests, Ratenlimits und Fristen bleiben unverändert. Jenkins-
Referenz `l` und Leroy-Nachprüfung `m` bestehen beide alle 21 Webgruppen mit
42 identischen erfolgreichen Fällen einschließlich des Soak-Tests. Die
ursprünglichen CI-Artefakte sind vollständig geprüft. Das erste Tabellenbild
oben bleibt ausdrücklich der historische Gruppenvergleich.

Die ergänzenden Qualitätsprotokolle zeigen bei beiden 195 bestandene Python-
Tests und eine bestandene Formatprüfung. Komponenten: Jenkins 96/98, Leroy
97/98; der Fokusfehler der Chat-Präsentation ist gemeinsam. In beiden
Vollversuchen unterschreitet das NAS während Clippy die unveränderte freie
Swap-Schutzreserve. Vollständige originale Qualitätsarchive, nachfolgende
Testinventare und Release-Gesamtquittungen fehlen. Leroy meldet zusätzlich
Lease-Erneuerungsausfälle mit `ReadTimeout`, deren vollständige Ursache offen ist.

Die ursprünglichen CI-Läufe sind terminal und die Test-VM sowie der private
Test-Jenkins aus. Die vollständigen produktiven Jenkins-Historien bestätigen
ruhige Messfenster. Die neue Leroy-Supervisor-Korrektur ist als Image-Unterschied
zur erhaltenen Jenkins-Referenz offengelegt. 18 zusätzliche UI-Ansichten
bestehen technisch und nach direkter Sichtprüfung; insgesamt 359 NAS-Ansichten.
Die vollständige Produktionsfreigabe bleibt offen.
[Originalnachweise und Grenzen](nas-full-release.md).

Die anschließende gemeinsame Serie `n` ist ebenfalls unter beiden Engines
terminal beendet. Die gezielte Korrektur blockierender Systemdiagnosen ist
installiert; Originalquellen, Tests und Fristen bleiben unverändert. Im neuen
Paar stimmen Supervisor-Image, Infrastruktur, Gast-/Host-Ressourcen und
Ausführungshilfen überein. Jenkins besteht 42/42 Webfälle, Leroy 41/42. Der
Dev-Umgebungs-Browserfall scheitert unter Leroy an der ursprünglichen
5-Sekunden-Sichtbarkeitsprüfung; die Ursache ist offen. Beide vollständigen
originalen Webarchive einschließlich Fehlerdiagnosen sind geprüft.

Beide bestehen Python 195/195, dieselben Komponenten 97/98 und Format. Unter
Clippy folgen bei beiden erneut NAS-Speicher-/I/O-Stau, Controller-Timeouts
und die Swap-Sicherung. Leroy verliert seine Lease. Die vollständigen originalen
Qualitätsarchive und Gesamtquittungen fehlen weiterhin. Die gepufferte
Diagnosezustellung allein löst diesen zusätzlichen Lastengpass nicht.
Produktiver Jenkins führt Postdeploy-Qualität auf einem externen Linux-Ziel aus;
unsere zusätzliche Ziel-VM liegt auf dem NAS. Produktions-Performanceparität
wird daraus nicht abgeleitet.

Alle Ursprungsläufe und Worker dieses Vergleichs sind beendet, VM und privater
Jenkins aus. Die vollständigen produktiven Jenkins-Historien bestätigen ruhige
Messfenster. 18 weitere Desktop-/Mobilansichten und ein echter Artefakt-Download
bestehen technisch und nach direkter Sichtprüfung; insgesamt 377 historische
NAS-Ansichten. Details: [Log-Korrektur](nas-control-logging.md) und
[Originalvergleich](nas-full-release.md). Die Produktionsfreigabe bleibt offen.

Die anschließenden unveränderten Einzelgruppen reproduzieren den Browserfehler
auch unter Jenkins und bestehen danach unter beiden Engines. Diese geprüften
Originalarchive ersetzen keine vollständige Web-/Release-Abnahme. Wirksame
Speicherreservierung und qualifizierte DB-Namensauflösung sind im eigenen
Teststack installiert. Zwei Clippy-Proben mit einem passend größeren 10-GiB-
Gast überschreiten die unveränderte RAM- beziehungsweise Swap-Reserve; im
zweiten Lauf verliert Leroy zusätzlich die Lease. Die vollständige Stabilität
ist weiterhin nicht belegt. Alle Läufe sind terminal, eigene Jobworker,
Test-VM und privater Jenkins aus. Die historische Zahl der technisch und
direkt visuell geprüften NAS-Ansichten beträgt nun 395. Details:
[Speicher und Originalgruppen](nas-control-memory.md),
[vorbereitetes Ressourcenfenster](nas-resource-window.md).

Das danach freigegebene feste Zweistundenfenster besteht bei der gezielten
Folgeprobe die unveränderte Originalgruppe `server-clippy` unter Leroy #162
und privatem Jenkins #21, ohne wiederverwendete Erfolge und mit vollständigem
Cleanup. Release-Identität, fünf Build-Basis-Image-Digests, VM-Profil und
Steuerinfrastruktur sind gleich; beide Basisanwendungen bleiben gesund.
Die sieben identischen NAS-Dienste werden vor Fristende gesund wiederhergestellt.
407 historische NAS-UI-Ansichten sind technisch und direkt visuell geprüft.

Ein belegter OOM-Neustart des 256-MiB-Controllers während des Jenkins-Vergleichs
verhindert eine vollständige Stabilitätsfreigabe dieses Laufs. Die zusätzliche
SQL-Probe teilt künftig nicht mehr dessen Speicherbudget; das Controllerlimit
ist separat qualifiziert auf 512 MiB ohne Swap erhöht. Die vollständigen
Original-Pipelines nach dieser Korrektur sind noch nicht geprüft. Details:
[begrenztes Fenster und Controllerkorrektur](nas-resource-window.md).

## Bewertungsgrenzen

- Home-Lab: echte Builds und Pushes; Image-Inhalte und Konfiguration sind verglichen, keine Byteidentität der Image-Dateien behauptet.
- Nikicas-Hub: Leroy korrigiert Persistenzrechte und wartet auf einen gesunden Dienst. Der gleiche Jenkins-Szenariolauf meldete Erfolg, obwohl die Anwendung ungesund war.
- Graphato: explizit eingefrorener Master `0ad540dd578033d45e4d0c25d89fbe57b32102a4` ist ohne Anwendungspatches auf jeweils frischem Ziel geprüft. Der frühere grüne Kandidat `9968c226f943` ersetzt diesen Nachweis nicht.
- Graphato-Prüfgruppen: zusätzliches Szenario mit einem bereits vorhandenen privaten Steuerverzeichnis. Beide Engines erhalten dieselbe eingefrorene Anwendung und denselben VM-Snapshot. Der gesonderte Fehler bei der frischen Installation bleibt dokumentiert.
- Antares: keine erfolgreiche NAS-Ausführung behauptet. Seine bisherigen Quell-, Patch- und Ausführungsbelege bleiben erhalten.

Die vollständige Produktionsfreigabe bleibt offen. Der geprüfte Master gilt nur für diesen Commit. Produktionsziele, Zugangsdaten und Trigger sind vor der freigegebenen Umschaltung einzurichten. Details: [NAS-Vergleich](nas-parity.md).
