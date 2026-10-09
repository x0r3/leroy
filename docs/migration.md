# Migration der vorhandenen Jenkins-Aufgaben

Grundlage sind die live aus Jenkins gelesenen 13 Job-Konfigurationen und die vier
von ihnen referenzierten Repositories. `jenkins-inventory.json` hält Parameter,
Quellen, Commit-IDs, Stages und Hashes der Jenkins-Konfigurationen fest.
Private Rohdaten liegen ausschließlich unter `.sources/jenkins`.

| Repository | Inventarisierte Revision | Relevante weitere Artefakte |
| --- | --- | --- |
| home-lab-service-collection | `9fb528a1bb4b736d53d294510b374d516e973a03` | Jenkins-Konfiguration/Inline-Pipelines, Image-Kontexte, Musik-Python-Skript, Paperless-Shellskript und Regeldatei, Hub-Ansible, Graphato-Bootstrap-Transport |
| graphato | `ffd4be75f36f4590272832691df04b06ae9e388a` | Vier Jenkinsfiles, `scripts/ci.py`, Build-/Transfer-Skripte, Linux-/Windows-Dockerfiles, Host-Bootstrap, Forced-Command-Receiver, Deploy-/Postdeploy-Implementierung und Receipts |
| nikicas-hub | `f7fcfcf78e8f3717217f841734be824a8e97bbd2` | Jenkinsfile, Dockerfile, Compose-Konfiguration, Laufzeitbenutzer, Persistenzpfade und Healthcheck |
| antares | `ab245279a2c5ba85dedef1180e7fd63b7f5b1398` | Jenkinsfile, Paket-/Lockdateien, Vitest-Coverage, PostgreSQL-Integrationstests, Docker-Images, Playwright-Projekte und Browseranforderungen |

Die weiterführenden Artefakte ergeben insbesondere Anforderungen, die aus einem
einfachen Jenkins-Stage-Import nicht hervorgehen: AppArmor/rootless Docker und
Bubblewrap bei Graphato, Release-Identität über mehrere Kindläufe, Windows-Build
auf Linux, Benutzer-IDs für persistente Hub-Dateien und echte Browser/DB-Prüfungen
bei Antares.

| Pipeline | Erhaltene Aufgabe und Semantik |
| --- | --- |
| home-lab-ci | Änderungen seit letztem Erfolg, `NO_CI`, betroffene Docker-Kontexte, Commit- und latest-Tags, Registry-Push |
| nikicas-hub-ci | Image-Build mit ursprünglichen Build-Argumenten, SHA/Datums-Tag in Europe/Berlin und Push |
| antares-ci | npm ci/audit, Lint, Typprüfung, Unit/Coverage und Integration, Produktions-Images, Browser-Suite; alte Läufe ersetzen |
| graphato-ci | Immutable Checkout, Release-Entscheidung, Boundaries, Server/Worker, Windows-Portable, erneuter Master-Abgleich, Deploy, asynchrone Abnahme, Desktop-Veröffentlichung, Cleanup |
| graphato-release-acceptance | Web und Quality als Kindläufe; Quality auch nach Web-Fehler; gemeinsame Release-Identität und vollständige Receipts erforderlich |
| graphato-postdeploy-web | Originale isolierte Web-Prüfungen auf dem Zielhost, `CHECK_GROUP`, Berichte und Cleanup-Receipt |
| graphato-postdeploy-quality | Originale isolierte Qualitätsprüfungen auf dem Zielhost, Teilgruppen und vollständige Receipts |
| graphato-bootstrap-host | Originale Transporttests, Inspect standardmäßig; Apply mit unveränderten Hardening-Vorgaben |
| music-library-sync-smartphone | Originales Python-/rsync-Verhalten, SSH/known_hosts, Quellen, Ausschlüsse, Dry Run und täglicher H-Cron |
| nikicas-hub-bootstrap-host | Originales Ansible-Playbook, Deploy-Identität, Verzeichnisse, Docker und optional Firewall |
| nikicas-hub-deploy | Parameter, immutable Checkout, Registry-Pull/Export, SSH-Transfer und Compose-Deployment |
| gitea-bootstrap-repo | Administrator sicherstellen, Benutzer-/Organisations-Repository erzeugen, Sichtbarkeit/Default-Branch |
| paperless-ngx-bootstrap-rules | Originales Bash-Skript und Regeldatei gegen die Paperless-API, idempotente Metadatenpflege |

## Gezielte Korrekturen

Übersetzte Jenkins-Stages ohne eigenes Limit erhalten das Budget ihrer Pipeline,
statt unbemerkt Leroys allgemeinen 30-Minuten-Schrittdefault zu verwenden.
Graphatos wartende Web-/Quality-Schritte erlauben jeweils die ursprünglichen
420 Minuten; die gemeinsame Abnahme bleibt auf insgesamt 480 Minuten begrenzt.

Der Hub-Deploy verwendet fest hinterlegte SSH-Hostschlüssel. Ein globales Docker-
Prune auf dem Zielhost wurde entfernt, damit fremde Dienste unberührt bleiben.
Die drei App-Secret-Namen werden korrekt zugeordnet. Ein ergänzendes Ansible-
Playbook setzt die Daten-/Galerie-Verzeichnisse auf die Laufzeit-UID des Images
(standardmäßig 1000); sonst scheitert die App nach scheinbar erfolgreichem Deploy
mit `SQLITE_CANTOPEN`. Compose wartet jetzt bis zu 180 Sekunden auf Gesundheit.
Die SQLite-Datei ist Bestandteil des Hub-Projekts, nicht Leroys Datenbank.

Graphatos originale Python-Funktionen werden weiterverwendet; Transport, lokaler
Speicher und BuildKit werden an Runner-Profile angebunden. Erfolgs-Receipts werden
nicht simuliert. Die bestehende AppArmor-Prüfung wird nicht abgeschwächt, um einen
ungeeigneten Docker-Desktop-Kernel als erfolgreiche Abnahme auszugeben.

Antares ist im inventarisierten Stand beim Audit rot. Der getrennte lokale
Validierungsbranch enthält Updates der Produktionsabhängigkeiten und eine nach
CPU-Profilierung vorgenommene Gruppierung sichtbarer Karten-DOM-Elemente.
Reviewbare Patches: `upstream-patches/antares-security.patch` und
`upstream-patches/antares-grid-performance.patch`. Originale Tests und Grenzwerte
bleiben bestehen; eine vollständige Abnahme zählt ausschließlich für den
jeweils dokumentierten Kandidaten-Commit.

`upstream-patches/antares-snapshot-http.patch` berücksichtigt, dass Fastifys
HTTP-Injection keine echte Socket-Timer-Methode besitzt. Die Eingabevalidierung
läuft dadurch auch im Integrationstest; echte TCP-Sockets behalten die bestehende
Timeout-Ausnahme für lange Snapshot-Operationen. Alle sechs gezielten HTTP-Fälle
haben bestanden.

`upstream-patches/antares-browser-lifecycle.patch` beseitigt eine Reader-Lease,
deren HTTP-Verbindung bereits während der Gate-Transaktion geschlossen wurde,
und vereinheitlicht Fortschrittsdaten und SVG-Koordinaten der Kampfarena. Ein
reproduzierbarer TCP-/PostgreSQL-Test sowie die ursprünglichen Browserabläufe
bestätigen beide Korrekturen.

Graphatos originaler Vier-Tab-Lasttest akzeptiert vorübergehende Event-Drosselung,
sein Fixture-Schreibclient brach aber bei einer ausdrücklich vor der Ausführung
abgewiesenen Anfrage sofort ab. `upstream-patches/graphato-acceptance-rate-limit.patch`
ergänzt einen begrenzten Retry nur für HTTP 429 mit `serverRateLimited` und
übereinstimmendem `Retry-After`. Request-ID und Body bleiben gleich. Transportfehler,
andere Statuscodes, ungültige Header und dauerhaftes Throttling bleiben Fehler.
Die 120 Prompts, fünf Minuten, vier Tabs und sämtliche Ergebnisprüfungen bleiben
unverändert. Drei unabhängige Tests decken Wiederholung, Budget und Nicht-Wiederholung
mehrdeutiger Fehler ab. Die Serverlimits werden nicht verändert.

`upstream-patches/graphato-connection-lease.patch` gibt die Dateisperre einer
Model-Verbindung explizit beim Ende der Lease frei. Ein nebenläufiger Fork kann
sonst den offenen Dateideskriptor kurz über deren Lebensdauer hinaus halten und
eine unmittelbar anschließende Schlüsselrotation blockieren. Ein zusätzlicher
Regressionstest hält gezielt einen duplizierten Deskriptor offen und prüft auch
die weiter wirksame Sperre des nächsten Besitzers. Bestehende Tests bleiben erhalten.

Alle Anwendungskorrekturen werden in separaten Clones ausgeführt und als Patch
aufbewahrt. Sie wurden nicht in Originalrepositories gepusht. Ein grüner Lauf auf
einem solchen Branch belegt nicht die Funktionsfähigkeit des unveränderten Originals.
Für Antares fasst `upstream-patches/antares-all.patch` alle Änderungen relativ zur
inventarisierten Revision zusammen. Die Einzelpatches gelten in der Reihenfolge
Security, Grid-Performance, Snapshot-HTTP, Browser-Lifecycle. Der Gesamtpatch und beide Graphato-Patches
wurden mit `git apply --check` gegen die sauberen Originalcheckouts geprüft.

Der isolierte Testkatalog kann die erfolgreich abgenommenen Kandidaten mit
`scripts/retain_validated_catalog.py` dauerhaft auswählen; alle automatischen
Trigger bleiben dabei pausiert. Die Änderung gilt ausschließlich für lokale
Testdefinitionen. Die Anwendungskorrekturen sind separat zu bewerten; ihre Übernahme
ist keine belegte Voraussetzung für den produktiven Wechsel auf Leroy. Zunächst
werden dieselben unveränderten Commits unter vergleichbaren Bedingungen mit
Jenkins und Leroy ausgeführt. Abweichungen werden zuerst in Leroys Ausführung
beziehungsweise Konfiguration untersucht; siehe [nas-parity.md](nas-parity.md).

## Umstieg

Jenkins bleibt bis zur vollständigen Abnahme aktiv. Danach für jede Pipeline zuerst
ihren Jenkins-Trigger deaktivieren, Produktions-Credentials/Zielparameter in Leroy
bereitstellen, einen kontrollierten Lauf mit überprüften Ergebnissen durchführen
und erst anschließend Leroys Polling/Cron aktivieren. Ein globaler gleichzeitiger
Umstieg ohne Abgleich kann doppelte Deployments oder Synchronisierungen auslösen.
Historische Jenkins-Läufe werden durch diese Implementierung nicht importiert;
die gesicherte Jenkins-Instanz bleibt dafür bis zur Aufbewahrungsentscheidung lesbar.
