# Betrieb

## Konfiguration und Vertrauensgrenzen

`compose.yaml` betreibt Controller, PostgreSQL und einen Runner. Für einen regulären
Linux-Host müssen `.local/leroy.toml` und `.local/runner.toml` auf dessen Repositories,
Netzwerke, Registry und Secret-Dateien zeigen. Die vom lokalen Setup erzeugten
`/sources/...`-Pfade gehören zur Testkonfiguration; auf einem Produktionshost
stattdessen die echten Git-URLs und SCM-Zugangsdaten konfigurieren.

Der Controller erhält `LEROY_DATABASE_URL`, `LEROY_ORIGIN`,
`LEROY_COOKIE_SECURE`, `LEROY_ADMIN_PASSWORD_FILE` und `LEROY_RUNNER_TOKEN_FILE`.
Für Zugriff über einen vorhandenen HTTPS-Proxy die exakte externe Origin setzen
und Secure-Cookies aktivieren. Proxy-Buffering für Server-Sent Events deaktivieren.
PostgreSQL ist im regulären Compose-Stack nicht nach außen veröffentlicht.

Der initiale Administrator wird beim ersten Start angelegt. Die Passwort-Datei
ändert ein bereits existierendes Konto nicht. Konten werden über die lokale CLI
im Controller verwaltet (Zugriff auf den Docker-Host erforderlich):

```sh
docker compose exec controller leroy user list
docker compose exec controller leroy user add alice --role operator
docker compose exec controller leroy user password admin
docker compose exec controller leroy user role alice --role viewer
docker compose exec controller leroy user delete alice
```

Neue Passwörter werden verdeckt abgefragt, nie als Kommandoargument übergeben.
Passwort- und Rollenänderungen widerrufen bestehende Sitzungen einschließlich
laufender Ereignisstreams. Der letzte Administrator kann nicht entfernt oder
herabgestuft werden. Die Bootstrap-Identität `admin` bleibt bestehen, ihr Passwort
kann rotiert werden. SSO und eine grafische Benutzerverwaltung sind nicht enthalten.
Die API unterscheidet `viewer`, `operator` und
`admin`; Veröffentlichungen und automatische Auslöser benötigen `admin`.
Gleichzeitige Passwortprüfungen werden begrenzt. Ist bereits eine Prüfung aktiv,
antwortet die Anmeldung sofort mit HTTP 429 und `Retry-After: 1`, statt eine
Datenbankverbindung wartend zu belegen. Der normale Jobbetrieb bleibt unabhängig.

Ein Runner-Profil bestimmt Image, Docker-Netz, CPU-/RAM-/Prozesslimits,
Dateisystem-Mounts und ob Docker-Zugriff erlaubt ist. Jobs mit Docker-Socket-Zugriff
sind gegenüber diesem Daemon privilegiert: ausschließlich vertrauenswürdige
Repositories auf solchen Runnern ausführen. Für fremde PRs einen eigenen Daemon
ohne Produktionsgeheimnisse verwenden. Ein Container ist keine VM-Sicherheitsgrenze.

```toml
capacity = 2
[profiles.default]
image = "leroy-job:local"
network = "leroy-jobs"
memory = "4g"
memory_reservation = "128m"
memory_swap = "4g"
cpus = 2
docker = false

[profiles.default.secrets.git]
GIT_USER = "/run/credentials/git-user"
GIT_PASSWORD = "/run/credentials/git-token"
```

`memory_reservation` ist eine optionale weiche Docker-Speicherreservierung für
den Jobcontainer. Sie hilft unter Speicherdruck, den Worker samt Heartbeat
ausführbar zu halten; sie ersetzt weder ausreichend RAM/Swap noch die Limits
separater BuildKit-Container. Heartbeats verwenden eine eigene HTTP-Verbindung
und beenden den Versuch bei dauerhaft ausbleibender Bestätigung konservativ vor
dem serverseitigen Lease-Ablauf. Eine abgelaufene Lease wird nicht verlängert
oder automatisch neu gestartet; mögliche externe Wirkungen müssen geprüft werden.

`memory_swap` legt optional das gesamte RAM-plus-Swap-Budget des Jobcontainers
fest. Ist es gleich `memory`, kann dieser Container keinen Swap verwenden
([Docker-Ressourcenlimits](https://docs.docker.com/engine/containers/resource_constraints/)).
Beim NAS-Graphato-Profil betrifft dies den kleinen Python-Steuerprozess samt
SSH-/Docker-Clients; die separaten BuildKit-Container behalten ihre eigenen Limits.
Lease-Diagnosen protokollieren Fehlertypen und Zeitabstände ohne HTTP-Antwortkörper,
URLs oder Exception-Texte, die Zugangsdaten enthalten könnten.

Im isolierten NAS-Stack sind auch Controller, PostgreSQL und Runner gegen
Swap-Auslagerung konfiguriert: RAM-Obergrenzen 256/256/192 MiB,
RAM-plus-Swap-Budgets in gleicher Höhe und weiche Reservierungen 128/128/64 MiB.
Die Konfiguration steht in `infra/nas/compose.yaml`. Die kleinen Steuerdienste
brauchen ihre Reservierung außerhalb des separaten Build-Daemons; dessen
RAM-/Swap-Budget gilt nicht für sie. Ein vierminütiger echter NAS-Job prüft die
API-Verbindung nach dieser Änderung. Die anschließende vollständige
Graphato-Wiederholung beendet alle 21 Web- und acht Qualitätsgruppen ohne
Ausführungsabbruch. Die Ergebnisse hängen vom geprüften Commit ab: Beim
eingefrorenen Master `0ad540dd5780` bestehen im ersten vollständigen Vergleich
unter beiden Engines 20/21 Webgruppen, unter Jenkins 8/8 und unter Leroy 7/8
Qualitätsgruppen. Die offene Rust-Abweichung wird gesondert untersucht;
die Abnahme- und Speicherbelege stehen in `docs/nas-parity.md`.
Der spätere vollständige originale Leroy-Lauf mit acht Ziel-CPUs besteht
Qualität mit 8/8, 1.625 Rust-Tests bei 32 ignorierten Tests und 195 Python-Tests.
Web bleibt bei 20/21; das ursprüngliche Prompt-Ratenlimit im Soak-Test verhindert
weiterhin eine vollständige Release-Abnahme. Die erste Rust-Abweichung bleibt
als historischer Fehler erhalten; eine Ursache ist damit nicht bewiesen.
Die Reservierung garantiert keine Antwortzeit unter
beliebiger Hostlast. Server-Lease und Worker-Bestätigungsgrenze bleiben 90 bzw.
45 Sekunden.

Alle Werte in `secrets` sind Dateipfade auf dem Runner. Der Runner lädt nur die
von einer Pipeline benötigten Secret-Gruppen. Der Worker bindet ihre Werte an die
jeweiligen Schritte und maskiert bekannte Werte im Log, auch über Chunk-Grenzen.
Benötigte Geheimnisse existieren dennoch im Job-Container und sind für dortigen
Code erreichbar. Maskierung ersetzt keine Zugriffstrennung; Artefakte müssen vom
Projekt selbst frei von Geheimnissen gehalten werden.

SSH-Material (`*_FILE`, `*_KEY`, `KNOWN_HOSTS`) wird als Datei eingebunden.
Hostschlüssel müssen über einen vertrauenswürdigen Kanal hinterlegt werden.
Git HTTP verwendet ein temporäres Askpass-Skript; Passwörter gehören weder in
Repository-URLs noch in Pipeline-Parameter. Für private SCM-Abfragen des Schedulers
dieselben Dateireferenzen separat in der Controller-Konfiguration angeben:

```toml
[scm_credentials."home-lab-ci"]
GIT_USER = "/run/credentials/git-user"
GIT_PASSWORD = "/run/credentials/git-token"
```

Alternativ `GIT_SSH_KEY_FILE` und `GIT_KNOWN_HOSTS` angeben. Die Dateien müssen auf
dem betreffenden Container tatsächlich read-only gemountet werden. Abweichende
Credential-IDs aus migrierten Parametern werden nur über explizite
`profiles.<profile>.credential_overrides.<group>.<id>` auf weitere Dateireferenzen
aufgelöst. Unbekannte Referenzen führen zu einem Fehler.

## Ausführungs- und Wiederanlaufmodell

Für wiederkehrende Graphato-Builds einen eigenen dauerhaften BuildKit-Builder
im Runner-Profil benennen, damit Cargo-, pnpm- und Docker-Layer-Caches nach einem
Lauf erhalten bleiben:

```toml
[profiles.graphato.graphato]
builder_name = "leroy-graphato"
```

Ohne diese optionale Einstellung erzeugt jeder Lauf einen eigenen Builder und
entfernt ihn im Cleanup. Ein konfigurierter Name muss mit `leroy-` beginnen;
er bezeichnet ausschließlich Leroys Builder im ausgewählten Docker-Daemon.
Die Ressource `graphato-delivery` verhindert überlappende Auslieferungsläufe.
Ein angehaltener Builder behält seine Cache-Volumes und wird beim nächsten Build
gestartet. Cache-Nutzung ersetzt keine Tests oder Release-Receipts.

Claims werden in PostgreSQL unter Transaktions- und Advisory-Locks vergeben.
`serial`, `parallel`, `replace`, globale Ressourcen und Runner-Kapazität begrenzen
die Ausführung. Queue und Pipeline-Snapshots überleben Controller-Neustarts.
Cron mit Jenkins-artigem `H` verwendet die konfigurierte Zeitzone; SCM-Polling
dedupliziert Revisionen. Verpasste Zeitfenster werden zusammengefasst, damit nach
einem Ausfall nicht zahlreiche Deployments gleichzeitig nachgeholt werden.

Ein Versuch erhält einen eigenen Token und eine 90-Sekunden-Lease. Heartbeats
verlängern sie. Ein kurzzeitiger Controller-Ausfall kann überbrückt werden.
Nach Lease-Verlust wird ein Versuch als unterbrochen markiert und sein Token
widerrufen. Der Runner räumt seine beendeten Container und Workspaces anhand von
Labels auf. Es gibt bewusst keinen automatischen Neustart unklar abgeschlossener
Seiteneffekte. Vor einem manuellen Wiederholen eines Deployments den Zielzustand
prüfen; SSH-Prozesse auf einem entfernten Host können unabhängig weiterlaufen.

Es gibt keine allgemeine Exactly-once-Garantie für externe Aktionen. Projekte
müssen ihre Seiteneffekte idempotent gestalten oder anhand ihrer Release-Receipts
prüfen. Graphato verwendet dafür seine bestehenden Protokolle. Kinder werden
verknüpft; wartende Eltern geben Ausführungskapazität frei. Abbruch wird auf Kinder
übertragen, auch bei Pipeline-Timeout oder verlorenem Eltern-Runner. Kapazität wird
nur freigegeben, wenn sämtliche aktiven Schritte auf Kinder warten. Der Supervisor
überwacht Container ohne einen dauerhaft belegten Thread je Lauf; ein Exit ohne
abgeschlossenen Worker-Bericht wird auch nach Runner-Neustart als Fehler erkannt.
`always` erlaubt Cleanup, ohne Fehler abhängiger Schritte zu verdecken.

Unterpipelines erhalten ausschließlich explizite Parameter, zum Beispiel:

```python
Step(id="verify", name="Abnahme", action="child", timeout=600, options={
    "pipeline": "acceptance", "wait": True,
    "parameters": {"MODE": "full"},
    "parameter_sources": {"REVISION": "commit", "TARGET": "parameters.TARGET"},
})
```

`parameter_sources` unterstützt `commit`, `parameters.NAME` und `values.NAME`
(Schrittergebnisse). `inherit_commit=False` unterbindet die standardmäßige
Übernahme der Checkout-Revision, etwa bei einem anderen Zielrepository.
Wiederholte Übertragung desselben Schrittes ist idempotent; zwei verschiedene
Schritte erzeugen zwei Kindläufe. Das Timeout eines wartenden Schrittes bricht
seinen Kindlauf ab. Zyklische Unterpipeline-Aufrufe und von Eltern gehaltene
Ressourcen dürfen nicht zu wartenden Abhängigkeiten führen.
Leroy weist zyklische Aufrufe und Kindläufe, deren Ressource ein wartender Vorfahr
belegt, vor dem Einreihen mit einer konkreten Fehlermeldung ab. Ein asynchroner
Aufruf ohne Warten darf dieselbe Ressource später nach Freigabe übernehmen.

Beim Abbruch oder Schritt-Timeout beendet der Worker die gesamte Prozessgruppe,
auch wenn deren Hauptprozess bereits beendet ist. Nach 15 Sekunden folgt SIGKILL
für verbliebene Nachkommen; anschließende Cleanup-Schritte können weiterlaufen.
Ein Prozess, der nur seine Ausgabe schließt, wird weiterhin bis zu seinem Ende
oder dem konfigurierten Timeout überwacht.

Logs werden in begrenzten Chunks und anhand bestätigter Byte-Offsets übertragen.
Wiederholte Übertragungen sind idempotent. Ein vollständiger Download ist in der
UI verfügbar; die Live-Konsole lädt nur das letzte begrenzte Fenster. Artefakte
haben SHA-256, Größe und die Zuordnung zum erzeugenden Schritt.
Log-Flush und `fsync` halten eine eigene PostgreSQL-Advisory-Sperre statt der
Laufsperre. So kann derselbe Lauf seine Lease während langsamer Log-I/O erneuern.
Vor Veröffentlichung des bestätigten Offsets wird seine Berechtigung erneut
geprüft. Konkurrierende Wiederholungen bleiben serialisiert; die Dateibereinigung
verschiebt die Löschung, solange ein Schreibvorgang die Log-Sperre hält.
UTF-8-Zeichen über Chunk-Grenzen werden vollständig zusammengesetzt. Die globalen
Aktivitätszähler der Oberfläche kommen aus der gesamten Datenbank und hängen
nicht vom angezeigten Historienausschnitt oder Pipeline-Filter ab.

## Sicherung und Wiederherstellung

Zusammen gehören PostgreSQL, das `/data`-Volume mit Logs/Artefakten sowie die
Konfiguration und separat geschützte Zugangsdaten. Ein PostgreSQL-Dump allein ist
keine vollständige Leroy-Sicherung. Keine Dateikopie eines laufenden PG-Volumes
verwenden.

Für eine einfache konsistente Offline-Sicherung:

1. Automatische Auslöser pausieren und laufende/wartende Versuche abschließen lassen.
2. Runner stoppen, dann Controller stoppen. PostgreSQL weiterlaufen lassen.
3. `pg_dump -U leroy -Fc leroy` im Datenbankcontainer binär in `database.dump`
   schreiben. Unter Windows eine binäre Python-Pipe verwenden, keine textuelle
   PowerShell-Umleitung. `scripts/test_recovery.py` enthält das getestete Verfahren.
4. Das stillstehende Daten-Volume über einen Hilfscontainer read-only mounten und
   mit `tar -C /data -czf ... .` sichern. Konfiguration/Version der Container-Images
   und Secret-Dateien separat verschlüsselt sichern. Prüfsummen erzeugen.
5. Controller und Runner wieder starten. Healthcheck und einen kleinen Lauf prüfen.

Restore zuerst in einen neuen, isolierten Stack durchführen: leere Datenbank mit
passender PostgreSQL-Version erzeugen, `pg_restore --exit-on-error` einspielen,
das dazugehörige Daten-Archiv in ein neues Volume entpacken, Konfiguration und
Zugänge bereitstellen. Zunächst nur den Controller starten und automatische
Auslöser deaktiviert halten. Etwaige gespeicherte aktive Versuche müssen als
unterbrochen behandelt werden. Artefakt-Downloads gegen ihre SHA-256 prüfen,
erst dann Runner zulassen. Niemals einen Restore-Test gegen die laufende
Produktionsdatenbank richten.

Der Datenbankteil einschließlich Neuinstallation der Alembic-Migration und Restore
realer Läufe/Ereignisse wurde mit `scripts/test_recovery.py` geprüft. `scripts/test_backup.py` hat zusätzlich eine gemeinsame Offline-Sicherung in eine
neue Datenbank und ein neues Daten-Volume zurückgespielt: 362 Artefakte einschließlich
SHA-256 und 365 Logs waren konsistent. Der Restore der produktiven Infrastruktur
mit deren Credentials bleibt vor dem tatsächlichen Umstieg zu proben.

## Aufbewahrung, Updates und Grenzen

Die stündliche Aufbewahrung berücksichtigt `retention_runs`, das Mindestalter
`retention_min_age_days` (Standard 7), aktive Läufe sowie ganze Eltern-/Kind- und
Retry-Familien. Zusammenhängende Familien können deshalb länger erhalten bleiben.
Dateilöschungen werden zusammen mit dem Entfernen der DB-Metadaten als dauerhafte
Aufträge gespeichert. Fehlgeschlagene oder unterbrochene Löschungen werden im
nächsten Aufbewahrungslauf erneut versucht. Migration `0002` ergänzt diese Queue; `0003` ergänzt die Zuordnung laufender
Uploads. Bereits vor dem ersten Upload-Byte wird eine Löschabsicht gespeichert.
Sie wird bei erfolgreicher Registrierung atomar entfernt. Abgebrochene Uploads
werden nach Ende beziehungsweise Lease-Verlust ihres Versuchs aufgeräumt; aktive
Uploads bleiben geschützt. Freien Speicher weiterhin überwachen.
Docker-Service-Logs sind auf drei Dateien zu je 20 MB begrenzt.

Updates: sichern, Images bauen, Alembic-Migration ausführen, Controller und Runner
erneuern, Readiness und Regressionstests prüfen. Für den jetzigen Stand ist ein
Controller mit gemeinsamem Dateisystem vorgesehen. Hochverfügbarkeit mehrerer
Controller, OIDC, Webhooks, Prometheus und verteilter Artefaktspeicher sind nicht
implementiert und keine Voraussetzung für die gefundenen Jenkins-Jobs.

### Abbruch und temporäre Testdaten

Ein angeforderter Abbruch beendet gewöhnliche Schritte. Der Worker erneuert seine
Lease während Artefaktübertragung und `always`-Bereinigung weiter; erst nach deren
Abschluss wird der Heartbeat beendet. Jede Bereinigung hat weiterhin ihr eigenes
Zeitlimit. Entzogene Ausführungsberechtigung beendet die Lease-Erneuerung sofort.
Temporäre Antares-Datenbanken und Browser tragen die Laufkennung. Die normale
Bereinigung entfernt zugeordnete Container mit ihren anonymen Volumes, behält
benannte Volumes und den noch berichtenden Worker. Nach einem harten Worker-Verlust
entfernt der Runner nach Bestätigung des endgültigen Status auch diese mit der
Laufkennung markierten Hilfscontainer. Er hält zuerst den Worker an und entfernt
diesen erst nach erfolgreicher Hilfsbereinigung, sodass ein fehlgeschlagener
Versuch erneut aufgeräumt werden kann. Benannte Hilfsvolumes bleiben erhalten.
Externe Auslieferungen auf Zielhosts sind weiterhin gesondert zu prüfen; ein
`interrupted`-Status belegt keine erfolgreiche anwendungsseitige Bereinigung.

## Vorbereitete Umschaltung von Jenkins

Der Vergleichsstand für die neue Graphato-Abnahme ist der am 6. Oktober 2026
beobachtete `master`-Commit `0ad540dd578033d45e4d0c25d89fbe57b32102a4`.
Der vollständige Commit, Git-Tree, vier Jenkinsfile-Prüfsummen und das transportierte
Git-Bundle stehen im [Quellnachweis](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/frozen-master.json).
Der frische Ausführungsvergleich dieses Standes ist abgeschlossen; der zusätzliche
vollständige Gruppenvergleich ist ebenfalls abgeschlossen. Beide Engines
führen alle 29 Gruppen aus. Web besteht jeweils 20/21; Qualität besteht bei
Jenkins mit 8/8 und bei Leroy mit 7/8. Die Retry-Anzahl-Assertion bleibt eine
ungeklärte Abweichung. Diese Vorbereitung ist keine Freigabe.
Der zusätzliche vollständige originale Leroy-Lauf besteht inzwischen 28/29
Gruppen, einschließlich aller Qualitätsgruppen. Die unveränderte Soak-Gruppe
scheitert erneut. Das getrennte Produktionsbundle unter `infra/nas/production`
enthält geprüfte native NAS-Kontexte und deaktivierte Trigger; Credentials,
Schreibrechte und produktive Geschäftsaufgaben sind noch nicht validiert.

Die [Zuordnung der produktiven Jenkins-Konfiguration](../test-results/nas-parity/followup/cutover-preparation/jenkins-mapping.json)
erfasst alle 13 Jobs, Skript- und Konfigurationsprüfsummen, Parameter,
Credential-IDs und Trigger. Die fünf Inline-Skripte sind unverändert.
Secret-Werte bleiben in Jenkins und werden nicht in diesen Nachweis exportiert.
Für die Umschaltung zählen zwölf Jobs; Antares bleibt ausgenommen.

| Einstieg | Auslöser nach Freigabe | Folgeläufe |
| --- | --- | --- |
| `graphato-ci` | SCM-Polling alle zwei Minuten auf `master` | Release-Abnahme mit genau diesem Commit, anschließend Web und Qualität |
| `home-lab-ci` | SCM-Polling alle zwei Minuten | Nur tatsächlich geänderte Image-Kontexte bauen und veröffentlichen |
| `nikicas-hub-ci` | SCM-Polling alle zwei Minuten | Hub-Deployment bleibt ein gesonderter manueller Einstieg |
| `music-library-sync-smartphone` | `H 3 * * *`, Europe/Berlin | Ein geplanter Synchronisationslauf pro Tag |
| Übrige Bootstrap-, Gitea-, Paperless- und Deploy-Jobs | Manuell | Parameter und Credential-Selektoren aus der erfassten Konfiguration |

Leroys stabile Hash-Minute für `H` kann von Jenkins abweichen; das tägliche
Zeitfenster bleibt gleich. Diese Auslöser sind im Teststack deaktiviert.
Die produktiven Ziele und Credentials werden erst in einer gesonderten, zunächst
deaktivierten Betriebs-Konfiguration zugeordnet. Test-URLs, Test-Registry,
VM-Tunnel und Testzugänge dürfen dort nicht als produktive Defaults verbleiben.
Der Controller und sämtliche CI-Worker laufen auf dem NAS. Die isolierte Linux-VM
ist ausschließlich ein Anwendungsziel für die Abnahme.

Vor Aktivierung werden die getesteten Image-Identitäten, Profile, Ressourcen und
Konfiguration festgeschrieben sowie Sicherung, Wiederherstellung und Wiederanlauf
mit diesem Stand geprüft. Danach gilt folgende Reihenfolge:

1. Die gewünschte Betriebs-Konfiguration und die Abnahmeergebnisse prüfen und
   die tatsächliche Umschaltung freigeben.
2. Nur die zwölf zu ersetzenden Jenkins-Einstiege deaktivieren, ihre aktiven Läufe
   und Warteschlange abschließen lassen und alle bisherigen Einstellungen erhalten.
   Antares wird durch diesen Ablauf nicht umgestellt.
3. Die SCM-Ausgangsrevisionen vor der ersten Aktivierung in Leroy prüfen.
   Die zuletzt durch Jenkins ausgelieferte Revision darf nicht allein durch das
   Einschalten ein zweites Mal veröffentlicht werden.
4. Leroys manuelle Einstiege und danach die drei SCM-Auslöser und den Musik-Zeitplan
   aktivieren. Dieselben Ziele dürfen nicht gleichzeitig durch beide Systeme
   automatisiert verändert werden.
5. Die ersten echten Läufe anhand von Commit, Release-Identität, Artefakten,
   Dienstgesundheit und Laufhierarchie prüfen.

Das Image-Pinning des Teststacks verwendet für die Infrastrukturprüfung eine
gesonderte `compose.release.json` mit den tatsächlich getesteten lokalen Image-IDs.
Für eine spätere Neuerstellung dieses Stacks sind beide Dateien anzugeben:
`docker compose -f compose.yaml -f compose.release.json up -d`.
Die Datei wird gemeinsam mit der Konfiguration verschlüsselt gesichert.
Lokale Image-IDs ersetzen keine Image-Sicherung oder Verfügbarkeit in einer Registry.
Die abschließende Image-Abnahme archiviert deshalb die getesteten Service- und
Job-Images separat unter `release-images/<Graphato-Commit>/` im eigenen NAS-Testroot.
Die Archive werden anhand ihrer SHA-256-Prüfsummen in jeweils einen leeren
Docker-Daemon mit `network_mode=none` und demselben Image-Speichermodell wie die
Quelle geladen: klassischer Speicher für NAS-Service-Images, containerd für die
Worker-Images mit OCI-Indizes. Danach müssen die ursprünglichen Image-IDs und
RootFS-Layer exakt stimmen. Der erste Versuch in ausschließlich klassischem
Speicher ist als Fehler erhalten; er kann die OCI-Index-Identitäten nicht prüfen.
Es werden keine Anwendungscontainer daraus gestartet. Jeder temporäre Daemon
und sein eigenes Volume werden nach der Prüfung entfernt.
Die CI-Datensicherung umfasst Datenbank, Logs, Artefakte und Konfiguration;
sie behauptet keine vollständige Sicherung des verschachtelten Docker-Daemons
oder der Anwendungsdaten auf den Auslieferungszielen.

Nach dem anschließenden vollständigen Stack-Neustart ist je ein kurzer echter
Job in allen vier Runner-Profilen erfolgreich ausgeführt. Die Prüfung kontrolliert die
registrierte Image-ID, die tatsächlichen Ressourcenlimits und einen per SHA-256
verifizierten Artefaktdownload. Die vorherige Diagnose-Pipeline wird danach
wiederhergestellt. Diese Jobs prüfen den CI-Betrieb und liefern keine Anwendung aus.

`finish_frozen_master_nas_acceptance.py --phase operations --infrastructure-only`
erlaubt diese unabhängigen Betriebsprüfungen auch bei roten Anwendungsprüfungen.
Voraussetzung bleiben erfolgreiche unveränderte Bootstrap-/CI-Auslieferungen,
vollständig abgeschlossene Prüfläufe beider Engines vom gleichen Snapshot und
gesunde Zieldienste. Unterbrochene oder unvollständige Ausführungen werden
abgelehnt. Der Bericht enthält die fehlgeschlagenen Anwendungspipelines weiterhin
und setzt `production_replacement_ready` ausdrücklich nicht. Sechs gezielte Tests
prüfen diese Abgrenzung. Die abschließenden Betriebsprüfungen auf dem NAS
bestehen: sieben Images mit identischen IDs/Layern wiederhergestellt, vollständiger
Teststack-Neustart, vier reale Profile-Jobs und Rücksicherung sämtlicher
Datenbankzeilen, 537 Artefakte, 251 Logs sowie der geschützten Konfiguration.
Der wiederhergestellte Controller ist bereit.
[Betriebsnachweis](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/final-operations-acceptance.json).

Der vollständige Teststack-Neustart setzt einen tatsächlich ruhenden
verschachtelten Docker-Daemon voraus. Nach abgeschlossenen Läufen können die
zwei bewusst beibehaltenen Graphato-BuildKit-Container noch laufen. Vor der
Wartung sind die fehlende CI-Warteschlange, die konkreten Container-Identitäten
und der gestoppte Test-Jenkins zu prüfen; anschließend werden nur diese Builder
angehalten. Ihre Container und Cache-Volumes bleiben erhalten. Der frühere
Neustart-Versuch hat diese Voraussetzung vor jeder Dienstunterbrechung abgelehnt.
Ein neuer Nachweis verwendet eine eigene `--operations-attempt`-Kennung; die
fehlgeschlagenen Versuche werden nicht gelöscht oder überschrieben.

`scripts/prepare_scm_baseline.py` bereitet diesen SCM-Ausgangspunkt standardmäßig
als schreibfreie Vorschau vor. Es akzeptiert ausschließlich den Commit des
letzten tatsächlich erfolgreichen Leroy-Laufs einer deaktivierten SCM-Pipeline
und lehnt aktive Läufe ab. Erst `--apply` setzt `last_revision`; dabei entstehen
weder ein erfolgreicher Lauf noch ein Deployment. Die Änderung erhält einen
Audit-Eintrag und ist idempotent. Sie läuft als vertrauenswürdiges Betriebswerkzeug
im Controller. Neun Tests mit echter PostgreSQL-Datenbank prüfen insbesondere
die Ablehnung ungetesteter, fehlgeschlagener oder ungültiger Revisionen sowie
Git-Repositories mit SHA-256-Objekt-IDs.
Ein erfolgreicher CI-Einstieg kann nach dem ursprünglichen Jenkins-Vertrag
fehlgeschlagene nachgelagerte Release-Prüfungen haben. Das Setzen des SCM-
Ausgangspunkts bewertet diese Anwendungsprüfungen nicht; deren eigene Quittungen
gehören weiterhin zur Freigabe.

Bei Rückkehr zu Jenkins zuerst Leroys Einstiege deaktivieren und gestartete
Seiteneffekte anhand ihres tatsächlichen Zielzustands prüfen. Anschließend die
erhaltenen Jenkins-Einstellungen wieder aktivieren. Ein Zurücksetzen von
CI-Triggern setzt keine ausgelieferte Anwendung oder deren Daten zurück.
Anwendungs-Rollbacks verwenden die vorige geprüfte Image-/Release-Identität;
bei inkompatiblen Datenänderungen gehört die passende Anwendungssicherung dazu.

### Bewertung der Hub-Abweichung

Der belegte Test verwendet für beide Engines dasselbe App-Image und dieselbe
Compose-Datei. Auf dem frischen Host hat der Deploy-Benutzer UID 1001, das
Image läuft mit UID 1000. Jenkins meldet Erfolg trotz ungesunder Anwendung;
Leroy richtet die drei beschreibbaren Bind-Verzeichnisse auf UID 1000,
Deploy-Gruppe und Modus 2770 aus und wartet bis zu 180 Sekunden auf die Gesundheit
des App-Containers. Der korrigierte Testdienst ist gesund und startet nicht neu.

Die Rechtekorrektur ist Teil des Bootstrap-Jobs und verändert nur diese drei
Verzeichnisse, nicht rekursiv vorhandene Dateien. Sie ist keine Migration
bestehender Daten. Auf einem bestehenden Ziel sind Image-UID, Datei-Eigentümer
und Schreibzugriff deshalb gesondert zu prüfen, bevor Bootstrap angewendet wird.
Eine Rückkehr zu Jenkins braucht keine Rücksetzung auf die früheren unpassenden
Verzeichnisrechte.

Wenn der Healthcheck scheitert, bleibt Leroy fehlgeschlagen; es erfolgt kein
automatisches Zurückrollen des Images oder der Daten. Das übertragene Image-Archiv
bleibt beim Fehler erhalten, und es gibt kein globales Image-Pruning.
Das letzte gesunde Image und die zugehörige Konfiguration sind für eine gezielte
Rücksetzung zu erhalten. Der Deploy-Parameter `DRY_RUN` verhindert das Starten
oder Aktualisieren von Containern, überträgt jedoch Compose- und Env-Dateien;
er ist deshalb keine schreibfreie Produktionsprüfung.
