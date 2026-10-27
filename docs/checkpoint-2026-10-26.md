# Leroy: gesicherter Zwischenstand vom 26. Oktober 2026

Die Jenkins-Ablöse ist auf Nutzerwunsch verschoben, bis ein geeigneter Build-Server
außerhalb des NAS bereitsteht. Jenkins bleibt produktiv. Leroy hat keine
Produktionsfreigabe. Dieser Stand bewahrt Implementierung und Nachweise für die
spätere Fortsetzung; er ist keine bestandene vollständige Release-Abnahme.

## Aktueller Betrieb

| Bestandteil | Zustand |
| --- | --- |
| Produktiver NAS-Jenkins | Gesund; ursprüngliches Image, Ressourcen, Benutzer, Mounts, Netzwerk und Ports bestätigt |
| Produktive Jenkins-Jobs | Erhalten; keine Rücksetzung von Quellen, Konfiguration oder Buildhistorie |
| Paperless, Sonarr, Radarr, SABnzbd, Plex, yt-downloader-service, mail-ingest-service | Gesund; gleiche Container und Konfigurationen wie vor dem letzten Fenster |
| Leroy-Controller, Runner, PostgreSQL, Testdaemon, VM-Zugangsbrücke | Gestoppt; automatische Neustarts deaktiviert |
| Isolierte Graphato-Test-VM | Gestoppt; kein automatischer Neustart |
| Lokale Leroy-Docker-Dienste und lokale Test-VM | Nicht gestartet; die Vorgabe „lokal nur NameFinder“ bleibt bestehen |
| Automatische NAS-Abnahmefortsetzung | Beendet; keine neuen CI-Aufträge oder Wartungsfenster |

Der produktive Jenkins musste nicht zurückgerollt werden: Die Ablöse hatte nie
stattgefunden. Der Abgleich mit dem NAS-Inventar vom 3. Oktober bestätigt das Image
`sha256:03daffe03ae4aa3d90256f10e04b635bf6b8f5e981f55f97f1115105ae4d230f`,
unbegrenzte ursprüngliche Container-Ressourcen sowie dieselben Datenträger und Ports.
Er wurde während der Stilllegung nicht neu gestartet oder verändert. Auch die
Buildzähler und die älteren, möglicherweise überlappenden Buildhistorien wurden
vor und nach den Arbeiten geprüft. Es gab dabei keinen laufenden Produktionsbuild.

## Was implementiert wurde

- Python-Pipelines und versionierter Pipeline-Katalog; Ausführung in getrennten
  Docker-Workern mit Checkout, Parametern, Zeitlimits und begrenzten Zugangsdaten.
- FastAPI-Controller mit PostgreSQL, SQLAlchemy/Alembic, dauerhafter Queue,
  Statusübergängen, Ereignissen, Zeitplanung, Authentifizierung und Runner-Leases.
- Svelte-/TypeScript-Oberfläche mit Pipeline-Graph, Zeitachse, Live-Logs,
  Ergebnissen, Artefakten und nachvollziehbarer Ausführungsidentität.
- Migration der inventarisierten Jenkins-Jobs und ihrer referenzierten Skripte;
  getrennte Prüfungen für Quellstände, Runtime-Images, Fixtures und Zielsysteme.
- Sicherung/Rücksicherung, Wiederanlauf- und Abbruchbehandlung sowie Werkzeuge
  zum Vergleich ursprünglicher Jenkins- und Leroy-Aufträge.
- Korrekturen an Heartbeat-, Lease- und Transportbehandlung. Eine begrenzte
  asynchrone Console-Ausgabe verhindert die reproduzierte Blockade des Controllers
  an einer vollen Ausgabepipe, ohne dauerhafte Joblogs oder Artefakte zu ersetzen.
- NAS-seitige Koordination mit eindeutigen systemd-Invocations, atomaren Journalen,
  unabhängigen Wiederherstellungswächtern und Schutz vor doppeltem CI-Dispatch.

Die NAS-Werkzeuge unter `scripts/` enthalten bewusst gebundene historische
Versuche. Ihre Namen, Belege und Hostpfade sind keine portable Produktionskonfiguration.
Sie dürfen beim späteren Neustart nicht pauschal oder in einer Schleife ausgeführt
werden. Architektur, Betrieb und Jobmigration sind in [README](../README.md),
[operations.md](operations.md) und [migration.md](migration.md) beschrieben.

## Was tatsächlich nachgewiesen ist

Der lokale Python-Quellstand besteht 788 Tests. 43 Prüfungen benötigen hier nicht
vorhandene PostgreSQL-/SCM-Testumgebungen und sind übersprungen. Ruff besteht für
`src`, `scripts` und `tests`; Svelte-Check meldet null Fehler/Warnungen und der
Web-Produktionsbuild ist erfolgreich. Eine separate Kopie der 549 Git-fähigen
Dateien (ohne lokale Belege, Zugangsdaten, `.sources` oder Laufzeitabhängigkeiten)
besteht ebenfalls 788 Tests mit denselben 43 Skips. Die Prüfung findet keines der
bekannten lokalen NAS-/Leroy-Secrets im eincheckbaren Dateisatz.
Der [bereinigte Prüfbericht](evidence/checkpoint-validation-20261026.json) hält
Umfang und Ergebnis fest. Die letzte separate NAS-Operatorqualifikation bestand
678 native Tests ohne Skips. Diese Zahlen unterscheiden sich nach Umgebung und
Prüfumfang und dürfen nicht als Graphato-Release-Ergebnis gelesen werden.

Historische Infrastruktur-, Backup-/Restore- und einzelne Pipelinevergleiche sind
erfolgreich dokumentiert. Die frühere lokale Jobabnahme enthielt bei Graphato und
Antares separat bewertete Anwendungspatches. Diese sind keine nachgewiesene
Voraussetzung für Leroy und werden nicht als Beleg für unveränderte Originalquellen
übernommen. Antares war nur im NAS-Vergleich aus Kapazitätsgründen ausgenommen.

Am 26. Oktober wurden nochmals sechs aktuelle Desktop-/Mobilansichten von Leroy
#186 technisch und direkt visuell geprüft. Graph, Zeitachse, Fehleranzeige,
Ergebnisse und Artefakte sind lesbar; es gab keine Seitenfehler oder Seitenüberläufe.
Das originale 189-Byte-Abbruchartefakt ist per SHA-256 geprüft. Dies ersetzt keine
abschließende UI-Prüfung eines künftig erfolgreichen Release-Laufs.

### Letzter eingefrorener Graphato-Vergleich

| Merkmal | Leroy #186 | Privater Jenkins #31 |
| --- | --- | --- |
| CI-Ergebnis | `failed` | `FAILURE` |
| Original-Run | `f4af042f894b422bbeda50a8b07c8d98` | Backend `20ba640fd3144335b3d9a24111577651` |
| Ursprüngliche CI-Artefakte | Abbruchquittung, 189 Byte | Leeres Artefaktverzeichnis; ursprüngliche Builddateien vollständig gesichert |
| Getrennte Offline-Quittung | Kompilierlimit erreicht, vollständige Bereinigung | Abgebrochen, vollständige Bereinigung |
| Ausgeführte Rust-Tests | 0 | 0 |

Beide Läufe binden denselben Commit
`0ad540dd578033d45e4d0c25d89fbe57b32102a4`, dieselbe Runtime
`6251c60f499e41e706613f931bf281ce52312b957d5a6a123cf4e27dd3242585`,
dasselbe Quellarchiv
`f0c737a8133cd73f6b34c66be5081316a7047a1881583532874b40abaec59708`
und den Buildstempel `20261006113757`. Die vollständigen Ausgangsmanifeste und
Vorbereitungsparameter stimmen überein. Quellen, Tests, ursprüngliche Fixture-
und Zeitlimits wurden für diesen Vergleich nicht verändert.

Bei Leroy hielten nach der Console-Korrektur Controller und Lease; Gast-SSH fiel
aus. Die Offline-Daten belegen das ursprüngliche 90-Minuten-Kompilierlimit.
Jenkins verlor seinen Dateisystem-Heartbeat; sein Console-Log endet mit einem
Fehler beim Speichern des Pipeline-Zustands. NAS-Prozessbeobachtungen zeigen
Btrfs-Transaktionswartezeiten von Steuerung und Jenkins-Heartbeat. Die private
Jenkins-Persistenz und Operatorjournale lagen weiterhin auf HDD, VM und Engine
auf NVMe. Weder gleiche Laufzeiten noch Gleichwertigkeit oder eine erfolgreiche
ursprüngliche Rust-Abnahme sind damit bewiesen.

Jenkins #31 ist bereits am 17. Oktober beendet worden. Der Wächter startete alle
sieben Dienste bis 15:18:45 Berliner Zeit wieder, vor der Fensterfrist. Die
vollständige damalige Gesundheitsquittung fehlt; die Gesundheit am 26. Oktober ist
dagegen neu geprüft. Das nach dem NAS-Neustart zurückgebliebene `running` im alten
Koordinatorjournal berechtigt nicht zum Wiederholen dieses Auftrags.

Nach dem NAS-Neustart trat zusätzlich ein Adresskonflikt auf: Der dynamisch
adressierte Runner belegte die feste PostgreSQL-Adresse. Explizite Adressen für
PostgreSQL, Testdaemon und Runner beseitigen diesen Fehler. Die tatsächliche
Gegenprobe „Runner zuerst, danach PostgreSQL“ ist bestanden; Container-IDs, Images,
Ressourcen und Datenbankbestand blieben gleich. Die Korrektur ist in
`infra/nas/compose.yaml` und `scripts/recover_nas_control_network.py` nachvollziehbar.

Ein begonnener SSD-Umzug des privaten Jenkins wurde auf den neuen Nutzerwunsch
hin bereits während der Bestandsaufnahme beendet. Es wurde noch kein Verzeichnis
kopiert, kein Volume umgeschaltet und kein Container dafür ersetzt. Dieser Umzug
ist nicht durchgeführt oder qualifiziert.

## Sicherungen und Nachweise

Der NAS-Testbestand bleibt erhalten. Vor dem Stilllegen wurde ein logischer
PostgreSQL-Dump erzeugt: 174 Runs, 476 Schritte, 610 Artefakte, kein aktiver Lauf.
Der Dump liegt privat unter
`/volume1/docker/leroy-nas-parity/postponed-20261026/leroy.dump`;
SHA-256 `b22325ea2c0e14b53ad7c289bd247ab5f7ead9c46356f23aafa47e8f43a73986`.
Controllerdaten und Artefakte verbleiben auf dem zugehörigen SSD-Testdatenträger,
die ursprünglichen Volumes und vorherigen Sicherungen bleiben erhalten.

Beide letzten Testplatten sind auf HDD archiviert und vollständig zurückgelesen:

| Platte | Bytes | SHA-256 |
| --- | ---: | --- |
| W / Leroy | 14.269.743.104 | `b85506cb036aa395ada45f5ade22eb2a8db4d8835e9128e778a4f6f5bc4b3d71` |
| Y / Jenkins | 14.331.805.696 | `c16dfdee5a450cf62b7e915db88ab011457304304c36d0359131c919ceb56095` |

Sie liegen unter
`/volume1/docker/leroy-nas-parity/release-vm/0ad540dd5780/archived-acceptance-20261017/`.
Die entsprechenden SSD-Kopien und RAM-Dateien sind entfernt. Diese Platten bleiben
historische Fehlernachweise und werden nicht als frische Ausgangs-Fixtures verwendet.

Die detaillierten privaten Nachweise liegen unter `test-results/nas-parity/followup/`,
insbesondere `status-20261026-y2/`, `jenkins-only-20261026/`,
`control-network-recovery-20261026/` sowie in den W-/Y-Laufverzeichnissen.
Die sechs aktuellen UI-Aufnahmen stehen unter
`test-results/nas-parity/recovered-nas-186-20261026/`.
Ein kleiner, bereinigter Abschlussnachweis wird unter
[evidence/jenkins-only-20261026.json](evidence/jenkins-only-20261026.json) mit versioniert.

Zugangsdaten, Rohlogs, Datenbankdumps, VM-Platten, Quellkopien und lokale Laufzeiten
gehören nicht ins Git. `.local/`, `.sources/`, `test-results/`, gebaute Webdateien
und Abhängigkeiten sind ausgeschlossen. Die Rohbelege sind daher nach einem
frischen Checkout nicht automatisch vorhanden. Die historischen NAS-Operatoren
verlangen diese privaten Belege absichtlich; die normale Softwareprüfung benötigt
sie nicht. Die Eincheckbarkeit wird zusätzlich an einer Kopie ausschließlich der
Git-fähigen Dateien geprüft.

## Wiederaufnahme auf dem neuen Build-Server

1. **Neue Ausführungsumgebung festlegen.** Linux, Docker, getrennte Testnetze,
   persistente SSD-Verzeichnisse für Controller, PostgreSQL, Logs, private Jenkins-
   Referenz und Worker-Caches einrichten. Kapazität für den ursprünglichen
   6-GiB-Builder ohne Swap zuzüglich Runtime, Datenbanken, Browsern und CI-Steuerung
   anhand der tatsächlichen Last prüfen. NAS-spezifische Speicherumgehungen und
   feste Testadressen nicht ungeprüft übertragen. Der produktive NAS-Jenkins bleibt
   währenddessen verfügbar.
2. **Quellen und Vergleichsbasis neu binden.** Zunächst den offenen eingefrorenen
   Graphato-Stand mit seinen originalen Quellen und Tests reproduzieren. Ein
   späterer Wechsel auf einen neueren Master benötigt eine bewusst neu gebundene
   Vergleichsbasis für beide Engines. Runtime, Quellarchiv, Buildstempel,
   Abhängigkeiten, Worker und Fixture-Inventare vor dem Start vollständig erfassen.
3. **Steuerung qualifizieren.** PostgreSQL-Integrationstests, Queue-/Lease- und
   Abbruchbehandlung, blockierende Console-Ausgabe, Verbindungsverlust,
   Wiederanlauf und Sicherung/Rücksicherung auf dem neuen Linux-Host testen.
   Automatische Trigger bleiben bis zur Umschaltung deaktiviert.
4. **Frische ursprüngliche Rust-Aufträge vergleichen.** Neue eindeutige Läufe unter
   Jenkins und Leroy mit gleichen Parametern und Ressourcen starten. Keine
   Wiederholung einer unklar quittierten Dispatch-Anfrage, keine Übernahme alter
   Caches oder gescheiterter Testplatten als frische Fixture. Beide Original-CI-
   Abschlüsse und vollständigen benannten Testinventare sind erforderlich.
5. **Vollständige Graphato-Release-Abnahme ausführen.** Alle 29 Originalgruppen
   müssen in beiden Engines mit unveränderten Quellen, Tests, Fixtures und
   ursprünglichen Grenzen erfolgreich enden. Originalarchive müssen vollständig
   von der jeweiligen CI veröffentlicht werden; Offline-Daten bleiben Ergänzung.
   Externe Ratenlimits und Hintergrundlast erfassen, ohne Tests passend zu machen.
6. **Weitere migrierte Pipelines erneut prüfen.** Bootstrap-, Gitea-, Home-Lab-,
   Nikicas-Hub-, Paperless- und Musiksynchronisationsaufgaben in isolierten Zielen
   samt Abhängigkeiten und Zugangsdaten prüfen. Die NAS-Ausnahme für Antares ist
   auf dem neuen Server neu zu bewerten. Anwendungspatches separat bewerten.
7. **UI und Betrieb abschließend abnehmen.** Alle Ansichten, Erfolgs-/Fehlerzustände,
   Live-Logs, Artefakte, Graph und Zeitachse auf Desktop und Mobil direkt visuell
   prüfen. Backups, Wiederherstellung, Neustart, Authentifizierung, Secret-Redaktion
   und Alarmierung an der finalen Installation testen.
8. **Erst danach umschalten.** Nach geprüften Originalergebnissen und ausdrücklicher
   Freigabe Trigger und Credentials schrittweise übernehmen. Jenkins-Jobdefinitionen
   und Daten für einen belegten Rückweg sichern. Keine parallelen Schreibzugriffe
   beider CI-Systeme auf produktive Deploy- oder Synchronisationsziele zulassen.

Alte NAS-Wartungsfreigaben sind beendet. Der neue Build-Server eröffnet keine
automatische Berechtigung, die sieben NAS-Dienste erneut zu pausieren oder alte
Abnahmejobs wieder zu starten.

## Prüfen und einchecken

```powershell
.venv/Scripts/ruff.exe check src scripts tests
.venv/Scripts/python.exe -m pytest -q
npm --prefix web run check
npm --prefix web run build
git diff --check
git status --short
```

Für einen neuen Checkout zuerst die Python-Testabhängigkeiten aus `pyproject.toml`
und die Web-Abhängigkeiten mit `npm ci` installieren. PostgreSQL-/SCM- und laufende
UI-Prüfungen brauchen ihre ausdrücklich eingerichteten Testumgebungen. Keiner der
oben genannten Standardchecks startet Docker oder eine VM. Dieser Arbeitsstand
wird vorbereitet, aber durch die Dokumentation nicht automatisch committed,
gepusht oder produktiv ausgerollt.
