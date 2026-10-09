# Lokale Linux-VM für die isolierte Abnahme

Am 3. Oktober 2026 auf diesem Windows-System eingerichtet und geprüft.

Die VM verwendet Ubuntu 24.04.5 LTS, den eigenen Kernel `6.8.0-142-generic`
und Docker Engine 29.8.0 gemäß Graphatos geprüften Paket-Pins. AppArmor ist aktiviert und erzwingt seine Regeln.
Auch Graphatos unverändertes `graphato-server`-Profil wurde geladen und befindet
sich im Enforce-Modus. Host-Bootstrap, Build und Deployment haben ihre vollständigen
Aufgaben bereits bestanden. Der aktuelle Stand der anschließenden Testsuiten steht
in [implementation.md](implementation.md).

## Aufbau und Isolation

```text
Windows 11 / vorhandenes Docker Desktop mit WSL 2
  └─ eigener Compose-Stack leroy-vm
      └─ QEMU/KVM (Container leroy-linux-vm, Zugriff nur auf /dev/kvm)
          └─ Ubuntu-VM mit eigenem Kernel und AppArmor
              └─ eigener Docker-Daemon
```

QEMU läuft als Verwaltungsprozess in einem Container. Ubuntu selbst ist eine
vollständige hardwarebeschleunigte VM mit eigenem Kernel. Die vorhandene
KVM-Unterstützung wurde durch eine erfolgreiche VM-Erzeugung und im Gast durch
`systemd-detect-virt` nachgewiesen. Windows-Features, die bestehende WSL-Distribution
und die laufende Leroy-Testumgebung wurden dafür nicht umkonfiguriert.

- 4 virtuelle CPUs, 64 GiB dynamische virtuelle Systemplatte; im Abnahmemodus
  10 GiB Gast-RAM und 11 GiB Containerlimit einschließlich Overhead.
  Ohne Test-Erweiterung gelten 4 GiB Gast-RAM und 5 GiB Containerlimit.
- Eigene Platte und UEFI-Variablen in einem Docker-Volume. Die ursprüngliche
  Platte `leroy-vm_disk` bleibt erhalten; die frische Abnahme verwendet
  `leroy-vm_acceptance-9c69406dbcbf` (Auswahl in `.local/vm/fresh.compose.yaml`).
- Keine Windows-Dateifreigabe im Gast, kein äußerer Docker-Socket im QEMU-Container.
- Eigener Admin-SSH-Schlüssel; Passwortanmeldung ist deaktiviert. Für Graphatos
  Original-Bootstrap wird ein separater Testschlüssel hinterlegt; Deployments
  verwenden einen eigenen Testschlüssel mit dem originalen Forced-Command-Receiver.
- Der SSH-Hostschlüssel wird vor dem ersten Boot erzeugt und lokal fest hinterlegt.
- Öffentliches Internet bleibt für Paket- und Image-Downloads erreichbar.
  Ausgehende Verbindungen in RFC1918-Netze, Link-Local und CGNAT-Netze werden
  außerhalb des Gasts im Netzwerk-Namespace des QEMU-Containers abgewiesen.
- Ausschließlich Loopback-Portfreigaben auf Windows: `2224 → SSH`,
  `8089 → Gast-Port 80`, `8444 → Gast-Port 443`. Die Webports führen zur
  Graphato-Testinstallation mit ausschließlich im Gast vertrauten Testzertifikaten.

Die VM kann keine Verbindungen zu produktiven LAN-Zielen aufbauen. Die explizite
Test-Erweiterung erlaubt eingehendes SSH aus dem Leroy-Testnetz; die weiteren
Testdienste laufen innerhalb des Gasts. Nur Graphatos Ziel wurde auf diese VM
umgestellt. Die anderen Pipelines behalten ihre separaten Container-Testziele.

## Verwendung

Im Leroy-Verzeichnis:

```powershell
.venv/Scripts/python.exe scripts/vm.py status
.venv/Scripts/python.exe scripts/vm.py ssh
.venv/Scripts/python.exe scripts/vm.py ssh 'sudo docker ps'
.venv/Scripts/python.exe scripts/vm.py console
.venv/Scripts/python.exe scripts/vm.py stop
.venv/Scripts/python.exe scripts/vm.py start
```

`stop` stoppt zuerst den Graphato-Testdienst über die gepinnte SSH-Verbindung
und fordert anschließend `systemctl poweroff` an. Scheitert das Stoppen des
Dienstes, bleibt die VM laufen. Ist SSH nicht erreichbar, bleibt QMP/ACPI als
Fallback. Nach 210 Sekunden ohne Abschluss wird QEMU beendet; Compose lässt
insgesamt 240 Sekunden zu. `/vm/shutdown.json` dokumentiert ausdrücklich, ob
eine erzwungene Beendigung nötig war; der Neustarttest akzeptiert diese nicht.
Für normale Abschaltungen daher dieses Kommando verwenden. Docker Desktop muss
für den Betrieb laufen; die VM startet nicht als separater Windows-Systemdienst.

Zugriff: `leroy-admin@127.0.0.1:2224`, Schlüssel `.local/vm/id_ed25519`.
Konfiguration, SSH-Schlüssel und Image-Cache liegen unter `.local/vm/` und werden
nicht versioniert. Das Festplatten-Volume enthält ebenfalls Test-Zugangsdaten.

Bei gestoppter VM kann ein weiterer interner Disk-Snapshot angelegt werden:

```powershell
.venv/Scripts/python.exe scripts/vm.py stop
.venv/Scripts/python.exe scripts/vm.py snapshot before-graphato
.venv/Scripts/python.exe scripts/vm.py start
```

Die Snapshot-Namen des ausgeführten Neustarttests stehen in
`test-results/vm/restart.json`. Disk-Snapshots liegen im selben Volume und sind
kein externes Backup. Das Volume deshalb nicht mit `docker compose down -v` löschen.

## Wiederholbare Einrichtung und Nachweise

```powershell
.venv/Scripts/python.exe scripts/setup_vm.py
.venv/Scripts/python.exe scripts/test_vm.py
.venv/Scripts/python.exe scripts/test_vm_restart.py
```

Die Einrichtung bewahrt vorhandene Schlüssel, Seed-Daten und Systemplatten.
Das offizielle Ubuntu-Cloud-Image wird per HTTPS heruntergeladen und vor Nutzung
gegen die ebenfalls über HTTPS bezogene SHA-256-Liste geprüft. URL, Datum und
Prüfsumme bleiben in `.local/vm/config/image.json` erhalten. Ein abweichendes
Basisimage ersetzt niemals stillschweigend eine bestehende VM.

`test_vm.py` prüft den eigenen Kernel, KVM, AppArmor und Docker, einen tatsächlich
verweigerten Dateizugriff, Graphatos Originalprofil, Loopback-Bindings, fehlenden
Host-Docker-Socket und die Netzsperre. `test_vm_restart.py` prüft geordnetes
Herunterfahren, einen Offline-Snapshot sowie eine neue Boot-ID, erhaltene Daten
und AppArmor/Docker nach erneutem Start. Bei installiertem Graphato verlangt er
zusätzlich aktive Testdienste und HTTPS 200 vor und nach dem Neustart, ohne
zwischenzeitliche Freigabe einer Runtime-Sperre. Ergebnisse: `test-results/vm/`.
Für die abschließende Abnahme verlangt `test_vm_restart.py --require-application`
ausdrücklich eine vorhandene Anwendung. Die Erkennung erfolgt mit Root-Rechten,
weil das originale Hardening `/opt/graphato` für den Admin-Benutzer nicht lesbar macht.

Offizielle Grundlagen: [QEMU/KVM](https://www.qemu.org/docs/master/system/introduction.html),
[Ubuntu-Cloud-Images](https://cloud-images.ubuntu.com/releases/noble/release/),
[NoCloud-Provisionierung](https://docs.cloud-init.io/en/latest/reference/datasources/nocloud.html)
und [Docker auf Ubuntu](https://docs.docker.com/engine/install/ubuntu/).

## Vollständige Graphato-Abnahme

Die Test-Erweiterung `compose.vm.test.yaml` gibt der VM 10 GiB RAM (11 GiB
Containerlimit) und die Adresse `10.231.88.11` im bestehenden isolierten
Leroy-Testnetz. Der SSH-Endpunkt für Jobs heißt `graphato-vm:2222`; der Gast
empfängt weiterhin auf Port 22. Ausgehende private Verbindungen bleiben gesperrt.
Nach `setup_graphato_vm.py` verwendet `vm.py` diese Erweiterung automatisch.

```powershell
.venv/Scripts/python.exe scripts/setup_graphato_vm.py
.venv/Scripts/python.exe scripts/vm.py start
.venv/Scripts/python.exe scripts/setup_vm_acme.py
.venv/Scripts/python.exe scripts/setup_vm_lifecycle.py
docker compose -f compose.yaml -f compose.test.yaml restart runner
.venv/Scripts/python.exe scripts/test_graphato_vm.py
```

Die ursprüngliche Graphato-Hostpolicy verlangt eine global klassifizierte
Hostadresse und den fest eingetragenen Let's-Encrypt-Endpunkt. Die VM bildet
diese externe Infrastruktur lokal nach: `graphato.test` zeigt ausschließlich im
Gast auf dessen Dummy-Interface `11.254.254.254/32`. Die QEMU-Firewall blockiert
diese Adresse zusätzlich nach außen. Die ACME-Adresse wird ausschließlich im
Gast auf den dortigen [Pebble-Testserver](https://github.com/letsencrypt/pebble)
aufgelöst. Ein kleiner HTTPS-Dienst leitet dessen Directory-Anfrage weiter.
Pebble führt echte Domain-Challenges und Zertifikatsausstellung aus;
`PEBBLE_VA_ALWAYS_VALID` ist nicht gesetzt. Die generierten Test-CAs werden nur
im disposable Gast vertraut, niemals im Windows-Truststore.

Damit bleiben DNS-Zuordnung, TLS-Verifikation, HTTPS-Weiterleitung, API-Auth,
AppArmor und Firewallprüfungen der unveränderten Originalskripte aktiv. Diese
Abnahme prüft die automatisierten Abläufe, keine reale öffentliche DNS-Zone
oder Zertifikatsausstellung durch Let's Encrypt. Die lokale Testinfrastruktur
wird durch `leroy-test-acme.service` nach Neustarts wiederhergestellt. Alte
Test-Issuer-Zertifikate bleiben für bereits ausgestellte Zertifikate im Gast
vertraut, da Pebble seinen Ausstellerschlüssel bei jedem Start neu erzeugt.

`leroy-test-graphato.service` startet das Original-Compose-Projekt und stoppt es
beim Herunterfahren vor Docker. Damit bleibt PostgreSQL für Graphatos geordneten
Runtime-Shutdown verfügbar; die ursprüngliche Stop-Frist von 120 Sekunden bleibt
erhalten. Die bisherigen Abschaltungen mit dem alten VM-Wrapper mussten QEMU
hart beenden und hinterließen die absichtlich persistente Runtime-Owner-Sperre.
Ein bloßer Wechsel der Boot-ID war deshalb kein Nachweis eines geordneten
Neustarts. Nach einer solchen Beendigung verlangt Graphato seine explizite
Recovery-Prozedur. Eine automatische Recovery gehört nicht zur Unit: Unklare
Abstürze bleiben gesperrt. Der korrigierte Neustarttest wurde nach der vollständigen
Release-Abnahme mit `--require-application` erfolgreich ausgeführt: `forced: false`,
QEMU-Exit-Code 0, neue Boot-ID, persistente Daten, AppArmor sowie beide Testdienste
aktiv und HTTPS 200 vor/nach dem Boot. Eine manuelle Recovery war nicht nötig.
Der Nachweis steht in `test-results/vm/restart.json` und `docs/acceptance.json`.

Die Einrichtung gleicht Docker mit den Pins im geprüften Graphato-Commit ab.
Ein bereits aktives Release verhindert einen automatischen Versionswechsel.
Nachweise einschließlich aller Kind- und Enkel-Pipelines stehen in
`test-results/vm/graphato.json` (Originalstand),
`test-results/vm/graphato-validation.json` (Korrekturstand) und
`test-results/migrations/`.

## Frische unabhängige Wiederholung

`scripts/provision_fresh_vm.py` hält aktive Graphato-Jobs an dieser Grenze zurück,
stoppt die Test-VM und wählt eine neu angelegte virtuelle Festplatte. Die bisherige
Festplatte wird nicht gelöscht oder verändert. Die lokale Datei
`.local/vm/fresh.compose.yaml` wählt das neue Volume für `vm.py`; die Zuordnung,
der erhaltene alte Name und die Ubuntu-Prüfsumme stehen unter
`test-results/vm/fresh-provision.json`. `prepare_fresh_acceptance.py` provisioniert
den neuen Gast und führt die originalen Inspect-/Apply-Bootstrapjobs aus.
`test_graphato_validation.py --fresh-host` prüft anschließend die erste vollständige
Auslieferung samt aller Folgepipelines. Diese Option setzt ausdrücklich voraus,
dass noch kein aktives Graphato-Release existiert.

Dieser Weg wurde gewählt, weil die Werkzeug-Freigabeprüfung die manuelle Recovery
der alten Runtime-Sperre auch nach Nutzerbestätigung blockierte. Die neue Instanz
hat eine neue Datenbank; die alte Sperre wird weder verändert noch umgangen.
