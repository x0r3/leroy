# Speicherreservierung der NAS-Steuerdienste

Am 12. Oktober 2026 wurde eine weitere Korrektur **nur im isolierten NAS-Stack**
installiert. Sie ist keine Produktionsfreigabe und keine Änderung an Graphato.

Die bisherigen Reservierungen lagen unter `system.slice`. Dort waren sowohl
`memory.low` als auch `memory.min` null. Die Schutzgrenzen eines Kindes werden
durch seine Vorfahren begrenzt; die drei vorhandenen Reservierungen konnten
damit keinen wirksamen Schutz gegen globale Rückgewinnung gewährleisten.
Siehe [Linux-Cgroup-Dokumentation](https://docs.kernel.org/admin-guide/cgroup-v2.html#memory).

`deploy_nas_control_memory_group.py` legt eine eigene oberste Systemd-Gruppe
`leroyparity.slice` an. Nur PostgreSQL, Controller und Runner werden dieser
Gruppe zugeordnet. Ihre Reservierungen bleiben 128, 128 und 64 MiB; der
gemeinsame Vorfahr erhält entsprechend 320 MiB `MemoryLow`. `MemoryMin` bleibt
null. Dies ist bevorzugte Rückgewinnung, keine harte RAM-Zuteilung. NAS-Docker,
produktive Dienste, Ziel-VM und verschachtelter Docker-Daemon werden nicht
umgeordnet. Der NAS verwendet Cgroup v2 und den Systemd-Treiber.

Vorher wurden das Compose-Override, die ursprünglichen Containerinformationen
und ein synchronisierter PostgreSQL-Dump geschützt gesichert. Anschließend sind
Images, Umgebungswerte, Befehle, Mounts, Containerlimits und Durabilität geprüft.
Die Compose-Prüfsumme und automatisch erzeugte Docker-Metadaten ändern sich
beim Neuerstellen; Bind-Mounts und Umgebungswerte werden nach Inhalt verglichen.
Die ursprünglichen Abbrüche der zu strengen Metadatenprüfung bleiben erhalten.
Der explizite Wiederanlauf stellte denselben begonnenen Rollout fertig und
startete keine CI-Pipeline erneut. Die abschließende Hierarchieprüfung bestätigt
die drei Reservierungen und den gemeinsamen Vorfahren.

Die Sicherung liegt auf dem NAS unter
`/volume1/docker/leroy-nas-parity/control-memory-group-20261012`.
Für einen Rückbau müssen bei ruhendem eigenen CI-Stack das gesicherte
`compose.override.yaml.before` wiederhergestellt und ausschließlich die drei
Steuercontainer neu erstellt werden. Danach kann die unbenutzte, eindeutig
markierte `/etc/systemd/system/leroyparity.slice` entfernt werden. Die
Produktionsdienste und globalen Schutzgrenzen sind dabei unverändert zu lassen.
Die Sicherungen werden behalten.

## Abgeschlossene Clippy-Nachprüfung

`control-stability-clippy-20261012` führt die **ursprüngliche** Qualitätsgruppe
`server-clippy` durch die bestehende Leroy-Pipeline aus. Die VM verwendet eine
frische Kopie der eingefrorenen Basis, sechs GiB Gast-RAM und die unveränderten
Fixture-Limits und Schutzreserven des Profils `nas-6g-ssd-soft-ram-3584`.
Die Anwendung bleibt auf `0ad540dd578033d45e4d0c25d89fbe57b32102a4`.
Quellen, Tests, 45-/90-Sekunden-Leases und Zeitlimits werden nicht geändert.

Der ursprüngliche Leroy-Lauf `418fb86f4535435d926f4b76e9a730d3` (Nummer 157)
endet als **fehlgeschlagen**, nicht als Lease-Abbruch. Die Swap-Schutzreserve
stoppt den Zielgast bei 2.357.400 KiB freiem Swap gegenüber der unveränderten
Grenze 2.359.296 KiB. 778.320 KiB RAM sind noch verfügbar. Der Gast fährt
regulär herunter (`forced: false`, QEMU-Code null). Das ursprüngliche
Clippy-Inventar ist nicht vollständig; das CI liefert nur seine 189 Byte große
Abbruchquittung. Das ist keine bestandene Anwendungsprüfung.

52 gespeicherte Messpunkte enthalten keinen Gesundheits-API-Timeout. Elf
SQL-Wrapper-Abfragen scheitern; die erhaltenen direkten SQL-Messungen haben
keinen Fehler. Die Beobachtung wurde nach einer HTTP-500-Antwort der
Anmeldungsprüfung unterbrochen und mit derselben CI-ID fortgesetzt. Ein
zusätzlicher Versuch, beim Wiederaufnehmen Giteas Gesundheit zu lesen,
überschritt die Docker-Exec-Frist; die bereits gestartete CI brauchte diese
erneute Vorprüfung nicht. Die Messpunkte beweisen daher keine lückenlose
Verfügbarkeit. Die vollständigen produktiven Jenkins-Historien bestätigen
ein ruhiges Messfenster.

Parallel werden echte HTTP-Abfragen und eine lesende SQL-Probe beobachtet.
Die SQL-Zeit innerhalb des Containers umfasst den Verbindungsaufbau; die
SSH-/Docker-Exec-Zeit wird separat gespeichert. Ein Wrapper-Timeout beweist
keinen SQL-Timeout. Diese Messung hat eigenen Ressourcenverbrauch. Ein ruhiger
produktiver Jenkins schließt andere NAS-Hintergrundlast nicht aus.

Eine einzelne Qualitätsgruppe ersetzt weder die vollständigen acht Gruppen
noch die Release-Quittung. Insbesondere fehlt ihr die Vorgeschichte der
vorangehenden Frontend- und Browserlast des vollständigen Releases.

## Nachgewiesener DNS-Fehler und Korrektur

Die geschützte, begrenzte Analyse des echten Controllerlogs findet
`failed to resolve host` und `Temporary failure in name resolution` als Ursache
des Psycopg-/SQLAlchemy-Verbindungsfehlers. Sie speichert keine Rohlogs oder
Zugangsdaten. Keine OOM-Beendigung der drei Steuerdienste wurde festgestellt.

Die separate Probe `control-dns-20261012` verwendet zweimal das tatsächliche
Controllerimage und dieselbe lesende Datenbankabfrage. Nur der Resolver dieser
Probecontainer wird auf einen nicht vorhandenen lokalen DNS-Dienst gesetzt.
Ohne Hosteintrag scheitert die Verbindung als `OperationalError`; mit
`postgres:10.232.98.2` besteht sie. Die Datenbank-URL und der Hostname `postgres`
bleiben identisch. Beide Probecontainer sind entfernt; NAS-DNS wurde nicht
geändert. Dies belegt den Fehlermechanismus und die Wirkung des Hosteintrags,
keine vollständige Erklärung aller historischen Controller-Aussetzer.

`deploy_nas_control_dns.py` reserviert die bereits vorhandene PostgreSQL-Adresse
im ausschließlich eigenen Docker-Netz und ergänzt den entsprechenden
Hosteintrag im eigenen Controller. Die erfolgreiche Abschlussprüfung bestätigt
unveränderte Images, Umgebungswerte, Befehle, Mounts, Limits, Speichergruppen
und Lease-Fristen. Vorher sind Konfiguration und PostgreSQL-Dump gesichert.
Die Sicherung liegt in `control-dns-deployment-20261012` unter dem eigenen
NAS-Testverzeichnis. Die erste Validierung beanstandete ausschließlich Composes
Listenrepräsentation des Hosteintrags vor dem Neustart; die explizite Fortsetzung
prüfte dieselben ursprünglichen Container und stellte diesen Rollout fertig.
Eine Produktionskonfiguration wurde nicht aktiviert.

## Originaler Ressourcenvertrag des Postdeploy-Builders

Eine echte Aufnahme im frischen Jenkins-Gegenlauf zeigt
`buildx_buildkit_graphato-postdeploy0` mit **6 GiB RAM und 6 GiB MemorySwap**,
also ohne zusätzlichen Swap. Dies entspricht `BUILDER_OPTIONS` des eingefrorenen
`deployments/linux/host/postdeploy.py`. Der separate NAS-Build aus `scripts/ci.py`
hat andere Vorgaben (4 GiB plus 2 GiB Swap); diese beiden Builder dürfen nicht
gleichgesetzt werden.

Der bisherige 6-GiB-Gast meldet nur 6.060.404 KiB nutzbaren RAM und keinen Swap.
Damit liegt schon die originale Builder-Grenze über seinem gesamten nutzbaren
Speicher; zusätzlich laufen Basisserver, PostgreSQL, Worker und Betriebssystem.
Das beweist eine unzureichende Dimensionierung für den deklarierten maximalen
Bedarf, nicht den alleinigen Grund sämtlicher historischer Abbrüche. Die Aufnahme
zu Beginn der Builderphase findet keinen Gast-OOM. Später sind Basisserver und
Wartungscontainer bei den Browserproben ungesund; ihre genaue Ursache ist noch
nicht nachgewiesen. Erfolgreiche isolierte Browser-Fixtures ersetzen keine
Gesundheitsprüfung der Basisanwendung.

Das neue, ausdrücklich getrennte Testprofil `nas-10g-ssd-soft-ram-4096` gibt dem
Gast 10 GiB. Die äußeren QEMU-Grenzen sind 11 GiB Speicher und 15 GiB einschließlich
Swap; bevorzugte Rückgewinnung beginnt bei 4 GiB. Virtuelles Gast-RAM ist keine
zusätzliche physische NAS-Kapazität. Der NAS behält seine unveränderten Grenzen
von 128 MiB freiem RAM und 2.304 MiB freiem Swap. Quellen, Tests, originale
Container-/Buildergrenzen, CPU-Zahl und SSD-I/O-Grenzen bleiben gleich. Dieser
gezielte Umgebungswechsel wird zunächst mit der einzelnen originalen Clippy-
Gruppe geprüft; ein Erfolg oder eine Produktionsfreigabe wird nicht vorweggenommen.

Der erste tatsächliche 10-GiB-Lauf `a39bf4e0693a41fcbb80c1fed931d8e2` endet als
fehlgeschlagen, ohne Lease-Abbruch. Diesmal stoppt die RAM-Schutzreserve bei
129.592 KiB verfügbarem RAM gegenüber 131.072 KiB Mindestreserve; Swap hat noch
4.271.352 KiB frei. Der Gast fährt regulär herunter. 44 erhaltene Messpunkte
haben keinen Gesundheits-API-Timeout, sechs SQL-Wrapper-Lücken und keinen
Fehler in den erhaltenen direkten SQL-Abfragen. Clippy ist unvollständig;
die 189-Byte-Abbruchquittung ersetzt sein Originalarchiv nicht. Der Basisserver
war während einer echten Compileraufnahme gesund, ohne Neustart oder Gast-OOM.
Das ist eine begrenzte Beobachtung, keine vollständige Verfügbarkeitsgarantie.

Das getrennte Profil `nas-10g-ssd-soft-ram-3584` behält Gastgröße, harte QEMU-
Grenzen, Original-Builder, CPU und I/O bei und verschiebt nur 512 MiB des
bevorzugten RAM-Budgets zu möglichem Swap. Das folgt der tatsächlich gemessenen
RAM-Unterschreitung bei freiem Swap; die Schutzgrenzen werden nicht gelockert.
Seine einzelne Original-Clippy-Prüfung ist inzwischen ebenfalls beendet.
Der Leroy-Lauf `62f4c829e60c461a9f112a0f89e5a6bd` (Nummer 160) ist
**abgebrochen**, mit `Controller lease could not be renewed`; sein Qualitäts-
Archiv fehlt vollständig. Am 12. Oktober um 21:33:53,737 UTC löst die
unveränderte Swap-Schutzreserve aus: 2.184.148 KiB frei gegenüber 2.359.296 KiB
Mindestreserve, bei 701.676 KiB verfügbarem RAM. Die VM endet um 21:35:07,136 UTC
mit `forced: true`, QEMU-Code null und ohne äußeren OOM. Der Abbruch des
Prüfschritts wird um 21:35:06,437 UTC gespeichert.

57 erhaltene Gesundheitsmesspunkte haben keinen API-Timeout; 21 zusätzliche
Docker-Exec-/SSH-SQL-Proben haben Wrapperfehler. Die erhaltenen direkten
SQL-Abfragen haben keinen Fehler. Die externe Bereitschaftsprüfung verwendet
ebenfalls PostgreSQL, beweist aber nicht die Erreichbarkeit vom tatsächlichen
Jobworker. Dessen Container war vor der abschließenden Logabfrage bereits
entfernt; die genaue letzte Lease-Fehlerklasse ist nicht erhalten. Die zeitliche
Nähe zum VM-Schutzstopp ist kein exklusiver Ursachennachweis. Damit ist die
Controller-/Worker-Stabilität unter dieser Gesamtlast weiterhin nicht belegt.

Die Infrastruktur vor und nach diesem Lauf stimmt abgesehen vom Aufnahmezeitpunkt
überein, einschließlich sechs Ausführungshilfen. VM, privater Jenkins und alle
Leroy-Jobworker sind aus; vollständige produktive Jenkins-Historien sind ruhig.
Die anschließende Leerlaufprobe besteht fünfmal: Bereitschaft höchstens 13 ms,
direktes `SELECT 1` einschließlich Verbindung höchstens 20 ms, keine Fehler.
Dies ersetzt keine erfolgreich abgeschlossene Original-Clippy-Prüfung.

Für zukünftige Einzelgruppen zeichnet der Diagnosehelfer automatisch die
begrenzten, zeitgestempelten Lease-Meldungen laufender eigener Worker auf,
bevor normale Runner-Bereinigung ihre Container entfernt. Beliebige Joblogs,
Fehlermeldungsinhalte, Umgebungsvariablen und Zugangsdaten werden nicht
gespeichert. Transportlücken bleiben ausdrücklich erkennbar. Die neue
Beobachtung wurde erst nach den beendeten Versuchen hinzugefügt und füllt deren
fehlende Daten nicht nachträglich auf. Sie bringt zusätzliche Diagnosearbeit
mit sich und muss bei der nächsten Paarqualifikation berücksichtigt werden.

Die nächste Gegenprüfung benötigt mehr NAS-Reserve oder ein separates
isoliertes Linux-Testziel. Controller und CI-Worker sollen weiterhin auf dem
NAS bleiben. Ein konkretes, höchstens zweistündiges Fenster mit sieben
vorübergehend gestoppten NAS-Anwendungen ist in
[nas-resource-window.md](nas-resource-window.md) vorbereitet, aber nicht
ausgeführt: Diese Anwendungen liegen außerhalb des freigegebenen Teststacks.

## Browser-Gegenprüfung

Jenkins #23 reproduziert denselben Originalfehler der fehlenden Expand/Collapse-
Schaltfläche innerhalb von fünf Sekunden. Sein originales CI-Archiv ist
421.765 Byte groß, SHA-256 `4e56b9f1871c656929d7a15411071b12dd156cf8d6568f331c611bd41468e3cb`.
Der anschließende Leroy-Lauf `975f6c65b6204a818c8c52af319d1d40` und Jenkins #24
bestehen den unveränderten einzelnen Fall auf jeweils frischer Basis. Ihre
originalen Archive haben SHA-256
`93268ed3ebb2c5c1d5c52e77067c55dcd88c223fe617eebcfc4ffc08060682b4` und
`0119e01a2db112bf577241a737a2efbc0404bb1e75ed33934b3e044bc5323552`.
Alle Quittungen haben dasselbe Runtime-Image, Quellenarchiv und Bauzeitpunkt;
Cleanup ist vollständig, kein Erfolg wiederverwendet. Bilder, Konfiguration,
Ressourcen, Durabilität und sechs Treiber sind über das erfolgreiche Paar gleich.
Auch der Zusatzbeobachter hat bei diesem Paar denselben Quellstand.

Diese Ergebnisse widerlegen eine feste Bindung dieses Fehlers an Leroy. Sie
beweisen keine historische Ursache oder Leistungsgleichheit. Die Zusatzspuren
sind wegen Paketverlusten, Parserfehlern und Neustart-/Cleanup-Lücken unvollständig.
Cookie-, Konto-, Token- und Client-Zuordnungen werden nur über HMAC-Pseudonyme
gespeichert. Browser-DOM und verschlüsselte Client-Proxy-Strecken werden nicht
vollständig erfasst. Auch beide erfolgreiche Einzelfälle sind kein vollständiger
Web- oder Release-Nachweis. Sämtliche ursprünglichen Erfolge und Fehler bleiben
erhalten, einschließlich des ersten fehlerhaften Beobachterstarts.

Die nächste Beobachterversion stellt ausschließlich am eigenen Paket-Socket
einen größeren Empfangspuffer ein. Eine echte Linux-Probe bestätigt 16 MiB
wirksamen Puffer und danach allein NET_RAW als verbleibende Capability;
`net.core.rmem_max` des Gasts bleibt unverändert. Die Beobachtung wird nach
Netzwerk-Namensraum statt nur nach Container-PID unterschieden. Erwartete
`ps`-/`inspect`-Rennen bei der ursprünglichen Fixture-Bereinigung beenden den
Beobachter nicht mehr vorzeitig. Parser-Selbstprüfung und Datenschutztests
bestehen. Diese begrenzte Socket-Probe beweist noch keinen verlustfreien
Original-Browser-Mitschnitt; die älteren verlustbehafteten Spuren bleiben erhalten.

Der zusätzliche Zielgast auf dem NAS bleibt ein erheblicher Unterschied zum
produktiven Jenkins, dessen Postdeploy-Qualität auf einem externen Linux-Ziel
läuft. Auch die isolierte einzelne Clippy-Gruppe überschreitet hier die sichere
NAS-Swap-Reserve. Eine weitere vollständige Serie ohne Lösung dieses Problems
wäre kein belastbarer Freigabeschritt.

Für `dev-environments` ist zusätzlich ein passiver HTTP-Beobachter vorbereitet.
Seine optionalen Client-Metadaten verwenden zufällige HMAC-Schlüssel pro
Lauf, gemeinsam über dessen Serverneustarts: Login-Konten, Browser-Cookies,
Tokens und Client-IDs werden ausschließlich als
Pseudonyme zugeordnet; Passwörter, Kontonamen, Tokens, Befehlsargumente und
Pakete werden nicht gespeichert. Der bisherige Beobachtermodus bleibt ohne
diese Option inhaltlich gleich. Paketverluste, Parserfehler, fehlende
Startabdeckung und Beobachtereinfluss sind zu prüfen. HTTP-Spuren erfassen
keinen Browser-DOM und beweisen allein nicht, welcher Expand-Button fehlt.


## Transport und visuelle Prüfung

Große Gast-Diagnoseprogramme überschritten vor dem ersten Browser-CI-Start
die Windows-Prozessargumentgrenze. Der SSH-Helfer überträgt diese Eingaben nun
als geschützte Dateien und prüft ihre Bytes mit SHA-256 vor der Übergabe an
denselben Gast. Hostschlüsselprüfung, Namespace, Befehle und Nutzdaten bleiben
gleich. Die ungewisse Vorbereitung wurde geprüft und weiterverwendet; der
ursprüngliche CI-Start wurde dadurch nicht wiederholt.

78 gezielte lokale Tests bestehen; Ruff für die geänderten Hilfen besteht.
Sechs zusätzliche Ansichten des tatsächlichen Clippy-Fehlerlaufs wurden auf
Desktop und Mobilgerät technisch und direkt visuell geprüft, einschließlich
des Downloads der tatsächlichen 189-Byte-Quittung. Bilder und Artefakt haben
Prüfsummen; die Visualisierung stimmt mit den CI-Daten überein. Dies erhöht die
historische NAS-UI-Zahl zunächst auf 383 und erteilt keine Anwendungsfreigabe.
Weitere sechs direkt geprüfte Ansichten des erfolgreichen einzelnen
Leroy-Browserlaufs bestätigen Status, Prüfumfang und beide Artefakt-Prüfsummen;
die historische NAS-UI-Zahl steigt dadurch auf 389. Weitere sechs direkt
geprüfte Ansichten des tatsächlich abgebrochenen Laufs Nummer 160 bestätigen
Lease-Grund, Schrittstatus, Zeitachse, unveränderte Parameter und das Fehlen
von Ergebnissen und Artefakten. Die aktuelle historische NAS-UI-Zahl ist 395.

## Abschluss des begrenzten Fensters am 13. Oktober

Die zusätzliche freigegebene NAS-Reserve und das Profil mit 3,5 GiB bevorzugtem
QEMU-RAM ermöglichen erstmals vollständige erfolgreiche Original-Clippy-
Prüfungen auf der Ziel-VM unter beiden Engines. Leroy #162 und privater Jenkins
#21 verwenden die unveränderte eingefrorene Quelle, gleiche Release-Identität,
fünf gleiche aufgelöste Build-Basis-Images und die gleiche Infrastruktur. Beide
Quittungen bestätigen Exitcode 0, vollständigen Cleanup und keine Wiederverwendung.
Alle vier Basisdienste bleiben bei beiden gesund. Das ist ein positiver
Einzelgruppennachweis und keine vollständige Release- oder Leistungsfreigabe.

Der ursprüngliche erste Fensterlauf mit 4 GiB bevorzugtem VM-RAM bleibt als
RAM-Schutzabbruch erhalten. Eine Folgeprobe erhält ausdrücklich keine neue
Zweistundenfrist. Alle sieben ursprünglichen Dienste sind um 02:07 Uhr Berliner
Zeit wieder gestartet, vor 02:10 Uhr gesund und stabil geprüft; ursprüngliches
Fristende 02:20 Uhr, insgesamt rund 107 Minuten. Test-VM, privater Jenkins,
Jobworker und Rücksicherung sind beendet. Einzelbelege:
[nas-resource-window.md](nas-resource-window.md).

### Controller-OOM und Messkorrektur

Der Kernel belegt während Jenkins #21 einen lokalen Controller-Cgroup-OOM bei
256 MiB. Uvicorn wird beendet und derselbe Container automatisch neu gestartet.
Die regelmäßige Python-/SQLAlchemy-Zusatzprobe teilte dieses Budget mit der API;
erfolgreiches SQL nach dem Neustart schloss die kurzzeitige API-Unterbrechung
nicht aus. Ihr Anteil an sämtlichen historischen Lease-Ausfällen ist nicht bewiesen.

`diagnose_nas_release_group.py` startet diese Probe künftig nicht mehr im
Controller. Der leichte PostgreSQL-Client prüft die eigene Datenbank lokal,
schreibgeschützt und mit Statement-Frist; seine Ergebnisse sind ausdrücklich
als `postgres_container` bezeichnet. Die bestehende API-Bereitschaftsprüfung
prüft weiter den echten Controller-Datenbankpfad. Historische Messreihen und
ihre Fehler werden nicht nachträglich geändert.

`probe_nas_controller_memory.py` qualifiziert begrenzte Anmeldung und die alte
Probe in einer getrennten 512-MiB-API mit eigener Datenbank. Acht Runden bestehen
ohne OOM oder Neustart; das frische Datenvolumen reproduziert die historische
Last nicht vollständig. Container und Datenbank werden entfernt. Der erhaltene
Fehler des ersten Probehelfers betraf die vor dem Start gelesene Container-IP;
die korrigierte Qualifikation ist ein eigener Versuch.

`deploy_nas_controller_memory.py` setzt nach dieser Grundqualifikation das
eigene laufende Controllerlimit auf **512 MiB ohne Swap** und persistiert es
im Compose-Override. Reservierung 128 MiB, oberste gemeinsame Reservierung
320 MiB, CPU-Grenze, PID, Image, Mounts, Umgebung und übrige Dienste bleiben
unverändert. Keine Neuerstellung oder zusätzlicher Neustart. Vorherige
Konfiguration, Containeraufnahmen und PostgreSQL-Dump sind geschützt gesichert
unter `/volume1/docker/leroy-nas-parity/controller-memory-deployment-20261013`.
Backup SHA-256 `08c299d3c1c7b2d0f3f5f4fbad4a60e5284255dbee0065f4d6caf79a5d76b4db`.

Die Compose-Normalisierung verwendet Zeichenketten für Speicherwerte. Die
erste Validierung stoppte deshalb vor jeder Änderung; die explizite Fortsetzung
verwendete dieselben gesicherten Ausgangsdateien und prüfte, dass ausschließlich
die zwei Speichergrenzen abweichen. Der Laufzustand blieb während der Korrektur
erhalten. NAS- und vorbereitete Produktions-Compose-Datei enthalten ebenfalls
512 MiB; die Produktionskonfiguration ist nicht aktiviert.

Zehn parallele authentifizierte Metadaten-Abfragesequenzen am tatsächlichen
Controller bestehen ohne neuen OOM oder Neustart. Diese Grundprüfungen ersetzen
keinen vollständigen Original-Lastlauf nach der Korrektur. Die alten Clippy-
Nachweise gelten für den zuvor gemessenen Stand. 88 gezielte Tests bestehen;
407 historische NAS-Ansichten sind technisch und direkt visuell geprüft.
Die vollständige Produktionsfreigabe bleibt offen.
