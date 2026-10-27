# NAS-Nachanalyse vom 14. Oktober 2026

Die anschließende gezielte Rust-Ressourcenqualifikation ist in
[nas-rust-memory.md](nas-rust-memory.md) beschrieben.

Die vollständige Graphato-Abnahme bleibt offen. Die Nachanalyse behebt einen
nachgewiesenen Fehler in der Prozessumgebung und einen Fehler im Abnahmehelfer.
Sie ersetzt keinen fehlgeschlagenen Originaljob und gibt Leroy nicht für die
Produktion frei. Der eingefrorene Graphato-Commit bleibt
`0ad540dd578033d45e4d0c25d89fbe57b32102a4`; sein Checkout ist unverändert.

## Nachgewiesene Abfolge beim Laufzeitabbruch

Die ausgeschalteten QCOW2-Datenträger beider Versuche wurden mit einem getrennt
bereitgestellten Dissect-Werkzeug gelesen. Es gab keinen VM-Start, kein Mounten,
keine Journal-Wiederholung und keine Änderung ihrer Dateigröße oder mtime.
Die Werkzeugversionen und SHA256-Werte liegen im privaten Diagnoseverzeichnis;
Dissect wird keine Laufzeitabhängigkeit von Leroy.

Die Docker-Logs der Graphato-Datenbank zeigen eine zuvor nicht erfasste interne
Neuinitialisierung. Der PostgreSQL-Container selbst bleibt dabei gestartet;
sein Docker-Neustartzähler ist deshalb kein ausreichender Nachweis.

| Ereignis | Leroy, UTC | Jenkins, UTC |
| --- | --- | --- |
| PostgreSQL: unbekannter Kindprozess endet mit Code 2 | 13.10. 20:13:48.226 | 13.10. 22:58:00.062 |
| PostgreSQL beendet andere Datenbankprozesse und initialisiert neu | unmittelbar danach | unmittelbar danach |
| Graphato meldet Verlust seiner PostgreSQL-Laufzeit-Lease | 20:13:54.363 | 22:58:01.284 |
| Supervisor behält die Laufzeitsperre zurück | 20:13:54.376 | 22:58:01.307 |

Die PostgreSQL-Konfiguration des erhaltenen Zielsystems verwendet keinen
Init-Prozess. PostgreSQL läuft als PID 1. Sein unveränderter
[Postmaster-Code](https://github.com/postgres/postgres/blob/REL_18_STABLE/src/backend/postmaster/postmaster.c)
behandelt den Exit eines unbekannten Kindprozesses mit Code 2 als Absturz und
leitet die beobachtete Neuinitialisierung ein. Welcher konkrete Prozess im
Originalversuch verwaist ist, bleibt unbelegt. Die Shell-Gesundheitsprüfung ist
ein Kandidat; sie wird nicht als bewiesener Verursacher bezeichnet.

Graphatos Originalcode prüft die Eigentümerverbindung alle drei Sekunden mit
einer zusätzlichen Abfragefrist von drei Sekunden. Aus den neuen Belegen folgt
kein Anlass, diese Fristen zu verlängern: Die Datenbankverbindung wurde durch
eine tatsächliche Neuinitialisierung unterbrochen. Der Maintenance-Container
teilt den PID-Namensraum des Servers. Sein Exit 137 ist daher kein unabhängiger
Nachweis eines Speicherabsturzes. Die Kontrollversuche verändern weder diese
Fristen noch Graphatos Wiederherstellungsregeln.

## Kontrollversuch und umgesetzte Absicherung

Zwei kleine PostgreSQL-Container liefen nacheinander im eigenen NAS-Testdaemon,
mit getrennten flüchtigen Daten und ohne veröffentlichte Ports. Das verwendete
Image ist das erhaltene PostgreSQL 18.6, gebunden an
`postgres@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2`.
Plattform und sämtliche RootFS-Digests stimmen mit dem Original-Zielsystem
überein. Ein absichtlich verwaister Shell-Kindprozess endet jeweils mit Code 2.

| Kontrollfall | Unbekannter Kindprozess im PostgreSQL-Log | Neuinitialisierung | SQL-Datensatz erhalten |
| --- | --- | --- | --- |
| ohne Docker-Init | 1 | 1 | ja |
| mit Docker-Init | 0 | 0 | ja |

Beide Container wurden entfernt. Ein produktiver Jenkins-Lauf wurde während
dieser Diagnose an den erfassten Grenzen nicht festgestellt; sämtliche 13
Jobhistorien wurden berücksichtigt. Der Live-Queue-Zustand wird nicht behauptet.

Leroys lokale, NAS-Test- und Produktionsvorlagen enthalten jetzt `init: true`
für PostgreSQL. Auf der **isolierten Leroy-NAS-Testdatenbank** ist die Änderung
angewendet und dauerhaft in deren Compose-Override gespeichert. Vorher wurde
eine geschützte Datenbanksicherung erstellt. Image, Datenträger, Ressourcen,
Umgebung und feste IP bleiben gleich. Die ursprünglichen 152 Läufe, 433 Schritte,
592 Artefakte und 16 Pipeline-Einträge sind erhalten. Controller, Runner und
Testdaemon behalten IDs und Prozesse; die API ist danach wieder bereit.
Die Verifikation wurde nach einem ausschließlich durch die Reihenfolge der
Umgebungsvariablen ausgelösten Vergleichsfehler ohne weitere Neuerstellung
abgeschlossen. Die Wiederaufnahmebelege bleiben erhalten.

Für Graphatos **nächste isolierte Vergleichsbaseline** ist die entsprechende
separate Compose-Konfiguration vorbereitet:
`infra/vm/postgres-init.override.yaml`. Der Vollvergleich unterstützt
`--postgres-init`. Die optionale Einrichtung wird vor dem ersten Start der vier
Baseline-Dienste erzwungen und in einer neuen Vergleichskennung protokolliert.
Das tatsächlich gestartete PostgreSQL muss anschließend Init aktiviert haben.
Die beiden Engines erhalten dieselbe Einstellung. Die neue Baseline wurde
anschließend für eine ursprüngliche Frontend-Gruppe gestartet und geprüft;
ein neues vollständiges Vergleichspaar fehlt. Die ursprünglichen
Release-Dateien und die beiden alten Vergleichsdatenträger werden nicht verändert.
Produktive Graphato- oder Jenkins-Dienste wurden nicht umkonfiguriert.

## Vergleich der erzeugten Test-Images

Beide aufgezeichneten Image-Identitäten wurden über ihre geprüften OCI-Deskriptoren
bis zur Konfiguration aufgelöst. Die Ausführungskonfiguration ist gleich; von
23 Dateisystemschichten unterscheiden sich 21 in ihren Diff-Digests. Eine reine
Abweichung des obersten Erstellungsdatums ist damit keine ausreichende Erklärung.
Die Digest-Unterschiede beweisen für sich allein noch keine unterschiedlichen
Programmdateien: Schichtarchive enthalten ebenfalls Metadaten.

Über die jeweils zugehörige Containerd-Snapshot-Kette wurden folgende Dateien
zusätzlich gelesen und byteweise über SHA256 verglichen:

- Debian-Paketstatus mit identischen 264 installierten Paketen und Versionen;
- npm- und pnpm-Paketmanifest sowie pnpm-Einstiegspunkt;
- Rust-Toolchain-Manifest und rustc-Binärdatei;
- Cargo.toml, Cargo.lock und rust-toolchain.toml aus dem Build-Verzeichnis.

Alle neun Dateihashes stimmen überein. Die Browser-Worker wurden zusätzlich über
die erhaltenen Containerd-Imageverzeichnisse aufgelöst. Sie besitzen jeweils
16 Schichten und dieselbe Ausführungskonfiguration. Die ersten acht Schichten
stimmen zwischen beiden alten Versuchen und dem neuen Frontend-Versuch überein;
die späteren Installations-, Quell- und Prüfschichten unterscheiden sich.
Die ursprünglichen Tag-Identitäten bleiben mit ihren Metadatendateien gebunden.
Das ist eine konkrete Eingrenzung und
kein Nachweis vollständiger Image-Inhaltsgleichheit. Für einen endgültigen
Vergleich bleibt eine gemeinsame, gebundene Werkzeug-/Cache-Baseline oder eine
vollständige Inhaltsprüfung erforderlich. Es wird kein Paket- oder
Toolchain-Versionsunterschied als Ursache der bisherigen Fehler behauptet.

## Ressourcen und übrige offene Punkte

Die nachträglich gelesenen Gast-Cache-Protokolle enthalten 152 bzw. 155 Messpunkte.
Die letzten erhaltenen Werte weisen nach Cache-Bereinigung noch etwa 3,0 bzw.
3,6 GiB freie Gastseiten aus. Trotzdem erreichte der NAS-Host seine unveränderte
Swap-Reserve. Diese Werte stammen nicht exakt aus demselben Messzeitpunkt.
Vor einem erneuten Volllauf muss die Zuordnung zwischen freien Gastseiten,
QEMU-Speicher und tatsächlich belegtem Host-Swap geprüft werden. Eine weitere
Wiederholung mit demselben 10-GiB-Profil ist dadurch nicht qualifiziert.
Host-Schutzgrenzen, Gast-Swap und ursprüngliche Fixture-Limits wurden nicht
geändert. Alle CI-Controller und Worker bleiben entsprechend der Nutzervorgabe
auf dem NAS; die zusätzliche KVM-Zielumgebung wird gesondert bewertet.

Der gemeinsame Frontend-Fehler ist an derselben Originalassertion gebunden:
`chat-presentation.test.mjs:24`, `expect(turn).toBeFocused()`, erwarteter Fokus,
tatsächlich inaktiv, fünf Sekunden Frist. In beiden Läufen bestehen 97/98 Fälle.
Die anschließende Einzelanalyse weist einen verzögerten Fokuswechsel des Editors
nach; die ursprüngliche Prüfung wird nicht abgeschwächt. Ein etwaiger
Graphato-Patch ist separat zu bewerten.

Die sechs vorübergehenden Leroy-Lease-Fehler bleiben dokumentiert. Die erhaltenen
Logs enthalten keinen Lease-Stopp in diesen beiden Vollversuchen. Die Logs von
Leroys eigener PostgreSQL-Instanz enthalten im begrenzten lesbaren Zeitraum
keine entsprechende Neuinitialisierung; eine gemeinsame Ursache wird nicht
behauptet. Der einzelne Docker-Hub-TLS-Fehler ist weiterhin keine nachgewiesene
dauerhafte Leroy-Abweichung und die 21 nicht ausgeführten Core-Fälle bleiben offen.

## Abnahmehelfer und nächste Durchführung

Der Helfer erfasst nach einem nachgewiesenen Stopp der eigenen VM jetzt eine
explizite `*-target-after-unavailable.json`, beendet die Belegsammlung und
qualifiziert die Produktionsbeobachtung. Er startet keine VM erneut und erfindet
keinen Abschlusszustand. Fehler bei einer weiterhin laufenden VM werden nicht
als erfolgreicher Abschluss behandelt. Wiederaufnahme nutzt denselben CI-Lauf.

Die Korrektur wurde auf einer separaten Kopie aller 58 Originaldateien der letzten
Versuche ausgeführt. Der erzeugte Bericht weist beide Fehlerstatus, die vier
fehlenden Originalarchive/Release-Quittungen und die beiden fehlenden
Abschlusszustände aus. Die Originaldateien sind unverändert. Produktionsfreigabe
und vollständige Ausführung aller Gruppen bleiben ausdrücklich falsch.

Vor dem nächsten vollständigen Paarlauf sind diese Voraussetzungen zu erfüllen:

1. Neue, gemeinsame Baseline mit überprüftem PostgreSQL-Init und gebundenen
   Werkzeug- und Cache-Eingängen qualifizieren.
2. Host-/Gast-Speicherverhalten mit der unveränderten ursprünglichen Rust-Gruppe
   untersuchen; Schutzreserven beibehalten und produktive Builds berücksichtigen.
3. Den nachgewiesenen Fokuskonflikt und die zusätzliche Retry-Renderer-Abweichung
   separat auf Anwendungsseite bewerten. Ein abweichender Anwendungskandidat
   erfordert eine gesonderte Einordnung; der eingefrorene Vergleich bleibt rot.
4. Erst danach frische vollständige Läufe mit allen 29 Gruppen, vollständigen
   Originalinventaren, Ergebnisarchiven und Bereinigungsnachweisen durchführen.

Beide freigegebenen Wartungsfenster bleiben geschlossen. Alle sieben ursprünglich
pausierten Dienste sind gesund und in ihrer Konfiguration unverändert. Die
Ziel-VM ist ausgeschaltet. Das ursprüngliche Vollvergleichspaar wurde nicht
neu gestartet; eine neue, getrennte Frontend-Diagnose wurde ausgeführt.
115 passende lokale Tests und Ruff bestehen; die Leroy-UI wurde
nicht geändert. Die bisherigen visuellen Nachweise bleiben gültig.

Die privaten Nachweise liegen unter
`test-results/nas-parity/followup/offline-forensics-20261014/`, insbesondere
`paired-postgres-reinitialization-proof.json`, `paired-runtime-ownership-proof.json`,
`postgres-init-probe.json`, `postgres-init-deployment.json`,
`image-comparison.json`, `toolchain-file-comparison.json`,
`reanalysis-of-original-attempt/analysis.json` und `final-operations-proof.json`.
Rohprotokolle, Backups, Datenträger und Zugangsdaten werden nicht veröffentlicht.

## Qualifikation mit der ursprünglichen Frontend-Gruppe

Die zusätzliche Diagnose `quality-frontend-pg-init-20261014` verwendet eine neue
frische Baseline, den identischen Commit, das identische Runtime-Image und
unveränderte Originalquellen, Tests und Fixture-Limits. PostgreSQL-Init ist der
ausdrücklich separate Konfigurationsunterschied. Alle sieben NAS-Dienste laufen
währenddessen; diese Hintergrundlast entspricht nicht den beiden alten
Wartungsfenstern. Ein Leistungsvergleich mit diesen Fenstern wird nicht behauptet.

Der originale Leroy-Lauf `2a9e414117f64d50aa9d6b0a5f61bb74` führt die Gruppe
`frontend-and-deployment` vollständig aus und endet **failed**. Von 98
Browser-Komponentenfällen bestehen 96. Der bekannte Fokusfall scheitert erneut;
zusätzlich scheitert `embedded-startup.test.mjs:63` an der Sichtbarkeit von
`Retry renderer`. Für diese zusätzliche Abweichung wird keine Ursache behauptet.
Die vollständigen Originalergebnisse und die abgeschlossene Bereinigung sind
im Originalarchiv SHA256
`102682cfcda5af78ef814203b88a0fbabbbf0f34a3feaf47130cb5f13ad33006`
erhalten. Es gab keinen Abbruch an der Speicherreserve und keine Wiederverwendung
eines früheren Gruppenresultats.

Alle vier Basisdienste sind vor und nach der Gruppe gesund, ohne Neustart.
Die erhaltenen vollständigen PostgreSQL-Logs dieses neu angelegten Containers
zeigen keine interne Neuinitialisierung und keinen unbekannten Kindprozess;
der Server protokolliert keinen Lease-Verlust. 63 API-Messpunkte enthalten keinen
Timeout; zwei zusätzliche SQL-Beobachtungsfehler bleiben ausgewiesen. Die
ursprünglichen Jenkins-Jobhistorien sind an den Grenzen unverändert und inaktiv.

## Einzelbeobachtung des Fokuskonflikts

Nach Abschluss und Sicherung dieses Originaljobs wurden in derselben separaten
Diagnose-VM direkte Einzelaufrufe des ursprünglichen Fokusfalls durchgeführt.
Es gab keine Leroy-Jobsteuerung und keine laufenden Graphato-Basisdienste.
Die originale Testdatei stimmt über SHA256 mit dem eingefrorenen Git-Blob überein.
Die Container verwenden das neu gebaute, gebundene Browser-Image mit 3 GiB ohne
Swap, zwei CPUs und ohne Netzwerk. Die Quelle kommt direkt aus dem Image;
Vite-Cache und temporäre Dateien liegen in getrennten flüchtigen Mounts. Diese
Bedingungen sind unterstützende Diagnose und kein weiterer Original-CI-Lauf.

Der direkte unveränderte Einzelaufruf scheitert am gleichen Fokusfehler. Eine
umfangreiche externe Beobachtung einschließlich Layoutabfragen besteht einmal;
dieses Ergebnis wird ausdrücklich nicht als bestandene Abnahme gezählt.
Zwei weitere Kontrollfälle mit gleicher knapper Ereignisprotokollierung, einmal
ohne und einmal mit zusätzlichem `offsetWidth`-Lesen, scheitern beide erneut.
Ein einfacher Layout-Lesezugriff ist damit keine belegte Korrektur.

In beiden fehlgeschlagenen Beobachtungen ist die Abfolge eindeutig:

1. Graphato ruft `focus()` auf dem verbundenen Artikel auf.
2. Der Artikel erhält den Fokus tatsächlich.
3. Unmittelbar danach ruft die Eingabekomponente `focus()` auf der Textarea auf.
4. Die Textarea übernimmt den Fokus; die ursprüngliche Assertion sieht den
   Artikel als inaktiv.

Die vorher beobachtete Verzögerung ist somit nicht bloß ein zu kurzer
Assert-Timeout. Ein verzögertes Autofokus-Verhalten überschreibt die explizite
Navigation zum Artikel. Eine Anwendungsänderung, eine Testabschwächung oder eine
Deadline-Verlängerung wurde nicht vorgenommen. Sämtliche Zusatzcontainer wurden
entfernt und die VM anschließend sauber ausgeschaltet.

Die neuen Nachweise liegen unter
`test-results/nas-parity/followup/quality-frontend-pg-init-20261014/`, insbesondere
`original-frontend-result-proof.json`, `original-component-worker-proof.json`,
`baseline-stability-log-proof.json`, `focus-race-proof.json` und den getrennten
Original- und Einzelbeobachtungs-Abschlusszuständen. Diese Nachweise ergänzen die
alten Fehlversuche; sie ersetzen sie nicht.
