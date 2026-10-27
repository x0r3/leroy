# Begrenztes NAS-Testfenster

## Aktueller Status vom 26. Oktober

Die NAS-Abnahme und das Wartungsfenster sind auf Nutzerwunsch beendet. Alle sieben
Dienste laufen gesund; Leroy-Testdienste und VM sind gestoppt und starten nicht
automatisch neu. Die folgende frühere Freigabe ist ein historischer Beleg und
berechtigt nicht zu neuen Dienstpausen. Die Ablöse wird nach Bereitstellung eines
separaten Build-Servers neu geplant: [Checkpoint](checkpoint-2026-10-26.md).

## Historische Freigabe vom 17. Oktober

Der Anwender hat ausdrücklich erklärt: „Das Wartungsfenster ist nun unbegrenzt
offen. Fahre fort wie vorgeschlagen“. Der Beleg liegt in
`test-results/nas-parity/followup/authorization-open-ended-20261017.json`.
Dies erlaubt weitere getrennte Fenster für dieselben sieben Dienste. Jede Phase
behält eine feste Frist von höchstens vier Stunden, einen unabhängigen NAS-Wächter
und 15 Minuten Wiederherstellungsreserve. Nach jeder Phase werden dieselben Dienste
wiederhergestellt und auf Gesundheit und Stabilität geprüft. Alte Fenster bleiben
geschlossen; Produktionsumschaltung und Eingriffe am produktiven Jenkins sind nicht
freigegeben. Neue produktive Builds beenden die eigene Testlast.

Fenster U ist wiederhergestellt; die ursprüngliche Quittung bestätigt Abbruch und
Bereinigung. Die RAM-Datei ist freigegeben, die Testplatte mit SHA-256 geprüft auf
HDD archiviert und vom SSD-Testbereich entfernt. Der neue Versuch V verwendet
eine eigene NAS-Steuerung; 644 native Linux-Prüfungen bestehen. Versuch V ist geschlossen: Leroy #185 wurde durch Lease-Verlust unterbrochen.
Alle sieben Dienste sind wieder gesund und stabil, Fensterabschluss **10:41:51
Berliner Zeit**, vor der festen Endzeit 13:07:53. Der Koordinator hat einen
erzwungenen Neustart ohne erneuten Start des Phasenprozesses überstanden und
nach dem gescheiterten Originallauf keine nächste Phase gestartet.
Die ursprüngliche Quittung ist offline gesichert; RAM-Datei freigegeben und
Testplatte mit SHA-256 geprüft auf HDD archiviert, SSD-Kopie entfernt.
Die weiteren Console-Diagnosen pausieren keine der sieben Anwendungen.

Versuch W/Leroy #186 ist am 17. Oktober um **11:23:08 Berliner Zeit** mit dem
korrigierten Controller und unveränderten Graphato-Quellen/Tests gestartet. Der
Wächter hat dieselben sieben Dienste pausiert. Feste Endzeit **15:12:04**,
Wiederherstellungsbeginn spätestens **14:57:04**. Der eigene NAS-Koordinator bleibt
für Wiederanlauf und die nach Erfolg freizugebenden Folgephasen zuständig.
650 Linux-Prüfungen der neuen Steuerung bestehen; daraus folgt kein erfolgreicher
ursprünglicher Rust- oder Release-Abschluss.

## Tagesfreigabe vom 15. Oktober

Fenster S ist geschlossen: ursprünglicher Leroy-Lauf #180 mit DNS-Fehler vor Rust,
alle drei originalen Artefakte veröffentlicht. Die VM endete um **09:47:31** sauber,
alle sieben Dienste sind seit spätestens **09:50:32 Berliner Zeit** gesund und
stabil. Infrastruktur, produktive Jenkins-Stände und Controller-Prozess unverändert,
kein neuer OOM. RAM-Datei freigegeben, Testplatte bytegeprüft archiviert und SSD-Kopie
entfernt. Die ergänzende Sammlung enthält SSH-Beobachtungslücken.

Das Fenster T/Leroy ist vorzeitig geschlossen. Ein JSON-Leserennen der lokalen
Abnahmesteuerung löste die Wiederherstellung um **10:31:25 Berliner Zeit** aus.
Die originale Zielquittung bestätigt den anschließenden Abbruch und vollständige
Bereinigung. Die VM endete sauber um **10:32:19**, alle sieben Dienste sind vor
10:36 wieder gesund und stabil bestätigt. Kein produktiver Jenkins-Build,
keine geänderte Infrastruktur, kein neuer Controller-OOM. Die RAM-Datei ist
freigegeben; die Plattenarchivierung ist bytegeprüft abgeschlossen, SSD-Kopie entfernt.

U/Leroy verwendet ein eigenes neues Journal und die auf dem NAS geprüfte Korrektur
der atomaren Fortschrittsübergabe. Feste Endzeit **16. Oktober, 14:49:01 Berliner Zeit**;
Wiederherstellungsbeginn spätestens **14:34:01**. Quellen und Tests, Gast-/Containergrenzen,
CI-Slots und die direkte Gast-DNS-Konfiguration bleiben gleich. Nach diesem Fenster
werden dieselben sieben Dienste wiederhergestellt und dreimal auf Gesundheit und
Stabilität geprüft. Ein fehlgeschlagener oder abgebrochener Rust-Auftrag qualifiziert
weiterhin keine vollständigen Releases.

T hatte die feste Endzeit **16. Oktober, 13:57:34 Berliner Zeit**;
Wiederherstellungsbeginn spätestens **13:42:34**. Nur der frische Gast verwendet
direkte öffentliche DNS-Upstreams, nachdem der bisherige Gast-DNS-Pfad bei
gleichzeitig erfolgreicher direkter Anfrage ausgefallen war. Für beide CI-Systeme
ist dieselbe Einstellung vorgeschrieben. Die ursprünglichen Graphato-Tests und
Fristen werden nicht verändert. NAS-DNS und Netzwerkisolation bleiben unverändert;
die DNS-Einstellung im Gast wird vor und nach dem Auftrag nachgewiesen.

Die zusätzliche ausdrückliche Freigabe „dein Arbeitsfenster ist noch für den
gesamten morgigen Tag freigegeben“ umfasst auch den **16. Oktober bis 23:59:59
Berliner Zeit**. Sie gilt für dieselben sieben Dienste und weitere getrennte
Fenster von höchstens vier Stunden, jeweils mit 15 Minuten Reserve und geprüfter
Wiederherstellung. Die früheren Fenster und ihre gespeicherten Endzeiten am
15. Oktober bleiben unverändert. Neue Datumspläne und Wächter dürfen erst nach
dem vollständigen Abschluss des vorigen Fensters vorbereitet werden; geschlossene Journale bleiben
geschlossen. Die Freigabe umfasst keine Produktionsumschaltung.

Das Fenster P ist geschlossen. Leroy #179 endete um 00:12:54 nach Verlust der
SSH-Verbindung zum isolierten Ziel als `failed`; die Folgephasen wurden gestoppt.
Die NAS-Wache forderte um **16. Oktober, 03:15:09 Berliner Zeit** die
Wiederherstellung an. Die VM endete um 03:15:34 sauber, alle sieben ursprünglichen
Container waren um **03:15:57** wieder gestartet, vor der unveränderten Endzeit
03:30:03. Kein Reserveabbruch oder neuer NAS-OOM. Der SSH-Zugang war am Morgen
wieder verfügbar; drei Kontrollen bestätigen jetzt sieben gesunde, stabile Dienste.
Die Gesundheit vor der festen Endzeit bleibt wegen fehlender Beobachtung ungeprüft.
Infrastruktur und Controller-Prozess sind unverändert, die 7-GiB-RAM-Datei der
gestoppten VM ist freigegeben. Kein neuer Testauftrag oder erneutes Pausieren.
Die Originalquittung wurde aus der gestoppten Platte gelesen: Rust-Timeout,
vollständige Bereinigung, keine ausgeführten Rust-Tests. Sie ersetzt kein
veröffentlichtes CI-Artefakt und erlaubt keine Produktionsfreigabe.

Das getrennte diagnostische Jenkins-Fenster P ist ebenfalls geschlossen.
Jenkins #30 scheiterte vor Rust am DNS-Fehler `EAI_AGAIN` bei der npm-Registry.
Die VM endete am 16. Oktober um **08:58:25**, alle sieben ursprünglichen Container
waren um **08:58:59 Berliner Zeit** gestartet und vor 09:01 dreimal gesund und
stabil bestätigt. Damit wurde die feste Endzeit 12:32:56 eingehalten. RAM-Datei
freigegeben, Testplatte bytegeprüft auf HDD archiviert, SSD-Kopie entfernt;
produktive CI während Fenster und Archivierung unverändert. Das Journal bleibt
geschlossen. Die diagnostische Referenz ersetzt keinen Rust-Erfolg.

Versuch S bindet die Korrektur des Leroy-Graphato-Adapters an die unveränderten
ursprünglichen SSH-Optionen, das genaue auf dem NAS geprüfte Image und neue
Linux-Nachweise der Abnahmesteuerung. Q und R wurden vor Dienstpause und
CI-Auftrag abgefangen; ihre Pläne bleiben erhalten. Die tatsächliche Wächterrichtlinie
wird jetzt schon lokal beim Erstellen des Plans geprüft. Neues Journal für S/Leroy,
frische Baseline, dieselben physischen Grenzen und CI-Slots. Feste Endzeit
**16. Oktober, 13:21:59 Berliner Zeit**, Wiederherstellungsbeginn spätestens **13:06:59**.
DNS-/Firewall-Konfiguration und Graphato-Quellen, Tests und Fristen bleiben
unverändert. Erst erfolgreiche ursprüngliche Rust-Aufträge beider Engines
erlauben vollständige Releases; S darf die diagnostischen P-Ergebnisse nicht
übernehmen. Nach diesem Fenster werden dieselben sieben Dienste wiederhergestellt.

Die Antwort „den ganzen Tag“ gilt für dieselben sieben Dienste bis zum
15. Oktober, 23:59:59 Berliner Zeit. Neue Journale verwenden eigene Namen
`resource-window-day-20261015-*`; alte Fenster werden nicht wieder geöffnet.
Jedes neue Fenster dauert höchstens vier Stunden, mit 15 Minuten Reserve für
die Wiederherstellung. Nach jedem Fenster werden die ursprünglichen Container
und ihre Gesundheit geprüft. Der neue Wächter berücksichtigt weiterhin
produktive Jenkins-Builds und die unveränderten RAM-/Swap-Untergrenzen.

Das Fenster H/Jenkins ist geschlossen. Die ursprüngliche Zielprüfung endete
um 18:12:26 Berliner Zeit mit `TimeoutExpired` und vollständiger Bereinigung.
Die Wiederherstellung wurde erst danach angefordert. Der Wächter musste die
registrierte eigene VM zwangsweise beenden; dieser Umstand bleibt dokumentiert.
Alle sieben Dienste waren um **18:29:35 Berliner Zeit** wieder gesund und stabil.
Der ursprüngliche Jenkins-Job #29 ist als `FAILURE` gesichert, ohne neuen Build
oder erneuten Testauftrag. Testplatte bytegeprüft archiviert, SSD-Kopie und
eigene RAM-Datei freigegeben. Kein neuer NAS-OOM, produktive CI unverändert.

Das Fenster I ist geschlossen. Leroy #178 wurde wegen nicht bestätigter
Worker-Lease unterbrochen; alle sieben Dienste sind seit **20:21:07 Berliner Zeit**
gesund und stabil. VM sauber beendet, eigene RAM-Datei freigegeben und Platte
bytegeprüft archiviert. Die zusätzliche Originalquittung wurde nur offline gelesen.

Das Fenster J ist nach einem SSH-Banner-Timeout vor dem Original-CI-Auftrag
geschlossen. Alle sieben Dienste sind wieder gesund und stabil. Die VM ist sauber
beendet, die RAM-Datei freigegeben und die Testplatte bytegeprüft archiviert.
Die Korrektur klassifiziert bekannte OpenSSH-Transportfehler als unbekannte Antwort
derselben Aktion; sie setzt weder Fristen zurück noch startet sie den CI-Auftrag neu.
15 Gegenbeispiele bestehen auf dem NAS im unveränderten Worker-Image.

Das Fenster K ist ebenfalls vor dem Original-CI-Auftrag geschlossen. Eine innere
Abfrage produktiver Jenkins-Jobstände verlor die SSH-Verbindung bei 2.048 MiB.
Die äußere Beobachtung und Wiederherstellung wiederholten denselben Journalzugriff
innerhalb ihres festen Budgets; alle sieben Dienste sind wieder gesund und stabil.
Die Vorbereitung darf jetzt ausschließlich unbekannte Leseabfragen vor einer
Zuteilung innerhalb eines gemeinsamen 60-Sekunden-Budgets wiederholen. Danach
müssen aktuelle Jobstände und NAS-Reserven die unveränderten Prüfungen bestehen.
Keine Zuteilungswiederholung, keine Verlängerung des Fensters oder der Originaltests.

Das Fenster L ist nach ausgeschöpftem Lese-Budget bei 2.048 MiB geschlossen;
kein Original-CI-Auftrag. Alle sieben Dienste sind wieder gesund und stabil,
VM sauber beendet, RAM-Datei freigegeben und Testplatte bytegeprüft archiviert.

Das Fenster `resource-window-day-20261015-m-rust-leroy` ist seit **15. Oktober,
22:16:36 Berliner Zeit** geschlossen. Es endete vor jedem ursprünglichen
Graphato-CI-Auftrag nach einem Fehler der Gast-Steuerung bei 3.584 MiB.
Alle sieben Dienste sind gesund und stabil, die VM sauber beendet, keine neue
NAS-OOM-Auslösung; produktive CI und Infrastruktur unverändert.
Seine gespeicherte Endzeit **16. Oktober, 01:54:50 Berliner Zeit** bleibt als
historische Grenze erhalten. Es nutzte die zusätzliche Freigabe für den gesamten 16. Oktober,
bleibt selbst auf vier Stunden begrenzt und bindet die Linux-Prüfung der lokalen
NAS-Kapazitätssteuerung an den Plan. Deren temporärer eigener Prozess liest die
Produktions- und Reservewerte direkt, steuert denselben Gastfüller und endet vor
dem eigentlichen CI-Lauf. Die Windows-Seite darf einen verlorenen Startbeleg nur
beobachten, nicht den Start wiederholen. Das Fenster bindet außerdem den geprüften
weichen Speicherschutz der eigenen
verschachtelten Test-Engine, die 28 bestandenen Linux-Workerprüfungen und die
Quell- und Linux-Nachweise der SSH-Korrektur und der sicheren Leseabfragen an den Plan.
Frische Kapazitäts- und Original-CI-Ergebnisse sind erforderlich. NAS-Untergrenzen,
Graphato-Quellen, Tests und Fristen bleiben unverändert. Der Wächter sendet ein an
die gespeicherte Identität gebundenes Stoppsignal vor einem weiteren Journal-fsync.
Geschlossene Journale und ihre ursprünglichen Wächter werden nicht geändert.

Das getrennte Fenster `resource-window-day-20261015-n-rust-leroy` endet spätestens
am **16. Oktober, 02:24:48 Berliner Zeit**, mit Wiederherstellung ab spätestens
**02:09:48**. Es bindet die auf dem NAS geprüfte erweiterte Fehlerdiagnose
(29 Prüfungen ohne VM oder Speicherlast). Ressourcen, Probe und Originaltests
bleiben gleich. Sein Vorgänger M ist geschlossen; dessen sieben Dienste waren
vor N gesund und stabil und dessen Testplatte ist bytegeprüft archiviert.

N ist seit **15. Oktober, 22:44:28 Berliner Zeit** geschlossen; alle sieben
Dienste sind gesund und stabil. Der Gastlog bestätigt den Leerlauf-Timeout der
Zusatzprobe, bevor ein ursprünglicher Graphato-Auftrag gestartet wurde.
VM sauber beendet, RAM-Datei freigegeben, Testplatte bytegeprüft archiviert.

Das neue Fenster `resource-window-day-20261015-o-rust-leroy` endet spätestens
am **16. Oktober, 02:51:58 Berliner Zeit**, mit Wiederherstellungsbeginn spätestens
**02:36:58**. Aktive reine Statusabfragen halten die Zusatzprobe während langsamer
Steuerungsprüfungen erreichbar. Sie verwenden nur den vorhandenen privaten
Gast-Master-Socket; neue Verbindungen als Rückfall sind gesperrt. Dieses Verhalten
nutzt die dokumentierte [OpenSSH-Verbindungsteilung](https://man.openbsd.org/ssh_config#ControlMaster)
mit einem absichtlich fehlschlagenden [ProxyCommand](https://man.openbsd.org/ssh_config#ProxyCommand)
für den Rückfall. Zuteilungen behalten die vollständige Identitätsprüfung.
Weder Probegrenzen noch ursprüngliche Tests oder Fensterfristen wurden verlängert.
41 Gegenbeispiele bestehen auf dem NAS ohne VM oder Speicherlast.

O ist seit **15. Oktober, 23:19:36 Berliner Zeit** geschlossen, alle sieben
Dienste gesund und stabil. Auch mit 21 Statusantworten fehlt der vollständige
Kapazitätsbeleg; die negative Zusatzprobe bleibt erhalten. Die Test-VM endete
sauber, RAM-Datei freigegeben und Testplatte bytegeprüft archiviert.

`resource-window-day-20261015-p-rust-leroy` verwendet einen ausdrücklich getrennten
Modus zur Qualifikation durch die unveränderten Originalaufträge. Der Plan bindet
die negative Zusatzprobe, ihre Wiederherstellung, unveränderte physische Ressourcen
und die Linux-Prüfung der neuen Ausführungskontrollen. Kein positiver synthetischer
Kapazitätsbeleg wird erzeugt oder übernommen. Die vollständigen ursprünglichen
Rust-/Release-Nachweise und die NAS-Untergrenzen bleiben erforderlich.
P endet spätestens am **16. Oktober, 03:30:03 Berliner Zeit**, mit Wiederherstellung
ab spätestens **03:15:03**. Die Freigabe bis Ende des 16. Oktober gilt weiterhin;
geschlossene Fenster werden nicht wieder geöffnet.

Das Tagesfenster G/Jenkins ist geschlossen; alle sieben Dienste sind seit
15:50:30 Berliner Zeit gesund und stabil. Nach einem SSH-Statuslesefehler musste
die eigene Abnahmesteuerung wiederhergestellt werden. Fehlende Antworten gelten
jetzt als unbekannter Beobachtungsstand derselben CI-ID. Die Wiederherstellung
darf nach einem Transport-Timeout dieselbe Aktion erneut anfordern, bleibt aber
auf ihr festes Budget und die genehmigte Endzeit begrenzt.
Das neue Journal `resource-window-day-20261015-h-rust-jenkins` endet spätestens
um 20:04:14, mit Wiederherstellungsbeginn spätestens 19:49:14 Berliner Zeit.
G und die Nachtjournale bleiben geschlossen; H ändert keine NAS-Untergrenze,
Graphato-Quelle, Originaltest oder Leroy-Lease-Frist.

Seit Tagesversuch E werden wiederholte Produktionsbeobachtungen nach einmaliger
Container-Ermittlung direkt über das verifizierte Jenkins-Datenverzeichnis
gelesen. Vor und nach dem Lesen werden dieselbe Boot-ID, PID-Startzeit,
Kommando-Prüfsumme, Cgroup, Namensräume und Mount-Inodes geprüft. Eigene
Gastzugriffe verwenden dieselbe Prozessprüfung vor und nach SSH. Das vermeidet
die in D beobachtete Docker-Metadaten-Zeitüberschreitung; ein Identitätswechsel
bleibt ein Abbruchgrund. NAS-Schutzgrenzen und Produktionskonfiguration bleiben
unverändert. Die Prüfung ist mit positiven und negativen Fällen auf dem NAS
lesend validiert.
Das erste Fenster dient ausschließlich dem ursprünglichen Rust-Schritt unter
Leroy mit einem separaten Gast-Swap-Profil. NAS-Swap, Kernelkonfiguration des
NAS, Anwendungsquellen, Tests und ursprüngliche Fixture-Limits bleiben gleich.
Die vollständigen Release-Läufe benötigen vorher erfolgreiche Original-Rust-
Nachweise unter beiden Engines. Die nachfolgenden Abschnitte dokumentieren
die bereits abgeschlossenen Nachtfenster.

Abschluss der Nacht am 15. Oktober 2026: **Alle Nachtfenster sind geschlossen.** E endete
nach produktivem Musik-Timer #244. In F blieb die produktive CI ruhig;
der unveränderte NAS-Swap-Schutz beendete die Testlast. Alle sieben
Originalcontainer waren um **05:28:30 Berliner Zeit** gesund und stabil
wiederhergestellt, vor dem Ende um 06:00. Test-VM und privater Jenkins sind aus.
Keine weiteren schweren Builds in dieser Nacht, keine Produktionsumschaltung.

Der VM-Stopp in F dauerte nach Unterschreiten der Swap-Untergrenze etwa
drei Minuten und war erzwungen. Die folgende Quellkorrektur ergänzt deshalb
eine Reserveprüfung direkt im unabhängigen NAS-Wächter. Sie verwendet dieselben
128 MiB verfügbaren RAM und 2.304 MiB freien Swap. Im Reserve-Notfall wird
ausschließlich der zuvor verifizierte eigene VM-Initprozess direkt beendet:
SIGTERM, nach zehn Sekunden nötigenfalls SIGKILL, erneute Identitätsprüfung
vor jedem Signal. Für andere Stopps bleibt die 210-Sekunden-Schonfrist.
Erst nach VM-Ende starten die Anwendungen. Die Registrierung folgt nun auch
Jenkins-only-Boots ohne neue Leroy-Lauf-ID. Geschlossene Journale und ihre
freigegebenen Quellkopien bleiben unverändert. Die Nachkorrekturen sind lokal
und mit dem tatsächlichen Linux-Prozessparser geprüft. Die Tagesprüfung unter
Jenkins hat den Reservepfad inzwischen ausgelöst: verifizierte VM beendet,
sieben Dienste wieder gesund und stabil, kein neuer NAS-OOM. Der abgebrochene
Rust-Lauf bleibt unvollständig.

Die geschlossenen Platten werden mit laufenden, gesunden Anwendungen und
ruhiger produktiver CI bei begrenzter I/O archiviert. Erst nach unabhängigem
Hashvergleich darf die eigene SSD-Kopie entfallen. Das öffnet kein Testfenster
erneut. Der Gesamtstand steht in `docs/status.md`; die folgenden Abschnitte
bewahren frühere, jeweils getrennt abgeschlossene Fenster.

## Erstes Zweistundenfenster vom 13. Oktober

Stand: 13. Oktober 2026, Berliner Zeit. Der Nutzer hat das begrenzte Fenster
ausdrücklich freigegeben. **Das Fenster ist abgeschlossen. Alle sieben
ursprünglichen Container laufen wieder, mit gesunden Healthchecks. Die einzelne
originale Clippy-Gruppe besteht unter Jenkins und Leroy; die vollständige
Release-Abnahme bleibt offen.**

Beginn: **00:20:24 Uhr**, spätestes Ende **02:20:24 Uhr** am 13. Oktober.
Ein unabhängiger NAS-Prozess sicherte die Wiederherstellung mit fünf Minuten
Reserve vor dem Fristende ab. Tatsächlich sind alle Dienste um **02:07 Uhr**
wieder gestartet und vor 02:10 Uhr gesund und stabil geprüft. Die ursprüngliche
Frist wurde durch die Folgeprobe nicht verlängert; die gesamte Zeitspanne
beträgt rund 107 Minuten, einschließlich der zwischenzeitlichen Wiederherstellung.

Die zusätzliche isolierte Linux-Ziel-VM konkurriert auf dem NAS mit dessen
Anwendungen. Die unveränderte Graphato-Postdeploy-Prüfung erlaubt ihrem Builder
6 GiB RAM ohne Swap. Ein 6-GiB-Gast kann diesen Builder und die Basisanwendung
nicht gleichzeitig mit voller deklarierter Kapazität versorgen. Ein 10-GiB-Gast
behebt diese Größenabweichung, schafft aber keinen zusätzlichen physischen
NAS-Speicher. Tatsächliche Clippy-Versuche mit 4 GiB beziehungsweise 3,5 GiB
bevorzugtem QEMU-RAM unterschreiten die NAS-RAM- beziehungsweise Swap-Reserve.
Im zweiten Lauf verliert Leroy zusätzlich die Lease. Die vollständige Ursache
des Lease-Verlusts ist nicht belegt.

## Vorbereiteter Umfang

Die schreibgeschützte Aufnahme vom 12. Oktober, 21:42 UTC findet folgende
laufende Dienste. Zahlen sind Cgroup-Aufnahmen und keine zugesicherte freie
Kapazität nach einem Stopp. Nicht enthalten sind Betriebssystem- und sonstige
Hostprozesse. Die vollständigen Container-IDs stehen im privaten Beleg.

| Dienst | Geprüfter Container | RAM, MiB | Swap, MiB |
| --- | --- | ---: | ---: |
| paperless | `0a2fd4c04bc5` | 262 | 523 |
| sonarr | `65784b3a21c4` | 251 | 0 |
| radarr | `2cb52665b391` | 191 | 0 |
| sabnzbd | `86c44ff19715` | 142 | 0 |
| plex | `700764987c1d` | 79 | 62 |
| yt-downloader-service | `047db6c14aaa` | 41 | 39 |
| mail-ingest-service | `ba526b946e4e` | 26 | 16 |

Zusammen sind das rund 991 MiB RAM und 640 MiB Swap, etwa 1,6 GiB.
Während des Fensters sind diese Anwendungen und ihre laufenden Aufgaben
vorübergehend nicht verfügbar. PostgreSQL/Redis und die übrigen
Paperless-Hilfsdienste bleiben erhalten. Jenkins, Gitea, Registry, Portainer,
VPN und NAS-Systemdienste werden nicht gestoppt oder umkonfiguriert.

## Ablauf nach ausdrücklicher Freigabe

1. Erneut alle produktiven Jenkins-Historien prüfen. Bei aktiven Builds keinen
   Test starten. Alle bisherigen originalen CI-Läufe müssen terminal, privater
   Jenkins und Test-VM ausgeschaltet sein.
2. Die sieben vollständigen Container-IDs gegen den privaten Plan prüfen.
   Ersetzte Container, geänderte Konfigurationen oder bereits anderweitig
   gestoppte Dienste erfordern eine neue Bestandsaufnahme. Zustand und
   Konfigurationsprüfsummen vor jeder Aktion geschützt protokollieren.
3. Die sieben geprüften Container mit ihrem normalen Stoppsignal und bis zu
   120 Sekunden Schonfrist pro Dienst stoppen. Kein Container, Volume, Image,
   Netzwerk oder Datensatz wird gelöscht. Ungewisse Stoppergebnisse erst
   untersuchen; nicht pauschal weiterarbeiten.
4. Freie RAM-/Swap-Reserve erneut messen. Die bisherigen Schutzgrenzen
   bleiben unverändert. Auf frischer Basis die einzelne Originalgruppe
   `server-clippy` zuerst unter Leroy prüfen. Nur bei erfolgreichem Abschluss
   ohne Lease-Ausfall die gleiche Gruppe unter privatem Jenkins ausführen.
   Quellen, Tests, Buildergrenzen und Originalfristen bleiben unverändert.
5. Das Fenster dauert höchstens zwei Stunden ab dem ersten Dienststopp.
   Schutzstopp, neue produktive Jenkins-Arbeit, ungewisser CI-Zustand oder
   Fristende beenden die zusätzliche Last. Alle begonnenen CI-Läufe werden
   abgeglichen und ihr tatsächliches Ergebnis gesichert. Ein Abbruch wird
   niemals als bestandene Prüfung gewertet.
6. Genau die in diesem Fenster tatsächlich gestoppten Container wieder
   starten, auch nach einem Diagnosefehler. Container-IDs, Konfiguration,
   vorhandene Healthchecks und stabile Prozesszustände prüfen. Wiederanlauf-
   Fehler ausdrücklich berichten. Bereits vor dem Fenster gestoppte Dienste
   werden nicht gestartet. Images, Daten und Konfiguration bleiben unverändert.

Ein erfolgreicher Clippy-Vergleich ermöglicht die nächste Entscheidung über
das Ressourcenfenster für die vollständigen Original-Pipelines. Dieses
begrenzte Fenster ist keine vorweggenommene Release- oder Produktionsfreigabe.
Auch eine identische Pause bei beiden Engines belegt keine Leistungsgleichheit
mit dem laufenden produktiven NAS.

## Durchführung

Die vollständigen produktiven Jenkins-Historien waren vor dem Fenster ruhig,
Test-VM und privater Jenkins aus, keine eigenen Jobworker aktiv. Alle sieben
Container-IDs wurden erneut geprüft. Geschützte vollständige Bestandsaufnahmen
und Konfigurationsprüfsummen liegen im eigenen NAS-Verzeichnis. Docker liefert
Mounts in wechselnder Reihenfolge; nur diese Reihenfolge wird für die
Prüfsumme normalisiert, die Mount-Inhalte bleiben vollständig geprüft.

Sechs Dienste stoppen mit Exitcode 0. `mail-ingest-service` braucht nach
120 Sekunden Schonfrist einen erzwungenen Stopp und endet mit Exitcode 137.
Sein Wiederanlauf und die vorhandenen Dienst-Healthchecks sind noch zu prüfen.

`nas_resource_window_guard.py` protokolliert vor jeder Aktion und startet
ausschließlich dieselben Container, deren Stopp in diesem Fenster vermerkt ist.
Die Rücksicherung ist vom Windows-Prozess unabhängig. Sie beendet nur die
registrierten eigenen CI-Worker und die Ziel-VM der beiden freigegebenen
Vergleichsnamensräume. Fehler beim Beenden der Testlast blockieren die
Dienstwiederherstellung nicht. Fünf gezielte Eigentums-/Rücksicherungstests
bestehen; zusammen mit den bisherigen betroffenen Tests sind es 83.

Die ursprünglichen Clippy-Datenträger der zwei beendeten 10-GiB-Versuche werden
vor der neuen CI-Last mit Byte-, Eigentums- und SHA-256-Prüfung auf den HDD-Pool
archiviert. Nur verifizierte einzelne SSD-Dateien werden anschließend
freigegeben; Diagnosebelege und Originaldaten bleiben erhalten.

Die neue Prüfung verwendet auf beiden Engines das Profil
`nas-10g-ssd-soft-ram-4096`, die frische eingefrorene Basis und ausschließlich
die bestehende Originalgruppe `server-clippy`. Original-Buildergrenzen, Quellen,
Tests und NAS-Schutzreserven bleiben unverändert. Dies ist eine gezielte
Gegenprüfung unter verringerter Hintergrundlast, keine Produktionsumschaltung.

### Erster Versuch und gezielte Folgeprobe

Leroy #161 (`220d05e2204a496bad1e78cc6b02461a`) endet fehlgeschlagen.
Am 13. Oktober um 00:48:23,767 Uhr Berliner Zeit unterschreitet das NAS die
unveränderte RAM-Reserve: 125.972 KiB verfügbar gegenüber 131.072 KiB Minimum.
Swap hat noch 5.185.872 KiB frei. Der Gast fährt regulär herunter
(`forced: false`, QEMU-Code null, kein äußerer OOM). Die Original-Clippy-
Prüfung bleibt unvollständig; das CI liefert nur eine 189-Byte-Abbruchquittung,
SHA-256 `f1b57957c0116c067d24f267ae551db1f1aede9ee5f6712b8aab957966217a7d`.
Ein Clippy-Quellfehler oder bestandener Check wird daraus nicht abgeleitet.

Zwei kurzzeitige `ReadTimeout`-Erneuerungsfehler werden zeitgestempelt erhalten;
die Lease wird danach wieder erneuert und geht nicht verloren. 50 Gesundheits-
Messpunkte haben keinen API-Timeout, sechs Zusatzproben haben SSH-/Docker-
Wrapperfehler; erhaltene direkte SQL-Abfragen haben keinen Fehler. Die
Infrastruktur einschließlich sechs Ausführungshilfen ist vor/nachher gleich.
Jenkins startet gemäß der bedingten Reihenfolge nach diesem Fehler nicht.

Alle sieben Dienste sind um etwa 00:51 Uhr mit unveränderten Containern,
Images und Konfigurationen wieder gestartet. Alle vorhandenen Healthchecks
sind gesund; Prozesszustände sind über mehr als 40 Sekunden stabil. Die erste
Pause beträgt rund 30,8 Minuten. Der produktive Jenkins bleibt unverändert
und seine vollständigen Historien ruhig. Sechs weitere technische und direkt
visuell geprüfte UI-Ansichten stimmen mit dem tatsächlichen Fehler überein;
insgesamt sind es 401 historische NAS-Ansichten.

Die hohe verbliebene Swap-Reserve begründet eine einzige weitere Probe mit
`nas-10g-ssd-soft-ram-3584`: Sie verschiebt 512 MiB des bevorzugten QEMU-RAM-
Budgets zu möglichem Swap. Gastgröße, harte Grenzen, Original-Builder, Quellen,
Tests und NAS-Schutzreserven bleiben gleich. Die Folgeprobe läuft innerhalb
derselben Nutzerfreigabe und **derselben ursprünglichen Endzeit 02:20:24 Uhr**.
Der Guard gewährt keine weiteren zwei Stunden; er verweigert die Folgeprobe
ohne mindestens 30 Minuten Restbudget. Der abgeschlossene erste Zustand und
seine ursprüngliche Guard-Version bleiben gesichert. Nach dieser Folgeprobe
werden die Dienste erneut wiederhergestellt. Nur bei erfolgreicher vollständiger
Clippy-Gruppe ohne Lease-Verlust startet noch die Jenkins-Gegenprüfung, sofern
ausreichend Restbudget besteht. Zwei zusätzliche Grenztests prüfen ausdrücklich,
dass keine neue Zweistundenfrist entsteht; insgesamt 85 gezielte Tests.

Leroy #162 (`c426a44362de438d93ee38dc533a9c59`) besteht diese Folgeprobe.
Die originale Quittung bestätigt die vollständig ausgeführte einzelne Gruppe
`server-clippy`, Exitcode 0, 1.147,757 Sekunden, vollständigen Cleanup,
keinen Abbruch und keinen wiederverwendeten Erfolg. Das Originalarchiv ist
29.275 Byte groß, SHA-256
`5b07c539277f6bbc8bd2f380e66c1e795fd5507f338153b120eb792ec45bc208`.
Commit, Runtime-Image, Quellenarchiv und ursprünglicher Bauzeitpunkt stimmen
mit dem eingefrorenen Release überein. Alle vier Basisdienste sind nachher
gesund, ohne Neustart. Eine einzelne `RemoteProtocolError`-Erneuerungslücke
wird aufgezeichnet; die Lease geht nicht verloren.

56 gespeicherte Gesundheitsmesspunkte enthalten keinen API-Timeout.
14 zusätzliche SSH-/Docker-SQL-Proben haben Wrapperfehler; die erhaltenen
direkten SQL-Abfragen haben keinen Fehler. Eine weitere begrenzte Controller-
Logabfrage wird wegen Transport-/I/O-Timeout als Beobachtungslücke gesichert.
Die Ausführung ist damit erfolgreich, eine lückenlose Verfügbarkeitsmessung
wird nicht behauptet. Quellen, Tests, Original-Builder und harte Ressourcen-
Grenzen bleiben unverändert. Die Infrastruktur vor/nachher einschließlich
sechs Ausführungshilfen stimmt überein.

### Ergebnis der Gegenprüfung

Der private Jenkins #21 besteht ebenfalls die vollständige Originalgruppe
`server-clippy`, Exitcode 0, 1.258,068 Sekunden, vollständiger Cleanup, kein
Abbruch und keine wiederverwendete Quittung. Originalarchiv SHA-256
`fb8f691f9e45c37f532d9e29ba3bb987239ba48fad5457f6a0cf617f2725feb4`.
Beide verwenden denselben Commit, dieselbe Runtime-/Quellen-/Bauzeitpunkt-
Identität, dasselbe VM-Profil und dieselben fünf tatsächlich aufgelösten
Build-Basis-Image-Digests, einschließlich Rust 1.94.1. Steuerimages, Konfiguration,
PostgreSQL-Durabilität und sechs Ausführungshilfen stimmen im Paar überein.
Alle vier Basisdienste bleiben bei beiden gesund. Die Laufzeiten werden
aufgezeichnet, daraus aber keine allgemeine Leistungsgleichheit abgeleitet.

62 Jenkins-Gesundheitsmesspunkte enthalten eine Probe mit zwei `ConnectError`-
Ergebnissen für die äußere Live-/Bereitschaftsprüfung. 21 zusätzliche SQL-Proben
haben Wrapperfehler, die erhaltenen direkten Abfragen keinen SQL-Fehler.
Die Verbindungsprobe liegt am 13. Oktober um 02:04:44,573 Uhr; der nächste
erhaltene Messpunkt ist wieder erfolgreich. Die interne erfolgreiche SQL-Probe
allein konnte einen API-Prozessausfall nicht ausschließen.

Die Nachprüfung **belegt einen Controller-OOM**: Der Kernel beendet Uvicorn
beim Erreichen des 256-MiB-Cgroup-Limits um etwa 02:04:15 Uhr. Docker startet
denselben Container um 02:04:24 Uhr neu; die Anwendung ist um 02:04:51 Uhr
wieder bereit. Der Jenkins-Check besteht trotzdem. Die bisherigen Zusatzproben
starteten einen weiteren Python-/SQLAlchemy-Prozess im selben Controllerbudget.
Dies ist ein relevanter Beobachtereinfluss; sein exklusiver Anteil an allen
Speicherspitzen oder historischen Lease-Ausfällen wird nicht behauptet.

### Korrektur nach dem abgeschlossenen Originalvergleich

Die regelmäßige Zusatz-SQL-Probe läuft künftig nur als leichter `psql`-Prozess
im eigenen PostgreSQL-Container, mit schreibgeschützter Sitzung und
Statement-Frist. Standort, serverseitige Statement-Zeit und SSH-/Docker-
Transportkosten bleiben getrennt. Der tatsächliche Controller-DB-Pfad wird
weiter über `/health/ready` geprüft. Die alten Messungen werden nicht verändert.

Das Controllerlimit steigt auf **512 MiB ohne Swap**. Eine getrennte API mit
eigener temporärer Datenbank besteht acht Runden realer Anmeldung und der alten
SQL-Probe ohne OOM oder Neustart; diese begrenzte leere Datenbank ersetzt keinen
vollständigen NAS-Lastlauf. Der erste Probehelfer las seine dynamische IP vor
dem Start und scheiterte; sein Container und seine Datenbank wurden entfernt,
der Fehlerbeleg blieb erhalten. Die korrigierte Probe ist separat dokumentiert.

Das höhere Limit ist anschließend im eigenen laufenden Controller und dessen
Compose-Override gesetzt. Container-ID, Image, PID, Mounts, Umgebung,
CPU-Grenzen, Speicherreservierung, Cgroup-Vorfahr und übrige Dienste bleiben
gleich; keine Neuerstellung oder zusätzlicher Neustart. Vorherige Konfiguration,
vollständige Containeraufnahmen und ein PostgreSQL-Dump sind geschützt gesichert.
Zehn parallele authentifizierte Metadaten-Abfragesequenzen auf dem tatsächlichen
Controller bestehen ohne neuen OOM oder Neustart. Die NAS- und vorbereiteten
Produktions-Compose-Dateien enthalten ebenfalls 512 MiB; das Produktionsbundle
ist weiterhin nicht aktiviert. Die vollständigen Original-Pipelines wurden
nach dieser Korrektur noch nicht erneut geprüft.

Alle ursprünglichen CI-Läufe sind terminal, Test-VM und privater Jenkins aus,
keine eigenen Jobworker aktiv. Alle sieben ursprünglichen Container, Images und
Konfigurationen sind wiederhergestellt; ihre vorhandenen Healthchecks sind
gesund und Prozesse über mehr als 40 Sekunden stabil. Vollständige native
Jenkins-Historien und unveränderte Buildnummern bestätigen ruhige Fenster.
Der Rücksicherungsprozess ist beendet. Alle zusätzlichen Probecontainer und
temporären Datenbanken sind entfernt. 88 gezielte Tests bestehen; die Zahl
direkt und technisch geprüfter NAS-Ansichten ist 407. Die vollständige
Release-Abnahme und die Produktionsfreigabe bleiben offen.

Abschlussbelege: `window-result.json`, `paired-clippy-proof.json` und
`recovery-verification-attempt2.json` im folgenden Rohbelegordner.
Die Controller-Korrektur steht zusätzlich in
`test-results/nas-parity/followup/controller-memory-20261013/`.

Aktuelle Rohbelege:
`test-results/nas-parity/followup/resource-window-20261013/`.

Ursprünglicher Planbeleg:
`test-results/nas-parity/followup/control-stability-clippy-10g-3584-20261012/capacity-and-lease-proof.json`.

## Neue vollständige Abnahme mit 512-MiB-Controller

Der Nutzer hat anschließend zwei **getrennte Wartungsfenster von jeweils
höchstens vier Stunden** zum Pausieren derselben sieben Dienste freigegeben.
Nach jedem Fenster müssen alle Dienste wiederhergestellt und gesund geprüft
werden. Diese Freigabe verlängert nicht das abgeschlossene Clippy-Fenster.

Der neue Vergleich verwendet den eingefrorenen Graphato-Commit
`0ad540dd578033d45e4d0c25d89fbe57b32102a4`, unveränderte Quellen und Tests,
die gleiche saubere Zielbasis und das Profil `nas-10g-ssd-soft-ram-3584`.
Zuerst läuft der vollständige originale Release-Abnahmejob unter Leroy,
anschließend unter dem privaten Jenkins. Das beinhaltet alle Browser- und
Qualitätsgruppen sowie die gemeinsame abschließende Release-Prüfung.
Frühere Einzelgruppenergebnisse werden nicht als Ersatz angerechnet.

`scripts/run_nas_full_release_window.py` bereitet pro Engine ein eigenes
geschütztes NAS-Journal und einen unabhängigen Wiederanlaufwächter vor.
Die absolute Frist beginnt vor dem ersten Stoppbefehl. Der Wächter beendet
zusätzliche Testlast mit 15 Minuten Wiederherstellungsreserve. Eine neue
produktive Jenkins-Buildnummer oder ein ungewisser Produktionsnachweis
beendet das Fenster ebenfalls. Native Jenkins-Dienste bleiben unverändert.
Ein Abbruch wird als unvollständige Abnahme erhalten. Die originalen
Pipeline-Fristen und Graphato-Buildergrenzen werden nicht geändert.

Vor dem Pausieren werden aktuelle Container-IDs, Images, Konfiguration und
vorhandene Healthchecks erfasst. Nachher werden dieselben IDs und
Konfigurationen sowie gesunde, stabile Prozesse geprüft. Controllerzustand,
Originalgruppen, Artefakte, Release-Identität, Ressourcen und Beobachterfehler
bleiben getrennt dokumentiert. Der korrigierte Controller wird erstmals in
diesen neuen vollständigen Original-Läufen unter Last beurteilt.

Neue Belege:

- `test-results/nas-parity/followup/full-release-controller512-20261013/`
- `test-results/nas-parity/followup/resource-window-full-leroy-20261013/`
- `test-results/nas-parity/followup/resource-window-full-jenkins-20261013/`

Vorbereitung und Freigabe allein bedeuten noch keinen erfolgreichen Lauf
oder eine Produktionsfreigabe.

Das neue Leroy-Fenster ist nach 91,75 Minuten abgeschlossen. Alle sieben
Dienste sind am 13. Oktober um etwa 23:35 Uhr wieder gestartet und vor
23:38 Uhr gesund und stabil geprüft. Der Controller bleibt unverändert,
ohne neuen Neustart oder Cgroup-OOM. Der NAS-Swap-Wächter beendet den
Testgast während der Rust-Phase; nach Abschalt-Timeout ist die QEMU-
Beendigung ausdrücklich als erzwungen dokumentiert. Die originalen
Leroy-Läufe bleiben fehlgeschlagen und ihre volle Release-Abnahme unvollständig.
Die Details und Beobachtungslücken stehen in [nas-full-release.md](nas-full-release.md).

Die abgeschalteten Platten dieses Laufs und der früheren Serie `n` sind
anschließend byte- und eigentümergetreu sowie mit SHA-256-Prüfung auf HDD
archiviert. Alle Originalbelege bleiben erhalten. Auf SSD stehen danach
86.001.229.824 Bytes frei. Während dieser Archivierung laufen alle sieben
Dienste; es wird keine zusätzliche Archivierungslast in eine aktive
Originalprüfung eingebracht.

Das zweite Fenster für den privaten Jenkins beginnt am 13. Oktober um
**23:55:44 Uhr Berliner Zeit**. Die absolute Endzeit ist der 14. Oktober um
**03:55:44 Uhr**, der Wächter beginnt spätestens um 03:40:44 Uhr mit der
Wiederherstellung. Davor werden erneut gesunde Dienste, ruhige produktive
Jenkins-Historien und unveränderte Steuerungsinfrastruktur geprüft.
Die Jenkins-Zielbasis wird frisch aus dem ursprünglichen sauberen Snapshot
gestartet; keine Daten oder bestandenen Checks des abgebrochenen Leroy-Gasts
werden übernommen. Das zweite Fenster ist zum jetzigen Dokumentationsstand
noch in Bearbeitung.

## Abschluss am 14. Oktober

Auch das Jenkins-Fenster ist abgeschlossen. Es dauert 94,12 Minuten;
alle sieben ursprünglichen Container sind um etwa 01:30 Uhr wieder gestartet
und vor 01:33 Uhr gesund und stabil geprüft, vor der Endzeit 03:55:44 Uhr.
Die Container-IDs, Images und Konfigurationen sind unverändert. Ziel-VM,
privater Jenkins und eigene Jobworker sind aus, beide Wächter beendet.
Vollständige native Jenkins-Historien bleiben ruhig. Es wird kein weiterer
Original-CI-Lauf gestartet und kein Fenster verlängert oder neu eröffnet.

Jenkins besteht alle 42 Browserfälle sowie Format und Clippy. Derselbe
Frontend-Komponententest schlägt mit 97/98 auch hier fehl. In der Rust-Phase
unterschreitet der NAS-Swap die unveränderte Reserve; nach Abschalt-Timeout
wird QEMU zwangsweise beendet. Die vollständige Original-Qualitäts- und
Release-Abnahme bleibt unter beiden Engines unvollständig. Der Controller
behält in beiden Fenstern denselben Prozess und Container ohne neuen OOM
oder Neustart. Die Vergleichsgrenzen, Beobachtungslücken und unterschiedlichen
erzeugten Verifikations-Image-IDs stehen in [nas-full-release.md](nas-full-release.md).

Die jeweiligen Abschlussbelege heißen `window-result.json`,
`recovery-verification.json`, `control-summary.json` und
`terminal-outer-vm-proof.json` in den beiden Wartungsordnern. Der gemeinsame
Vergleichsordner enthält `paired-attempt-report.json` und
`final-operations-proof.json`. Die vollständige Produktionsfreigabe bleibt offen.

## Vorbereitete neue Serie nach Controller-Korrektur

Vorbereitungsstand vor der neuen Freigabe: Die zuvor genehmigten beiden
Vierstundenfenster sind abgeschlossen. Für weitere Dienstpausen benötigt diese
neue Serie deshalb eine neue Freigabe. Diese ist inzwischen erteilt; der
aktuelle Ablauf steht im anschließenden Abschnitt.

Der neue Vergleich heißt `full-release-reconcile8g-20261014`. Die beiden
vorbereiteten Fenster heißen `resource-window-reconcile8g-leroy-20261014` und
`resource-window-reconcile8g-jenkins-20261014`. Jedes besitzt ein eigenes
unveränderliches Vierstundenbudget ab der ersten Stop-Anforderung. Der Wächter
auf dem NAS beginnt spätestens 15 Minuten vor Ablauf mit der Wiederherstellung,
auch wenn die Windows-/SSH-Verbindung verloren geht. Keine Frist wird verlängert.

In jedem Fenster dürfen ausschließlich die gleichen sieben Container pausieren:
Paperless, Sonarr, Radarr, SABnzbd, Plex, yt-downloader-service und
mail-ingest-service. Ihre Anwendungen sind während der Pause nicht verfügbar.
Nach jedem Fenster werden dieselben Container mit ihren geprüften ursprünglichen
IDs, Images und Konfigurationen gestartet und stabil gesund geprüft. Alle sieben
müssen wieder gesund sein, bevor das zweite Fenster vorbereitet werden darf.
Produktiver Jenkins wird nicht angehalten; aktive Builds und Änderungen seiner
Buildzähler verhindern neue konkurrierende Testarbeit.

Der konkrete Ablauf pro Fenster ist:

1. Freigabe, ruhige vollständige Jenkins-Historien, inaktive eigene Testjobs,
   gesunde Dienste und mindestens 70 GiB freien SSD-Speicher prüfen. Das
   Controllerimage muss genau dem mit 34 echten PostgreSQL-Tests qualifizierten
   Image entsprechen; Konfiguration und Vergleichsskripte werden gebunden.
2. NAS-Wiederherstellungswächter aktivieren, die sieben Dienste geordnet pausieren.
3. Eine frische ursprüngliche Graphato-Gruppe `server-test` mit eingefrorenem
   Commit `0ad540dd578033d45e4d0c25d89fbe57b32102a4`, unveränderten Quellen und
   Tests ausführen. Beide Engines erhalten `nas-8g-ssd-soft-ram-3584` und den
   separat qualifizierten PostgreSQL-Init-Override. Die eigenen Rust-Kennungen
   sind `full-release-reconcile8g-20261014-rust-leroy` und
   `full-release-reconcile8g-20261014-rust-jenkins`.
4. Originaljob-Erfolg, vollständiges Archiv, ursprüngliches Rust-Inventar und
   Fixture-Bereinigung prüfen. Beobachtete NAS-RAM-/Swap-Reserveunterschreitungen,
   fehlende Belege oder Fehler sperren den Volllauf. Ergebnisse werden erhalten;
   ein fehlgeschlagener Job wird nicht automatisch erneut gestartet.
5. Nur bei bestandener Vorprüfung und mindestens zwei Stunden plus 15 Minuten
   Restbudget eine weitere frische Zielbasis für den ursprünglichen vollständigen
   Release-Ablauf starten. Keine Ergebnisse oder Buildverzeichnisse der
   Vorprüfung übernehmen. Controller, Ressourcen und Konfiguration bleiben
   zwischen den beiden Engine-Fenstern identisch.
6. Originalarchive, Testinventare, Fehler, Beobachtungslücken und Bereinigung
   sichern, Testlast beenden und alle sieben Dienste wiederherstellen. Geschlossene
   Platten bei Bedarf erst nach der Wiederherstellung bytegeprüft archivieren;
   keine parallele Archivierung während ursprünglicher CI-Messungen.

Die lokale Vorlage liegt privat unter
`test-results/nas-parity/followup/reconcile8g-window-plan-20261014/prepared-plan.json`
mit `user_approved: false`. Die ausführbare Freigabedatei `approval.json` wird erst
nach einer neuen ausdrücklichen Nutzerfreigabe erstellt. Es sind keine neuen
Wächter installiert und keine neuen Dienste gestoppt.

Die vorbereitende Archivierung ist abgeschlossen: Drei geschlossene
Rust-Diagnoseplatten sind vollständig gehasht und unabhängig gegengelesen
auf HDD erhalten; rund 80 GiB SSD sind frei. Der Abschlussbeleg vom 14. Oktober
16:23:56 UTC bestätigt sieben gesunde Anwendungen mit unveränderten IDs und
Konfigurationen, keine aktiven Testworker und keinen aktiven Wartungswächter.
Sonarr und SABnzbd besitzen zwischenzeitlich neue Prozesse unbekannter Ursache;
die [gesonderte Beobachtung](nas-rust-memory.md) bleibt erhalten. Vor einer
tatsächlichen Pause werden alle Betriebsbedingungen erneut geprüft.

Nach Freigabe beginnt das erste Fenster mit:

```powershell
.venv/Scripts/python.exe scripts/run_nas_full_release_window.py --round full-release-reconcile8g-20261014 --engine leroy
```

Das zweite Fenster verwendet `--engine jenkins` und beginnt erst nach bestätigter
Wiederherstellung und erneuter Ressourcenprüfung. Neue ursprüngliche Anwendungsfehler
bleiben erhalten; weder Quellen noch Tests oder Fristen werden für ein positives
Ergebnis geändert. Der Stand und die Grenzen stehen in [nas-rust-memory.md](nas-rust-memory.md).

## Neue Freigabe und erstes Fenster am 14. Oktober

Der Nutzer hat die zwei neuen Fenster ausdrücklich mit jeweils höchstens vier
Stunden freigegeben und die Wiederherstellung aller sieben Dienste nach jedem
Fenster verlangt. Die getrennte `approval.json` enthält diese Anweisung,
Zeitpunkt, unveränderten Umfang und die vorbereiteten Skripthashes. Die zuvor
ausgeschaltete Ziel-VM, inaktive Testjobs, ruhige produktive Jenkins-Historien,
gesunde NAS-Anwendungen und das PostgreSQL-geprüfte Controllerimage sind vor
dem ersten Fenster erneut geprüft.

Das Leroy-Fenster beginnt am 14. Oktober um **18:33:24 Uhr Berliner Zeit**;
die absolute Endzeit ist **22:33:24 Uhr**. Der NAS-Wächter ist vor dem ersten
Stop aktiviert und beginnt spätestens um 22:18:24 Uhr die Wiederherstellung.
Die sieben Dienste werden geordnet gestoppt. Danach beginnt zuerst die
ursprüngliche Rust-Vorprüfung. Für dieses neue Fenster liegt noch kein
abgeschlossenes Abnahmeergebnis vor. Das zweite Fenster wird erst nach der
bestätigten Wiederherstellung vorbereitet.

Das erste Fenster ist inzwischen geschlossen. Alle sieben ursprünglichen
Container sind um **18:58:03 Uhr** wieder gestartet; bis **19:00:38 Uhr** ist
ihre Gesundheit und Stabilität bestätigt. Die Stop-/Start-Spanne beträgt
24,65 Minuten. IDs, Images und Konfigurationen sind unverändert. Der Controller
behält seinen Prozess ohne Neustart oder neuen Cgroup-OOM, produktive Jenkins-
Historien und Buildzähler sind ruhig. Der ursprüngliche Rust-Job endet als
`interrupted`; der Volllauf wird durch die Eingangskontrolle ausdrücklich
nicht gestartet. Es ist kein NAS-Ressourcenabbruch dieses Jobs belegt.

Die geschlossene Testplatte wird bei vollständig wiederhergestellten Diensten
und ohne aktive CI bytegeprüft archiviert. Erst danach wird das zweite genehmigte
Fenster mit demselben Controller-/Workerstand und demselben Ressourcenprofil
vorbereitet. Seine Vierstundenfrist beginnt erst mit seiner eigenen ersten
Stop-Anforderung. Quellen, Tests und Schutzfristen bleiben für die Gegenprobe gleich.

Das zweite Fenster beginnt um **19:09:19 Uhr Berliner Zeit**, mit absolutem
Ende um **23:09:19 Uhr** und Wiederherstellung spätestens ab 22:54:19 Uhr.
Vorher ist die erste geschlossene Platte vollständig gehasht und unabhängig
gegengelesen auf HDD archiviert; auf SSD sind wieder rund 80 GiB frei.
Alle sieben Anwendungen sind an der Übergangsgrenze gesund. Der zweite
Wächter ist vor dem Stop aktiv. Controllerimage, tatsächliches NAS-Workerimage,
Runner-Konfiguration und Vergleichsskripte stimmen mit dem ersten Fenster
überein. Der lokale Worker-Quelltext enthält währenddessen eine getrennt
vorbereitete Taktkorrektur; sie wird vor Ende der Gegenprobe nicht auf dem NAS
gebaut oder installiert und verändert weder Graphato noch diese Messung.

## Abschluss der beiden neuen Fenster und anschließende Worker-Korrektur

Auch das zweite Fenster ist geschlossen. Seine Stop-/Start-Spanne beträgt
30,95 Minuten; alle sieben ursprünglichen Anwendungen sind am 14. Oktober
um **19:42:49 Uhr Berliner Zeit** wieder gesund bestätigt. IDs, Images und
Konfigurationen stimmen mit dem jeweiligen Fensterbeginn überein. Beide
Wiederherstellungen liegen vor den genehmigten Vierstundenfristen. Die
geschlossenen Fenster werden nicht erneut geöffnet oder verlängert.

Der private Jenkins-Qualitätsjob `graphato-postdeploy-quality#24` scheitert
während der ursprünglichen Rust-Prüfung an der NAS-Swap-Schutzreserve. Der
Wächter misst 2341412 KiB freien Swap bei mindestens 2359296 KiB; die eigene
Ziel-VM wird geordnet beendet (`forced: false`, QEMU-Exit 0). Die ergänzende
Speicherreihe enthält später auch niedrigere Werte. Ein vollständiges
Original-Rust-Archiv fehlt, deshalb startet der Release-Volllauf nicht.
Der Controller behält seinen Prozess ohne neuen Cgroup-OOM; native Jenkins-
Historien und Buildzähler sind an den geprüften Grenzen ruhig. Messlücken
bleiben im Nachweis erhalten.

Erst nach beiden abgeschlossenen Fenstern wird die belegte zusätzliche
Worker-Wartezeit korrigiert. Das Linux-qualifizierte Image
`sha256:0beba2d521cb061818bbf18295ab0329094d31092b4a2cbd8cfa24dca2cf74dc`
ist anschließend ausschließlich im Graphato-Profil des eigenen Test-Runners
aktiviert. Nur dieser Runner wird dafür neu gestartet; Controller, Datenbank,
Testdaemon und produktiver Jenkins bleiben dabei unverändert. Geschützte
Rückfallkonfiguration und vorheriges Image bleiben erhalten. Diese Installation
ist kein bestandener ursprünglicher CI-Lauf. Für kleine getrennte Diagnosen
bleiben alle sieben NAS-Anwendungen aktiv; eine weitere Dienstpause benötigt
ein neues Wartungsfenster.

Private Nachweise: `window-result.json` und `recovery-verification.json` in
beiden `resource-window-reconcile8g-*-20261014/`-Ordnern,
`original-rust-gate-report.json` im Planordner sowie `qualification-proof.json`
und `deployment-proof.json` in `worker-lease-cadence-20261014/`.

## Vorbereiteter einmaliger Kapazitätstest: neue Freigabe erforderlich

**Fortsetzung am 14. Oktober:** Der Nutzer hat das einmalige 60-Minuten-Fenster
inzwischen ausdrücklich freigegeben. Der vorbereitete Quellstand stimmt mit
allen gespeicherten Hashes überein. Die eigene `approval.json` bewahrt diese
neue Freigabe getrennt von den geschlossenen Vierstundenfenstern.
Der NAS-Wächter ist vor dem ersten Stop aktiv. Das Fenster beginnt um
**21:45:54 Uhr Berliner Zeit**, endet spätestens um **22:45:54 Uhr** und
plant die Wiederherstellung ab **22:30:54 Uhr**. Der Kapazitätstest und die
Wiederherstellung sind noch nicht abgeschlossen. Es startet kein Graphato-Job.
Die folgende Vorbereitung bleibt als ursprünglicher Plan erhalten.

Die anschließende Diagnose mit allen sieben Anwendungen aktiv hält 4608 MiB
zusätzlichen anonymen Gastspeicher. Der nächste 512-MiB-Schritt wird bei
2721372 KiB freiem NAS-Swap durch eine vorsichtige Eingangskontrolle verweigert;
die unveränderte Schutzreserve beträgt 2359296 KiB. Kein ursprünglicher CI-Job
wird gestartet. Die Testbelegungen werden freigegeben, die VM wird geordnet
beendet, alle sieben NAS-Dienste bleiben gesund. Dies qualifiziert weder
6144 MiB Last noch den ursprünglichen Rust-Lauf.

Für die nächste konkrete Kapazitätsprüfung ist **ein neues, einmaliges Fenster
von höchstens 60 Minuten** vorbereitet. Es ist noch nicht freigegeben oder auf
dem NAS eingerichtet. Die alten Vierstundenfenster bleiben geschlossen.
Der Plan ist lokal unter `capacity-window-plan-20261014/prepared-plan.json`
mit `user_approved: false` gespeichert. Das ausführbare Verfahren verweigert
eine neue Dienstpause ohne eigene ausdrückliche Freigabe, passende Quellhashes
und genau den folgenden Umfang:

1. Ruhige vollständige native Jenkins-Historien, inaktive Testjobs, sieben
   gesunde unverändert konfigurierte Anwendungen, ausgeschaltete Ziel-VM und
   privaten Jenkins prüfen. Die qualifizierten Controller-/Workerstände sowie
   mindestens 50 GiB freien SSD-Speicher bestätigen; die VM-Reserve bleibt 40 GiB.
2. Einen neuen NAS-Wiederherstellungswächter unter
   `resource-window-capacity-order0-20261014` vor dem ersten Stop aktivieren.
   Die absolute Stunde zählt ab der ersten Stop-Anforderung. Spätestens nach
   45 Minuten beginnt der Wächter die Wiederherstellung; ein Verbindungsverlust
   nach Windows verlängert die Frist nicht.
3. Ausschließlich dieselben sieben Anwendungen pausieren. Den vorhandenen
   privaten Jenkins mit unveränderter Konfiguration starten und inaktiv halten;
   seine Queue und Buildzähler prüfen. Produktiver Jenkins und die übrige
   NAS-Infrastruktur bleiben aktiv und unverändert.
4. Eine neue Wegwerf-VM `capacity-window-order0-20261014` mit 8 GiB Gast-RAM,
   unveränderten NAS-Schutzgrenzen, `memory.high=3584 MiB`, PostgreSQL-Init und
   Gast-Reporting-Order 0 starten. In 512-MiB-Schritten höchstens 6144 MiB
   zusätzliche anonyme Last belegen und bei ausreichender Reserve 60 Sekunden
   halten. Der Lastprozess gibt seine Belegungen bei ausbleibenden Steuerbefehlen
   selbstständig frei. Vor jedem Schritt gelten die zusätzlichen vorsichtigen
   Zulassungsgrenzen. Eine Verweigerung bleibt ein fehlender Kapazitätsnachweis.
5. Speicherproben, Teilbelegung, Fehler, Beobachtungslücken und das Ergebnis
   sichern. Ziel-VM und privaten Jenkins beenden, dieselben sieben Anwendungen
   starten und Gesundheit sowie Stabilität bestätigen. Der Wächter stellt
   auch bei Fehlern wieder her. **Es startet in diesem Fenster kein Graphato-
   Originaljob und kein vollständiger Releasejob.**

Ein positiver synthetischer Nachweis erfordert tatsächlich gehaltene Last,
geprüfte Stichproben der behaltenen Seiten, unveränderte Hostreserven, keinen
neuen OOM, eine abgeschaltete VM und ruhige native Jenkins-Historien. Er
ersetzt keine Originaltests. Ein erneuter Volllauf wird aus diesem Ergebnis
nicht automatisch abgeleitet; zunächst entscheidet der Kapazitätsnachweis,
ob eine weitere ursprüngliche Rust-Prüfung überhaupt sinnvoll ist.

Die Vorbereitung ist ohne NAS-Aktionen ausführbar:

```powershell
.venv/Scripts/python.exe scripts/run_nas_capacity_window.py --prepare
```

`--run-approved` benötigt eine neue, zum vorbereiteten Plan passende
`approval.json`. Sie wird ausschließlich nach ausdrücklicher Nutzerfreigabe
angelegt; ältere Freigaben werden nicht übernommen. Die neue Vorbereitung
und ihre Quellhashes bleiben von den ursprünglichen fehlgeschlagenen
Abnahmen getrennt.

## Abschluss der Stunde und getrenntes Nachtfenster am 14./15. Oktober

Das genehmigte einstündige Fenster begann am 14.10. um 21:45:54 Uhr Berlin.
Alle sieben Anwendungen waren um 21:57:21 wieder gestartet; ihre Gesundheit
und Stabilität ist anschließend bestätigt. Kein Graphato-Originaljob wurde
gestartet. 5120 MiB Zusatzlast bestanden, die weitere Zuteilung wurde wegen
der vorsichtigen Reserveprüfung verweigert. 6144 MiB bleiben unqualifiziert.
Der Abschlussbeleg bestätigt unveränderte Steuerdienste, keinen neuen OOM
und ruhige native Jenkins-Buildhistorien. Dieses Fenster bleibt geschlossen.

Der Nutzer hat danach ausdrücklich erklärt: „Das Fenster wird die ganze
Nacht laufen nur zur Info daher tob dich ruhig aus“. Diese neue Freigabe
wird getrennt unter `resource-window-night-20261014` umgesetzt. Mangels
anderer Endzeit ist die vorsichtig festgelegte absolute Wiederherstellungszeit
15.10.2026, 06:00 Uhr Berlin; der NAS-Wächter beginnt spätestens um 05:45 Uhr.
Die Zeit verlängert sich weder durch neue Phasen noch Verbindungsabbrüche.
Native Jenkins-Buildzähler lösen weiterhin den Abbruch und die Wiederherstellung
aus. Ausschließlich dieselben sieben Dienste dürfen pausieren.

Ablauf in `scripts/run_nas_night_window.py`: Ein eigener NAS-Wächter startet
vor dem ersten Stop. Höchstens drei neue Kapazitätsproben nutzen getrennte
VMs mit 8 GiB Gast-RAM und 3584, 3840 bzw. 4096 MiB `memory.high`. Die
Startprüfsumme bleibt vollständig, gelesene Snapshotseiten erhalten nur
Cachefreigabe-Hinweise; die weiche Grenze greift schon vor dem Gaststart.
Die Probe muss 6144 MiB für 60 Sekunden halten, behaltene Seiten prüfen und
alle bisherigen Reserven einhalten. Ein unterschrittener Schutzwert oder
ein technischer Fehler beendet die Folge zur Untersuchung.

Erst ein positiver Kapazitätsnachweis erlaubt je einen ursprünglichen
Rust-Job unter Leroy und privatem Jenkins. Nur zwei vollständige erfolgreiche
Rust-Inventare samt gebundenen Belegen und sauberem Abschluss erlauben die
vollständigen Graphato-Release-Läufe. Gleiche Quellen, Tests, Rate Limits und
Fixture-Grenzen bleiben eingefroren. Abgeschlossene Testplatten werden bei
Bedarf außerhalb der CI-Last bytegeprüft auf HDD archiviert. Bei Abschluss
oder Fehler werden VM und privater Jenkins beendet und alle sieben
Anwendungen wiederhergestellt und dreimal auf Gesundheit/Stabilität geprüft.
Eine Produktionsumschaltung ist nicht Teil der Nachtfreigabe.

Der anschließende begrenzte Originalvergleich wird separat unter
`resource-window-original-night-20261014` vorbereitet. Das Kapazitätsfenster
wird vorher geschlossen und die Gesundheit/Stabilität der sieben Dienste
bestätigt. Die ausdrückliche Nachtfreigabe bleibt die Grundlage; die neue
Phase erhält **dieselbe absolute Endzeit 06:00 Uhr**, keine neue Zeitspanne
bis zehn Stunden nach ihrem Start. Der Wächter beginnt weiter um 05:45 Uhr
die Wiederherstellung. Der ausführbare Plan bindet die tatsächlichen
Kapazitätsbelege und alle verwendeten Skripte per SHA-256.

Die Fenster A und B sind geschlossen und mit sieben gesunden, stabilen
Anwendungen abgeschlossen. B endete nach einer Leroy-Lease-Unterbrechung
und einem späteren NAS-RAM-Schutzabbruch beim privaten Jenkins #25.
Die separat vorbereitete Fortsetzung C verwendet erneut frische Baselines,
die qualifizierte Runner-Korrektur und numerische Transportdiagnosen.
`memory.high` sinkt auf 3584 MiB; Gast-RAM, originale Containergrenzen und
NAS-Schutzwerte bleiben unverändert. Die bestehende ausdrückliche
Nachtfreigabe trägt dieses neue Journal; die Endzeit bleibt absolut
06:00 Uhr Berlin mit Wiederherstellungsbeginn um 05:45 Uhr.
Abgeschlossene Fenster werden weder wieder geöffnet noch verlängert.

C wurde ebenfalls geschlossen: Die eigene VM fuhr nach dem NAS-Swap-
Schutz sauber herunter. Alle sieben Anwendungen waren anschließend gesund
und stabil; der produktive Jenkins und die Steuerdienste blieben unverändert.
Der ursprüngliche Jenkins-Job und vollständige Releases wurden nicht gestartet.

Nach diesem Abschluss wurde ausschließlich der eigene Docker-Testpool auf
einen frischen SSD-Laufzeitbereich vorbereitet. Daten-Volumes und der gesamte
alte Pool bleiben erhalten; ein zusätzlicher schreibgeschützter Mount hält
das alte benannte Volume ausdrücklich referenziert. Die sieben NAS-Anwendungen
liefen während dieser Vorbereitung. Der neue Beleg umfasst unveränderte Worker-
Image-Inhalte und 28 bestandene Linux-Tests.

Die anschließende Fortsetzung D erhält das getrennte Journal
`resource-window-original-night-20261014-d`. Der mittlere VM-Wert von
3840 MiB wird für beide Engines gleich gesetzt. Die ausdrückliche Nachtfreigabe
gilt weiterhin mit unveränderter absoluter Endzeit 06:00 Uhr Berlin und
Wiederherstellungsbeginn um 05:45 Uhr. Alte Fenster bleiben geschlossen.

D endete vor einem CI-Dispatch an einer alten privaten Jenkins-ID im
Abnahmewerkzeug. Der Abschluss bestätigt sieben gesunde und stabile Dienste.
Die folgenden Prüfungen nutzen die belegte neue ID, das Snapshot-Image und das
bisherige Daten-Volume; die Identitätsgrenze bleibt damit erhalten.

E verwendet ein eigenes Journal und unmittelbar die vollständigen ursprünglichen
Release-Läufe beider Engines. Deren Rust-Prüfungen werden vollständig ausgeführt;
zusätzliche eigenständige Rust-Vorläufe entfallen. Die einmal angehaltene lokale
Vorbereitung hatte noch keinen NAS-Wächter und keine CI-Ausführung angelegt,
weil der Mail-Dienst nach einem vorübergehenden IMAP-Verbindungsfehler ungesund
war. Nach erfolgreichem Poll mit unveränderter Konfiguration wurde sie fortgesetzt;
die ersten Belege wurden vorher verschoben und erhalten. Die absolute Endzeit
bleibt 06:00 Uhr Berlin, Wiederherstellungsbeginn 05:45 Uhr.
