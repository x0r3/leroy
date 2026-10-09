# Isolierte Abnahme

Aktueller Projektstand und weiterer Plan: [status.md](status.md). Die folgenden
Aufbau- und Ausführungsbeschreibungen enthalten auch ältere Abnahmeszenarien.
Die lokale Leroy-Docker-Umgebung bleibt derzeit gestoppt; lokal läuft nur
NameFinder. Private Detailnachweise unter `test-results/` gehören nicht zum Clone.

Aktueller NAS-Umfang gemäß Nutzerentscheidung: zwölf Pipelines; Antares als Artefakt
ausgenommen. Controller und CI-Worker bleiben auf dem NAS. Die folgenden lokalen
Antares-/Linux-Pool-Nachweise sind historische Tests und keine Betriebsanforderung
an das gewählte NAS-Setup. Quellen und Ausnahme:
`test-results/nas-parity/followup/production-source-review/`.
Die aktuelle Pipeline-Matrix wird durch `scripts/summarize_nas_acceptance_scope.py`
aus vorhandenen Quell- und Ausführungsbelegen erzeugt und steht in
[nas-acceptance.md](nas-acceptance.md). Ausgenommene Artefakte zählen weder als
erfolgreiche NAS-Builds noch als offene Anforderungen an einen externen Worker.

Der aktuelle eingefrorene Graphato-Stand ist
`0ad540dd578033d45e4d0c25d89fbe57b32102a4`, ohne Anwendungspatches.
Im früheren Szenario mit `ed21c2e6346a` wurden beide Anwendungsziele separat
aus `nas-parity-base` restauriert;
`prepare_nas_vm.py` deaktiviert nur in dieser Fixture automatische APT-Hintergrundupdates.
Das eigene NAS-Daemon-Budget beträgt 4,5 GiB RAM und zusätzlich 3 GiB Swap:
2 GiB für den unveränderten Graphato-Builder und 1 GiB Reserve für Test-Jenkins,
Test-Gitea und Docker-Hilfsdienste. Die Eingriffe in den ersten laufenden
Jenkins-Build sind dokumentiert; Laufzeiten
sind damit kein Benchmark. `compare_nas_graphato.py --delivery-only --candidate <SHA>`
kann eine erfolgreiche Auslieferung prüfen, ohne fehlgeschlagene Kindprüfungen
als erfolgreiche vollständige Abnahme zu behandeln. `verify_nas_graphato_candidate_ui.cjs`
kann mit `--allow-failed` die tatsächlichen Fehlerzustände der vollständigen
Laufhierarchie prüfen; der UI-Erfolg ändert keine Pipeline-Ergebnisse.

Die Schnellstart-Befehle stehen im README. Für die reproduzierbare Migration danach:

```powershell
.venv/Scripts/python.exe scripts/publish_test_catalog.py
.venv/Scripts/python.exe scripts/test_migrations.py
```

`test_migrations.py` führt echte Skripte gegen die Testziele aus, wartet auf Ergebnisse
und schreibt Logs/Snapshots nach `test-results/migrations/`. Bei fehlgeschlagenen
Pipelines endet es mit Exitcode 1. Graphatos vollständige Abnahme setzt die
Linux-VM und deren lokale DNS-/ACME-Testdienste voraus; Einrichtung: [vm.md](vm.md).
Die generischen Engine-Tests ersetzen diese Abnahme nicht.

## Aufbau

Der Compose-Projektname ist `leroy-test`. Controller-Port 8088 und Test-PostgreSQL-
Port 55439 sind ausschließlich an Loopback gebunden. Ein eigenes Docker-in-Docker
betreibt Registry, Gitea, Paperless und die SSH-/systemd-Ziele. Der Test-Runner
verwendet ausschließlich diesen inneren Daemon. Keine produktiven Secret-Dateien
werden eingebunden.

`scripts/setup_test_targets.py` erstellt oder startet nur die benannten inneren
Testcontainer. Generierte Schlüssel/Passwörter bleiben bei Wiederholung erhalten.
Hostschlüssel werden direkt aus deren Dateisystem gelesen. Das Skript installiert
Graphatos originalen Forced-Command-Receiver mit einem eigenen Testschlüssel.
Die vollständige Hostabsicherung erfolgt weiterhin durch die Bootstrap-Pipeline.

Die Laufzeitprofile stehen in `examples/runner.test.toml`; `setup_local.py` kopiert
sie nur bei der ersten Einrichtung. Jede Secret-Referenz zeigt auf eine Datei im
Testverzeichnis. Die Parameter in `examples/migration-cases.json` ersetzen externe
Ziele durch `hub-target`, `music-target`, `graphato-vm`, `gitea-test`,
`paperless-test` und `registry:5000`. `publish_test_catalog.py` setzt diese Werte auch als Defaults der lokalen Oberfläche.
Die Originalwerte bleiben im Jenkins-Inventar erhalten. Ohne Testkatalog sind
manuelle Starts kein reproduzierbarer Abnahmelauf.

Die festen Testadressen `10.231.88.0/24` und `10.231.88.10` ermöglichen dem inneren
Docker-Netz Zugriff auf den äußeren Controller auch nach Container-Neuanlage.
Bei einem lokalen Netzkonflikt beide Werte in Compose und im Runner-Profil ändern.
Im regulären Stack erfolgt die Adressierung über Docker-DNS.

## Nachweise je Aufgabe

| Aufgabe | Überprüftes Ergebnis |
| --- | --- |
| Home-Lab Build | Beide echten Image-Kontexte gebaut, Commit-Tags und latest in der inneren Registry vorhanden; reale Vorgängerrevision zum Auslösen der Änderungserkennung verwendet |
| Hub Build | Image für die inventarisierte Revision gebaut und unter `f7fcfcf78e8f-20260619` veröffentlicht |
| Hub Bootstrap/Deploy | Originales Ansible auf Ubuntu/systemd; Image per SSH übertragen; App und Proxy gestartet; App-Healthcheck gesund, nicht bloß erfolgreicher Compose-Exitcode |
| Musik | Originales rsync-Skript über SSH; Zieldatei und SHA-256 gegen Quelldatei geprüft |
| Gitea | Privates Repository `test-admin/leroy-migrated` auf echtem Gitea erstellt und per API überprüft |
| Paperless | Originale Regelpflege auf echtem Paperless; 64 Tags, 31 Korrespondenten und 15 Dokumenttypen per API überprüft |
| Graphato Bootstrap | Vollständiger Apply-Modus auf der VM erfolgreich: Original-Docker-Pins, SSH, Firewall, AppArmor und echtes lokales ACME/HTTPS |
| Graphato Build | Originale Server-/Worker-Pakete und Windows-Portable gebaut, Release aktiviert, HTTPS/API und aktive AppArmor-Policy geprüft |
| Graphato Abnahme | Korrekturstand auf frischer VM vollständig grün: 21 Browsergruppen, acht Qualitätsgruppen mit 1504 bestandenen Rust-Tests und 29 ursprünglichen Auslassungen, gemeinsame Release-Identität und vollständiges Cleanup bestätigt |
| Antares | Original-Audit rot; Kandidat besteht nach Korrekturen Audit/Lint/Typen, 635 Unit- und 102 Integrationstests. Produktionsimage und gesamte Browsermatrix grün: 26 bestanden, drei ursprüngliche Skips |

## Host und Anwendungskorrekturen

Der Docker-Desktop-Kernel allein unterstützt die benötigte AppArmor-Erzwingung
nicht. Graphato läuft deshalb auf einer isolierten Ubuntu-24.04-VM mit eigenem
Kernel und Docker. Host-Bootstrap und Deployment sind vollständig erfolgreich;
Details und Grenzen der lokalen DNS-/ACME-Nachbildung: [vm.md](vm.md).

Die getrennten Clones `.sources/antares-validation` und `.sources/graphato-validation`
enthalten die reviewbaren Änderungen unter `upstream-patches/`. Originalcheckouts
und Upstream bleiben unverändert. Die separate Antares-Nachprüfung enthält Änderungen
an Testquellen und erhöhte Unit-/Integrationstest-Fristen; die Quellprüfung dokumentiert
diese ausdrücklich. Sie belegt keine unveränderten Tests gegenüber dem Originalprojekt.
Ein erfolgreicher Kandidat wird mit
seinem eigenen Commit dokumentiert und nicht dem unveränderten Original zugerechnet.

`scripts/test_antares_validation.py` und `scripts/test_graphato_validation.py`
veröffentlichen die Kandidaten vorübergehend im pausierten Testkatalog und stellen
danach dessen vorherige Definitionen wieder her. Alle gestarteten Läufe behalten
ihren unveränderlichen Quell-Snapshot. Graphatos Prüfung umfasst rekursiv alle
Kind- und Enkeljobs; ein grüner Build mit roter nachgelagerter Prüfung ist kein
vollständiger Erfolg.

Der erfolgreiche Graphato-Stand ist `e4e31e6a28d6fe6d9762830524c4276d257d2f7f`,
der Antares-Stand `2af9555e41aeae1bb145fa253a79b2a6b6e6cc2a`. Die Web-Abnahme
enthält den unveränderten Lasttest mit vier Tabs, 120 eindeutigen Prompts und
1.797 erfolgreichen Event-Abfragen über 309 Sekunden. Keine Teilgruppe wurde
aus einem früheren Lauf wiederverwendet. Der anschließende VM-Neustart bestand
mit geordnetem QEMU-Ende und HTTPS 200 vor und nach dem Boot ohne manuelle Recovery.

Nach erfolgreicher Gesamtabnahme hält `scripts/retain_validated_catalog.py` die
fünf betroffenen Testdefinitionen auf den tatsächlich geprüften Antares-/Graphato-
Commits. Das Skript verlangt erfolgreiche Abnahmeberichte, passende saubere
Validierungscheckouts, pausierte Trigger und eine leere Queue. Die Auswahl wird
unter `test-results/catalog-validation.json` protokolliert. Ein erneutes
`publish_test_catalog.py` setzt den Katalog wieder auf die Originalquellen;
anschließend kann die nachgewiesene Auswahl mit dem Retain-Skript erneuert werden.

`scripts/check_antares_regressions.py --browsers` prüft die Arena und den
HTTP-Abbruch während des Erwerbs einer Reader-Lease gegen eine eigene
PostgreSQL-Testdatenbank und anschließend die drei betroffenen Admin-Browserabläufe.
Es ersetzt keinen vollständigen Pipeline-Nachweis.

## Technische und visuelle Tests

Die NAS-Nachprüfung am 5. Oktober umfasst 65 erfolgreiche Python-/PostgreSQL-Tests.
Ein zusätzlicher Regressionstest hält den Log-Flush gezielt an und verlangt den
erfolgreichen Heartbeat desselben Laufs. Weitere Fälle prüfen konkurrierende
Wiederholungen und die Bereinigung nach Entzug der Ausführungsberechtigung.
Der erste Test schlägt vor der Korrektur fehl. Auf dem aktualisierten NAS-Controller
überträgt `scripts/test_nas_log_heartbeat.py` anschließend 120 Logmeldungen über zwei
Minuten, während der produktive Graphato-Build aktiv ist; die Lease bleibt erhalten.
Diese Betriebsnachweise ersetzen die noch offenen vollständigen Kandidatenvergleiche
nicht. Aktueller Stand: [nas-parity.md](nas-parity.md).

- `scripts/test_postgres.py`: echte PostgreSQL-Transaktionen; konkurrierende Claims,
  Ressourcen/Kapazität, lange blockierte Queues, abgelaufene Leases, Token-Fencing, idempotente Log-Offsets,
  unzulässige Erfolgszustände, Rollen/CSRF, Kontenrotation, Timeout-Weitergabe,
  Dateilöschungs-Wiederholung, abgebrochene Uploads, Ereigniscursor und Scheduling
  trotz einzelner SCM-Fehler. Einschließlich Kindlauf-Deadlocks, UTF-8-Loggrenzen
  und nicht blockierender Anmeldung: 47 Prüfungen erfolgreich.
- `scripts/test_execution.py`: echte Jobcontainer; transitive Fehler, Cleanup,
  Kindläufe, Controller-/Runner-Neustart, aktiver Abbruch, Replacement und Worker-Absturz.
- `scripts/test_children.py`: zwölf gleichzeitig wartende Eltern mit echten
  Kindcontainern, sechs getrennte Aufrufe derselben Unterpipeline und Kind-Timeout.
- `scripts/test_execution_edges.py`: beendeter Hauptprozess mit SIGTERM ignorierendem
  Kindprozess, Timeout/Abbruch samt anschließendem Cleanup, geschlossene Ausgabe
  bei weiterlaufendem Prozess sowie verständliche Ablehnung von Kindlauf-Zyklen
  und unmöglichen Ressourcen-Warteketten. Ausschließlich im isolierten Test-Stack.
- `scripts/test_stream.py`: eine bestehende HTTP-Ereignisverbindung wird bei
  Sitzungswiderruf tatsächlich geschlossen.
- `scripts/test_recovery.py`: neue Alembic-Datenbank sowie binärer Dump/Restore in
  eine separate Testdatenbank. Kein Eingriff in vorhandene Schemas.
- `scripts/test_backup.py`: nur bei pausierten Triggern und geleerten Queues;
  Controller/Runner kurz stoppen, PostgreSQL und `/data` gemeinsam sichern, in eine
  neue DB/ein neues Volume zurückspielen und alle Artefakt-Hashes/Loglängen prüfen.
- `scripts/test_log_progress.py`: kurze Phasenmeldung vor Prozessende trotz geladenem
  langem SSH-Schlüssel; Chunk-Grenzen, Überlappungen und begrenzter Maskierungspuffer
  werden zusätzlich durch Unit-Tests geprüft.
- `scripts/test_git_auth.py`: tatsächlicher Git-Zugriff auf das private Test-Gitea,
  erfolgreiche Authentifizierung und Ablehnung falscher Credentials.
- `web/tests`: Playwright auf Desktop 1440×1000 und Mobil 390×844, Dialoge aller
  Pipelines, alle Hauptseiten, Graph/Timeline, Logs, Ergebnisse, Artefakt-Download,
  Ereignisse, Vergleich, Verknüpfungen, Fehler und Abbruch. Lesende Rollen erhalten
  keine Start-/Abbruchknöpfe. Lange Ereignislisten und Wiederaufnahme nach mehr als
  500 neuen Ereignissen werden mit ausdrücklich synthetischen UI-Fixtures geprüft;
  der API-Cursor separat mit echten PostgreSQL-Zeilen. Axe prüft Zugänglichkeit.
  Ein zusätzliches UI-Fixture prüft globale Aktivitätszähler bei 100 neueren
  abgeschlossenen Läufen und älteren aktiven Aufträgen, auch nach Pipeline-Filter.

Die Screenshots unter `test-results/visual` und `visual-states` wurden zusätzlich
visuell auf Lesbarkeit, Überlagerungen, abgeschnittene Felder und Darstellung langer
Pipelines überprüft. Korrekturen betrafen Graph-Zoom auf kleinen Displays, Kontraste,
Tastaturzugriff auf scrollbare Ausgaben und veraltete Laufdetails beim Wechseln.
Screenshots eines einzelnen Browserlaufs decken beobachtete Zustände ab, nicht jede
mögliche Kombination sämtlicher Pipeline-Parameter.

Die Belege enthalten bewusst auch rote und unterbrochene Versuche. Erfolgreiche
Wiederholungen überschreiben deren Geschichte nicht. Nach Änderungen sind die
jeweils betroffenen Prüfungen erneut auszuführen; der Abnahmestatus im
`implementation.md` ist maßgeblich.

## NAS-Nachprüfungen für Abbruch und Bereinigung

`tests/test_heartbeat.py` prüft fortgesetzte Lease-Erneuerung während Abbruch und
Aufräumen sowie sofortige Reaktion auf entzogene Berechtigung.
`scripts/test_antares_database_cleanup.py` prüft mit echtem lokalem PostgreSQL
Schreibzugriff, Entfernen anonymer und Erhalten benannter Volumes.
`scripts/test_antares_database_readiness.py` verlängert ausschließlich in einer
Docker-Testfixture die Initialisierung um acht Sekunden und weist den Unterschied
zwischen temporärem Socket-Server und nutzbarem TCP-Server nach.
`scripts/test_nas_cancel_cleanup.py` lässt eine eigens definierte Diagnosepipeline
ablaufen und bereinigt länger als die unveränderte 90-Sekunden-Lease. Sie verändert
keine Frist einer migrierten Pipeline.
`scripts/test_runner_nested_cleanup.py` prüft lokal mit Docker die Wiederherstellung
nach einem Worker-Ausfall, einschließlich unveränderter fremder Container und
benannter Hilfsvolumes. `scripts/test_nas_runner_nested_cleanup.py` injiziert
einen Ausfall ausschließlich in einen eigens erzeugten NAS-Diagnoselauf.
Die Skripte erhalten Fehlversuche und verhindern stillschweigende Wiederholungen.

`scripts/probe_nas_antares_timing.py` beobachtet unveränderte Browserprüfungen in
einer temporären Testkopie. Optional erfasst es Chromium-CPU-Samples und lange
Browser-Tasks; `--database-tmpfs` isoliert den Datenbank-I/O-Einfluss diagnostisch.
Die ursprünglichen Assertions und Zeitlimits werden nicht verändert. Diese
Proben ersetzen keinen vollständigen Pipeline-Lauf.
`scripts/collect_nas_jenkins_evidence.py` sichert auch begrenzte Suite-Archive
fehlgeschlagener Builds mit Größen- und SHA-256-Prüfung. Der Graphato-Vergleich
schreibt auch abgeschlossene Fehlerzustände ausdrücklich als fehlgeschlagenen
Vergleich, statt ohne Ergebnisdatei abzubrechen.

`scripts/run_nas_graphato_candidate_jenkins.py` führt einen bereits hinterlegten
Kandidaten einmalig aus. Es wartet auf die produktive CI, zeichnet Buildnummern
vor dem Start auf und beobachtet vorhandene Builds bei Wiederaufnahme weiter.
`scripts/complete_nas_graphato_candidate.py` wartet auf erfolgreiche, gesicherte
Jenkins-Nachweise und die angehaltene Test-Jenkins-Instanz. Erst danach sichert es
den Zielzustand, stellt die frische Test-VM wieder her und startet dieselben
Pipelines unter Leroy. Beide Seiten erhalten dieselbe belegte Docker-Netzpolicy.
Fehler werden nicht automatisch wiederholt. Die abschließende Ergebnisdatei
bestätigt ausschließlich diesen Graphato-Kandidaten; sie gibt keine allgemeine
Produktionsfreigabe. Die Sequenz für `9968c226f943` ist vollständig erfolgreich abgeschlossen.

Nach dem VM-Restore wartet `scripts/prepare_nas_vm.py` höchstens vier Minuten
auf tatsächlich authentifiziertes SSH und einen aktiven Docker-Dienst, bevor es
Test-Infrastruktur schreibt. Ein gestarteter QEMU-Container genügt dafür nicht.
Fehler bei Anmeldung oder Hostschlüsselprüfung brechen sofort ab. Das
anwendungsfreie Ziel wird vor der ersten Änderung geprüft.

`scripts/start_nas_graphato_candidate.py` prüft vor jedem Graphato-Bootstrap
den tatsächlichen, mit Hostschlüssel abgesicherten SSH-Zugriff aus dem eigenen
Test-Jenkins sowie das anwendungsfreie Ziel. Bei einem aufgezeichneten
Bootstrap-Fehler erlaubt `--retry-bootstrap-reason` eine ausdrücklich begründete
Wiederholung vor dem Leroy-Vergleich. Vorherige Buildnummern, Ergebnis und
Vergleichsdatei werden separat erhalten; aktive Jobs oder Warteschlangeneinträge
verhindern den Start. Die TCP-Verbindung wird unabhängig von einer früheren
Tunnel-Statusdatei geprüft.

Für eine weitere Antares-I/O-Diagnose kann `--artifacts-in-tmpfs` zusammen mit
`--browser-tmpfs` ausschließlich das Schreiben von Traces und Videos während
des Tests in begrenztes RAM verlagern. Danach werden die Dateien in ein eigenes
Verzeichnis `test-results/playwright-<Versuch>` kopiert. Der Artefaktsammler liest
dieses mit `--result-directory`. Die HTML-Berichterstellung und die ursprünglichen
Testassertionen bleiben erhalten. Die fokussierte NAS-Probe `ram-trace-auth`
besteht alle drei ursprünglichen Authentifizierungstests. Auch die anschließende
Probe mit Artefakten auf Festplatte besteht alle drei Tests; dies bestätigt
keine alleinige Ursache im Artefaktspeicher und keine vollständige CI-Abnahme.

`scripts/run_nas_antares_storage_pair.py` wartet zunächst auf den vollständigen
Graphato-Vergleich. Erst dann führt es die ursprünglichen drei Authentifizierungs-
Tests unter Chromium zweimal aus: einmal mit Traces/Videos im RAM, einmal mit
deren bisheriger Speicherung. Beide Proben nutzen denselben Commit, dieselbe
begrenzte RAM-Datenbank mit aktivierter PostgreSQL-Dauerhaftigkeit und dasselbe
Browser-`/tmp` im RAM. Fehlerartefakte und Produktions-Buildnummern werden für
beide Varianten getrennt gesichert. Das sind fokussierte Diagnosen, kein
wiederholter Leistungsbenchmark und keine vollständige Antares-Abnahme. Vor
dem Start werden neben dem Commit auch unveränderte versionierte Arbeitsdateien
geprüft. Vor und nach jeder Probe werden die Speicher-/I/O-Druckzähler des eigenen Daemons
lesend gesichert; anschließend wird die Entfernung beider Diagnosecontainer
geprüft. Die Produktionsprüfung erfasst jetzt alle vorhandenen Jenkins-Jobs,
einschließlich bislang nicht gestarteter Jobs, statt nur Graphato-CI. Aktive Jobs
verhindern den Diagnosestart; eine zwischenzeitlich veränderte Buildhistorie
verhindert die Interpretation als Speichervergleich. Die gesonderte Vorprüfung
erfasst 13 Jobs, alle inaktiv. Sie ist noch keine Antares-Messung.
Vor diesen Proben werden die tatsächlichen vier abgeschlossenen
Graphato-Läufe zusätzlich in 16 Desktop-/Mobilansichten automatisiert geprüft.
Die Screenshots erhalten erst nach visueller Prüfung deren separate Bestätigung.

Bei Diagnosecontainern wartet die Nachprüfung nach `docker stop` höchstens
30 Sekunden auf die tatsächlich abgeschlossene automatische Entfernung.
Eine sofortige Containerliste kann noch die laufende `--rm`-Bereinigung zeigen.
Die fokussierte RAM-Probe wurde deshalb nicht erneut ausgeführt: Originalergebnis
und Prüfsumme bleiben in `ram-trace-auth-cleanup-recovery.json` erhalten,
beide Container wurden anschließend lesend als entfernt bestätigt. Drei gezielte
Regressionen prüfen verzögerte Entfernung, einen verbliebenen Container sowie
fehlenden Docker-Zugriff.

Für die vollständigen Snapshot-Prüfungen reicht die ursprüngliche 512-MiB-
RAM-Datenbank nicht aus: Die gesicherte Probe zeigt einen WAL-Schreibabbruch
wegen Platzmangel. `--database-tmpfs-size 1g` erlaubt eine ausdrücklich
begründete Diagnose mit höherer Kapazität. Die Obergrenze bleibt fest;
Dauerhaftigkeit wird weiterhin abgefragt und muss vollständig aktiviert sein.
Der separate Fehlerartefaktsammler verwendet nach Validierung erweiterte
Windows-Pfade. Ein tatsächlicher Datei-Schreib-/Leseversuch über 260 Zeichen
sowie Traversal, absolute Pfade, Laufwerks-/Datenstromnamen und Backslash-
Traversal werden in `diagnostic-path-regression.json` geprüft.

`infra/nas/antares-docker.py` ist eine optionale Docker-CLI-Konfiguration
ausschließlich für den isolierten Antares-Vergleich. Bei gesetztem
`LEROY_NAS_ANTARES_TMPFS=1` erhalten eindeutig zugehörige Browsercontainer ein
fest begrenztes RAM-Dateisystem für `/tmp`. PostgreSQL bleibt nach dem belegten
Kapazitätsfehler von Jenkins #12 auf Disk. Der echte Docker-Client
führt alle anderen Befehle unverändert aus. Anwendungen, Jenkinsfile,
Testassertionen, Retries und Fristen bleiben erhalten. Die Einrichtung prüft
identische Policy-Dateien sowie echte PostgreSQL-Schreib-/Leseversuche unter
beiden Engines. Ein ausdrücklich diagnostischer Vergleich fehlgeschlagener
Gates ist nur mit dokumentiertem Anlass möglich und bleibt als fehlgeschlagene
Abnahme sichtbar. `prepare_nas_antares_tmpfs_retry.py` erhält vorher das
abgeschlossene frühere Paar einschließlich Artefakten und Dateiprüfsummen.

Nach dem belegten Browser-OOM erhöht `configure_nas_antares_headroom.py` nur
den eigenen Test-Daemon auf 4,5 GiB RAM, bei unveränderter 6-GiB-Gesamtgrenze
und sechs CPUs. Es verlangt identifizierte OOM-Ereignisse, inaktive Test- und
Produktionsjobs, den exakten Test-Daemon sowie mindestens 2 GiB verfügbaren
Hostspeicher vor der Änderung. Es erfolgt kein Neustart. Der anschließende
Arena-Test mit Bilddateien im RAM zeigt denselben Phasenfehler ohne neuen OOM.

Die spätere Disk-Browsermatrix wurde nach belegtem hostweitem Speicher-/I/O-Stall
gezielt beendet. Der exakte Container-Init wurde über Cgroup, eingefrorenen
Quellhash, Prozessstartzeit und Command-SHA verifiziert und per SIGTERM beendet;
kein Produktionsprozess wurde signalisiert. Der Lauf ist als Abbruch markiert,
eine fehlende Gesamtzusammenfassung wird nicht ersetzt. Nachweise und Fehler-
artefakte bleiben erhalten. `configure_nas_antares_safe_budget.py` deaktiviert
danach zusätzlichen Swap ausschließlich für den eigenen 4,5-GiB-Daemon, ohne
Neustart und mit erhaltener Produktionshistorie. Bestehende Swap-Seiten werden
gesondert ausgewiesen; es wird kein sofortiger Nullverbrauch behauptet.

`nas_diagnostic.py` nimmt einen erhaltenen Diagnosebeleg nur bei identischem
Programm, Profil, Artefaktvertrag und Zeitlimit wieder auf. Vorprüfungen sind an
die konkrete Jenkins-Buildnummer gebunden. Fünf Regressionen verhindern, dass
ein älterer erfolgreicher Beleg eine geänderte Vorprüfung ersetzt.

`complete_nas_antares_tmpfs_pair.py --attempt ""` erfasst den ersten Vergleich
eines neuen Kandidaten; benannte Wiederholungen müssen exakt mit dem erhaltenen
Vergleichsbeleg übereinstimmen. Teilweise Vitest-Zusammenfassungen behalten
bestandene, fehlgeschlagene und übersprungene Tests. Fehlende oder abgeschnittene
Browser-Zusammenfassungen bleiben unvollständig. Vier gezielte Regressionen
decken diese Fälle ab; zusammen mit Speicherregel und Diagnosebelegen bestehen
22 Prüfungen.

`compare_nas_antares_via_leroy.py --memory 4g --cpus 6` verlangt vorab eine
tatsächlich bestandene lokale Linux-Unit-Probe desselben Kandidaten unter
diesem Budget, ohne OOM. Jenkins und Leroy erhalten anschließend denselben
Jobrahmen. Die gemeinsame 4,5-GiB-Daemon-Grenze bleibt erhalten, zusätzlicher
Swap bleibt deaktiviert. Die lokale 3-GiB-Kontrolle von `58da3ef5d112` scheitert
mit OOM, die 4-GiB-Kontrolle besteht alle 637 Tests und Coverage. Der NAS-Vergleich
muss unabhängig davon seine vollständigen ursprünglichen Gates bestehen.

Nach einem weiteren belegten WebKit-Speicher-/I/O-Stall begrenzt
`recover_nas_antares_pressure.py` den eigenen NAS-Daemon auf 3 GiB und entfernt
nur dessen schweres Antares-Profil. Vorher werden alle vorhandenen Fehlerdateien
lokal anhand ihrer SHA-256 geprüft. Produktions-Buildnummern und Ergebnisse
müssen unverändert sein. Die ursprüngliche fehlgeschlagene Diagnose bleibt
erhalten und wird nicht als vollständige Browsermatrix ausgegeben.

`setup_nas_linux_pool.py export` übernimmt die Images und Plugins ausschließlich
aus dem eigenen Vergleichsstack. `setup` erstellt einen eigenen Linux-Daemon
mit 8 GiB, sechs CPUs, neuen Netzbereichen und eigenen Volumes in Docker Desktop.
Der Pool verwendet Leroys vorhandenes verteiltes Worker-Protokoll; der Controller
bleibt auf dem NAS. Jobrahmen beider CI-Systeme: 4 GiB, sechs CPUs, 2-GiB-Node-Heap.
PostgreSQL bleibt auf Disk, temporäre Browserprofile verwenden 1 GiB tmpfs.
Ein schreibgeschützter Python-HTTP-Server stellt die eingefrorenen Git-Objekte
unter der unveränderten Vergleichs-URL bereit; damit wird kein Gitea-Funktionstest
ersetzt. Private Netzbereiche sind außer dem NAS-Testcontroller und DNS-Port 53
des Docker-Desktop-Resolvers gesperrt. Es werden keine Ports veröffentlicht.

`verify_nas_linux_pool.py` führt einen echten Auftrag über den NAS-Controller aus,
prüft den zugewiesenen Worker, Image, Jobrahmen, Git-Commit und Jenkinsfile-SHA,
den zurückgeladenen Ergebnisbeleg sowie gesperrte NAS-Verwaltungsports.
`--execution-pool test-results/nas-parity/followup/linux-pool/pool.json` wählt
diesen Pool ausdrücklich in den Jenkins-/Leroy-Vergleichsskripten. Die ursprünglichen
Jenkins- und Browserfristen sowie Assertions bleiben gleich. Ein Scheitern vor
dem ersten Jenkins-Build bleibt als eigener Diagnosebeleg erhalten; ein neuer
Observer erfordert den ausdrücklichen `--setup-retry`-Parameter. Die verteilte
Abnahme bestätigt keine ausreichenden Rechenressourcen der NAS-Hardware allein.

### Abschluss des verteilten Antares-Vergleichs vom 5. Oktober

Der NAS-Controller hat den vollständigen Lauf auf dem isolierten Docker-Desktop-
Linux-Pool ausgeführt. Jenkins #1 und Leroy #88 bestehen auf demselben eingefrorenen
Commit `58da3ef5d112f58bc0a3d1cbd75179eb71d421c1` jeweils 637 Unit-,
102 Integrations- und 26 Browsertests; drei Browserauslassungen stammen aus der
Originalmatrix. Coverage, Sicherheitsprüfung, statische Prüfungen und Produktionsbuild
sind unter beiden Engines erfolgreich. Es gibt keine Browserwiederholung.

`scripts/finalize_nas_linux_pool_pair.py` prüft nach dem tatsächlichen Abschluss
die Identität des eigenen Pools, den gestoppten Test-Jenkins mit wiederhergestelltem
Ressourcenrahmen, entfernte Run-Container und Arbeitsvolume, alle 110 lokalen
Artefakte gegen Größe/SHA-256, die sechs bereits visuell geprüften UI-Ansichten,
Controller-Bereitschaft, deaktivierte Trigger und unveränderte 13 Produktionshistorien.
Das Ergebnis steht in `test-results/nas-parity/followup/linux-pool/complete-pair.json`.
Die Prüfung startet keinen weiteren Build und überschreibt keinen Abschlussbeleg.

Dieser Erfolg gilt für die verteilte Ausführung und den dokumentierten
Anwendungskandidaten. Er belegt weder ausreichende Ressourcen der NAS-Hardware
allein noch Neustart/Sicherung eines künftig dauerhaften Linux-Ausführungspools.
