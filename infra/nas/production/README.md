# NAS-Betriebskonfiguration

Vorbereiteter Stand für zwölf Pipelines, vier Worker-Profile und den Parallelport
`192.168.178.97:8089`. Die Schritte entsprechen den getesteten Definitionen.
Alle automatischen Auslöser sind deaktiviert. Antares bleibt ausgeschlossen.
Das Bundle wurde noch nicht auf dem NAS gestartet.

`pipelines.json` enthält die geprüften Importdefinitionen;
`config/leroy.toml` konfiguriert den Startkatalog. Die zwölf Definitionen müssen
vor dem ersten manuellen Lauf über Leroys Pipeline-API importiert werden, damit
auch die nachgewiesene Herkunft übernommen wird. `RELEASE_COMMIT` hat absichtlich
keinen produktiven Vorgabewert: Der tatsächlich ausgelieferte Commit wird explizit
übergeben beziehungsweise vom CI-Elternlauf übernommen.

Der Runner verwendet den nativen NAS-Docker-Daemon. Das Gitea-Profil kann dadurch
den vorhandenen Gitea-Container adressieren. Das Operations-Profil erhält die
beiden bestehenden Musikverzeichnisse ausschließlich lesend. Graphato verwendet
Host-Netzwerk und `127.0.0.1:5005`, einschließlich BuildKit. Die übrigen Jobs verwenden
`home-lab-stack_default`; Docker-Login, Pull und Push laufen über den nativen Daemon.
Der Registry-Daemon erlaubt derzeit HTTP nur für Loopback-Adressen. Ein Wechsel
auf eine andere Push-Adresse würde eine gesonderte Anpassung benötigen.

Vor einem Start fehlen noch diese konkreten Betriebsmittel:

- `config/controller.env` mit derselben Datenbankkennung wie `config/db_password`;
  Vorlage: `config/controller.env.example`.
- Eigene Controller-, Datenbank- und Runner-Zugänge in den drei Compose-Secret-Dateien.
- Die Produktions-Credentials gemäß `secret-file-mapping.json` und geprüfte
  Host-Schlüssel für die SSH-Ziele. `smartphone-known-hosts` wurde über das
  per USB angeschlossene Gerät bestätigt; Authentifizierung und Schreibrechte
  wurden damit noch nicht geprüft.
- Die geprüften Docker-/Buildx-/Compose-Werkzeuge unter
  `/volume1/docker/leroy-production/tools/`. Die Profilprüfung verwendet bislang
  die getrennt bereitgestellten Werkzeuge aus dem Testpool.

Die beiden Job-Images sind inzwischen im nativen Docker-Store vorhanden. Der
klassische NAS-Store verwendet die Konfigurations-Digests `9e3dd4549026…` und
`207b18644442…`; der Test-Store verwendet OCI-Index-Digests. Die Archiv-Prüfsumme,
Konfigurations-Blobs und Dateisystem-Layer bestätigen identischen Inhalt. Die
vorherigen Job-Aliase bleiben erhalten. Vier temporäre native Profilcontainer
bestehen Docker-/Werkzeugprüfung, Gitea-Containerzugriff, Loopback-Registry sowie
lesenden Zugriff auf beide Musikquellen und den Smartphone-SSH-Port. Das prüft
die Ausführungskontexte; Geschäftsaufgaben und produktive Authentifizierung
wurden dabei nicht ausgeführt.

Die Vorgabewerte der beiden bislang unbenutzten manuellen Jenkins-Jobs stammen
aus ihren mit dem NAS abgeglichenen Inline-Skripten. Damit verwendet Gitea
`gitea-admin@local.lan`, den bestehenden Owner und das ursprüngliche Repository;
Paperless verwendet die bestehende NAS-Adresse. Dies ersetzt frühere Testwerte.

Die getesteten Image-Archive und deren Prüfsummen stehen in
`test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/release-image-restore.json`.
Die tatsächliche Anwendung der Produktionskonfiguration, manuelle produktive
Läufe und die Trigger-Umschaltung bleiben getrennte Schritte. Der aktuelle
Graphato-Gesamtlauf und die offene Jenkins-Soak-Abweichung sind in
`docs/nas-parity.md` dokumentiert.
