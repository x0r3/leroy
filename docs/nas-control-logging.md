# Controller-Antworten unter Logdruck

Stand: 12. Oktober 2026. Die Korrektur ist im isolierten NAS-Stack installiert.
Sie ist kein abgeschlossener Graphato-Release-Nachweis und keine Umschaltung
des produktiven Jenkins.

Die Originalquellen von Graphato bleiben auf
`0ad540dd578033d45e4d0c25d89fbe57b32102a4` eingefroren. Die vorherige NAS-Serie
`m` meldete Controller-ReadTimeouts und verlor die Worker-Lease. Ihre Docker-
Systemlogs lagen trotz SSD-Datenbank und SSD-CI-Speicher auf dem HDD-Pool und
verwendeten blockierende Zustellung.

Eine begrenzte Probe verwendet deshalb einen zusätzlichen Controller mit eigener
Datenbank und einen echten unveränderten Worker. Ein nur lokal erreichbarer
Syslog-Empfänger staut für etwa 70 Sekunden die Diagnoseausgabe. Beide Modi
verwenden identische Controller-/Runner-/Worker-Images, Pipeline, Fristen und
Probeinstrumentierung. Dies belegt die Fehlerklasse; die historische HDD-
Ursache aller früheren NAS-Ausfälle ist damit noch nicht vollständig bewiesen.

| Gesicherter Nachweis | Blockierend | Gepuffert |
| --- | --- | --- |
| API-Timeouts | 12 | 0 |
| Direkte Datenbankfehler | 0 | 0 |
| Ursprünglicher Probejob | Lease abgelaufen, unterbrochen | Erfolgreich |
| Vollständige Joblogs | kein vollständiger Abschluss | Alle 21 Einträge |
| Abschlussartefakt | fehlt | Größe, Inhalt und SHA-256 geprüft |

Die direkte SQL-Antwort bleibt während der blockierten API bei etwa 12–50 ms.
Der bisherige Controller-Speicher-/Datenbankpfad ist somit nicht Voraussetzung
für diese gezielt nachgestellte Blockade. Docker beschreibt blockierende
Logzustellung als Standard und die gepufferte Zustellung als Schutz vor
[Log-Backpressure](https://docs.docker.com/engine/logging/configure/#configure-the-delivery-mode-of-log-messages-from-container-to-log-driver).

Die Compose-Dateien setzen `mode=non-blocking` und `max-buffer-size=4m` für
Systemdiagnosen. Auch der Supervisor setzt diese Optionen bei neuen Jobs.
Der begrenzte Puffer darf bei überlastetem Empfänger Systemdiagnosen verlieren;
CI-Schrittlogs und Artefakte werden weiterhin separat dauerhaft gesichert.
Diese Unterscheidung ist durch den erfolgreichen Probejob geprüft. Lease-Fristen,
Transaktionsdurabilität und Anwendungstests werden nicht gelockert.

Installation: Runner-Image
`620623e9be9a3bfdbc521c066de591ae973badeb7e4e05429493bef18dad6416`.
Controller, PostgreSQL, Docker-Daemon und tatsächliche Job-Worker behalten ihre
Images. Datenbankbestand, Ressourcen, Mounts, übrige Konfiguration und zuvor
aktive verschachtelte Dienste sind verifiziert. Datenbankdump, vorherige
Compose-Datei und vorheriges Runner-Image bleiben geschützt erhalten.
Das vollständige produktive Jenkins-Fenster ist ruhig.

Auch der installierte Runner besteht die erneute Lastprobe: echte Jobcontainer
besitzen die gepufferte Diagnosezustellung; alle Logs und das Artefakt sind
vollständig. Ein anfänglicher Timeout beim Beenden des künstlichen Empfängers
ist erhalten und anschließend gezielt bereinigt. Probecontainer, Jobs und die
temporäre Freigabe in der eigenen Docker-Netzisolation sind entfernt.
Vier vorausgehende Aufbau-/Collector-Probleme bleiben gesondert erhalten und
werden nicht als erfolgreiche Druckproben gezählt.

22 gezielte Runner-/Heartbeat-/Kindfehlerprüfungen bestehen; mit den gezielten
VM-Sicherheits-/Cache-/Profilprüfungen bestehen 77 Tests. Dies ist kein neuer
vollständiger App-Regressionslauf.

Die Quellen bestätigen außerdem eine Grenze des bisherigen Testaufbaus:
Produktiver Jenkins läuft auf dem NAS, seine Postdeploy-Qualität wird per SSH
auf dem Linux-Zielhost ausgeführt. In unserer NAS-Isolation läuft zusätzlich
dieser Linux-Zielhost als eigene VM auf dem NAS. Die bisherige RAM-/Swap-Grenze
dieses Aufbaus ist daher keine belegte Grenze des normalen Produktionsbetriebs.
Die neue Serie `n` bleibt ein funktionaler Vergleich beider Engines auf demselben
isolierten NAS-Ziel. Ein Produktions-Performancevergleich wird nicht behauptet.
Die lesende Docker-Aufnahme bestätigt zusätzlich: Der produktive Jenkins-
Controller hat keine konfigurierten Container-RAM-/CPU-Limits; der private
Test-Jenkins besitzt 2 GiB RAM, 4 GiB RAM plus Swap und zwei CPUs. Die Hardware
des externen Produktionsziels wurde nicht abgefragt. Diese Grenzen des
Testaufbaus sind im `n/jenkins-production-topology-proof.json` festgehalten;
produktive Dienste und das externe Ziel wurden dabei nicht verändert.
Ihr frühes VM-Reclaim-Limit beträgt 3584 statt 3328 MiB, gestützt auf die noch
freie RAM-Reserve bei den bisherigen Swap-Schutzstopps. Gastkapazität, harte
Limits, ursprüngliche Testfristen und NAS-Schutzreserven bleiben unverändert.

Rohbelege: `test-results/nas-parity/followup/control-latency-20261012/`.
Die nachfolgende Serie `n` ist inzwischen unter beiden Engines terminal beendet.
Ihre ursprüngliche Clippy-Last erzeugt trotz des korrigierten Logmodus erneut
API- und Docker-Exec-Timeouts sowie starken Host-Speicher-/I/O-Stau. Code-/Image-
Dateizugriffe vom HDD-Pool und Cgroup-Dateiseiten-Rückladungen sind festgehalten;
die PostgreSQL-/Controller-Datenpfade bleiben auf SSD und Durabilität eingeschaltet.
Beide VMs enden an der unveränderten Swap-Schutzreserve, Leroy verliert zusätzlich
seine Lease. Die begrenzte Fehlerprobe bleibt gültig; sie belegt keine vollständige
Controller-Verfügbarkeit unter dieser realen Last. Weitere Absicherung ist offen.

Der Original-Webvergleich belegt Jenkins 42/42 und Leroy 41/42 erfolgreiche
Fälle; ein Dev-Umgebungs-UI-Timeout bleibt ursächlich ungeklärt. Komponenten
97/98 und Python 195/195 stimmen überein. Vollständige Qualitäts-/Release-
Artefakte fehlen bei beiden. 18 terminale UI-Ansichten sind technisch und direkt
visuell geprüft. Alle eigenen Ursprungsläufe sind geschlossen, kein Worker
dieses Paars läuft weiter, und produktiver Jenkins bleibt unverändert.
Der vollständige Befund steht in [nas-full-release.md](nas-full-release.md).

Der abgeschlossene `m`-Datenträger ist bytegenau auf HDD archiviert:
20.151.533.568 Bytes, SHA-256
`16e4e874afd8d2fc61061d824f573c573d28e314d0c3ee2fddbf2f29c0e2dbeb`.
Die einzelne SSD-Datei wurde erst nach Kopie, Prüfsumme, Metadatenprüfung und
Fsync entfernt. Das Archiv wird nicht als frische Ausgangsbasis wiederverwendet.

## Zusätzlicher Schutz vor der ersten Prozess-Pipe (17. Oktober)

Versuch V/#185 blockierte trotz des Docker-Puffers. Die ergänzende Aufnahme zeigt
Uvicorns Hauptthread in `anon_pipe_write`, während PostgreSQL im Leerlauf war.
Der Docker-Puffer greift hinter seinem eigenen Leser; stockt dieser Leser,
kann bereits die erste stdout/stderr-Pipe voll werden.

Sechs echte Linux-Prozesstests mit Uvicorn vergleichen beide Varianten bei voller,
ungelesener Pipe, einschließlich Dependency-Loggern und geordnetem Beenden.
Zusätzlich ist die Probe mit separater Datenbank und echtem unverändertem Worker
für 120 Sekunden blockierter Anfangs-Pipe auf dem NAS ausgeführt:

| Nachweis | Bisherige Ausgabe | Begrenzte asynchrone Ausgabe |
| --- | --- | --- |
| Run | `f703dfd4e1a64a7b817f5e257d0e24fb` | `d66fce1f0da14e4db14b02408d941f3b` |
| Ergebnis | `interrupted` | `succeeded` |
| API-Timeout-Samples | 20 | 0 |
| Direkte SQL-Fehler | 0 | 0 |
| Joblog | abgebrochen | alle 21 Takte vollständig |
| Abschlussartefakt | fehlt | Inhalt, Größe und SHA-256 verifiziert |

Beide verwenden weiterhin `json-file`, `mode=non-blocking`, 4 MiB Docker-Puffer,
denselben Runner und Worker sowie 45/90 Sekunden Lease-Grenzen. Nur der
zusätzliche Controller verwendet die neue Ausgabe. Keine Graphato-Quellen,
Tests oder Fixture-Grenzen wurden verändert, keine produktiven Builds im geprüften
Zeitraum. Die temporären Container und die eigene Netzregel sind entfernt.
Die Proben pausierten keinen der sieben freigegebenen NAS-Dienste.

Belege: `test-results/nas-parity/followup/console-queue-20261017/`.
Console-Diagnosen besitzen eine begrenzte Queue und können bei Rückstau entfallen;
Pipeline-Logs, Audit-Ereignisse und Artefakte behalten ihre dauerhaften Speicherwege.
Die neue Fehlerprobe belegt den gezielt injizierten Ausfall und seine Korrektur,
keinen vollständigen ursprünglichen Graphato-Release und keine alleinige Ursache
aller früheren Ausfälle.

Installiertes Controller-Image:
`d343d116ebd39f3c1fff8d3d1e8bf36eb1579f05bb9cf0dd2c798cf4fcfa7094`.
Es ergänzt das zuvor qualifizierte Image `ffaa70367cd503b316c714859df6fefa1275344fee1fcfe5cc183b8878c477aa`
um die beiden Module `console_logging.py` und `server.py` und den zugehörigen
Startbefehl. Ausschließlich der Controller wurde ersetzt; API gesund,
Datenbankzeilenzahlen und alle übrigen Containerprozesse unverändert. Dump,
Konfigurationskopien und das vorherige Image bleiben geschützt erhalten.
Die Prüfung rekonstruierte die alten Konfigurationshashes exakt durch
Permutation ausschließlich von Env-/Bind-/Mount-Reihenfolgen. Es wurde kein
abweichender Wert akzeptiert. Die fehlgeschlagenen ersten Vergleiche bleiben
als solche erhalten; die anschließende Sammlung wiederholt keine Installation.
