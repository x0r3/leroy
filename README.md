# Leroy

Python-Pipelines mit PostgreSQL, getrennten Docker-Runnern und einer Oberfläche für
Abhängigkeiten, Zeitachsen, Logs, Artefakte und die Herkunft jedes Ausführungsversuchs.

**Stand 9. Oktober 2026: implementiert und isoliert geprüft;
die vollständige Produktionsfreigabe bleibt offen.** Jenkins läuft weiterhin
produktiv. Bisherige Arbeiten, geprüfte Ergebnisse, offene Punkte und die nächsten
Schritte stehen in [docs/status.md](docs/status.md).

Die frühere lokale Abnahme aller 13 Jobs verwendet bei Antares und Graphato
separat dokumentierte Anwendungskorrekturen. Für den NAS-Betrieb bleiben
Controller und CI-Worker auf dem NAS; Antares ist ausgenommen, sodass zwölf
Pipelines abgenommen werden. Infrastruktur, Sicherung/Rücksicherung,
Home-Lab-Buildvergleich und 227 UI-Ansichten sind geprüft. Der unveränderte
Graphato-Vergleich bleibt wegen fehlgeschlagener Originalprüfungen und einer
noch nicht erklärten früheren Qualitätsabweichung offen. Spätere vollständige
Qualitätsproben bestehen; die Original-Release-Abnahme bleibt am Browser-Soak rot.
Die neue J/L/L/J-Serie auf dem NAS ist vorbereitet, hat nach einem Runtime-
Importfehler aber noch keine Tests gestartet.

Die [Abnahmematrix](docs/nas-acceptance.md),
[historische Implementierungsabnahme](docs/implementation.md) und der
[NAS-Vergleich](docs/nas-parity.md) enthalten die Details. Verweise auf
`test-results/` betreffen private lokale Nachweise, die nicht mitgepusht werden.
Anwendungspatches werden separat bewertet und gelten nicht als belegte
Voraussetzung für Leroy.

## Architektur

| Bestandteil | Aufgabe |
| --- | --- |
| Python / FastAPI | API, Authentifizierung, Zeitplanung, versionierte Pipeline-Definitionen |
| PostgreSQL / SQLAlchemy / Alembic | Dauerhafte Queue, Status, Ereignisse, Transaktionen und Migrationen |
| Docker-Runner | Je Versuch ein Container, Ressourcenlimits, Heartbeats und begrenzte Zugangsdaten |
| Svelte / TypeScript / Svelte Flow | Statische Web-App mit Pipeline-Graph, Zeitachse und Live-Ausgaben |
| Persistentes Dateisystem | Logs und Artefakte; Metadaten und Prüfsummen in PostgreSQL |

Kein Redis, RabbitMQ, Kafka, Kubernetes, Elasticsearch, S3-Dienst oder separater
Node-Webserver ist für Leroy erforderlich. Dienste solcher Art in Testprojekten
sind Anforderungen der migrierten Anwendungen.

## Lokale Docker-Testumgebung

Voraussetzungen: Docker mit Linux-Containern und Compose mit `!override`, Python ab
3.12, Git und Zugriff auf die inventarisierten Quell-Repositories. Die vollständigen
Projekt-Builds benötigen deutlich mehr Ressourcen als Leroy selbst. Die
ursprüngliche Umgebung stellte Docker 12 CPUs und 16 GiB RAM zur Verfügung.
Aktuell bleiben die lokalen Leroy-Dienste und die Test-VM gestoppt;
gemäß Nutzerwunsch läuft lokal nur NameFinder. Die folgenden Befehle starten
die Testumgebung ausdrücklich neu.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[test]"
.venv/Scripts/python.exe scripts/setup_local.py
.venv/Scripts/python.exe scripts/prepare_sources.py
docker build --target job -t leroy-job:local .
docker compose -p leroy-test -f compose.yaml -f compose.test.yaml up -d --build
.venv/Scripts/python.exe scripts/load_test_image.py
.venv/Scripts/python.exe scripts/setup_test_targets.py
.venv/Scripts/python.exe scripts/publish_test_catalog.py
```

Die Oberfläche ist unter http://127.0.0.1:8088 erreichbar. Benutzer: `admin`;
das lokal generierte Passwort liegt in `.local/admin_password`. Zugangsdaten und
Testdaten sind vom Git-Repository ausgeschlossen. Automatische Auslöser bleiben
bis zum geplanten Umstieg deaktiviert. Konfigurationsdateien werden beim erneuten
Setup nicht überschrieben.

Der Test-Runner verwendet einen eigenen verschachtelten Docker-Daemon, eigene
Volumes und eigene Zielcontainer. Er erhält keinen Zugriff auf den äußeren
Docker-Socket. Das ist eine getrennte Testumgebung, keine Abschottung vom Internet:
Builds müssen ihre Abhängigkeiten herunterladen können. Es werden ausschließlich
neu erzeugte Test-Zugangsdaten verwendet.

Konfiguration, Testziele und Nachweise: [docs/testing.md](docs/testing.md).
Betrieb, Sicherung und Wiederanlauf: [docs/operations.md](docs/operations.md).
Migration und bewusst abweichendes Verhalten: [docs/migration.md](docs/migration.md).

## Eigene Python-Pipeline

```python
from leroy.schema import Pipeline, Step

pipeline = Pipeline(
    id="example", name="Example", repository="https://example.org/team/project.git",
    ref="main", concurrency="serial",
    steps=[
        Step(id="checkout", name="Checkout", action="checkout", secrets=["git"]),
        Step(id="verify", name="Verify", needs=["checkout"],
             command=["python", "-m", "unittest", "discover"]),
    ],
)
```

`leroy validate pipeline.py` validiert die Definition lokal. `leroy publish
pipeline.py --url http://127.0.0.1:8088` veröffentlicht sie mit `LEROY_USER` und
`LEROY_PASSWORD` aus der lokalen Prozessumgebung. Python-Dateien sind ausführbarer,
vertrauenswürdiger Code; der Controller akzeptiert ausschließlich das validierte
Datenmodell. Jeder Lauf speichert einen unveränderlichen Definitions-Snapshot.

## Entwicklung und Prüfung

```powershell
.venv/Scripts/python.exe scripts/test_postgres.py
.venv/Scripts/python.exe scripts/test_recovery.py
.venv/Scripts/python.exe scripts/test_execution.py
.venv/Scripts/python.exe scripts/test_execution_edges.py
.venv/Scripts/python.exe scripts/test_children.py
.venv/Scripts/python.exe -m ruff check src scripts tests
cd web
npm.cmd ci
npx.cmd playwright install chromium
npm.cmd run check
npm.cmd run build
npm.cmd run test:e2e
```

Die Docker- und Browser-Tests setzen die laufende lokale Testumgebung voraus.
`test_execution.py` startet Controller und Runner gezielt neu. Den Test nicht
gegen einen Produktions-Stack umkonfigurieren. Browserberichte und Screenshots
liegen in `test-results/`; diese enthalten reale Ausführungsmetadaten und werden
nicht ungeprüft veröffentlicht.
