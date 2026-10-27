# Vollständiger Graphato-Release-Vergleich auf dem NAS

**Stand 26. Oktober 2026:** Der NAS-Testbetrieb ist beendet; Jenkins bleibt
produktiv. Die folgenden Ergebnisse sind historische Teilnachweise. Die fehlende
vollständige Abnahme wird auf einem späteren separaten Build-Server fortgesetzt.
Maßgeblich ist der [Checkpoint](checkpoint-2026-10-26.md).

Dieser zusätzliche Vergleich verwendet den eingefrorenen Originalcommit
`0ad540dd578033d45e4d0c25d89fbe57b32102a4`. Jenkins und Leroy starten jeweils
ihre bestehenden vollständigen Release-Pipelines: 21 Webgruppen, acht
Qualitätsgruppen und die abschließende, an den Release gebundene Quittung.
Quellen, Tests, Ratenbegrenzungen und Ressourcenlimits der Testfixtures werden
nicht geändert. Diagnose-Soaks ersetzen diese Abnahme nicht.

Abschluss vom 15. Oktober: Die originalen Webarchive belegen unter Jenkins
und Leroy jeweils **42/42 Fälle in allen 21 Gruppen bestanden**, einschließlich
unverändertem Soak, korrekter Quellen-/Runtime-Bindung und vollständiger
Bereinigung. Beide Frontend-Läufe liefern dasselbe vollständige Inventar mit
98 Komponententests: 97 bestanden, derselbe Fokusfehler scheitert in
`chat-presentation.test.mjs:24`. Rust-Formatprüfung und Clippy bestehen bei
beiden. Die vollständigen Rust-Tests und ursprünglichen Release-Gesamtquittungen
fehlen; beide Elternläufe sind fehlgeschlagen.

E überlappte mit dem produktiven Musik-Timer #244. F blieb ohne produktive
Builds, endete jedoch ebenfalls am unveränderten NAS-Swap-Schutz. Der Stopp
war erzwungen. Alle sieben NAS-Dienste waren nach F um 05:28:30 Berliner Zeit
gesund und stabil zurück, Test-VM und privater Jenkins sind aus. Ende des
Fensters war unverändert 06:00. Die lokalen Auswertungen verwenden die bereits
gesammelten Archive und starten keine CI erneut. Offline gelesene Teilquittungen
und Logs werden als ergänzende Forensik gekennzeichnet und ersetzen keine
originalen Qualitätsarchive.

Die Nachkorrekturen des Abnahmewerkzeugs beheben optionale Cache-Abholung bei
bereits gestoppter VM, die VM-Registrierung ohne neue Leroy-Lauf-ID und den
unabhängigen Reserve-Notstopp. Sie ändern weder Graphato noch dessen Tests oder
Fixture-Limits und sind noch nicht durch einen neuen Volllauf belastet.
Vollständige Paarabnahme und Produktionsfreigabe bleiben offen. Zunächst muss
die Ausführung des vollständigen Rust-Schritts die unveränderten NAS-Reserven
einhalten; mehr Laufzeit allein genügt dafür nicht. Details in `docs/status.md`.

Historischer Stand vom 12. Oktober: Serie `n` ist unter beiden Engines terminal
beendet. Die vollständigen originalen Webarchive belegen Jenkins 42/42 und
Leroy 41/42 erfolgreiche Fälle. Eine zusätzliche Dev-Umgebungsabweichung bleibt
offen. Beide Qualitätsläufe enden während Clippy nach NAS-Speicher-/I/O-Stau
und Unterschreiten der Swap-Schutzreserve. Qualitätsarchive, vollständiges
Rust-Inventar und Release-Gesamtquittungen fehlen weiterhin. Der gemeinsame
Supervisor, die Infrastruktur und Originalquellen/-tests bleiben innerhalb
dieses Paars unverändert. Die jüngste Fortsetzung steht am Ende dieses Dokuments.

## Gemeinsames Anwendungsziel

Der vorbereitete Snapshot `graphato-existing-host-0ad540dd5780` wird aus der
ausgeschalteten Windows-Test-VM exportiert. Der Export liest das ursprüngliche
Volume ausschließlich schreibgeschützt und löst seine Backing-Datei und die
anderen internen Snapshots auf. Die Windows-VM bleibt ausgeschaltet.

Die exportierte Basis wird mit SHA-256 geprüft und schreibgeschützt auf dem NAS
bereitgestellt. Jeder CI-Lauf erhält ein eigenes neues QCOW2-Overlay. Der
Ubuntu-Gast läuft mit eigenem Kernel unter KVM auf dem NAS, mit sechs CPUs und
einem je Serie dokumentierten Gastspeicherbudget. Auf dem NAS stehen etwa 7,5 GiB
physischer RAM für alle Dienste zur Verfügung. Host-Swap und Speicher-/I/O-Druck
werden deshalb als Ausführungsbedingungen protokolliert.
Die unveränderten Originallimits innerhalb des Gasts gelten weiterhin.

Die erste Serie `full-release-nas-20261011-a` mit zehn GiB Gastspeicher ist
unvollständig fehlgeschlagen: Jenkins-Elternjob #9 sowie Web #12 und Qualität #10
sind rot. QEMU protokolliert einen fehlgeschlagenen Flush; der Gast bricht sein
Ext4-Journal ab und hängt das Dateisystem schreibgeschützt ein. Ein geordnetes
Herunterfahren gelingt danach nicht; der eigene QEMU-Prozess wird nach Ablauf
der Shutdown-Frist beendet. Leroy wurde in dieser Serie nicht gestartet.
Dies ist kein abgeschlossener Vergleich der 29 Prüfgruppen.

Die NAS-Prüfung findet freien Speicherplatz, keine Btrfs-Gerätefehler und keine
Qgroup-Grenze. Begrenzte direkte Schreibproben sowie je drei GiB QCOW2-Schreiblast
mit Flushes bestehen sowohl mit `cache=none` als auch mit `cache=writeback`.
Die konkrete Ursache des ersten Flush-Fehlers bleibt offen. Die neue Serie
`full-release-nas-20261011-b` verwendet für beide Engines `cache=writeback` mit
aktiven Flushes und weniger VM-RAM. Sie ist eine geänderte Infrastrukturbedingung,
kein Beweis der Fehlerursache. Eine Fehler-Trace erfasst künftig den Flush-
Rückgabewert. Vor jedem CI-Lauf prüft eine separate Gastprobe ein GiB Schreiben,
128 Fsyncs, Prüfsumme und ein beschreibbares Root-Dateisystem. Die Originaltests
werden dabei nicht geändert oder ersetzt.

Auch Serie `full-release-nas-20261011-b` bleibt unvollständig: Der NAS-Dienst
`earlyoom` beendet QEMU während der Browser-Worker-Vorbereitung mit SIGKILL.
Unmittelbar davor bleiben nur etwa 286 MiB Swap frei. Jenkins #10, Web #13 und
Qualität #11 schlagen fehl; Leroy ist nicht gestartet. Die bisherige VM-Docker-
OOM-Markierung und der Kernel-Zähler erfassen diesen Userspace-Kill nicht.
Der Schutzdienst beendet außerdem `taskmgr_serv`; dieser NAS-Dienst startet
automatisch neu und sein neuer Prozess ist geprüft. Die produktiven Jenkins-
Buildstände bleiben unverändert. Diese Nebenwirkung des Tests bleibt dokumentiert.

Serie `full-release-nas-20261011-c` reduziert den Gast für beide Engines auf sechs
GiB und aktiviert Virtio-Free-Page-Reporting. Die VM gibt damit freie Gastseiten
an den Host zurück. Der Launcher prüft zusätzlich die Hostreserve: Unter zwei
GiB freiem Swap oder 512 MiB verfügbarem RAM startet er keinen Gast beziehungsweise
fordert dessen ACPI-Abschaltung an. Wird die Reserve während eines Laufs erreicht,
bleibt dies ein Infrastrukturabbruch; nach 45 Sekunden darf nur der eigene QEMU-
Prozess beendet werden. Der NAS-Schutzdienst bleibt aktiv und seine Auswahlregeln
werden nicht umgangen. Guard-Grenzen und Ereignisse bleiben im VM-Overlay erhalten.

Serie `full-release-nas-20261011-c` wird durch den eigenen Guard beendet:
508.532 KiB RAM sind verfügbar, aber noch 3.690.220 KiB Swap frei. Die ursprüngliche
512-MiB-RAM-Grenze bricht damit zu früh ab. Jenkins #11, Web #14 und Qualität #12
bleiben unvollständig fehlgeschlagen; Leroy wurde nicht gestartet. Der Shutdown
benötigt die dokumentierte QEMU-Terminierung nach Ablauf der Guard-Frist.

Die tatsächliche NAS-Konfiguration verwendet `earlyoom -M 65536 -s 20`.
Serie `full-release-nas-20261011-d` verwendet daher 128 MiB RAM und 2,25 GiB freien
Swap als eigene Mindestreserve. Der Gast erhält für beide Engines 4,5 GiB, um
seinen maximalen Hostverbrauch neben dem produktiven und dem eigenen Test-Jenkins
zu begrenzen. Dies verändert die gemeinsame Testhardware, nicht die ursprünglichen
Fixture-Konfigurationen. Der VM-Container erhält sechs GiB RAM, insgesamt neun
GiB RAM/Swap und sechs CPUs. Auch diese Serie kann bei Reserveunterschreitung
abgebrochen werden; ein solcher Abbruch ist kein ausgeführter Release-Vergleich.
Die ursprünglichen sechs GiB ohne zusätzlichen Swap für den Graphato-Builder
und die übrigen Testfixture-Limits bleiben erhalten.

Beide Engines prüfen denselben ursprünglichen Leroy-Build vom
`20261006113757`, Runtime-ID
`sha256:6251c60f499e41e706613f931bf281ce52312b957d5a6a123cf4e27dd3242585`.
Dieser Stand ist vom späteren nativen Diagnosevergleich mit dem ursprünglichen
CI-#23-Runtime-Inhalt zu unterscheiden. Der vorbereitete Snapshot enthält ein
bereits vorhandenes privates Steuerverzeichnis. Der separat dokumentierte
Fehler beim frischen Anlegen dieses Verzeichnisses bleibt bestehen.

## Schutz und Wiederaufnahme

Vor Vorbereitung und Start jedes Engines wartet der Helfer lesend auf einen
inaktiven produktiven Jenkins. Während der Läufe erfasst ein lesender Beobachter
die aktuellen Buildstände und NAS-Speicher-/I/O-Druck. Die vollständige
Historienprüfung einschließlich älterer paralleler Builds bleibt an den
Phasengrenzen bestehen; die laufende Beobachtung liest nur aktuelle Datensätze,
um historische XML-Dateien unter I/O-Druck nicht jede Minute erneut einzulesen.
Zeitüberschreitungen und Beobachtungslücken bleiben im Protokoll erhalten.
Eine Produktionsüberschneidung
entwertet die Lastqualifikation; das funktionale Testergebnis bleibt erhalten.
Andere NAS-Dienste werden nicht abgeschaltet und gleiche Hintergrundlast wird
nicht behauptet.

Nur der eigene Testcontainer und Dateien unter
`/volume1/docker/leroy-nas-parity/release-vm/0ad540dd5780` werden verändert.
Die bisherigen VM-Snapshots, Fehlversuche und beide Engine-Overlays bleiben
erhalten. SSH-Schlüssel bleiben in ignorierten privaten Konfigurationen.
Die vorhandenen Hostschlüssel werden weiter strikt geprüft. Administrative
Abfragen verwenden die eigene VM-Netzwerk-Namespace und eine wiederverwendete
SSH-Verbindung; der ursprüngliche CI-Zugang bleibt bestehen. Bereitschafts-
abfragen berücksichtigen die ursprüngliche SSH-Begrenzung des Testhosts.

Startmarker verhindern eine erneute Auslösung beim Wiederaufnehmen. Nach einem
Beobachtungsfehler wird derselbe CI-Lauf weiter beobachtet. Ein existierendes
Overlay wird nicht automatisch zurückgesetzt. Nach abgeschlossenem Vergleich
wird die eigene Testmaschine geordnet ausgeschaltet.

## Helfer und Nachweise

`scripts/nas_release_vm.py stage` überträgt und prüft die vorbereiteten privaten
Assets. Der bereits exportierte Snapshot und der bestehende NAS-Teststack sind
Voraussetzungen; ein neuer Repository-Clone allein stellt sie nicht her.

```powershell
.\.venv\Scripts\python.exe scripts/compare_nas_full_release.py `
  --folder test-results/nas-parity/followup/full-release-nas-20261011-d `
  --engine both
```

Der Vergleich behält Originalkonsolen, Artefaktprüfsummen, vollständige Suite-
Ergebnisse, Release-Identitäten, Produktionsverlauf und Ressourcenbeobachtungen.
Die Auswertung prüft außerdem das vollständige Rust-Testinventar und die vom
Elternjob archivierte Original-Release-Quittung. Fehlgeschlagene Gruppen bleiben
fehlgeschlagen. Dieser Nachweis ist keine automatische Produktionsumschaltung.

Die 21 Webgruppen enthalten 42 Originalfälle: 21 Core-Fälle, zwei Preview-Fälle
für Firefox und Chromium sowie 19 einzeln ausgewählte Open-Fälle. Ihr Inventar
wird aus den unveränderten eingefrorenen Testquellen gelesen. Die aggregierte
Ergebnisdatei wird genau einmal gezählt und gegen die entsprechende Ergebnisdatei
des Browser-Workers geprüft. Fehlende Fälle nach einem Fixture-Startfehler oder
einem frühen Testabbruch bleiben ausdrücklich fehlend. Alle 29 Gruppenquittungen
allein belegen deshalb noch keine vollständig ausgeführte Abnahme.

Die Inventarauswertung ist gegen die beiden erhaltenen Originalarchive der
früheren Host-Snapshot-Abnahme geprüft. Eine gekürzte Kopie eines erfolgreichen
Core-Ergebnisses wird abgewiesen; bei einer fehlgeschlagenen Gruppe wird der
fehlende Fall ausgewiesen. Die ursprünglichen Archive und Graphato-Tests werden
dabei nicht verändert.

Auch rote Qualitätsgruppen werden gegen das erhaltene Originalinventar geprüft:
1.657 Rust-Testidentitäten einschließlich 32 ignorierter Tests sowie sechs
Python-Suiten mit insgesamt 195 Tests sowie 98 Komponententest-Identitäten. Eine in sich vollständige, aber verkürzte
Rust-Suite reicht nicht aus. Kontrollierte Kopien mit nur einem Rust-Test oder
einer fehlenden Python-Suite oder einem fehlenden Komponententest werden als unvollständig ausgewiesen; eine grüne
Gruppenquittung mit solch verkürzten Daten wird abgewiesen. Der Nachweis liegt in
`quality-inventory-parser-proof.json`; Originalquellen und -archive bleiben intakt.
Fehlgeschlagene Format-, Clippy-, Entwicklungs- oder Host-Smoke-Gruppen erhalten
ohne zusätzlichen Abschlussbeleg ebenfalls keine Bestätigung vollständiger
Ausführung. Eine versuchte Gruppe wird damit nicht als vollständig ausgeführte
Prüfung ausgegeben.

## Belegter Fixture-Startfehler unter Jenkins

Im ursprünglichen Jenkins-Elternlauf #12 / Weblauf #15 scheitert die Gruppe
`browser-dev-environments`, bevor ihre Browserfälle starten. Die passive
Erfassung ordnet die Ereignisse demselben isolierten Compose-Projekt zu:

| Ereignis am 11. Oktober 2026 | UTC |
| --- | --- |
| PostgreSQL meldet `healthy` | 15:18:28,253 |
| Graphato meldet einen PostgreSQL-I/O-Fehler | 15:18:34,420 |
| PostgreSQL öffnet seinen TCP-Port | 15:18:36,887 |
| PostgreSQL ist nach dem endgültigen Start bereit | 15:18:38,674 |

Der unveränderte Healthcheck in `compose.prod.yaml` verwendet
`pg_isready -U graphato -d graphato` und prüft damit auch den temporären lokalen
Socket während der Initialisierung. Der normale Entrypoint verbindet den
Anwendungsserver mit `postgres:5432`. Im dokumentierten Fall beginnt die
Anwendung vor der TCP-Bereitschaft. Die Originalfixture verwendet außerdem
`restart: "no"`; der fehlgeschlagene Start wird nicht automatisch wiederholt.

Der Nachweis liegt in `jenkins-fixture-startup-race-proof.json` der Serie `d`,
zusammen mit den gefilterten Original-Startlogs, Docker-Ereignissen und dem
archivierten Fehler der betreffenden Gruppe. Es wurden keine zusätzlichen
HTTP-/Datenbankanfragen gesendet und keine Graphato-Quellen, Tests oder
Fixture-Konfigurationen geändert. Dieser Nachweis erklärt den konkreten
Startfehler unter Jenkins; er belegt weder alle anderen Fehler noch bereits
ein Ergebnis unter Leroy. Die separat aufgetretenen Browser-Navigationslimits
bleiben gesondert zu bewerten.

## Zwischenstand der unveränderten Originalsuite

Jenkins-Weblauf #15 hat alle 21 Gruppenquittungen erstellt und ist fehlgeschlagen.
Sechs Gruppen bestehen: Core, Cleanup, Clipboard, Database, Rotation und Previews.
Ihre 27 Originalfälle bestehen. Der Soak-Fall wird ausgeführt und schlägt fehl;
seine Meldung belegt keine konkrete HTTP-Ursache. Die übrigen 14 Originalfälle
werden nach früheren Abbrüchen nicht ausgeführt. Damit sind 28 von 42 Fällen
protokolliert, nicht 42 vollständig ausgeführte Fälle.

Zehn Gruppen scheitern beim Compose-Start mit dem protokollierten PostgreSQL-
I/O-Fehler, vier beim ursprünglichen 20-Sekunden-Navigationslimit. Nur für die
oben dokumentierte Gruppe ist die Startreihenfolge mit zeitgleichen PostgreSQL-
Logs belegt. Eine gemeinsame Ursache aller zehn Startfehler wird nicht behauptet.
Die Suite meldet ihre Bereinigung als abgeschlossen. Qualität #13 und Elternjob
#12 sind inzwischen ebenfalls fehlgeschlagen. Leroy erhält anschließend eine
neue Kopie derselben Basis. Der folgende Abschnitt dokumentiert den
unvollständigen Abschluss dieses Engine-Vergleichs.

In Qualität #13 bestehen alle 195 Python-Tests. Die 98 ursprünglichen
Komponententest-Identitäten sind vollständig nachgewiesen; 97 bestehen, der
Chat-Präsentationstest scheitert an der Fokuserwartung. Die Rust-Formatprüfung
besteht. Clippy schlägt mit Exitcode 101 fehl: Der Gastkernel protokolliert am
11. Oktober um 16:56:31 UTC einen globalen OOM-Kill von `clippy-driver`, dessen
anonymer Speicher etwa 3,45 GiB belegt. Der 4,5-GiB-Gast erweist sich für diese
Spitze samt übrigen Gastdiensten als zu klein. Das ist ein Infrastrukturfehler
dieser Testkonfiguration und kein belegter Graphato-Quellfehler. Die unveränderten
inneren Fixture-Limits werden nicht mit dem kleineren globalen Gastbudget
gleichgesetzt. Docker meldet in den betreffenden Original-Inspect-Ausgaben
`OOMKilled: false`; der Kernelbefund bleibt deshalb maßgeblich. Die Test-VM läuft
zunächst weiter und die Originalsuite versucht anschließend die Rust-Prüfung.
Der Beleg liegt in `jenkins-clippy-oom-proof.json`.

Um 17:48:51 UTC beendet der Gastkernel auch `rustc` mit einem globalen OOM-Kill;
der anonyme Speicher beträgt etwa 3,57 GiB. Das Originalprotokoll bestätigt
SIGKILL während des Kompilierens. Es werden keine Rust-Testfälle ausgeführt.
Die ursprüngliche SSH-Verbindung ist unter dem Speicherdruck zuvor abgebrochen;
Jenkins kann die Diagnose anschließend nicht abholen. Sein einziges
Qualitätsartefakt ist deshalb eine Abbruchquittung mit `status: unconfirmed`.
Die drei Entwicklungs-Smoke-Gruppen und Host-Smoke fehlen. Der Elternjob
archiviert keine abschließende Release-Quittung.

Eine spätere reine Leseverbindung sichert die vier protokollierten Gruppen,
Compilerlogs und Kernelereignisse separat als
`jenkins-quality-incomplete-target-diagnostics.tar.gz` und
`jenkins-quality-interruption-proof.json`. Der Zielprozess ist nicht mehr aktiv;
die Zielquittung enthält weiterhin `completedAt: null`. Diese zusätzlichen
Diagnosedaten ersetzen kein ursprüngliches CI-Artefakt und keinen vollständigen
Inventarnachweis. Der ursprüngliche Graphato-Server befindet sich außerdem in
einer Neustartschleife mit ungelöster Laufzeiteigentümerschaft. Der Test setzt
diese Sperre nicht während des Vergleichs zurück.

Der Vergleichstreiber erfasst auch einen nicht erreichbaren Zielserver als
Fehlerzustand. Fehlende Originalarchive und Release-Quittungen führen zu einem
explizit unvollständigen Bericht; sie werden nicht durch nachträglich erzeugte
Erfolgsquittungen ersetzt. Quellen und Tests bleiben unverändert.

## Abschluss der Serie `d` und nächste Infrastrukturbedingung

Leroys Elternlauf `a2378ef710bd468c8c9021f8e60f788c` und Web-Kindlauf
`bfa36cfde937454db689c98e985b6d14` enden als `interrupted`: Die Runner-Lease
läuft ab. Die Web-Vorbereitung wird abgebrochen, bevor Originalbrowserfälle
starten; Qualität und Release-Quittung werden übersprungen. Der Gast meldet
keinen OOM-Kill. Die Controller-, Runner- und PostgreSQL-Container laufen ohne
Neustart oder OOM weiter. Gleichzeitig protokolliert die Datenbank einen
Checkpoint mit 38,684 Sekunden Synchronisation und 67,517 Sekunden Gesamtdauer.
Das belegt erhebliche I/O-Verzögerungen; eine ausschließliche Ursache aller
verlorenen Heartbeats wird daraus nicht abgeleitet.

`analysis.json` weist beide beendeten Elternläufe, fehlende Originalartefakte,
unvollständige Testinventare und die geprüften ruhigen Produktionsfenster aus.
Zusätzliche Gastdiagnosen bleiben getrennt. Beide Overlays sind erhalten; die
VM wurde sauber gestoppt. Diese Serie ist keine bestandene vollständige Abnahme.

Die Darstellung der tatsächlichen zwei unterbrochenen Läufe wird in zwölf
Desktop-/Mobilansichten von Graph, Ergebnissen und Artefakten manuell geprüft.
Fehlende Qualitätsläufe oder Artefakte werden nicht erfunden. Der ursprüngliche
Live-UI-Prüfversuch mit einem Login-Timeout und die Beobachtung des Übergangs
zwischen Elternabbruch und Kindabbruch bleiben ebenfalls erhalten. Die
ursprüngliche Schrittmeldung `Child job did not succeed` verdeckt hier den
Lease-Abbruch; der Worker-Code übernimmt dafür künftig die tatsächliche
Abbruchursache. Die 16 relevanten Worker-/Heartbeat-Tests bestehen. Graphato-
Tests werden dabei nicht geändert. Die abgeschlossene Serie behält ihr altes
Worker-Image und ihre ursprünglichen Meldungen.

Für die nächste Serie ist das gemeinsame Profil `nas-6g-io-limited` vorbereitet:
sechs GiB Gast-RAM, sieben GiB äußeres RAM-Limit und zehn GiB RAM/Swap, weiterhin
sechs CPUs und derselbe unveränderte Snapshot. Nur die eigene VM erhält
Durchsatzgrenzen von 24 MiB/s Lesen und acht MiB/s Schreiben auf dem geprüften
NAS-Blockgerät. Host-Scheduler, andere Container und Datenbank-Durabilität
bleiben unverändert. Die Begrenzung soll Platz für Controller-/Datenbank-I/O
lassen; ihr Nutzen muss im tatsächlichen Vergleich nachgewiesen werden. Leroy
läuft zuerst, um einen wiederholten Lease-Verlust früh zu erkennen. Das ist
eine neue Infrastrukturbedingung, kein nachträgliches Bestehen der Serie `d`.

Das mit 16 gezielten Tests geprüfte Worker-Image ist am 11. Oktober um
18:20 UTC im NAS-Testprofil eingespielt. Sein ursprüngliches Image und dessen
Konfiguration bleiben bis auf eine zusätzliche Worker-Dateischicht erhalten.
Nur `profiles.graphato.image` wird auf das neue Image festgeschrieben; allein
der eigene, zuvor inaktive Runner wird neu gestartet. Die ursprünglichen
Graphato-Quellen, Tests, Lease-Fristen und Datenbank-Durabilität bleiben gleich.
Die Vorbereitung musste nach einer zu kurzen Importprobe und einer falschen
BuildKit-Basisreferenz fortgesetzt werden; diese Vorbereitungspannen gehören
nicht zu einem ursprünglichen CI-Release-Lauf.

Serie `full-release-nas-20261011-e` ist mit Leroy als erster Engine gestartet.
Die initiale Produktionsprüfung findet keine laufenden Jenkins-Builds.
Die aktive VM-Cgroup bestätigt `253:0 rbps=25165824 wbps=8388608`, sieben
GiB äußeres RAM-Limit und drei GiB zusätzlichen Swap. Dies belegt die
eingestellten Ressourcen, noch keine bestandene Release-Abnahme.

Leroys ursprünglicher Elternlauf `fb72ee9cbb2944ef9d53e024e1aee790` startet um
18:30 UTC und erzeugt den Web-Kindlauf `6d6577bb74114abc9fc8207a695fc1c7`.
Die vorbereitende Ein-GiB-Schreib-/Prüfsummenprobe mit 128 Fsyncs besteht nach
189,196 Sekunden; QEMU meldet keine fehlgeschlagenen I/O-Operationen. Die
aktive Job-Image-ID stimmt mit dem eingespielten Worker überein. Ein gesonderter
lesender Beobachter sichert ausschließlich freigegebene Lease-Diagnosezeilen,
Job-Image-IDs und Zustandsfelder. Er liest weder Jobumgebungen noch beliebige
Logtexte aus und verändert keine laufenden Jobs. Seine zusätzliche Last bleibt
eine Messgrenze des Vergleichs.

Die erste laufende Datenbankmessung enthält nur inaktive Sitzungen. Eine
spätere sechsfach lesende Probe um 18:40 UTC erfasst dagegen zwei Commits,
die auf `WalSync` beziehungsweise `WALWrite` warten, und nachgelagerte
Transaktions-/Zeilen- und Advisory-Sperren. Die beobachteten Transaktionen
altern bis etwa 17 Sekunden; am Ende der Probe sind keine Sitzungen mehr aktiv.
Dies belegt vorübergehende Commit-Verzögerungen mit einer wartenden Sperrkette,
keinen dauerhaften Deadlock. Gleichzeitig protokollieren die Worker einzelne
Heartbeat-`ReadTimeout`s; bis zu dieser Probe ist keine Lease abgelaufen.
Die Cgroups von Controller und Datenbank zeigen dabei keinen CPU-/Speicherdruck,
aber die Datenbank zeigt I/O-Wartezeit. Die exklusive physische Ursache der
Schreibverzögerungen bleibt offen; keine Durabilitätsoption wird abgeschaltet.

Leroy wird in Serie `e` erneut unterbrochen. Die Worker protokollieren
`ReadTimeout`s bis 47,342 beziehungsweise 49,250 Sekunden seit der letzten
bestätigten Erneuerung und beenden daraufhin ihre Lease-Überwachung. Der
Controller kennzeichnet beide Läufe anschließend als `interrupted`. Die
Meldungskorrektur ist tatsächlich sichtbar: Der Web-Schritt übernimmt
`Controller lease could not be renewed (last failure: ReadTimeout)`.
Qualität und Release-Quittung werden übersprungen. Ein separat gesichertes
Web-Zielarchiv enthält die abgebrochene Core-Vorbereitung; beim Sicherungszeitpunkt
sind `completedAt: null` und `cleanupComplete: false` ausdrücklich erhalten.
Das Build-Protokoll endet beim Entpacken des ursprünglichen Playwright-Images.
Ein vollständiger Originalbrowser-Inventarnachweis liegt nicht vor.

Der Gast hat zu dieser Zeit über vier GiB verfügbaren Speicher und keinen
OOM-Kill. Das RAID ist vollständig und ruht; es ist keine laufende
Synchronisation oder degradierte Platte erfasst. Die zusätzliche Gastlast,
Gast-/Host-Caches und NAS-Swap bleiben mögliche Verstärker. Jenkins erhält
anschließend die unveränderte eigene Basiskopie mit identischem Profil.
Seine Ein-GiB-/128-Fsync-Probe besteht nach 214,278 Sekunden. Elternjob #13,
Web #16 und Qualität #14 enden dennoch mit `FAILURE`: Um 19:09:43 UTC
unterschreitet die NAS-Swapreserve den eigenen Guard um ungefähr 1,8 MiB.
Der Guard fordert ausschließlich die Test-VM zum Herunterfahren auf; nach
ausbleibendem Abschluss wird sie um 19:11:25 UTC beendet. Ein anschließender
Zielzustand ist nicht mehr lesbar und wird nicht durch den vorherigen Zustand
ersetzt. Alle ursprünglichen CI-Versuche und Overlays bleiben erhalten.
Die vier Produktionsprüffenster dieser Serie sind ohne laufenden produktiven
Jenkins-Build und mit unveränderten Buildnummern abgeschlossen. Andere
NAS-Hintergrundlast ist dadurch nicht ausgeschlossen.

Als weitere gemeinsame Infrastrukturbedingung ist `nas-6g-ssd` im Helfer
vorbereitet. Das NAS besitzt bereits eine eingehängte SSD mit ungefähr 84 GiB
freiem Platz. Erst bei gestopptem Testgast, gestopptem Test-Jenkins und inaktiven
Leroy-Jobs darf eine identische, erneut gehashte Basiskopie unter
`/overlay/leroy-nas-parity-release-test` angelegt werden. Neue Overlays bleiben
auf dieser SSD; die ursprünglichen HDD-Overlays werden erhalten. Ein eigener
VM-Guard schützt 40 GiB freien SSD-Platz und darf ausschließlich die eigene
Test-VM beenden. Drei gezielte Guard-Prüfungen bestehen. Es wird kein Laufwerk
formatiert, kein NAS-Swap geändert und keine produktive Konfiguration verschoben.
Die SSD-Kopie wird erst nach Ende der Serie `e` gestartet und gesondert belegt.
Das neue Profil begrenzt ausschließlich die VM auf 128 MiB/s Lesen und
32 MiB/s Schreiben am geprüften SSD-Blockgerät.

Serie `e` weist bei identischer Konfiguration 16 KiB Unterschied in `MemTotal`
aus. Die vollständigen BIOS-E820-RAM-Bereiche beider Bootprotokolle sind identisch;
beide Kernel melden dieselbe physische Gesamtkapazität. Ihre frühen reservierten
Kernelbereiche unterscheiden sich um 32 KiB. Der Helfer akzeptiert deshalb bis
zu 32 KiB Unterschied nur mit passenden physischen Bootdaten; ohne diesen
Nachweis gilt weiterhin die bisher beobachtete Ein-Seiten-Toleranz. Vier gezielte
Prüfungen verwerfen geänderte CPU-Zahlen, größere RAM-Abweichungen, andere
physische Bereiche oder andere physische Gesamtkapazität. Das bestätigt die
gemeinsame Hardwarekonfiguration, keine erfolgreiche Anwendungsausführung.

Die laufende Jenkins-Cacheprobe erfasst ungefähr 3,6 GiB Gast-Dateicache und
etwa 2,9 GiB Swap im äußeren VM-Cgroup, obwohl der Gast fast fünf GiB verfügbaren
Speicher meldet. Die zusätzliche Virtualisierungslast wird damit als
Ausführungsbedingung gesichert. Daraus folgt noch kein Anwendungscodefehler.

Im neuen SSD-Profil ist außerdem eine gemeinsame, protokollierte Cache-Regel
für beide Testgäste vorgesehen: Bei weniger als 4352 MiB NAS-Swapreserve darf
frühestens alle 90 Sekunden ausschließlich der bereite KVM-Testgast seinen
sauberen Dateicache freigeben (`drop_caches=1`), sofern mindestens 1024 MiB
Gast-Speicher verfügbar und 768 MiB Dateicache vorhanden sind. Kein `sync`,
keine NAS-Host-Kerneländerung und keine Änderung an Original-Fixture-Limits,
Quellen, Tests oder Fristen ist Teil dieser Regel. Die Freigabe kann zusätzliche
Lese-/CPU-Arbeit verursachen; sie gilt als neue gemeinsame Testbedingung,
nicht als Produktionskonfiguration oder Beweis einer einzelnen Fehlerursache.
Zehn gezielte Prüfungen sichern Gastzuordnung, Berechtigungen, KVM-/Bereitschafts-
Voraussetzungen und Schwellwerte. Mit Worker-, Disk- und Speicherprüfungen
bestehen insgesamt 33 gezielte Tests.

Nach Abschluss der Serie `e` sind zwölf weitere echte Desktop-/Mobilansichten
visuell geprüft. Die tatsächliche `ReadTimeout`-Ursache erscheint im Elternschritt;
der ausgefallene Qualitätslauf und fehlende Originalartefakte werden nicht
erfunden. Das rohe strukturierte `web_result` bleibt der zuletzt gemeldete
`running`-Snapshot, während der tatsächliche Kindstatus sichtbar `interrupted`
ist. Der UI-Nachweis bescheinigt Darstellung, keine vollständige Release-Abnahme.

Die SSD-Vorbereitung endet um 19:21 UTC mit identischer Basissumme
`bcf9cb6c92f452da04b802bb7a60a560a366739e49dd4191d57325837a67a491`.
Seed und UEFI-Variablen sind ebenfalls identisch; der neue Launcher ist separat
gehasht. Nach der Kopie sind 86.535.118.848 Bytes frei. Das lesend geprüfte
Produktionsfenster ist ruhig und seine Buildnummern sind unverändert.

Die Vorbereitung `full-release-nas-20261011-f` scheitert vor jedem Original-CI-
Start: Die private SSD-Ablage benötigt eine privilegierte Mountprüfung; danach
weist `io.max` die SSD-Partition `259:7` zurück. Containerzustand und leeres
Vorbereitungsverzeichnis sind erhalten. Der Gast wurde dabei nie gestartet.
Der Helfer prüft nun zusätzlich die tatsächliche Elternzuordnung der Partition
und setzt die VM-Grenzen am ganzen NVMe-Gerät `259:0`. Andere Cgroups werden
nicht geändert. Serie `g` beginnt mit einer neuen eigenen Ablage; der laufende
VM-Cgroup bestätigt `259:0 rbps=134217728 wbps=33554432`, sieben GiB RAM und
drei GiB zusätzlichen Swap. Diese Startprüfung ist noch kein Testergebnis.

Leroys Vorbereitung in Serie `g` besteht: Die Ein-GiB-Prüfsummenprobe mit
128 Fsyncs benötigt 35,320 Sekunden; QEMU meldet keine fehlgeschlagenen
Operationen und die vier ursprünglichen Dienste sind gesund. Der eigene
Elternlauf `c78d02c3ae894c0eba1266b143eceee6` startet um 19:25:48 UTC.
Sein Job verwendet das geprüfte Worker-Image. Das vorherige Produktionsfenster
ist ruhig; der Gast meldet zu Beginn keinen OOM. Eine spätere Freigabe bleibt
von vollständigen Originalinventaren und tatsächlichen Release-Quittungen
unter beiden Engines abhängig.

Auch Leroy in Serie `g` verliert seine Lease: Die Worker erfassen
`ReadTimeout` mit 53,586 beziehungsweise 60,948 Sekunden seit Bestätigung.
Der Elternlauf und Weblauf werden unterbrochen, der nur eingereihte Qualitätslauf
`50cf00efad8c4d7cb3765fc3e44da986` wird abgebrochen. Originalartefakte fehlen;
der anschließend lesbare Zielzustand weist denselben Release-Manifestinhalt
und vier gesunde Dienste aus. Keine Originalbrowser-Inventare sind abgeschlossen.
Die reaktive Gast-Cache-Freigabe erfasst 3.772.564 KiB Cache davor und
381.784 KiB danach, kommt aber erst nach der kritischen Lease-Verzögerung.
Der lesende Vergleichstreiber wird nach einem Auth-/Status-Timeout mit denselben
Lauf-IDs wieder aufgenommen; solche Transportfehler werden künftig erfasst,
ohne die Ressourcenüberwachung oder den ursprünglichen CI-Versuch zu beenden.

Jenkins erhält anschließend dieselbe frische Basis. Seine entsprechende
Datenträgerprobe besteht nach 35,524 Sekunden. Elternjob #14, Web #17 und
Qualität #15 enden mit `FAILURE`. Die Test-VM ist nach Auslösung ihres Guards
beendet; ein anschließender Zielzustand ist nicht mehr lesbar. Beide Kindjobs
archivieren nur ihre ursprünglichen Abbruchquittungen, keine vollständigen
Testarchive. Alle vier Produktionsprüffenster bleiben ruhig und die nativen
Buildnummern unverändert. Andere NAS-Last ist damit nicht ausgeschlossen.

Der zusätzliche Modus `nas-6g-ssd-proactive-cache` ist für einen Folgeversuch
vorbereitet, wird in Serie `g` jedoch nicht aktiviert. Ein verifizierter eigener
Root-Prozess ausschließlich im bereiten KVM-Testgast prüft alle 30 Sekunden
dieselben Gast-Schwellwerte und protokolliert saubere Cache-Freigaben lokal.
So hängt seine Arbeit nicht von NAS-Status-/SSH-Abrufen unter Speicherdruck ab.
Installierte Programm-Prüfsumme, exakte Prozessargumente und Startzeit-Ticks
verhindern doppelte Starts oder Signale an einen wiederverwendeten fremden PID.
Die Kosten einer kalten Cache-Bedingung gehören weiterhin zum Vergleich;
eine erfolgreiche Original-Abnahme wird dadurch nicht vorweggenommen.
Mit drei zusätzlichen Schutzprüfungen bestehen 36 gezielte Tests. Serie `g`
behält bis zu ihrem Ende den bisherigen reaktiven Modus.

Um 19:43:30 UTC löst auch bei Jenkins in Serie `g` der eigene VM-Guard aus:
2.332.900 KiB NAS-Swap liegen unter der Reserve von 2.359.296 KiB. Verfügbares
RAM liegt gleichzeitig über seiner separaten Mindestreserve. Nur die eigene
Test-VM wird zum Herunterfahren aufgefordert. Nach ausbleibendem Gastabschluss
wird ausschließlich diese VM zwangsweise beendet; der äußere Container meldet
keinen OOM-Kill. Die Fehlerpfade der ursprünglichen Jenkins-Jobs sind vollständig
beendet. `analysis-incomplete-target.json` und `final-state.json` halten die
fehlenden Inventare und den unlesbaren Zielzustand ausdrücklich fest.

Die visuelle Prüfung aller 18 Ansichten der tatsächlichen Serie-`g`-Laufhierarchie
findet eine weitere UI-Ungenauigkeit: Der vor Zuweisung abgebrochene Qualitätslauf
zeigt noch zukünftige Runner-Platzhalter. Die lokale Korrektur verwendet für
solche Endzustände `Nicht zugewiesen` und `Nicht erfasst`. Strukturierte Ausgaben
heißen `Gemeldete Ergebnisse`, weil sie historische Worker-Meldungen enthalten
können. Typprüfung und UI-Build bestehen. Diese 18 Ansichten gelten bis zum
Deployment und der erneuten visuellen Prüfung nicht als bestanden.

Serie `full-release-nas-20261011-h` beginnt um 19:51 UTC mit dem gemeinsamen
Profil `nas-6g-ssd-proactive-cache`. Basiskopie, Quellen, Tests, Fixture-Limits
und Testfristen bleiben unverändert. Die Gastregel ist bereits vor dem originalen
CI-Start aktiv: Der Prozess mit PID 4110, Startzeit-Ticks 7723 und Programm-SHA
`a7b0994e376bba3105f9bd458878a2466657f7f293187f41adcf59842f709427`
protokolliert zwei frühe Freigaben. Der Cache sinkt dabei von 856.844 auf
420.212 KiB und von 1.515.544 auf 427.908 KiB. Der nächste Datensatz liegt unter
dem Schwellwert und führt keine Freigabe aus. Das belegt die laufende gemeinsame
Infrastrukturregel, keine bestandene Original-Abnahme.

Der ursprüngliche Leroy-Elternlauf `e23fca2dc33a4b0584165c463189ab25` startet
um 19:54:48 UTC. Sein Web-Kindlauf `c376ddccccaf43dba37d1070233f715c` läuft
mit dem geprüften Worker-Image. Die produktiven Jenkins-Jobs sind beim Start
inaktiv; laufende Transportfehler und NAS-Ressourcen werden weiterhin erfasst.
Der Controller erhält die vorbereitete UI-Korrektur erst nach Ende aktiver
CI-Leases. Der Vergleich ist weiterhin offen.

Leroy endet in Serie `h` erneut mit `interrupted`. Der Elternschritt nennt
`Controller lease could not be renewed (last failure: ReadTimeout)`; Web verliert
ebenfalls seine Lease. Qualität wird nicht gestartet, Originalartefakte fehlen.
Die abgeschlossene Gastregel-Aufzeichnung enthält 22 Messpunkte, 18 tatsächliche
Freigaben und keinen Regel-Fehler. Frühzeitige Gast-Cache-Freigabe allein reicht
somit in dieser Ausführung nicht, um die Lease zu erhalten. Eine frühe lesende
Datenbankprobe zeigt nur kurze WAL-Wartezeiten; eine spätere Probe scheitert
selbst an ihrer zeitlichen Begrenzung. Beobachtungslücken bleiben erhalten.
Der letzte originale Web-Zielzustand meldet die Core-Vorbereitung abgebrochen
und ihre Bereinigung abgeschlossen. Keine Originalbrowserfälle sind vollständig
belegt; der Gast meldet keinen OOM-Kill. Der tatsächliche Zielzustand nach dem
Versuch enthält dasselbe Release-Manifest und vier gesunde Dienste. Das komplette
Produktionsfenster ist ruhig. Jenkins erhält anschließend eine eigene frische
Basis mit derselben vor CI-Start aktiven Gastregel.

Beide Ausgangsmanifeste und äußeren VM-Ressourcen sind identisch. Die
physische RAM-Konfiguration ist mit gleichen BIOS-Bereichen belegt; `MemTotal`
unterscheidet sich um eine 4-KiB-Seite. Die Datenträgerproben bestehen nach
42,824 Sekunden bei Leroy und 41,781 Sekunden bei Jenkins, ohne gemeldete
QEMU-I/O-Fehler. Jenkins-Elternjob #15 startet mit Web #18 und Qualität #16.
Die originale Web-Vorbereitung läuft; Originaltests werden nicht beschleunigt,
verändert oder durch Diagnosen ersetzt.

Um 20:37 UTC meldet der laufende originale Jenkins-Versuch 14 bestandene
Webgruppen mit 34 bestandenen Browserfällen in den Zielquittungen. Der Gast
meldet keinen OOM-Kill. Diese Zwischenquittungen sind noch kein abgeschlossenes,
archiviertes CI-Ergebnis; die Qualitätsprüfung und Release-Quittung fehlen noch.

Für den verbliebenen Steuerungsengpass ist
`scripts/migrate_nas_test_control_storage.py` lokal vorbereitet. Der Helfer darf
erst bei ausgeschalteter Test-VM, gestopptem Test-Jenkins, inaktiven Leroy-Läufen
und deaktivierten Triggern arbeiten. Er kopiert ausschließlich die eigenen
PostgreSQL- und Controller-Volumes auf die vorhandene SSD. Eine logische
Sicherung, bytegenaue physische Kopien einschließlich Dateirechten und ein
Vergleich der Tabelleninhalte vor Start des Controllers sichern den Übergang.
Die bisherigen Volumes bleiben erhalten; Images, Laufzeiteinstellungen,
Durabilität und Lease-Fristen bleiben gleich. Ein eigener Compose-Override
ändert nur die beiden Datenmounts. Der Kopierumfang ist auf vier GiB begrenzt;
40 GiB SSD-Platz plus Kopierbudget werden vor dem Stop geprüft. Syntaxprüfung
und Ruff bestehen, ein NAS-Deployment oder Wirksamkeitsnachweis liegen noch
nicht vor. Die laufende Serie `h` erhält diese Änderung nicht.

Der Statusbeobachter verwendet künftig einen authentifizierten Client über
mehrere Abrufe hinweg. Der bisherige Anmeldehelfer hat die private Sitzung
bereits wiederverwendet; es entfällt die zusätzliche `/api/auth/me`-Abfrage
pro Poll, keine regelmäßige neue Passwortanmeldung. Fünf gezielte Tests prüfen
Verbindungswiederverwendung, Transportfehler, anfängliche Authentifizierungs-
fehler, Sitzungsablauf und verweigerten Zugriff. Sie bestätigen insbesondere,
dass dabei kein ursprünglicher CI-Versuch neu gestartet oder abgebrochen wird
und sensible Fehlertexte nicht in den Beobachtungsnachweis gelangen. Der bereits
laufende `h`-Treiber lädt diese Änderung nicht nach. Ein ursächlicher Anteil der
bisherigen zusätzlichen Sitzungsabfragen am Lease-Ausfall ist nicht belegt.

Um 20:56 UTC ist der originale Jenkins-Webjob #18 mit `SUCCESS` abgeschlossen.
Die Zielquittungen enthalten alle 21 bestandenen Webgruppen und 42 bestandenen
Browserfälle einschließlich Soak; ihre Bereinigung ist abgeschlossen. Qualität
#16 läuft anschließend. Um 20:58 UTC enthält ihr ursprüngliches Frontend-/
Deployment-Log 195 Python-Tests mit sechs erfolgreichen Suite-Abschlüssen.
Rust-, Komponenten- und Smoke-Prüfungen sowie die originale Release-Quittung
bleiben zu diesem Zeitpunkt offen. Der Gast meldet keinen OOM-Kill; die letzten
produktiven Buildnummern sind unverändert. Die Abschlussprüfung verwendet
ausschließlich die noch einzusammelnden Original-CI-Archive. Zusammen mit den
36 zuvor bestandenen gezielten Prüfungen bestehen fünf neue Beobachtertests;
dies sind 41 Prüfungen aus getrennten Aufrufen, kein vollständiger neuer
Testlauf der Anwendung.

Um 21:07 UTC sind alle 98 ursprünglichen Komponentenfälle abgeschlossen:
97 bestehen, einer scheitert. Der Frontend-/Deployment-Schritt meldet deshalb
einen Fehler; die folgenden Qualitätsgruppen werden unverändert ausgeführt.
Die Rust-Formatprüfung besteht anschließend. Die genaue Komponentenfehler-
Signatur und die übrigen Inventare werden erst anhand des Original-CI-Archivs
abschließend bewertet, nicht aus einer Zwischenquittung abgeleitet.

Die lesende SSD-Platzprüfung um 21:10 UTC erfasst 54.778.847.232 freie Bytes.
Die vier bisherigen `g`-/`h`-Overlays belegen zusammen rund 32 GB. Vor einem
weiteren vollständigen Paar ist deshalb `scripts/archive_nas_release_overlays.py`
vorbereitet: ausschließlich diese vier inaktiven Testdatenträger werden in den
eigenen HDD-Testbereich kopiert. Sämtliche Kopien werden bytegenau mit SHA-256,
Größe und Eigentümerrechten geprüft und synchronisiert, bevor irgendeine
Originaldatei von der SSD entfernt wird. Kleine Originaldiagnosen bleiben dort;
ein Archivverweis hält Pfad und Prüfsumme fest. Produktive Buildnummern werden
auch während der Kopie lesend geprüft; eine Änderung bricht die Vorbereitung
ab. Der Helfer verlangt ausgeschaltete Test-VM, gestoppten Test-Jenkins und
inaktive Leroy-Läufe. Syntaxprüfung einschließlich des NAS-Programms und Ruff
bestehen. Die laufende Serie `h` wird weder verschoben noch verändert.

Serie `h` ist um 21:20 UTC beendet. Jenkins-Web #18 hat das originale
522.198-Byte-Archiv mit SHA-256
`d5d0a0c1f7c13339dbae164d11eedc4c34a97797db69faa2be1a9edfbdc6daab`
archiviert. Die strenge Prüfung von Archivindex, Bytes, Quittung, Gruppen und
Fallidentitäten bestätigt alle 21 Webgruppen und 42 Browserfälle einschließlich
Soak. Die sechs Python-Suiten mit zusammen 195 Tests bestehen laut ursprünglichem
Zielprotokoll. Bei den 98 Komponentenfällen scheitert genau einer:
`presented results belong to their chat turn, retain selection, and reveal or explain their source`.
Die Assertion in `apps/desktop/e2e-web/chat-presentation.test.mjs` erwartet den
Fokus auf dem Artikel nach `Show in chat`. Die Quelle und der Test bleiben
unverändert. Diese Signatur ist vorläufig aus dem Original-Zielprotokoll belegt;
ein vollständiges Qualitätsarchiv fehlt.

Um 21:18:58 UTC unterschreitet `MemAvailable` mit 76.748 KiB die unveränderte
NAS-RAM-Reserve von 131.072 KiB. Gleichzeitig sind 4.029.212 KiB Swap frei;
diesmal löst die RAM-Reserve aus, nicht die Swap-Reserve. Die eigene VM wird
nach erfolglosem Gastabschluss zwangsweise beendet, ohne gemeldeten äußeren
OOM-Kill. Clippy ist zu diesem Zeitpunkt nicht abgeschlossen. Qualität #16 und
Elternjob #15 enden mit `FAILURE`; Rust-Testinventar, vier Smoke-Gruppen und
originale Release-Quittung fehlen. `analysis-incomplete-target.json` bewahrt den
fehlenden Jenkins-Zielzustand. Alle vier Produktionsfenster sind ruhig; gleiche
übrige NAS-Hintergrundlast wird weiterhin nicht behauptet. Beide Test-CI-Systeme
sind inaktiv, Test-VM und privates Jenkins gestoppt, der eingefrorene Checkout
ist sauber und unverändert.

Um 21:25 UTC ist die UI-Korrektur mit unveränderten Backend-Layern ausschließlich
im Testcontroller eingespielt. Achtzehn neue Desktop-/Mobilansichten der
Serie-`g`-Hierarchie und zwölf der Serie `h` bestehen technische und vollständige
manuelle Sichtprüfung. Endzustände zeigen `Nicht zugewiesen` beziehungsweise
`Nicht erfasst`; historische strukturierte Ausgaben heißen `Gemeldete Ergebnisse`.
Die ursprünglichen 18 semantisch beanstandeten Bilder bleiben erhalten und zählen
weiterhin nicht als bestanden. Insgesamt sind 305 NAS-Ansichten qualifiziert.
Keine dieser UI-Prüfungen zertifiziert eine vollständige Graphato-Abnahme.

Die SSD-Migration des eigenen Testcontrollers und PostgreSQL ist anschließend
abgeschlossen. 333.551.689 physische Bytes einschließlich Dateirechten sind
identisch geprüft; Tabellenanzahlen und aggregierte Inhaltsprüfsummen stimmen
vor Controller-Start überein. Eine logische Sicherung und die ursprünglichen
benannten Volumes bleiben erhalten. Basis-Compose, Konfiguration und Secret-
Datei haben dieselben Prüfsummen; PostgreSQL, Controller und Runner verwenden
dieselben Images. Der Override ändert nur die beiden Datenmounts.

Die Vorbereitung hatte zwei Fehler: Ein Kopier-Callback erhielt String-Pfade;
nach Korrektur und zwei Regressionstests wurden ausschließlich validierte
Teilkopien fortgesetzt. Danach startete Compose über Abhängigkeiten zusätzlich
den eigenen Docker-Testdienst neu, dessen Gesundheitsprüfung länger dauerte.
Nach seiner tatsächlichen Gesundmeldung wurde der vorhandene Runner gestartet.
Künftige Starts verwenden `--no-deps`. Der private Jenkins wurde nach dem
Docker-Neustart wieder gestoppt. Die Wiederherstellung erhält Images, Dateibytes,
Tabellen und Konfigurationsprüfsummen; ein vollständiger vorheriger Container-
Laufzeitsnapshot ist nicht aufbewahrt und wird deshalb nicht behauptet. Produktive
Dienste wurden nicht geändert; die überwachten Vorbereitungsfenster sind ruhig.

Für das nächste Paar ist das getrennte Profil `nas-6g-ssd-fine-pages` vorbereitet.
Der bereit geprüfte eigene KVM-Gast meldet freie Speicherblöcke ab 64 KiB
(`page_reporting_order=4`) statt ab zwei MiB (`order=9`) zurück. Die Gastkapazität
bleibt sechs GiB; es wird weder Balloon-RAM entzogen noch ein NAS-Kernelparameter
geändert. Die bestehende identische Cache-Regel, Fixture-Limits, Tests und
Schutzreserven bleiben erhalten. Der Gast unterstützt diese
[freie-Seiten-Rückmeldung](https://cdn.kernel.org/doc/html/latest/mm/free_page_reporting.html);
ein Wirksamkeitsnachweis auf dem NAS liegt noch nicht vor. Elf gezielte Prüfungen
decken Gast-/Eigentums-/Startbedingungen und den einzelnen Parameterwechsel ab.
Zusammen mit den zwei Kopiertests, fünf Beobachtertests und 36 vorherigen
gezielten Prüfungen sind dies 54 verschiedene erfolgreiche Prüfungen aus
getrennten Aufrufen, kein vollständiger neuer Anwendungstestlauf.

Die Archivierung endet nach rund 13 Minuten mit vier identischen, dauerhaft
gespeicherten Originaldatenträgern. Die SSD-Kopien werden erst nach vollständiger
SHA-/Größen-/Rechteprüfung aller vier Archive entfernt. Originaldiagnosen und
Archivverweise bleiben erhalten. 86.198.312.960 Bytes sind danach auf SSD frei;
das vollständige Produktionsfenster ist ruhig. Serie
`full-release-nas-20261011-i` startet anschließend mit Jenkins und dem getrennten
Profil `nas-6g-ssd-fine-pages`. Die beobachtete Steuerungsinfrastruktur ist vorab
mit Image-IDs, Ressourcen, Mounts, Konfigurations- und Umgebungsprüfsummen
festgehalten; PostgreSQL bestätigt `fsync`, `synchronous_commit` und
`full_page_writes` jeweils `on`. Der eingefrorene Graphato-Checkout ist weiterhin
sauber. Mehrere explizite Infrastruktur-/Beobachteränderungen zwischen den
Versuchen erlauben keine ausschließliche Ursachenzuordnung zu einer einzelnen
Änderung. Das neue Originalpaar und seine Wirksamkeit bleiben zunächst offen.

Die Gastvorbereitung von Serie `i` besteht: `page_reporting_order` wechselt
belegt von neun auf vier, die sechs-GiB-Konfiguration bleibt erhalten. Die
Datenträgerprobe besteht nach 42,220 Sekunden mit einem GiB und 128 `fsync`s;
vier Dienste sind gesund, alte Quittungen fehlen und QEMU meldet keine I/O-Fehler.
Jenkins-Elternjob #16 scheitert jedoch bereits beim Git-Checkout:
`Could not resolve host: gitea`. Der interne, bestehende Gitea-Container wurde
beim Test-Docker-Neustart gestoppt und nicht wieder gestartet. Netzwerk und
Konfiguration sind erhalten; kein ursprünglicher Graphato-Test wurde ausgeführt.
Die vorhergesagten Web-/Qualitäts-Buildnummern sind keine gestarteten Jobs.
Leroy wird in dieser Serie nicht gestartet.

Der ursprüngliche fehlgeschlagene Elternlauf, sein Checkout-Protokoll und die
Originaldiagnosen bleiben erhalten. Nur der lokale Beobachter wird beendet,
nachdem die originalen Jobs und Queue belegt inaktiv sind. Zielzustand und
Gastregel werden eingesammelt; der private Jenkins und die eigene VM werden
sauber gestoppt. Produktionsfenster sind ruhig. Anschließend wird ausschließlich
derselbe bestehende Gitea-Testcontainer gestartet. ID, Image, vollständige
Containerkonfiguration und Mounts stimmen vor/nach Start überein; Gesundheits-
abfrage und lesendes `git cat-file` bestätigen den Dienst und den eingefrorenen
Commit. Es werden keine Git-Objekte oder Refs geändert.

Der Treiber prüft diesen Dienst und das vorhandene Commit-Objekt künftig vor
VM-Zuweisung oder CI-Dispatch. Bereits abgeschlossene Versuchsnamen bleiben
geschlossen. Bei einem beendeten Jenkins-Elternlauf wartet der Beobachter nur
auf tatsächlich aktive beziehungsweise wartende Originaljobs; fehlen danach
Kindjobs, beendet er seine Beobachtung mit explizitem Unvollständigkeitsnachweis.
Er startet und annulliert keinen Originaljob. Zwei gezielte Regressionstests
prüfen den frühen Checkout-Fehler und einen noch tatsächlich aktiven Kindlauf;
zusammen mit den fünf bisherigen Beobachtertests bestehen sieben Prüfungen in
diesem Aufruf. Insgesamt sind 56 verschiedene gezielte Prüfungen aus getrennten
Aufrufen bestanden.

Um 21:58 UTC beginnt Serie `full-release-nas-20261011-j` mit Jenkins, einer
eigenen neuen VM-Kopie und demselben Profil `nas-6g-ssd-fine-pages`. Gitea ist
wieder verfügbar; alle Originalquellen, Tests, Fixture-Limits, Image-Identitäten
und Schutzreserven bleiben erhalten. PostgreSQL-Durabilität und die vier äußeren
Teststack-Images sind erneut belegt. Die vollständige Original-Abnahme ist offen.

Die neue Jenkins-Vorbereitung besteht einschließlich der originalquittungsfreien
Basis und einer Datenträgerprobe von 43,145 Sekunden. Elternjob #17 startet um
22:02 UTC und läuft über den Git-Checkout hinaus; Web #19 und Qualität #17 sind
als seine ursprünglichen Kindjobs vorgesehen. Das Startfenster ist ruhig.

Eine lesende Speicherprobe während der ursprünglichen Web-Vorbereitung hält
QEMU-RSS, proportionalen Speicher, eigene Cgroup-Zähler und NAS-Speicherbelegung
fest, ohne Prozessargumente, Umgebungen oder Speicherinhalte auszulesen.
Die NAS-Swap-Aufteilung enthält zwei GiB SSD-Partition, vier GiB vorhandene
SSD-Swapdatei und vier ZRAM-Geräte mit zusammen knapp vier GiB logischer
Kapazität. Deren tatsächlicher komprimierter Speicherbedarf liegt in dieser
Probe bei rund 1,34 GB RAM. Freie Swapkapazität und physisch verfügbares NAS-RAM
werden deshalb weiterhin getrennt erfasst. Keine Swapdatei, Host-Kernelregel
oder produktive Konfiguration wird verändert. Der Gast meldet weiterhin
`page_reporting_order=4` und keinen OOM-Kill; diese Zwischenprobe ist kein
vollständiger Abnahme- oder alleiniger Wirksamkeitsnachweis.

Um 22:41 UTC ist Jenkins-Web #19 mit `SUCCESS` beendet. Die strenge Prüfung
des Original-CI-Archivs mit SHA-256
`3a4de88e7799f169699e43e782417bc75a78fd76a7f8f5abdb051d04a6c83c6c`
bestätigt alle 21 Gruppen und 42 ursprünglichen Browserfallidentitäten als
bestanden, einschließlich Soak und abgeschlossener Bereinigung. Runtime-Image,
Quellarchiv-SHA und Build-Zeitstempel entsprechen der unveränderten Basis. Die
zusätzliche reine Prüfskript-Abfrage wird nach Korrektur des verschachtelten
Manifest-Zeitstempelfelds wiederholt; kein CI-Job oder Test wird wiederholt.
`jenkins-original-web-proof.json` enthält den abgeschlossenen Nachweis. Qualität
#17 und die ursprüngliche Release-Quittung bleiben noch offen.

Um 22:52 UTC meldet das ursprüngliche Qualitätsprotokoll wiederum alle 195
Python-Tests aus sechs erfolgreichen Suiten und 98 abgeschlossene Komponenten-
fälle: 97 bestehen, genau einer scheitert an derselben `Show in chat`-Fokus-
Assertion wie in Serie `h`. Zwei Reporterzeilen benennen denselben Fehler;
der Suite-Abschluss zählt ausdrücklich einen fehlgeschlagenen Fall. Die
Frontend-/Deployment-Gruppe endet mit Fehler, die unveränderten folgenden
Qualitätsgruppen werden dennoch ausgeführt. Rust-Formatprüfung läuft;
Clippy, das vollständige Rust-Inventar, Smoke-Gruppen und Qualitätsarchiv fehlen
noch. Der Gast meldet keinen OOM-Kill; beide NAS-Schutzreserven sind eingehalten.


Um 23:02 UTC wird nur der lokale Beobachter von beiden Engines auf Jenkins-only
umgestellt, um die SSD-Kapazität vor der zweiten Original-Abnahme zu prüfen.
Dieselben Buildnummern werden ohne Dispatch oder Annullierung weiterbeobachtet.
Die Jenkins-Testplatte belegt dabei rund 18,2 GB; etwa 67,9 GB sind auf SSD frei,
während die unveränderte Reserve 40 GiB beträgt. Zusätzliche Gastabfragen haben
unter Clippy-Last Zeitüberschreitungen; diese Lücken bleiben erhalten. Der reine
Fortschrittsbeobachter erfasst die Fehler anschließend als bereinigten Fehlertyp.

Die Formatgruppe besteht. Serie `j` erreicht jedoch am 11. Oktober um 23:10:53 UTC
die physische NAS-RAM-Reserve: `MemAvailable=83.492 KiB` liegt unter 131.072 KiB.
`SwapFree=3.143.544 KiB` liegt oberhalb der unveränderten Swapreserve. Die eigene
VM wird zwangsweise gestoppt; äußerer Exitcode ist null, `OOMKilled=false`.
Elternjob #17 und Qualität #17 enden mit `FAILURE`. Alle ursprünglichen Jenkins-
Jobs sind beendet und der private Jenkins ist gestoppt. Die beiden vollständigen
Produktionsfenster bestätigen keine Überschneidung, trotz erhaltener Lücken der
Zwischenabfragen. Die erfolgreiche Original-Web-Abnahme mit 42 Fällen bleibt
belegt. Die zuletzt beobachteten 195 Python-Fälle und 98 Komponentenfälle sind
Teilprotokolle; Clippy-Abschluss, vollständiges Rust-Inventar, Smoke-Gruppen,
Qualitätsarchiv, Elternquittung und lesbarer Zielzustand nach dem Lauf fehlen.
Leroy wird in dieser gescheiterten Serie nicht gestartet. `final-state.json` und
`analysis-incomplete-target.json` schließen diesen unvollständigen Versuch ab.

Für die nächste eigene Serie `full-release-nas-20261012-k` wird das separate
Profil `nas-6g-ssd-soft-ram` vorbereitet. Es setzt ausschließlich `memory.high`
der verifizierten VM-Cgroup auf drei GiB, damit Speicherrückgewinnung vor einer
globalen NAS-RAM-Knappheit einsetzt. Gastkapazität, harte Docker-Grenzen, SSD-I/O,
Original-Fixture-Limits, Quellen, Tests und Schutzreserven bleiben unverändert;
beide Engines erhalten dieselbe Regel. Container-ID, Namespace, Engine, Commit,
PID-Startzeit, Cgroup-Pfad und bestehende harte Grenzen werden vor der Änderung
prüfbar validiert. Globale Host-Kernelparameter werden nicht verändert.
Die [Kernel-Dokumentation](https://docs.kernel.org/admin-guide/cgroup-v2.html)
beschreibt die Rückgewinnungs-/Drosselwirkung und mögliche Überschreitungen der
Schwelle; sie ersetzt keinen Wirksamkeitsnachweis. 18 zusätzliche Schutz-,
Wiederaufnahme- und Profilprüfungen bestehen. Der gemeinsame gezielte Aufruf
besteht mit 58 Prüfungen; einschließlich vorheriger getrennter Prüfungen sind
74 verschiedene gezielte Prüfungen bestanden, kein vollständiger Anwendungslauf.
Die tatsächliche NAS-Anwendung und der vollständige neue Vergleich bleiben offen.

Der NAS-Kernel ist `6.18.15`; seine verifizierte 6.18-Kernelimplementierung
unterstützt `O_NONBLOCK` für `memory.high`. Die einzelne Cgroup-Datei wird mit
`O_NONBLOCK` und `O_NOFOLLOW` geschrieben; Rücklesen, Identitätsprüfung und
Originalgrenzen bleiben Pflicht. Dadurch wartet der SSH-Verwaltungsprozess nicht
auf synchrone Rückgewinnung. Eine frühere lokale Infrastrukturaufnahme wird als
Vorbereitungsentwurf erhalten; die finale Aufnahme vor dem ersten Original-CI-
Start erfasst die abgeschlossene Implementierung einschließlich aller sechs
Vergleichs-/VM-Helferprüfsummen. Noch ist kein Job der neuen Serie gestartet.

Die abgeschlossene Jenkins-Platte der Serie `j` wird anschließend offline als
19.698.548.736 Byte große Originaldatei erhalten. SHA-256, Größe, Eigentümer,
Rechte, Zeitstempel und dauerhaft gespeicherte Kopie stimmen überein; erst danach
wird ausschließlich die SSD-Datei entfernt. Alle Diagnose-/CI-Dateien bleiben
unverändert. Das Archivierungsfenster ist vollständig ruhig, und auf SSD sind
86.140.956.672 Byte frei. Die neue Serie `k` beginnt danach mit Jenkins-only-
Beobachtung, damit die Kapazität vor Leroy explizit geprüft werden kann. Der
Original-CI-Start erfolgt erst nach vollständiger gemeinsamer Gastvorbereitung;
alle Images und PostgreSQL-Durabilitätswerte sind erneut erfasst.

Die reale NAS-Vorbereitung von `k` bestätigt die neue Cgroup-Regel: `memory.high`
wechselt von `max` auf 3.221.225.472 Byte. Harte RAM-Grenze 7.516.192.768 Byte,
Swapgrenze 3.221.225.472 Byte, Gastkapazität sechs GiB und sechs CPUs bleiben
bestehen. `page_reporting_order=4`, vier gesunde Dienste und fehlende alte
Quittungen sind belegt. Die Datenträgerprobe besteht nach 41,828 Sekunden mit
einem GiB, 128 `fsync`s und null QEMU-I/O-Fehlern. Eine Vorbereitungsbeobachtung
prüft die Schwelle vor ihrer Anwendung und bleibt als nicht erfolgreiche
Zwischenabfrage erhalten; die explizite Anwendung und alle Startbedingungen
bestehen danach. Das gesamte Vorbereitungsfenster ist ruhig.
Um 23:29:23 UTC wird Jenkins-Elternjob #18 ausgelöst; Web #20 startet und führt
die ursprüngliche Browser-Abnahme aus. Qualität #18 ist noch nicht gestartet.
Dies ist der Beginn des Originallaufs, kein Wirksamkeits- oder Abnahmeabschluss.

Um 00:08 UTC am 12. Oktober endet Jenkins-Web #20 mit `SUCCESS`. Die strenge
Originalarchivprüfung bestätigt alle 21 Gruppen und 42 ursprünglichen Fälle,
einschließlich Soak und Bereinigung. Archiv-SHA-256 ist
`07c4d2a366c7197d386c2657d6f414322dfdf2b1077967aec0d1e5e44b45b5c1`.
Runtime-Image, Quellarchiv-SHA und Build-Zeitstempel entsprechen unverändert
der Basis. `jenkins-original-web-proof.json` hält diesen abgeschlossenen
Teilnachweis fest. Der reale Original-Qualitätsjob #18 ist anschließend gestartet;
vollständiges Qualitätsinventar, Elternquittung und Leroy bleiben offen.

Um 00:20 UTC ist die erste Qualitätsgruppe abgeschlossen: 195 Python-Tests aus
sechs Suiten bestehen, und alle 98 Komponentenidentitäten sind im ergänzend
lesend gesicherten Zielprotokoll belegt. 96 Fälle bestehen, zwei scheitern:
`presented results belong to their chat turn, retain selection, and reveal or explain their source`
(Fokus-Assertion) und
`real embedded host preserves startup progress through session allocation and view readiness`
(`Retry renderer` fehlt nach fünf Sekunden, `embedded-startup.test.mjs:63`).
Der zweite Fehler trat in den früheren Jenkins-Teilprotokollen nicht auf; eine
Zuordnung zu Leroy oder der neuen Cgroup-Regel ist nicht belegt. Während der
Frontend-Phase melden die beobachteten Cgroup-Zähler `high=0` und `oom_kill=0`.
Originaltests und Quellen bleiben unverändert. Das ergänzende Zielprotokoll ist
explizit kein CI-Archiv; dessen Bytes müssen später mit dem Originalarchiv
übereinstimmen. Formatprüfung läuft. Der spätere Vergleich muss einzelne
Testausgänge berücksichtigen: Zwei identische fehlerhafte Gruppenstatus allein
belegen keine identischen fehlgeschlagenen Fälle.

Ein rein lokaler zusätzlicher Auswerter `compare_nas_original_test_outcomes.py`
vergleicht nach vorhandener vollständiger Original-CI-Auswertung Browser- und
Komponentenausgänge je Identität, originale Rust-Ereignisse mit ihrer
Namens-/Status-Multiplizität und die erfolgreichen Python-Suiten. Gleiche
Gruppenstatus werden getrennt ausgewiesen; fehlende Fälle können keine Parität
belegen. Ergänzende Zielprotokolle müssen mit den späteren Originalarchivbytes
übereinstimmen. Fünf gezielte Regressionen bestehen, darunter zwei fehlerhafte
Gruppen mit unterschiedlichen fehlgeschlagenen Fällen. Insgesamt sind nun 79
verschiedene gezielte Prüfungen aus getrennten Aufrufen bestanden. Dieser Helfer
kontaktiert weder CI noch Ziel und startet keinen Test. Die sechs vor dem
laufenden Originalpaar festgehaltenen Ausführungshelfer bleiben unverändert.

Während der Rust-Prüfimage-Vorbereitung melden die NAS-Cgroup-Zähler erstmals
Rückgewinnungsdruck (`high=1308` in der Probe um 00:23 UTC), ohne Cgroup-OOM-Kill.
Dies belegt das Auslösen der neuen Regel, noch nicht den Abschluss unter der
zuvor kritischen Clippy-Last. Die Original-Formatgruppe arbeitet weiter.

Die Formatgruppe besteht anschließend. Um 00:39:01 UTC am 12. Oktober löst
jedoch der unveränderte freie-Swap-Schutz aus: 2.324.764 KiB liegen unter der
Reserve von 2.359.296 KiB; gleichzeitig sind noch 637.288 KiB NAS-RAM verfügbar.
Die eigene VM fährt bis 00:39:34 UTC regulär herunter (`forced=false`, QEMU-
Exitcode null, kein äußerer OOM-Kill). Clippy war noch nicht abgeschlossen;
vollständiger Rust-Testlauf und die vier anschließenden Qualitätsgruppen sind
nicht belegt. Die drei Original-Jenkins-Jobs enden ohne Neustart: Web #20
`SUCCESS`, Qualität #18 und Elternjob #18 `FAILURE`. Das Original-Qualitätsarchiv
und die Elternquittung fehlen; das vorhandene originale Abbruchartefakt und alle
Konsolen bleiben erhalten. Die Zielaufnahme nach Jenkins ist wegen der
heruntergefahrenen VM nicht beobachtbar. Die neue Speicherregel hat den
vollständigen Jenkins-Lauf somit nicht ermöglicht. Das ist kein Leroy-spezifischer
Fehler und kein vollständiger Release-Nachweis. Vor dem geplanten zweiten
Originalmotor werden die Jenkins-Belege abgeschlossen und die unveränderte
SSD-Platte offline gesichert; Leroy erhält dieselbe frische Basis und dasselbe
Ressourcenprofil. Es wird keine Reserve während des Vergleichs abgesenkt.

Das vollständige native Jenkins-Historienfenster des ersten Motors ist ruhig.
Die regulär heruntergefahrene Jenkins-Platte wird anschließend mit allen
19.706.216.448 Originalbytes erhalten; SHA-256
`bd0104ad0d08b48887b5e384a2e3048057288a24040e73f73b5e617cbc41df8d`,
Eigentümer, Rechte, Größe, Zeitstempel und dauerhaft gespeicherte Kopie sind
verifiziert. Erst danach wird die einzelne SSD-Datei entfernt. Das gesamte
Archivierungsfenster ist ruhig; auf SSD sind danach 86.152.343.552 Byte frei.
Dieses Archiv dient nicht als Leroy-Basis.

Leroy startet um 00:52:17 UTC am 12. Oktober als Original-Elternlauf
`e1beaa62574e4a508d14fc696ff9e164`. Die frische Basis hat keine alten Quittungen;
Release-Manifest, äußere RAM-/CPU-/I/O-Grenzen, Gastressourcen, Page-Reporting und
`memory.high` entsprechen Jenkins. Die Datenträgerprobe besteht nach 41,881
Sekunden mit einem GiB, 128 `fsync`s und null QEMU-I/O-Fehlern. Das vollständige
Wiederherstellungsfenster ist ruhig. `common-preparation-proof.json` bestätigt
ausdrücklich nur die beiden Startzustände, keine vollständigen Endzustände.
Die gleichen sechs Ausführungshelfer und Infrastruktur bleiben unverändert;
die Originalsourcen und Tests sind weiterhin sauber. Leroys Webgruppe beginnt.

Ein vorläufiger Logvergleich findet im Leroy-Worker-Bau mehrere Minuten lang
keine neue Meldung nach einem Workspace-Test. Die spätere Originalmeldung
bestätigt jedoch den Abschluss derselben Prüfstufe nach 39,3 Sekunden; Jenkins'
Originalarchiv meldet 40,4 Sekunden. Das anschließende Exportieren dauert bei
Leroy 203,5, bei Jenkins 196,3 Sekunden. Der verzögert sichtbare Logabschluss
belegt keinen Testhänger oder CI-Fehler. Die zusätzliche Prozess-/Fixture-Abfrage
ist rein lesend; kein Test wird geändert oder neu gestartet. Gegen 01:04 UTC
liegt die abgeschlossene ursprüngliche Browser-Core-Gruppe mit 21 erfolgreichen
Fallquittungen vor. Dies ist zunächst ein Zielprotokoll, noch kein abschließend
verifiziertes Original-CI-Archiv des gesamten Webjobs.

Während Leroy um 01:19 UTC noch die Web-Abnahme ausführt, meldet die laufende
lesende Produktionsabfrage `music-library-sync-smartphone` #241 als aktiv.
Der funktionale Originallauf wird fortgesetzt; Produktionsjob und Trigger
bleiben unberührt. Die Überschneidung ist im Live-Journal und im Beobachter-
Ausgang gespeichert. Um 01:20:57 UTC ist kein produktiver Job mehr aktiv.
Dieses spätere Ende stellt die Lastqualifikation des gesamten Leroy-Fensters
nicht wieder her: Der Buildzähler hat sich geändert. Jenkins' erster Original-
Vergleichslauf und beide Wiederherstellungsfenster waren dagegen vollständig
ruhig. Gleiche sonstige NAS-Hintergrundlast ist weiterhin nicht belegt.

Um 01:30 UTC endet Leroys ursprünglicher Webjob
`7f983231c8f543c993c256f5de856398` mit `succeeded`. Die unabhängige reine
Artefaktsammlung und strenge Prüfung bestätigen alle 21 Gruppen, alle 42
ursprünglichen Fallidentitäten, Soak und abgeschlossene Bereinigung. Quell-SHA,
Runtime-ID und Build-Zeitstempel entsprechen der unveränderten Basis.
Leroys originales Archiv hat SHA-256
`2a00c5de881f36b358a88b3c19f634b4e2e5bb81f065be446aa17fabe2bbdcb2`.
`original-web-outcome-comparison.json` bestätigt identische ursprüngliche
Browserausgänge je Fall unter beiden Engines. Dies ist ein vollständiger
funktionaler Web-Vergleich, keine vollständige Qualitäts-/Elternabnahme oder
qualifizierte Lastmessung. Der echte Original-Qualitätslauf
`d4f944682cc74c229240ea1001a565a3` wird danach angelegt; keine Tests werden ersetzt.

Gegen 01:42 UTC endet Leroys erste Qualitätsgruppe mit `FAILURE`: Alle 195
Python-Tests aus den sechs ursprünglichen Suiten bestehen. Das vollständige
ursprüngliche Komponenteninventar umfasst erneut 98 Identitäten, davon 97
erfolgreich und ein Fokusfehler. Jenkins hatte bei demselben Stand 96/98 mit
dem zusätzlichen Startup-Fehler. Die strikt geprüften ergänzenden Zielprotokolle
haben genau eine unterschiedliche Fallantwort: `real embedded host preserves
startup progress through session allocation and view readiness` ist bei Jenkins
fehlgeschlagen und bei Leroy erfolgreich. Der Fokusfall scheitert bei beiden.
`supplementary-component-outcome-comparison.json` bezeichnet diese Belege
ausdrücklich als Zielprotokolle, nicht als zwei Original-CI-Archive. Quell-SHA,
Runtime-ID und Build-Zeitstempel sind für die Leroy-Quittung geprüft. Ein früher
lokaler Auswertungsversuch vor Abschluss der Dateiübertragung findet die Datei
noch nicht; die Sammlung wird ohne erneute CI-Ausführung abgeschlossen und erst
danach ausgewertet. Formatprüfung läuft; Clippy, Rust-Inventar, weitere Gruppen
und Elternquittung bleiben offen. Die einzelne Abweichung belegt noch keine
exklusive Ursache in CI, Ausführungsbedingungen oder Anwendung.

Um 01:50 UTC besteht auch Leroys Original-Formatgruppe, und Clippy startet.
Eine zusätzliche rein lesende Cgroup-/Gastaufnahme während der Imagevorbereitung
erfasst etwa 2,38 GB anonymen äußeren Speicher und 337 MB Dateicache. Der Gast
meldet dabei 4.027.664 KiB freie Seiten. Eine zweite Leseprüfung bestätigt das
ausgehandelte Reporting-Feature des Virtio-Balloon-Geräts; die Init-on-free-
Standardoption ist nicht eingeschaltet. Es werden keine Limits, Caches oder
Kernelparameter durch diese Diagnose geändert. Die Werte erlauben noch keine
exklusive Ursachenbehauptung für den Swap-Abbruch unter Jenkins. Der original
laufende Clippy-Job, vollständiges Rust-Inventar, vier weitere Qualitätsgruppen
und Elternquittung bleiben zu diesem Zeitpunkt offen.

Leroys eigener Schutz wird um 02:02:18 UTC ausgelöst: `MemAvailable` beträgt
784.808 KiB, freier Swap 2.333.720 KiB, unter der unveränderten Grenze von
2.359.296 KiB. Nach Ablauf der Shutdown-Frist wird QEMU zwangsweise beendet;
QEMU meldet Exitcode null, Docker keinen OOM-Kill. Die VM endet um 02:04:55 UTC.
Originalqualität und Elternlauf sind `failed`; der Collector sichert deren
Original-CI-Logs und Artefaktverzeichnisse, kann den ausgeschalteten Zielgast
aber nicht mehr lesen. Es werden kein Endzustand und keine Qualitätsquittung
erfunden. Beide Qualitätsjobs enthalten nur ihre ursprüngliche
`cancellation.json` mit unbestätigter Bereinigung; Qualitätsarchiv und
`release-status.json` fehlen bei beiden. Rust-Inventar und vier weitere
Qualitätsgruppen bleiben unvollständig. Der gesamte Laufbaum ist terminal.

`analysis-incomplete-target.json` bestätigt den vollständigen identischen
Webvergleich und genau eine unterschiedliche ergänzende Komponentenantwort
(Startup: Jenkins fehlgeschlagen, Leroy bestanden). Es zertifiziert ausdrücklich
keinen vollständigen Original-Qualitätsvergleich. `final-state.json` bestätigt
beide abgeschalteten CI-Versuche, ausgeschaltete Test-VM, weiterhin unberührte
Produktion und den wegen Musik #241 ungeeigneten Leroy-Lastvergleich. Der
abschließende lesende Produktionscheck findet keinen aktiven Job, prüft aber
nicht die Live-Queue. Ein fehlgeschlagener erster Infrastrukturvergleich beruht
ausschließlich auf Docker-Mount-Listenreihenfolge. Die rohe Beobachtung bleibt
erhalten; nach Sortierung nur dieser Listen stimmen alle Mount-Felder, Images,
Ressourcen, Konfigurations- und Helferprüfsummen und PostgreSQL-Durabilität
überein. Keine Umgebung wird für diese Auswertung verändert.

18 neue Desktop-/Mobilansichten des tatsächlichen Leroy-Laufbaums bestehen die
technische Prüfung und werden anschließend sämtlich direkt visuell angesehen:
Graph, Mobilzeitachse, Fehler und Erfolg, Konsolen, Ergebnisse, Parameter,
Ausführungsidentität, Kind-/Elternverweise und Artefakte. Zwei Downloads stimmen
in Größe und SHA-256. Der Bericht dokumentiert die tatsächlich geprüften Bilder
mit Prüfsummen; die Anzahl qualifizierter historischer NAS-Ansichten steigt auf
323. Eine erfolgreiche UI-Prüfung ist keine bestandene Anwendungsabnahme.

## Neuer gemeinsamer Versuch `l`

Erst nach Abschluss beider Originalmotoren wird ein neues Profil
`nas-6g-ssd-soft-ram-3328` ergänzt. `memory.high` beträgt 3.328 statt 3.072 MiB;
die beabsichtigte Verschiebung von Swap zu RAM betrifft nur die eigene
Test-VM-Cgroup. Die dokumentierten freien RAM-Werte beim letzten Swap-Abbruch
motivieren den Versuch, beweisen aber keine ausschließliche Ursache. Gast-RAM
(sechs GiB), CPUs, harte RAM-/Swap-Grenzen, I/O-Budgets, Cache- und Page-Reporting-
Verfahren sowie sämtliche NAS-Schutzreserven bleiben unverändert. Gleiches
Profil und neue festgeschriebene Helferprüfsummen gelten für beide Engines.
Vier zusätzliche Prüfungen sichern Profilwahl, unzulässige Profile vor jedem
Fernzugriff und unveränderte harte Grenzen; die gezielte Auswahl besteht mit
60 Tests, Ruff besteht. Die alte Serie wird weder umgeschrieben noch erneut
gestartet. Vor einer frischen SSD-VM wird Leroys alte Originalplatte offline
bytegenau archiviert; der zwangsweise Shutdown bleibt Teil dieses Nachweises.

Leroys Originalplatte aus `k` wird anschließend mit 19.767.820.288 unveränderten
Bytes archiviert; SHA-256
`b5b99cbb616afddebf599bc30a7b49c9c97cc02980c622ff5560771547e4aad3`.
Eigentümer, Rechte, Größe, Zeitstempel und dauerhaft gespeicherte Kopie stimmen.
Erst danach wird die einzelne SSD-Quelldatei entfernt; alle kleinen Diagnosen
und der Archivverweis bleiben erhalten. Das ganze Archivierungsfenster ist
ruhig. Die freie SSD-Kapazität beträgt danach 86.139.281.408 Byte. Die Kopie
beweist keine saubere Gastabschaltung und wird nicht als neue Basis verwendet.
Die neue Infrastrukturaufnahme schreibt die sechs neuen Helferprüfsummen vor
dem ersten Start von `l` fest; Images, Secrets-Umgebungsprüfsummen, Ressourcen,
Mounts und PostgreSQL-Durabilität entsprechen der erhaltenen Konfiguration.

Jenkins' neue Wiederherstellung ist ruhig. Die tatsächliche VM-Cgroup liest
3.489.660.928 Byte `memory.high` zurück; harte Grenzen bleiben sieben GiB RAM
und drei GiB äußerer Swap. Die ursprüngliche Gastkapazität und Fixture-Grenzen
bleiben sechs GiB. Die neue Datenträgerprobe besteht nach 42,235 Sekunden mit
einem GiB, 128 `fsync`s und null I/O-Fehlern. Jenkins-Elternlauf #19 startet
um 02:20:40 UTC mit geplantem Web #21 und Qualität #19. Browser-Core bestätigt
gegen 02:32 UTC alle 21 ursprünglichen Fälle. Diese erste Zielquittung ist noch
kein abgeschlossenes Original-CI-Archiv des gesamten Webjobs; die ursprüngliche
Pipeline wird unverändert fortgesetzt. Währenddessen werden produktive
Jenkins-Jobs weiter lesend beobachtet.

Um 02:59 UTC besteht Jenkins-Web #21 vollständig. Die separat gesammelten
Original-CI-Artefakte bestätigen alle 21 Gruppen und 42 ursprünglichen Fälle,
einschließlich Soak und abgeschlossener Bereinigung, bei unveränderter Quell-SHA,
Runtime-ID und Release-Zeitstempel. Originalarchiv-SHA-256:
`92b2551e87e0d55462afe6b9e30512308094ef4d856d2cb325bc25da77201b86`.
Jenkins-Qualität #19 ist danach aktiv und beginnt mit Frontend und Deployment.
Eine vollständig bestandene Qualitäts- oder Elternabnahme ist damit noch nicht
belegt; Leroy wurde in `l` noch nicht gestartet.

Die erste Qualitätsgruppe endet gegen 03:10 UTC mit Fehler. Alle 195 Python-Tests
aus sechs Suiten bestehen; von den 98 ursprünglichen Komponentenfällen bestehen
96. Wie im vorherigen Jenkins-Versuch scheitern Fokusprüfung und Startup-/
Renderer-Prüfung. Der rein lesende Zusatzcollector sichert 130.453 unveränderte
Logbytes, prüft vollständiges 98-Fälle-Inventar sowie Quell-/Runtime-/Zeitstempel-
Identität und bezeichnet die Datei ausdrücklich als ergänzendes Zielprotokoll.
Das abschließende Original-CI-Qualitätsarchiv liegt zu diesem Zeitpunkt noch
nicht vor. Der Originallauf setzt die Formatgruppe fort; er wird nicht neu
gestartet. Eine Speicheraufnahme während der ersten Gruppe ist separat erhalten
und verändert keine Limits, Caches oder Tests.

Gegen 03:19 UTC besteht auch Jenkins' ursprüngliche Formatgruppe. Clippy startet
mit dem unveränderten Originalkommando und seiner bisherigen Frist. Der
vollständige Rust-Testlauf, vier weitere Qualitätsgruppen und die Elternquittung
bleiben offen. Die laufenden lesenden Produktionsabfragen sind bis zu diesem
Zeitpunkt ruhig; Gleichheit anderer NAS-Hintergrundlast ist nicht nachgewiesen.

Um 03:30:21 UTC greift erneut die unveränderte freie Swap-Reserve:
2.356.364 KiB liegen unter der Grenze von 2.359.296 KiB. Freier verfügbarer RAM
liegt mit 578.684 KiB oberhalb seiner 131.072-KiB-Reserve. Nach der regulären
Shutdown-Frist wird die eigene Jenkins-Test-VM um 03:31:12 UTC zwangsweise
beendet; ein äußerer Docker-OOM-Kill ist nicht verzeichnet. Dies beweist weder
eine saubere Gastabschaltung noch eine ausschließlich durch Swap verursachte
Anwendungsabweichung. Web #21 bleibt erfolgreich, Qualität #19 und Elternjob
#19 schließen fehlgeschlagen ab. Der gesamte ursprüngliche CI-Laufbaum ist
terminal. Qualitätsarchiv und Elternquittung fehlen; erhalten ist die originale
189-Byte-`cancellation.json` mit unbestätigter Bereinigung. Die nachträgliche
Zielaufnahme ist nicht mehr möglich und wird nicht durch einen Gastneustart
nachgestellt. Die vollständigen Produktionshistorien qualifizieren sowohl
Wiederherstellungs- als auch Jenkins-Testfenster als ruhig. Leroy wird erst nach
Sicherung dieser abgeschlossenen Nachweise unter demselben Profil gestartet.

Die abgeschaltete Jenkins-Platte wird mit 19.759.169.536 identischen Bytes und
SHA-256 `8a4bea8d1b2abd2a9eb570fff9fef882d88d0308c0f48a6cddf4ca5da4bd0f2c`
dauerhaft auf HDD gesichert. Erst nach vollständigem Byte-/Metadatenvergleich
wird die einzelne SSD-Quelldatei entfernt. Das Archivierungsfenster ist ruhig;
der ursprüngliche Zwangsstopp bleibt im Nachweis enthalten. Leroy startet um
03:49:36 UTC mit frischer unveränderter Basis, Eltern-ID
`9d9ce8c0388b432f934abb4bbfc84049`. Auch seine Wiederherstellung ist ruhig.
Der Vergleich tatsächlicher Voraufnahmen bestätigt identisches Release-Manifest,
Gastkapazität, CPU-, RAM-, Swap-, I/O- und `memory.high`-Werte. Eine zusätzliche
rein lesende Aufnahme identifiziert ausdrücklich den echten Virtio-Balloon-
Treiber und sein ausgehandeltes Free-Page-Reporting; seine Order bleibt vier.
Das belegt die aktivierte Funktion, nicht ihre Wirksamkeit unter jeder Last.

Leroys Web- und Qualitätskind enden jeweils nach etwa 30 Sekunden mit
`Runner infrastructure failure: TimeoutExpired`, vor Checkout oder Teststart.
Die Docker-Ereignisse zeigen spätere Container-Erstellung, aber weder Assignment-
Kopie noch Start dieser beiden Kinder. Das begrenzt die konkrete Ursache auf die
Runner-Vorbereitung; es ist kein Graphato-Testergebnis. Der ursprüngliche
Elternlauf endet ebenfalls fehlgeschlagen und sichert eine wahrheitsgemäße
`release-status.json` ohne vollständige Abnahme. Beide gesamten Produktions-
Testfenster sind anhand der Historien ruhig, andere NAS-Hintergrundlast bleibt
unbewiesen. Die Nachaufnahme von Leroys unverändertem Ziel gelingt; seine
Test-VM wird nach allen terminalen CI-Läufen regulär abgeschaltet. Alle sechs
Ausführungshilfen, Images, Ressourcen, Mounts, Konfiguration und PostgreSQL-
Durabilität stimmen in den abschließenden Infrastrukturaufnahmen überein.

18 neue Desktop-/Mobilansichten des echten fehlgeschlagenen Laufbaums bestehen
technisch und nach direkter Sichtprüfung aller einzelnen Bilder. Ein tatsächlicher
Artefakt-Download stimmt in Größe und SHA-256; die leeren Kindlogs und fehlenden
Kindartefakte werden korrekt gezeigt. 341 historische NAS-Ansichten sind damit
qualifiziert. Auch diese UI-Prüfung ersetzt keine vollständige Release-Abnahme.

Erst nach Abschluss dieser Serie wird Leroys Runner angepasst: Container-
Erstellung, Assignment-Kopie und Start erhalten eine begrenzte 120-Sekunden-
Frist, die unveränderte 90-Sekunden-Server-Lease wird während der Vorbereitung
unabhängig erneuert. Vor und nach jedem Docker-Aufruf wird die Startberechtigung
geprüft. Fehler nennen die Operation und den Typ, niemals Kommandoargumente
mit Attempt-Token oder Zugangsdaten. Die eigentlichen Graphato-Prüfkommandos,
Tests, Ressourcen und Testfristen werden nicht verändert. Sechs neue gezielte
Startup-Prüfungen und vorhandene Lease-/Worker-Prüfungen bestehen gemeinsam
mit 22 Tests; Ruff besteht. Die Wirksamkeit auf dem NAS ist gesondert nachzuweisen.

Die Korrektur ist danach ausschließlich im isolierten NAS-Supervisor installiert:
neues Runner-Image `4f48c8a5ead4bfd0f97e3223be10a01e1c2b1162823f85c820ca0f397da670e1`,
Runner-Modul-SHA `ea7b002e386459688e8f70023b47f57af3f5c8eb4da880e4e4ad9f8dd6e2c66a`.
Die Originalabbilder bleiben erhalten. Image-Konfiguration und Abhängigkeiten,
Runner-Umgebung, Ressourcen und Mounts sowie Controller, PostgreSQL, Docker-
Daemon und der tatsächlich konfigurierte unveränderte Graphato-Worker werden
verifiziert. Die zunächst abgelehnte geordnete Env-Liste stimmt als Menge und
anhand der vorher festgeschriebenen SHA überein; die Installation wird nicht
wiederholt. Das komplette Installationsfenster ist ruhig.

## Leroy-Nachprüfung `m` nach der Runner-Korrektur

Ein neuer vollständiger Leroy-Originallauf wird aus derselben frischen Basis
vorbereitet. Jenkins wird nicht nochmals disponiert: Seine abgeschlossenen
Originalnachweise aus `l` bleiben ausdrücklich verlinkte Referenz. Der Wechsel
des Leroy-Supervisor-Images wird im Vergleich offengelegt; eine identische
globale Infrastruktur über diese beiden Testfenster wird nicht behauptet.
Gastkapazität, harte Limits, Quellen, Tests, Worker-Image, ursprüngliche Fristen
und gemeinsame sechs Ausführungshilfen bleiben unverändert. Die fehlgeschlagenen
Leroy-Originalläufe aus `l` bleiben erhalten. Der neue Versuch ersetzt weder
deren Fehler noch Jenkins' fehlenden Qualitätsnachweis.

Der neue Elternlauf `4a7abe4f24f749ec87e794b87dce4d88` startet um 04:06:53 UTC.
Die vollständige Wiederherstellungshistorie ist ruhig. Tatsächliche Voraufnahmen
bestätigen identisches Release-Manifest und gleiche Gast-/Cgroup-/I/O-Budgets
gegen die verlinkte Jenkins-Referenz; der Supervisor-Unterschied bleibt sichtbar.
Der Web-Kindjob erreicht nach der Korrektur tatsächlich die Originaltests und
scheitert nicht erneut vor Checkout an der früheren 30-Sekunden-Frist. Gegen
04:18:48 UTC besteht die ursprüngliche Core-Gruppe vollständig mit 21 Fällen.
Dies ist zunächst eine Zielquittung; das vollständige Original-CI-Webarchiv
bleibt bis zum Abschluss aller Gruppen offen. Die übrigen Webgruppen laufen
unverändert weiter, produktive Jenkins-Builds werden weiter lesend beobachtet.

Eine zusätzliche lesende Zeitstempelaufnahme bestätigt die tatsächliche Lease-
Erneuerung bereits vor dem Containerstart: sechs erfolgreiche Controller-
Heartbeats beim Elternlauf und sieben beim Web-Kind. Docker-Start und vorherige
Claim-Zeit liegen diesmal 17,193 beziehungsweise 21,102 Sekunden auseinander.
Damit ist die Startup-Ownership auf dem NAS tatsächlich belegt. Dieses aktuelle
Startfenster enthält keinen erneut über 30 Sekunden dauernden Containerstart;
die frühere Timeout-Ursache bleibt durch die ursprünglichen Ereignisse aus `l`
dokumentiert. Keiner dieser Zusatzcollector verändert Tests oder Testfristen.

Anschließend beendet der ursprüngliche Leroy-Web-Kindlauf
`a470d7030fe341fda01d204990162db8` alle 21 Gruppen mit allen 42 Fällen erfolgreich,
einschließlich des unveränderten Soak-Tests. Sein tatsächliches CI-Webarchiv
hat SHA-256 `a5a2625dbc9a4688541ffaf66e370713d0780f9ce94be994fac7363a38d0dd83`.
Der Collector prüft vollständige Originalfall-Inventare, Quellen, Runtime,
Build-Zeitstempel, Abschluss und Cleanup. Die Qualitätsprüfung startet danach
als Originalkind `4e2439aefc354ce4817021ffb0caafc5`; die folgenden Absätze halten
ihren tatsächlichen Abschluss fest.

Der fallweise Offlinevergleich dieser beiden originalen Webarchive bestätigt
42 identische erfolgreiche Ergebnisse. In Leroys abgeschlossener erster
Qualitätsgruppe bestehen 195 Python-Tests aus sechs Suiten und 97 von 98
Komponententests. Das ergänzende, unveränderte Zielprotokoll ist gesichert;
es gilt bis zur Sammlung des Qualitätsarchivs ausdrücklich nicht als originales
CI-Artefakt. Die gemeinsame Chat-Präsentations-Assertion erwartet innerhalb
von fünf Sekunden Fokus auf der Agentenantwort und erhält bei beiden Engines
`inactive`. Der zusätzliche Jenkins-Fehler erwartet den sichtbaren Button
`Retry renderer`; dieser Test besteht unter Leroy. Gleiche Quellen und
Testinventare belegen diese Ergebnisabweichung, aber nicht ihre Ursache.

Die Formatgruppe besteht anschließend nach 495,494 Sekunden. Während Clippy
unterschreitet die freie NAS-Swap-Reserve am 12. Oktober um 05:18:45,478 UTC
die unveränderte Grenze: `SwapFree=2347948 KiB < 2359296 KiB` bei weiterhin
`MemAvailable=765220 KiB > 131072 KiB`. Die VM-Sicherung beendet das Ziel
regulär bis 05:19:25,947 UTC, QEMU-Exitcode null, `forced=false`, äußerer
Docker-OOM-Status falsch. Die frühere Jenkins-Referenz wurde bei derselben
Swap-Grenze zwangsweise beendet. Keiner der Zielstände wird für eine
nachträglich künstlich erzeugte Abschlussquittung erneut gestartet.

Leroys Qualitäts- und Elternlauf enden tatsächlich `cancelled`; beide nennen
`Controller lease could not be renewed (last failure: ReadTimeout)`. Das
Originalqualitätsprotokoll enthält den Verlust der SSH-Verbindung zum Ziel,
die anschließende Identitätsprüfung kann keine neue Verbindung aufbauen.
Die lesend gesicherten Controller-Antwortzeitstempel zeigen letzte erfolgreiche
Heartbeats um 05:17:26,518 UTC beim Qualitätskind und 05:17:29,927 UTC beim
Elternlauf, bereits vor der VM-Sicherung. Das belegt eine vorgelagerte
Antwortlücke; Antwortprotokolle sind weder Request-Startzeitstempel noch
Latenzmessungen. Der VM-Stopp allein ist damit keine belegte Ursache aller
Lease-Probleme. Die Korrektur der Container-Vorbereitung behebt diesen
gesonderten Ausfall im laufenden Betrieb nicht nachweislich.

Die Originalsammlung ist terminal abgeschlossen. Beide originalen Webarchive
belegen vollständige 21 Gruppen und 42 identische grüne Fälle. Die ergänzenden
Komponentenprotokolle unterscheiden sich ausschließlich im oben genannten
Startfortschritts-Test. Bei beiden Engines fehlen das vollständige originale
Qualitätsarchiv, das vollständige Rust-Inventar mit den nachfolgenden Gruppen
und die Release-Gesamtquittung. Die 29 Originalgruppen sind deshalb nicht
vollständig gemeinsam abgenommen. Die Ziel-Nachaufnahmen bleiben tatsächlich
unbeobachtbar; Teilprotokolle werden nicht als CI-Qualitätsarchive ausgegeben.

Die vollständigen Produktionshistorien bestätigen ruhige Jenkins- und
Leroy-Messfenster einschließlich der Wiederherstellungen. Andere NAS-Last
bleibt unbewiesen. Alle tatsächlichen Ursprungsläufe sind terminal, die eigene
VM und der private Test-Jenkins sind aus. Die abschließende Infrastrukturaufnahme
bestätigt unveränderte Konfiguration, Ressourcen, Mounts, Images, PostgreSQL-
Durabilität und sechs Ausführungshilfen innerhalb dieser Leroy-Nachprüfung.
Der verlinkte Supervisor-Image-Unterschied gegenüber Jenkins bleibt ausdrücklich
erhalten. Beide Originaldiskstände und alle früheren Fehlversuche bleiben erhalten.

18 neue reale Desktop-/Mobilansichten der abgeschlossenen Laufhierarchie bestehen
technisch und nach direkter Sichtprüfung jedes Bildes. Der echte JSON-Download
stimmt in Größe und SHA-256; Web-Artefakte und leere Abbruch-Artefaktbereiche
werden korrekt dargestellt. Bildprüfsummen und Sichtprüfungszeit sind im
UI-Bericht festgehalten. Insgesamt sind 359 historische NAS-Ansichten geprüft.
Diese UI-Abnahme und der grüne Webvergleich ersetzen die fehlende vollständige
Qualitäts-/Release-Abnahme nicht.

## 12. Oktober: gleiche Ursprungsläufe nach der Log-Korrektur, Serie n

Eine begrenzte Fehlerprobe stellt blockierende Controller-Diagnoseausgabe mit
identischen echten Jobs nach: zwölf API-Timeouts und Lease-Unterbrechung im
blockierenden Modus, erfolgreicher Job mit allen 21 Logeinträgen und geprüftem
Artefakt im gepufferten Modus. Die Korrektur ist im eigenen NAS-Stack installiert,
einschließlich neuer Jobcontainer. Sie beweist diese Fehlerklasse; ihre
vollständige Wirksamkeit unter Graphatos ursprünglicher Last bleibt gesondert
zu prüfen. Aufbaufehler und ein später bereinigter Probe-Cleanup-Timeout bleiben
erhalten. Details: [nas-control-logging.md](nas-control-logging.md).

Die anschließende gemeinsame Serie `full-release-nas-20261012-n` verwendet
dieselbe unveränderte flache Basis und je Engine ein frisches Overlay. Gast
6 GiB, Container hart 7 GiB RAM plus 3 GiB Swap, sechs CPUs, SSD-I/O-Limits
128/32 MiB pro Sekunde, freie Seitenmeldung Ordnung vier und das frühe
`memory.high` von 3584 MiB stimmen überein. NAS-Schutzreserven bleiben 128 MiB
freier RAM und 2304 MiB freier Swap. Originalfixture-Limits, Quellen, Tests,
Ratenlimits und ursprüngliche Fristen bleiben unverändert.

Jenkins-Elternlauf #20 mit Web #22 und Qualität #20 endet tatsächlich
`FAILURE / SUCCESS / FAILURE`. Alle 21 Webgruppen mit 42 Fällen bestehen,
einschließlich Soak. Das vollständige Originalarchiv besitzt SHA-256
`2f85be6f6b78501e360de344319cd8f19df4c7c043378c866caf3fecb95fc31c`.
Die gebundenen ergänzenden Qualitätsprotokolle belegen Python 195/195 und
Komponenten 97/98; die Formatgruppe besteht. Bei Clippy folgen API-/Docker-
Exec-Timeouts und ein Swap-Schutzstopp um 08:40:50,507 UTC mit
`SwapFree=2343620 KiB < 2359296 KiB`, `MemAvailable=562552 KiB`. Die VM wird
zwangsweise beendet, QEMU-Exitcode null und äußerer Docker-OOM-Status falsch.
Qualitätsarchiv und Release-Gesamtquittung fehlen; das Ziel wird nicht neu
gestartet, um nachträglich eine Quittung zu erzeugen.

Vor Leroy wird dieser geschlossene Datenträger bytegenau auf HDD archiviert:
19.785.515.008 Bytes, SHA-256
`ff9c58443fd698cd1f58d7eea3308fc77f30838de026bfd67fcc12d7c27a9b8b`.
Kopie, Prüfsumme, Rechte, Eigentümer, Zeitstempel und Fsync sind geprüft, bevor
die einzelne SSD-Ursprungsdatei entfernt wird. Das Archiv ist keine frische
Leroy-Basis; ein sauberer Gast-Dateisystemabschluss wird nicht behauptet.

Leroy-Elternlauf `8379bdf2005a4ae8b01b7997c738b1f8` startet um 08:56:20,889 UTC.
Web `7fdc491e59804a2da73a32a08eda7c1a` endet `failed`, Qualität
`b6d8a530fc3342839dad9345bbb1e114` und Elternlauf enden `interrupted` mit
`Runner lease expired; external effects require reconciliation`. Das vollständige
originale Webarchiv belegt alle 42 ausgeführten Fälle, 41 bestanden und einen
Fehler, SHA-256
`c94c6935fc6c4e54fa05bb32be5be31efe055cd6119bfddcc1e8d9397ace0bbd`.
Python 195/195, dieselben Komponenten 97/98 und die Formatgruppe bestehen.
Der gemeinsame Komponentenfehler ist weiterhin die Chat-Präsentations-
Zuordnung. Während Clippy werden beide Health-Abfragen und die Docker-Exec-
Datenbankprobe erneut zeitweise unerreichbar. Der Swap-Schutzstopp folgt um
10:06:14,394 UTC mit `SwapFree=2308824 KiB < 2359296 KiB` und
`MemAvailable=841268 KiB`. Auch diese VM wird zwangsweise beendet; äußerer OOM
ist falsch, QEMU-Exitcode null. Qualitätsarchiv und Gesamtquittung fehlen.

Die neue Browserabweichung ist allein `dev-environments`: Nach dem geprüften
Serverneustart findet die unveränderte Sichtbarkeitsprüfung den Expand/Collapse-
Button nicht innerhalb von fünf Sekunden. Jenkins besteht den Fall. Beide
Originalabläufe enthalten die absichtlich ausgelösten 503-Leseprobleme und
502-Antworten während des Neustarts; Jenkins zeichnet vier, Leroy drei dieser
502-Antworten auf. Dies beweist keine Ursache des unterschiedlichen Ergebnisses.
Die vorhandenen Ablaufdaten beobachten den Kollaborator; Fehlertext und
Aufnahmen identifizieren die fehlschlagende Client-Ansicht nicht eindeutig.
Hauptseite und Kollaborator sind aufgenommen, eine Besitzer-Aufnahme fehlt.
Alle gesicherten Leroy-Diagnosen stimmen bytegenau mit dem ursprünglichen
CI-Archiv überein. Kein Fall wurde für diese Untersuchung wiederholt oder
geändert. Die Ursache bleibt offen.

Die Hostdruckmessungen zeigen bei beiden Lastspitzen starken Speicher-/I/O-
Stau. Die Controller-/PostgreSQL-/Runner-Codepfade lesen weiterhin vom HDD-Pool,
obwohl ihre Datenverzeichnisse auf SSD liegen. Erneut geladene Dateiseiten sind
in den Cgroup-Zählern festgehalten; die vorhandenen Speicherreservierungen
bleiben aktiv. SQL-Stichproben über Docker-Exec enthalten Start-/Transportkosten
und werden nicht als reine SQL-Latenz ausgegeben. Direkte API-Timeouts beginnen
vor den Schutzstopps. Erfolgreiche Leroy-Heartbeat-Antwortprotokolle enden um
10:03:11,142 UTC für den Elternlauf und 10:03:12,261 UTC für Qualität; diese
Zeitstempel sind weder Request-Anfänge noch vollständige Latenzspuren. Gepufferte
Diagnoselogs können bei vollem Puffer verloren gehen. Ein exklusiver Ursache-
Nachweis für alle historischen Lease-Ausfälle wird nicht behauptet.

Die Topologieaufnahme bestätigt außerdem: Der produktive Jenkins-Controller
hat keine konfigurierten Docker-RAM-/CPU-Limits und führt die ursprüngliche
Postdeploy-Qualität per SSH auf einem externen Linux-Ziel aus. Test-Jenkins
besitzt 2 GiB RAM, 4 GiB RAM plus Swap und zwei CPUs; das zusätzliche Linux-Ziel
läuft als VM auf dem NAS. Die Hardware des Produktionsziels wurde nicht
abgefragt. Der Aufbau belegt keine Produktions-Performanceparität.

Die abschließende Infrastrukturaufnahme stimmt vollständig mit der Aufnahme
vor beiden Engines überein: Images, Konfiguration, Mounts, Ressourcen,
Diagnosezustellung, PostgreSQL-Durabilität und sechs Ausführungshilfen.
Beide verwenden den Supervisor `620623…`; der frühere verlinkte Image-Unterschied
aus `l/m` gilt für dieses neue Paar nicht. Alle Original-CI-Läufe sind terminal,
VM und privater Test-Jenkins aus, kein Worker dieses Vergleichs läuft weiter.
Vollständige produktive Jenkins-Historien bestätigen ruhige Messfenster,
einschließlich Wiederherstellung und Jenkins-Archivierung. Andere NAS-Hintergrundlast
ist nicht als identisch belegt. Der gestoppte Leroy-Datenträger bleibt erhalten.

18 neue reale Desktop-/Mobilansichten bestehen technisch und nach direkter
Sichtprüfung jedes Bildes; Endzustände, Logs, Laufhierarchie, Parameter,
Artefakte und leere Unterbrechungsbereiche sind korrekt dargestellt. Der echte
JSON-Download ist in Größe und SHA-256 geprüft; Bildprüfsummen und Sichtprüfungszeit
stehen im Bericht. Insgesamt sind 377 historische NAS-Ansichten geprüft.
Dies ersetzt weder die fehlenden ursprünglichen Qualitätsinventare noch die
offene Browserabweichung. Die vollständige Produktionsfreigabe bleibt offen.

Rohbelege: `test-results/nas-parity/followup/full-release-nas-20261012-n/`,
UI: `test-results/nas-parity/full-release-nas-20261012-n-terminal-labels-ui/report.json`.

## Ergänzende Untersuchung nach Serie n

Die folgenden Einzelgruppen ersetzen den unvollständigen ursprünglichen
Gesamtlauf nicht. Quellen und Tests bleiben auf demselben eingefrorenen Commit.

Am Abend des 12. Oktober ist die gemeinsame Speicherreservierung der eigenen
Steuerdienste in einer obersten Cgroup installiert. Ein tatsächlicher
PostgreSQL-Namensauflösungsfehler wird separat durch eine begrenzte DNS-Probe
qualifiziert und durch reservierte eigene DB-Adresse und Controller-Hosteintrag
abgesichert. Beide Änderungen gelten nur für den isolierten Leroy-NAS-Stack.

Die einzelne originale Browsergruppe `dev-environments` scheitert nun auch
unter privatem Jenkins #23 an derselben Fünf-Sekunden-Assertion. Leroy #158 und
privater Jenkins #24 bestehen anschließend denselben unveränderten einzelnen
Fall auf frischen Basen mit gleicher Infrastruktur und Beobachterquelle.
Originalarchive, Quellenbindung und vollständiger Fixture-Cleanup sind geprüft.
Ein ausschließlich an Leroy gebundener Fehler ist damit nicht belegt. Die
historische Ursache bleibt offen; die ergänzenden passiven Spuren sind wegen
Verlusten und Neustart-/Cleanup-Lücken unvollständig.

Der ursprüngliche Postdeploy-Builder besitzt tatsächlich 6 GiB ohne Swap.
Der bisherige Gast stellt insgesamt nur etwa 5,8 GiB nutzbares RAM bereit.
Die getrennte 10-GiB-Gastkonfiguration behebt diese erklärte Größenabweichung,
erhöht aber die Belastung des physischen NAS. Zwei echte einzelne Clippy-
Versuche überschreiten mit unveränderten Schutzgrenzen erst die RAM-, dann
die Swap-Reserve. Leroy #160 verliert zusätzlich die Lease. Sein originaler
Qualitätsnachweis fehlt; die Fehlerklasse der letzten Erneuerung ist nicht
erhalten. Gesunde externe API-Stichproben ersetzen die fehlende Beobachtung
des Workerpfads nicht.

Alle diese Läufe sind terminal, die Test-VM und der private Jenkins aus,
keine eigenen Jobworker aktiv. Die vollständigen produktiven Jenkins-Historien
bestätigen ruhige Messfenster. 18 zusätzliche Desktop-/Mobilansichten sind
technisch und direkt visuell geprüft; die historische Gesamtzahl ist 395.
Weitere Details und Einzelbelege stehen in
[nas-control-memory.md](nas-control-memory.md). Ein begrenztes zusätzliches
Ressourcenfenster ist in [nas-resource-window.md](nas-resource-window.md)
vorbereitet, nicht ausgeführt. Die vollständige ursprüngliche Release-Abnahme
und die Produktionsfreigabe bleiben offen.

## Begrenztes Ressourcenfenster am 13. Oktober

Innerhalb der ausdrücklich freigegebenen festen Zweistundenfrist werden sieben
NAS-Anwendungen pausiert; der produktive Jenkins bleibt unverändert. Der erste
Leroy-Einzelversuch unterschreitet mit 4 GiB bevorzugtem QEMU-RAM weiterhin
die RAM-Reserve und wird mit unvollständigem Clippy-Nachweis beendet. Die sieben
identischen Container werden gesund wiederhergestellt. Die Folgeprobe verschiebt
512 MiB bevorzugtes QEMU-RAM zu möglichem Swap, ohne Quellen, Tests,
Original-Buildergrenzen, harte VM-Grenzen oder NAS-Schutzreserven zu ändern.
Sie erhält keine neue Zweistundenfrist.

Leroy #162 besteht damit die einzelne Originalgruppe `server-clippy` vollständig.
Originalarchiv SHA-256
`5b07c539277f6bbc8bd2f380e66c1e795fd5507f338153b120eb792ec45bc208`;
vollständiger Cleanup, kein Abbruch, kein wiederverwendeter Erfolg, gleiche
eingefrorene Release-Identität. Alle vier Basisdienste bleiben gesund, ohne
Neustart. Die erfolgreiche Lease enthält eine vorübergehende Protokolllücke;
Zusatzdiagnosen haben SSH-/Docker-Start-/Transportlücken. Eine lückenlose
Verfügbarkeit oder Produktions-Performanceparität wird nicht behauptet.

Der passende private Jenkins-Lauf #21 besteht ebenfalls die Originalgruppe,
mit vollständigem Cleanup und gleicher eingefrorener Identität. Originalarchiv
SHA-256 `fb8f691f9e45c37f532d9e29ba3bb987239ba48fad5457f6a0cf617f2725feb4`.
Alle fünf aufgelösten Build-Basis-Image-Digests, VM-Profil, Steuerinfrastruktur und
sechs Ausführungshilfen stimmen überein; beide Basisanwendungen bleiben gesund.

Während der Jenkins-Gegenprüfung beendet allerdings der Kernel den eigenen
256-MiB-Controller wegen eines Cgroup-OOM. Er startet automatisch neu; eine
Messprobe enthält zwei äußere `ConnectError`-Ergebnisse. Die interne SQL-Probe
allein schloss den API-Prozessausfall nicht aus. Die zusätzliche Diagnose
startete einen zweiten Python-/SQLAlchemy-Prozess im Controllerbudget. Künftig
läuft ihre SQL-Probe im eigenen PostgreSQL-Container, der echte Controller-DB-
Pfad bleibt über Bereitschaft geprüft. Nach getrennter Grundqualifikation ist
das laufende Controllerlimit auf 512 MiB ohne Swap erhöht, mit geschützter
Sicherung und ohne Neuerstellung oder weiteren Neustart. Zehn parallele
authentifizierte Metadaten-Abfragesequenzen bestehen; eine vollständige originale
Lastabnahme nach dieser Korrektur steht noch aus.

Die sieben unveränderten NAS-Container laufen um 02:07 Uhr wieder, vor 02:10 Uhr
gesund und stabil geprüft, innerhalb der ursprünglichen Endzeit 02:20 Uhr.
Alle CI-Läufe sind terminal, Test-VM und privater Jenkins aus. 88 gezielte Tests
bestehen; native Jenkins-Historien sind ruhig. Zwölf neue technische und
direkt visuell geprüfte Leroy-Ansichten bestätigen die echten Fehler- und
Erfolgsergebnisse, insgesamt 407 historische NAS-Ansichten. Details und
jeweiliger Betriebszustand stehen in [nas-resource-window.md](nas-resource-window.md).
Die ursprünglichen vollständigen Release-Läufe der Serie n bleiben unvollständig;
ein einzelner erfolgreicher Check ersetzt deren Qualitätsinventare und
Gesamtquittungen nicht.

### Neuer Vergleich mit korrigiertem Controller, 13. Oktober

Der Nutzer hat zwei getrennte Wartungsfenster von jeweils höchstens vier
Stunden zum Pausieren der sieben geprüften NAS-Dienste freigegeben; nach jedem
Fenster werden dieselben Dienste wiederhergestellt. Das erste Fenster beginnt
am 13. Oktober um 22:03:19 Uhr Berliner Zeit. Seine absolute Endzeit ist der
14. Oktober um 02:03:19 Uhr; der unabhängige NAS-Wächter beginnt spätestens
15 Minuten vorher mit der Wiederherstellung. Der vollständige ursprüngliche
Leroy-Releasejob startet um 22:09:29 Uhr, auf dem unveränderten eingefrorenen
Commit und einer frischen Zielbasis im Profil `nas-10g-ssd-soft-ram-3584`.

Der laufende Browserjob enthält einen frühen Fehler vor Ausführung der
`browser-core`-Fälle: Der BuildKit-Abruf aus Docker Hub scheitert mit einem
TLS-Handshake-Timeout. Eine spätere schreibgeschützte Registry-Probe ist
erfolgreich. Der Fehler bleibt erhalten und wird nicht durch einen neu
gestarteten Check ersetzt. Andere ursprüngliche Browsergruppen, einschließlich
`browser-dev-environments`, bestehen. Zwei Graphato-Basisdienste verlieren
nach zunächst gesunder Zielvorbereitung ihre gesunden Zustände; der Server
meldet ungeklärte persistente Runtime-Besitzerschaft nach einem unsauberen
Worker-Ende. Die erhaltenen begrenzten Gast-Kernelproben zeigen keinen OOM;
das belegt noch keine vollständige Ursache. Quellen, Tests, Runtime-Sperren
und Originalfristen werden während des laufenden Vergleichs nicht verändert.

Eine Zwischenaufnahme des Leroy-Controllers um 22:36 Uhr zeigt denselben
Prozess und Container wie vor dem Fenster, rund 129 MiB RAM bei 512 MiB Limit,
kein Swap und keine Cgroup-OOM-Ereignisse. Das ist ein Zwischenbefund unter
Browserlast; die Qualitätslast und der vollständige Jenkins-Vergleich stehen
noch aus. 129 gezielte lokale Tests bestehen. Vorbereitung, erfolgreiche
Einzelgruppen und Zwischenmessungen sind keine Produktionsfreigabe.

Die laufenden Originalbelege stehen unter
`test-results/nas-parity/followup/full-release-controller512-20261013/`;
Wartung und zusätzliche Beobachtungen unter
`test-results/nas-parity/followup/resource-window-full-leroy-20261013/`.

Das erste Fenster ist inzwischen abgeschlossen: Alle sieben ursprünglichen
Dienste werden um etwa 23:35 Uhr wieder gestartet und vor 23:38 Uhr gesund
und stabil geprüft. Es dauert 91,75 Minuten. Vollständige native Jenkins-
Historien und unveränderte Jobstände qualifizieren das ruhige Fenster;
die Live-Queue bleibt gesondert ungeprüft. Der Controller behält Container,
Prozess und Konfiguration, ohne neuen Neustart oder Cgroup-OOM.

Der Original-Browserjob führt alle 21 Gruppenaufrufe aus: 20 bestehen, auch
Soak und Entwicklungsumgebungen. Die Core-Gruppe scheitert vor ihren
ursprünglichen Fällen am BuildKit-Abruf; damit sind die 42 ursprünglichen
Browserfälle insgesamt nicht vollständig ausgeführt. Das unveränderte
Originalarchiv, seine Prüfsumme und die vollständige Bereinigungsquittung
sind erhalten. In der Qualitäts-Abnahme besteht die Formatprüfung und
anschließend **Clippy innerhalb des vollständigen Originaljobs**. Die
Frontend-Komponentenprüfung endet erneut mit 97/98 bestandenen Tests und
dem Fehler bei der Zuordnung präsentierter Ergebnisse zum Chatverlauf.

Während der Rust-Testphase unterschreitet der NAS-Swap die unveränderte
Reserve: 2.339.984 KiB frei bei mindestens 2.359.296 KiB. Der eigene
Gastwächter leitet die Abschaltung ein. Diese erreicht ihre Frist nicht;
QEMU wird zwangsweise beendet. `forced: true` bleibt ausdrücklich erhalten,
auch wenn Docker `OOMKilled: false` und QEMU Exitcode 0 meldet. Der Gast
wird nicht als sauber abgeschaltet oder als wiederverwendbare Zielbasis
bewertet. Alle drei ursprünglichen CI-Läufe enden fehlgeschlagen. Das
Qualitätsarchiv, die verbleibenden Gruppen und die abschließende Release-
Quittung fehlen. Der Versuch ist keine vollständige Release-Abnahme.

233 äußere Gesundheitsmesspunkte sind erfolgreich; 21 zusätzliche SQL-
Wrapperfehler und 13 Worker-Beobachtungslücken bleiben erhalten. Die
erhaltenen begrenzten Logs enthalten sechs vorübergehende Lease-
Erneuerungsfehler, aber kein Stoppen wegen Lease-Verlusts. Diese Proben
werden nicht als verlustlose oder lückenlose Verfügbarkeitsmessung bewertet.
22 weitere Ansichtsprüfungen bestehen technisch und durch direkte
Sichtprüfung, einschließlich echter Fehlerzustände, Artefakt-Prüfsummen,
beider Kindlauf-Verknüpfungen und mobiler Zeitachsen. Insgesamt sind damit
429 historische NAS-Ansichtsprüfungen dokumentiert. Die UI wird nicht geändert.

Nach Wiederherstellung werden die ausgeschalteten Zielplatten des neuen
Versuchs und der früheren Serie `n` mit Byte-, Besitz- und Prüfsummenprüfung
archiviert. Dies erzeugt keine zusätzliche Archivierungslast während eines
laufenden Originaltests. Das getrennt freigegebene Jenkins-Fenster steht
noch aus und startet von derselben ursprünglichen sauberen Basis; es
übernimmt keine Daten oder bestandenen Checks dieses abgebrochenen Gasts.

Das zweite Fenster startet um 23:55:44 Uhr am 13. Oktober, mit absoluter
Endzeit 03:55:44 Uhr am 14. Oktober. Der private Jenkins führt den
ursprünglichen Releasejob #21 mit Browserjob #25 und Qualitätsjob #22 aus.
Das Original-Browserarchiv ist inzwischen geprüft: **21/21 Gruppen und
42/42 ursprüngliche Fälle bestehen**, ohne wiederverwendete Checks und mit
vollständiger Bereinigung. Release-Commit, Runtime-Image, Quellenprüfsumme
und Build-Zeitstempel stimmen mit Leroy überein. Sein Archiv hat SHA-256
`b662542601b54635da12b0c2b342e84de198bf0291e3f11db69bf6c891e09078`.
Damit reproduziert sich der frühe Leroy-Core-Bootstrapfehler unter Jenkins
nicht; die fehlenden Core-Fälle des Leroy-Versuchs bleiben fehlend.

Der Frontendfehler reproduziert sich unter Jenkins: ebenfalls 97/98
Komponententests, mit demselben Test zur Zuordnung präsentierter Ergebnisse
zum Chatverlauf. Beide direkt gelesenen Original-Gastlogs sind mit
Prüfsummen gebunden. Diese zusätzlichen Logproben ersetzen weiterhin keine
vollständige Original-Qualitätsquittung. Beleg:
`full-release-controller512-20261013/paired-frontend-failure-proof.json`.

Die vier Graphato-Basisdienste bleiben während der Jenkins-Browserphase
gesund. Nach dem folgenden Runtime-Build verlieren jedoch auch hier
Maintenance und Server ihren gesunden Zustand. Der Server zeigt dieselben
Meldungen zu ungeklärter persistenter Runtime-Besitzerschaft nach einem
unsauberen Worker-Ende; der Maintenance-Exitcode ist 137. Der Gastzähler
meldet zu diesem Zeitpunkt keinen Kernel-OOM-Kill. Das Verhalten wird
somit in beiden Testumgebungen beobachtet; die vollständige Ursache und
ein exklusiver Zusammenhang mit der CI-Engine werden daraus nicht abgeleitet.

Die Formatgruppe ist inzwischen bestanden, Clippy noch in Bearbeitung.
Die tatsächlich erfassten Prüfcontainer verwenden bei beiden Engines
6 GiB ohne Swap und zwei CPU-Kerne. Der BuildKit-Digest stimmt überein,
die während der ursprünglichen Builds erzeugten Verifikations-Image-IDs
unterscheiden sich. Deren vollständige inhaltliche Identität ist bislang
nicht nachgewiesen; Release-Runtime, Quellen und Ressourcen bleiben separat
gebunden. Diese Einschränkung wird nicht durch die gleichen Dockerfile-
Versionsangaben oder die früheren Clippy-Einzelgruppenbelege ersetzt.
Das zweite Fenster und die vollständige Release-Abnahme sind noch offen.

### Abschluss beider freigegebenen Fenster

Stand: 14. Oktober, 01:33 Uhr Berliner Zeit. **Beide Fenster sind beendet,
alle sieben ursprünglichen Dienste wieder gesund und stabil. Die vollständige
Release-Abnahme ist nicht bestanden.** Das Jenkins-Fenster dauert 94,12 Minuten;
die Wiederherstellung ist um etwa 01:30 Uhr abgeschlossen, die stabile
Gesundheitsprüfung vor 01:33 Uhr. Beide absoluten Vierstundenfristen sind
eingehalten. Beide unabhängigen Wächter sind beendet; Ziel-VM, privater
Jenkins und eigene CI-Worker sind aus. Eine abschließende Aufnahme prüft
erneut dieselben Container-IDs, Images und Konfigurationsprüfsummen sowie
ruhige vollständige native Jenkins-Historien.

Jenkins besteht nach der Formatprüfung ebenfalls Clippy innerhalb des
vollständigen ursprünglichen Releasejobs. Während seiner Rust-Testphase
unterschreitet der NAS-Swap dieselbe Reserve: 2.328.540 KiB frei bei mindestens
2.359.296 KiB. Die Gastabschaltung erreicht ihre Frist nicht; auch hier
bleibt die QEMU-Beendigung ausdrücklich `forced: true`. Der Browserjob #25
endet erfolgreich, Qualitätsjob #22 und Releasejob #21 fehlgeschlagen.
Die vollständigen Qualitätsarchive, nachfolgenden Gruppen, abschließenden
Release-Quittungen und nachträglichen Zielzustände sind in diesem Paar nicht
belegt. Weder Teilquittungen noch die gleichen Gesamtstatus ersetzen sie.

| Befund | Leroy | Privater Jenkins |
| --- | --- | --- |
| Originale Browsergruppen | 20/21 bestanden | 21/21 bestanden |
| Vollständige ursprüngliche Browserfälle | 21 Core-Fälle nicht ausgeführt | 42/42 bestanden |
| Frontend-Komponenten | 97/98, derselbe fehlgeschlagene Test | 97/98, derselbe fehlgeschlagene Test |
| Format und Clippy im vollständigen Originaljob | bestanden | bestanden |
| Rust und spätere Gruppen | wegen NAS-Swap-Schutzstopp unvollständig | wegen NAS-Swap-Schutzstopp unvollständig |
| Graphato-Basisdienste | Maintenance/Server verlieren gesunden Zustand | derselbe Zustand nach dem Runtime-Build |
| Neuer Controller-Neustart oder Cgroup-OOM | keiner | keiner |
| Gesunde ursprüngliche Dienste vor Fensterfrist | bestätigt | bestätigt |

Die abschließende Controlleraufnahme zeigt weiter denselben Container und
Prozess mit 512 MiB Limit und ohne neue Cgroup-OOM-Ereignisse. Jenkins liefert
244 erfolgreiche äußere Gesundheitsmesspunkte, 11 zusätzliche SQL-
Wrapperfehler und sieben Worker-Beobachtungslücken. Die erhaltenen begrenzten
Jenkins-Fensterproben enthalten keine Lease-Ereignisse; unter Leroy sind sechs
vorübergehende Erneuerungsfehler, aber kein Lease-Stopp erhalten. Einzelne
zusätzliche Jenkins-Logabfragen laufen in SSH-Timeouts. Aus den Proben wird
keine lückenlose Verfügbarkeit oder vollständige Ursachenanalyse abgeleitet.

Der Vergleich ist mit unveränderten Quellen und Tests sowie gleicher
Release-Identität, Steuerungsinfrastruktur, Vergleichssoftware und
Ressourcenkonfiguration abgeschlossen. Die während der ursprünglichen
Builds erzeugten Verifikations-Image-IDs bleiben unterschiedlich und ihre
vollständige inhaltliche Gleichheit ungeprüft. Allgemeine Leistungsgleichheit,
vollständige Release-Abnahme und Produktionsfreigabe werden nicht behauptet.
Es wird kein neuer CI-Lauf ausgelöst und kein Anwendungspatch als bestandene
Voraussetzung für den Jenkins-Wechsel eingeführt.

Abschlussbelege im Vergleichsordner:
`paired-attempt-report.json`, `final-operations-proof.json`,
`jenkins-original-web-proof.json`, `leroy-original-web-proof.json` und
`paired-frontend-failure-proof.json`. Beide Wartungsordner enthalten ihre
eigenen `window-result.json`, `control-summary.json`, Wiederherstellungs-
nachweise und `terminal-outer-vm-proof.json`. Diese Abschlussbelege ersetzen
keinen fehlenden Original-CI-Nachweis.

## Nachanalyse am 14. Oktober

Die [Datenträger-Nachanalyse](nas-release-forensics.md) weist unter beiden
Engines eine interne PostgreSQL-Neuinitialisierung vor Graphatos Lease-Verlust
nach. Der Mechanismus durch verwaiste Kindprozesse wurde mit dem ursprünglichen
PostgreSQL-Image reproduziert und durch einen Init-Prozess im Kontrollfall
verhindert. Leroys eigene Testdatenbank ist entsprechend abgesichert; für eine
neue Graphato-Testbaseline ist die getrennte Konfiguration vorbereitet.
Quellen und Tests bleiben unverändert. Neun geprüfte Dateien und 264 Paketstände
sind gleich; vollständige Image-Gleichheit bleibt ungeprüft. Ein neuer Volllauf
wurde noch nicht gestartet. Eine neue ursprüngliche Frontend-Gruppe mit Init
ist inzwischen vollständig beendet: 96/98 Komponentenfälle, gesunde Basisdienste,
vollständiges Originalarchiv. Direkte Einzelbeobachtung weist ein anschließendes
Fokus-Stehlen durch Graphatos Eingabefeld nach; der zusätzliche Retry-Renderer-
Fehler bleibt separat offen. Vollständige Abnahme und Produktionsfreigabe bleiben
offen. Die bisherigen fehlgeschlagenen Vergleichsnachweise bleiben erhalten.

## Controller-Korrektur und geplante Folgeserie

Die nachfolgende [Rust-Diagnose](nas-rust-memory.md) mit 8-GiB-Gast endet unter
Leroy mit Lease-Verlust und unter dem privaten Jenkins mit derselben NAS-Swap-
Reservegrenze. Alle sieben NAS-Dienste laufen dabei. Sie ersetzt keine Gruppe
der bisherigen vollständigen Vergleichsserie. Ein konkret reproduzierter
Controller-Sperrfehler ist anschließend mit 34 echten PostgreSQL-Tests geprüft
und als einzig geänderte Laufzeitdatei in den eigenen NAS-Controller übernommen.
Produktiver Jenkins, Graphato-Quellen, Tests und Laufzeitfristen bleiben gleich.

Eine neue Serie `full-release-reconcile8g-20261014` ist vorbereitet, aber noch
nicht gestartet. Sie verlangt eine neue Freigabe für zwei getrennte Fenster
mit höchstens vier Stunden. Die alten Fenster werden nicht verlängert oder
wiedereröffnet. Pro Engine muss zuerst eine frische ursprüngliche Rust-Gruppe
vollständig bestehen, einschließlich unverändertem Inventar und Bereinigung.
Ohne vollständigen Nachweis, bei beobachteter Reserveunterschreitung oder
unzureichendem Restbudget startet kein Volllauf. Jede neue Zielbasis wird
frisch vorbereitet. [Wartungsplan und Wiederherstellung](nas-resource-window.md)
gelten für beide Engine-Fenster.

Die ergänzenden vollständigen Inventare der Rust-Prüfimages zeigen gleiche
Ausführungskonfiguration und identische Compiler-, Bibliotheks- und Quelldateien.
Abweichungen bleiben in erzeugten Caches und Logs; die abweichende Git-Konfiguration
enthält dieselben vier Git-LFS-Werte in anderer Reihenfolge. Dies ist kein
Nachweis bytegleicher Images der früheren Vollläufe oder gleicher Leistung.
Die bestätigte Graphato-Fokusübernahme und die zusätzliche Retry-Renderer-
Abweichung bleiben getrennte Anwendungsbefunde. Quellen und Prüfungen werden
nicht angepasst, um einen grünen Vergleich zu erhalten. Produktionsfreigabe
und vollständige Release-Abnahme sind weiterhin nicht belegt.

## Ergebnis der neu genehmigten Gegenprobe am 14. Oktober

Die Serie `full-release-reconcile8g-20261014` ist inzwischen unter beiden
Engines bis zur ursprünglichen Rust-Eingangskontrolle ausgeführt. Beide
Wartungsfenster sind geschlossen; alle sieben Dienste sind jeweils rechtzeitig
wieder gesund. Commit `0ad540dd578033d45e4d0c25d89fbe57b32102a4`, Quellen,
Tests, Fixture-Limits, Controller-/Workerstände und Vergleichskonfiguration
sind innerhalb dieses Paars gebunden.

| Eingangskontrolle | Leroy | Privater Jenkins |
| --- | --- | --- |
| Ursprünglicher Rust-Job | `0d570e8cf25e4dac9cc40f44f54b20eb`, unterbrochen | `graphato-postdeploy-quality#24`, fehlgeschlagen |
| Belegter Abbruch | lokale Lease-Grenze nach zusätzlicher Wartezeit | NAS-Swap-Schutzreserve |
| Neues vollständiges Release gestartet | nein | nein |
| Sieben Dienste wieder gesund, Berliner Zeit | 19:00:38 Uhr | 19:42:49 Uhr |
| Neuer Controller-Neustart oder Cgroup-OOM | keiner | keiner |

Die nachgewiesene Worker-Wartezeit ist erst nach Abschluss beider Fenster
korrigiert, unter Linux geprüft und im eigenen Teststack installiert.
Die unveränderten Lease-Fristen bleiben bestehen. Ein ursprünglicher Rust-
oder vollständiger Releasejob mit dem neuen Worker ist noch nicht belegt.
Die Jenkins-Gegenprobe zeigt außerdem eine eigenständige Ressourcengrenze
der isolierten VM. Ein synthetischer Speichertest oder ein erfolgreicher
produktiver Build eines anderen Commits ersetzt diese eingefrorene Abnahme
nicht. Details: [Rust-Diagnose](nas-rust-memory.md) und
[Wiederherstellungsnachweise](nas-resource-window.md).

## Nachtfortsetzung nach den Kapazitätsproben

Die Kapazitätsproben vom 14.10. erbringen keinen vollständigen 6-GiB-Nachweis.
Das getrennte Nachtverfahren misst deshalb die echten ursprünglichen Rust-Jobs
innerhalb der unveränderten NAS-Abbruchgrenzen. Nur vollständige erfolgreiche
Ergebnisse beider Engines erlauben die vollständigen Release-Läufe. Die neue
Planvariante bindet die abgeschlossenen Teilkapazitätsbelege und verwendeten
Skripte per SHA-256; sie erklärt die Teilbelegung nicht zu einem Maximalnachweis.

Die erste Originalvorbereitung wurde vor jedem CI-Dispatch wegen eines
Fehlers im Abnahmewerkzeug beendet: Die Zielprüfung verlangte noch
Reporting-Order 4 trotz ausdrücklicher Auswahl von 0. Die Prüfung folgt nun
der ausgewählten Konfiguration und lehnt tatsächliche Abweichungen weiter ab.
Die Wächterregistrierung behandelt zusätzlich die flache Fortschrittsstruktur
einzelner Originaljobs. Drei Gegenbeispiele scheitern mit dem alten Code;
292 lokale Tests bestehen nach der Korrektur (43 separate Umgebungsprüfungen
übersprungen). Die Vorbereitungs-VM ist sauber beendet und separat erhalten;
alle sieben Anwendungen sind wieder gesund und stabil. Kein Graphato-Job
wurde bis dahin gestartet oder neu ausgeführt.

Die Fortsetzung ab 22:53 Uhr Berlin erhält das eigene Journal
`resource-window-original-night-20261014-b` und frische Vergleichsnamen
`original-night-b-rust-{leroy,jenkins}-20261014` sowie
`original-night-b-release-20261014`. Die feste Endzeit bleibt 06:00 Uhr Berlin
mit automatischer Wiederherstellung ab 05:45 Uhr. Vollständige Abnahme und
Produktionsfreigabe sind weiterhin offen.

Diese Fortsetzung B ist inzwischen beendet: Leroy wurde nach einer
77-sekündigen Lease-Anfrage unterbrochen, der private Jenkins #25 durch
den NAS-RAM-Schutz gestoppt. Beide Images bauten erfolgreich und begannen
die ursprüngliche Rust-Kompilierung; ein vollständiger Rust-Erfolg liegt
für keinen der beiden Läufe vor. Alle sieben NAS-Anwendungen sind nach
Abschluss gesund und stabil; beide Testlaufwerke sind prüfsummengebunden
archiviert. Es wurde kein vollständiger Release-Lauf ausgelöst.

Die neue Fortsetzung C verwendet `memory.high=3584 MiB` bei unverändertem
8-GiB-Gast, Quellen und Tests. Sie bindet das Linux-geprüfte diagnostische
Jobimage und die nun auch im tatsächlichen Runner installierte Lease-
Erneuerungskorrektur. Frische Namen lauten
`original-night-c-rust-{leroy,jenkins}-20261014` und
`original-night-c-release-20261014`. Nur zwei vollständige, erfolgreiche
Original-Rust-Inventare erlauben die anschließenden vollständigen Releases.
Die Wiederherstellungsfrist bleibt 15.10., 06:00 Uhr Berlin.

C endete durch den NAS-Swap-Schutz, nachdem die ursprüngliche Kompilierung
das Graphato-Paket erreichte. Leroys Lease blieb erhalten; die VM fuhr sauber
herunter, danach fiel die Zielverbindung aus. Ein vollständiger Testabschluss
liegt nicht vor. Jenkins und vollständige Releases wurden in C nicht gestartet.
Alle sieben Anwendungen sind nach dem Fenster gesund und stabil.

D setzt den begrenzten Originalvergleich auf beiden Seiten mit 3840 MiB
`memory.high` und SSD-Speicher für die Docker-Laufzeit fort. Das Worker-Image
ist unverändert und mit 28 Linux-Tests geprüft. Die bisherigen privaten
Jenkins-/Gitea-Dateisysteme und Daten bleiben erhalten; das neue Rootfs-
Snapshot-Image enthält ihren bisherigen Stand. Quellen und Tests von Graphato
bleiben unverändert. Frische Fälle heißen
`original-night-d-rust-{leroy,jenkins}-20261014` sowie
`original-night-d-release-20261014`. Der vollständige Release-Vergleich bleibt
an zwei erfolgreiche Original-Rust-Inventare und die feste Endzeit gebunden.

D wurde vor jedem CI-Start wegen einer alten Jenkins-ID im Abnahmewerkzeug
beendet und mit sieben gesunden Diensten abgeschlossen. Die Identitätsprüfung
ist jetzt an den geprüften SSD-Pool gebunden und prüft auch Image und Daten-
Volume, bevor eine neue Ziel-VM angelegt wird.

Die Fortsetzung E führt direkt die vollständigen Original-Release-Pipelines
aus, einschließlich aller darin enthaltenen Rust-Prüfungen. Sie verzichtet auf
zusätzliche eigenständige Wiederholungen dieser Prüfungen vor der eigentlichen
Abnahme. Kein ursprünglicher Test, Quellstand, Rate Limit oder Fixture-Grenzwert
wird geändert oder ausgelassen. Beide Engines erhalten dieselbe frische
Baseline und das 3840-MiB-Profil. Der neue Fall heißt
`original-night-e-release-20261014`; die absolute Wiederherstellungsfrist bleibt
06:00 Uhr Berlin. Erfolgreiche Vollständigkeit ist erst aus den tatsächlichen
Originalinventaren und Abschlussbelegen beider Engines abzuleiten.
