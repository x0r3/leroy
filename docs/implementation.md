# Abnahmestand Leroy

Der aktuelle Projektstand vom 9. Oktober und der weitere Plan stehen in
[status.md](status.md). Dieser Bericht enthält historische Abnahmen mit ihren
jeweiligen Grenzen. Spätere vollständige Qualitätsproben bestehen, die
Original-Release-Abnahme bleibt am Browser-Soak rot. Die neue NAS-Serie hat nach
einem Runtime-Importfehler am 7. Oktober noch keine Tests gestartet. Private
Detailnachweise unter `test-results/` sind nicht im Git-Repository enthalten.

## Historischer Stand vom 6. Oktober

Der am 6. Oktober ausdrücklich eingefrorene Graphato-Master ist
`0ad540dd578033d45e4d0c25d89fbe57b32102a4`. Der unveränderte Vergleich auf jeweils
frischem Ziel ist abgeschlossen: Jenkins-Bootstrap #8 und CI #6 sowie Leroy-
Bootstrap #104 und CI #105 sind erfolgreich. Die Auslieferungen haben vier gesunde
Dienste und geprüfte Desktop-Pakete. Beide Engines scheitern mit den nachgelagerten
Prüfläufen vor dem ersten Prüffall am gleichen ursprünglichen Markerfehler.
Die Vorbereitungsdaten beider Gäste stimmen überein. Der zusätzliche vollständige
Gruppenvergleich auf einem identischen privaten Host-Snapshot ist abgeschlossen.
Die Web-Prüfung ist bereits verglichen: Jenkins #8 und Leroy #110 führen
alle 21 Gruppen aus, 20 bestehen; beide scheitern im Browser-Dauertest an exakt
derselben Credential-Ratenbegrenzung. Jenkins-Qualität #8 besteht alle acht
Gruppen mit 1.625 bestandenen Rust-Tests, 32 ignorierten Tests und 195 bestandenen
Python-Tests. Leroy-Qualität #111 führt ebenfalls alle acht Gruppen und alle
1.657 Rust-Testereignisse aus: 1.624 bestanden, 32 ignoriert, ein Fehler.
Die einzige Abweichung ist die Assertion, dass die überlappenden Merge-Transaktionen
mindestens einen Serialisierungs-Retry auslösen müssen. Alle 195 Python-Tests
bestehen auch dort. Das bleibt eine ungeklärte Ausführungsabweichung; beide
Release-Abnahmen sind fehlgeschlagen.
[Gruppenvergleich](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/scenarios/root-private-existing-host/analysis.json).
Der betroffene Rust-Test besteht in vier zusätzlichen Einzelproben mit jeweils
frischer PostgreSQL-Fixture, zwei Rust-Testthreads und unveränderten Limits.
Diese gefilterte Diagnose ersetzt den vollständigen fehlgeschlagenen Lauf nicht
und beweist noch keine Ursache der Abweichung. Der Diagnosehelfer hatte zuerst
einen Startfehler durch unzulässige Adapterargumente; dieser Versuch ist erhalten.
[Einzelproben](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/scenarios/root-private-existing-host/rust-retry-coverage-probe.json).

Die unten aufgeführten älteren Ergebnisse bleiben gesonderte Nachweise. Quelle:
[Master-Nachweis](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/frozen-master.json).

Vorhandene produktive Jenkins-Quittungen für denselben Commit sind ebenfalls
lesend geprüft: Web #18 besteht 21/21 Gruppen, Qualität #17 besteht 8/8 Gruppen;
beide haben vollständiges Cleanup. Das ist ein gesonderter Produktionsnachweis:
[Beobachtung vom 6. Oktober](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/production-evidence-observation-20261006T123824Z.json).

Die abschließende CI-Betriebsabnahme mit diesem Stand besteht: sieben
festgeschriebene Images sind in leeren Daemons mit passendem Speichermodell und
identischen IDs/Layern wiederhergestellt. Der vollständige eigene NAS-Teststack
ist neu gestartet; danach bestehen echte Jobs in allen vier Worker-Profilen.
Die Rücksicherung bestätigt alle Datenbankzeilen und Prüfsummen, 537 Artefakte,
251 Logs und die verschlüsselte Konfiguration; der wiederhergestellte Controller
ist bereit. 21 gezielte Tests sichern die Abnahmehelfer ab. Der Quellstand ist
sauber und unverändert. Diese Infrastrukturabnahme ersetzt die roten
Anwendungsprüfungen nicht.
[Betriebsnachweis](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/final-operations-acceptance.json).

Stand: 6. Oktober 2026. **Die historische technische Abnahme in der isolierten Umgebung ist abgeschlossen.**
Das gilt für die unten angegebenen Anwendungskorrekturen. Die Gleichwertigkeit
der unveränderten Originalstände mit Jenkins auf dem NAS ist nicht vollständig
belegt. Vergleichsläufe aller 13 Pipelines sind inzwischen ausgewertet; Fehler,
übersprungene Pfade und die inzwischen korrigierte SSH-Ratenbegrenzung stehen in
[nas-parity.md](nas-parity.md). Das ist keine erfolgreiche Produktionsabnahme.

Aktuelle Nutzerentscheidung: Controller und CI-Worker sollen wie Jenkins auf dem
NAS laufen. Antares ist als Artefakt ausdrücklich aus dieser NAS-Abnahme ausgenommen;
der Umfang beträgt zwölf Pipelines. Der zusätzliche lokale Linux-Testpool ist
gestoppt und startet nicht automatisch. Seine erfolgreichen Antares-Nachweise
bleiben historische Belege. Der ursprünglich ausgewählte Produktionscommit
`ed21c2e6346a` ist inzwischen ohne Anwendungspatches verglichen. Im zusätzlichen
Szenario mit bereits privatem Steuerverzeichnis führen beide Engines alle 21
Web- und acht Qualitätsgruppen aus: jeweils 20/21 und 7/8 erfolgreich,
identische Fehlersignaturen sowie 1.579 bestandene und 30 ignorierte Rust-Tests
mit identischem normalisiertem Ergebnishash. Der frische Installationsfehler
bleibt separat erhalten. Die inzwischen neueren Produktionscommits sind damit
nicht unter Leroy abgenommen.
Die neue lesende Quellen- und Patchprüfung ist abgeschlossen; die fünf direkt
in Jenkins hinterlegten Skripte und die Jenkinsfiles sind unverändert.

Aktuelle Nachprüfung: 102 Leroy-Tests mit echter PostgreSQL-Datenbank bestehen;
neun davon sichern die Zuordnung von Quellen, Quittungen
und vollständigen ursprünglichen Testereignissen ab.
Abbruch und Bereinigung über die 90-Sekunden-Lease hinaus, automatische Entfernung
verwaister Hilfscontainer nach Worker-Absturz und PostgreSQL-TCP-Bereitschaft sind
korrigiert und auf dem NAS-Teststack geprüft. Die Zeitachsenfarben und die Auswahl
unterbrochener Schritte sind korrigiert; 227 NAS-Ansichten sind automatisiert und
visuell geprüft. Darin enthalten sind vier Ansichten des separaten Linux-Workers
und sechs Ergebnisansichten des vollständig erfolgreichen Antares-Laufs sowie
acht neue Ansichten der NAS-Worker und der Antares-Ausnahme sowie vier Ansichten
des unterbrochenen Graphato-Laufs #90 und 16 Ansichten der aktuellen unveränderten
Graphato-Ausführung: CI #91 erfolgreich, Release #92 und dessen Kindläufe
nach dem ursprünglichen Markerfehler fehlgeschlagen. Hinzu kommen 28 Ansichten
des eingefrorenen Masters auf frischem und vorbereitetem Ziel; sieben weitere
UI-Artefaktdownloads sind gegen SHA-256 geprüft. Die früheren Offline-Anzeigen
während des Jenkins-Builds sind tatsächliche Lastbefunde; UI-Erfolg bestätigt
keine gesunde Worker-Ausführung. Vier der Scope-Ansichten bestätigen den
NAS-Worker online und den zusätzlichen Pool offline. Der NAS-Worker meldet sich nach Korrektur des
gemeinsamen Testbudgets wieder online. Jenkins CI #5 startete unter der früheren
3-GiB-Grenze und hat den unveränderten Stand inzwischen erfolgreich gebaut und
ausgeliefert. Seine Prüfläufe enden auf dem frischen Ziel vor den Gruppen an einem
ursprünglichen Berechtigungsfehler. Die Leroy-Wiederholung #91 besteht vollständig
bis zur Veröffentlichung und zum Cleanup; ihre anschließenden Prüfgruppen
scheitern vor dem Start am selben ursprünglichen Fehler. 471 erfolgreiche
Heartbeats sind erfasst, größte Lücke 17,7 Sekunden. Leroy stehen 4,5 GiB RAM
und zusätzlich 3 GiB Swap im eigenen Test-Daemon zur Verfügung, davon 1 GiB Reserve
für dessen Hilfsdienste. Der kleine Steuerprozess darf keinen Swap verwenden;
typisierte Lease-Diagnosen enthalten keine Exception-Inhalte. Der zuvor
unterbrochene Versuch bleibt mit allen Nachweisen erhalten.
Die erste zusätzliche Gruppenprüfung #95 wurde ebenfalls wegen ausgebliebener
Lease-Bestätigung abgebrochen und bleibt vollständig archiviert. Controller,
PostgreSQL und Runner dürfen nun ebenfalls keinen Swap nutzen. Die Wiederholung
#99 mit Kindern #100/#101 beendet den rund 61-minütigen Lauf ohne Unterbrechung;
19 Speicherproben zeigen keinen Swap, keine OOM-Ereignisse und keine Neustarts
dieser drei Dienste. Die größte beobachtete Heartbeat-Lücke beträgt zwölf Sekunden.
Die Ursache der früheren Unterbrechung ist damit nicht abschließend bewiesen.
Zwölf weitere Ergebnis-/Graphansichten sind einzeln visuell geprüft.
Eine unabhängige Worker-Korrektur ergänzt den Kindlauf-Grund im aggregierten
Fehlerbanner. Sie ist nach dem eingefrorenen Vergleich auf beiden NAS-Jobimages
installiert, mit den tatsächlich roten Läufen #102/#103 und vier weiteren
Desktop-/Mobilansichten geprüft. Die anfänglich falsche Exitcode-Erwartung des
Testharness wurde anhand derselben Läufe korrigiert: der Testbefehl endet mit 17,
der Aktions-Launcher nach `CalledProcessError` mit 1. Keine Wiederholung und keine
Änderung dieses Ausführungsverhaltens waren erforderlich.
Der ursprüngliche Graphato-Builder verlangt 4 GiB RAM und
insgesamt 6 GiB RAM+Swap; seine Grenzen und die Produktion bleiben unverändert. Identische
Startbedingungen oder ein Leistungsvergleich werden nicht behauptet.
Antares' Ausführung ausschließlich auf der NAS-Hardware war nach Browserfehlern
unvollständig; sie ist durch die aktuelle Nutzerentscheidung ausgenommen.
Der getrennte Kandidat `58da3ef5d112` korrigiert den Bestätigungsdialog und die
zeitkritische Arena-Testaufnahme; lokal bestehen 26 Browsertests mit drei
ursprünglichen Auslassungen ohne Wiederholung oder OOM. Der vollständige Vergleich
mit NAS-Controller und separatem Linux-Ausführungspool besteht nun unter Jenkins #1
und Leroy #88: jeweils 637 Unit-, 102 Integrations- und 26 Browsertests, drei
ursprüngliche Browserauslassungen, Coverage, Audit, Lint, Typprüfung und Produktionsbuild.
Alle neun Leroy-Schritte bestehen; es gibt keine Browserwiederholung oder OOM-Ereignisse.
Alle 110 Leroy-Artefakte sind gegen Größe und SHA-256 geprüft; Job, Hilfscontainer und
Arbeitsvolume sind entfernt. Alle 637 Unit-Tests und Coverage bestehen auch lokal mit sechs CPUs und
4 GiB RAM; die 3-GiB-Kontrolle wird wegen OOM als fehlgeschlagen erhalten. Eine
vollgelaufene diagnostische RAM-Datenbank wurde auf Disk
zurückgestellt. Der eigene Test-Daemon darf nach belegten Speicher-/I/O-Stalls
für die damalige Antares-Diagnose keinen zusätzlichen Swap mehr belegen. Im
aktuellen Graphato-Vergleich gilt der oben dokumentierte ursprüngliche Spielraum.
Auch die fokussierte NAS-Probe des
Dialog-Kandidaten endet nach zeitabhängigen Arena-Fehlern und starkem WebKit-
Speicher-/I/O-Druck unvollständig. Ihre Traces bleiben erhalten, alle 13
Produktionshistorien unverändert. Der NAS-Test-Daemon ist anschließend auf
3 GiB begrenzt; Antares wurde für den damaligen Vergleich auf einen separaten
Linux-Testpool mit identischen Vergleichsimages verlagert. Dieser Pool ist jetzt
gestoppt und entfällt im vorgesehenen Betrieb. Die verteilte Abnahme bestätigt
keine ausreichenden NAS-Rechenressourcen.
Diese Infrastrukturkorrekturen ändern
weder die Assertions des jeweils eingefrorenen Kandidaten noch die ursprünglichen
Pipeline-Zeitlimits. Gegenüber Antares' Originalprojekt enthält das Patchbündel
auch geänderte Testquellen und erhöhte Unit-/Integrationstest-Fristen. Der gleiche
Kandidat wurde unter beiden Engines geprüft; daraus folgt keine Identität aller
Originalassertions oder sämtlicher ursprünglicher Testfristen.
Graphatos frische Jenkins-Wiederholung #3 besteht CI und Qualität, scheitert aber
in einer der 21 Webgruppen an HTTP 429 im Testtreiber. Der getrennte Korrekturkandidat
`9968c226f943` besteht 38 gezielte Prüfungen und den vollständigen NAS-Vergleich unter
Jenkins und Leroy auf frischen VMs: 21 Webgruppen, acht Qualitätsgruppen und
Release-Abnahme erfolgreich, mit übereinstimmenden normalisierten Rust-Ergebnissen.
Die Details und unveränderten Fehlernachweise stehen in [nas-parity.md](nas-parity.md).
Die lesende Produktionsprüfung zeigt inzwischen einen anderen Graphato-Quellstand
(`ed21c2e6346a`): CI #18 besteht, seine vollständige Release-Abnahme #11 scheitert;
Web besteht 20/21 und Qualität 7/8 Gruppen. Dieser Befund bleibt vom eingefrorenen
Kandidatenvergleich getrennt; der neuere Stand ist damit nicht produktiv abgenommen.

In der historischen isolierten Abnahme haben alle 13 migrierten Jenkins-Jobs
ihre vollständigen Aufgaben auf den dokumentierten Korrekturständen erfolgreich
ausgeführt. Graphatos 21 Web- und acht Qualitätsgruppen sowie die gemeinsame
Release-Abnahme sind grün. Antares besteht ebenfalls die vollständige Pipeline.
Für beide Anwendungen gelten die unten dokumentierten Korrekturstände.
Der geordnete VM-/Anwendungsneustart und die abschließende Sicherung/Rücksicherung
sind erfolgreich. Jenkins wurde nicht abgeschaltet oder produktiv umgestellt.

## Fertigstellungskriterien

- [x] Live-Jenkins und die weiterführenden CI-Artefakte aller vier referenzierten Repositories untersuchen.
- [x] Python-Controller, PostgreSQL-Queue, Docker-Runner und Migrationen implementieren.
- [x] Authentifizierung, Parameter-/Credential-Bindung, Logs, Artefakte und nachvollziehbare Versuche implementieren.
- [x] Alle 13 Pipeline-Definitionen mit Quellen/Hashes übersetzen.
- [x] Alle 13 Jobs tatsächlich in der isolierten Umgebung ausführen; Fehler erhalten.
- [x] Alle 13 migrierten Aufgaben auf den dokumentierten Anwendungskorrekturständen erfolgreich abschließen und deren Ergebnisse nachweisen (historische isolierte Abnahme).
- [x] Fehlerweitergabe, Cleanup, Kindläufe, Abbruch, Replacement, Worker-Ausfall, Timeout und Neustart prüfen.
- [x] Alle implementierten UI-Seiten, Dialoge und Detailansichten auf Desktop/Mobil visuell prüfen.
- [x] Setup, Betrieb, Grenzen und überprüften Backup/Restore dokumentieren.

## Pipeline-Nachweise

Die Links zeigen auf den laufenden lokalen Test-Controller. Vollständige Logs und
Snapshots liegen zusätzlich unter `test-results/migrations/<pipeline>/<run>/`.

| Pipeline | Lauf | Ergebnis der tatsächlichen Aufgabe |
| --- | --- | --- |
| antares-ci | [#132](http://127.0.0.1:8088/#/runs/1ba237df6e034ab29d4aef92393da68b) | Korrekturstand erfolgreich: Audit, Lint, Typen, 635 Unit- und 102 Integrationstests, Produktionsimage und gesamte Browsermatrix (26 bestanden, drei ursprüngliche Skips). |
| gitea-bootstrap-repo | [#8](http://127.0.0.1:8088/#/runs/620af719cd884087baf3a03efcd7d63e) | Erfolgreich: echtes privates Repository per API nachgewiesen. |
| graphato-bootstrap-host | [#134](http://127.0.0.1:8088/#/runs/dfa925a4729f4474ad34b8708f1f2624) | Vollständiger Apply-Modus auf der frisch provisionierten Ubuntu-VM: Firewall, SSH, AppArmor und echtes lokales ACME/HTTPS erfolgreich. |
| graphato-ci | [#135](http://127.0.0.1:8088/#/runs/6ed894d4ea1e4f12b75dd7bc131b3015) | Korrekturstand erfolgreich: Server, Worker und Windows-Client gebaut; neue VM mit neuer Datenbank ausgeliefert; HTTPS, API, AppArmor und Paketveröffentlichung geprüft. Beide nachgelagerten Testsuiten und gemeinsame Release-Abnahme erfolgreich. |
| graphato-postdeploy-quality | [#138](http://127.0.0.1:8088/#/runs/a340c4585a6b4f42851a3ca0be3a6eb7) | Alle acht Qualitätsgruppen erfolgreich: Frontend/Deployment, Rust-Format/Clippy/Tests (1504 bestanden, 29 ursprüngliche Auslassungen), Entwicklungsprofile, Repository-Verwaltung, Reset und Host-Laufzeit. |
| graphato-postdeploy-web | [#137](http://127.0.0.1:8088/#/runs/1a6f06a7d5644fabaac391f8127f4713) | Vollständig erfolgreich: alle 21 Gruppen inklusive vier Tabs/120 Prompts/über fünf Minuten Lasttest; Cleanup bestätigt, keine wiederverwendeten Teilnachweise. |
| graphato-release-acceptance | [#136](http://127.0.0.1:8088/#/runs/2fe74374e65242ceb9967e6f85c718fe) | Vollständige Web- und Qualitätsnachweise für dieselbe Release-Identität geprüft; beide Kindläufe erfolgreich. |
| home-lab-ci | [#20](http://127.0.0.1:8088/#/runs/ec789c32d14546a7bfc33e7296a86d20) | Erfolgreich: beide betroffenen Images gebaut und in Test-Registry veröffentlicht. |
| music-library-sync-smartphone | [#5](http://127.0.0.1:8088/#/runs/a728f2223c924eff9e964419da78c527) | Erfolgreich: rsync über SSH; Inhalt und Prüfsumme am Ziel stimmen. |
| nikicas-hub-bootstrap-host | [#66](http://127.0.0.1:8088/#/runs/ac710a28c9ed4679bbb57d4d721fd23b) | Erfolgreich: Ansible, Docker, Deploy-Benutzer, Persistenzrechte und Firewall. |
| nikicas-hub-ci | [#4](http://127.0.0.1:8088/#/runs/d9bba9e7eb1542719afcad7b21ef2920) | Erfolgreich: getaggtes Image gebaut und veröffentlicht. |
| nikicas-hub-deploy | [#40](http://127.0.0.1:8088/#/runs/f24b00107cfb4804b2ef3d081a8498db) | Erfolgreich: echter Deploy; App-Healthcheck gesund. |
| paperless-ngx-bootstrap-rules | [#10](http://127.0.0.1:8088/#/runs/b4ad8508c1b1436d9c931392f3df43e2) | Erfolgreich: 64 Tags, 31 Korrespondenten und 15 Dokumenttypen per API geprüft. |

Der frühere AppArmor-Blocker ist behoben: Die lokale Ubuntu-VM führt die originalen
Schutzprofile tatsächlich aus. Der komplette Bootstrap und das Deployment sind
nun erfolgreich. DNS und ACME werden ausschließlich im Gast nachgebildet, mit
echter Domain-Challenge, Zertifikatsausstellung und Vertrauensprüfung; Aufbau und
Abgrenzung zur öffentlichen Infrastruktur: [vm.md](vm.md).

Der unveränderte Antares-Stand hat sechs hohe Audit-Befunde. Der getrennte
Validierungsbranch enthält Sicherheitsupdates, eine nach CPU-Profilierung
vorgenommene DOM-Korrektur und die Behandlung timerloser HTTP-Testtransporte.
Die anschließend aufgedeckten Browserfehler betrafen eine verwaiste Reader-Lease bei Verbindungsabbruch und
inkonsistente Countdown-Daten beim Layoutwechsel. Beide wurden reproduziert und
korrigiert: 29 Arena-Tests, ein echter HTTP-/PostgreSQL-Regressionstest und alle
drei betroffenen Browserabläufe bestehen. Die vollständige Pipeline besteht mit 635 Unit-, 102 Integrations- und
26 Browsertests (drei ursprüngliche Skips) auf Commit `2af9555e41aeae1bb145fa253a79b2a6b6e6cc2a`.

Graphatos ursprüngliche Web-Abnahme bestand 20 von 21 Gruppen; der Lasttest
brachte einen fehlenden Retry im Fixture-Client zum Vorschein. Der ursprüngliche
Rust-Lauf bestand 1502 Tests und fand eine Dateisperre, die bei gleichzeitigem Fork
länger als die Lease bestehen blieb. Die Korrekturen liegen in separaten Patches vor.
Commit `e4e31e6a28d6fe6d9762830524c4276d257d2f7f` besteht die gesamte Wiederholung:
21 Webgruppen mit vier Tabs, 120 eindeutigen Prompts und 1.797 erfolgreichen
Event-Abfragen über 309 Sekunden; acht Qualitätsgruppen mit 1504 bestandenen
Rust-Tests, null Fehlern und 29 ursprünglichen Auslassungen. Beide Receipts
bestätigen vollständiges Cleanup und keine wiederverwendeten Teilnachweise.

Die vollständige Graphato-Abnahme lief auf einer frisch provisionierten unabhängigen
VM, einschließlich originalem Inspect-/Apply-Bootstrap, AppArmor und Isolation.
Ihr anschließender Neustart bestand mit `forced: false`, QEMU-Exit-Code 0 und
HTTPS 200 vor und nach dem Boot, ohne manuelle Runtime-Recovery. Die zuvor hart
beendete alte VM-Platte samt Runtime-Sperre bleibt unverändert erhalten. Deren
manuelle Recovery hatte die Werkzeug-Freigabeprüfung auch nach Nutzerbestätigung
blockiert; die frische Abnahme verwendet eine neue Datenbank.

Alle Änderungen liegen als reviewbare Patches unter `upstream-patches/`.
Die Schutz-Gates bleiben erhalten. Antares' Patchbündel enthält jedoch geänderte
Testquellen und erhöhte Unit-/Integrationstest-Fristen, wie oben dokumentiert.
Die historische grüne Abnahme belegt deshalb keine unveränderten Prüfbedingungen
gegenüber sämtlichen Originalprojekten.
Der pausierte lokale Testkatalog verwendet nun die erfolgreich geprüften
Validierungsbranches. Das übernimmt die Patches noch nicht in produktive
Quell-Repositories. Ihre Integration ist keine belegte Voraussetzung für Leroy.
Vor dem Umstieg steht der Vergleich derselben unveränderten Commits unter
vergleichbaren Bedingungen; Anwendungspatches werden separat bewertet.
Produktionsziele, Zugangsdaten und Jenkins-/Leroy-Trigger werden erst danach
je Pipeline kontrolliert gewechselt; siehe [migration.md](migration.md).

## Nachbesserungen der Implementierungsprüfung

- Ausführbare Jobs werden vor der Begrenzung der Queue-Abfrage in PostgreSQL
  ausgewählt. Mehr als 200 blockierte/unpassende Vorgänger verhindern ihren Start nicht.
- Der Runner belegt Threads nur für Containerstarts. Zwölf gleichzeitig wartende
  Eltern und ihre zwölf echten Kindjobs wurden erfolgreich abgearbeitet.
- Unterpipelines erhalten explizite Parameter. Mehrere Schritte derselben Pipeline
  werden separat dedupliziert; sechs parallele Aufrufe wurden vollständig geprüft.
- Abbruch, Pipeline-Timeout, Kind-Timeout und verlorene Eltern-Leases werden
  weitergegeben. Gleichzeitiger Abschluss und Abbruch überschreiben keinen Erfolg.
- Ungültige Zeitpläne, Zeitzonen und Parameterdefaults werden beim Veröffentlichen
  abgewiesen; geänderte Trigger werden neu berechnet.
- Dateilöschungen und laufende Uploads haben persistente Bereinigungsaufträge
  (Alembic `0002`/`0003`). Aktive Uploads bleiben geschützt, Crash-Reste werden entfernt.
- Die lokale Konten-CLI unterstützt Rollen, Passwortrotation und Sitzungswiderruf;
  der letzte Administrator ist geschützt. Bestehende SSE-Verbindungen enden bei Widerruf.
- Die UI lädt aktuelle Ereignisse zuerst und ältere über Cursor nach, auch nach
  längerer Unterbrechung. Aktionen entsprechen der Rolle; Desktop/Mobil geprüft.

Zusätzlich wurden während der vollständigen Abnahme verzögerte Live-Logs, unbeabsichtigte
30-Minuten-Grenzen in übersetzten Jenkins-Stages und verlorene Timeout-Ursachen
bei gleichzeitigem Prozessende korrigiert. Der Abnahmekatalog verwendet nun die
vorgesehenen Pipeline-/Kindlaufbudgets; die Gesamtlimits bleiben bestehen.

## Übergreifende Nachweise

- 47 Python-/PostgreSQL-Prüfungen erfolgreich, einschließlich konkurrierender Claims,
  langer blockierter Queues, Rollen/CSRF, Kontenrotation, Lease-Fencing,
  Log-Wiederholung, Ereigniscursor und wiederholbarer Dateibereinigung.
- Reale Docker-Ausführung mit Controller-/Runner-Neustart, Kindlauf, aktivem Abbruch,
  Ersetzung, Worker-Crash und gesondertem Timeout-Status erfolgreich getestet.
- Neue Alembic-Datenbank und PG-Dump/Restore erfolgreich; gemeinsame Offline-Sicherung
  in neue DB/neues Volume zurückgespielt, dabei 362 Artefakt-Hashes und 365 Logs geprüft.
- Privates Git: echter authentifizierter Clone/ls-remote erfolgreich, falsche Credentials abgewiesen.
- Fünf Playwright-Szenarien erfolgreich; Desktop 1440×1000 und Mobil 390×844.
  Screenshots aller Hauptseiten, aller Pipeline-Definitionen/Parameterdialoge,
  Graphen/Zeitachsen und Detailtabs visuell geprüft. Axe meldet keine schwerwiegenden
  Zugänglichkeitsfehler. Verbindungsverlust und Sitzungsablauf zusätzlich geprüft.
- Die große Historie im Pagination-Test ist ausdrücklich ein UI-Fixture; sie zählt
  nicht als Pipeline-Abnahme. Die übrigen Pipeline-Screenshots zeigen reale Läufe.

Befehle und Detailumfang: [testing.md](testing.md). Quellen und Abweichungen:
[migration.md](migration.md). Sicherung und Betrieb: [operations.md](operations.md).

## Nachprüfung nach abgeschlossener Pipeline-Abnahme

Die zusätzliche Prüfung behebt konkrete Randfälle in Leroy. Die migrierten
Anwendungsskripte und deren abgenommene Quellstände bleiben unverändert.

- Ein beendeter Hauptprozess konnte einen SIGTERM ignorierenden Nachkommen mit
  offenem Ausgabekanal hinterlassen. Der alte Worker blieb im realen Docker-Test
  nach Timeout und Ablauf der Stop-Frist hängen. Der korrigierte Worker beendet
  die gesamte Prozessgruppe und erreicht anschließend den Cleanup-Schritt;
  Timeout und manueller Abbruch sind getrennt nachgewiesen.
- Unterpipeline-Zyklen und durch wartende Vorfahren belegte Ressourcen werden
  vor dem Einreihen abgewiesen. Die Fehlermeldung bleibt im Lauf sichtbar.
  Zulässige asynchrone Aufrufe und idempotente Wiederholungen bleiben möglich.
- Gleichzeitige Anmeldungen warten nicht mehr auf den globalen Passwortprüfungs-
  Lock. Die API antwortet bei belegtem Lock mit HTTP 429 und Retry-After.
- UTF-8-Logs behalten vollständige Zeichen über Seiten- und Übertragungsgrenzen;
  auch noch unvollständige laufende Ausgaben sind durch Regressionstests abgedeckt.
- Globale Aktivitätszähler verwenden die gesamte Laufhistorie statt der neuesten
  100 Einträge. Die Kontraste des aktiven Navigationszählers und der Projektzähler wurden korrigiert.

Gezielte Docker-Nachweise: `test-results/execution-edges.json`;
Reproduktion am alten Worker: `test-results/execution-edges-before.json`.
Die UI-Zähler werden mit einem ausdrücklich synthetischen Historien-Fixture
unter `test-results/visual-counts/` auf Desktop und Mobil geprüft.

Die Nachprüfung besteht 47 Python-/PostgreSQL-Tests, die vollständigen Docker-
Ausführungs- und Unterpipeline-Tests sowie alle fünf Playwright-Szenarien
(59,6 Sekunden). Desktop-/Mobil-Screenshots wurden visuell geprüft; Axe meldet
keine schwerwiegenden Zugänglichkeitsfehler. Controller, Runner und Job-Image
sind im isolierten Stack aktualisiert. Die vollständigen 13 Anwendungspipelines
wurden dafür nicht erneut gebaut; ihre vorherigen Abnahmen bleiben separat
mit den ursprünglichen Lauf- und Image-Identitäten dokumentiert.
Zusammengefasster Nachweis: `test-results/followup-review.json`.
