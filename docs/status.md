# Projektstand und nächste Schritte

Dokumentationsstand: 9. Oktober 2026. Letzter erhaltener NAS-Versuch:
7. Oktober 2026. **Leroy ist implementiert und im isolierten Parallelbetrieb
geprüft; die vollständige Produktionsfreigabe bleibt offen.** Jenkins ist weiterhin
das produktive CI-System. Die Veröffentlichung dieses Quellstands stellt keine
Produktionsumschaltung dar.

## Implementiert

- Python-Controller mit FastAPI, PostgreSQL, SQLAlchemy und Alembic. Pipeline-
  Definitionen, Ausführungsversuche, Queue, Ereignisse und Artefakt-Metadaten
  werden dauerhaft gespeichert. Läufe behalten ihren Definitions-Snapshot.
- Docker-Runner mit getrennten Ausführungsprofilen, Ressourcenlimits,
  Heartbeats, Lease-Wiederherstellung, Abbruch, Timeout und erneuten Versuchen.
  Kindläufe und gemeinsame Release-Abnahmen sind abgebildet.
- Authentifizierung, Administrator-/Leserrollen, begrenzte Runner-Zugänge und
  Secret-Dateien. Logs und Artefakte liegen auf persistentem Speicher;
  Herkunft und Prüfsummen werden mitgeführt.
- Manuelle Starts, Parameter, Git-Änderungserkennung und Zeitplanung sowie
  versionierter Import der migrierten Pipeline-Definitionen.
- Statische Svelte-/TypeScript-Oberfläche mit Abhängigkeitsgraph, Zeitachse,
  Schrittstatus, Live-Logs, Artefakten, Laufhierarchie und Fehlerursachen.
  Beschreibende Werbetexte wurden entfernt.
- Docker-/Compose-Konfigurationen für Entwicklung, isolierte Testziele,
  Linux-Test-VM und NAS-Parallelbetrieb. Ein gesondertes Produktionsbundle für
  zwölf Pipelines und vier Worker-Profile ist vorbereitet; seine produktive
  Konfiguration und Trigger sind noch nicht aktiviert.

Redis, Message Broker, Kubernetes, Elasticsearch, ein S3-Dienst und ein separater
Node-Webserver sind für Leroy nicht erforderlich. Weitere Dienste in den
Testumgebungen gehören zu den ausgeführten Anwendungen.

## Migration und bisherige Prüfungen

Die Inventarisierung umfasst alle 13 vorhandenen Jenkins-Jobs und die weiteren
Artefakte der referenzierten Repositories `home-lab-service-collection`,
`graphato`, `nikicas-hub` und `antares`. Jenkinsfiles, Inline-Skripte,
Build-/Deployment-Helfer, Hostabsicherung, Release-Receipts und Browser-/DB-Tests
wurden dabei berücksichtigt. Die Umsetzung und bewusste Unterschiede stehen
in [migration.md](migration.md), das Inventar in
[jenkins-inventory.json](jenkins-inventory.json).

In der früheren lokalen Docker-/Linux-VM-Abnahme haben alle 13 migrierten Jobs
ihre Aufgaben abgeschlossen. Die dort erfolgreichen Antares-/Graphato-Stände
enthalten separat dokumentierte Anwendungskorrekturen. Diese Ergebnisse belegen
die damaligen Kandidaten; sie beweisen keine Gleichwertigkeit unveränderter
Produktionsstände. Die Patches sind unter [upstream-patches](upstream-patches/)
erhalten und gelten nicht als belegte Voraussetzung für den Jenkins-Wechsel.

Gemäß Nutzerentscheidung sollen Controller und CI-Worker vollständig auf dem NAS
laufen. Antares ist als Artefakt von dieser NAS-Abnahme ausgenommen; der Umfang
besteht deshalb aus zwölf Pipelines. Ein zusätzlicher externer Linux-Worker ist
keine Anforderung. Die Pipeline-Matrix steht in
[nas-acceptance.md](nas-acceptance.md).

Erhaltene positive Nachweise umfassen insbesondere:

- Den echten Home-Lab-Build-/Push-Vergleich auf gleichem Originalcommit und
  gleichem Ausgangspunkt, einschließlich Image-Inhalten und Registry-Prüfung.
- Graphato-Build, Auslieferung und Veröffentlichung mit unveränderten Quellen
  unter beiden Engines. Fehler bei der frischen Installation werden gesondert
  von den Prüfungen auf einem vorbereiteten Host-Snapshot behandelt.
- NAS-Betriebsprüfungen für Queue, Prozessabbruch, zwei Worker, Neustart bei
  aktiver Arbeit, vollständigen Stack-Neustart und Rücksicherung von Datenbank,
  Logs, Artefakten und geschützter Konfiguration. Festgeschriebene Images wurden
  wiederhergestellt und echte Jobs in allen vier Worker-Profilen ausgeführt.
- Technische und visuelle Prüfung von insgesamt 227 NAS-Ansichten auf Desktop
  und Mobilgeräten sowie Prüfungen von Fehler-, Lade- und Wiederanlaufzuständen.
- Korrekturen in Leroy, unter anderem an SSH-Sitzungen im Fehlerpfad,
  Runner-Cleanup, Log-Heartbeats, Artefaktbehandlung und sichtbaren Kindlauf-
  Fehlerursachen. Die jeweiligen gezielten Nachprüfungen sind erhalten.

Die detaillierten historischen Ergebnisse stehen in
[implementation.md](implementation.md) und [nas-parity.md](nas-parity.md).
[acceptance.json](acceptance.json) enthält historische Abnahmequittungen und
deren jeweiligen Umfang; sein früheres `complete` ist keine aktuelle
Produktionsfreigabe.

## Offener Graphato-Vergleich

Der ausdrücklich eingefrorene Originalstand bleibt
`0ad540dd578033d45e4d0c25d89fbe57b32102a4`. Anwendung, Originaltests und Ratenlimits
werden für die aktuelle Ursachenuntersuchung nicht geändert. Der gesonderte
Soak-Testtreiber-Vorschlag ist zurückgestellt.

Im vollständigen Vergleich auf gleichem vorbereiteten Host-Snapshot bestehen
bei beiden Engines 20 von 21 Webgruppen. Der ursprüngliche Browser-Soak bricht
an einer HTTP-429-Ratenbegrenzung ab. Qualität besteht zunächst bei Jenkins
8/8 und bei Leroy 7/8 Gruppen: Eine Rust-Assertion erwartet mindestens einen
Serialisierungs-Retry. Spätere vollständige Rust-Vergleichsläufe bestehen unter
beiden Engines; auch der zusätzliche vollständige Leroy-Release-Lauf besteht
alle acht Qualitätsgruppen. Die Ursache der früheren Abweichung ist damit noch
nicht bewiesen. Dieser Release bleibt wegen des Soak-Fehlers mit 28/29 bestandenen
Prüfgruppen fehlgeschlagen.

Erhaltene Original-Soak-Läufe zeigen sowohl Erfolg als auch denselben
Ratenlimitfehler. Ein A/B/A-Vergleich mit dem isoliert gebauten und dem originalen
produktiven Runtime-Inhalt scheitert in allen drei Proben. Ein produktiver
Jenkins-Build überschneidet sich mit diesen Proben; deshalb sind sie kein
Vergleich bei ruhiger NAS-Last. Die lesende Analyse findet zusätzliche
UI-Statusabfragen als konkreten Kandidaten für die Lastverstärkung, beweist aber
noch keine Ursache der historischen Ergebnisdifferenz.

Der nächste Vergleich ist vorbereitet: **Jenkins, Leroy, Leroy, Jenkins** direkt
im vorhandenen isolierten NAS-Testdaemon, mit frischer Fixture pro Probe,
originalem CI-#23-Runtime-Inhalt und einem gemeinsamen Browser-Worker aus dem
unveränderten Original-Dockerfile. Ein separater passiver Beobachter soll
ausschließlich HTTP-Metadaten erfassen; sein Aufwand bleibt eine Messgrenze.
Die Quell- und Archivprüfsummen sind bestätigt, das Runtime-Archiv ist vollständig
auf das NAS übertragen. Ein passender AppArmor-Parser wurde ausschließlich im
isolierten Testdaemon bereitgestellt und liest das Originalprofil erfolgreich.

**Letzter tatsächlicher Schritt:** Nachdem die beobachteten produktiven Jobs
beendet waren, scheiterte die Materialisierung am 7. Oktober um 02:34 Uhr MESZ
beim `docker load` im isolierten NAS-Testdaemon mit Exitcode 1. Die erhaltene
Fehlerquittung enthält keine ausreichende Docker-Fehlerausgabe zur Ursachenklärung.
Worker-Bau und die neue J/L/L/J-Serie sind nicht als abgeschlossen nachgewiesen;
es wurden dabei keine Soak-Tests gestartet. Dieser Importfehler wird nicht als
belegter Speicher-, Archiv- oder Anwendungsfehler eingeordnet.

Die lokale Leroy-Docker-Umgebung und die zuvor durch OOM beendete Windows-Test-VM
bleiben gestoppt. Lokal läuft gemäß Nutzerwunsch ausschließlich NameFinder.
Volumes, Images und bisherige Nachweise sind erhalten.

## Weiterer Plan

1. Den gescheiterten Import im eigenen NAS-Testdaemon untersuchen: tatsächliche
   Docker-Fehlerausgabe, Speicher-/Plattenbelegung und Daemon-Zustand erfassen.
   Das bereits verifizierte Archiv erhalten und gezielt wiederverwenden.
   Produktive Dienste und Docker-Stores bleiben außerhalb dieser Wiederherstellung.
2. Nach erfolgreichem Import den gemeinsamen Original-Worker bauen und dessen
   Testdateien, Werkzeuge, Images und AppArmor-Konfiguration prüfen. Danach die
   vorbereitete J/L/L/J-Serie ausführen. Vor und nach jeder Probe produktive
   Jenkins-Aktivität lesend prüfen; Überschneidungen kennzeichnen den Lauf als
   ungeeignet für einen Lastvergleich. Jenkins darf parallel weiterarbeiten.
3. Originale Ergebnisse, Server-Anfragezeiten, 429-Antworten und Ressourcen-
   bedingungen vergleichen. Beobachterverluste und Beobachtereinfluss als Grenzen
   ausweisen. Bei einer CI-Abweichung zuerst Leroys Ausführung und Konfiguration
   untersuchen; Anwendungspatches und Teständerungen separat bewerten.
4. Die vollständige Graphato-Release-Abnahme unter beiden Engines mit demselben
   eingefrorenen Stand wiederholen und die offenen Installations-/Prüfergebnisse
   bewerten. Einzelproben und erfolgreiche Infrastrukturtests ersetzen diese
   Anwendungsläufe nicht. Danach die zwölfteilige NAS-Abnahmematrix aktualisieren.
5. Nach abgeschlossener Abnahme das vorbereitete Produktionsbundle mit den
   tatsächlichen Secret-Dateien, Hostschlüsseln und Werkzeugen vervollständigen.
   Manuelle Produktionsläufe und Sicherung/Rücksicherung prüfen, anschließend
   Trigger kontrolliert von Jenkins auf Leroy übertragen und einen Rückweg
   beibehalten. Neuere Graphato-Commits benötigen eigene Nachweise.

## Veröffentlichung und Reproduktion

Der Branch ist wie in den Nachbar-Repositories `master`. Die Remotes sind:

| Remote | Repository |
| --- | --- |
| `origin` | [GitHub](https://github.com/x0r3/leroy) |
| `gitea` | [NAS-Gitea](http://192.168.178.97:3000/gitea-admin/leroy) |

Beide erhalten denselben Quellstand. Zugangsdaten, generierte Konfigurationen,
Quellkopien, VM-/Image-Dateien und private Laufartefakte werden nicht veröffentlicht.
Wie bei Graphato sichert `.gitattributes` LF-Zeilenenden der Linux-Laufzeitdateien;
historische JSON-Nachweise und Anwendungspatches behalten ihre gespeicherten Bytes.
Die historischen Detaildokumente verweisen teilweise auf lokale
`test-results/`-Nachweise. Diese sind bewusst vom Git-Repository ausgeschlossen;
ein neuer Clone enthält deren Rohdaten nicht. Die obige Zusammenfassung benennt
die belegten Ergebnisse und verbleibenden Grenzen auch ohne diese Dateien.

Vor diesem Commit am 9. Oktober geprüft: Ruff für `src`, `scripts` und `tests`;
90 erfolgreiche Python-Tests; Svelte-Prüfung ohne Fehler oder Warnungen;
erfolgreicher UI-Produktionsbuild. 41 PostgreSQL-Tests sind ohne isolierte
Datenbank übersprungen. Docker-/NAS- und visuelle Abnahmeläufe wurden für diese
Veröffentlichung nicht neu gestartet. Setup und Prüfkommandos stehen im
[README](../README.md), [testing.md](testing.md), Betriebsabläufe in
[operations.md](operations.md). NAS-Diagnosehelfer benötigen zusätzlich die
privaten lokalen Zugangsdaten und die vorhandene Testumgebung; ein Clone allein
rekonstruiert diese nicht.
