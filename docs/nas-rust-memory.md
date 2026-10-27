# Rust-Ressourcenqualifikation auf dem NAS

## DNS-Fehler unter beiden CI-Systemen

Unter der korrigierten DNS-Testumgebung wurde im originalen Leroy-Lauf #181
das Image erfolgreich gebaut. Danach löste ein lokales JSON-Leserennen die
Wiederherstellung der Abnahmesteuerung aus. Die gestoppte Platte enthält
`Cancelled` und vollständige Bereinigung: 1.311,774 Sekunden erfolgreicher
Imagebau, nur 14,189 Sekunden gestartete Rust-Kompilierung. Das ist kein
vollständiger Rust-Nachweis und kein belegter Graphato-Testfehler. Die Offline-Daten
bleiben getrennt vom ursprünglichen fehlgeschlagenen CI-Abschluss. Alle sieben
Dienste sind wieder gesund. Der neue Versuch U verwendet dieselbe DNS-Konfiguration
und eine durch Gegenbeispiele geprüfte atomare Übergabe der Fortschrittsdaten.

Jenkins #30 und Leroy #180 scheiterten auf dem eingefrorenen Stand bereits beim
Installieren von `pnpm@11.1.3` mit `EAI_AGAIN registry.npmjs.org`. Kein Rust-Test
wurde ausgeführt. Leroy veröffentlichte im neuen Lauf Ergebnis, laufgebundene
Abbruchquittung und Diagnosearchiv vollständig. Beide Fenster sind geschlossen,
die sieben Dienste sind gesund und stabil, Platten bytegeprüft archiviert.

Im Gast antwortete der virtuelle DNS-Pfad bei einer begrenzten Probe nicht,
während die direkte öffentliche Anfrage erfolgreich war. Versuch T konfiguriert
deshalb ausschließlich den frischen Gast mit direkten Upstreams und prüft den
Stand vor und nach dem Auftrag. Die Per-Link-Konfiguration nutzt die dokumentierten
[`resolvectl`-Befehle](https://github.com/systemd/systemd/blob/v255/man/resolvectl.xml).
Die unveränderte Baseline, Anwendung und Tests bleiben getrennt von dieser
ausdrücklich geänderten DNS-Testumgebung. NAS-Einstellungen und ursprüngliche
Build-Limits werden nicht geändert. Der vollständige Rust-Nachweis fehlt weiter.

## Originalversuch P am 16. Oktober

Die getrennte Jenkins-Referenz #30 scheiterte bereits beim Imagebau an
`EAI_AGAIN registry.npmjs.org`; kein Rust-Container und keine Rust-Tests.
Die originale Ergebnisquittung und das Diagnosearchiv sind veröffentlicht,
Bereinigung vollständig, kein angeforderter Abbruch. Die sieben Dienste waren
vor 09:01 gesund und stabil, VM sauber beendet, eigene RAM-Datei freigegeben
und Platte bytegeprüft archiviert. Beide P-Fenster sind geschlossen.

Die Jenkins-Speicherreihe enthält 82 Proben, davon 68 zugeordnet. Kleinste
beobachtete NAS-Werte: 3.252.972 KiB RAM und 6.169.448 KiB Swap. Der private
Java-Prozess erreichte in 97 Proben höchstens 726.124 KiB RSS und keinen Swap.
Das betrifft ausschließlich diesen Imagebau und beweist kein Verhalten unter
vollständiger Rust-Last. Die 18 fehlgeschlagenen SQL-Prozessaufrufe bleiben
Beobachtungslücken; erfolgreiche direkte SQL-Proben allein schließen keine
Datenbankpause in diesen Lücken aus.

Die unveränderten Checkouts unterscheiden sich nicht; der Leroy-Adapter hatte
jedoch eigene SSH-Keepalives und einen gemeinsamen Master. Für den frischen
Versuch S ist er auf die ursprünglichen Optionen und einzelne Verbindungen
umgestellt. 37 Prüfungen im genauen NAS-Worker-Image bestehen. Das erklärt
weder den Rust-Timeout noch den DNS-Ausfall bereits ursächlich.

Der unveränderte Rust-Auftrag unter Leroy #179 endete um 00:12:54 Berliner Zeit
mit Exitcode 1 nach einem SSH-Timeout zum isolierten Ziel. Es gibt kein vollständiges
Testinventar. Das einzige veröffentlichte
Artefakt ist `cancellation.json` (189 Byte, `unconfirmed`, `JSONDecodeError`).
Der BuildKit-Export endete in 372,9 Sekunden; die anschließende Rust-Kompilierung
begann unter den gemessenen ursprünglichen Grenzen von 6 GiB ohne Swap und zwei
CPUs. Dieser Beginn ist kein erfolgreicher Rust-Abschluss. Ein Test- oder
Compilerfehler ist durch den Transportabbruch nicht belegt.

Die API blieb erreichbar; um 00:27 war der Runner mit letzter Meldung 23:55:50
offline. Auch die NAS-Verwaltungsanmeldung und Belegsammlung fielen aus.
Der NAS-Wächter beendete die VM um 03:15:34 sauber und hatte um 03:15:57 alle
sieben Originalcontainer gestartet. Seit dem wieder verfügbaren Zugang am Morgen
sind alle sieben Dienste dreimal gesund und stabil bestätigt. Kein neuer NAS-OOM,
keine geänderte Infrastruktur, eigene RAM-Datei freigegeben. Die Gesundheit vor
der festen Endzeit wurde wegen des Zugangsausfalls nicht beobachtet.

Die unverändert gelesene Testplatte enthält die passende Originalquittung:
`TimeoutExpired` nach 6.390,356 Sekunden, `cancelled: false`, `cleanupComplete: true`.
Die Kompilierung überschritt mit 5.412,311 Sekunden ihre ursprüngliche Frist;
der Compose-Prozess endete mit -9, die anschließende Bereinigung mit 0.
`rust-test-times.json` enthält null ausgeführte Tests und `complete: false`.
Diese zusätzliche Diagnostik ist kein von Leroy veröffentlichtes CI-Artefakt.
Die Speicherreihe enthält 1.144 Proben: 707 zugeordnet, 437 fehlend oder nicht
zuordenbar, 339 Gast-Lesefehler. Kleinste beobachtete NAS-Werte: 3.415.512 KiB RAM,
6.144.252 KiB Swap; NAS-OOM blieb drei. Der Gast-OOM-Zähler null ist nur teilweise
beobachtet. Der Worker-Beobachter selbst hat keinen vollständigen Abschlussbeleg
und meldete einen eigenen Timeout beim Aufräumen. Der Folgeablauf bleibt gestoppt;
für P gibt es keinen erfolgreichen ursprünglichen Rust- oder Produktionsnachweis.

## Abschluss I und neuer Versuch J

Leroy #178 ist wegen nicht bestätigter Worker-Lease unterbrochen. Trotz schneller
direkter API-Proben zeigten die letzten Worker-Anfragen fünf bis sieben Sekunden
Laufzeit, geringe Thread-CPU-Zeit und viele Major Page Faults. Die offline gelesene
Originalquittung enthält `Cancelled`, 3.949,918 Sekunden und erfolgreiche Bereinigung;
kein vollständiges Testinventar. Die sieben Dienste sind seit 20:21:07 Berliner Zeit
gesund und stabil, VM sauber beendet, RAM-Datei freigegeben und Platte bytegeprüft
archiviert. Die lokalen Beobachtungslücken bleiben erhalten.

Die bestehende Worker-Reservierung war durch `system.slice` und die äußere
Test-Engine mit jeweils `memory.low=0` nach oben begrenzt. Der tatsächliche NAS-Mount
verwendet bereits `memory_recursiveprot`. Laut
[Kernel-Dokumentation](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html)
begrenzt die Hierarchie den wirksamen Schutz; rekursive Anwendung schützt einen
Teilbaum ohne einzelne Änderungen an allen Blättern. Deshalb erhielt ausschließlich
die eigene Test-Engine einen direkten Root-Parent und 1.536 MiB `memory.low`.
Das ist weicher Schutz, keine harte RAM-Zuteilung. Globale Gruppen und NAS-Swap
bleiben unverändert. Gleiche Images, Volumes, innere Container-IDs und harte Limits
sind vor/nach dem kontrollierten Engine-Neustart geprüft. 28 Linux-Workerprüfungen
bestehen. Ein exklusiver Ursachenbeweis oder erfolgreicher Original-Rust-Lauf folgt
daraus nicht; Versuch J benötigt frische eigene Kapazitäts- und CI-Nachweise.

J wurde vor dem ursprünglichen CI-Auftrag durch einen SSH-Transportfehler der
Abnahmesteuerung abgebrochen. Die Probe hatte erst 2.048 MiB erreicht; ein
vollständiger Kapazitätsnachweis fehlt. Die sieben Dienste sind wieder gesund
und stabil, die VM ist sauber beendet. Der Trace enthält nur 14 Proben, davon
zehn zugeordnet und vier Gast-Lesefehler, ohne neuen NAS-OOM. RAM-Datei freigegeben,
Testplatte mit 4.341.825.536 Byte bytegeprüft archiviert, SHA-256
`10ed23fee58c386f02b4850fa7fa70e2e3cd62bb81ae4fb10eaa1fdb53e1cd9b`.
Die SSH-Korrektur ändert keine Ressourcen oder Testfristen; Versuch K prüft
denselben Ressourcenstand frisch. Ein erfolgreicher Rust-Lauf fehlt weiterhin.

Auch K endete vor dem CI-Auftrag bei 2.048 MiB: Eine Leseabfrage produktiver
Jobstände verlor ihre SSH-Verbindung. Der äußere Beobachter blieb diesmal korrekt
beim selben Journal. Alle sieben Dienste sind seit spätestens 21:14:57 Berliner Zeit
wieder gesund und stabil, VM sauber beendet, RAM-Datei freigegeben. Die Platte
mit 4.342.218.752 Byte ist bytegeprüft archiviert, SHA-256
`76de02db91c6daf779cde8c8131230e46103dc27b6b9b2ec79c57cb4007e7dc7`.
K enthält 15 Trace-Proben, neun zugeordnet und sechs fehlend/uneindeutig;
kein neuer NAS-OOM. Die erweiterte Beobachtung wiederholt ausschließlich sichere
Zulassungs-Leseabfragen mit einem festen gemeinsamen Budget. Die Speicherprobe
selbst, ihre 1.200-Sekunden-Grenze, Markerprüfung, Originaltests und Limits
bleiben unverändert. Versuch L prüft diesen Stand frisch; 23 Linux-Gegenbeispiele
und 538 lokale Tests bestehen.

L schöpfte auch das feste Lese-Budget aus und endete vor dem CI-Auftrag bei
2.048 MiB. Kein Grenzwert wurde aufgehoben. Alle sieben Dienste sind wieder gesund
und stabil, VM sauber beendet, RAM-Datei freigegeben. Die bytegeprüfte Testplatte
mit 4.341.694.464 Byte hat SHA-256
`37fc6be450eb166ecc726d0dbf22ca24e6597bce467d4f0640df4228e132b4e7`.
14 Trace-Proben, davon 13 zugeordnet und eine fehlend/fehlerhaft; kein neuer NAS-OOM.

M verlagert ausschließlich die Vorbereitung der Kapazitätsprobe auf das NAS.
Der unveränderte Speicherfüller und seine Grenzen bleiben gleich; derselbe
kanonische, an den produktiven Container gebundene Lese-Code entscheidet vor
jeder Zuteilung. Der eigene temporäre Prozess erhält 32 MiB `memory.low`,
128 MiB `memory.max`, kein Swap, eine halbe CPU und maximal 64 Prozesse innerhalb
der vorhandenen Gruppe mit 448 MiB weichem Schutz. Die tatsächlichen Werte und
18 Gegenbeispiele sind auf dem NAS geprüft. Die Steuerung benötigt unter Last
keine neuen NAS-SSH-Anmeldungen. Die reale Probe erreichte 3.584 MiB trotz
verlorener externer SSH-Abfragen, endete aber beim nächsten Gast-Steuerbefehl.
Der Gastfüller protokollierte sieben Zuteilungen, keinen vollständigen Abschluss.
Die genaue Ursache des nicht erfolgreichen Gastbefehls ist noch offen.
Alle sieben Dienste sind seit 22:16:36 Berliner Zeit gesund und stabil;
VM sauber beendet, RAM-Datei freigegeben, kein neuer NAS-OOM. Von 22 Trace-Proben
sind nur zwei Gast/NAS-Werte zeitlich zugeordnet; Lücken bleiben ausdrücklich erhalten.
Kein ursprünglicher Graphato-CI-Auftrag wurde gestartet, kein Produktionsnachweis.
Im folgenden Versuch N konnte die ergänzte Diagnose den Fehler präzisieren:
Der Probe-Container endete mit Exit-Code 1; der offline gelesene Gastlog enthält
`TimeoutError` beim Warten auf den nächsten Socket-Aufruf. Zwischen letzter
Zuteilung und dem nächsten Befehl lag mehr als die unveränderte Leerlauffrist.
Die nächste Zuteilung scheiterte nach 0,681 Sekunden am bereits geschlossenen Socket.
Ein CPU-Limit- oder OOM-Abbruch erklärt dieses konkrete Ereignis nicht.
N ist geschlossen, alle sieben Dienste gesund und stabil, VM sauber beendet,
RAM-Datei freigegeben und Testplatte bytegeprüft archiviert.

O ergänzt deshalb reine Statusabfragen über den bereits aufgebauten privaten
Gast-Master-Socket, während die Hauptsteuerung die vollständigen Prüfungen ausführt.
Der Statuspfad kann keine neue Verbindung und keine Speicherzuteilung auslösen.
Seine kleinen Beobachtungen bleiben bis zum Beenden des Threads im RAM, damit
NAS-Journal-I/O keine erneute Statuslücke verursacht. Eine verlorene Antwort
bleibt unbekannt und verhindert einen Erfolgsbeleg. Zusätzliche Statusantworten
zählen weder als die drei Halteproben noch als vollständige Markerprüfung.
Alle ursprünglichen Probegrenzen und Fixture-Limits bleiben gleich.
41 Gegenbeispiele und die tatsächlichen NAS-Prozessgrenzen sind ohne VM/Last geprüft;
die neue reale Kapazitätsprüfung und vollständige Original-Rust-Abnahme stehen aus.
O bestätigte 21 zusätzliche Statusantworten, blieb aber bei 3.072 MiB stehen.
Nach einer 101 Sekunden dauernden Statusanfrage war der Socket geschlossen;
der Gastlog enthält wieder den Leerlauf-Timeout. Dies qualifiziert die
synthetische Vollkapazität nicht. Die lange Zwischenoperation ist noch offen.
O ist geschlossen, Dienste gesund und stabil, VM sauber beendet, RAM-Datei
freigegeben und Testplatte bytegeprüft archiviert.

P verwendet deshalb einen getrennten Ausführungsmodus für die vollständigen
unveränderten Originalaufträge. Das negative Zusatzstress-Ergebnis wird über
Prüfsummen gebunden und ausdrücklich nicht zu einem Erfolg umgedeutet.
`*-original-workload-qualification.json` beschreibt nur diesen Modus und fordert
den tatsächlichen Original-CI-Ergebnisbeleg. Es ersetzt keine Testquittung.
Der alte positive `*-file-memory-capacity.json` wird weder erzeugt noch übernommen.
Die physische Konfiguration, ursprünglichen Tests und Limits sowie Wächter bleiben
gleich; beide CI-Engines erhalten frische Zustände. Die synthetische
Vollkapazität bleibt unqualifiziert und wird als separate Betriebsgrenze dokumentiert.
19 Linux-Gegenbeispiele und die geänderten Operatorprogramme sind auf dem NAS
ohne VM oder Speicherlast geprüft; Original-Rust und vollständiger Release sind offen.
Die Windows-Seite behält den einen
Start über verlorene Antworten hinweg bei und akzeptiert nur eine vollständige,
an Quellen und Konfiguration gebundene Quittung nach Ende des temporären Dienstes.

## Abschluss H und neuer Versuch I

Der ursprüngliche private Jenkins-Qualitätsjob #29 endet als `FAILURE`.
Die unveränderte Zielquittung nennt `TimeoutExpired` nach 6.277,407 Sekunden,
vollständige Bereinigung und keine Benutzerstornierung. Der Compile-Aufruf
dauerte 5.407,672 Sekunden und endete mit 130; kein vollständiges Rust-Inventar
entstand. Jenkins veröffentlichte ausschließlich die 189 Byte große
`cancellation.json`. Vier separat ohne Boot, Mount oder Journal-Wiederholung
gelesene Originaldateien der Testplatte bleiben als zusätzliche Diagnosen
erhalten; sie sind ausdrücklich keine veröffentlichten CI-Artefakte.

Das originale Jenkins-Protokoll enthält `JENKINS-48300` und die Warnung über
den nicht aktualisierten Shell-Wrapper. Eine direkte Messung des verifizierten
privaten Java-Prozesses erfasst 18.868 KiB RAM, 530.960 KiB Swap und 1.722.396
größere Seitenfehler. Seine Cgroup und die Vorfahren im eigenen Docker-Pool
hatten keine wirksame Speicherreservierung. Wiederholte Leroy-API-Zeitüberschreitungen
treten auch ohne laufenden Leroy-Auftrag unter dieser Jenkins-Last auf.
Eine alleinige Ursache aller Wartezeiten ist nicht bewiesen.

Nach dem ursprünglichen Timeout wurde nur dieses Fenster wiederhergestellt.
Der Wächter musste die eigene VM zwangsweise beenden; `shutdown.json` fehlt,
Dateisystemkonsistenz und sauberer VM-Abschluss werden nicht bescheinigt.
Alle sieben Dienste sind seit 18:29:35 Berliner Zeit gesund und stabil.
Der ursprüngliche Jenkins-Job wurde nach Wiederaufnahme seiner Abschlussmetadaten
gesichert, ohne neuen Build, VM-Boot oder erneuten Testauftrag. Die Testplatte
mit 14.316.142.592 Byte wurde unabhängig kopiert und zurückgelesen:
`527dadd0e8192c2f4fa701bd6ad6a1b8ea0633c68e15c263087a9294694a320a`.
Die SSD-Kopie und die eigene 7-GiB-RAM-Datei sind freigegeben.
Der ursprüngliche Trace enthält 345 Proben, davon 180 streng zugeordnet und
87 Gast-Lesefehler. NAS-RAM mindestens 3.461.608 KiB, Swap mindestens
5.353.584 KiB; beobachteter NAS-OOM-Zähler unverändert 3. Die Lücken bleiben erhalten.

Nach dem geschlossenen Fenster wurde nur die eigene Controller-Reservierung
von 128 auf 256 MiB und die eigene übergeordnete Gruppe von 320 auf 448 MiB
angehoben. Images, Prozess-IDs, harte Grenzen, Swap-Verbot und übrige Ressourcen
blieben gleich; PostgreSQL-Dauerhaftigkeit bleibt eingeschaltet. Acht
Leerlaufproben liefern HTTP 200. Der neue Versuch I verwendet außerdem
64-KiB-Seitenrückgabe statt 4 KiB ausschließlich im Gast. Die vermutete geringere
Dateisystemlast der RAM-Datei ist noch zu bestätigen. Beide Engines benötigen
neue Kapazitätsproben und erfolgreiche Original-Rust-Läufe. Alte Ergebnisse
werden nicht dafür übernommen. Globale NAS-Swap- und Kernelparameter bleiben gleich.

Private Belege stehen unter `day-h-rust-jenkins-20261015/`,
`resource-window-day-20261015-h-rust-jenkins/`, `control-working-set-20261015/`
und `day-window-plan-20261015-i-rust-leroy/` im gemeinsamen Follow-up-Verzeichnis.

## Tagesfortsetzung am 15. Oktober

Die Freigabe „den ganzen Tag“ wird in getrennten Fenstern mit unveränderter
NAS-RAM-/Swap-Untergrenze genutzt. Das erste Fenster
`resource-window-day-20261015-rust-leroy` verwendet den eingefrorenen Stand
und den ursprünglichen einzelnen Rust-Schritt. Das separate Profil
`nas-8g-ssd-guest-swap-3840` ergänzt 4 GiB Swap auf der eigenen SSD-Testplatte
im Gast. Gast-RAM, äußeres RAM-/Swap-Budget und ursprüngliche Fixture-Limits
bleiben gegenüber dem vorherigen 3840-MiB-Profil gleich.

Die tatsächliche Builder-Instanz bestätigt 6 GiB RAM, 6 GiB kombiniertes
RAM-/Swap-Limit, zwei CPU sowie `memory.swap.max=0` und null Swap-Verbrauch.
Der Original-Rust-Lauf der Tagesserie A unter Leroy ist vollständig bestanden:
1.657 Tests, davon 1.625 erfolgreich, dieselben 32 ignorierten Testidentitäten
und kein Fehler. Die originale Quittung bestätigt die vollständige Bereinigung;
Inventar-SHA-256 ist unverändert
`081378cf2cc50f02203e85061246fc82a7172e1adde7c5da195889b3f0691724`.
Laufzeit der ursprünglichen Gruppe: 3.662,849 Sekunden. Quellen, Runtime,
Gast-Ressourcen und Swap-Konfiguration stimmen vor und nach dem Lauf überein;
der eingefrorene Checkout ist unverändert. Der produktive Jenkins blieb ruhig.

Die erfassten NAS-Minima liegen bei 306.964 KiB verfügbarem RAM und 2.437.800 KiB
freiem Swap; das sind nur rund 77 MiB Abstand zur Swap-Untergrenze. Der NAS-OOM-
Zähler blieb bei 3. Von 370 Speicherproben sind 141 Gast-/Hostwerte streng
zeitlich zugeordnet; Gastbeobachtungen bleiben damit lückenhaft. Die
kumulativen Gast-Swap-Zähler zeigten während Kompilierung und Tests null.
Ein ursächlicher Nutzen des neuen Gast-Swaps ist daher nicht nachgewiesen.
Der einzelne erfolgreiche Rust-Schritt ersetzt keine vollständige Release-
Paarabnahme. Die geschlossene Platte ist nach unabhängigem Hashvergleich auf HDD
archiviert; alle sieben Dienste waren am Ende dieses Fensters gesund und stabil.
Die separate Jenkins-Referenz verwendet dieselbe VM-/Swap-/Fixture-
Konfiguration. Beim Anlegen der Swapdatei wird nach jeweils 64 MiB
`fdatasync` und `POSIX_FADV_DONTNEED` angefordert, um vermeidbaren Dateicache
zu reduzieren. Diese Vorbereitung ist mit 64 MiB auf dem NAS-Linux bytegeprüft;
eine garantierte Cache-Freigabe wird nicht behauptet. Die fertige Swapdatei und
gemessene CI-Konfiguration ändern sich dadurch nicht.

Jenkins `graphato-postdeploy-quality #27` erreicht die ursprüngliche
Rust-Kompilierung, wird aber vom NAS-Swap-Schutz beendet. Um 09:49:04 Berliner
Zeit erfasst der Wächter 2.006.128 KiB freien Swap bei 2.359.296 KiB Untergrenze.
SIGTERM folgt um 09:49:05, der verifizierte Notstopp um 09:49:17. Die Test-VM
ist danach aus; alle sieben Dienste sind um 09:52:39 gesund und stabil.
NAS-OOM-Zähler 3, produktive CI unverändert. Jenkins #27 ist original als
`FAILURE` gesammelt; die Rust-Tests sind unvollständig. Die 126 Speicherproben
enthalten 67 streng zugeordnete Gast-/Hostwerte und verpassen den kritischen
Minimalwert. Das unabhängige Wächterjournal belegt die Reserveunterschreitung.

Der zusätzliche Jenkins-Controller lief nur in seiner Einzelprüfung. Diese
Diagnosen erlauben deshalb keinen fairen Laufzeitvergleich. Die nächste Serie
`day-b-*` begrenzt den Gast auf 7 GiB (`nas-7g-ssd-guest-swap-3840`) und hält
beide CI-Controller während beider Engines aktiv. Der ursprüngliche Builder
behält 6 GiB ohne Swap und zwei CPUs; äußeres Budget 9 GiB RAM plus 4 GiB Swap,
`memory.high=3840 MiB`, NAS-Untergrenzen und I/O-Limits bleiben gleich.
Das neue Profil muss erst zwei vollständige Original-Rust-Nachweise erbringen.

Die äußere Docker-API meldete zeitweise Abfrage-Timeouts, während die Leroy-API
weiterhin schnell antwortete. Zusätzliche lesende Beobachtungen verwenden die
bereits vom Wächter verifizierte Prozessidentität mit erneuter Prüfung von
PID-Startzeit, Cgroup und Kommando-Prüfsumme. Das ändert weder den laufenden
CI-Auftrag noch die Schutzgrenzen. Belege liegen im eigenen Tagesjournal;
die folgenden Abschnitte erhalten die abgeschlossenen Nachtversuche.

Zusätzlich wurde eine bisherige Konfigurationsabweichung erfasst: produktiver
Jenkins zwei Ausführungsplätze, privater Jenkins und Leroy jeweils einer.
Für einzelne Rust-Aufträge ändert das die mögliche Parallelität nicht.
Vor der vollständigen Paarabnahme sollen beide Testsysteme auf zwei Plätze
angeglichen werden; der laufende, gebundene Quellstand bleibt bis zum Ende
seines Fensters unverändert.

Die Angleichung ist nach Abschluss beider ersten Rust-Fenster durchgeführt:
beide APIs bestätigen zwei Plätze. Sicherung und Nachweise stehen unter
`test-results/nas-parity/followup/ci-concurrency-20261015/`. Die produktive
Jenkins-Konfiguration und alle Images bleiben unverändert. Die neue Serie
prüft außerdem dieselbe private Jenkins-Prozessidentität vor und nach jeder
Messung. Das ersetzt keinen Nachweis identischer sonstiger NAS-Hintergrundlast.

## Geschlossene 7-GiB-Prüfung und Dateispeicher für die Test-VM

Auch die neue Leroy-Prüfung mit beiden CI-Controllern (`day-b-rust-leroy-20261015`,
Originalrun #176) bleibt unvollständig. Der Wächter erfasst 2.291.452 KiB freien
Swap gegenüber 2.359.296 KiB Untergrenze, bei 810.244 KiB verfügbarem RAM.
SIGTERM folgt um 10:37:34, der verifizierte Notstopp um 10:37:47 Berliner Zeit.
Alle sieben Dienste sind seit 10:41:13 wieder gesund und stabil; NAS-OOM 3,
produktive CI unverändert. Von 132 Speicherproben sind 115 streng zugeordnet;
der kleinste erfasste Swapwert ist 2.290.992 KiB. QEMU erreicht etwa 3,5 GiB
NAS-Swap. Die Platte ist bytegeprüft mit SHA-256
`29e253714131e15d81e6c12c956b9ce7c4f77c3f9fe3d2e6a93934e8b6e53a09`
auf HDD archiviert; die SSD-Kopie ist entfernt. Kein Jenkins-Rust-Lauf dieser
Serie wurde gestartet.

Die folgende Serie C verwendete den QEMU-Dateispeicher für den Gast-RAM. Ein
128-MiB-Probelauf ohne Gast-OS bestätigt auf dem vorhandenen QEMU 8.2.2 die
gemeinsam beschreibbare Datei. Die vorgesehene 7-GiB-Datei liegt ausschließlich
im privaten SSD-Testbereich, getrennt von den archivierten Systemplatten.
Der ursprüngliche VM-Launcher und die unveränderliche Basisplatte bleiben auf
dem NAS erhalten. Der neue Launcher ist separat gehasht und abgelegt.
Die Bedeutung von `memory-backend-file` und `share=on` beschreibt die
[QEMU-Dokumentation](https://www.qemu.org/docs/master/system/invocation.html).
Aus der bloßen Unterstützung des Modus folgt keine Qualifikation.

Vor beiden Engines wird in derselben frischen VM ein separater Speicherprozess
im ursprünglichen 6-GiB-Limit ohne Swap und mit zwei CPUs gestartet. Er belegt
5.888 MiB, setzt je 4-KiB-Seite einen eindeutigen Marker, hält die Belegung
60 Sekunden und prüft sämtliche Marker vor der Freigabe. Erst nach Beendigung
dieses isolierten Prozesses darf der Originaljob starten. NAS-Untergrenzen,
Anwendungsquellen, Tests und ursprüngliche Fixture-Limits bleiben gleich.
Nach normalem VM-Stopp wird ausschließlich die eigene RAM-Datei anhand ihrer
gespeicherten Inode-, Pfad- und Besitzeridentität entfernt. Fehlversuche behalten
ihre Diagnosezustände. Keine NAS-Swapdatei wird hinzugefügt.

C erreichte 5.888 MiB Belegung. Die erste zusätzliche Stichprobenlesung
benötigte etwa 183 Sekunden und überschritt den eigenen SSH-Diagnose-Timeout.
Die nach Abschluss ausschließlich lesend aus der archivierten Platte
extrahierte Agentenaufzeichnung bestätigt intakte Stichproben, danach einen
`BrokenPipeError`. Die vollständige Prüfung aller Seitenmarker fehlt; C ist
deshalb nicht qualifiziert. Es wurde kein Graphato-Auftrag gestartet.
Alle sieben Dienste waren am 15. Oktober um 11:30:13 Berliner Zeit wieder
gesund und stabil. Die Platte ist mit SHA-256
`a4f884708a33d7e440a26ab9aeb8211e5ffcf8ce37562980f3065b735c852c9c`
bytegeprüft archiviert; die SSD-Kopie ist entfernt. QEMU beendete sich ohne
erzwungenen Stopp. Die danach vollständig freigegebene RAM-Datei enthielt nur
noch Löcher und ist kein RAM-Abbild vor dem Stopp.

Die 70 Speicherproben enthalten nur drei streng zugeordnete Gast-/Hostwerte;
43 Gastabfragen scheiterten. Die beobachteten NAS-Minima liegen bei
3.443.372 KiB verfügbarem RAM und 6.163.144 KiB freiem Swap. Der NAS-OOM-Zähler
blieb bei 3. Trotz ausreichender NAS-Reserve deutet der starke Anstieg von
`workingset_refault_file` und Seitenrückgewinnung auf häufiges erneutes Lesen
der RAM-Dateiseiten hin. Eine Speicherbeschädigung ist damit nicht belegt.

## Prüfung mit geschütztem VM-Arbeitssatz

Das separate Profil `nas-7g-ssd-file-memory-protected` behält QEMU, 7 GiB
Gast-RAM, 4 GiB Gast-Swap, sechs Gast-CPUs und alle ursprünglichen
6-GiB-/Ohne-Swap-/Zwei-CPU-Builder-Limits. Auch die äußeren harten Budgets,
SSD-I/O-Limits und NAS-Schutzreserven ändern sich nicht. Die eigene VM läuft
in einer eigenen Cgroup unmittelbar unter der Wurzel, mit `memory.low=4 GiB`
und `memory.high=5 GiB`. Das ist ein bestmöglicher Verdrängungsschutz, keine
harte Reservierung. Vorher werden vorhandene NAS-Elternquoten geprüft; keine
Wurzel- oder `system.slice`-Attribute werden verändert. Platzierung und die
konkrete Richtlinie sind mit kleinen eigenen Linux-Containern geprüft.
Die Bedeutung von `memory.low` beschreibt die
[Linux-Cgroup-Dokumentation](https://docs.kernel.org/admin-guide/cgroup-v2.html).

Die eigene VM-Systemplatte verwendet `cache=none`, um zusätzlichen Hostcache
für QCOW-Daten zu vermeiden. Der separate Diagnoseprozess meldet während der
Haltezeit nur den Belegungsstand; die vollständige Kontrolle sämtlicher
4-KiB-Seitenmarker am Ende bleibt erhalten. Ausschließlich sein eigener
Kontroll- und SSH-Timeout wurde erhöht. Quellen, Tests, Zeitlimits und
Ratenbegrenzungen von Graphato bleiben unverändert. Beide CI-Controller sind
mit zwei Ausführungsplätzen vor dem frischen VM-Start aktiv.

D erreichte 3.072 MiB, scheiterte aber bei einer lesenden Abfrage des produktiven
Jenkins an `docker inspect jenkins` nach 20 Sekunden. Auch der Bereinigungsversuch
über die bisherige Gast-Zugriffsfunktion scheiterte. Der unabhängige Wächter
stellte die Dienste wieder her; alle sieben waren um 12:19:20 Berliner Zeit
gesund und stabil. Es wurde kein ursprünglicher Graphato-Auftrag gestartet.
Die Testplatte ist bytegeprüft archiviert, SHA-256
`ac9959094749336c88db3c6aaa4d809bd387eb61de575e2821977fa45e225225`.
QEMU beendete sich ohne erzwungenen Stopp, die anschließend leere RAM-Datei
ist entfernt. 31 Speicherproben enthalten sieben streng zugeordnete Werte;
14 Gastabfragen scheiterten. Beobachtete NAS-Minima: 3.432.416 KiB verfügbarer
RAM, 5.633.000 KiB freier Swap. NAS-OOM blieb bei 3; daraus folgt keine
vollständige Speicherqualifikation.

Die neue Serie E behält dieses Ressourcenprofil. Nur der Zugriff des eigenen
Abnahmewerkzeugs ist korrigiert: einmalige Docker-Ermittlung vor der VM-Last,
danach Prüfung derselben PID mit Boot-ID, Startzeit, Kommando, Cgroup und
Namensräumen vor und nach jedem Zugriff. Für die produktiven Jenkins-Daten
werden zusätzlich Gerät und Inode des Quellverzeichnisses und des tatsächlichen
Prozess-Mounts verglichen. Identitätswechsel werden zurückgewiesen, ohne
automatisch ein neues Ziel zu wählen. Wiederholte Produktionsbeobachtung und
alle sechs Ablehnungsfälle sind lesend auf dem NAS-Linux geprüft. Jenkins-Daten,
Quellen und ursprüngliche Graphato-Prüfungen wurden dabei nicht verändert.

Das erste E-Fenster endet am 15. Oktober spätestens um 16:23:34 Berliner Zeit;
der unabhängige Wächter beginnt spätestens um 16:08:34 die Wiederherstellung.
Ein erfolgreicher Speicherprobelauf allein ersetzt auch hier keinen
ursprünglichen Rust- oder vollständigen Release-Nachweis.

E ist inzwischen geschlossen. Die Zusatzprobe hat die vollständigen 5.888 MiB
gehalten und sämtliche Seitenmarker erfolgreich geprüft. Der Originalauftrag
wurde dennoch nicht gestartet: Die Prüfung danach traf auf eine unterbrochene
Graphato-Laufzeitsperre. Aus der gestoppten Platte wurden ohne Boot, Mount oder
Journal-Replay die vier Containerzustände und ausgewählte Protokolle gelesen.
Sie enthalten Datenbank-Pool-Timeouts ab 12:36:21 Berliner Zeit, den Verlust der
PostgreSQL-Laufzeitsperre um 12:37:07, anschließend die verwaiste Sperre und
35 Server-Neustarts. Die Anwendung blieb dadurch beschädigt; ein vorübergehend
fehlgeschlagener Healthcheck allein erklärt den Zustand nicht. Ein ursächlicher
Kernel-OOM ist nicht belegt. Die ursprünglichen CI-Tests liefen noch nicht.

Alle sieben Dienste waren um 12:53:44 Berliner Zeit wieder gesund und stabil,
NAS-OOM weiterhin 3, produktive CI und Infrastruktur unverändert. Die Platte
ist bytegeprüft mit SHA-256
`30f722a14597eada94fb7c62cfdecdb88ef3ac9b2c167ee2919f385e61c4a8bc`
archiviert. QEMU beendete sich geordnet; die anschließend vollständig leere
RAM-Datei ist anhand ihrer Inode-Identität entfernt. 58 Speicherproben enthalten
17 streng zugeordnete Werte und 26 Gastabfragefehler; NAS-Minima 3.199.416 KiB
verfügbarer RAM und 5.567.096 KiB freier Swap.

## Getrennte Kapazitätsprüfung und frischer Originalauftrag

Die eigene Zusatzlast darf die Anwendungsinstanz des eigentlichen Vergleichs
nicht vorher in einen Fehlerzustand versetzen. F verwendet deshalb denselben
bestandenen Kapazitätsbeleg und eine frische Kopie der unveränderlichen
Ausgangsplatte für jeden Originalauftrag. Acht Dateien der physischen
VM-Konfiguration müssen gegenüber E bytegleich bleiben. Die Bindung prüft
5.888 MiB, tatsächliche Haltezeit, alle Seitenmarker, ursprüngliche Builder-
Limits und Runtime sowie E-Abschluss, gesunde NAS-Dienste, Archivierung,
unveränderte produktive CI und eingehaltene NAS-Reserven.

Die Referenz nennt ausdrücklich die fehlgeschlagene Anwendungsgesundheit von E
und dass ihre Zusatzprobe in einer anderen VM lief. Es werden weder die
beschädigte Anwendungsinstanz noch Graphato-Ergebnisse wiederverwendet.
Alle Originaltests müssen in F neu laufen. Vor deren Start wird der gesunde
Anwendungsausgangszustand erfasst; auch ein fehlgeschlagener Ausgangszustand
wird jetzt vor dem Abbruch gespeichert. Das neue F-Fenster endet spätestens
um 17:00:19 Berliner Zeit, Wiederherstellung spätestens ab 16:45:19.

Auch F scheiterte vor dem ursprünglichen Auftrag. Die frische Instanz verlor
am 15. Oktober um 13:14:06 Berliner Zeit ihre PostgreSQL-Laufzeitsperre, während
die eigene Datenträgerprüfung 1 GiB mit 128 fsync-Aufrufen schrieb. Diese Probe
dauerte 167,652 Sekunden. Die gespeicherte Gesundheitsbeobachtung enthält fünf
Server-Neustarts; bis zum VM-Stopp wurden zwölf erfasst. Damit erklärt die
große Speicher-Zusatzprobe aus E den Fehler nicht allein. Die sieben Dienste
waren um 13:19:42 gesund und stabil, produktive CI und Infrastruktur unverändert.
Die Testplatte ist mit SHA-256
`d0497726d5c10ae584a5ccaf86f236bb7e3e2f10f9dec157a80203515540b653`
bytegeprüft archiviert. Die nach geordnetem Stopp leere RAM-Datei ist entfernt.

## Getrennte I/O-Begrenzung für RAM-Datei und Gastlaufwerk

Die bisherige äußere I/O-Grenze erfasst beim Dateispeicher auch RAM-Writeback
und konkurriert dadurch mit Datenbank-I/O. Ob dies die Laufzeitsperrenverluste
verursacht, wird mit einem eigenen Profil geprüft. QEMU 8.2.2 bestätigt die
Begrenzung ausschließlich des virtuellen Laufwerks in einer angehaltenen
128-MiB-KVM-Instanz mit 4-MiB-Testplatte, ohne Gast-OS oder CI-Auftrag. QMP meldet
128 MiB/s Lesen und 32 MiB/s Schreiben. Die Optionen beschreibt das
[QEMU-QMP-Handbuch](https://www.qemu.org/docs/master/interop/qemu-qmp-ref.html).

`nas-7g-ssd-file-memory-disk-qos` behält RAM, Swap, CPU, ursprüngliche
Builder-Limits und sämtliche NAS-Schutzreserven. Nur die eigene VM besitzt
keine zusätzliche äußere Datenträgerdrossel; die bisherigen 128/32 MiB/s liegen
direkt auf ihrem virtuellen Systemlaufwerk. Globale NAS-I/O-Einstellungen und
andere Cgroups werden nicht verändert. Der neue Launcher liegt separat unter
`file-memory-v2`; der alte Launcher und die unveränderliche Basisplatte bleiben
erhalten. Linux-Prüfungen bestätigen Rechte, Dateidentität und zulässige
Optionen. QMP und tatsächliche Docker-Konfiguration müssen die Trennung vor
und nach dem Lauf unter beiden Engines bestätigen.

Der frühere E-Kapazitätsbeleg wird bei geänderter physischer Konfiguration
zurückgewiesen. G führt deshalb die vollständige neue Speicherprobe aus und
erfasst den gesunden Anwendungszustand vor und nach den Zusatzprüfungen.
Zusätzliche Neustarts verhindern den Start des Originalauftrags. Das neue
G-Fenster endet spätestens um 17:25:56 Berliner Zeit, Wiederherstellung
spätestens ab 17:10:56. Ein kausaler Erfolg des neuen Profils ist noch offen.

Die G-Vorbereitung ist inzwischen bestanden. Der Ausgangszustand um 13:35:26
und der Zustand nach den Zusatzprüfungen um 13:44:54 Berliner Zeit enthalten
dieselben vier gesunden Container und jeweils null Neustarts. Die vollständige
Speicherprobe prüfte alle Seitenmarker erfolgreich; die Datenträgerprobe
bestand. Direkte HTTP- und HTTPS-Gesundheitsabfragen antworteten mit 200.
QMP und Docker bestätigen 128/32 MiB/s nur am Gastlaufwerk und leere äußere
I/O-Quoten. Damit ist der frühere Vorbereitungsfehler unter dem neuen Profil
ohne Graphato-Änderungen überwunden. Der ursprüngliche Rust-Auftrag läuft seit
13:45:17 unter Leroy (`e9b8e76def8446e3baf767d72bfeabbd`); sein Ergebnis und
das Jenkins-Gegenstück bleiben offen.

Der G-Originalauftrag (#177) ist inzwischen mit `interrupted` beendet.
Das Prüfimage wurde vollständig erzeugt; der ursprüngliche Rust-Build-Container
hatte nachweislich 6 GiB RAM, null Swap und zwei CPUs. Während der Kompilierung
von `graphato_desktop_lib` blieb die Bestätigung der Leroy-Runner-Lease aus.
Die Worker-Diagnose enthält 45,733 Sekunden ohne Bestätigung und wiederholte
HTTP-Lese-Timeouts; der Großteil der Request-Zeit lag beim Warten auf
Antwortheader. Der Worker brach den Auftrag ab, später markierte der Controller
die abgelaufene Lease als `interrupted`. `cancel_requested` war falsch.

Die originale Graphato-Quittung enthält `Cancelled` nach 1.510,430 Sekunden,
vollständige Bereinigung und kein vollständiges Rust-Inventar. Kein CI-Artefakt
wurde veröffentlicht. Ohne Boot, Mount oder Journal-Replay gelesene Original-
Quittung und -Protokolle sind zusätzliche Diagnosebelege, keine nachträglich
veröffentlichten CI-Artefakte. Die erste gescheiterte Live-Sicherung und
Speichersammlung bleiben ebenfalls erhalten.

Nach dem VM-Stopp konnte dieselbe ursprüngliche Speicheraufzeichnung gesichert
werden: 177 Proben, davon 155 streng zeitlich zugeordnet, fünf Gastabfragefehler.
NAS-RAM mindestens 3.348.748 KiB und freier Swap mindestens 5.605.664 KiB;
NAS-OOM blieb bei 3. Die Schutzreserve wurde nicht unterschritten. Hohe
Speicher- und I/O-Wartezeiten sowie Aussetzer der Gesundheits-API sind erfasst.
Sie belegen nicht, dass jede Verzögerung dieselbe Ursache hatte.

Alle sieben Dienste waren um 14:24:48 Berliner Zeit wieder gesund und stabil,
produktive CI und Infrastruktur unverändert. Zunächst folgt ein frischer
Jenkins-Referenzlauf mit demselben eingefrorenen Stand, Ressourcenprofil,
Originaltest und unveränderten Leroy-Lease-Fristen. Diese Diagnose darf nach
dem belegten Leroy-Abbruch stattfinden, ist aber keine Ausnahme von der
erforderlichen vollständigen Rust- und Release-Abnahme beider Engines.

Der G-Jenkins-Job #28 erreichte ebenfalls die ursprüngliche Rust-Kompilierung
mit 6 GiB, null Swap und zwei CPUs. Während seiner Ausführung überschritten
Leroys Gesundheitsproben wiederholt fünf Sekunden; Jenkins blieb zunächst
aktiv. Ein 60-Sekunden-SSH-Timeout beim Statuslesen brach jedoch die eigene
Abnahmesteuerung ab. Die anschließende Wiederherstellungsabfrage überschritt
ebenfalls ihre SSH-Frist. Die verifizierte VM wurde geordnet beendet und alle
sieben Dienste waren um **15:50:30 Berliner Zeit** gesund und stabil. Der
Originaljob ist als `ABORTED` gesammelt, kein vollständiges Rust-Ergebnis.
Die geborgenen 182 Speicherproben enthalten 99 streng zugeordnete Werte;
NAS-Minima 3.500.092 KiB RAM und 5.478.424 KiB Swap, OOM-Zähler unverändert 3.

Die Korrektur betrifft ausschließlich das Abnahmewerkzeug: Ein nicht lesbarer
Jenkins-Status bleibt unbekannt und wird für dieselbe Nummer erneut gelesen;
unbekannte Kinder zählen nicht als fehlende Jobs. Auch Artefakt-Lesezugriffe
bleiben an die ursprüngliche Nummer und die bestehende Frist gebunden.
Wiederherstellungsabfragen wiederholen nur dieselbe idempotente Aktion innerhalb
des festen Budgets. 479 lokale Tests bestehen, 43 sind umgebungsabhängig
übersprungen. Das neue H-Jenkins-Fenster verwendet unveränderte physische
VM-Einstellungen, Quellen, Tests und Leroy-Lease-Fristen; es endet spätestens
um **20:04:14 Berliner Zeit**, Wiederherstellung ab 19:49:14. Die ursprüngliche
Jenkins-Rust-Abnahme muss dort vollständig neu laufen.

Stand: 15. Oktober 2026. Diese Untersuchung ergänzt die fehlgeschlagenen
Vollabnahmen und ersetzt deren Ergebnisse nicht. Leroy ist dadurch noch nicht
für den produktiven Jenkins-Ersatz freigegeben.

Die vollständigen Original-Läufe E/F auf SSD mit 8-GiB-Gast und
`memory.high=3840 MiB` bestanden Formatprüfung und Clippy unter beiden Engines.
Das ursprüngliche Rust-Inventar mit 1.657 Tests ist unter keiner vollständig
belegt. E überlappte mit dem produktiven Musik-Timer #244 und erlaubt deshalb
keine reine Kapazitätsaussage. F blieb ohne produktive Builds und erreichte
dennoch die unveränderte NAS-Swap-Untergrenze: 2.357.208 KiB gegenüber
2.359.296 KiB. Während des etwa dreiminütigen erzwungenen VM-Stopps sank der
beobachtete freie Swap bis auf 1.532.392 KiB. Der NAS-OOM-Zähler blieb bei 3;
lückenhafte Gastmessungen belegen keine vollständige OOM-Abwesenheit.

Alle sieben Anwendungen sind nach F seit 05:28:30 Berliner Zeit gesund und
stabil wiederhergestellt, vor dem unveränderten Ende um 06:00. Die unabhängige
NAS-Reserveprüfung und der kürzere Notstopp für den verifizierten VM-Prozess
sind im Abnahmewerkzeug ergänzt und lokal sowie mit dem Linux-Prozessparser
geprüft. Ein erneuter realer Volllauf mit dieser Nachkorrektur steht aus.
Die Grenzwerte und ursprünglichen Fixture-Limits bleiben unverändert.
Ein vollständiger Rust-Ressourcennachweis muss einer weiteren Paarabnahme
vorausgehen; diese Nacht startet keine weitere schwere Testlast. Die folgenden
Abschnitte bewahren die früheren Einzelversuche.

## Auftrag und Grenzen

Die ursprüngliche Gruppe `server-test` wird auf dem eingefrorenen Graphato-Commit
`0ad540dd578033d45e4d0c25d89fbe57b32102a4` ausgeführt. Quellen, Tests, Cargo-Profile,
Testparallelität und ursprüngliche Fixture-Limits bleiben unverändert. Die
zusätzliche Ziel-VM sowie beide CI-Steuerungen laufen auf dem NAS. Die sieben
NAS-Anwendungen bleiben während der ersten Diagnosephase aktiv. Später folgen
zwei gesondert genehmigte, unten dokumentierte Fenster; keines der früheren
Fenster wird erneut verwendet. Die
abschließend beobachteten zwei Dienstneustarts sind unten getrennt ausgewiesen.
Produktive Jenkins-Jobs werden ausschließlich lesend beobachtet.

Ein neuer einzelner Gruppenlauf ist eine Diagnose und keine Wiederholung oder
Ersetzung eines früheren Originaljobs. Ein gemeinsamer Anwendungsfehler ist
kein Beweis für einen Leroy-Fehler und auch keine eigenständige Produktionsfreigabe.

## Getrenntes Infrastrukturprofil

`nas-8g-ssd-soft-ram-3584` stellt dem Linux-Gast 8 GiB statt 10 GiB bereit.
Der äußere Container erhält 9 GiB hartes RAM-Limit und zusätzlich 4 GiB möglichen
Swap; `memory.high` bleibt bei 3584 MiB. Das ursprüngliche Builder-Limit von
6 GiB ohne Swap und zwei CPUs bleibt bestehen. Der Gast erhält sechs CPUs und
keinen Swap. Ein erfolgreicher Vergleich muss auch die tatsächlich ausgeführten
Compile- und Testcontainer nachweisen.

Unverändert bleiben 128 MiB minimale verfügbare NAS-RAM-Reserve, 2304 MiB freie
NAS-Swap-Reserve, 40 GiB freie SSD-Reserve und die SSD-Limits von 128 MiB/s Lesen
und 32 MiB/s Schreiben. Auch die vorhandene Gast-Cachepolitik und die
Free-Page-Reporting-Granularität bleiben gleich. Der gesondert qualifizierte
PostgreSQL-Override `init: true` wird verwendet. Das neue Profil ist zunächst
ein zu prüfender Kandidat, keine belegte Behebung des früheren Reserveabbruchs.

## Beobachtung und Abschlusskriterien

Ein begrenzter NAS-lokaler Prozess erfasst ungefähr alle zehn Sekunden:

- NAS-RAM, Swap, Paging und Druckindikatoren vor und nach der Gast-Abfrage;
- die tatsächliche VM-Cgroup einschließlich RAM, Swap und OOM-Zählern;
- QEMU-RSS und Swap; die erste Diagnose liest `smaps_rollup`, spätere Beobachter
  verwenden die leichteren `/proc/PID/status`-Zähler;
- Gast-RAM, freien Speicher, Cache, Paging und OOM-Zähler;
- alle 30 Sekunden die Speicherbelegung der vorhandenen NAS-Container.

Gast-Abfragelücken, Uhrzeitabweichungen und langsame Proben bleiben ausgewiesen.
Nur Proben mit Gastzeit innerhalb der höchstens zehn Sekunden breiten
NAS-Beobachtungsspanne werden als zeitlich zugeordnet gezählt. Der Beobachter
verändert keine RAM-Einstellung und beendet spätestens nach vier Stunden oder
24 MiB Protokollgröße seine Arbeit. Seine Identität und sein Quellhash werden
gebunden; die Ergebnisse werden vor der Bereinigung gesichert.

Ein bestandener Schritt verlangt die ursprüngliche Ergebnisquittung, ein
vollständiges unverändertes Rust-Testinventar, abgeschlossene Fixture-Bereinigung,
keinen Ressourcenabbruch und gesunde Basisdienste. Der Jenkins-Gegenlauf erhält
eine frische Basis mit demselben Profil. Gleiche Hintergrundlast wird auch bei
ruhigem produktivem Jenkins nicht behauptet.

Für die anschließend noch offene Image-Qualifikation wird ein vollständiges
Dateiinventar vorbereitet. Inhalte, Eigentümer, Rechte, Links und Attribute
zählen; reine Archivzeitstempel werden getrennt behandelt. Ein solches Inventar
führt keine Programme aus dem Image aus und ersetzt keine Originaltests.

## Erster einzelner Leroy-Versuch

`quality-rust-memory8g-leroy-20261014`, Run
`b1971839654b40c38b4326094a4700d5`, endet am 14. Oktober um 14:19:24 UTC
als `interrupted` mit abgelaufener Runner-Lease. Der ursprüngliche vollständige
Rust-Nachweis fehlt. Die gesunde Basisanwendung und die erfolgreich gebaute
Prüfimage-Datei sind kein bestandener Gruppenlauf.

97 NAS-lokale Speicherproben enthalten 88 zeitlich zugeordnete Gastproben und
fünf Gast-Abfragefehler. Das Minimum des verfügbaren NAS-RAMs beträgt
268904 KiB, das Minimum des freien NAS-Swap 4144828 KiB. Der Gast zählt
weiterhin null OOM-Kills; der physische NAS-Zähler bleibt bei seinen drei
historischen Ereignissen. Die VM-Cgroup erreicht etwa 3,34 GiB RAM und
1,31 GiB Swap. Die ursprünglichen Builder- und Compile-Containergrenzen sind
direkt belegt. Der Compiler erreicht bis zur beobachteten Unterbrechung noch
nicht seine bekannte schwerste Phase; daraus folgt keine RAM-Freigabe.

Der Controller protokolliert für diesen Worker HTTP 200 um 14:17:02.716 UTC
und erneut um 14:17:54.104 UTC. Der Worker meldet um 14:17:56.729 UTC seinen
lokalen Lease-Abbruch. Die konservative Schutzlogik zählt ab dem Beginn eines
Bestätigungsversuchs. Eine stark verspätete erfolgreiche Antwort oder eine
Scheduling-Pause kann deshalb zum Abbruch führen. Der konkrete Ablauf ist noch
nicht vollständig belegt. Externe API-Proben enthalten keinen Timeout; drei
SQL-Zusatzabfragen besitzen Beobachtungslücken. Diese erfolgreichen äußeren
Proben beweisen keine zeitgerechte Worker-Ausführung.

Während des Versuchs wird der ausgeschaltete ältere Frontend-Datenträger von
der SSD bytegeprüft auf HDD gesichert, um die SSD-Reserve zu erhalten. Seine
10011017216 Bytes besitzen vor und nach der Übertragung SHA-256
`b0fb5c8cd13a0643e5761e3a3948ad58899c01d9893dcddbc83a732c5d219d2d`.
Er liegt nun unter
`/volume1/docker/leroy-nas-parity/release-vm/0ad540dd5780/archived-frontend-20261014/system.qcow2`.
Nur die verifizierte SSD-Kopie wurde entfernt; ursprüngliche CI-Ergebnisse
bleiben erhalten. Diese zusätzliche Last überlappt die Lease-Lücke. Die
Diagnose belegt deshalb keine isolierte Ursache und keine Geschwindigkeitsparität.

Vor einem frischen, getrennten Folgeversuch ist passive Worker-Zeitdiagnostik
im eigenen Testprofil installiert. Sie erfasst langsame erfolgreiche Bestätigungen, die Zeit seit der
letzten Bestätigung und den Abstand zwischen Monitor-Schleifen. Der Vergleich
der ASTs nach Entfernen genau dieser Diagnoseanweisungen bestätigt unveränderte
Lease-Entscheidungen und unveränderten übrigen Worker-Code. Die Schutzfrist,
Controller-Lease, Graphato-Quellen und Tests werden nicht verlängert oder verändert.

Das neue eigene Jobimage ist
`sha256:e20b2a7fb36ab09f72c2b6038e33a971be8409a18bb76fb0f2ee4ce9185bcc79`,
Worker-Quelldatei SHA-256
`bd4672235dd2cc2cd9e3d30c3d1b690089bed900abee0bb449487b859c90abac`.
Image-Konfiguration und alle vorherigen Dateisystemschichten bleiben erhalten;
die einzige neue Schicht kopiert die geprüfte Worker-Datei. Das vorherige Image
und die geschützte Runner-Konfiguration bleiben rückholbar. Nur `graphato.image`
im eigenen Runner-Profil wird geändert und der eigene Runner neu gestartet.
Controller, PostgreSQL und Docker-Daemon bleiben mit denselben Prozessen aktiv.
Produktive Jenkins-Historien bleiben an den Grenzen unverändert und inaktiv.

Die vollständige lokale Prüfung besteht mit 228 Tests; 41 Tests werden
übersprungen. Neue Laufzeitabhängigkeiten wurden nicht eingeführt. Die Leroy-UI
wurde nicht verändert. Private Nachweise liegen unter
`test-results/nas-parity/followup/worker-lease-timing-20261014/` und
`test-results/nas-parity/followup/rust-resource-qualification-20261014/`.

Vor dem Folgeversuch ist auch der alte ausgeschaltete Jenkins-Datenträger
bytegeprüft archiviert: 21025521664 Bytes, SHA-256
`123fb226aeea27b37f9a1581c434fd33e29661d24df158142646fcf48e035baa`. Neuer Pfad:
`/volume1/docker/leroy-nas-parity/release-vm/0ad540dd5780/archived-full-release512-jenkins-20261014/system.qcow2`. Seine SSD-Kopie wurde erst nach
der vollständigen Gegenprüfung entfernt. Der archivierte ursprüngliche
Schutzabbruch bleibt erhalten; der Datenträger wurde nicht gebootet.
Die nächste Diagnose startet erst nach abgeschlossener Archivierung.

## Frischer Folgeversuch und getrennte Schreibpfad-Beobachtung

`quality-rust-memory8g-leroy-timing-20261014`, Run
`37458c3644584265b9c28e64cba92478`, startet um 14:45:23 UTC von einer neuen Basis.
Die Archivierungen sind vor seiner Vorbereitung beendet. Alle ursprünglichen
Quellen, Tests, Fixture-Grenzen und das Ressourcenprofil bleiben gleich; die
passive Worker-Zeitdiagnostik ist der ausgewiesene Unterschied.

Ein einzelner Worker-ReadTimeout ist um 14:48:22 UTC erfasst; der Lauf erholt
sich. Eine spätere erfolgreiche Bestätigung benötigt 4,466 Sekunden. Der
laufende Worker besitzt tatsächlich 2 GiB ohne Swap, zwei CPUs und eine
128-MiB-Reservierung. Eine direkte Cgroup-Probe zeigt etwa 53 MiB RAM, keinen
Swap, keinen OOM und nur geringe CPU-Drosselung. Die laufende Controller-Datei
`api.py` entspricht exakt dem lokal geprüften Stand; eine veraltete Kopie ist
damit als Erklärung ausgeschlossen.

Ein zusätzlicher begrenzter NAS-lokaler Beobachter liest ausschließlich
`pg_stat_activity`, Sperrbeziehungen und WAL-Statistik der eigenen Leroy-DB.
Er verwendet eine eigene schreibgeschützte Verbindung und speichert keine
SQL-Texte, Token oder beliebigen Jobausgaben. Bereits die ersten Proben zeigen
Commits in `WalSync` bis zu einem beobachteten Abfragealter von 4,22 Sekunden;
andere Transaktionen warten dahinter auf Advisory- oder Transaktionssperren.
Die schnellen SELECT-/Bereitschaftsproben beweisen deshalb keine zeitgerechte
Schreibbestätigung für Leases. Die Ursache der längeren historischen Lücke
ist dadurch noch nicht vollständig bewiesen.

Eine ergänzende kleine Dateiprobe schreibt abwechselnd auf denselben
SSD-Dateisystemtyp wie die eigene Datenbank und auf den vorhandenen HDD-Speicher.
Zwölf Proben mit jeweils 4096 Bytes und `fsync` ergeben im Mittel 58 ms auf SSD
und 267 ms auf HDD, maximal 602 bzw. 698 ms. Die Messung überschneidet eine
andere Lastphase als einige der WAL-Warteproben und beweist keine allgemeine
Latenzgrenze. Sie begründet keinen Wechsel auf HDD. Datenbankeinstellungen,
Lease-Fristen und produktive Dienste bleiben unverändert. Die zusätzliche
Beobachtungs- und Probelast wird ausgewiesen; gleiche Hintergrundlast oder
Produktionsgeschwindigkeit werden weiterhin nicht behauptet.

Der Folgeversuch endet ebenfalls mit abgelaufener Runner-Lease. Die endgültige
Speicherauswertung enthält 121 Proben, davon 59 zeitlich zugeordnete Gastproben
und sechs Gast-Abfragefehler. Einige Proben dauern erheblich länger als geplant.
Das gemessene NAS-RAM-Minimum beträgt 90392 KiB, freier Swap mindestens
2818524 KiB. Der RAM-Messwert unterschreitet also zeitweise die konfigurierte
Reserve; eine lückenlose Einhaltung wird nicht behauptet. Der VM-Launcher
protokolliert allerdings keinen eigenen Ressourcenabbruch: Der spätere
geordnete Diagnose-Abschluss besitzt `forced: false` und
`resource_guard_triggered: false`. Es gab keinen neuen physischen OOM-Zähler.
Die Rust-Gruppe ist nicht vollständig bestanden und das Profil bleibt
unqualifiziert.

Die erste Sammlung wartete nur zehn Sekunden auf einen verzögerten Beobachter
und unterbrach dadurch dessen optionale Nachweissicherung. Die Fortsetzung
sammelte ausschließlich denselben bereits terminalen Originaljob und schaltete
die VM aus; es gab keinen erneuten Teststart. Der Helfer gibt verzögerten
Beobachtern künftig begrenzt mehr Zeit und dokumentiert fehlende Zusatzdaten,
statt die Bereinigung eines terminalen Jobs daran scheitern zu lassen. Die
regelmäßige QEMU-Probe benötigt keinen vollständigen Seitentabellen-Durchlauf
mehr. Zwei gezielte Fehlerfälle prüfen, dass Sammelfehler weder sensible
Ausnahmetexte veröffentlichen noch eine vollständige Speicherabnahme vortäuschen.

## Geprüfte und installierte Controller-Korrektur

Die bisherige `reconcile`-Abfrage sperrt alle aktiven Runs mit `FOR UPDATE`,
auch wenn weder Lease noch Pipeline-Zeitlimit fällig sind. Eine solche Sperre
kann Heartbeats derselben Zeile bis zum Transaktionsende blockieren und selbst
Schreibarbeit verursachen; siehe die
[PostgreSQL-Dokumentation zu Zeilensperren](https://www.postgresql.org/docs/18/explicit-locking.html#LOCKING-ROWS).
Das ist ein konkreter vermeidbarer Engpass, aber noch kein vollständiger Beweis
für die Ursache jeder historischen Verzögerung.

Die Korrektur liest gesunde Runs ohne Zeilensperre. Erst bei einem
fälligen Eingriff sperrt er die betreffende Zeile mit `SKIP LOCKED`, lädt ihren
aktuellen Zustand neu und prüft die Entscheidung erneut. Dadurch darf eine
zwischenzeitlich erneuerte Lease nicht anhand eines alten ORM-Objekts beendet
werden. Lease-Zeiten, Fencing, Haltbarkeitsgarantien und Graphato-Tests bleiben
gleich.

Zwei echte PostgreSQL-Regressionen prüfen einen parallelen Heartbeat bei offen
gehaltener Zustandsprüfung und eine zwischenzeitlich erneuerte Lease. Die
Qualifikation ist nach dem unveränderten Jenkins-Gegenlauf in einer separaten,
flüchtigen NAS-Testdatenbank ausgeführt. Beide Gegenbeispiele scheitern auf dem
ursprünglichen Controller-Code und bestehen mit der Korrektur. Alle **34 echten
PostgreSQL-Tests bestehen ohne übersprungene Fälle**. Die Datenbank, das interne
Testnetz und der Testcontainer sind anschließend entfernt. Der Test verwendet
weder produktive noch bestehende Leroy-Daten und startet kein lokales Docker.
Pytest und seine Hilfsdateien sind ausschließlich als separates Operator-Archiv
eingehängt; das geprüfte Laufzeitimage erhält keine neuen Abhängigkeiten.

Genau dieses geprüfte Image ist im eigenen NAS-Testcontroller installiert:
`sha256:ffaa70367cd503b316c714859df6fefa1275344fee1fcfe5cc183b8878c477aa`.
Die einzige neue Imageschicht enthält `engine.py`, SHA-256
`db7fa487b3fd6b7a59ab5280e996846e434a22afc80d05420a2d40af6021643e`.
Vorher wurden Datenbankdump, ursprünglicher Container und Konfigurationen
geschützt gesichert. Nach dem Wechsel sind 155 Runs, 439 Schritte und
595 Artefakte gegen den gesicherten Dump abgeglichen; die API ist bereit.
Ressourcen, Umgebungsvariablen, Mounts und Konfigurationsdateien bleiben gleich.
PostgreSQL, Runner und Testdaemon behalten bei diesem Wechsel ihre Prozesse.
Produktiver Jenkins und die sieben NAS-Anwendungen werden nicht verändert.

Der NAS-SSH-Dienst erlaubt kein TCP-Forwarding. Der erste externe
Testverbindungsversuch ist deshalb ausdrücklich verworfen und bereinigt;
die bestandene Prüfung läuft vollständig in begrenzten Linux-Testcontainern
auf dem NAS. Die SSH-Einstellungen werden nicht geändert. Die ursprüngliche
fehlende Pytest-Hilfsdatei im Operator-ZIP und die fehlerhafte erste
Bereitschaftsadresse bleiben als reparierte Operatorfehler dokumentiert.
Die API ist an die NAS-Adresse gebunden; die abschließende Prüfung verwendet
`192.168.178.97:8088`. Die Wiederaufnahme prüft den bereits installierten
Controller und erzeugt keinen weiteren Containerwechsel.

Private Nachweise: `controller-reconcile-locks-20261014/` unter dem gemeinsamen
Follow-up-Ordner, insbesondere `counterexamples.json`, `postgres-validation.json`,
`postgres-cleanup.json` und `deployment-proof.json`. Die lokale vollständige
Prüfung ohne PostgreSQL besteht abschließend mit 240 Tests und neun übersprungenen Fällen;
die 34 PostgreSQL-Fälle sind zusätzlich tatsächlich auf Linux ausgeführt.
Die zusätzliche Eingangsprüfung ist darin enthalten; 23 gezielte Operator-
und Rust-Protokollprüfungen bestehen ebenfalls. Ruff und `git diff --check`
melden keine Fehler. Der eingefrorene Graphato-Checkout ist weiterhin sauber.

## Unveränderter Jenkins-Gegenlauf

Der private Jenkins führt `graphato-postdeploy-quality #23` in
`quality-rust-memory8g-jenkins-20261014` mit derselben frischen Basis und dem
8-GiB-Profil aus. Checkout, ursprüngliche Gruppe und Fixture-Limits sind
gebunden. Der Compiler erreicht mindestens 4195057664 Bytes; tatsächlich
gelten weiterhin 6 GiB ohne Swap und zwei CPUs. Es gibt keine Quell- oder
Teständerung und keine Übernahme eines früheren Ergebnisses.

Der NAS-Swap-Wächter beendet auch diesen Versuch: 2341564 KiB freier Swap
liegen unter der unveränderten Reserve von 2359296 KiB. Die originale
Abschaltung erfolgt geordnet (`forced: false`, QEMU Exit 0), der Jenkins-Job
endet als `FAILURE`. Das vollständige Rust-Archiv und seine Bereinigungsquittung
fehlen. 116 Speicherproben enthalten 104 zugeordnete Gastproben und elf
Gast-Abfragefehler. NAS-RAM mindestens 344812 KiB, freier Swap mindestens
2314680 KiB; Gast-OOM-Zähler null, physischer NAS-OOM-Zähler unverändert drei.
Die VM-Cgroup erreicht 3757424640 Bytes RAM und 3034873856 Bytes Swap.

Diese Gegenprobe belegt eine gemeinsame NAS-Ressourcengrenze. Sie erklärt
Leroys zusätzliche Lease-Abbrüche nicht vollständig. Die neue Controller-
Korrektur muss unter der ursprünglichen CI-Last noch qualifiziert werden.
Der gesonderte PostgreSQL-Beobachter ist beendet: 501 Proben, 56
Beobachtungsfehler, 20 beobachtete I/O-Warteereignisse, maximal 4,907 Sekunden
beobachtetes Abfragealter bei I/O-Warten. Datenbank-Haltbarkeit bleibt aktiv;
die längeren historischen Heartbeat-Lücken werden dadurch nicht abschließend
erklärt.

## Dateiinventare der erzeugten Rust-Prüfimages

Beide ausgeschalteten Diagnosegäste wurden anschließend ausschließlich zur
Image-Prüfung separat gebootet und wieder geordnet ausgeschaltet. Dabei
läuft kein ursprünglicher CI-Job erneut. Die Testbaseline ist vor dem Inventar
gestoppt; ein nur erzeugter, niemals gestarteter Image-Container wird exportiert
und entfernt. Die Inventare ersetzen keine fehlenden Originalarchive.

Die Images besitzen jeweils 24842 Einträge und dieselbe Ausführungskonfiguration.
Die vollständigen Inventare gleichen Dateiinhalte, Eigentümer, Rechte, Links,
Geräte und erweiterte Attribute ab; reine Archivzeitstempel werden ignoriert.
547 Einträge unterscheiden sich: 539 Node-Compile-Cache-Dateien, zwei npm-
Cacheindizes, vier Paketverwaltungslogs, der ldconfig-Hilfscache und
`/etc/gitconfig`. Ein npm-Debuglog trägt jeweils einen anderen Zeitstempelnamen.
Alle übrigen Einträge stimmen einschließlich Inhalten und relevanten Metadaten
überein. Das bindet insbesondere Compiler, Bibliotheken und Quellmanifeste.

Die Konfigurationsabweichung ist gesondert aus den ausgeschalteten QCOW2-Platten
ohne Mount, Journal-Replay oder Schreiböffnung gelesen. Die Dateihashes stimmen
mit dem jeweiligen Image-Inventar überein. Beide Dateien enthalten denselben
einzigen Git-LFS-Abschnitt mit denselben vier eindeutig benannten Werten;
lediglich die Reihenfolge dieser Schlüssel ist anders. Rohe Konfigurationswerte
werden nicht veröffentlicht. Unterschiedliche Cacheinhalte können trotzdem
Laufzeiten beeinflussen; vollständige Bytegleichheit oder allgemeine
Leistungsgleichheit wird nicht behauptet.

Private Belege: `full-worker-filesystem-comparison.json` und
`gitconfig-equivalence.json` in `rust-resource-qualification-20261014/`, sowie
`leroy-worker-filesystem.json` und `jenkins-worker-filesystem.json` in den
jeweiligen ursprünglichen Diagnoseordnern. Die historischen neun Dateihashes
und 264 Paketstände bleiben eine zusätzliche, enger begrenzte Gegenprüfung.

## Vorbereitung der folgenden Serie, inzwischen ausgeführt

Die beiden früher genehmigten Vierstundenfenster sind abgeschlossen. Es gibt
keine erneute Dienstpause unter dieser alten Freigabe. Eine neue Serie
`full-release-reconcile8g-20261014` ist für zwei getrennte Fenster von jeweils
höchstens vier Stunden vorbereitet; siehe [Wartungsplan](nas-resource-window.md).
Sie verwendet den tatsächlich geprüften Controller, dasselbe 8-GiB-Profil und
dieselbe gesonderte PostgreSQL-Init-Konfiguration unter beiden Engines.

Jedes Fenster beginnt mit einer frischen unveränderten Rust-Gruppe inklusive
Speicherbeobachtung. Erst ein erfolgreicher Originaljob mit vollständigem Archiv,
unverändertem Testinventar, abgeschlossener Bereinigung und ohne beobachtete
Reserveunterschreitung erlaubt den anschließenden frischen Volllauf. Es müssen
dann noch mindestens zwei Stunden plus 15 Minuten Wiederherstellungsmarge
verbleiben. Andernfalls werden die Dienste unmittelbar wiederhergestellt.
Ergebnisse und Platten der Vorprüfung werden nicht in den Volllauf übernommen.

Die neue Freigabeprüfung verweigert schon vor der Vorbereitung einen Start ohne
neuen ausdrücklich genehmigten Plan. Der NAS-Wächter kennt nur die genauen
eigenen Vergleichs- und Rust-Vorprüfungskennungen und dieselben sieben Dienste.
Alle Quellen, Tests, Fixture-Limits und Abnahmeergebnisse bleiben erhalten.
Ein erfolgreicher Rückgriff auf alte Ergebnisse ist kein Eingangsnachweis.
Vollständige Graphato-Release-Abnahme und Produktionsfreigabe bleiben offen.

## Beobachtete Dienstneustarts außerhalb eines neuen Wartungsplans

Der Abschlussvergleich findet bei Sonarr und SABnzbd neue Prozesse in denselben
unveränderten Containern. Sonarr startet am 14. Oktober um 15:05:31 UTC,
SABnzbd um 15:32:20 UTC. Beide sind bei den Abschlussproben gesund; ihre
Konfigurationshashes, IDs und Images sind unverändert. Der aktuelle Docker-
OOM-Kennwert ist bei beiden falsch, der Docker-Restartzähler null; diese Werte
beweisen nicht, dass es keinen zwischenzeitlichen Neustart gab.

Die begrenzt erhaltenen Docker-Ereignisse enthalten keinen passenden Datensatz.
Die begrenzte Journalprobe zur SABnzbd-Zeit enthält eine Docker-Meldung über
eine nicht rechtzeitig beendete SIGTERM-Anforderung, aber keinen belegten
Anforderer. Für Sonarr liefert die zeitlich begrenzte Journalprobe keine Zeilen.
Eine manuelle Aktion oder ein bestimmter NAS-Verwaltungsmechanismus wird daraus
nicht abgeleitet. Die Ursache ist offen. Diese Beobachtung verhindert die
Behauptung, alle sieben Dienste hätten während der gesamten Diagnose dieselben
Prozesse oder eine unterbrechungsfreie, identische Hintergrundlast besessen.
Es wird deshalb kein zusätzlicher NAS-Dienst zur Ursachenprüfung angehalten.
Die privaten Belege heißen `nas-service-process-changes.json`,
`nas-service-process-journal-probe.json` und
`nas-service-process-classification.json` im gemeinsamen Rust-Qualifikationsordner.

## Abgeschlossene Archivierung und Betriebszustand

Alle drei ausgeschalteten Rust-Diagnoseplatten sind außerhalb laufender CI
auf HDD archiviert. Die Quelle wird beim Kopieren gehasht; eine unabhängige
vollständige Gegenlesung des Archivs bestätigt denselben Hash und dieselbe
Länge. Rechte, Eigentümer und Zeitstempel werden erhalten. Erst danach wird
ausschließlich die genau benannte geschlossene SSD-Datei entfernt. Die
produktiven Jenkins-Buildzähler sind vor, während und nach der Archivierung
unverändert; vollständige Historien sind an den Grenzen inaktiv.

Der Archivstamm ist
`/volume1/docker/leroy-nas-parity/release-vm/0ad540dd5780/archived-rust-memory8g-20261014/`.
Darunter bleiben Vergleichsname, Engine-Verzeichnis und `system.qcow2` erhalten:

| Vergleich | Bytes | SHA-256 |
| --- | ---: | --- |
| `quality-rust-memory8g-leroy-20261014` | 10903093248 | `954fcf95e522e4fb04e272b106d462441bf7c001804db280205f4be36173c0e9` |
| `quality-rust-memory8g-leroy-timing-20261014` | 10843455488 | `0baa29eb59c5900bfb6236dc0e8afe77663874960d0b294818ae12c3d52cad36` |
| `quality-rust-memory8g-jenkins-20261014` | 10180493312 | `e26074806e7cb93f7920d651dbf293cb13a603c8c4fc8ded7581e83812e3a634` |

Am 14. Oktober um 16:23:56 UTC sind 86018854912 Bytes auf SSD frei, rund
80,1 GiB. Ziel-VM, privater Jenkins und eigene Jobworker sind aus. Die
flüchtige Qualifikationsdatenbank und ihr Testnetz sind entfernt, der
PostgreSQL-Beobachter ist beendet, kein Ressourcenfenster-Wächter läuft und
keines der neuen Wartungsverzeichnisse ist auf dem NAS angelegt. Alle sieben
Anwendungen sind gesund mit denselben IDs und Konfigurationen; die oben
dokumentierten zwei Prozesswechsel werden dabei ausdrücklich nicht übergangen.
Leroys korrigierter Controller ist gesund, ohne weiteren Neustart oder OOM;
Runs, Schritte und Artefakte sind weiter erhalten. Der eingefrorene Checkout
ist sauber. Lokales Docker und die Windows-VM werden nicht gestartet oder
verändert; die UI bleibt unverändert.

Die privaten Abschlussbelege heißen `closed-rust-disk-archives.json`,
`final-operations-proof.json`, `validation-final.json` und
`local-tests-final.xml` im gemeinsamen Rust-Qualifikationsordner. Der neue
Wartungsplan war zu diesem Zeitpunkt konkret vorbereitet; die danach erteilte
Freigabe und beide Ergebnisse sind in den folgenden Abschnitten dokumentiert.

## Erstes neu freigegebenes Fenster: lokale Lease-Wartezeit belegt

Der Nutzer hat inzwischen zwei neue Vierstundenfenster mit Wiederherstellung
der sieben Dienste nach jedem Fenster genehmigt. Das erste, unter Leroy,
ist nach 24,65 Minuten Stop-/Start-Spanne geschlossen; alle sieben ursprünglichen
Container sind bis 17:00:38 UTC gesund und stabil geprüft. Controller, PostgreSQL,
Runner, Testdaemon, Skripte und Konfigurationen sind während des Fensters gleich;
der Controller besitzt keinen neuen Neustart oder OOM. Native Jenkins-Historien
und Zähler bleiben ruhig. Quellen und Tests sind unverändert.

Die ursprüngliche Rust-Gruppe läuft in
`full-release-reconcile8g-20261014-rust-leroy`, Run
`0d570e8cf25e4dac9cc40f44f54b20eb`. Checkout besteht, Verifikation endet als
`interrupted`. Der neue Volllauf startet folgerichtig nicht. 104 Speicherproben
enthalten 96 zugeordnete Gastproben und acht Gast-Abfragefehler. Das gemessene
NAS-Minimum ist 304020 KiB verfügbares RAM und 4129784 KiB freier Swap;
die ursprünglichen Reserven sind darin nicht unterschritten. Gast-OOM bleibt
null, physischer NAS-OOM-Zähler unverändert drei. Die VM erreicht
3757395968 Bytes RAM und 2664640512 Bytes Swap. 55 zusätzliche Kontrollproben
enthalten keinen API-Timeout und sechs SQL-Wrapperfehler. Fehlende Beobachtungen
werden weiterhin nicht als erfolgreiche Messungen gewertet.

Die passiven Worker-Logs liefern diesmal die Entscheidung selbst: Eine
erfolgreiche Bestätigung benötigt 44,071 Sekunden; der anschließende lokale
Abbruch zählt 47,071 Sekunden seit dem maßgeblichen Request-Start. Der Worker
wartet nach der langsamen erfolgreichen Antwort regulär drei Sekunden und
erreicht damit vor dem nächsten Versuch die unveränderte 45-Sekunden-Grenze.
Die Controller-Lease wird dabei nicht rechtzeitig durch den Worker erneut
bestätigt. Einzelne lesende API-Proben zuvor zeigen tatsächlich frisch
gespeicherte Leases, nicht nur eine erreichbare Oberfläche. Woher die lange
Request-Latenz stammt, ist durch diese Logs noch nicht vollständig bewiesen.

Ein gesondertes deterministisches Gegenbeispiel verwendet genau 44,071 Sekunden:
Der unveränderte Worker bricht bei 47,071 Sekunden ab, ohne zweiten Request.
Ein ausschließlich in einer privaten Funktionskopie geprüfter Kandidat lässt
nach einer späten erfolgreichen Antwort die reguläre Wartezeit aus und kann
sofort erneut bestätigen. Die Request-Start-Uhr sowie 45-/90-Sekunden-Grenzen
bleiben gleich. Eine 70 Sekunden verspätete Antwort und ein fehlgeschlagener
Folgerequest führen weiterhin zum Abbruch. Diese Simulation ist kein bestandener
Rust-Lauf und kein Beleg für die Ursache der ursprünglichen Transportlatenz.
Repository-Worker und NAS-Jobimage bleiben vor der Jenkins-Gegenprobe unverändert.

Neue private Belege stehen im Planordner `reconcile8g-window-plan-20261014/`
(`lease-pause-counterexample.json`) und im ursprünglichen Rust-Ordner
(`operator-sudo-worker-probes.jsonl`, `operator-readonly-lease-probes.jsonl`,
`leroy-memory-summary.json`). Die Wiederherstellung ist unter
`resource-window-reconcile8g-leroy-20261014/` mit `window-result.json` und
`recovery-verification.json` belegt. Nach einer getrennten Archivierung der
geschlossenen Platte folgt die genehmigte Jenkins-Gegenprobe mit denselben
unveränderten Laufzeitständen. Die vollständige Release-Abnahme bleibt offen.

## Zweites neues Fenster und installierte Taktkorrektur

Die private Jenkins-Gegenprobe mit demselben Laufzeitstand ist beendet:
`graphato-postdeploy-quality#24` scheitert an der unveränderten NAS-Swap-
Reserve. Der Schutzstopp misst 2341412 KiB bei mindestens 2359296 KiB freiem
Swap. Die Ziel-VM beendet sich anschließend geordnet mit QEMU-Exit 0 und
`forced: false`. Ein vollständiges Rust-Archiv fehlt; es startet kein Volllauf.
Alle sieben Dienste sind bis 17:42:49 UTC wieder gesund, nach 30,95 Minuten
Stop-/Start-Spanne. Der Controller bleibt ohne Neustart oder neuen OOM.

144 Speicherproben enthalten 111 streng zugeordnete Gast-/Host-Messungen,
neun Gastfehler und insgesamt 33 fehlende oder nicht zuordenbare Gastproben.
Das beobachtete NAS-Minimum beträgt 331284 KiB verfügbares RAM und
2022076 KiB freien Swap. Gast-OOM bleibt null, der physische NAS-Zähler
unverändert drei. Getrennte Spitzen sind 3758088192 Bytes VM-RAM und
4160004096 Bytes VM-Swap; sie werden nicht als gleichzeitige Messung addiert.
Nahe am Schutzstopp zeitnah aufgenommene Gast-/QEMU-Proben liefern keinen
Beleg für mehrere GiB ungenutzt zurückgehaltenen Speicher. Ihre gelockerte
Uhrzuordnung ist ausdrücklich kein streng synchroner Messnachweis.

Nach beiden geschlossenen Fenstern ist der konkrete Worker-Fehler korrigiert:
Die Drei-Sekunden-Taktung zählt jetzt ab Request-Start. Eine langsame
erfolgreiche Antwort erhält nicht zusätzlich drei Sekunden Wartezeit. Die
konservative Request-Start-Uhr, lokale 45-Sekunden-Grenze, serverseitige
90-Sekunden-Lease, Fencing und Fehlerbehandlung bleiben unverändert. Fünf
Gegenbeispiele scheitern mit dem tatsächlichen alten Modul; 250 lokale Tests
bestehen, neun sind übersprungen. Die zuvor bestandenen 34 echten PostgreSQL-
Tests betreffen den unveränderten Controller und wurden hierfür nicht wiederholt.

Die Linux-Qualifikation prüft 22 echte Worker-Fälle im neuen unveränderten
Basisimage plus einem einzigen Worker-Modul-Layer. Ein zunächst dort
mitgeprüfter Runner-Fall scheitert wegen des anderen Komponentenstands;
dieses ursprüngliche fehlgeschlagene XML bleibt erhalten. Die korrigierte
Zuordnung prüft denselben Runner-Fall im tatsächlich laufenden Runnerimage:
22 Worker-Fälle und ein Runner-Fall bestehen ohne Skip. Es wurde kein Fall
gelöscht und keine zusätzliche Runtime-Abhängigkeit installiert.

Genau das qualifizierte Workerimage
`sha256:0beba2d521cb061818bbf18295ab0329094d31092b4a2cbd8cfa24dca2cf74dc`
ist im eigenen NAS-Testprofil installiert. Seine einzige veränderte Quelldatei
ist `leroy/worker.py`, SHA-256
`62e0bb95efa87469a8677aaf91c198b840f3b14dbabb79e3742ac0d50b86b938`.
Altes Image und geschützte Rückfallkonfiguration bleiben erhalten. Nur der
eigene Runner wird neu gestartet. Graphato-Quellen, Tests und Fixture-Limits
bleiben gleich. Die Ursache der 44-Sekunden-Transportlatenz ist weiter offen;
ein DNS-Versuch im äußeren Docker-Namensraum belegt nicht das Verhalten im
eigentlichen Jobnetz. Es erfolgt keine unbelegte Netzwerkumstellung.

Eine kleine getrennte Diagnose untersucht anschließend die Rückgabe
fragmentierter freier Gastseiten. Sie verwendet ausschließlich eine neue
Wegwerf-VM, höchstens 2 GiB physischen Container-RAM und 512 MiB synthetische
Last; alle sieben NAS-Anwendungen bleiben aktiv. Sie ist keine ursprüngliche
Graphato-Prüfung und kann fehlende Rust- oder Release-Nachweise nicht ersetzen.
Für weitere ursprüngliche Lastprüfungen bleibt zuerst eine belastbare
Ressourcenqualifikation erforderlich. Beide Wartungsfenster sind verbraucht;
vollständige Release-Abnahme und Produktionsfreigabe bleiben offen.

Die fragmentierte Speicherdiagnose ist abgeschlossen. 65487 absichtlich
freigegebene 4-KiB-Seiten entsprechen rund 255,8 MiB. Bei unveränderter
Gastkapazität sinkt QEMUs kombinierter RSS-/Swap-Verbrauch nach Umstellung
von Reporting-Order 4 auf 0 um rund 256,9 MiB (Median aus zwei beziehungsweise
drei ruhigen Messpunkten). Alle behaltenen Seiten bestehen die Inhaltsprüfung;
Gast-Swap bleibt null. Diese kleine künstliche Last weist den Mechanismus
nach, aber weder seine Größenordnung unter Rust noch ausreichende Kapazität
für die ursprüngliche CI. Kein Originalprofil ist dadurch geändert.
Der erste Diagnoseansatz bricht vor der Last an einer Setup-Reihenfolge ab;
sein Fehlerbeleg bleibt erhalten, die korrigierte Diagnose verwendet eine
neue eigene VM-Kennung. Beide VMs sind aus. Kein NAS-Dienst wird dafür pausiert.

Die Abschlussaufnahme um 18:29:17 UTC bestätigt alle sieben ursprünglichen
Container mit unveränderten IDs, Konfigurationen und Prozessen seit der
zweiten Wiederherstellung. Controller, Datenbank und Testdaemon behalten ihre
Prozesse; nur der autorisierte eigene Runner wurde für den Workerwechsel
neu gestartet. Controller ist gesund ohne Neustart oder OOM. Eigene Ziel-VM,
privater Jenkins, Jobworker, Qualifikationscontainer und Wartungswächter sind
aus beziehungsweise entfernt. Die eingefrorenen Quellen sind sauber; native
Jenkins-Historien und Buildzähler bleiben seit Fensterende ruhig. Rund 70,4 GiB
SSD sind frei. Kein lokales Docker oder Windows-Testsystem wurde gestartet.

Private Abschlussbelege: `final-operations-proof.json` im Planordner und
`mechanism-summary.json`, `guest-phases.jsonl`, `leroy-memory-samples.jsonl`
sowie `production-measurement-qualification-page-fragments.json` in
`diag-page-fragments-20261014-b/`. Die ursprünglichen fehlgeschlagenen CI-
Ergebnisse werden weder ersetzt noch als erfolgreich gewertet.

## Weitere Kapazitätsprüfung mit aktiven Anwendungen

`capacity-order0-20261014` untersucht die tatsächlich nutzbare Reserve mit
allen sieben NAS-Anwendungen aktiv, einer frischen 8-GiB-VM und Reporting-Order
0. Die ursprünglichen Hostgrenzen, das 3584-MiB-`memory.high`, der PostgreSQL-
Init und die Gast-Cachepolitik bleiben bestehen. Es werden keine ursprünglichen
Graphato-Jobs oder Tests ausgeführt. Die zusätzliche Last ist ein synthetischer
anonymer Speicherverbrauch, keine Nachbildung der gesamten 6-GiB-Testfixture.

4608 MiB werden in neun 512-MiB-Schritten belegt und gehalten. Der nächste
Schritt wird bei 2721372 KiB freiem Swap und 826444 KiB verfügbarem NAS-RAM
verweigert. Die zusätzliche Zulassung verlangt vor einer weiteren 512-MiB-
Belegung mindestens 3072 MiB freien Swap, also die ursprünglichen 2304 MiB
plus den nächsten Schritt und 256 MiB Vorsichtsmarge. Das ist ein fehlender
Kapazitätsnachweis für 6144 MiB; es beweist nicht, dass jeder echte Rust-Lauf
bei genau 4608 MiB scheitern muss. Die Stichproben der behaltenen Daten sind
intakt. Der Agent gibt seine Speicherbelegungen frei, die VM fährt sauber herunter.

Die unabhängige Zehnsekundenreihe enthält 29 Proben, davon 13 streng zugeordnete
Gast-/Host-Proben, einen Gast-Abfragefehler und insgesamt 16 fehlende oder nicht
streng zuordenbare Gastproben. Ihr Minimum ist 444376 KiB verfügbares NAS-RAM
und 2748536 KiB freier Swap; die getrennte Zulassungsprobe enthält den oben
genannten niedrigeren Swapwert. Gast-OOM bleibt null, der physische NAS-Zähler
unverändert drei. Es ist keine Unterschreitung der ursprünglichen Reserven
aufgezeichnet. Die sieben Container behalten an den Vor-, Zwischen- und
Nachprüfungen ihre Konfigurationen und Hauptprozesse und sind gesund.
Die vollständige native Jenkins-Historienprüfung bestätigt ruhige Grenzen;
identische Hintergrundlast wird nicht behauptet.

Die geschlossenen Platten der beiden ursprünglichen Rust-Fenster werden danach
ohne Boot, Mount, Schreiböffnung oder Journal-Replay gelesen. Ihre Cachewächter
waren aktiv: Leroy enthält 32 Beobachtungen mit 30 Bereinigungen, Jenkins 43
mit 40. Der letzte Jenkins-Eintrag liegt etwa 28 Sekunden vor dem Swap-
Schutzstopp. Der Fehler ist damit nicht durch einen ausgefallenen Cachewächter
erklärt. Der danach verbleibende Dateicache darf nicht pauschal als vollständig
freigebbar oder als Speicherleck gewertet werden. Größe und Änderungszeit der
ausgewerteten Platten und Basiskopie bleiben unverändert.

Die zusätzlich lesend geprüften, bis zu 30 jüngsten Buildnummern pro nativem
Qualitäts-, Web- und Releasejob enthalten keinen erhaltenen passenden
`RELEASE_COMMIT`-Nachweis für `0ad540dd578033d45e4d0c25d89fbe57b32102a4`.
Dies ist keine Aussage über nicht mehr erhaltene ältere Builds. Neuere Erfolge
eines anderen Commits ersetzen weiterhin keine eingefrorene Abnahme.

Die Hostinventarisierung liefert keine große zurückgebliebene CI-Last im
eigenen Docker-Testdaemon: Vor dem Versuch belegt er rund 302 MiB einschließlich
Swap und enthält keine aktiven Jobworker oder privaten Jenkins. Ein eigener
Test-Gitea ist aktiv. Die Inventare unterscheiden äußere Container, verschachtelte
Container und Prozesswerte; gemeinsame RSS-Seiten werden nicht als eindeutige
physische Gesamtsumme addiert. Ein laufender produktiver Buildkit-Container und
NAS-Systemdienste werden ausschließlich gelesen und nicht angehalten.

Die reproduzierbare Diagnose liegt in `scripts/probe_nas_vm_capacity.py`.
Reporting-Order 0 ist ein ausdrücklicher neuer Parameter; vorhandene Aufrufer
behalten Order 4 und ihre gespeicherte Konfiguration. Eine vorhandene VM kann
beim Fortsetzen nicht unbemerkt umgestellt werden. Die ursprünglichen
Vergleichsprofile und Ergebnisse bleiben unverändert.

Vor einem weiteren ursprünglichen Lastlauf ist jetzt ein
[einmaliger kurzer Kapazitätstest](nas-resource-window.md) mit freigehaltenen
Ressourcen und zusätzlich inaktivem privatem Jenkins vorbereitet. Seine
Freigabe steht aus. Beide früheren Fenster bleiben geschlossen, alle sieben
Dienste aktiv. Die vollständige Graphato-Release-Abnahme ist weiter offen.

Private Belege: `capacity-order0-20261014/` mit Phasen, Agentenidentität,
Speicherreihe und Produktionsbeobachtung; `memory-capacity-followup-20261014/`
mit Hostinventaren, `original-offline-cache.json`, `native-frozen-history.json`
und dem tatsächlich ausgeführten ursprünglichen Diagnosequelltext.

Der Abschlussbeleg um 19:28:51 UTC bestätigt gesunde sieben NAS-Anwendungen
und unveränderte Hauptprozesse aller vier eigenen Steuerdienste. Ziel-VM,
privater Jenkins und Wartungswächter sind aus; eigene Jobworker und
Qualifikationscontainer sind entfernt. Rund 70,3 GiB SSD sind frei. Der
eingefrorene Checkout ist sauber. Die aktuelle lokale Gesamtsuite besteht
mit 266 Tests; 34 PostgreSQL- und neun SCM-Baseline-Prüfungen sind mangels
ihrer separaten Umgebung übersprungen. Der frühere vollständige Linux-
PostgreSQL-Nachweis des unveränderten Controllers bleibt getrennt erhalten.
Ruff und die Syntax-/Namensprüfung von elf Remote-Payloads bestehen.
Der neue Kapazitäts-Wartungsplan ist ausschließlich lokal vorbereitet;
sein NAS-Verzeichnis und Wächter sind noch nicht angelegt.

## Neuer Kapazitätsbefund vom 14.10., 21:45–21:57 Uhr Berlin

Bei pausierten sieben Anwendungen und zusätzlich inaktivem privatem Jenkins
erreichte die neue Probe 5120 MiB anonyme Zusatzlast. Die weitere Zuteilung
wurde mit 723652 KiB verfügbarem NAS-RAM und 3058272 KiB freiem NAS-Swap
vorsichtig verweigert; der nächste 512-MiB-Schritt benötigt zusätzlich
256 MiB Reserve über der unveränderten Swap-Untergrenze. Dies ist kein
Beleg einer harten 5-GiB-Grenze oder eines zwangsläufigen Originaltestfehlers.

Die Speicherreihe enthält 29 Proben, davon sieben streng zeitlich zuordenbar;
22 sind unvollständig oder wegen Gastzeitversatz nicht zuordenbar. Die
behaltenen Seiten waren intakt, Gast-Swap blieb null, Gastkapazität gleich,
kein neuer OOM. Alle sieben Anwendungen sind wieder gesund. Originaljobs
und eine vollständige Abnahme liefen dabei nicht.

Vor dem getrennt freigegebenen Nachtfenster wurde der VM-Start begrenzt:
Die vollständige SHA-256-Prüfung der Baseline verwendet Cachefreigabe-Hinweise
für bereits gelesene Abschnitte. Ihre Wirksamkeit ist zunächst eine Hypothese,
keine bereits gemessene Kapazitätsverbesserung. Zusätzlich kann die bestehende
weiche Cgroup-Grenze direkt nach Containerstart statt erst nach Gastbereitschaft
greifen. Snapshot, Saatdateien, Quellen und ursprüngliche Tests bleiben gleich.
Die alte Launcherdatei und die alten Stagingmetadaten sind separat gesichert.

## Nachtproben: tatsächliche Kapazität und begrenzter Originalvergleich

Die getrennten Proben mit frühem `memory.high` und unveränderten Quellen,
Tests, Fixture-Grenzen und NAS-Abbruchwerten ergeben:

| Weiche VM-Grenze | Erreichte anonyme Zusatzlast | Kleinster NAS-RAM-Wert | Kleinster NAS-Swap-Wert in der Reihe |
| --- | --- | --- | --- |
| 3584 MiB | 5120 MiB | 464900 KiB | 2980288 KiB |
| 3840 MiB | 5120 MiB | 337960 KiB | 3111200 KiB |
| 4096 MiB | 5632 MiB | 339496 KiB | 2672724 KiB |

Alle drei Proben verweigerten den nächsten Schritt vorab. Die Beobachtungen
zeigen keinen neuen OOM; behaltene Seiten wurden geprüft, Ziel-VMs sauber
beendet. Die getrennte Zulassungsprobe kann einen niedrigeren Swapwert als
die periodische Reihe enthalten; beide bleiben im Beleg erhalten. Streng
zeitlich zugeordnete Gast-/Hostproben: 18/28, 27/27 und 24/32. Der Nachweis
für 6144 MiB über 60 Sekunden ist **nicht** erbracht.

Diese synthetische Maximallast ist keine Messung des tatsächlichen
Rust-Jobs. Der weitere Plan ersetzt deshalb die zusätzliche Annahme,
dass vor jedem Originalversuch der volle synthetische Höchstwert erreicht
sein müsse, durch einen begrenzten ursprünglichen Rust-Vergleich mit den
bereits vorhandenen NAS-Abbruchgrenzen. Die Grenze von 6 GiB für den
Originalbuilder und alle Testinhalte bleiben gleich. Das 4096-MiB-Profil
hat in diesen Proben die höchste Teilbelegung bei gewahrten Reserven
erreicht; beide Engines erhalten dieselbe Konfiguration und frische
Baselines. Erst zwei vollständige erfolgreiche Original-Rust-Ergebnisse
mit passendem Inventar und Abschlussbelegen erlauben die Release-Läufe.
Es wird kein synthetischer Erfolg aus der Teilbelegung abgeleitet.

## Ursprüngliche Jobs im Nachtfenster B

Mit 4096 MiB `memory.high` wurden beide ursprünglichen Testimages gebaut:
462,576 Sekunden unter Leroy und 474,409 Sekunden unter privatem Jenkins.
Anschließend begann jeweils die ursprüngliche Rust-Kompilierung.
Leroy-Run `216e012393544c678c3773e91c7fe33f` wurde unterbrochen, nachdem
eine Lease-Anfrage 77,141 Sekunden dauerte. Die vorherige Bestätigung war
beim Anfragebeginn 8,211 Sekunden alt; die spätere lokale Altersmessung
ergab 80,819 Sekunden. Das beweist einen erheblichen Stillstand, erklärt
aber weder dessen Transportphase noch die zugrunde liegende Ursache.
Allgemeine API-Gesundheitsprüfungen blieben schnell.

Der private Jenkins-Job `graphato-postdeploy-quality#25` lief länger,
bis der unabhängige VM-Schutz 83276 KiB verfügbaren NAS-RAM gegenüber
131072 KiB Untergrenze meldete. Gleichzeitig waren 4812024 KiB Swap frei.
Die VM endete sauber; der NAS-OOM-Zähler blieb unverändert. Aus diesem
Schutzabbruch folgt kein Fehler in Graphato oder dessen Tests.

Beide Laufwerke wurden außerhalb der CI-Last nach vollständigem
Prüfsummenvergleich auf HDD archiviert. Alle sieben Anwendungen wurden
gesund und stabil wiederhergestellt. C senkt auf beiden Seiten die weiche
VM-Grenze auf 3584 MiB, behält den 8-GiB-Gast und die ursprünglichen
Fixture-Grenzen bei. Eine opt-in HTTP-Phasendiagnose, Thread-/Cgroup-
Beobachtung und lesende PostgreSQL-Wartezustände sollen einen erneuten
Lease-Stillstand erklären. Beliebige Logs, Anfrageinhalte und SQL-Texte
werden dabei nicht übernommen. Die lokale Lease-Grenze bleibt 45 Sekunden,
die serverseitige 90 Sekunden.

Die Erneuerungskorrektur war zuvor nur im Jobimage vorhanden. Sie ist jetzt
auch im tatsächlichen Runner-Image installiert und mit allen 23 Linux-Tests
geprüft; fünf Gegenbeispiele scheitern beim alten Image. Nur die Funktion
`maintain_lease` wurde dort ersetzt, alle anderen Modulbestandteile und die
Imagekonfiguration blieben gleich. Das zusätzliche diagnostische Jobimage
besteht 28 Linux-Tests. Diese Prüfungen ersetzen keine erfolgreichen
ursprünglichen Rust- oder Release-Läufe.

## Nachtfenster C: Lease blieb erhalten, VM-Swap-Schutz griff

Der unveränderte Testimage-Bau bestand in 476,562 Sekunden. Anschließend
erreichte die Kompilierung `graphato_desktop_lib`; ein beobachteter Compiler-
Prozess belegte gut 4 GiB im Gast. Leroy-Run
`c40b1b4e2f8d438d9aa90e034637137a` hielt seine Lease bis zum Zielausfall.
Um 22:34:52 UTC griff der NAS-Swap-Schutz mit 2351552 KiB gegenüber
2359296 KiB Untergrenze; verfügbarer RAM war dabei 724860 KiB. Die VM
fuhr sauber herunter (QEMU-Code 0, keine erzwungene Beendigung).
Der CI-Schritt scheiterte anschließend am nicht mehr erreichbaren Ziel.
Dies ist weder eine Lease-Unterbrechung noch ein vollständiges Testergebnis.

Die Speicherreihe enthält 116 Proben, zwölf streng zugeordnet; 104 sind
unvollständig oder nicht zuordenbar. Periodisches Minimum: RAM 378900 KiB,
Swap 2352788 KiB. Die Gast-OOM-Beobachtungen enthalten nur null, decken
aber wegen dieser Lücken nicht den gesamten Zeitraum ab. NAS-OOM blieb drei.
Der Jenkins-Vergleich wurde nach der Reserveunterschreitung nicht gestartet.
Alle sieben Anwendungen wurden gesund und stabil wiederhergestellt.

Die Zusatzdiagnose zeigt während kurzer Header-Wartezeiten PostgreSQL
`WalSync`/`WALWrite`. Andere Verzögerungen gehen mit Major Page Faults und
Kernel-Wartezuständen `read_extent_buffer_pages`, `blk_mq_get_tag` und
`folio_wait_bit_common` des Heartbeat-Threads einher. Das verschachtelte
Docker-Dateisystem liegt auf dem Btrfs-Datenpool, Controller und PostgreSQL
bereits auf SSD. Keine dieser Beobachtungen beweist rückwirkend die Ursache
der alten 77-Sekunden-Anfrage. Die ursprüngliche Init-Prozess-Beobachtung
wird getrennt von den korrigierten Python-/Thread-Daten aufbewahrt.
