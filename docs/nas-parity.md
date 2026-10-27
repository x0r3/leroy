# Jenkins-/Leroy-Vergleich auf dem NAS

**26. Oktober 2026: Der NAS-Testbetrieb ist auf Nutzerwunsch beendet.**
Jenkins bleibt produktiv; die Ablöse wird nach Bereitstellung eines separaten
Build-Servers fortgesetzt. Aktueller Stand und Plan:
[Checkpoint](checkpoint-2026-10-26.md), [status.md](status.md).
Die folgenden Ausführungen beschreiben historische Versuche. Die verlinkten Detailquittungen unter
`test-results/` bleiben private lokale Nachweise und sind nicht mitgepusht.

Am 7. Oktober ist die lokale Docker-Umgebung auf Nutzerwunsch angehalten, mit
Ausnahme von NameFinder. Die drei laufenden Leroy-Testdienste sind gestoppt;
Volumes, Images und bisherige Nachweise bleiben erhalten. Nach Freigabe des
WSL-Dateicaches sinkt der beobachtete Windows-Arbeitsspeicher des Docker-/WSL-
Prozesses von ungefähr 6,4 GiB auf gut 1 GiB. Die bereits zuvor durch OOM beendete
Windows-Test-VM wird nicht erneut gestartet.
[Lokale Docker-Bereinigung](../test-results/local-docker-cleanup/20261006T224728Z.json).
[Abschließende lokale Prüfung](../test-results/local-docker-cleanup/final-verification.json).

Der Vergleich wird direkt im vorhandenen isolierten NAS-Testdaemon
ausgeführt: Jenkins, Leroy, Leroy, Jenkins, mit frischen Fixtures pro Probe,
dem ursprünglichen produktiven CI-#23-Runtime-Inhalt und einem einmalig gebauten
Browser-Worker aus dem unveränderten Original-Dockerfile. Das ursprüngliche
Quellarchiv ist einschließlich seines gespeicherten SHA-256 und aller 53 zuvor
geprüften Worker-Dateien bestätigt. Ein separater Beobachter erfasst ausschließlich
HTTP-Metadaten an der Schnittstelle des isolierten Servers. Er hält keine Pakete,
Authentifizierungsheader oder Argumentwerte fest. Sein Aufwand ist begrenzt,
aber nicht als Einfluss ausgeschlossen. Die Originaltests und ihre Ressourcen-
und Ratenlimits bleiben unverändert. Diese Proben vergleichen den CI-Aufruf des
originalen Soak-Runners; sie ersetzen keine vollständige Release-Abnahme.
[Vorbereiteter Vergleich und Quellenprüfung](../test-results/nas-parity/followup/nas-native-soak-preparation/planned-comparison.json).

Der NAS-Host hat sechs CPUs und etwa 7,5 GiB physischen RAM. Das unterscheidet
sich sowohl von der vorherigen Windows-Test-VM als auch vom produktiven
Graphato-Anwendungshost mit acht CPUs und 16 GiB RAM. Der NAS-Systemparser kann
das unveränderte AppArmor-ABI-4-Profil zunächst nicht lesen. Die Vorbereitung
verwendet deshalb einen passenden Parser samt Includes ausschließlich im
isolierten Alpine-Testdaemon. Der installierte Parser 4.1.7 liest das bytegleiche
Originalprofil erfolgreich; die geladenen Kernelprofile sind dabei unverändert.
NAS-Systempakete werden nicht aktualisiert, bestehende Profile nicht ersetzt.
Ein für die späteren Proben neu geladenes Originalprofil wird nur ohne aktive
Nutzer wieder entfernt. Die übertragenen 2.406.604.800 Bytes des Runtime-Archivs
stimmen per SHA-256 mit dem zuvor verifizierten Originalarchiv überein. Der
Transfer nutzt den bereits vorhandenen NAS-Compilerplatz-Wächter; aktive externe
Postdeployment-Prüfungen sind ausdrücklich keine ruhige Messphase. Der Import,
Worker-Bau und die neuen Soak-Proben wurden zunächst hinter den produktiven
Jenkins-Jobs zurückgestellt. Nach deren Ende scheitert der Materialisierungsversuch
am 7. Oktober um 02:34 Uhr MESZ beim `docker load` im isolierten Testdaemon mit
Exitcode 1. Die erhaltene Fehlerausgabe belegt noch keine Ursache des Imports.
Bei diesem Versuch wurden keine Soak-Tests gestartet. Seine Quittung bleibt
als fehlgeschlagener Vorbereitungsversuch erhalten.
[Importfehler](../test-results/nas-parity/followup/nas-native-soak-preparation/preparation-failure.json).
[Lesende AppArmor-Vorprüfung](../test-results/nas-parity/followup/nas-native-soak-preparation/original-profile-preflight.json).
[Erfolgreiche Vorprüfung im Testdaemon](../test-results/nas-parity/followup/nas-native-soak-preparation/original-profile-owned-parser-preflight.json),
[Geprüfter Runtime-Transfer](../test-results/nas-parity/followup/nas-native-soak-preparation/runtime-transfer-verified.json).

Am 11. Oktober ist die Ursache reproduziert: `docker exec` ohne `-i` reicht keine
Standardeingabe an `docker load` weiter. Der Transportvergleich empfängt null
beziehungsweise 1.152 Bytes; der ursprüngliche Import liefert mit demselben
vollständigen Archiv `unrecognized image format`. Mit `-i` gelingt der Import.
Das Archiv bleibt 2.406.604.800 Bytes groß mit SHA-256
`5806b2d02f4b06dc0c66d4ba55a2e4231b823b87f9df3ebc8168741c1b90221e`.
Alle 20 RootFS-DiffIDs, das ursprüngliche Config-Digest `5fac4247b679…` und das
Serverprogramm `faab058b0006…` stimmen überein. Das lokale Docker-29-Image-ID
`b00a432be807…` ist das Manifest-Digest; dessen Content-Store-Blob verweist auf
das originale Config-Digest. Dieser Darstellungsunterschied ist keine Änderung
des Runtime-Inhalts.
[Transportfehler](../test-results/nas-parity/followup/nas-native-soak-import-recovery/missing-stdin-reproduction.json),
[Runtime-Inhaltsprüfung](../test-results/nas-parity/followup/nas-native-soak-import-recovery/runtime-content-verified.json).

Der Original-Worker wird erfolgreich auf dem NAS gebaut. Seine eingebauten
Originalprüfungen bestehen; alle 53 festgehaltenen Test-/Treiberdateien sowie
Node 24.14.1 und Playwright 1.63.0 stimmen überein. Beide Extraktionen enthalten
die exakt geprüften 2.339 Quelldateien. Der Buildkit-Builder ist anschließend
gestoppt. Die produktiven Jenkins-Jobs bleiben während der Wiederherstellung
unverändert und die Messwächter bestätigen eine ruhige Produktionsphase.
[Geprüfte Eingaben](../test-results/nas-parity/followup/nas-native-soak-preparation/prepared-inputs.json).

Die erste Jenkins-Probe (`leroy-original-soak-nas`, Build 1) scheitert beim
Fixture-Start mit `PostgreSQL operation failed (io)`. Sie führt keinen Soak-Fall
aus, wird von Jenkins korrekt als fehlgeschlagen behalten und bestätigt
vollständiges Cleanup. Ein separater Diagnoseversuch mit dem ursprünglichen
Fixture-Helfer startet PostgreSQL und Graphato erfolgreich. Der erste Startfehler
ist damit noch nicht erklärt. Die neue Serie und ihre Diagnosehelfer bekommen
eigene Kennungen; vorherige Verzeichnisse und CI-Builds bleiben erhalten.
Ein Fehler im erweiterten Vorprüfungshelfer (Image-Standardbenutzer statt explizitem
Root für das private Diagnoseverzeichnis) wird vor dem nächsten Teststart behoben.
Die vollständige Beobachtervorprüfung bestätigt Namespace-Eintritt, Kernel-Filter,
Dateischreiben und geordnetes Beenden. Originalquellen und Tests bleiben unverändert.
[Erster Startfehler](../test-results/nas-parity/followup/nas-original-soak-engine-comparison/jenkins-1/analysis.json),
[Gesunder Startversuch](../test-results/nas-parity/followup/nas-native-startup-diagnostics/20261011T093546534356Z/startup-diagnostic.json).

Die erste vollständige Serie `20261011-c` endet wie folgt:

| Probe | Originalergebnis | Soak-Dauer |
| --- | --- | --- |
| Jenkins 1 | Fehlgeschlagen beim Senden eines Prompts | 18,427 s |
| Leroy 1 | Bestanden: 120 Prompts, vier Tabs | 310,389 s |
| Leroy 2 | Fehlgeschlagen beim Senden eines Prompts | 31,288 s |
| Jenkins 2 | Bestanden: 120 Prompts, vier Tabs | 316,356 s |

Alle vier Originalfälle werden tatsächlich ausgeführt und vollständig aufgeräumt.
Die CI-Ergebnisse entsprechen jeweils dem Originaltest; Runtime und Worker bleiben
identisch. Alle Produktionswächter bestätigen ruhige Jenkins-Fenster. Beide Engines
zeigen in dieser Serie Erfolg und Fehler; sie belegt keine ausschließlich Leroy
zugeordnete Abweichung und keine stabile vollständige Release-Abnahme.
[Serienergebnis](../test-results/nas-parity/followup/nas-original-soak-engine-comparison-20261011-c/analysis.json).

Die Antworterfassung dieser Serie ist unvollständig. Der Packet-Socket mit
`ETH_P_IP` erfasst eingehenden Bridge-Verkehr, aber keine ausgehenden
API-Antworten. Die im ursprünglichen Serienbericht positiven
`server_boundary_metadata_qualified`-Flags prüfen noch keine Antwortabdeckung.
Die ergänzende Qualifikation korrigiert diese Einordnung für alle vier Spuren:
Keine Command-Antwort ist zugeordnet; null beobachtete 429 beweisen deshalb
keine Abwesenheit von 429. Originalberichte und Rohartefakte werden nicht ersetzt.
[Korrigierte Einordnung](../test-results/nas-parity/followup/nas-original-soak-engine-comparison-20261011-c/metadata-qualification.json).

Die kontrollierte NAS-Netzwerkprobe vom 11. Oktober bestätigt den Fehler und
isoliert seine Ursache: Der Originalbeobachter erkennt fünf Anfragen und null
Antworten; nach alleiniger Änderung des Socket-Protokolls auf `ETH_P_ALL`
werden fünf Antworten einschließlich einer vorgegebenen 429 erkannt. Auch die
vollständig korrigierte Fassung besteht. Es werden keine Graphato-Tests oder
Anwendungskommandos ausgeführt. Der IPv4-/TCP-8042-Kernelfilter bleibt aktiv;
Rohpakete, Authentifizierungsheader und Argumentwerte werden nicht gespeichert.
HTTP-Status wird beim Empfang der Header festgehalten; Paketzeitpunkte stammen
aus Kernel-Zeitstempeln. Der Kernel-Egresspfad verwendet die
[All-Protocol-Taps](https://github.com/torvalds/linux/blob/v6.12/net/core/dev.c#L2152).
Die nachfolgenden Serien verwenden diese separat geprüfte Beobachtung; alle
Anwendungs-/Test-/Image-Eingaben und Grenzwerte bleiben gleich.
[Kontrollierte Transportprobe](../test-results/nas-parity/followup/nas-passive-transport/20261011T100835723658Z/result.json).

Die Serie `20261011-d` scheitert bei ihrer ersten Jenkins-Fixture, bevor ein
Soak ausgeführt wird. Die ursprüngliche Prüfung `pg_isready -U graphato -d graphato`
akzeptiert bereits den temporären Unix-Socket-Server während der Initialisierung.
Ihr positiver Healthcheck endet um 10:12:05,202 UTC; der temporäre Server wird
um 10:12:05,955 UTC beendet. Graphato startet um 10:12:06,400 UTC und meldet
den Datenbank-I/O-Fehler um 10:12:11,702 UTC. Erst um 10:12:12,419 UTC entsteht
der endgültige TCP-Listener; die Datenbank wird um 10:12:13,035 UTC endgültig
bereit. Dieser Start-Race ist anhand der unveränderten Compose-Datei,
Docker-Healthlogs und PostgreSQL-/Graphato-Logs belegt. Die Ursache des älteren
Starts ohne Datenbanklog wird dadurch nicht rückwirkend bewiesen. Der Healthcheck
bleibt unverändert, Cleanup ist bestätigt, die nächste Serie heißt `20261011-e`.
[Belegter Fixture-Start-Race](../test-results/nas-parity/followup/nas-original-soak-engine-comparison-20261011-d/jenkins-1/setup-failure-analysis.json).

In `20261011-e` besteht die erste Jenkins-Probe nach 308,510 Sekunden. Die
korrigierte Beobachtung ordnet alle 120 Prompt-Antworten als HTTP 200 zu. Die
Gesamtspur bleibt wegen 122 Kernel-Paketverlusten, zehn Parserfehlern und
unvollständiger Antwortabdeckung unqualifiziert für eine vollständige
HTTP-Statusaussage. Null beobachtete 429 werden weiterhin nicht als Nachweis
ihrer vollständigen Abwesenheit bewertet. Die nachfolgende Leroy-Fixture
scheitert erneut vor der Testausführung beim Datenbankstart.
Die Fortsetzung `20261011-f` übernimmt ausschließlich den bereits ausgeführten
Jenkins-Fall mit identischen Quellen-/Image-/Helferprüfsummen und bestätigtem
Cleanup und Produktionsfenster. Sie wiederholt keinen ausgeführten Test.
Der Setup-Fehler bleibt im vorherigen Verzeichnis erhalten. Der Test-Jenkins
startet zwischen diesen Versuchen erneut; gleiche kontinuierliche Controller-
Ausgangsbedingungen werden deshalb nicht behauptet.
[Jenkins mit Antworterfassung](../test-results/nas-parity/followup/nas-original-soak-engine-comparison-20261011-e/jenkins-1/analysis.json),
[Explizite Fortsetzung](../test-results/nas-parity/followup/nas-original-soak-engine-comparison-20261011-f/continuation-receipt.json).

Die fortgesetzte Serie ist mit vier erfolgreichen Originalfällen abgeschlossen:

| Probe | Originalergebnis / CI-Ergebnis | Soak-Dauer | Erfasste Prompt-Antworten | Verlorene Kernel-Pakete |
| --- | --- | --- | --- | --- |
| Jenkins 1 aus `20261011-e` | Bestanden / `SUCCESS` | 308,510 s | 120 × HTTP 200 | 122 |
| Leroy 1 | Bestanden / `succeeded` | 315,857 s | 120 × HTTP 200 | 117 |
| Leroy 2 | Bestanden / `succeeded` | 309,201 s | 120 × HTTP 200 | 155 |
| Jenkins 2 | Bestanden / `SUCCESS` | 309,814 s | 120 × HTTP 200 | 159 |

Alle vier Originalfälle bestätigen Cleanup ohne OOM; alle Produktionsfenster
sind lesend als ruhig qualifiziert. Die Eingaben bleiben bytegleich. Die Zeiten
bezeichnen den originalen Soak-Fall, nicht die gesamte CI-Laufzeit einschließlich
Fixture-Start und Cleanup. Die vollständige HTTP-Statusabdeckung ist trotz der
zugeordneten Prompt-Antworten weiterhin nicht belegt: Paketverluste, unvollständige
TCP-Ströme und fehlende Antwortzuordnungen bleiben in allen vier Gesamtspuren.
Null beobachtete 429 beweisen ihre Abwesenheit deshalb nicht.
[Abgeschlossener Original-Soak-Vergleich](../test-results/nas-parity/followup/nas-original-soak-engine-comparison-20261011-f/analysis.json).

Während der letzten Jenkins-Probe läuft eine lesende SSH-Abfrage der produktiven
Historie in ein Zeitlimit. Der bestehende Testbuild wird nicht abgebrochen und
nicht erneut gestartet. `recover_nas_original_soak_observation.py` sammelt genau
diesen Build und vervollständigt dessen ursprünglichen Vorher-/Nachher-Wächter.
Eine fehlende Zwischenbeobachtung gilt nicht als ruhige Lastphase. Die erfolgreiche
Abschlussqualifikation bestätigt das gesamte ursprüngliche Fenster. Der eigene
Test-Jenkins ist anschließend wieder gestoppt, das temporäre Profil ohne aktive
Nutzer entfernt und die übrigen AppArmor-Profile unverändert.
[Wiederaufnahme ohne erneuten Teststart](../test-results/nas-parity/followup/nas-original-soak-engine-comparison-20261011-f/observation-recovery.jsonl),
[Controller wieder gestoppt](../test-results/nas-parity/followup/nas-original-soak-engine-comparison-20261011-f/jenkins-controller-restored.json),
[Profil bereinigt](../test-results/nas-parity/followup/nas-original-soak-engine-comparison-20261011-f/temporary-profile-removed.json).

Die Abschlussprüfung bestätigt einen bereiten Leroy-Controller, alle 16
Katalogeinträge deaktiviert, keine aktiven oder wartenden Leroy-Läufe, keine
laufenden Fixtures, Beobachter oder Koordinatoren und keine aktiven produktiven
Jenkins-Builds. Eine leere produktive Jenkins-Warteschlange wird nicht behauptet.
[Abschlusszustand](../test-results/nas-parity/followup/nas-original-soak-engine-comparison-20261011-f/final-state.json).

Nach Ende der Messläufe werden die realen Leroy-Läufe visuell geprüft: zwei
Erfolge (`dc697e0a…`, `dbf96612…`), ein ausgeführter Soak-Fehler (`25d685b6…`)
und ein Fixture-Startfehler (`1c00aeca…`). Graph/Konsole, Ergebnisse und Artefakte
sind jeweils bei 1.440 und 390 Pixel Breite geprüft. Alle 24 Screenshots werden
visuell kontrolliert; Status, Zeitachsenfarben, Textumbruch und Artefaktlisten
passen, ohne Seitenüberlauf oder Browserfehler. Die Größe und SHA-256 aller
16 Artefakt-Downloads stimmen mit den Metadaten überein. Der leere strukturierte
Ergebnisbereich ist bei diesen Diagnosebefehlen erwartbar: Sie hinterlegen die
Originalquittungen als Artefakte und melden das Ergebnis zusätzlich in der Konsole.
[Erfolgreiche Laufansichten](../test-results/nas-parity/original-soak-success-ui-20261011/report.json),
[Fehleransichten](../test-results/nas-parity/original-soak-failure-ui-20261011/report.json).

Damit ist der aktuelle Import-/Soak-Diagnoseauftrag abgeschlossen. Beide Engines
führen den unveränderten Test erfolgreich aus; die erste vollständige Serie
zeigt weiterhin beide Ergebnisarten unter beiden Engines. Weder die Ursache aller
früheren Fehler noch die historische Qualitätsabweichung sind damit bewiesen.
Die vollständige Graphato-Release-Abnahme und Produktionsfreigabe bleiben offen.

Produktive Jenkins-Builds dürfen während dieser Abnahme weiterlaufen, auch für
neue `master`-Commits. Die Vergleichsläufe bleiben auf `0ad540dd5780` gebunden;
die Anwendungs-Ziel-VM, Quellarchive und Runtime-Images sind getrennt von der
Produktion. NAS-CPU, Speicher und I/O bleiben gemeinsam genutzte Ressourcen.
Vor jedem neuen NAS-Messlauf und jeder Zielwiederherstellung prüft der Testhelfer
die produktiven Jenkins-Builds lesend über SSH. Bei einem aktiven Build wartet er;
Jenkins und seine Trigger werden nicht angehalten. Vor und nach dem Lauf werden
Build-Zähler und unvollständige Builds einschließlich älterer paralleler Builds
festgehalten. Ein währenddessen gestarteter Produktionsbuild entwertet den Lauf
für einen Lastvergleich, auch wenn er vor der Abschlussprüfung fertig ist.
Funktionale Ergebnisse bleiben erhalten. Eine spätere Wiederaufnahme ersetzt
den ersten Überschneidungsnachweis nicht. Andere NAS-Dienste und eine leere
Jenkins-Warteschlange sind durch diese Dateiprüfung nicht nachgewiesen; gleiche
Hintergrundlast wird damit nicht garantiert. Ein neuer Master-Commit ersetzt
den eingefrorenen Stand nicht.

Die aktuelle Untersuchung verwendet auf ausdrücklichen Nutzerwunsch weiterhin
die unveränderten Tests und den eingefrorenen Quellstand. Der separate
Soak-Testtreiber-Vorschlag wird zurückgestellt. Acht erhaltene Original-Läufe
von `0ad540dd5780` sind gemeinsam ausgewertet: drei erfolgreiche Soak-Läufe,
fünf Abbrüche beim ursprünglichen Prompt-Aufruf wegen des Ratenlimits nach
12,994 bis 19,861 Sekunden. Dasselbe isolierte Runtime-Image hat erfolgreiche
und fehlgeschlagene Läufe. Die erfassten Source-, PostgreSQL-, Compose-, Fixture-,
Node- und Rust-Angaben stimmen überein. Das ursprüngliche produktive Runtime-
Image und der Anwendungshost unterscheiden sich allerdings von der isolierten
Ausführung; insbesondere sind dort etwa 16 statt 10 GiB RAM verfügbar.
[Vergleich der unveränderten Original-Läufe](../test-results/nas-parity/followup/native-browser-observations/web-18/original-test-comparison.json).

Das ursprüngliche produktive CI-#23-Image ist über seinen gespeicherten
Registry-Digest lesend kopiert, einschließlich aller zwanzig Layer und ihrer
unkomprimierten Prüfsummen. Der Import in die isolierte VM ist abgeschlossen.
Alle 264 Debian-Paketversionen sowie die geprüften Node-, Systembibliotheks- und
Startskript-Dateien stimmen mit dem isoliert gebauten Image überein. Die
37.587.340 Bytes der ausführbaren Server-Code-Sektion unterscheiden sich an
zwölf Bytes; die Disassemblierung ordnet alle Unterschiede den beiden
Build-Zeitstempeln in Build-Information und Web-Asset-Prüfung zu. Die öffentlichen
UI-Dateien stimmen nach ausdrücklich dokumentierter Normalisierung dieser
Zeitstempel und der Asset-Dateinamen überein. Das belegt keine vollständige
Byteidentität der Images oder sämtlicher UI-Importkanten.
[Runtime-Inhalte](../test-results/nas-parity/followup/native-browser-observations/web-18/runtime-content-comparison.json),
[Code-Unterschiede](../test-results/nas-parity/followup/native-browser-observations/web-18/server-code-delta.json).

Der feste A/B/A-Vergleich ist abgeschlossen: isoliertes Runtime-Image,
produktives Original-Image, isoliertes Runtime-Image. Alle drei unveränderten
Soak-Aufrufe scheitern am ursprünglichen Prompt-Ratenlimit nach 14,130, 15,497
beziehungsweise 19,413 Sekunden. Sie verwenden frische private Fixtures und
denselben tatsächlichen Browser-Worker in der Vier-CPU-/10-GiB-Test-VM.
Die 53 geprüften Test-/Treiberdateien dieses Workers stimmen bytegenau mit
dem eingefrorenen Git-Stand und dem erhaltenen Jenkins-Worker überein; Node
24.14.1 und Playwright 1.63.0 sind ebenfalls gleich. Fixtures und Test-Credentials
werden durch den Originalhelfer entfernt. Das aktive Release und die ursprünglichen
Abnahmequittungen bleiben unverändert. Der Diagnoseauftrag ist als Sammlung
erfolgreich; keine seiner drei Soak-Proben besteht.

Die Vorprüfung findet keine produktiven Builds. Jenkins CI #28 startet jedoch
unabhängig am 6. Oktober um 23:31:11,009 Uhr MESZ und überschneidet sich mit allen
drei Proben. Dieser Lauf ist deshalb ausdrücklich kein Vergleich bei ruhiger
NAS-Last. Er zeigt, dass auch das produktive Original-Image in der Testumgebung
denselben funktionalen Fehler erreichen kann; die Ursache der historischen
Jenkins-/Leroy-Ergebnisdifferenz ist damit nicht abschließend bewiesen. Ein Wechsel
auf 16 GiB wäre bei der aktuellen Docker-Desktop-Speichergrenze kein tragfähiger
Vergleich. Die Diagnose ersetzt weder die vollständige Release-Abnahme noch einen
Vergleich beider CI-Engines.
[A/B/A-Ergebnisse und Lastgrenzen](../test-results/nas-parity/followup/frozen-runtime-aba-0ad540dd5780-owned-builder/analysis.json),
[Originaldateien des tatsächlichen Workers](../test-results/nas-parity/followup/frozen-runtime-aba-0ad540dd5780-owned-builder/worker-original-test-content-proof.json).

Die lesende Quellanalyse findet einen konkreten Mechanismus zusätzlicher
UI-Leseanfragen: Jede erfolgreiche Ereignisabfrage erhöht die Verbindungsrevision.
Der Provider-Installationsstore verwendet diese Revision als Verbindungsschlüssel,
stoppt seinen Poller und startet sofort eine neue Abfrage. Dadurch wird sein
vorgesehenes Zwei-/60-Sekunden-Intervall umgangen. `stop()` verwirft auch die
Zusammenfassung laufender Abfragen; derselbe Callback invalidiert zusätzlich die
globale Zusammenfassung laufender IPC-Leseanfragen. Queue-Ereignisse lösen weitere
Queue-Leseanfragen aus. Alle Clients teilen dasselbe Credential-Ratenbudget.

Die erneute Auswertung der bereits vorhandenen separaten HTTP-Beobachtung findet
419 Provider-Statusabfragen bei 430 erfolgreichen Ereignisantworten. 387 dieser
Statusabfragen beginnen innerhalb von 100 ms nach einer Ereignisantwort desselben
Browser-Kontexts. Vor der ersten 429-Antwort enthält das dichteste erfasste Fenster
744 Anfragestarts in 5,431 Sekunden, darunter 147 Provider-Statusabfragen und nur
40 Prompt-Aufrufe. Ohne diese 147 Statusabfragen bleibt die rechnerische Belastung
des aufgezeichneten Verlaufs deutlich unter der ursprünglichen Burst-Reserve.
Das stützt den Mechanismus als Kandidaten; es ist keine ausgeführte Korrektur.
Die Aufzeichnung identifiziert keine einzelnen Tabs, enthält keine tatsächlichen
Server-Ankunftszeiten und kann Beobachteraufwand nicht ausschließen. Sie erklärt
deshalb noch nicht, weshalb bestimmte historische Läufe erfolgreich sind.
Für diese Analyse wurden keine Tests, Anwendungssourcen oder Limits verändert
und keine neuen Tests mit Beobachter gestartet.
[Quellen- und Anfragedatenanalyse](../test-results/nas-parity/followup/frozen-soak-http-0ad540dd5780-attempt-3/read-amplification-analysis.json).

Nach dem Ende der produktiven NAS-Builds ist die Kopie aller zwanzig Layer
einschließlich ihrer unkomprimierten Prüfsummen erfolgreich. Beim ersten Import
in die Test-VM beendet der Docker-Desktop-Kernel am 6. Oktober um 23:04:15 Uhr MESZ
QEMU durch einen globalen OOM. Das Kernelprotokoll enthält gleichzeitig einen
Rust-Kompilierprozess mit rund 4,9 GiB residentem Speicher und vollständig
belegten 4 GiB Swap. Das ist kein belegter Archivformatfehler und kein ausgeführter
Soak-Test. Die geprüften Image-Daten und der Importfehler bleiben erhalten;
eine zusätzlich vorbereitete klassische Docker-Archivdarstellung enthält genau
dieselben Layer. Der Wiederanlauf wartet auch auf inaktive externe Docker-Desktop-
Tests und Compiler. Das vorhandene VM-Limit und der Graphato-Quellstand werden
dadurch nicht verändert. Der neue Import-OOM erklärt nicht die älteren
Prompt-Ratenlimit-Abbrüche.
[Kernel- und Container-Nachweis](../test-results/nas-parity/followup/native-browser-observations/web-18/runtime-import-global-oom.json).

Der zusätzliche vollständige originale Leroy-Release-Lauf mit acht Ziel-CPUs
hat Web mit 20/21 bestandenen Gruppen beendet. Wieder scheitert ausschließlich
`browser-soak` am ursprünglichen `sendSessionPrompt`-Ratenlimit. Die zwei
erfolgreichen einzelnen Soak-Läufe reichen deshalb nicht als Beleg für die
gesamte Web-Abnahme. Die Qualitätssuite besteht alle acht Gruppen, 1.625
Rust-Tests bei 32 regulär ignorierten Tests sowie alle 195 Python-Tests. Die
vollständige Rust-Testliste stimmt mit dem ursprünglichen Vergleich überein.
Damit bestehen 28/29 originale Gruppen; die Release-Abnahme bleibt rot. Die
lokale Auswertung übersah zunächst ein bereits heruntergeladenes Archiv wegen
der Windows-Pfadlänge. Die Metadaten- und Prüfsummenprüfung behebt ausschließlich
diesen Berichtsfehler; kein Test wurde dafür neu gestartet.
[Vollständiger Leroy-Lauf](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/controlled-groups/full-release-leroy-cpu-eight-round-1/analysis.json).

Während dieses Laufs startet die produktive Jenkins-SCM-Erkennung unabhängig
Graphato-CI #27 am 6. Oktober um 21:15:05 Uhr MESZ. Der originale Web-Test endet
bereits um 20:32:48 Uhr MESZ; dieser Produktionsbuild erklärt deshalb dessen
Soak-Fehler nicht. Der Qualitätstest endet erst um 21:20:30 Uhr MESZ und
überschneidet sich mit #27. Der Testprozess löst keinen produktiven Build aus.
Der native Jenkins-Cause-Nachweis ist gespeichert. Die nachträgliche Einordnung
ersetzt keine vorab bewachte Messung; identische Hintergrundlast zwischen Engines
wird ausdrücklich nicht behauptet.
[Produktionsaktivität](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/controlled-groups/full-release-leroy-cpu-eight-round-1/production-activity-audit.json).
[Zeitliche Einordnung](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/controlled-groups/full-release-leroy-cpu-eight-round-1/historical-production-load-qualification.json).

Die lesende Beobachtung um 22:05 Uhr MESZ bestätigt CI #27 als erfolgreich
beendet. Release #19 und Web #20 laufen danach für den neuen Produktionscommit
`25a5e84083036641c33f1cc3599ca924f7e715e6`; zusätzliche NAS-Messläufe bleiben
zurückgestellt. Der bereits fehlgeschlagene Qualitätslauf #18 gehört dagegen
zu CI #26 und Commit `eacd1c35900eb1fdab9fe4420d1ccfd094f105f2`. Dort scheitert
`frontend-and-deployment`, während die sieben anderen Gruppen bestehen.
Dieser Produktionsnachweis ersetzt keinen Vergleich des eingefrorenen `0ad540dd5780`.
Die Ursache dieses älteren Produktionsfehlers ist damit nicht diagnostiziert.
[Produktive Build-Zuordnung](../test-results/nas-parity/followup/cutover-preparation/native-builds-observation-20261006T200544Z.json),
[Qualitätsquittung #18](../test-results/nas-parity/followup/cutover-preparation/native-quality-18-observation-20261006T200502Z.json).

Die getrennte Testtreiber-Diagnose besteht mit vier Ziel-CPUs, vier Tabs, 120
eindeutigen Prompts und 309,142 Sekunden Laufzeit. Zwei native Ratenlimit-Antworten
werden mit begrenztem, geprüftem `Retry-After` behandelt. 16 von 621 UI-Anfragen
sind gedrosselt; die Original-Erholungsprüfung besteht. Ausschließlich zwei
Testtreiber-Dateien liegen in einem zusätzlichen Worker-Layer, bei identischer
Image-Konfiguration und unverändertem Runtime-Image, Quellarchiv und Serverlimit.
Der eingefrorene Checkout bleibt unverändert; Quittungen liegen in einem eigenen
Verzeichnis. Dies prüft einen separaten Vorschlag, keine vollständige originale
Release-Abnahme und keinen erfolgreichen Jenkins-/Leroy-Vergleich. Die Diagnose
läuft von 21:30:39 bis 21:40:00 Uhr MESZ bei aktivem Produktionsbuild #27.
Ihr funktionaler Erfolg belegt daher keine vergleichbaren Lastbedingungen.
[Vorschlag und Geltungsbereich](upstream-patches/graphato-soak-rate-handling-proposal.md).

Zusätzliche Diagnose vom 6. Oktober: Der neue vollständige originale Rust-Lauf
unter Leroy besteht mit 1.625 erfolgreichen und 32 regulär ignorierten Tests.
Die vollständige Testliste stimmt mit den ursprünglichen Jenkins- und
Leroy-Läufen überein; keine Filterung oder Wiederverwendung. Jenkins #9 besteht
denselben vollständigen Lauf aus demselben Ausgangssnapshot ebenfalls mit
1.625 erfolgreichen und 32 ignorierten Tests. Die Retry-Assertion besteht unter
beiden Engines. Diese einzelne Qualitätsgruppe ersetzt keine
vollständige Release-Abnahme und überschreibt den ersten Fehler nicht.
[Vollständiger Rust-Vergleich](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/controlled-groups/quality-server-test-round-1/full-rust-pair-inventory-proof.json).

Die Quellanalyse grenzt die Retry-Assertion ein: Sie erzwingt die zeitliche
Überlappung zweier Transaktionen, injiziert aber keinen Serialisierungsfehler.
PostgreSQL garantiert für erfolgreich abgeschlossene serialisierbare
Transaktionen eine mögliche serielle Reihenfolge; Überlappung allein erzwingt
keinen Retry. Daraus folgt die Hypothese einer vom Konflikt- und Abfrageplan
abhängigen Testannahme. Der konkrete Abfrageplan während des ursprünglichen
Fehlers ist nicht aufgezeichnet und diese Ursache deshalb nicht bewiesen.
[PostgreSQL-Dokumentation](https://www.postgresql.org/docs/18/transaction-iso.html#XACT-SERIALIZABLE).

Die getrennte Browser-Soak-Messung erfasst 2.202 API-Anfragen und sieben
HTTP-429-Antworten, darunter den fehlgeschlagenen `sendSessionPrompt`-Aufruf.
Die erste Ablehnung folgt auf 744 gestartete Anfragen in 5,431 Sekunden. Mit
den unveränderten Quellcode-Vorgaben von 100 Anfragen/Sekunde und 200 Reserve
entspricht dies bereits mehr als dem verfügbaren Budget. Gemessen sind
Client-Starts, keine Server-Ankunftszeiten; Anfragen der übergeordneten Fixture
sind nicht erfasst. Die Daten stützen damit eine Überlastung des gemeinsamen
Anfragebudgets durch Prompt-Aufrufe, Ereignisabfragen und UI-Aktualisierungen.
Der genaue Unterschied zum erfolgreichen Produktionslauf bleibt offen.
[HTTP-Messung](../test-results/nas-parity/followup/frozen-soak-http-0ad540dd5780-attempt-3/http-analysis.json),
[Anfragedichte](../test-results/nas-parity/followup/frozen-soak-http-0ad540dd5780-attempt-3/request-density-analysis.json).

Die ersten beiden Diagnosehelfer-Versuche scheitern vor einem Browserstart:
Lesen einer fehlenden Quittung und Prüfung optionaler Docker-Image-Felder.
Beide Versuche bleiben erhalten. Der dritte Versuch besteht als Messung,
seine Soak-Prüfung scheitert. Der Beobachter verändert das Worker-Image und hat
Messaufwand; dieser Lauf zählt ausschließlich als Diagnose. Anschließend laufen
originale Gruppenläufe mit vier beziehungsweise acht CPUs auf dem isolierten
Anwendungsziel. Vier CPUs: Jenkins #9 und Leroy scheitern beide am selben
`sendSessionPrompt`-Ratenlimit. Acht CPUs: Leroy besteht vier Tabs, 120 Prompts
und 308,779 Sekunden Soak. Sechs gedrosselte Leseanfragen sind im Originaltest
zulässig; alle Prompts werden verarbeitet und die abschließende Erholung
besteht. Jenkins #10 scheitert am ursprünglichen Prompt-Ratenlimit. Der zweite
Vergleich kehrt die Startreihenfolge um: Jenkins #11 scheitert ebenfalls, Leroy
besteht erneut 120 Prompts, vier Tabs und 308,926 Sekunden Soak. Auch hier sind
sechs gedrosselte Leseanfragen zulässig und die abschließende Erholung besteht.
Die Startreihenfolge erklärt den beobachteten Unterschied damit nicht; die
konkrete Ursache ist weiterhin offen. Acht CPUs allein garantieren keinen
erfolgreichen Lauf beider Engines. Anwendung, Ratenlimits und Testauswahl bleiben
unverändert. Controller und CI-Worker bleiben auf dem NAS.
[Zweiter Vergleich](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/controlled-groups/web-soak-cpu-eight-round-2/analysis.json).

Die erneute lesende Prüfung bestätigt unveränderte native Jenkins-Konfigurationen
für alle 13 Pipelines. Elf Credential-IDs und ihre Typen lassen sich zehn
Leroy-Secret-Gruppen zuordnen. Die Testprofile haben alle benötigten Dateien,
verwenden aber weiterhin Testzugänge. Credential-Inhalte und produktive
Berechtigungen sind damit nicht validiert. Produktionsmaterial wurde nicht
kopiert, kein Trigger umgestellt. Ein zusätzlicher Verbindungsversuch bestätigt,
dass der Test-Daemon die produktiven NAS-Endpunkte durch seine bestehende
Isolationsregel blockiert. Die Produktionskonfiguration benötigt passende
Netzrouten, denselben lesenden Zugriff auf `/srv/music` und `/srv/yt-music`
sowie für den Gitea-Administrationsjob Zugriff auf den nativen Docker-Daemon.
Dieser Job muss den bestehenden Gitea-Container adressieren können.
Registry-Adressen mit `127.0.0.1:5005` benötigen den richtigen Ausführungskontext.
[Zuordnung](../test-results/nas-parity/followup/cutover-preparation/production-credential-readiness.json).
[Betriebsvoraussetzungen](../test-results/nas-parity/followup/cutover-preparation/production-execution-requirements.json).

Das deaktivierte [Produktionsbundle](../infra/nas/production/README.md) ist für
zwölf Pipelines und vier Profile vorbereitet. Alle vier Profile bestehen die
zusätzliche lesende Prüfung im nativen NAS-Docker-Kontext. Die festgeschriebenen
Job-Images sind anhand von Archiv-, Konfigurations- und Layer-Prüfsummen
abgeglichen; OCI-Index- und klassische Image-Digests sind ausdrücklich zugeordnet.
Gitea- und Paperless-Vorgaben stammen aus den mit der Produktion abgeglichenen
Inline-Skripten. Der Smartphone-SSH-Dienst wurde über das autorisierte USB-Gerät
gestartet und sein öffentlicher Host-Schlüssel dort bestätigt. Tatsächliche
produktive Authentifizierung, Schreibrechte, Credential-Bereitstellung und
Aktivierung bleiben offen. Diese Kontextprüfung ersetzt keine Geschäftsaufgabe
oder Graphato-Abnahme.
[Native Profilprüfung](../test-results/nas-parity/followup/cutover-preparation/native-context-profile-preflight-attempt-3.json).

Der neue Vergleich des ausdrücklich eingefrorenen Graphato-Masters
`0ad540dd578033d45e4d0c25d89fbe57b32102a4` hat den frischen Zielvergleich abgeschlossen.
Jenkins-Bootstrap #8 und CI #6 sowie Leroy-Bootstrap #104 und CI #105 sind erfolgreich.
Beide Auslieferungen haben vier gesunde Dienste und geprüfte Desktop-Pakete.
Release, Web und Qualität scheitern unter beiden Engines vor dem ersten Prüffall
am gleichen ursprünglichen Markerfehler. Der zusätzliche vollständige Gruppenvergleich
auf einem identischen privaten Host-Snapshot ist ebenfalls abgeschlossen. Die Vorbereitungsdaten
beider Gäste stimmen überein. Vier Jenkinsfiles und `scripts/ci.py` sind
gegenüber der bisherigen Basis unverändert. Anwendungspatches werden nicht
angewendet. Die folgende Tabelle enthält weiterhin die abgeschlossenen älteren
Nachweise. Quelle: [Master-Nachweis](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/frozen-master.json).

Gesonderte lesende Produktionsbeobachtung: Native Jenkins-Quittungen für genau
diesen Commit bestätigen Web #18 mit 21/21 und Qualität #17 mit 8/8 bestandenen
Gruppen sowie vollständigem Cleanup. Der isolierte Engine-Vergleich bleibt ein
eigener Nachweis. [Produktionsquittungen](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/production-evidence-observation-20261006T123824Z.json).

Der neue isolierte Web-Erstversuch Jenkins #8 hat inzwischen alle 21 Gruppen
ausgeführt, davon 20 erfolgreich. `browser-soak` bricht bei `sendSessionPrompt`
mit der Credential-Ratenbegrenzung ab. Der ursprüngliche Browser-Testtreiber
wirft bei dieser Antwort sofort einen Fehler. Der genaue Unterschied zum
erfolgreichen Produktionslauf ist noch nicht bewiesen. Jenkins-Qualität #8
besteht alle acht Gruppen, 1.625 Rust-Tests (32 ignoriert) und sechs Python-Testläufe
mit insgesamt 195 bestandenen Tests. Leroy-Web #110 hat ebenfalls alle 21 Gruppen
ohne Wiederverwendung ausgeführt: 20 bestehen, `browser-soak` endet mit exakt
derselben Fehlermeldung. Cleanup ist vollständig. Leroy-Qualität #111 führt alle acht Gruppen aus und
beendet alle 1.657 Rust-Testereignisse: 1.624 bestanden, 32 ignoriert, ein Fehler
in der Retry-Anzahl-Assertion der überlappenden Merge-Transaktionen. Alle 195
Python-Tests bestehen. Jenkins besteht diese Assertion im vollständigen Lauf.
Das ist eine ungeklärte Ausführungsabweichung; Qualität bleibt unter Leroy rot.
[Direkter Fehlernachweis](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/scenarios/root-private-existing-host/rust-retry-coverage-failure-analysis.json).
Der betroffene Rust-Test besteht in vier zusätzlichen Einzelproben mit jeweils
frischer PostgreSQL-Fixture, zwei Rust-Testthreads und unveränderten Limits.
Diese gefilterte Diagnose ersetzt den vollständigen fehlgeschlagenen Lauf nicht
und beweist noch keine Ursache der Abweichung. Der Diagnosehelfer hatte zuerst
einen Startfehler durch unzulässige Adapterargumente; dieser Versuch ist erhalten.
[Einzelproben](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/scenarios/root-private-existing-host/rust-retry-coverage-probe.json).

[Leroy-Fehlernachweis](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/scenarios/root-private-existing-host/leroy-browser-soak-failure-analysis.json).
[Fehleranalyse](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/scenarios/root-private-existing-host/browser-soak-failure-analysis.json).

Die abschließende CI-Betriebsabnahme mit diesem Stand besteht: sieben
festgeschriebene Images sind in leeren Daemons mit passendem Speichermodell und
identischen IDs/Layern wiederhergestellt. Der vollständige eigene NAS-Teststack
ist neu gestartet; danach bestehen echte Jobs in allen vier Worker-Profilen.
Die Rücksicherung bestätigt alle Datenbankzeilen und Prüfsummen, 537 Artefakte,
251 Logs und die verschlüsselte Konfiguration; der wiederhergestellte Controller
ist bereit. 21 gezielte Tests sichern die Abnahmehelfer ab. Der Quellstand ist
sauber und unverändert. Diese Infrastrukturabnahme ersetzt die roten
Anwendungsprüfungen nicht.
[Betriebsnachweis](../test-results/nas-parity/followup/candidates/graphato/0ad540dd578033d45e4d0c25d89fbe57b32102a4/final-operations-acceptance.json).

Stand: 6. Oktober 2026. **NAS-Teststack läuft; die ursprünglichen Vergleichsläufe aller 13 Pipelines sind ausgewertet.
Im aktuellen Umfang von zwölf Pipelines sind alle eingefrorenen Vergleichsstände ausgewertet.
Die Produktionsfreigabe bleibt wegen fehlgeschlagener Originalprüfungen, belegter
Verhaltensunterschiede und der Abweichung im eingefrorenen Master offen.**
Die bisherige erfolgreiche isolierte Abnahme verwendet für Antares und Graphato
separate Anwendungskorrekturen. Sie belegt keine identische Ausführung der
unveränderten Quellen unter Jenkins und Leroy. Diese Patches bleiben bei diesem
Originalvergleich ausgeschlossen. Die anschließend einzeln belegten Fehler werden in
separaten Kandidaten geprüft; deren Nachweise stehen im Abschnitt zur Nachprüfung.

Aktuelle Nachprüfung:

| Bereich | Ergebnis |
| --- | --- |
| NAS-Betrieb | Neustarts, Warteschlange, Abbruch, parallele Worker sowie Sicherung/Wiederherstellung erfolgreich geprüft. |
| Home-Lab | Tatsächlicher Build und Push unter Jenkins und Leroy erfolgreich; Inhalte und Laufzeitkonfigurationen verglichen. |
| Graphato-Original `ed21c2e6346a` | Bootstrap und CI unter beiden Engines erfolgreich. Auf frischen Zielen scheitern die Prüfläufe am gleichen ursprünglichen Markerfehler. Das zusätzliche Szenario mit identischem privaten Host-Snapshot ist vollständig verglichen: Jenkins #6 und Leroy #99/#100/#101 führen 21 Web- und acht Qualitätsgruppen aus, jeweils 20/21 und 7/8 erfolgreich. Gleiche Fehlersignaturen und identische 1.609 Rust-Testereignisse einschließlich 30 regulärer Auslassungen. Leroy beendet den rund 61-minütigen Lauf ohne Lease-Abbruch; fehlgeschlagene Prüfungen bleiben rot. |
| Graphato `78e92e09fa5f` | Frische Jenkins-Wiederholung #3 mit derselben VM-Netzpolicy wie Leroy ausgewertet: Bootstrap, CI und alle acht Qualitätsgruppen bestehen. 20/21 Webgruppen bestehen; `browser-soak` scheitert an HTTP 429 im Testtreiber. Release-Abnahme entsprechend fehlgeschlagen. Die früheren erfolgreichen Jenkins-/Leroy-Nachweise bleiben archiviert. |
| Graphato `9968c226f943` | Separater Kandidat für typisierte Ratenbegrenzung im Browser-Testtreiber; 38 gezielte Prüfungen bestehen. Der vollständige Vergleich besteht unter beiden Engines auf jeweils frischer VM: Jenkins Bootstrap #5 und CI/Web/Qualität/Release #4; Leroy Bootstrap #76, CI #77, Release #78, Web #79 und Qualität #80. Jeweils 21/21 Webgruppen, 8/8 Qualitätsgruppen, 1.527 Rust-Tests und 29 ursprüngliche Auslassungen; identischer normalisierter Rust-Ergebnishash. Vollständiges Cleanup, keine wiederverwendeten Prüfergebnisse, vier gesunde Dienste und verifizierte Release-Quittungen. 14 Quell-/Policy-Dateien und VM-Netzpolicy stimmen überein; beide Windows-Pakete sind geprüft. Der frühere Tunnel-Fehlversuch bleibt erhalten. |
| Antares `9f05b7f1aa56` | NAS-Jenkins #9 und Leroy #65 mit zwei CPUs: jeweils 635 Unit-Tests, 102 Integrationstests und Build erfolgreich; Browserfehler und Ablauf des unveränderten 30-Minuten-Limits. Vollständige NAS-Abnahme offen. |
| Antares `8607cfd438c7` | Separater, durch Regression belegter ARIA-Fix. Lokal vollständige Browsermatrix erfolgreich: 26 bestanden, drei vorgesehene Auslassungen. NAS-Jenkins #11 besteht 636 Unit- und 102 Integrationstests sowie den Build, endet nach Browserfehlern am Pipeline-Limit. Leroy #72 besteht ebenfalls 636/102 Tests und Build, endet nach dem Zeitlimit beim Sichern der Artefakte mit Lease-Verlust. Vollständige NAS-Abnahme offen. |
| Antares `58da3ef5d112` | Getrennte Korrektur der Arena-Testaufnahme und des Bestätigungsdialogs, mit Regression vor/nach der Änderung. Vollständiger Vergleich mit NAS-Controller und separatem Linux-Testpool erfolgreich: Jenkins #1 und Leroy #88 bestehen jeweils 637 Unit-, 102 Integrations- und 26 Browsertests sowie Coverage und Produktionsbuild; drei ursprüngliche Browserauslassungen, keine Wiederholung. Jenkinsfile und Abhängigkeiten unverändert, gemeinsamer Jobrahmen 4 GiB/sechs CPUs. Die reine NAS-Ausführung bleibt nach Speicher-/I/O-Stalls fehlgeschlagen. |
| Leroy-UI | 227 Ansichten auf Desktop/Mobilgeräten automatisiert und visuell geprüft: 71 ursprüngliche, zwölf Live-, 16 Graphato-, sechs Graphfokus-, sechs Antares-, sechs Log-Test-, sechs korrigierte Unterbrechungs- und sechs Abbruch-/Bereinigungsansichten sowie 16 Ansichten des erfolgreichen Graphato-Kandidaten, vier Linux-Worker-, sechs erfolgreiche Antares-Ergebnis- und acht NAS-Scope-Ansichten. Hinzu kommen vier Ansichten von Graphato #90, 16 der unveränderten frischen Ausführung, zwölf des vollständigen Original-Gruppenvergleichs und vier der korrigierten Kindlauf-Fehleranzeige. 28 weitere Ansichten zeigen den eingefrorenen Master auf frischem und vorbereitetem Ziel. Insgesamt 161 Artefaktdownloads sind gegen SHA-256 geprüft. Historische Fehleransichten behalten ihre tatsächlichen Zustände. |

Die folgenden Originalergebnisse bleiben als Baseline erhalten. Spätere
Nachprüfungen ersetzen diese historischen Fehlernachweise nicht.

### Aktueller Abnahmeumfang: Betrieb auf dem NAS

Der Nutzer hat am 5. Oktober festgelegt: Controller und CI-Worker bleiben auf
dem NAS wie beim bestehenden Jenkins. Ein separater dauerhafter Linux-Worker
ist nicht vorgesehen. Antares wird als Artefakt aus der NAS-Abnahme ausgenommen,
wenn es auf dieser Hardware nicht gebaut werden kann. Damit umfasst diese
Abnahme zwölf Pipelines; Antares bleibt migriert, deaktiviert und mit allen
bisherigen Fehler- und Erfolgsnachweisen erhalten. Dies ist eine ausdrücklich
akzeptierte Ausnahme, kein erfolgreicher Antares-NAS-Build.

Der optionale Docker-Desktop-Linux-Testpool und sein Worker sind gestoppt,
automatischer Wiederanlauf ist deaktiviert. Seine Volumes und Vergleichsnachweise
bleiben erhalten. Die begonnene zusätzliche Pool-Sicherungsprüfung liefert keinen
abgeschlossenen Betriebsnachweis und ist für das gewählte NAS-Setup keine Voraussetzung.
Die bereits geprüften Neustart-/Sicherungsnachweise des NAS-Teststacks bleiben gültig.
Isolierte Linux-Anwendungsziele ersetzen weiterhin die vorhandenen SSH-Deploy-Ziele;
sie sind keine zusätzlichen produktiven CI-Worker.

Die lesende Quellenprüfung vom 5. Oktober bestätigt Antares-GitHub `master` auf `ab245279a2c5`
und Graphato-Gitea `master` sowie Jenkins CI #18 auf `ed21c2e6346a`.
Home-Lab `9fb528a1bb4b` und Nikicas-Hub `f7fcfcf78e8f` sind unverändert.
Alle fünf Inline-Jenkins-Skripte stimmen mit der Migration überein. Graphatos vier
Jenkinsfiles sind zwischen ursprünglicher Basis, geprüftem Kandidaten und aktuellem
Produktionsstand bytegleich; die ausführenden Anwendungsskripte können sich trotzdem
unterscheiden. Der aktuelle Graphato-Stand wird deshalb separat und ohne
Anwendungspatches im isolierten NAS-Stack bereitgestellt. Historische Vergleiche
werden nicht durch neue Quellstände überschrieben.

Die Patchprüfung korrigiert eine zu pauschale frühere Formulierung: Antares'
Kandidat enthält erhöhte Unit-/Integrationstest-Fristen und Änderungen an
Testquellen. Unverändert sind der Jenkinsfile und die Pipeline-/Browserkonfiguration.
Der Erfolg belegt denselben eingefrorenen Kandidaten unter beiden Engines;
er belegt nicht unveränderte Assertions und Fristen gegenüber dem Originalprojekt.
Die Aussage in früheren Speicher-Policy-Belegen bezieht sich ausschließlich auf
denselben Kandidaten vor/nach der Speicherregel. Die drei Graphato-Patches lassen
sich auf den aktuellen Quellstand anwenden, sind dort aber nicht enthalten.
Das beweist weder ihre Erforderlichkeit für Leroy noch eine Behebung der aktuellen
Produktionsfehler bei `browser-merge` und `frontend-and-deployment`.

Quellen, einzelne Patchkategorien, der Abnahmeumfang und die Pipeline-Matrix stehen
unter `test-results/nas-parity/followup/production-source-review/`.
Die aktuelle Übersicht über die zwölf einbezogenen Pipelines steht in
[nas-acceptance.md](nas-acceptance.md).

### Testaufbau für den unveränderten Produktionsstand

Graphato `ed21c2e6346a` ist unverändert in der eigenen NAS-Git-Fixture bereitgestellt.
Der frühere Kandidat bleibt als Tag und Bundle erhalten; Produktions-Gitea wurde
nicht verändert. Jenkins-Bootstrap #6 scheiterte, als `apt-daily-upgrade` im frisch
restaurierten Testgast gleichzeitig Systemdienste neu startete. Dieser Fehler und
das Journal bleiben erhalten. Auf dem nächsten frischen Gast sind ausschließlich
die automatischen Hintergrundupdates deaktiviert; Jenkins-Bootstrap #7 besteht.
Dieselbe Gastvorbereitung gilt für Leroy, ohne Änderungen am Anwendungscode.

Der NAS-Test-Daemon war nach der Antares-Diagnose auf insgesamt 3 GiB begrenzt.
Diese Grenze umfasst auch Test-Jenkins und Gitea; Graphatos unveränderter Builder
allein verlangt bereits 4 GiB. Jenkins CI #5 erreichte die Eltern-Grenze und
verursachte starke Speicher-/I/O-Wartezeiten. Leroys Anmeldung lief währenddessen
in einen 45-Sekunden-Timeout. Das ist ein belegter Testaufbaufehler, keine Aussage,
dass Graphato grundsätzlich nicht auf dem NAS gebaut werden kann.

Die Grenze des eigenen Test-Daemons wurde am 5. Oktober um 20:27 UTC auf 4,5 GiB
korrigiert, zunächst ohne zusätzlichen Swap oder Neustart. Laufzeitgrenze, gespeicherte
Docker-Konfiguration und Compose-Datei stimmen anschließend überein. Zwei unter
Last zeitlich abgebrochene Docker-Update-Anfragen bleiben als Fehler dokumentiert;
die tatsächlich gespeicherten Grenzen wurden danach lesend bestätigt.
Produktionscontainer und ihre Limits wurden nicht geändert. Jenkins CI #5 startete
unter der früheren Grenze; identische Startbedingungen oder ein Leistungsvergleich
werden deshalb nicht behauptet. Leroy erhält die korrigierte gemeinsame Grenze.
Die Weboberfläche wurde unter Jenkins gebaut, der weitere Lauf bleibt in seinen
tatsächlichen Ergebnissen erhalten.

Die lesende Prüfung des produktiven Builders bestätigt 4 GiB RAM, insgesamt
6 GiB RAM+Swap und zwei CPUs. Am 5. Oktober um 21:05 UTC wurde deshalb im eigenen
Test-Daemon der dafür notwendige Spielraum von 2 GiB Swap freigegeben: 4,5 GiB RAM
und insgesamt 6,5 GiB RAM+Swap. Die ursprünglichen Builder-Grenzen bleiben
unverändert. Laufzeit, Docker-Konfiguration und Compose sind übereinstimmend
geprüft; es erfolgte kein Neustart und keine Produktionsänderung. Beide Eingriffe
liegen nach dem Start von Jenkins CI #5. Dieser Versuch bleibt daher ausdrücklich
kein Leistungsvergleich und kein Nachweis identischer Startbedingungen.
`original-builder-swap-alignment.json` enthält die neue Grenze;
`parent-budget-correction.json` bleibt der historische Beleg des ersten Eingriffs.

Um 21:18 UTC zeigte die cgroup-Messung, dass Test-Jenkins, Test-Gitea und die
Docker-Hilfsdienste denselben Swap-Spielraum belegen. Die Eltern-Grenze war voll,
während der ursprüngliche Builder seine eigenen 2 GiB noch nicht nutzen konnte.
Der Test-Daemon erhält deshalb zusätzlich 1 GiB Reserve für diese Hilfsdienste:
4,5 GiB RAM und insgesamt 7,5 GiB RAM+Swap. Vor dem Eingriff waren über 3 GiB
Host-Swap frei. Die ursprüngliche Builder-Grenze bleibt unverändert bei 4+2 GiB;
Produktion und Dienste wurden nicht neu gestartet. Laufzeit, Docker-Konfiguration
und Compose sind geprüft. Die aktuelle Grenze steht in `fixture-swap-reserve.json`;
die früheren Grenzkorrekturen bleiben historische Belege.

Der tatsächliche Compose-Parser wurde zusätzlich mit `config --format json`
geprüft: RAM `4831838208`, RAM+Swap `8053063680`, sechs CPUs. Diese Werte stimmen
mit der gespeicherten Docker-Konfiguration und der laufenden cgroup überein.
Es wurden keine Dienste neu erstellt. Die unterschiedlichen JSON-Datentypen
sind normalisiert, die ursprünglichen Werte im Beleg erhalten
(`compose-budget-validation.json`).

Die archivierten Produktionsprüfungen #11 für denselben Commit sind lesend
gesichert und gegen SHA-256 geprüft. `browser-merge` erhält `local` statt des
erwarteten `pendingPush`; die zugrunde liegende Geschäftslogik ist damit noch
nicht abschließend diagnostiziert. Der archivierte Seitentext zeigt außerdem
einen Git-Fehler beim Remote-Zugriff, Kategorie `unclassified`. Im ursprünglichen
Quellcode kann `prepare_push` Fehler vor der späteren `pendingPush`-Aktualisierung
weitergeben. Diese Quellcode-Inferenz ist kein bestätigter Ursachennachweis;
Archiv-, Seitentext- und Quelldatei-Hashes stehen in `browser-merge-observation.json`.
Bei `frontend-and-deployment` scheitert genau
der ursprüngliche Python-Test
`ReleaseBoundary.test_current_production_compose_passes_release_policy`:
Die unverändert gepinnte Docker-CLI enthält Compose 2.40.3 und lässt im
gerenderten JSON `create_host_path: false` weg. Graphatos unveränderter Validator
verlangt den expliziten Wert `False`. Der gleiche Test besteht mit der
Compose-Version 5.5.1 des Hostziels, die diesen Wert erhält. Die Reproduktion
verwendet die ursprüngliche CLI per Image-Digest, ohne Docker-Socket, Netzwerk
oder Anwendungsdeployment; der Prüfcontainer ist entfernt. Sie belegt einen
Fehler im ursprünglichen Prüfpfad, keine vollständige Pipeline-Abnahme und
keine für Leroy erforderliche Anwendungskorrektur. Einzelne Belege stehen unter
`followup/production-source-review/failed-groups/`.

Der Original-Qualitätslauf enthält 1.579 bestandene Rust-Tests und 30 ursprüngliche
Auslassungen, insgesamt 1.609 terminale Testereignisse. Der normalisierte
Ergebnishash ist gesichert. Die ursprünglichen Python-Deploymenttests führen
146 Tests mit genau einem Fehler aus. Diese Zahlen stammen aus den tatsächlichen
Produktionsarchiven; die 1.527/29 des früheren gepatchten Kandidaten gelten nicht
für diesen Stand (`original-quality-test-evidence.json`).

Jenkins CI #5 baut und liefert den unveränderten Produktionsstand erfolgreich
aus. Auf dem frischen Ziel endet die Release-Abnahme anschließend vor den
Prüfgruppen: Das Steuerverzeichnis gehört root, hat aber Modus `0755`, während
der ursprüngliche Markerprüfer `0700` verlangt. Die gesicherten Jenkins-Metadaten
wurden mit dem bytegleichen Originalprüfer in einem temporären Linux-Verzeichnis
reproduziert; das war keine nachträgliche Laufzeitprobe auf dem inzwischen
restaurierten Jenkins-Ziel. Der ursprüngliche Fehler bleibt getrennt von einem
zusätzlichen Szenario mit bereits privatem Steuerverzeichnis.

Leroy #90 verliert während des Serverbuilds seine Lease. Controller, Runner und
PostgreSQL bleiben dabei aktiv, ohne Neustart oder neuen OOM-Nachweis. Der genaue
Transport-/Stillstandsgrund ist für diesen Versuch nicht belegt. Lauf, Logs und
Quittungen bleiben unter `attempts/leroy-90-interrupted/` erhalten; die vier
zugehörigen UI-Ansichten zeigen den tatsächlichen unterbrochenen Status.

Der NAS-Testworker enthält nun typisierte Lease-Diagnosen ohne Exception-Inhalte
und unterstützt eine getrennte RAM+Swap-Grenze für den Jobprozess. Für Graphatos
kleinen Steuerprozess sind 2 GiB RAM und kein Swap konfiguriert; der ursprüngliche
BuildKit-Builder behält 4 GiB RAM, 2 GiB Swap und zwei CPUs. Controller,
PostgreSQL, Anwendungscode und das Lease-Limit von 90 Sekunden sind unverändert.
96 Prüfungen gegen echtes PostgreSQL bestehen; drei Testimages sind anhand ihrer
Quellhashes überprüft und im eigenen NAS-Stack aktualisiert.

Die Wiederholung #91 besteht mit denselben unveränderten Quellen auf dem frischen
Ziel vollständig: zehn CI-Schritte, beide Builds, Deployment, Veröffentlichung
und Cleanup. Die 471 erfassten erfolgreichen Heartbeats haben einen größten
Abstand von 17,7 Sekunden. Vier kurze ReadTimeouts wurden diagnostiziert und
überstanden; es wird weiterhin keine bewiesene Ursache des früheren Abbruchs
behauptet (`control-residency-workload.json`). Beide Windows-Pakete sind gegen
Metadaten, SHA-256, ZIP-CRC und aktuelle Veröffentlichung geprüft. Quell-/Policy-
Dateien und Dienstkonfigurationen stimmen überein; vier Dienste sind gesund.

Die frischen Web-/Qualitäts- und Release-Läufe scheitern unter beiden Engines
am gleichen ursprünglichen Markerfehler, ohne ausgeführte Prüfgruppen. 16 neue
Desktop-/Mobilansichten wurden automatisiert und einzeln visuell geprüft; vier
Artefaktdownloads sind verifiziert. Die damaligen 183 geprüften NAS-Ansichten zeigen
die erfolgreichen CI-Schritte und fehlgeschlagenen Kindläufe getrennt. Ein
Restpunkt im aggregierten Fehlerbanner dieser archivierten Release-Läufe sind leere
Web-/Qualitätsfragmente; die Schrittansicht nennt den Kindlauf-Fehler und verlinkt
den betreffenden Lauf. Die unten belegte unabhängige Worker-Korrektur behebt das
für neue Läufe; gespeicherte historische Laufgründe werden nicht umgeschrieben.

Der zusätzliche vollständige Gruppenvergleich ist gegen denselben eingefrorenen
Anwendungsstand und denselben sauber gestoppten VM-Snapshot mit privatem
Steuerverzeichnis abgeschlossen. Vollständige Prüfquittungen, konkrete
Fehlersignaturen und einzelne Rust-Testereignisse sind verglichen; Anwendungspatches und
wiederverwendete Prüfergebnisse sind ausgeschlossen. Der gesonderte Fehler der
frischen Installation wird dadurch nicht überschrieben.

Jenkins #6 hat diesen zusätzlichen Gruppenvergleich vollständig beendet: Web
20/21, Qualität 7/8, Release-Abnahme fehlgeschlagen. Alle 1.609 Rust-Testereignisse
und der normalisierte Ergebnishash stimmen mit dem Produktionsarchiv überein;
die ursprünglichen Python-Deploymenttests führen 146 Tests mit einem Fehler aus.
Cleanup ist bestätigt, keine Teilnachweise wurden wiederverwendet.

Leroys erster Versuch #95 beendet die Websuite mit demselben Ergebnis, bricht
aber den Qualitätsteil und den Elternlauf wegen fehlgeschlagener Lease-Bestätigung
(`ReadTimeout`) ab. Dieser Versuch ist keine vollständige Abnahme. Seine
56 Nachweisdateien sind hashgeprüft unter
`scenarios/root-private-existing-host/attempts/leroy-95-cancelled/` erhalten.
Controller, PostgreSQL und Runner hatten nach dem Abbruch zusammen rund 143 MiB
im Swap. Sie laufen nun mit unveränderten Images ohne Swap und mit RAM-Reservierungen
von 128/128/64 MiB; die bisherigen RAM-Obergrenzen bleiben 256/256/192 MiB.
Builder und Test-Daemon bleiben unverändert, ebenso die 90-Sekunden-Server-Lease
und die konservative 45-Sekunden-Grenze im Worker.
Ein tatsächlicher vierminütiger NAS-Job besteht anschließend, mit 54 erfolgreichen
API-Abfragen und maximal 0,28 Sekunden Antwortzeit. Das belegt den kurzen
Steuerpfad. Die anschließende vollständige Graphato-Wiederholung #99/#100/#101
beendet alle Gruppen samt Cleanup ohne Unterbrechung: Web 20/21, Qualität 7/8,
identische ursprüngliche Fehlersignaturen und identischer normalisierter
Rust-Ergebnishash `49e30e2263d4…`. 19 Speicherproben während und nach diesem Lauf
zeigen keinen Swap, keine OOM-Ereignisse und keine Neustarts der Steuerdienste.
Sieben überlappende Heartbeat-Messfenster enthalten ausschließlich erfolgreiche
Antworten; die größte beobachtete Lücke beträgt 11,94 Sekunden. Der Lauf bleibt
wegen der Anwendungsprüfungen fehlgeschlagen, keine erfolgreiche Release-Abnahme
wird daraus abgeleitet.
Eine abschließende Ursache des vorherigen Abbruchs wird nicht behauptet.
Belege: `control-plane-residency-deployment.json` und
`control-plane-residency-workload/report.json` unter `followup/`.

Produktions-Jenkins hat während des Vergleichs selbst neue Graphato-Builds #19/#20
per SCM-Trigger gestartet, mit `82f52a6079b6` beziehungsweise `b88336f48953`.
Die Produktionszähler blieben deshalb nicht unverändert. Diese lesend gesicherte
Aktivität ist vom Eingriff in die eigenen Testdienste getrennt; gleiche
Hintergrundlast oder ein Leistungsvergleich werden nicht behauptet. Der Vergleich
ist weiterhin auf den unveränderten Commit `ed21c2e6346a` eingefroren und belegt
keine Abnahme der inzwischen neueren Quellen. Die Wiederholung stellt denselben
ursprünglichen VM-Snapshot wieder her; der abgebrochene Zustand bleibt zusätzlich
als eigener Snapshot erhalten.

Inzwischen liefen auch die zugehörigen Produktions-Kindjobs, ein Weblauf #13 mit
`UserIdCause` und Musik-Synchronisation #235 mit `TimerTriggerCause`. CI #20 ist
erfolgreich beendet. Die vollständige lesende Auslöserprüfung steht in
`scenarios/root-private-existing-host/production-activity-audit.json`.
Der manuelle Akteur ist nicht anhand dieser Daten bewiesen; die Prüfung behauptet
daher keine ausschließlich automatischen Auslöser. Diese Abnahme hat keinen
Produktionsjob ausgelöst und nimmt die neueren Quellen nicht für Leroy ab.

Die vier Jenkinsfiles der neueren Commits #19/#20 sind bytegleich zum
Vergleichsstand; auch `scripts/ci.py`, Bootstrap und Postdeploy-Ausführung bleiben
unverändert. Die neueren Anwendungsquellen enthalten allerdings Änderungen am
Release-Validator und an dessen Tests: ausgelassenes `create_host_path` wird als
`false` akzeptiert, während ausdrücklich `true` weiterhin abgelehnt wird.
Dieser lesende Quellvergleich ist keine erfolgreiche Ausführung der neueren
Releases. Beleg: `followup/production-source-review/newer-pipeline-contract.json`.

Die unabhängige Worker-Korrektur für den aggregierten Kindlauf-Grund wurde erst
nach diesem eingefrorenen Vergleich auf die beiden NAS-Jobimages kopiert. Image-
Konfiguration und Abhängigkeiten, Runner-Profile, Controller und Lease-Budgets
bleiben unverändert. Die tatsächlich fehlgeschlagenen Negativläufe #102/#103
zeigen jetzt `acceptance: Child job did not succeed`, behalten ihren roten Status
und sind bereinigt. Der anfängliche Prüfassert verlangte fälschlich den
Subprozess-Exitcode 17 am Aktions-Launcher. Derselbe Lognachweis bestätigt beide
Ebenen: Testbefehl 17, Launcher nach `CalledProcessError` 1. Die Prüfung wurde
anhand derselben Läufe fortgesetzt; weder Wiederholung noch Änderung dieser
Ausführungssemantik. Die ursprüngliche Diagnose-Pipeline ist wiederhergestellt,
die zusätzliche Eltern-Testdefinition bleibt deaktiviert mit ihrer Historie.
Zwölf Vergleichsansichten und vier Fehlergrundansichten wurden einzeln in
Originalauflösung geprüft, weitere drei UI-Downloads sind hashverifiziert.
Belege: `followup/child-failure-reason-nas/report.json`,
`visual-graphato-ed21c2e6346a-existing-host/report.json` und
`visual-child-failure-reason/report.json`.

Vier zusätzliche Desktop-/Mobilansichten prüfen die Antares-Ausnahme und beide
Worker-Anzeigen. Der optionale Pool ist offline; der NAS-Worker wurde während der
Last ebenfalls als offline dargestellt. Die UI-Prüfung bestätigt diese tatsächlichen
Zustände und die erhaltene Historie; sie bestätigt keine gesunde Worker-Ausführung.
Nach der Budgetkorrektur antworten beide Controller-Healthchecks wieder mit HTTP 200.
Belege: `followup/candidates/graphato/ed21c2e6346aab6f71494765a37ba91e0d4559b7/`
und `visual-nas-scope-after-budget-relief-v2/`.

### Aktuell beobachteter Produktionsstand

Die ausschließlich lesende Prüfung am 5. Oktober um 12:01 UTC zeigt für
Produktions-Jenkins CI #17 `SUCCESS`, aber dessen tatsächliche Release-Abnahme
#10 sowie Web #10 und Qualität #10 `FAILURE`. Die gespeicherten Upstream-Causes
weisen alle drei ausdrücklich CI #17 zu. Dieser Lauf verwendet Commit
`bc3bd268c753e6eda8280c6aa37f0857e71d3a18`, nicht den aktuell isoliert geprüften
Kandidaten `9968c226f943` und nicht dessen Originalbasis `48b741264f3b`.

Web #10 besteht 20/21 Gruppen einschließlich Dauertest und scheitert bei
`browser-merge`: erwartet wird `pendingPush`, gemeldet wird `local`.
Qualität #10 besteht sieben von acht Gruppen; `frontend-and-deployment`
endet mit `ValueError: Preview admission requires its dedicated, pre-created runtime mount`.
Die Ergebnisdateien bestätigen abgeschlossene Bereinigung und keine
wiederverwendeten Teilnachweise. Dies sind weitere Produktions-Jenkins-Fehler,
kein Beleg für eine Ursache in Leroy und kein Vergleich desselben Quellstands.
Produktionsdateien, Jobs und Laufzeit wurden nicht verändert.

Eine weitere lesende Beobachtung um 16:51 UTC zeigt CI #18 mit `SUCCESS`.
Dessen Web #11 und Release-Abnahme #11 laufen zu diesem Zeitpunkt noch;
Qualität #10 gehört zur vorherigen Prüfung. Daraus wird weder eine vollständige
Release-Abnahme noch die Gleichheit mit dem eingefrorenen Kandidaten abgeleitet.
Die begrenzten Fortschrittsmetadaten stehen unter
`followup/production-graphato-progress-*`. Antares wartet vor neuen NAS-Tests
auf das Ende aller produktiven Jenkins-Jobs.

Die anschließend abgeschlossene Produktions-Webprüfung #11 meldet `FAILURE`:
20/21 Gruppen bestehen, `browser-merge` scheitert erneut. Ihre Ergebnisquittung
nennt Commit `ed21c2e6346aab6f71494765a37ba91e0d4559b7`; Cleanup ist abgeschlossen,
keine Ergebnisse sind wiederverwendet. Quittungsprüfsumme und begrenzte Metadaten
stehen in `followup/production-graphato-web-11.json`. Die Qualitätsprüfung #11
ist inzwischen mit `FAILURE` abgeschlossen: sieben von acht Gruppen bestehen,
`frontend-and-deployment` scheitert. Ihre Quittung bestätigt denselben Commit,
vollständiges Cleanup und keine wiederverwendeten Ergebnisse; Nachweis:
`followup/production-graphato-quality-11.json`. Release #11 endet ebenfalls mit
`FAILURE`. Auch dieser andere Quellstand ist kein Gegenbeweis zum
erfolgreichen isolierten Vergleich und kein Nachweis einer Ursache in Leroy.

Die begrenzten Metadaten, ausgewählten Fehlerzeilen mit Log-Prüfsummen und
Build-Beziehungen stehen unter `followup/production-graphato-context-*`,
`production-graphato-failures-*`, `production-graphato-errors-*` und
`production-graphato-upstream-17.json`. Ein erfolgreicher Vergleich des
eingefrorenen Kandidaten bestätigt dessen Ausführung; eine Produktionsumstellung
muss zusätzlich den tatsächlich vorgesehenen Quellstand berücksichtigen.

Die Nachprüfung am 5. Oktober umfasst außerdem:

- Der Vergleich von Jenkins #9 und Leroy #65 ist abgeschlossen und fehlgeschlagen:
  beide bestehen dieselben Unit-/Integrationsprüfungen und den Build, erreichen aber
  in der Browserphase das Pipeline-Zeitlimit. Die Fehlerartefakte bleiben erhalten.
- Ein zu langer Windows-Dateipfad hatte nur die lokale Sammlung der bereits
  vorhandenen Artefakte unterbrochen. Der Sammler verwendet nach der Pfadvalidierung
  erweiterte Windows-Pfade und setzt anhand der Prüfsummen fort. Ein Regressionstest
  deckt einen Pfad über 260 Zeichen, Wiederaufnahme und Traversal-Abweisung ab.
- Antares' beschrifteter Reputationscontainer hatte keine passende ARIA-Rolle.
  Commit `8607cfd438c7645012bf0482a5da83acb122d6dd` ergänzt Liste/Listeneinträge;
  der neue Test schlägt vorher fehl und besteht danach. Typprüfung, Lint und die
  vollständige lokale Browsermatrix (26 bestanden, drei vorgesehene Auslassungen)
  bestehen. Bestehende E2E-Prüfungen und Zeitgrenzen sind unverändert.
- Beide Antares-Ausführungsumgebungen stellen nun dieselbe bereits vorhandene
  Buildx-Binärdatei bereit (`v0.37.0`, SHA-256 `ae43fa08c796b44efc86d7a63c55f73f7c35f3101188dea7bf93bcd6f99577ba`).
  Je ein isolierter Probe-Build besteht. Dies ist eine gemeinsame Infrastrukturänderung;
  eine Beschleunigung der vollständigen CI ist damit noch nicht nachgewiesen.
- Für Graphatos erneuten Jenkins-Lauf ist die VM frisch wiederhergestellt; dieselbe
  Docker-Netzpolicy wie beim erfolgreichen Leroy-Lauf ist auf einer frischen VM
  geprüft. Die bisherigen erfolgreichen Jenkins-Nachweise liegen unverändert unter
  `attempts/jenkins-before-network-alignment`; sie werden nicht als Ergebnis des neuen
  Laufs ausgegeben.
- Diese Wiederholung ist inzwischen ausgewertet: Jenkins #3 besteht CI und alle
  acht Qualitätsgruppen. Die normalisierten Rust-Ergebnisse stimmen erneut mit
  Leroy überein: 1.527 bestanden, 29 ausdrücklich ignoriert. Die Websuite besteht
  20 Gruppen und scheitert bei `sendSessionPrompt` im Dauertest an HTTP 429.
  Archiv, Fehlertext und Prüfsummen sind gesichert; der Vergleich meldet ausdrücklich
  `workload_success_both=false`. Alle vier Zielcontainer sind gesund und ohne
  Neustart; HTTP/HTTPS liefern 200, anonyme Zugriffe 401 und das Desktop-Paket ist
  geprüft. Das ersetzt die fehlgeschlagene Web-/Release-Abnahme nicht.
- Erst dieser Jenkins-Fehler belegt die zeitabhängige Ratenbegrenzung unabhängig
  von Leroy. Kandidat `9968c226f943eb177f31c36fa0e97e7fc7f260d5` ergänzt ausschließlich
  im Testtreiber ein begrenztes Warten nach konsistentem `Retry-After`, unter Erhalt
  derselben Request-ID. Serverlimits, Assertions und fünfminütiger Dauertest sind
  unverändert. Transportfehler und uneindeutige Antworten werden nicht wiederholt.
  Der ältere Graphato-Lease-Patch bleibt weiterhin ausgeschlossen.

Zu den bisherigen Kandidaten gehören die getrennten Patches
[Graphato `78e92e09fa5f`](upstream-patches/graphato-nas-78e92e09fa5f.patch) und
[Antares `8607cfd438c7`](upstream-patches/antares-nas-8607cfd438c7.patch).
Die neue Graphato-Nachprüfung verwendet stattdessen den vollständigen Patch
[Graphato `9968c226f943`](upstream-patches/graphato-nas-9968c226f943.patch).
Ihre Anwendung auf den jeweiligen Originalstand wurde mit einem separaten
Git-Index geprüft und ergibt jeweils exakt den Git-Dateibaum des Kandidaten.
Frühere Patchdateien dokumentieren andere Diagnosestände und werden nicht
zusätzlich auf diese Kandidaten angewendet. Insbesondere gehören die früheren
Graphato-Patches für Ratenbegrenzung und Verbindungs-Leases nicht zu `78e92e09fa5f`.

### Unterbrechungen der aktuellen Nachprüfung

Beim Kandidaten `9968c226f943` verweigerte der Tunnel-Endpunkt
`10.232.98.11:12225` den Zugriff des Test-Bootstraps #4. Test-VM und
NAS-Brückendienst liefen weiter, die lokal aufgezeichneten Tunnel- und
Supervisor-Prozesse waren beendet. Die Statusdatei beschrieb noch ihren früheren
Zustand; der Grund für das Prozessende ist nicht belegt. Nach Erneuerung des
ausschließlich eigenen Rücktunnels wurde der gepinnte SSH-Zugriff aus dem
Test-Jenkins und das weiterhin anwendungsfreie VM-Ziel tatsächlich geprüft.
Bootstrap #5 besteht anschließend. Die bisherigen Buildnummern, Ergebnisse und
Vergleichsdatei liegen zusätzlich unter `attempts/jenkins-bootstrap-4`; die
nummerierten Logs bleiben unverändert. Der Teststarter prüft künftig den
tatsächlichen SSH-Zugriff vor dem Bootstrap. Eine Wiederholung benötigt weiterhin
einen ausdrücklich angegebenen Grund; sie ist keine automatische Fehlerwiederholung.

Nach Abschluss der vollständigen Jenkins-Abnahme wurde deren VM-Zustand im
Snapshot `before-graphato-leroy-9968c226f943` erhalten und der gemeinsame
Ausgangssnapshot wiederhergestellt. Der erste Einrichtungsaufruf lief vor
Bereitschaft des Gast-SSH in einen Banner-Timeout, noch vor seiner ersten
VM-Änderung. Die Einrichtung wartet nun begrenzt auf authentifiziertes SSH und
aktiven Docker. Auf derselben bereits zurückgesetzten VM bestehen anschließend
Werkzeug- und Netzprüfung; die Unterbrechung steht separat in
`leroy-preparation-interruption.json`. Keine Pipeline wurde dabei wiederholt.

Graphatos erste Leroy-Qualitätssuite führte Rustfmt, Clippy, Frontend und alle
Rust-Tests erfolgreich aus: 1.527 bestanden, 29 ausdrücklich ignoriert, keine
fehlgeschlagen. Beim anschließenden Entwicklerszenario brach die SSH-Verbindung ab.
Die Abnahme blieb folgerichtig fehlgeschlagen. Ein kontrollierter Nachweis mit
vier kurzlebigen Docker-Netzen reproduzierte die Ursache: Der automatisch
zugewiesene Bereich `172.23.0.0/16` macht die SSH-Quelladresse `172.23.0.1` zu einer
lokalen Bridge-Adresse der VM und verdrängt deren Rückroute. Der exakte kurzlebige
Bereich des ursprünglichen Abbruchs war nicht aufgezeichnet; der reproduzierte
Mechanismus passt zum betroffenen Entwicklerszenario.

Die ausschließlich für die Test-VM reservierte Docker-Adressvergabe
`10.211.0.0/16` mit `/24`-Netzen verhindert diesen Konflikt. Vier gleichzeitig
angelegte Netze und 70 Sekunden fortgesetzte SSH-Kommunikation wurden erfolgreich
geprüft. Die Anwendung bleibt unverändert. Die Wiederholung beginnt mit dem
frischen VM-Basiszustand; vorherige Läufe, Artefakte und VM-Zustand bleiben erhalten.
Jenkins' bereits erfolgreicher Lauf verwendete noch die ursprüngliche dynamische
Adressvergabe; diese Infrastrukturabweichung bleibt im Vergleich ausdrücklich sichtbar.

Die frische Leroy-Wiederholung verwendet CI-Lauf `ddce0d121be146a890457a50fb82b0f6`
und Build-Zeitstempel `20261004054140`. Web-Lauf `eeb2ff56e81b4d5e9f5ed11798ee2f65`
besteht alle 21 Prüfungen in 1.372 Sekunden, mit `cleanupComplete=true` und
`reused=[]`. Qualitätssuite `2e436b5ac7894434a7c45a2ff3bbc553` besteht alle acht
Prüfungen in 2.650 Sekunden, ebenfalls frisch und vollständig bereinigt.
Jenkins und Leroy liefern dieselben 1.527 bestandenen und 29 ausdrücklich
ignorierten Rust-Tests; der Hash der normalisierten Einzelergebnisse ist identisch.
Die abschließende Release-Bestätigung lautet `verified`, alle vier Zielcontainer
sind gesund und ohne Neustart, HTTP/HTTPS liefern 200 und anonyme Zugriffe 401.
Die zwölfstündige Anmeldung des lokalen Beobachters lief zwischenzeitlich ab;
der Beobachter prüft und erneuert seine Sitzung jetzt vor jedem lesenden Snapshot.
Er wurde an denselben Lauf angehängt, ohne Jobs oder Prüfungen neu zu starten.

Antares-Jenkins #8 endete tatsächlich mit `FAILURE`; sein Leroy-Beobachter hatte
zuvor wegen ausgebliebener Lease-Erneuerung abgebrochen. Der abgeschlossene
Jenkins-Build wurde anschließend ausgelesen, ohne ihn erneut zu starten, und das
temporäre Jenkins-Ressourcenbudget zurückgesetzt. Der Lease-Abbruch und die
gleichzeitig beobachteten Speicher-/I/O-Wartezeiten werden getrennt untersucht.
Die ursprünglichen Test- und Pipeline-Zeitlimits wurden nicht erhöht.

Die lokale Wiederholung von exakt `9f05b7f1aa56` mit zwei CPUs, 3 GiB RAM und
ohne Swap besteht alle 635 Unit-Tests in 240,51 Sekunden und die unveränderten
Coverage-Grenzen (87,29 % Statements, 79,13 % Branches, 90,5 % Functions,
87,83 % Lines). Alle versionierten Dateien wurden gegen das Git-Archiv geprüft.
Vitest sieht dadurch zwei verfügbare CPUs; sein Standardpool startet einen
Worker statt der fünf bei sechs verfügbaren CPUs. Dies ist eine lokale Diagnose
mit Node 24.17.0, keine NAS-Abnahme mit der dortigen Node-Version 24.18.0.

Zusätzlich wurde eine unabhängige Leroy-Blockierung nachgewiesen: Wartet die
Artefaktregistrierung auf eine PostgreSQL-Zeilensperre, blockiert der synchrone
Datenbankzugriff im asynchronen Endpunkt den Controller-Event-Loop. Registrierung
und Veröffentlichung laufen nun außerhalb dieses Loops. Zwei Regressionstests
halten echte PostgreSQL-Sperren und prüfen gleichzeitig den Heartbeat eines
anderen Laufs. Alle 61 Tests bestehen. Die Veröffentlichung behält ihre
Dateibereinigung im selben Thread, damit ein abgebrochener HTTP-Request keine
Datei während einer noch laufenden Datenbankbestätigung entfernt.
Ein zusätzlicher Test bricht genau in diesem Moment den HTTP-Request ab und
prüft anschließend Datenbankeintrag, Prüfsumme und vollständigen Dateiinhalt.
Diese Korrektur wurde um 07:18 UTC im NAS-Testcontroller installiert und anhand
des Quellhashes sowie der Bereitschaftsprüfung bestätigt. Ein ursächlicher Zusammenhang mit dem Antares-Beobachterabbruch
ist bisher nicht bewiesen.

Die zusätzliche visuelle Prüfung des fehlgeschlagenen Antares-Laufs zeigte einen
außerhalb des sichtbaren Graphenausschnitts liegenden ausgewählten Fehlerschritt.
Die lokale UI bringt nun den ausgewählten Knoten in den sichtbaren Bereich,
ohne manuelles Verschieben bei nachfolgenden Live-Aktualisierungen zurückzusetzen.
Sechs Desktop-/Mobilansichten mit echten NAS-Laufdaten wurden automatisiert und
visuell geprüft: Fehler-, erster und letzter Schritt sowie erhaltene
Graphenposition über zwei Aktualisierungen. Typecheck und Frontend-Build sind
erfolgreich. Die Korrektur ist ebenfalls auf dem NAS installiert; dieselben sechs
Ansichten und die 16 vollständigen Graphato-Ansichten bestehen dort die erneute
automatisierte und manuelle Prüfung. Das vorherige Controller-Image bleibt als
`leroy-controller:nas-parity-before-artifact-concurrency` für eine Rückkehr erhalten.

Der neue Antares-Vergleich verwendet auf beiden Seiten zwei CPUs, 3 GiB RAM und
denselben Node-Heap. Nur das CPU-Limit wurde gegenüber dem archivierten Fehlversuch
angepasst. Jenkins-Build #9 besteht alle 635 Unit-Tests einschließlich Coverage,
102 Integrationstests sowie Anwendungs- und Docker-Build. Die Browsermatrix
meldet anschließend eine nach zwei Sekunden noch laufende Kamerabewegung und
im Wiederholungsversuch eine unzulässige ARIA-Beschriftung von `.reputation-list`.
Danach beendet das unveränderte Pipeline-Limit von 30 Minuten den Lauf mit
`ABORTED`; die Bereinigung wird ausgeführt. Fehlerkontexte, Screenshots und beide
Traces sind unter `browser-failures-jenkins9-cpu2` gesichert.
Nach #9 wurde das temporäre Jenkins-Ressourcenbudget zurückgesetzt und der Test-Jenkins
angehalten. Leroy-Gegenlauf `9acac76033a044099181b0708bf884f2` verwendete denselben
Commit und die nachgewiesenen Werkzeugversionen, Images und Ressourcenlimits.
Quellstand, Jenkinsfile und Prüfgrenzen bleiben unverändert. Der Vergleich ist
ausdrücklich als Gegenprobe eines fehlgeschlagenen Jenkins-Laufs gestartet.
Er endet mit `timed_out`: alle 635 Unit- und 102 Integrationstests sowie der Build
bestehen, die Browserphase wird nach 618 Sekunden abgebrochen. Die Bereinigung
besteht. Tests benötigen 735 Sekunden, der Build 360 Sekunden. Weitere Browserfehler
betreffen Kamera, Einstellungen und Ressourcenanzeige; daraus wird keine
erfolgreiche Abnahme abgeleitet.

Die anschließende instrumentierte Wiederholung der ursprünglichen
Authentifizierungsprüfungen auf demselben Commit zeichnet Kamera-Callbacks auf,
ohne ihre Zeitstempel zu verändern. In dieser Stichprobe bestehen die Kamera-
Assertions; beide Versuche scheitern später am bereits separat korrigierten
ARIA-Fehler. Eine Änderung der Kameraimplementierung ist daraus nicht begründbar.
Der vollständige Jenkins-Build #10 auf `8607cfd438c7` ist gestartet. Sein Jenkinsfile
und die seit `9f05b7f1aa56` bestehenden Testgrenzen sind unverändert; beide
Ausführungsumgebungen erhalten identisch das Buildx-Plugin. Der passende Leroy-
Gegenlauf und die vollständige NAS-Abnahme dieses Kandidaten stehen noch aus.

Jenkins #10 wurde anschließend kontrolliert gestoppt: Parallel war auf dem NAS
der produktive Graphato-Build #16 angelaufen (23:13:09 UTC). Bei der Gegenprüfung
zeigte der Host erhebliche I/O- und Speicherwartezeiten. Dieser abgebrochene
Versuch zählt nicht als vollständiger Pipeline-Nachweis. Die Vergleichsskripte
warten jetzt vor Jenkins und Leroy auf den Abschluss der produktiven CI;
Produktionsjobs werden ausschließlich lesend beobachtet.
Der spätere Abgleich der Produktions-Buildintervalle zeigt für Antares #9 und
Leroy #65 keine Überschneidung mit `graphato-ci`. Diese früheren Browserfehler
und Zeitüberschreitungen werden daher nicht dem Produktionsbuild #16 zugeschrieben.
`scripts/audit_nas_antares_load.py` hält die Intervalle und Überschneidungen pro
Vergleich fest; es misst keine kontinuierliche Compilerlast oder sonstige NAS-Last.

Der Leroy-Beobachter von #10 hatte zuvor erneut seine Lease-Bestätigung verloren.
Die API beantwortete währenddessen weiterhin andere Anfragen. Ein gezielter
Regressionstest belegt zusätzlich einen bisher verbliebenen Fehler: Log-Flush
und `fsync` hielten die Laufsperre und blockierten den Heartbeat desselben Laufs.
Log-Schreibvorgänge sind nun über eine separate PostgreSQL-Advisory-Sperre
serialisiert; die Laufsperre wird erst für die kurze Veröffentlichung des
bestätigten Offsets genommen. Die Ausführungsberechtigung wird danach erneut
geprüft. Dateibereinigung wartet auf noch laufende Schreibvorgänge. Alle 65
Tests bestehen, einschließlich paralleler Wiederholung und Löschung nach
entzogener Berechtigung. Die genauen Ursachen des NAS-Beobachterabbruchs bleiben
von dieser reproduzierten Korrektur getrennt; Lease- und Pipeline-Fristen wurden
nicht erweitert.

Die Korrektur ist seit 23:34 UTC im NAS-Testcontroller installiert (Image
`sha256:18161d6c6d4ff8f384d6014dda0cfc3e1a8df6574d4d923417a10f874f84fc83`).
Die drei installierten Module sind gegen ihre SHA-256 geprüft, die UI-Dateien
sind unverändert. Das vorherige Image bleibt unter
`leroy-controller:nas-parity-before-log-heartbeat` erhalten.
Der anschließende NAS-Lauf `1873d98e61684e749a7f928d4cc9977b` besteht:
120 kontinuierliche Logmeldungen sind vollständig und in der richtigen Reihenfolge
gespeichert, die Lease bleibt erhalten. Während des gesamten 120-Sekunden-Tests
läuft weiterhin der produktive Graphato-Build #16. Der Test erzeugt selbst keine
Compiler- oder synthetische Hostlast und ersetzt keine vollständige CI-Abnahme.
Seine sechs Desktop-/Mobilansichten für Graph, Ergebnisse und Artefakte sind
automatisiert und visuell geprüft; das Ergebnisartefakt stimmt mit seiner
SHA-256 überein (`visual-log-heartbeat/report.json`).

Der anschließende Antares-Jenkins-Build #11 verwendet `8607cfd438c7` und läuft
ohne zeitliche Überschneidung mit der produktiven Graphato-CI. Alle 636 Unit-Tests
(363 Sekunden), 102 Integrationstests (472 Sekunden), die statische Prüfung und
der Build bestehen. Die Browserphase scheitert erneut an Zeitgrenzen; danach
beendet das unveränderte Pipeline-Limit den Lauf mit `ABORTED`. Elf Fehlerdateien
einschließlich vier Traces sind mit SHA-256 gesichert. Die Traces zeigen unter
anderem rund 16 Sekunden für den ersten Browserstart und Spiel-API-Anfragen bis
5,7 Sekunden. Zwei Antworten melden `409 retry_required`. Diese Beobachtungen
belegen noch keine einzelne Ursache. Host- und Cgroup-Messwerte bleiben neben
den Traces erhalten; Testfristen, Anwendungsquellen und Ressourcenlimits wurden
während des Laufs nicht verändert.

Der Leroy-Beobachter `0870f76c87184a9990c897c35b1ed5fe` besteht einschließlich
Ergebnissammlung und Wiederherstellung des temporären Jenkins-Budgets. Er verliert
seine Lease während dieses vollständigen CI-Laufs nicht. Das ist ein zusätzlicher
Betriebsnachweis für Leroy, kein bestandener Antares-Pipeline-Lauf. Jenkins ist
wieder angehalten. Der explizite Gegenlauf des fehlgeschlagenen Builds ist
Leroy #72 (`b090e71eb7854c38b84414801e6c50ed`) auf demselben Commit und derselben
Konfiguration. Er besteht 636 Unit-Tests (306 Sekunden), 102 Integrationstests
(431 Sekunden) und den Build. Nach Browserfehlern erreicht er das unveränderte
30-Minuten-Limit und verliert während der Artefaktsicherung seine Lease.
Sein endgültiger Status bleibt `interrupted`; die Bereinigung war nicht ausgeführt.
Auch dieser Lauf überlappt zeitlich keinen produktiven Graphato-CI-Build.

Die Controller-Logs belegen den letzten erfolgreichen Heartbeat um 01:01:57 UTC,
anschließend laufende Artefaktübertragungen bis 01:03:27 UTC und die erste
Abweisung um 01:03:28 UTC. Der Worker beendete seine Heartbeats beim Empfang
eines Abbruchbefehls, obwohl Artefaktsicherung und `always`-Schritte noch liefen.
Drei neue Regressionen reproduzieren diesen Fehler und prüfen auch weiterhin
sofortige Reaktion auf entzogene Ausführungsberechtigung. Nach der Korrektur
bestehen alle zwölf Heartbeat-Tests; mit Definitionen, Artefaktsammler und
Gitea-Readiness bestehen zunächst 36 Tests. Nach allen Worker-/Runner-Korrekturen
besteht die vollständige Suite mit echter PostgreSQL-Datenbank: 68 Tests. Die Frist bleibt 90 Sekunden.

Der verbliebene PostgreSQL-Testcontainer von #72 und sein eindeutig zugeordnetes
anonymes Volume wurden nach Sicherung der Diagnose entfernt. Der historische
Laufstatus wird nicht nachträglich umgeschrieben. Ein gesonderter lokaler
Docker-Test belegt außerdem, dass erzwungenes Entfernen ohne `-v` das anonyme
Datenvolume zurücklässt, auch bei `--rm`. Leroy entfernt nun zugehörige anonyme
Volumes ausdrücklich; benannte Volumes bleiben im Regressionstest erhalten.
Browser-Testcontainer tragen künftig ebenfalls die Laufkennung.
Beide Änderungen sind seit 01:14 UTC in den beiden NAS-Jobimages installiert,
mit unveränderten Abhängigkeiten und Laufzeitkonfigurationen. Die neuen Images
und Quellhashes stehen in `followup/cancel-cleanup-deployment.json`.
Die erste gezielte NAS-Abbruchprüfung endet korrekt als `timed_out`, ihre
Bereinigung scheitert aber vor der Wartephase: Der PostgreSQL-Healthcheck hatte
bereits den temporären Initialisierungsserver als gesund gewertet. Die echte
TCP-Datenbank startet erst danach. Der ursprüngliche Jenkinsfile enthält denselben
Socket-Healthcheck; dies ist kein belegter Unterschied zwischen Jenkins und Leroy.
Eine lokale Docker-Regressionsprobe mit acht Sekunden Initialisierung reproduziert
die verfrühte Bereitschaft. Leroys Healthcheck prüft nun ausdrücklich TCP auf
127.0.0.1; dieselbe Probe wartet danach bis zum tatsächlich erreichbaren Server.
Die TCP-Bereitschaftsprüfung ist seit 01:22 UTC in den NAS-Jobimages installiert.
Der neue Diagnoseversuch `98e598ced109483caa5b7c665405fa0a` besteht die
Abbruchprüfung: endgültiger Status `timed_out`, erfolgreiche Bereinigung nach
113 Sekunden, währenddessen mehr als 116 Sekunden fortgesetzte Lease-Erneuerung.
Ein tatsächlicher Datenbank-Schreibzugriff ist geprüft; Container und anonymes
Volume sind entfernt. Der Ergebnisdownload stimmt mit seiner SHA-256 überein. Die migrierten
CI-Definitionen und deren Zeitgrenzen bleiben unverändert.

Bei sechs zusätzlichen Desktop-/Mobilansichten des unterbrochenen Laufs wurden
133 Artefakte erfolgreich gegen SHA-256 geprüft. Die visuelle Kontrolle deckte
eine falsche grüne Zeitachsenfarbe für `interrupted` auf. Die UI ordnet jetzt
auch Unterbrechung, Abbruch, Wartezustände und übersprungene Schritte ihren
Statusfarben zu und benennt den Status für Screenreader. Beim Öffnen eines
unterbrochenen Laufs wird außerdem der betroffene Schritt ausgewählt.
Typecheck und Build bestehen; die UI ist seit 01:20 UTC im NAS-Testcontroller
installiert. Automatisierte Farbprüfungen der echten Laufdaten bestehen.

Eine ausschließlich lesende Stichprobe während #72 erfasst 60 Beobachtungen
von PostgreSQL: 24 aktive Warteereignisse `IO:WalSync` und 24 `LWLock:WALWrite`.
Ein `COMMIT` wartet rund 2,8 Sekunden; weitere Transaktionen warten aufeinander.
Das ist ein konkreter Hinweis auf Datenbank-I/O, noch kein Beweis für sämtliche
Browserfehler. Die Originalmessung bleibt als `leroy-b090e71eb7854c38b84414801e6c50ed-database-waits.json`
im Kandidatenordner erhalten. Weitere Anwendungspatches oder längere Testfristen
werden daraus nicht abgeleitet.

## Festgehaltene Quellen

`scripts/prepare_nas_parity.py` prüft die vier Original-Checkouts auf den
inventarisierten Commit und einen sauberen Arbeitsbaum. Es ermittelt die
Jenkinsfiles direkt aus den Git-Objekten, damit Windows-Zeilenenden keine
abweichende Quellidentität vortäuschen. Inline-Jenkinsfiles werden mit LF gehasht.
Das Skript startet keine Jobs und veröffentlicht keine Definitionen.

| Repository | Unveränderter Commit |
| --- | --- |
| Antares | `ab245279a2c5ba85dedef1180e7fd63b7f5b1398` |
| Graphato | `48b741264f3b8353400649f6b05abf6a9c129233` |
| Home-Lab Service Collection | `9fb528a1bb4b736d53d294510b374d516e973a03` |
| Nikicas Hub | `f7fcfcf78e8f3717217f841734be824a8e97bbd2` |

Der lokale Bericht `test-results/nas-parity/baseline.json` enthält alle 13 Jobs,
Commit-/Tree-Identitäten, Skript-Prüfsummen und die ausgewerteten Laufnachweise.
Vier historische Graphato-Skript-Prüfsummen im Inventar passen nicht zu den dort
angegebenen Git-Commits. Das wird als Abweichung protokolliert; die alten Angaben
werden nicht als verifizierte aktuelle Jenkins-Konfiguration behandelt.
Die live verwendeten Jobdefinitionen und Build-Revisionen wurden vor der Ausführung
erneut aus Jenkins ausgelesen und separat gespeichert.

Graphato wurde vor seinem ersten NAS-Vergleich vom ursprünglichen Inventarstand
`ffd4be75…` auf den tatsächlich von Produktions-Jenkins in Build #4 verwendeten
Originalstand `48b74126…` festgelegt. Dazwischen liegen vier reguläre Commits;
die vier Jenkinsfiles sind unverändert. Die Quellen wurden aus einem ausschließlich
lesend gemounteten Jenkins-Checkout als Git-Bundle übernommen. Das ursprüngliche
Baseline-Dokument und der alte lokale Checkout bleiben erhalten; der neue liegt
unter `.sources/graphato-nas-original`. `graphato-live-source.json` dokumentiert
die Auswahl. Die separaten Abnahme-Patches wurden nicht übernommen.

## Ausführungsbedingungen

1. Über SSH zunächst nur NAS-Ressourcen, belegte Ports/Netze, Docker-Version,
   laufende Image-IDs und die effektive Jenkins-Toolchain erfassen. Keine vollständigen
   Container-Umgebungen oder Zugangsdaten in Berichte schreiben.
2. Einen eigenen Leroy-Test-Stack und eine isolierte Jenkins-Instanz mit manuellen
   Vergleichsjobs anlegen. Produktionsjobs und ihre Trigger bleiben unverändert.
   Testjobs erhalten keine produktiven Schreibziele oder Deployment-Schlüssel.
3. Quellen auf dieselben Original-Commits pinnen. Images, Node/npm, Docker/Compose,
   UID/GID, Befehlsargumente und Ressourcen anhand der tatsächlich laufenden
   Umgebung abgleichen. Die Dockerfiles allein reichen als Versionsnachweis nicht.
4. Beide Systeme nacheinander gegen äquivalente isolierte Zielzustände ausführen.
   Anfangszustand, Caches und Vergleichsrevision für Änderungsprüfungen festhalten.
   Insbesondere darf Leroys lokales `test_workers = 1` nicht unbemerkt von Jenkins'
   `npm test` abweichen.
5. Graphatos Postdeploy-Suiten laufen bereits bei Jenkins auf einem entfernten
   Linux-Ziel. Beide CI-Systeme müssen vergleichbare Testziele verwenden;
   der Standort des Controllers allein macht die Tests nicht vergleichbar.
   Vollständige Suiten frisch ausführen und wiederverwendete Receipts ausschließen.
6. Schritte, Exitcodes, Tests/Skips, Fehlerursachen, Artefakte und Zielzustände
   vergleichen. Abweichungen zuerst auf die Migration und die Ausführungsumgebung
   zurückführen. Anwendungspatches erst separat nach belegter Ursache bewerten.

Zwei rote Gesamtergebnisse allein beweisen keine Gleichwertigkeit. Wenn beide
Systeme am selben Audit abbrechen, sind die nachfolgenden Schritte dadurch noch
nicht verglichen. Ergänzende Diagnoseausführungen müssen separat ausgewiesen
werden und dürfen keine erfolgreiche vollständige Pipeline vortäuschen.

## Zugang und derzeitiger Stand

Portainer ist unter `http://192.168.178.97:9000` erreichbar. Der Nutzer hat die
Arbeit über SSH im Hintergrund gewünscht. Die Einrichtung erfolgte erfolgreich
über Passwortanmeldung für `nikica.strugar` mit strikter Prüfung der vorhandenen
Hostschlüssel. NAS-Port 22 wurde mehrfach geschlossen und erneut freigeschaltet;
zuletzt lehnt er seit dem 4. Oktober gegen 02:16 UTC wieder Verbindungen ab.
Die Ursache ist nicht belegt. API, UI und eigener Testtunnel bleiben erreichbar. Der neue Compose-Stack
`leroy-nas-parity` liegt unter `/volume1/docker/leroy-nas-parity`; die UI ist unter
`http://192.168.178.97:8088` erreichbar. Controller, PostgreSQL und Runner laufen
mit eigenen Volumes. Die automatischen Auslöser aller 13 migrierten Pipelines
und der zusätzlichen manuellen Diagnosepipeline sind pausiert. Für alle 13
migrierten Pipelines liegen ausgewertete Vergleichsläufe vor. Unter Leroy enden
im Originalvergleich neun erfolgreich und vier fehlerhaft; erfolgreiche Läufe können dennoch
übersprungene Pfade enthalten. Graphatos Build, Auslieferung und Veröffentlichung
sind unter beiden CI-Systemen erfolgreich. Die nachgelagerte Abnahme ist bei
beiden fehlerhaft und belegt keine ausgeführten Web-/Quality-Checks.
Produktionsdienste wurden nicht verändert. Die folgende Tabelle beschreibt
ausschließlich diesen Originalvergleich; den aktuellen Stand der ergänzenden
Prüfungen zeigt die Tabelle am Anfang dieses Dokuments.

| Bereich | Nachweis und verbleibende Einschränkung |
| --- | --- |
| Antares | Identischer Audit-Abbruch; Static-, Test-, Build- und Browser-Schritte nicht ausgeführt. |
| Home-Lab | Identischer Lauf ohne Änderungen; tatsächlicher Image-Build und Push nicht geprüft. |
| Hub-Build, Gitea, Musik, Paperless, Graphato-Bootstrap | Vergleich der jeweils vorbereiteten Szenarien erfolgreich. |
| Hub-Bootstrap/-Deploy | Gleiches Anwendungsimage; Leroys Korrektur der Laufzeitrechte und Gesundheitsprüfung auf dem frischen Testziel bestätigt. Kein identischer Zielzustand mit Jenkins. |
| Graphato-CI | Originalquellen, sechs Basisimage-Digests, Release-Dateien, Laufzeitregeln, gesunde Dienste und Desktop-Paket geprüft. |
| Graphato-Web/-Quality/-Abnahme | Gleiche Verzeichnisrechte-Ablehnung vor Teststart; zusätzlich SSH-Ratenbegrenzung bei Leroys Quality-Diagnostik und Abnahmestatus. 21 Web- und acht Quality-Checks bleiben offen. |

Der Stack wurde über SSH mit Docker Compose angelegt und ist damit in Portainer
als externer Stack sichtbar; er ist noch kein über die Portainer-API verwalteter Stack.
Die isolierte Jenkins-Instanz liegt im verschachtelten Test-Docker-Daemon und hat
keinen veröffentlichten Port. Beide Ausführungsumgebungen verwenden dasselbe
Vergleichsimage auf Basis des tatsächlich laufenden Jenkins-Images. Leroy erhält
einen zusätzlichen Python-Worker; die von Anwendungsskripten verwendeten Werkzeuge
bleiben dabei unverändert.

Ressourcen: NAS 6 logische CPUs, rund 7,5 GiB RAM. Begrenzungen für den zusätzlichen
Stack: Controller 256 MiB, PostgreSQL 256 MiB, Runner 192 MiB; gesamter Test-Daemon
einschließlich seiner Container zunächst 3 GiB RAM / 4 GiB RAM+Swap und 2 CPUs. Vergleichsläufe
werden nacheinander ausgeführt. Diese kontrollierten Limits unterscheiden sich von
dem unbegrenzten Produktions-Jenkins und sind als Vergleichsbedingung festzuhalten.

Während der ursprünglichen Graphato-Serverkompilierung beansprucht ein einzelner
Rust-Prozess rund 2,3 GiB RAM. Mit den übrigen Testdiensten führt das ursprüngliche
3-GiB-Gesamtlimit zu starkem Reclaim und Zeitüberschreitungen bei Docker-Abfragen.
Der eigene Test-Daemon erhält deshalb 3,5 GiB RAM. Nachdem auch der anfängliche
Swap-Spielraum ausgeschöpft war, wurde RAM+Swap auf insgesamt 6 GiB erweitert;
das RAM-Limit bleibt unverändert. Das CPU-Limit bleibt 2, die I/O-Gewichtung 100.
Die Änderungen erfolgen während Jenkins
Build #1; Leroy verwendet anschließend dasselbe angepasste Limit. Laufzeiten sind
deshalb ausdrücklich kein Performancevergleich. Der Nachweis steht in
`graphato-resource-adjustment.json`.

Beide Graphato-Builder beginnen den Vergleich mit getrennten leeren Build-Caches.
Jenkins verwendet `graphato-registry-ci`, Leroy `leroy-graphato-nas-parity`.
Danach bleiben die getrennten Caches für weitere Läufe erhalten. Das spart
wiederholte Abhängigkeits-Builds und übernimmt keine Test-Receipts.

Die Netzwerkregeln werden bei jedem Start innerhalb des Test-Daemons gesetzt.
Heimnetz, private Netze sowie die Produktionsziele `87.106.133.233` und
`213.165.73.233` sind gesperrt; erlaubt bleiben die
eigenen Testnetze, der Controller-Port und öffentliche Paketquellen. Ein Probecontainer
bestätigte die Sperren sowie erfolgreichen Controller- und npm-Zugriff.

Live-Befunde aus `test-results/nas-parity/nas-inventory.json` und
`production-jenkins-history.json`:

- Jenkins läuft als UID/GID 0; Node 24.18.0, npm 11.16.0, Python 3.13.5.
- Standard-Docker-CLI 26.1.5 ohne Compose-Plugin; Graphato verwendet separat
  Docker 29.8.0 und Compose 5.5.1. NAS-Daemon: 29.6.2.
- Antares hat nur einen alten fehlgeschlagenen Lauf: GitHub-Authentifizierung
  scheiterte bereits beim Laden des Jenkinsfiles. Anwendungstests liefen dort nicht.
- Graphato-Lieferung #4 ist erfolgreich, beide Postdeploy-Suiten und Release-Abnahme
  #4 sind fehlgeschlagen; Commit `48b741264f3b8353400649f6b05abf6a9c129233`.
  Frühere erfolgreiche Läufe sind deshalb keine aktuelle grüne Gesamtabnahme.

NAS-Oberfläche: `scripts/verify_nas_ui.cjs` prüfte Anmeldung, alle Hauptansichten,
13 Definitionen/Startformulare, Laufgraph, Zeitachse, Detailtabs sowie Mobilansichten.
Die aktuelle Runde umfasst 55 Screenshots einschließlich der gescrollten langen
Formulare und 66 Prüfungen ihrer Parameter-Vorgaben. Alle Bilder wurden visuell
kontrolliert. Zwei Detailtab-Aufnahmen waren noch während des Datenladens entstanden;
`scripts/verify_nas_ui_details.cjs` ergänzt deshalb sechs geprüfte Ansichten mit
geladenen Ereignissen, echtem Laufvergleich und einem heruntergeladenen Build-Artefakt,
dessen Größe und SHA-256 mit dem API-Nachweis übereinstimmen. Es gab keine
JavaScript-Fehler oder horizontalen Seitenüberläufe. Das ersetzt keine Pipelineabnahme.

Dabei wurde ein tatsächlicher Navigationsfehler korrigiert: Bis die Daten der
gewählten Pipeline eintreffen, zeigt die UI nun einen Ladezustand statt einer
vorübergehend leeren oder veralteten Historie. Ein Test mit absichtlich verzögerten
API-Antworten schlägt vorher fehl und besteht nach der Korrektur. Die NAS-Formulare
verwenden jetzt die isolierten Vergleichsziele als Vorgaben; `APPLY_CHANGES` bleibt
ausgeschaltet. Bereits ausgeführte Läufe und ihre Parameter bleiben erhalten.

Auch innerhalb eines Laufs wird eine falsche Zuordnung während langsamer Antworten
verhindert: Beim Schrittwechsel verschwinden die vorherigen Logs und Ereignisse
sofort zugunsten eines Ladezustands. Der Vergleichstab zeigt seinen eigenen
Ladezustand. `detail-loading.spec.ts` reproduziert den vorherigen Fehler und
besteht nach der Korrektur; Ereignispagination, Verbindungswiederherstellung und
Seitennavigation bestehen weiterhin. Die UI-Schicht wurde separat als
`detail-loading-ui.json` auf dem NAS verifiziert; die erneute visuelle Prüfung
liegt unter `visual-detail-loading` und `visual-populated-details`.

Der NAS-Controller erhielt ausschließlich eine zusätzliche Schicht mit den
gebauten UI-Dateien auf seinem bisherigen Image; Backend und Abhängigkeiten
blieben identisch. Ein beim Neustart sichtbar gewordener Leserechtefehler der
eigenen `leroy.toml` ist behoben. Der Deployment-Helfer prüft nun die Rechte und
die tatsächliche Bereitschaft des Controllers. `route-loading-ui.json` dokumentiert
Image-Identität, Schichten und die über HTTP verifizierten Asset-Prüfsummen.

## Erste Läufe und weiterer Abgleich

Die erste Vergleichsinstanz verwendete die Plugins aus dem Jenkins-Docker-Image.
Der anschließende Live-Abgleich ergab denselben Jenkins-Core 2.541.3, aber einen
anderen `workflow-job`-Patchstand und zusätzliche installierte Plugins im
Produktions-Jenkins. Deshalb sind diese ersten Läufe als Vorläufe eingeordnet.
`scripts/align_nas_jenkins.py` übernimmt ausschließlich die installierten Plugin-JARs
lesend aus Jenkins in eine neue Testinstanz; bestehende Konfigurationen und
Zugangsdaten des produktiven Jenkins werden nicht übernommen. Die vorige
Testinstanz und ihre Daten bleiben als `jenkins-parity-initial` erhalten.

Im angeglichenen Vergleichsimage verwendet auch Leroys Worker Python 3.13.5 in
einer eigenen virtuellen Umgebung. Das verhindert, dass importierte ursprüngliche
Python-Skripte versehentlich mit dem Python 3.14 des normalen Leroy-Images laufen.
Die erneuten Nachweise werden unter `test-results/nas-parity/aligned/` getrennt gespeichert.
Der erneute Versionsabgleich bestätigt alle 98 aktiven Plugins und den Jenkins-Core
identisch zum produktiven Jenkins.

Im angeglichenen Durchlauf bestätigen Jenkins #1 und Leroy `f9c15a5e…` für
Antares denselben Audit-Abbruch mit sechs High-Funden und denselben 30 Advisory-IDs.
Die Folgeschritte bleiben ungeprüft. Home-Lab ist auf beiden Systemen erfolgreich:
Jenkins #1 und Leroy `e0d321ad…` verwenden denselben Vergleichsstand `9fb528a1…`,
erkennen keine Änderungen und überspringen Build/Push. Auch dieser Durchlauf prüft
den tatsächlichen Image-Build noch nicht. `scripts/summarize_nas_parity.py` hält
diese begrenzten Aussagen in den Vergleichsberichten und `docs/acceptance.json` fest.

Die Vorläufe haben bereits Folgendes gezeigt:

- Antares, Commit `ab245279…`: Jenkins #2 und Leroy `f95a4ffa…` brechen beide
  am unveränderten `npm audit --omit=dev --audit-level=high` mit Exitcode 1 ab.
  Beide melden sechs High-Funde und dieselben Advisory-IDs. Checkout, Toolchain,
  Datenbankstart und Cleanup liefen; Statik, Tests, Image und Browser wurden
  in beiden Systemen übersprungen. Damit sind diese Folgeschritte nicht verglichen.
- Home-Lab, Commit `9fb528a1…`: Jenkins #1 und Leroy `4376e1a8…` erkennen
  dieselbe reine Dokumentationsänderung gegenüber `b19bb907…`. Beide sind
  erfolgreich und überspringen Build/Push. Der tatsächliche Build-Pfad ist dadurch
  noch nicht geprüft.
- Hub, Commit `f7fcfcf7…`: Jenkins #1 baute und veröffentlichte erfolgreich
  `registry:5000/home-lab/nikicas-hub:f7fcfcf78e8f-20260619` ausschließlich in die
  innere Test-Registry. Der folgende angeglichene Vergleich ersetzt diesen Vorlauf.

Es liegt weiterhin **keine vollständige NAS-Abnahme aller 13 Pipelines** vor.

Der angeglichene Hub-CI-Vergleich ist inzwischen erfolgreich: Jenkins #1 und
Leroy `5e5bc152…` bauen denselben ursprünglichen Commit `f7fcfcf7…` mit demselben
Node-Basisimage und veröffentlichen ausschließlich in die Test-Registry.
Alle 4.262 Einträge unter `/app` stimmen in Inhalt, Rechten, Besitzern und
Symlink-Zielen überein; auch die Laufzeitkonfiguration ist identisch. Image-IDs
unterscheiden sich, da Zeitstempel und Layer-Metadaten nicht normalisiert wurden.
`aligned/nikicas-hub-ci/artifact-comparison.json` dokumentiert den Vergleich.
Bootstrap und Deployment sind gesondert weiter unten dokumentiert.

Gitea und Musik-Sync sind inzwischen ebenfalls verglichen:

- Gitea: Jenkins #2 und Leroy `0e03da19…` erzeugen identische Admin- und
  Repository-Eigenschaften in getrennten leeren Instanzen desselben Images.
  Jenkins #1 startete noch während der ersten Datenbankmigration und scheiterte
  an einer Datenbanksperre. Dieser Fehlversuch bleibt erhalten; für den eigentlichen
  Vergleich wurde die API-Bereitschaft beider Instanzen vorher geprüft.
- Musik: Jenkins #1 und Leroy `3f8712da…` übertragen zwei WAV-Dateien mit
  Leerzeichen beziehungsweise Umlaut im Namen. Dateipfade, SHA-256, Rechte und
  Besitzer stimmen überein; temporäre Dateien und Metadaten werden ausgeschlossen.

Die Gitea-Testinstanzen verwenden wie die vorhandene Gitea-Installation SQLite;
Leroys eigene Datenhaltung läuft weiterhin ausschließlich auf PostgreSQL.
Beim Transport vorhandener Images zwischen NAS-Daemon und innerem Test-Daemon
können die Image-IDs abweichen. `scripts/nas_target_images.py` vergleicht deshalb
die tatsächlichen RootFS-Schichten und die Laufzeitkonfiguration und dokumentiert
beide IDs. Produktive Containerkonfigurationen und Daten werden nicht kopiert.

Hub-Bootstrap unter Jenkins #1 ist erfolgreich. Auf der frischen VM entsteht der
Deploy-Benutzer mit UID 1001; die ursprünglichen Bind-Verzeichnisse gehören ihm
mit Modus 0755. Das Anwendungsimage verwendet UID 1000. Dieser beobachtete
Unterschied wurde im anschließenden Deployment geprüft. Das Hub-Testnetz blockiert
ausgehende Verbindungen zu öffentlichen Diensten einschließlich öffentlichem ACME;
öffentliche Zertifikatsausstellung gehört nicht zu dieser Testumgebung.

Der anschließende Hub-Vergleich ist abgeschlossen: Jenkins-Bootstrap #1 und
Deployment #1 melden Erfolg, aber der App-Container startet mit `SQLITE_CANTOPEN`
ständig neu. Eine Zugriffsprüfung mit dem unveränderten Image bestätigt, dass
UID 1000 nicht in das Verzeichnis von UID 1001 schreiben kann. Leroy-Bootstrap
`022fdbb5…` richtet die Bind-Verzeichnisse für UID 1000 und die Deploy-Gruppe mit
Modus 2770 ein. Deployment `4976313f…` wartet zusätzlich auf den Healthcheck.
Anschließend sind HTTP-Probe, Schreibzugriff und Containerzustand erfolgreich,
ohne Neustarts. Beide Versuche verwenden exakt dasselbe App-Image `224eb8ef…`,
dasselbe Proxy-Image und dieselbe Compose-Datei. Die VM wird zwischen beiden
Versuchen auf denselben sauberen Snapshot zurückgesetzt.

Das ist eine belegte Verhaltensverbesserung in Leroys Ausführung, keine vollständige
Verhaltensgleichheit und kein Anwendungspatch. Der Befund gilt für diesen frischen
Host mit UID 1001; er behauptet keinen entsprechenden Fehler auf dem produktiven
Hub-Host. Beide VM-Ergebnisse bleiben als Snapshots erhalten.

Paperless ist auf beiden Systemen erfolgreich: Jenkins #1 und Leroy `de7c64ea…`
erzeugen je 64 Tags, 15 Dokumenttypen und 31 Korrespondenten in getrennten frischen
Instanzen mit denselben produktiven Image-Schichten und eigenen PostgreSQL-Datenbanken.
Der API-Vergleich bestätigt sämtliche erfassten fachlichen Eigenschaften identisch.
Nach dem Vergleich werden nur die eigenen Paperless-Testcontainer gestoppt, um
Speicher für Graphato freizugeben; Volumes und Nachweise bleiben erhalten.

Graphato-Bootstrap ist unter Jenkins #1 erfolgreich. Die installierten Empfänger-,
Firewall- und AppArmor-Dateien entsprechen den Git-Blobs von `48b74126…`.
Gepinnte Docker-Pakete, aktive Dienste, UFW und erzwungenes AppArmor sind geprüft.
HTTPS wurde tatsächlich über die lokale Test-CA ausgestellt und validiert.
Leroy-Bootstrap `49057934…` ist ebenfalls erfolgreich; alle erfassten Zielwerte
stimmen exakt überein.

Jenkins-CI #1 hat aus diesem unveränderten Commit Server und Windows-Client
gebaut und erfolgreich ausgeliefert. Authentifizierte HTTP- und HTTPS-Prüfungen
liefern Status 200 mit der erwarteten Build-Identität, anonyme Anfragen Status 401.
Alle vier Container sind gesund und ohne Neustarts. Das veröffentlichte portable
ZIP stimmt mit seiner Manifest-Prüfsumme überein; Mitglieder, CRC, Windows-Header
und eingebettete Build-Metadaten wurden geprüft. Die Nachweise liegen in
`aligned/graphato-ci/jenkins-final-state.json`.

Die automatisch gestarteten Jenkins-Jobs `graphato-postdeploy-web` #1 und
`graphato-postdeploy-quality` #1 scheitern dagegen vor ihren eigentlichen Checks.
Graphatos Wartungsdienst legt beim Start `postdeploy` über `create_dir_all` bei
Umask 0022 als root:0755 an (`maintenance/host_service.rs`). Der unveränderte
Python-Abnahmecode verlangt für dieses Verzeichnis root:0700 und lehnt es mit
`Run markers require root-private directories` ab. Die Diagnose ist auf der VM
bestätigt und in `jenkins-postdeploy-startup-failure.json` gespeichert. Die
übergeordnete Abnahme #1 schlägt deshalb korrekt fehl; die Release bleibt als
ausgeliefert mit fehlenden Suite-Nachweisen registriert. Dies belegt keine
ausgeführten Browser- oder Quality-Tests. Derselbe Verzeichnisbefund ist inzwischen
auch auf dem frisch durch Leroy ausgelieferten Ziel bestätigt.
Der gesamte VM-Zustand bleibt im Snapshot `before-graphato-leroy` erhalten.

Der erste Leroy-CI-Versuch `efb7bc31…` wurde am 3. Oktober um 18:11 UTC beim
Server-Build durch eine abgelaufene Runner-Lease unterbrochen. Im eigenen
Docker-Dienst waren 3,5 GiB RAM und 2,5 GiB Swap ausgeschöpft; die Messung zeigte
starken Speicherdruck, jedoch keinen OOM-Kill. Deployment und Veröffentlichung
wurden nicht ausgeführt. Der Jobcontainer und die Build-Prozesse sind beendet;
das Ziel enthält weiterhin nur den geprüften Bootstrap. Dieser Versuch ist eine
Leroy-Infrastrukturabweichung und kein Fehlernachweis gegen Graphatos Quellcode.

Die Untersuchung fand außerdem eine unzureichende Fehlerbehandlung im Worker:
Heartbeats nutzten dieselbe HTTP-Verbindungssammlung wie Uploads und konnten
innerhalb eines Aufrufs sechs lange Wiederholungen durchlaufen. Leroy verwendet
nun eine separate Verbindung, einen einzelnen kurzen Versuch und ein Zeitbudget
ab der letzten bestätigten Anfrage. Abgewiesene Versuche werden sofort beendet;
die serverseitige Lease bleibt bei 90 Sekunden. Docker-Aufrufe im Supervisor
haben ebenfalls ein Zeitlimit. 57 Tests einschließlich PostgreSQL und acht neuen
Worker-/Runner-Prüfungen sind erfolgreich. Diese Codebefunde beweisen nicht,
dass HTTP-Wiederholungen die konkrete NAS-Unterbrechung allein verursacht haben.
Ein zusätzlicher Test mit einem echten lokalen HTTP-Server bestätigt, dass ein
blockierter Log-Upload bei ausgeschöpfter Upload-Verbindung die separate
Heartbeat-Verbindung nicht blockiert; alle neun Lease-/Runner-Tests bestehen.

Für die Wiederholung erhalten die Jobprozesse im Graphato-Profil eine
Speicherreservierung von 128 MiB. Der bereits abgeschlossene Test-Jenkins und
sein unbenutzter Builder sind gestoppt; Volumes und Ergebnisse bleiben erhalten.
Die eigenen Docker-Gesamtlimits bleiben unverändert. Die Wiederholung verwendet
den teilweise gefüllten Leroy-Buildcache; Laufzeiten sind deshalb ausdrücklich
kein Leistungsvergleich. Der erste Versuch samt Logs und Wiederherstellungsgrund
wird separat aufbewahrt und über `retry_of` mit der Wiederholung verknüpft.
Diese Verknüpfung sowie Abbruchgrund und Schrittzustände sind auf Desktop und
Mobilgerät mit vier weiteren Screenshots geprüft (`visual-retry/report.json`).

Der zweite Versuch `f36b0cbe…` baut Server, Worker und Windows-Client erfolgreich.
102 Messungen über etwa 51 Minuten zeigen mindestens 82,8 Sekunden verbleibende
Lease und höchstens 0,312 Sekunden API-Antwortzeit. Die Auslieferung scheitert
anschließend vor dem Upload an `graphato-vm:12225: Connection refused`: Der
separate Rücktunnel war vom entfernten Ende geschlossen worden. Die VM läuft
weiter und enthält nachweislich noch keine Graphato-Installation. Dieser zweite
Versuch samt Build-Artefakten ist ebenfalls separat aufbewahrt.

Der gepinnte Testtunnel wurde wiederhergestellt und erhält für sechs Stunden eine
lokale Überwachung mit Wiederverbindung. Ein zusätzlicher, manueller Diagnosejob
bestätigt per erzwungenem SSH-Statusbefehl das unveränderte Bootstrap-Ziel.
Ein gezielter Abbruch ausschließlich des eigenen lokalen Tunnelprozesses während
der Kompilierung bestätigt die automatische Wiederverbindung innerhalb von
14 Sekunden einschließlich anschließender Stabilitätskontrolle
(`tunnel-recovery/reconnection-test.json`).
`d84285fa…` wiederholt danach die Originalpipeline. Diese Infrastrukturkorrektur
ändert keine Anwendungsquellen. NAS-Verwaltungs-SSH auf Port 22 ist inzwischen
nicht erreichbar; der eigene Brückendienst auf Port 12226 bleibt erreichbar.
Die Ursache für die geschlossenen Verbindungen ist nicht belegt.

Dieser dritte CI-Versuch endet um 19:56 UTC erfolgreich: alle zehn Schritte,
einschließlich Auslieferung und Veröffentlichung. 49 Lease-Messungen erfassen
mindestens 79,9 Sekunden Restzeit und höchstens 0,265 Sekunden API-Antwortzeit.
Server, Wartungsdienst, Test-Worker und PostgreSQL sind gesund ohne Neustarts;
HTTP und vertrauenswürdig geprüftes HTTPS liefern die erwartete Build-Identität.
Anonyme Anfragen werden mit 401 abgewiesen. Die Release-Dateien einschließlich
der ursprünglichen Prüfquellen stimmen mit Jenkins überein; die sechs verwendeten
Basisimage-Digests ebenfalls. Buildzeitstempel unterscheiden sich, weshalb keine
binäre Byte-Identität behauptet wird.

Die Kindläufe `2d6bef89…` (Abnahme), `d12f8af6…` (Web) und `1e198c89…` (Quality)
enden fehlerhaft. Das unveränderte Ziel hat wiederum root:0755 statt root:0700
für `postdeploy`; es existieren keine Prüfreceipts. Während der schnellen
Fehlerbehandlung erreicht Leroy zusätzlich die unveränderte SSH-Ratenbegrenzung
des Zielhosts. Das Kerneljournal bestätigt elf `UFW LIMIT BLOCK`-Beobachtungen;
über das VM-NAT teilen Testtunnel und lokaler Administrator dieselbe Quelladresse.
Quality-Diagnostik und der abschließende SSH-Status scheitern deshalb zusätzlich
an Timeouts. Nach Ende der Aufrufe ist der Zugang ohne Konfigurationsänderung
wieder verfügbar. Diese Ausführungsabweichung ist gesondert dokumentiert und wird
nicht als identisches Fehlerergebnis ausgegeben. Ein dauerhaft belastbarer
Transport für diesen schnellen Fehlerpfad bleibt nachzuweisen.

`aligned/graphato-ci/leroy-final-state.json` enthält die unabhängig gelesenen
Ziel- und Veröffentlichungsdaten. Der manuelle Diagnosejob `521c4172…` prüft
das tatsächlich auf dem NAS veröffentlichte Windows-Paket in einem Container
mit schreibgeschütztem Mount: Manifest, SHA-256, Dateigröße, Latest-Kopie, ZIP-CRC,
fünf Mitglieder, Windows-Header und Build-Metadaten. Seine Evidenz wird wiederum
mit Größe und SHA-256 vom Controller geladen. Der fehlende NAS-Verwaltungszugang
blockiert diesen Nachweis nicht.

Die abschließenden zwölf Screenshots unter `visual-graphato-final/` und
`visual-diagnostics/` wurden auf Desktop und Mobil visuell geprüft: Erfolg des
Hauptlaufs, rote Kindläufe, Elternverknüpfungen, Graph, Zeitachse, Logs,
Diagnosedefinition, Startdialog und Artefakt. Browserprüfungen zeigen keine
Seitenfehler oder horizontalen Seitenüberläufe. Die fehlgeschlagenen Kindläufe
bleiben auch unter dem erfolgreichen Hauptlauf sichtbar.

Neben den 13 migrierten Pipelines gibt es deshalb eine ausdrücklich als Diagnose
gekennzeichnete Pipeline `leroy-nas-diagnostics`, ohne automatische Trigger.
Sie dient auch der unabhängigen, schreibgeschützten Kontrolle der veröffentlichten
Test-Pakete über einen eigenen Container. Der NAS-Verwaltungszugang ist dafür
nicht erforderlich; Produktionspfade werden nicht gemountet.

Beim Gitea-Abgleich wurde eine Lücke im Leroy-Adapter gefunden: Der vorhandene
Parameter `GITEA_WAIT_SECONDS` wurde bisher nicht ausgewertet. Der Adapter wartet
nun wie der Jenkins-Job nach dem Abgleich des Admin-Kontos auf die API. Zwei Tests
mit einem lokalen HTTP-Server belegen die Erholung nach HTTP 503 sowie einen
begrenzten Abbruch ohne Repository-Anfrage, wenn der Dienst nicht bereit wird.
Die Korrektur betrifft Leroy; Gitea und die Jenkins-Quellen bleiben unverändert.
Sie erhält für den NAS-Vergleich ein eigenes Gitea-Jobimage.

## Frisches Linux-Ziel für Graphato

Auf dem Windows-Docker-Host läuft `leroy-nas-target-vm` mit eigener Ubuntu-VM,
10 GiB Gast-RAM, Kernel `6.8.0-142-generic` und aktivem AppArmor. Die vorherige
Abnahme-VM wurde sauber heruntergefahren; ihre Disk bleibt erhalten. Das neue
Volume `leroy-nas-target_disk` enthält keine übernommenen Anwendungspatches.
Docker-Pakete entsprechen den Pins der unveränderten Graphato-Hostrichtlinie.
DNS und ACME laufen ausschließlich innerhalb der Test-VM. Vor der ersten
Anwendungsinstallation wurde nach sauberem Herunterfahren der Snapshot
`nas-parity-base` angelegt, um äquivalente Zielzustände herstellen zu können.

Der NAS-SSH-Dienst erlaubt keine Portweiterleitung. Seine Konfiguration bleibt
unverändert. Stattdessen betreibt der Teststack einen eigenen SSH-Dienst auf
NAS-Port 12226, ausschließlich mit einem generierten Testschlüssel. Er erlaubt
nur den Rückleitungs-Listener auf `10.232.98.11:12225`, keine Shell,
Passwortanmeldung oder weiteren Listener. Die eingerichtete Verbindung führt zu Windows-Loopback-Port 2225
der neuen VM. Nur dieser Port ist zusätzlich in der Testnetz-Sperre freigegeben.
Es wurde keine Windows-Firewall-Ausnahme eingerichtet.

Die eigene Jenkins-SSH-Konfiguration leitet Graphatos feste Zieladresse auf
diesen Testanschluss um. Ein separater, gepinnter Hostschlüssel bleibt mit strikter
Prüfung aktiv; die Git-Quellen einschließlich ihrer ursprünglichen `known_hosts`
bleiben unverändert. Ein Verbindungstest aus dem NAS-Test-Jenkins bestätigte
Gast-Kernel, KVM und AppArmor. `vm-transport.json`, `vm-ready.json` und
`vm-snapshot.json` dokumentieren die Einrichtung. Die SSH-Verbindung benötigt
den laufenden Windows-Rechner; dies ist eine Abnahmeumgebung.

`scripts/nas_ssh.py` verwendet die von Git ausgeschlossene Datei
`.local/nas-ssh.json` und führt ausschließlich ein explizit übergebenes Skript aus.
Es installiert keinen Schlüssel und deaktiviert keine Hostschlüsselprüfung.
Passwörter werden nicht als Kommandoargumente übergeben oder ausgegeben.

## Nachprüfung vom 3. Oktober, ab 20:00 UTC

Der NAS-Verwaltungszugang wurde vom Benutzer erneut aktiviert und funktioniert.
Die frühere Zugangsbeschränkung ist damit aufgehoben. Die folgenden Nachweise
ergänzen die unveränderte Baseline; fehlgeschlagene Originalversuche bleiben erhalten.

### SSH-Transport

Graphatos SSH-Aktionen verwenden jetzt jeweils eine eigene, private OpenSSH-
Masterverbindung. Status, Polling, Diagnostik und Aufräumen derselben Aktion
verwenden diesen Kanal. Ein verschwundener Master verursacht einen lokalen Fehler;
es gibt weder eine automatische neue Verbindung noch eine Wiederholung entfernter
Kommandos mit unbekanntem Ergebnis. Hostschlüssel- und Credential-Prüfung bleiben
erhalten. Socket-Verzeichnisse sind privat und werden auch nach Fehlern entfernt.

Der reale VM-Test `092f5f3e…` bestätigt 18 Aufrufe über eine Verbindung,
unveränderte Fehlercodes, zehn lokal fehlschlagende Aufrufe nach Masterverlust
und Aufräumen bei Exceptions. Die beiden NAS-Jobimages enthalten nur das geprüfte
Quellcode-Overlay; Abhängigkeiten und Runner-/Controller-Version wurden dabei
nicht geändert (`followup/ssh-session-deployment.json`).

Die anschließende Original-Abnahme `a7820df9…` einschließlich beider Kindläufe
beendet ihre SSH-Kommandos ohne Transportfehler und lädt den Release-Status.
Alle drei Läufe bleiben wegen des unveränderten Anwendungsfehlers rot. Das ist
ein bestandener Transport-Regressionsnachweis, keine bestandene Graphato-Abnahme
(`followup/ssh-acceptance-after-pressure/report.json`). Ein vorheriger Versuch
`e7e6ddfb…` bleibt separat dokumentiert: Ein Kindlauf konnte unter NAS-Speicherdruck
nicht innerhalb des Docker-Aufruflimits gestartet werden.

### Getrennte Anwendungskandidaten

Die rein lesend geprüfte Produktionshistorie zeigt keinen erfolgreichen Antares-
Lauf: Jenkins scheiterte beim Git-Zugang. Graphatos Produktions-Kindläufe auf
`48b74126…` starteten dagegen und scheiterten beim Browser-Modelltest. Dieser
suchte einen Svelte-Zweig nur auf oberster Ebene, obwohl die Anwendung inzwischen
Layout-Wrapper besitzt. Die letzte erfolgreiche vollständige Graphato-Abnahme
stammt von einem älteren Commit (`52c5fc44…`). Ein grüner neuerer CI-Hauptlauf
belegt deshalb keine erfolgreiche nachgelagerte Prüfung.

Der separate Graphato-Kandidat `78e92e09…` umfasst zwei nachvollziehbare Commits:
private Postdeploy-Verzeichnisrechte auf frischen Hosts mit Tests gegen Dateien,
Symlinks und falsche Eigentümer; außerdem die Korrektur der Testsuche innerhalb
der Layout-Wrapper. Lokal bestanden Architekturprüfung (25 Tests) und Webtests
(76 erfolgreich, ein unter Windows übersprungener Test); die Linux-Gesamtprüfung
ist noch ausstehend. Der separate Antares-Kandidat `88382cc0…` aktualisiert nur
die vom ursprünglichen Audit beanstandeten Produktionsabhängigkeiten und seine
Dokumentation. Beide Kandidaten sind als unveränderliche Git-Bundles im eigenen
NAS-Quellverzeichnis bereitgestellt. Jenkinsfiles und ihre Gates sind unverändert.
Patches liegen unter `docs/upstream-patches/*-nas-*.patch`. Diese Kandidaten sind
noch keine erfolgreich abgenommenen Release-Stände.

### NAS-Betriebsprüfungen

`followup/nas-lifecycle/state.json` bestätigt auf dem tatsächlichen Teststack:

- Controller-/Runner-Neustart während eines aktiven Jobs ohne erneuten Jobstart;
  alle 75 protokollierten Arbeitsschritte und sein Artefakt bleiben erhalten.
- Ein zweiter Job wartet bei Runner-Kapazität eins und startet erst nach dessen Ende.
- Abbruch beendet auch einen SIGTERM ignorierenden Nachkommen; Cleanup wird ausgeführt.
- Ein hart beendeter Worker wird als Fehler oder Unterbrechung beendet, niemals als Erfolg.

`followup/nas-backup/report.json` dokumentiert eine gemeinsame Offline-Sicherung
von PostgreSQL, Datenvolume und Konfiguration. Wiederherstellung erfolgte in eine
separate Datenbank und ein neues Volume. Alle zehn Tabellen stimmen zeilenweise
über normalisierte Hashes überein: 33 Läufe, 2.577 Ereignisse, 111 Schritte und
15 Pipeline-Definitionen. 19 Artefakte wurden mit Größe/SHA-256, 73 Logs gegen
ihre gespeicherten Byte-Zähler geprüft. Ein temporärer Controller mit dem
wiederhergestellten Datenbestand und den entschlüsselten Zugangsdaten wurde bereit.
Test-Restore-Ressourcen wurden danach entfernt; die Sicherung bleibt im privaten
NAS-Testverzeichnis. Das Konfigurationsarchiv ist verschlüsselt und mit HMAC
versehen; sein Schlüssel liegt separat im lokalen, nicht versionierten Verzeichnis.
Dies ist ein Restore des Teststacks, keine außer Haus gelagerte Produktionssicherung.

Eine weitere UI-Runde nach den Betriebsprüfungen erfasst 59 Desktop-/Mobilansichten
und 66 Parameterwerte. Alle 15 Kontaktbögen wurden visuell geprüft; keine
Seitenfehler oder horizontalen Seitenüberläufe wurden festgestellt
(`visual-followup-ops/report.json`).

Der zusätzliche manuelle Job `leroy-home-lab-build` prüft den zuvor unbetretenen
Build-/Push-Pfad auf Commit `9fb528a1…` mit identischem Diff-Ausgangspunkt
`d7744989…`. Der ausschließlich für diesen Vergleich erzeugte Checkout-Erfolg
setzt die Historienbasis und zählt nicht als Workload-Abnahme. Der tatsächliche
Vergleich ist erfolgreich: Jenkins #1 und Leroy `9204e744…` bauen und veröffentlichen
beide Images. Die Image-IDs unterscheiden sich nach getrennten Builds; verglichen
wurden deshalb Anwendung und Python-Bibliotheken einschließlich Dateimodus und
Eigentümer (599 bzw. 2.326 Einträge), Paketversionen und Laufzeitkonfiguration.
Diese Inhalte stimmen überein. Dateizeiten und generierter Python-Bytecode sind
ausgenommen; eine Byte-Identität der Images wird nicht behauptet. Alle vier
unveränderlichen OCI-Manifeste sind mit Digest-Prüfung aus der Testregistry abrufbar
(`followup/home-lab-build/comparison.json`).

Der erste vollständige Neustart deckte einen Fehler der Testnetz-Konfiguration
auf: Gitea bekam dynamisch die feste Registry-Adresse. Der dynamische Pool ist
jetzt `10.234.98.128/25`; Registry und Gitea verwenden reservierte Adressen außerhalb
dieses Bereichs. Die Namensauflösung des verschachtelten Docker-Daemons wird beim
Start wiederhergestellt. Die Netzwerkreparatur erhält alle Container, Images und
Volumes; das erste fehlgeschlagene Ergebnis bleibt dokumentiert.

Die Wiederholung `nas-stack-restart/attempts/network-reserved` besteht den
vollständigen Stop/Start aller fünf äußeren Dienste einschließlich SSH-Brücke
und beider inneren Dienste. 34 Läufe, 3.195 Ereignisse und 20 Artefakte bleiben
erhalten; beide Image-Digests lassen sich danach abrufen. Der zusätzliche reale
Job `be393be4…` bestätigt Controller, Registry, Gitea, den wiederhergestellten
VM-Tunnel und die Sperre geschützter NAS-/Produktionsendpunkte.

Der begrenzte Paralleltest besteht ebenfalls: zwei Worker arbeiten gleichzeitig
je 60 Sekunden mit 256 MiB Nutzspeicher und CPU-Arbeit, ein dritter wartet auf
einen Platz. Alle drei Läufe sind erfolgreich und ihre Artefakte stimmen mit den
gespeicherten Hashes überein. Kein OOM-Zähler steigt. Anschließend sind Kapazität
eins und die ursprünglichen Runner-Profile bytegenau wiederhergestellt
(`followup/nas-parallel/state.json`). Das belegt diesen begrenzten Lastfall,
keine unbegrenzte Produktionskapazität.

Zwölf weitere Desktop-/Mobilansichten zeigen die tatsächlichen Build-Ergebnisse,
Zeitachsen, Logs und Artefakte des Home-Lab-Builds und des Paralleltests. Alle drei
Kontaktbögen wurden visuell geprüft; beide heruntergeladenen Artefakte stimmen
mit Größe und SHA-256 überein (`visual-followup-results/report.json`).

Vollständige Kandidatensuiten bleiben vor der Produktionsfreigabe offen.

### Antares: Trennung von Speichergrenze und Anwendungsprüfung

Der Sicherheitskandidat `88382cc0…` besteht im Test-Jenkins #2 den produktiven
Audit ohne Befunde sowie Lint und Typprüfung. Die Unit-Suite meldet zehn
Timeouts und einen V8-Heap-Abbruch: 617 Tests bestanden, acht weitere wegen des
Worker-Abbruchs nicht abgeschlossen. Ein separater Diagnoseaufruf desselben
unveränderten Commits mit 3 GiB Container-Speicher und 2 GiB Node-Heap führt alle
635 Tests aus: 626 bestehen, neun überschreiten ihre Zeitbudgets; kein Heap-Abbruch.
Dieser Aufruf zählt nicht als Pipeline-Abnahme. Der JVM-Start überlappte seine
ersten Tests, weshalb daraus kein Laufzeitvergleich abgeleitet wird.

Kandidat `f6f891ce…` enthält zusätzlich die nach Zeilen gruppierte DOM-Darstellung
der Planetenzellen und gezielt 15-/30-Sekunden-Budgets für die betroffenen
funktionalen Großrasterprüfungen. Ihre Assertions bleiben vollständig erhalten;
Coverage-Grenzen, Jenkinsfile und die expliziten Zeitbudgets der Kamera-/
Virtualisierungstests sind unverändert. Die Speicherbudgets werden für Antares
unter beiden CI-Systemen gleich gesetzt. Jenkins #3 beendet alle 635 Tests ohne Speicherabbruch; 633 bestehen. Zwei
Kameratests ueberschreiten ihre bisherigen 5-/10-Sekunden-Budgets. Der separate
Folgekandidat `8f8b50e3...` setzt ausschliesslich diese beiden funktionalen
Testbudgets auf 15/30 Sekunden und korrigiert die Dokumentation; alle Assertions
bleiben erhalten. Der vollstaendige Jenkins-Lauf #4 ist noch offen. Keiner
dieser Zwischenstaende wird als abgeschlossene Workload-Abnahme gewertet.

Jenkins #4 auf `8f8b50e3…` besteht alle 635 Unit-Tests samt Coverage-Gate.
Die vorhandenen Integrationstests umfassen auf diesem Stand 101 Fälle: 97
bestehen, vier scheitern. Produktionsbuild und Browsermatrix werden deshalb
übersprungen. Die Nachweise liegen beim jeweiligen Kandidaten:

- Snapshot-HTTP: 500 statt 422; ein kleiner Probeaufruf im selben Jenkins-Container
  bestätigt, dass Fastifys Injection-Socket keine `setTimeout`-Methode besitzt.
- Gleichzeitiger Spielstart: ein gezielter Wiederholungslauf mit aussagekräftigerer
  Assertion reproduziert PostgreSQL `55P03` beim exklusiven Lock auf `solar_systems`.
  Zwei verschiedene Zielplaneten warten unnötig aufeinander.
- Forschungsfrist: 562 ms tatsächlicher Datenbank-Zeitfortschritt überschreiten
  die feste 500-ms-Toleranz gegenüber der vor den Arbeiten erfassten Uhrzeit.
- NPC-Aufbau: das 30-Sekunden-Testbudget wird überschritten; ein separater Lauf
  mit erweitertem Limit besteht sämtliche Zustands- und Idempotenzprüfungen.

Kandidat `b0210d2e…` korrigiert den optionalen Socket-Aufruf und verwendet eine
geteilte Systemsperre bei weiterhin exklusiv gesperrtem Profil und Zielplaneten.
Der Fristentest begrenzt die unveränderte SQL-Formel mit tatsächlich gemessenen
Datenbankzeiten; der NPC-Test erhält gezielt 60 Sekunden. Die ursprünglichen
Fehler bleiben erhalten. Die fokussierte Vorprüfung besteht Lint, Typen und alle
18 Tests der vier betroffenen Integrationsdateien; insbesondere beide parallelen
Spielstarts sind erfolgreich. Jenkins #5 prüft jetzt die vollständige Pipeline.
Keine der Diagnosen zählt als Pipeline-Erfolg.

Jenkins #5 auf `b0210d2e…` endet bereits in der Unit-Suite mit 634 erfolgreichen
Tests und einer weiteren 5-Sekunden-Überschreitung im Kamera-Frame-Test.
`096f6e8c…` gibt den aufwendigen Kamera-Szenarien gezielte 15-/30-Sekunden-Budgets
und der Mehrfachstart-Prüfung 60 Sekunden (zuletzt 29,9 von 30 Sekunden).
Assertions und Jenkinsfile bleiben gleich; die vollständige Prüfung dieses
Folgekandidaten ist noch offen.

Jenkins #6 auf `096f6e8c…` besteht alle 635 Unit- und 101 Integrationstests sowie
den Anwendungsbuild. Die Compose-Konfigurationsprüfung scheitert danach, weil
der Standard-Docker-CLI kein Compose-Plugin findet. Eine ausschließlich lesende
Prüfung bestätigt dieselbe fehlende Standardkonfiguration im produktiven Jenkins;
Graphato verwendet dort einen eigenen Werkzeugpfad. Dies ist ein Werkzeugproblem
der Antares-Ausführungsumgebung, kein weiterer Anwendungsfehler.

Für den erneuten Vergleich wird das bereits inventarisierte Compose-Binary
Version 5.5.1 beiden Antares-Umgebungen bereitgestellt: im Test-Jenkins über den
globalen Plugin-Suchpfad, in Leroy über einen schreibgeschützten Profil-Mount.
Jenkinsfile, Anwendungscode und Produktions-Jenkins bleiben unverändert. Der
fehlgeschlagene Lauf #6 bleibt mit eigener Logdatei und Wiederholungsgrund erhalten.

Jenkins #7 auf demselben `096f6e8c…` besteht erneut alle 635 Unit- und
101 Integrationstests, den Anwendungsbuild und die Compose-Prüfung. Beim
Image-Build überschreitet er jedoch das unveränderte Gesamtlimit von 30 Minuten.
`npm prune --omit=dev --ignore-scripts` arbeitet zu diesem Zeitpunkt bereits rund
acht Minuten an den Entwicklungs-Abhängigkeiten einer früheren Docker-Schicht.
Die gesicherten Prozessdaten zeigen steigende Schreibmengen und Threads in
`do_renameat2` beziehungsweise `write_all_supers`; die Browsermatrix wurde nicht
gestartet. Ergebnis: `ABORTED`, kein vollständiger Erfolg.

Der separate Commit `23ec36f…` installiert die Produktions-Abhängigkeiten direkt
mit `npm ci --omit=dev` in einer eigenen Docker-Stufe aus derselben Lockdatei.
Native Installationsskripte bleiben aktiviert. Er vermeidet dadurch das teure
nachträgliche Entfernen aus einer bestehenden Schicht. Dies ist eine gezielte
Build-Optimierung nach einem unter Jenkins beobachteten NAS-Zeitabbruch; sie
wird nicht als spezifische Voraussetzung für Leroy ausgegeben. Die fokussierte
Image-Prüfung besteht: 147 installierte Pakete stimmen mit der Lockdatei überein,
alle direkten Produktionspakete sind vorhanden, TypeScript/Vite/Vitest fehlen
im Laufzeitimage, und Argon2-Hash/Verifikation sowie eine echte Fastify-Anfrage
funktionieren als UID 1000. Der Build benötigt dabei 386 Sekunden unter
Wiederverwendung vorhandener Abhängigkeits-Schichten; dies ist kein Kaltstart-
Leistungsvergleich. Beide vollständigen Pipelines stehen noch aus.

Eine separate Browser-Diagnose auf `096f6e8c…` wird nach drei reproduzierten
Zeitüberschreitungen angehalten. Der ursprüngliche 30-Sekunden-Rahmen bleibt
unverändert. Im gesicherten Chromium-Trace benötigt der Anmeldeklick rund
27 Sekunden; mehrere Render-/Eingabeschritte warten jeweils mehrere Sekunden.
Der tatsächliche Grafikprozess verwendet `--use-angle=swiftshader-webgl` und
meldet wiederholt GPU-Stalls beim Auslesen des Bildes. Login und Bootstrap
antworten dagegen in rund 2,35 beziehungsweise 1,38 Sekunden.

Der separate Commit `8fdbbee…` aktiviert für erkannte Software-Renderer den
bereits vorhandenen statischen Login-Hintergrund. Nur der dekorative Shader
wird ausgelassen; Spielgrafik, Browser-Projekte, Assertions und Zeitlimits werden
nicht geändert. Die Gegenprüfung dieses Kandidaten steht noch aus. Traces,
Screenshot, Prozessparameter und der ausdrückliche Abbruchgrund der partiellen
Diagnose sind beim vorherigen Kandidaten gespeichert. Diese Diagnose ist kein
vollständiger CI-Erfolg.

Die Diagnose des ersten Grafik-Fallbacks `8fdbbee…` verwirft dessen vollständigen
Verzicht auf das Canvas: Die unveränderten Login-Tests erwarten ein sichtbares
Sternfeld. Der Trace belegt gleichzeitig die Entlastung der Eingabe von rund
27 Sekunden auf 133 Millisekunden. `4837546…` bewahrt deshalb denselben Shader
und ein sichtbares Canvas, begrenzt Software-Rendering jedoch auf einen
unbewegten Frame mit höchstens 131.072 Pixeln. Eine Größenänderung zeichnet den
Frame erneut; Hardware-Rendering und Spielgrafik behalten ihr Verhalten. Auch
dieser Folgeversuch muss erst die bestehenden Browser-Prüfungen bestehen.

Am 4. Oktober wird eine wesentliche Abweichung der bisherigen Zeitmessungen
festgestellt: Produktions-Jenkins hat keine CPU-Grenze, der gesamte isolierte
Docker-Daemon war dagegen gemeinsam auf zwei Kerne begrenzt. Der Test-Daemon
und beide Antares-Ausführungen erhalten nun sechs Kerne, entsprechend der
verfügbaren NAS-CPU. Die Speichergrenzen bleiben bestehen (3,5 GiB für den
Test-Daemon, 3 GiB je Antares-Job, 2 GiB Node-Heap). Auch das IO-Gewicht ist
weiterhin verschieden. Es wird daher keine vollständige Ressourcenidentität
behauptet. `followup/antares-cpu/applied.json` dokumentiert die Werte und die
Wiederherstellung nach einer zunächst fehlerhaften IO-Assertion. Frühere
Zeitüberschreitungen unter zwei gemeinsamen Kernen belegen ausdrücklich keine
notwendigen Anwendungsänderungen für einen produktiven Wechsel zu Leroy.

Der Browser-Diagnoselauf auf `4837546…` endet nach 20 Minuten ohne vollständigen
Erfolg. Anmelde- und mehrere Spielprüfungen bestehen; unter anderem bleiben
Navigation, Onboarding, WebKit und Administrator-Prüfungen offen. Traces und
Screenshots bleiben erhalten. Während der Wiederherstellung warten bis zu
17 Lesesperren länger als zwölf Minuten, obwohl die Datenbanksitzungen weitgehend
inaktiv sind. Eine gezielt gesteuerte TCP-Gegenprobe reproduziert unabhängig
von Browser-Geschwindigkeit einen Fehler: Trennt sich der Client während der
Sperrenerfassung, bleibt eine Lesesperre zurück und der Handler wird trotzdem
aufgerufen. `e4e4793…` gibt in diesem Fall die Sperre frei und beendet die
Anfrage; ein zusätzlicher PostgreSQL-Integrationstest deckt das Rennen ab.
Dieser Kandidat wird zunächst mit sechs Kernen und den unveränderten
Browser-Zeitbudgets geprüft. Der separate Versuch `bc887b8…` mit angepassten
Testabläufen bleibt erhalten, wird aber in dieser Gegenprobe nicht verwendet.

Die Gegenprobe `six-cpu-reader-fix` auf `e4e4793…` endet ebenfalls nach dem
diagnostischen Limit von 20 Minuten; zuletzt läuft die WebKit-Oberflächenprüfung
im Wiederholungsversuch. Sie ist kein vollständiger Pipeline-Erfolg. Die
gespeicherten Ressourcenproben zeigen während des Laufs keine zusätzlichen
CPU-Drosselungen und keine Treffer der Speichergrenze, jedoch deutliche
IO-Wartezeiten. In allen erfassten Zwischenständen stehen null Lesesperren.
Die gezielt gesteuerte TCP-Prüfung bestätigt anschließend null verbliebene
Sperren und null Handler-Aufrufe; auf dem Vorgänger waren beide Werte eins.

Der Administrator-Test erreicht nun die erfolgreiche Wiederherstellung, scheitert
aber später an der Löschbestätigung des Test-Spielstands. Weitere Fehler betreffen
Animationen, lange Bedienfolgen, Onboarding und bei Fehlern zurückbleibende
gemeinsame Testdaten. Chromium-, Low-DPR- und Firefox-Oberflächenprüfungen
werden durchlaufen; WebKit überschreitet sein Budget beim Screenshot.
Die fehlende abschließende Testzusammenfassung wird nicht durch errechnete
Erfolgszahlen ersetzt. 41 Fehlerdateien sind indiziert, davon 32 lokal gesichert.

Im Arena-Wiederholungsversuch zeigt sich zusätzlich eine konkrete falsche
Trennergeometrie: Der Fortschritt steht bereits auf eins, obwohl Runde null
gerade beginnt. Ein gezielter Unit-Test mit zwei Minuten Seitenlaufzeit
reproduziert den Fehler unabhängig von der NAS-Leistung. Die getrennte Korrektur
initialisiert die monotone Uhr beim Einblenden und verwendet einen gemeinsamen
Zustand für Metadaten und Geometrie. Danach bestehen alle 29 Arena-Unit-Tests,
die betroffene Lint-Prüfung und die vollständige Typprüfung. Die umfassende
NAS-Browser- und Pipeline-Abnahme dieser Korrektur bleibt offen.

Die HTTP-Traces von `e4e4793…` belegen außerdem: Snapshot-Erstellung antwortet
mit HTTP 201 nach 33,7 Sekunden, Wiederherstellung mit HTTP 200 nach 59,4
Sekunden, Löschen mit HTTP 204 nach 7,1 Sekunden. Der Folgekandidat
`a81afb1…` wartet bei Spielstart und Löschen ausdrücklich auf die erfolgreiche,
vollständig empfangene Antwort und prüft anschließend dieselben UI-Zustände.
Er verändert keine Browser-Zeitbudgets. Die betroffenen Lint- und Typprüfungen
bestehen; die Browser-Gegenprüfung ist noch offen.

Der Graphato-Kandidat `78e92e0…` besteht am 4. Oktober die Host-Einrichtung
unter Test-Jenkins #2 auf dem zuvor zurückgesetzten Ziel. Der vollständige
Release-Vergleich einschließlich der 21 Web- und acht Qualitätsprüfungen
steht weiter aus; ein erfolgreicher Bootstrap allein erfüllt diese Abnahme nicht.

Die lokale Linux-Gegenprobe von `a81afb1…` besteht 25 Browserprüfungen bei
drei vorgesehenen Auslassungen. Die verbleibende Administrator-Prüfung hängt
an dem neu eingeführten `response.finished()` für eine leere HTTP-204-Antwort.
`9f05b7f…` entfernt dieses Warten und behält sowohl die Prüfung auf HTTP 204
als auch die sichtbare Löschbestätigung bei. Danach bestehen die beiden
betroffenen Administrator-Prüfungen. Dies ist eine fokussierte lokale Diagnose;
der vollständige NAS-Vergleich dieses Kandidaten ist noch offen.

Eine zusätzliche lokale Gegenprobe verwendet unverändert den NAS-Diagnosestand
`e4e4793…` und dasselbe Playwright-Image. Lokal gilt eine Containergrenze von
3 GiB; auf dem NAS ist dagegen der gesamte Test-Daemon auf 3,5 GiB begrenzt,
während der Browsercontainer keine eigene Grenze hat. Dies ist daher ein
Standortvergleich der Quellen, kein identischer Ressourcenvergleich. Er besteht
25 Prüfungen bei drei Auslassungen. Nur die WebKit-Oberflächenprüfung scheitert:
Zwei Docker-OOM-Ereignisse im exakten Testcontainer belegen Speichermangel zum
Zeitpunkt des Absturzes und des Wiederholungsversuchs. Die Ereignisse bleiben
als `local-linux-browsers-nas-source-control-oom.json` erhalten. Daraus wird kein
zusätzlicher Anwendungsfehler abgeleitet. Der Diagnosehelfer erfasst solche
Ereignisse künftig vor dem Entfernen seiner Testcontainer.

Graphato `78e92e0…` besteht außerdem Test-Jenkins CI #2 einschließlich beider
Release-Pakete und der Auslieferung an das isolierte Ziel. Nach erneutem Ausfall
des NAS-Verwaltungsports 22 läuft die Beobachtung über einen manuellen
Leroy-Diagnosejob weiter. Dieser liest ausschließlich den fest gebundenen
Test-Jenkins-Container und sichert dessen Ergebnisse. Die nachgelagerten
Anwendungssuiten und die Gegenprüfung unter Leroy sind noch nicht abgeschlossen.

Die Jenkins-Websuite #2 auf `78e92e0…` besteht anschließend vollständig:
21 von 21 Gruppen, einschließlich fünf Minuten mit vier Browser-Tabs und
120 Prompts, ohne wiederverwendete Prüfungen. Die Zielquittung bestätigt die
abgeschlossene Bereinigung. In der Qualitätsphase bestehen bislang Frontend und
Deployment (einschließlich 65 Browser-Komponentenprüfungen), Rustfmt, Clippy
und die Servertests (1.527 bestanden, 29 deklarierte Auslassungen, keine Fehler).
Auch Entwicklungsprofile, Entwicklungs-Repositories, Reset und Host-Laufzeit
bestehen anschließend. Jenkins meldet für CI #2, beide Postdeploy-Jobs #2 und
Release-Abnahme #2 jeweils `SUCCESS`. Beide archivierten Suite-Quittungen
enthalten ausschließlich frisch ausgeführte Prüfungen und bestätigte Bereinigung.
Der Zielstatus lautet `verified`; HTTP und HTTPS antworten erfolgreich, alle
vier Anwendungscontainer sind gesund. Das veröffentlichte Windows-Paket,
seine Prüfsumme, CRC, Build-Identität und der aktuelle Paketverweis wurden über
einen ausschließlich lesenden Leroy-Diagnosejob geprüft. Die anschließende
frische Wiederholung unter Leroy bleibt für einen vollständigen Vergleich erforderlich.

Nach Sicherung des Jenkins-Zielzustands im Snapshot
`before-graphato-leroy-78e92e09fa5f` wird derselbe Ausgangssnapshot wiederhergestellt.
Leroys Bootstrap `64722a5c…` besteht auf diesem frischen Ziel; CI `cf28fcde…`
läuft anschließend mit demselben Graphato-Commit. Paketsicherung, Quittungsprüfung
und das Anhalten ausschließlich der eigenen Test-Jenkins-Instanz funktionieren
dabei über die Leroy-API, obwohl NAS-Port 22 weiterhin geschlossen ist.

In der frei gewordenen lokalen Linux-Umgebung besteht Antares `9f05b7f…`
anschließend die vollständige Browsermatrix mit 4 GiB: 26 bestanden, drei
vorgesehene Auslassungen, keine Fehler, keine Docker-OOM-Ereignisse; einschließlich
Vorbereitung dauert die Diagnose 343 Sekunden. Quellen, Browserimage und
unveränderte Browser-Zeitbudgets sind im Bericht festgehalten. Diese Diagnose
ersetzt weder die vollständigen CI-Gates noch den NAS-Vergleich beider Engines.

Leroys Graphato-CI `cf28fcde…` schließt anschließend alle zehn Schritte
erfolgreich ab, einschließlich Auslieferung und Windows-Veröffentlichung.
Die frischen Anwendungssuiten laufen über die tatsächliche Eltern-Kind-Kette.
Zwölf zusätzliche Desktop- und Mobilaufnahmen zeigen den abgeschlossenen
CI-Lauf, die auf den Unterjob wartende Abnahme und die laufende Websuite,
jeweils als Graph und Zeitachse. Die Ansichten wurden visuell geprüft;
Statusdarstellung, Revision, Konsole und Verknüpfungen sind nachvollziehbar,
ohne Seitenüberlauf oder JavaScript-Fehler. Der Screenshot-Helfer wählt beim
Ansichtswechsel nun ausdrücklich den Graphen, da die Anwendung die zuletzt
gewählte Zeitachsenansicht korrekt beibehält. Die abschließende Prüfung der
Ergebnisse und Artefakte erfolgt erst nach Abschluss beider Anwendungssuiten.

Die automatische Runner-Bereinigung wird ebenfalls auf eindeutig mit der
Laufkennung markierte Hilfscontainer erweitert. Nach Bestätigung des endgültigen
Status durch den Controller wird zuerst der Worker angehalten; sein Container
bleibt bis zur erfolgreichen Hilfsbereinigung als Wiederholungsanker erhalten.
Ein lokaler Docker-Test bestätigt entfernte Worker, Hilfscontainer und anonyme
Volumes sowie erhaltene benannte Hilfsvolumes und fremde Container. Die NAS-Prüfung
besteht ebenfalls: `2b7c7328a2ce4045928b5f89e7213912` wird als absichtlicher
Worker-Absturz korrekt `failed`; Worker, Hilfscontainer, anonymes Datenvolume
und Arbeitsvolume werden anschließend automatisch entfernt. Der Runner verwendet
seit 01:29 UTC das geprüfte Image `sha256:a8bec2e958bc488d050ed409228bb29478471a8898caabff4b8867d9f057e410`.
Produktionscontainer wurden nicht geändert.

Die fokussierte Antares-Diagnose `tmpfs-auth-smoke` verwendet unverändert
`8607cfd438c7`, eine frische, auf 512 MiB begrenzte temporäre RAM-Datenbank und
aktivierte PostgreSQL-Einstellungen `fsync`, `full_page_writes`,
`synchronous_commit`. Drei der vier ausgewählten Chromium-Prüfungen bestehen;
der authentifizierte UI-Test scheitert weiterhin zweimal an der zweisekündigen
Kamera-Animationsgrenze. Die Diagnose dauert einschließlich Schemavorbereitung
107 Sekunden und zählt nicht als vollständige Pipeline-Abnahme. Fehlerartefakte
sind unter `browser-failures-tmpfs-auth-smoke` gesichert. Dies widerlegt eine
ausschließliche Erklärung aller Browserfehler durch Datenbank-I/O.

Die anschließend identisch ausgewählte Diagnose `disk-auth-smoke` mit frischer
Datenbank auf dem bisherigen Plattenspeicher besteht ebenfalls drei Prüfungen.
Der authentifizierte UI-Test erreicht in beiden Versuchen seine 30-Sekunden-Grenze. Die Diagnose dauert
166 Sekunden einschließlich Schemavorbereitung. Beide Versuche verwenden dieselben
vier Tests, denselben Commit und unveränderte Testfristen. Die Einzelmessungen
liefern keinen belastbaren Leistungsbenchmark; sie zeigen verbleibende Browser-
Zeitprobleme auch mit RAM-Datenbank. Die Fehlerdateien beider Diagnosen sind
getrennt gesichert.

Die Netzwerkdaten der fokussierten Browser-Traces ergänzen die I/O-Stichprobe:
Mit RAM-Datenbank liegt der Login in diesen Versuchen bei 0,32 beziehungsweise
0,58 Sekunden; mit Plattenspeicher bei 2,14 beziehungsweise 2,27 Sekunden.
Weitere Spielanfragen erreichen mit Plattenspeicher rund 3,4 Sekunden. Die
Kamera-Fehler mit RAM-Datenbank bleiben davon unabhängig bestehen.
Die Rohdaten sind in `focused-browser-storage-network.json` festgehalten.
Die Kamera-Instrumentierung auf `8607cfd438c7` mit RAM-Datenbank reproduziert
eine 3,14 Sekunden dauernde Kamerafahrt mit nur fünf Bild-Callbacks, obwohl die
Animation 720 Millisekunden vorsieht. Der erste Versuch scheitert an der
Zwei-Sekunden-Assertion, der zweite später am 30-Sekunden-Testlimit. Die Messung
verändert weder Assertions noch Bild-Zeitstempel.

Die gesonderte Auswertung `recorded-callback-gap-analysis.json` zeigt zwischen
zwei beobachteten Callbacks 3,04 Sekunden verstrichene Zeit; auch deren
Bild-Zeitstempel rücken um 2,77 Sekunden vor. Im Wiederholungsversuch beträgt
die Lücke 2,81 Sekunden. Beide Zeitmessungen zeigen lange Callback-Pausen.
Allein die Animations-Zeitquelle zu ändern würde diese Pausen nicht beseitigen;
deren Ursache bleibt mit diesen Messungen ungeklärt. Anwendungscode bleibt
für die folgende Speicherdiagnose unverändert.

Die ergänzende Chromium-CPU-Aufzeichnung weist keinen einzelnen dominierenden
JavaScript-Aufruf als Ursache nach. Im ersten Versuch entfallen etwa 8,1 von
10,6 Sekunden auf als `idle` markierte CPU-Samples; gemessene Skriptausführung
liegt bei 0,76 Sekunden. Eine begleitende NAS-Stichprobe zeigt deutliche
I/O-Wartezeiten, aber keinen OOM-Abbruch. Dies ist eine Eingrenzung, kein
Nachweis einer vollständigen Ursache. `auth-cpu-summary.json`,
`auth-cpu-pressure.json` und die Rohprofile bleiben erhalten.

Der anschließende Versuch `tmpfs-browser-auth` verlagert zusätzlich nur `/tmp`
des Browsercontainers in 1 GiB begrenztes RAM. Er besteht zwei Tests und scheitert
beim Laden des Universums. Sein Container läuft von 07:56:21 bis 08:03:43 UTC;
der produktive Graphato-Build #17 läuft seit 07:53:17 UTC. Diese Probe ist deshalb
ausdrücklich kein belastbarer Vergleich der Speicheroptionen. Nach Unterbrechung
des lokalen Beobachters wurden Ergebnis und Prüfsummen vom beendeten Container
nachgelesen und ausschließlich die beiden zugehörigen Diagnosecontainer entfernt.
Die vorangehenden CPU-Profile liegen nach Umrechnung der monotonen NAS-Zeit etwa
zwischen 07:52:12 und 07:53:00 UTC, also vor Build #17; die Umrechnung enthält
keine separate Prüfung auf zwischenzeitliche Uhrsprünge.
Künftige Browserproben warten wie die vollständigen Vergleiche auf die produktive
CI und zeichnen deren Buildnummer vor und nach dem Test sowie die Testzeitspanne
auf. Produktionsjobs werden weder angehalten noch verändert.

### Antares: ruhiger NAS-Vergleich des Artefaktspeichers am 5. Oktober

Die ursprünglichen drei Chromium-Authentifizierungstests bestehen sowohl mit
Traces/Videos in begrenztem RAM (`ram-trace-auth`, 117,0 Sekunden Containerlaufzeit)
als auch mit deren Speicherung auf Festplatte (`disk-trace-auth`, 87,8 Sekunden).
Beide Proben verwenden unverändert `8607cfd438c7`, eine frische temporäre
PostgreSQL-Datenbank mit `fsync`, `full_page_writes` und `synchronous_commit`
aktiviert sowie Browser-`/tmp` im RAM. Alle 13 Produktionsjobs sind vor und nach
beiden Proben inaktiv und haben identische Buildnummern und Ergebnisse.
Beide Diagnosecontainer sind jeweils vollständig entfernt.

Diese zwei fokussierten Proben bestätigen weder einen Geschwindigkeitsvorteil
noch eine alleinige Ursache im Artefaktspeicher. Sie ersetzen die vollständige
CI-Abnahme nicht. Der folgende Versuch `tmpfs-full-matrix` prüft deshalb die
gesamte ursprüngliche Browsermatrix mit RAM-Datenbank und Browser-`/tmp`,
aber der bisherigen Speicherung der Artefakte. Er besteht 20 Tests und die drei
vorgesehenen Auslassungen; sechs Admin-Prüfungen scheitern. Die Datenbanklogs
belegen um 14:29:40 UTC `PANIC: could not write to file pg_wal/xlogtemp.178:
No space left on device`. Der Snapshot überschreitet die 512-MiB-Kapazität;
PostgreSQL bricht den Backend-Prozess ab und stellt sich wieder her, während
die Webserver nach getrennten Verbindungen enden. Es gibt keine OOM-Ereignisse.
Der Originalfehler und 36 Fehlerartefakte mit Prüfsummen bleiben erhalten
(26 einschließlich ausgewählter Traces lokal kopiert). Die Sammlung kann nun
auch lange Windows-Pfade verwenden; Traversal, Laufwerks- und Datenstrompfade
werden vor der Pfaderweiterung abgewiesen.

`full-matrix-1g` wiederholt ausdrücklich nur diese Diagnose mit 1 GiB
Datenbankkapazität. PostgreSQL-Dauerhaftigkeit, Originaltests, ein Retry und
Zeitgrenzen bleiben erhalten. Er endet mit 24 bestanden, drei vorgesehenen
Auslassungen und zwei Fehlern: Die Angriffsphase wechselt während der
Screenshot-Aufnahme; WebKit stürzt in der Planetendarstellung ab. Drei Docker-
OOM-Ereignisse sind eindeutig dem Browsercontainer zugeordnet; der eigene
Daemon meldet zwei zusätzliche OOM-Kills. Beide Diagnosecontainer sind entfernt,
alle Produktions-Buildnummern unverändert und zehn Fehlerartefakte gesichert.

Erst dieser belegte Speichermangel begründet eine zusätzliche RAM-Grenze für
den ausschließlich eigenen Test-Daemon: 4,5 statt 3,5 GiB; Gesamt-RAM+Swap
bleibt 6 GiB, CPU bleibt sechs. Vorher waren rund 2,9 GiB Hostspeicher verfügbar.
Die Änderung erfolgt ohne Neustart und bei inaktiven Test-/Produktionsjobs;
Nachweis `headroom-applied.json`. `arena-ram-headroom` untersucht danach
gezielt den ursprünglichen Arena-Test mit Screenshot-Dateien im Browser-RAM.
Anwendung, Assertions und Zeitgrenzen sind weiterhin unverändert. Auch diese
Probe scheitert in beiden vorgesehenen Versuchen an der Angriffsphase
(in Runde sechs beziehungsweise fünf), ohne neue OOM-Ereignisse. Sechs
Fehlerartefakte sind gesichert. Mehr RAM und die Speicherung der Bilder im RAM
beheben diesen Fehler damit nicht vollständig.

Der anschließende vollständige Vergleich beider Engines bleibt deshalb
ausdrücklich diagnostisch: derselbe Quellstand, dieselbe temporäre Docker-
Speicherkonfiguration, dieselben Assertions und Fristen. Auch ein identischer
Fehler ist keine bestandene CI-Abnahme.

Eine optionale gemeinsame Docker-Konfiguration für temporäre Antares-
Hilfscontainer ist vorbereitet und besteht 13 gezielte Prüfungen. Sie ist
für einen ausdrücklich begründeten diagnostischen Vergleich vorgesehen. Ohne
`--diagnostic-only-reason` verlangt der Konfigurationsbefehl eine vollständig
erfolgreiche Browsermatrix. Die diagnostische Ausnahme verlangt die erhaltene
fehlgeschlagene Gesamtmatrix, den isolierten Arena-Nachweis, bestätigte
Bereinigung und unveränderte Produktionshistorie. In keinem Fall setzt der
Befehl eine vollständige CI-Abnahme auf erfolgreich.
Die vollständigen Messwerte stehen in `trace-storage-pair.json`; eine sofortige
Nachprüfung während der automatischen Containerentfernung und deren spätere
Bestätigung sind separat in `ram-trace-auth-cleanup-recovery.json` erhalten.

Die gemeinsame temporäre Speicherkonfiguration ist inzwischen ausschließlich
im eigenen Test-Jenkins und im Antares-Runnerprofil eingerichtet. Jeweils ein
echter Datenbankschreib-/Leseversuch bestätigt 1-GiB-Tmpfs, keine anonymen
Datenbankvolumes, aktivierte Dauerhaftigkeit und vollständige Entfernung.
Docker-Version, Images, Abhängigkeiten und übrige Runnerprofile sind unverändert.
Die 13 lokalen Policy-Prüfungen decken außerdem fremde Container und unveränderte
Build-/Compose-/Exec-Aufrufe ab. `tmpfs-policy-applied.json` enthält die
Prüfsummen und den ausdrücklich diagnostischen Anlass. Der ursprüngliche
Jenkins #11-/Leroy #72-Vergleich liegt mit Manifest in `attempts/without-tmpfs`.
Jenkins #12 besteht anschließend alle 636 Unit-Tests, scheitert aber während
der Integration am vollen 1-GiB-Dateisystem (`could not extend file`,
`No space left on device`). Ergebnis: ein fehlgeschlagener, 66 bestandene und
35 übersprungene Integrationstests; Build und Browser werden nicht ausgeführt.
Das ist eine Kapazitätsgrenze dieser diagnostischen Datenbankkonfiguration.
Die frühere Disk-Ausführung #11 bestand alle 102 Integrationstests.

Die Leroy-Vorprüfung stoppt vor dem eigentlichen Pipeline-Start, weil ihr
wiederverwendeter Diagnosebeleg noch ein älteres Job-Image enthält. Das aktuell
installierte Image ist unverändert korrekt. Diagnosebelege werden nun gegen
Programm, Profil, Zeitlimit und Artefakte geprüft; die Vorprüfung erhält einen
eindeutigen Namen mit der tatsächlichen Jenkins-Buildnummer. Fünf Regressionen
decken gültige Wiederaufnahme und vier Arten veralteter Definitionen ab.

Die korrigierte temporäre Speicherregel belässt PostgreSQL auf Disk und verlagert
nur Browser-Temporärdateien nach `/tmp`. Sie besteht weiterhin 13 Prüfungen.
Jenkins #12 und die vorige Policy werden unter `attempts/database-tmpfs-1g`
erhalten; eine Wiederholung mit mehr Datenbank-RAM erfolgt nicht. Die komplette
unveränderte Browsermatrix wird auf Disk und mit dem begrenzten 4,5-GiB-Daemon
separat diagnostisch ausgeführt. Diese Prüfungen sind keine vollständige Abnahme.

Der zusätzliche Antares-Testtreiber-Kandidat `6f28a5d84311` ändert ausschließlich
die Arena-Aufnahme und deren Dokumentation. Während Zustands-/Geometrieprüfung
und PNG-Erzeugung pausiert die JavaScript-Uhr; danach laufen die Timer auch bei
Fehlern weiter. Die ursprünglichen Assertions und Fristen, Server-SSE,
CSS-Animationen und Anwendungscode bleiben erhalten. Lint, Typprüfung und eine
lokale echte Browserprobe mit langsamer Aufnahme, zusätzlicher Protokolllatenz
und absichtlichem Aufnahmefehler bestehen. Die vollständige lokale Linux-Matrix
endet mit 25 bestanden, drei vorgesehenen Auslassungen und einem Fehler im
Bestätigungsdialog. Der Arena-Test besteht im ersten Versuch.

Für dessen lokale Prüfung wurde die inzwischen vollständig abgenommene
Graphato-Test-VM nach bestätigten vier gesunden Diensten geordnet heruntergefahren:
`forced=false`, QEMU-Exitcode 0. Der VM-Datenträger und alle Abnahmebelege bleiben
erhalten. Dies ist eine Freigabe lokaler Testressourcen und kein Produktionsvorgang.

Der getrennte Anwendungskandidat `58da3ef5d112` behebt das wiederholte Öffnen
des Bestätigungsdialogs bei neuen Callback-Referenzen. Eine gezielte Regression
zeigt vorher sechs Öffnungen bei fünf Neurenderings, danach eine Öffnung und
korrekte aktuelle Eventhandler. Die vollständige lokale Linux-Browsermatrix
besteht anschließend mit 26 bestanden, drei ursprünglichen Auslassungen und
ohne Retry. Alle 637 Unit-Tests einschließlich Coverage bestehen unter sechs
CPUs und 4 GiB RAM. Die Kontrollprobe mit sechs CPUs und 3 GiB wird wegen OOM
als fehlgeschlagen erhalten. Diese lokalen Nachweise ersetzen keinen NAS-Lauf.
Der unveränderte Jenkinsfile und die Abhängigkeiten bleiben erhalten; der
Kandidat ist ausschließlich im isolierten NAS-Gitea bereitgestellt.

Die vorherige Disk-Matrix von `8607cfd438c7` wird nach belegtem Speicher-/I/O-Stall
gezielt per SIGTERM beendet. Der exakte eigene Container-Init wird vorher über
Cgroup, Prozessstartzeit und Command-SHA verifiziert. Kein Produktionsprozess
wird signalisiert. Alle 24 Fehlerartefakte einschließlich Traces sind lokal mit
SHA-256 gesichert; eine fehlende Gesamtzusammenfassung bleibt als unvollständig
markiert. Beide Diagnosecontainer sind entfernt, die Produktionshistorie bleibt
unverändert. Diese Matrix ist keine vollständige CI-Abnahme.

Danach begrenzt der eigene Test-Daemon RAM und gesamten RAM+Swap auf jeweils
4,5 GiB bei sechs CPUs; zusätzlicher Swap ist deaktiviert. Bereits vorhandene
Swap-Seiten werden separat ausgewiesen. Das Antares-Jobprofil erhält nach der
belegten lokalen Kontrolle 4 GiB und sechs CPUs, mit 2-GiB-Node-Heap. Derselbe
Jobrahmen ist für den nächsten Jenkins-Vergleich vorgesehen. Der Jenkins-JVM-
Heap bleibt auf 512 MiB begrenzt; übrige Profile und Produktionscontainer bleiben
unverändert. PostgreSQL verwendet weiterhin Disk, nur Browser-Temporärdateien
liegen im begrenzten RAM-Dateisystem. Die 22 gezielten Harness-Prüfungen bestehen.
Die fokussierte NAS-Probe von `58da3ef5d112` beginnt nach dem Ende aller
produktiven Jenkins-Jobs. Arena scheitert vor der ersten Aufnahme beziehungsweise
bei der abschließenden mobilen Prüfung, weil echte Backend-Runden während der
Bildschirmaufnahmen weiterlaufen. WebKit erzeugt danach erneut starken Speicher-
und I/O-Druck. Nach 900 Sekunden wird die Probe als fehlgeschlagen und
unvollständig erhalten. Der exakt verifizierte eigene Init-Prozess wird per
SIGTERM beendet, ohne erzwungenen Abbruch oder Signal an Produktionsprozesse.
Alle sechs vorhandenen Fehlerartefakte einschließlich beider Arena-Traces sind
lokal mit SHA-256 geprüft. Danach sind beide Diagnosecontainer entfernt und
alle 13 Produktions-Buildnummern und Ergebnisse unverändert.

Der NAS-Test-Daemon wird ohne Neustart auf 3 GiB RAM und gesamten RAM+Swap
begrenzt. Das schwere Antares-Profil wird aus diesem Worker entfernt; übrige
Profile bleiben gleich. Die Nachweise stehen unter
`focused-browsers-capture-dialog-safe-{pressure,termination,recovery}.json`.
Auch ein ausgeschlossener zusätzlicher Swap verhindert auf diesem NAS den
Speicherdruck großer Browserprozesse nicht.

Ein eigener Linux-Ausführungspool in Docker Desktop übernimmt deshalb die
Antares-Vergleiche beider CI-Systeme; Leroys Controller bleibt auf dem NAS.
Dieser Pool verwendet die exakten Images, Jenkins-Plugins, CLI-Werkzeuge und
eingefrorenen Repository-Objekte des bisherigen Teststacks. Seine eigenen
Netzregeln erlauben auf dem NAS ausschließlich den Testcontroller auf Port 8088.
Diese verteilte Ausführung ist separat von einer vollständigen Ausführung auf
der NAS-Hardware zu bewerten. Der eingefrorene Antares-Kandidat besteht anschließend
den vollständigen Vergleich: Test-Jenkins #1 und Leroy #88
(`3afb3b4f534448779cfa7dca15593147`) bestehen jeweils 637 Unit- und
102 Integrationstests, Coverage, Audit, Lint, Typprüfung und Produktionsimagebau.
Die unveränderte Browsermatrix besteht unter beiden Engines mit 26 bestandenen
Prüfungen, drei ursprünglichen Auslassungen und ohne Wiederholung. Alle neun
Leroy-Schritte sind erfolgreich. Beide Engines verwenden dieselben Assertions
und Fristen dieses Kandidaten; Pipeline-/Browserkonfiguration und Jenkinsfile-Bytes
sind gegenüber der Originalbasis unverändert. Beide Engines verwenden dieselben
Werkzeugversionen und Service-Images sowie 4 GiB/sechs CPUs und einen 2-GiB-Node-Heap.

Die Einrichtungskorrekturen bleiben getrennt erhalten: falsche Eigentümerschaft
des neuen Jenkins-Testvolumes wurde vor dem ersten Build korrigiert; der private
Docker-Desktop-DNS-Resolver wurde für Port 53 freigegeben, bevor die Teststufen
begannen. Fehlgeschlagene Vorprüfungen und Archivübertragungen zählen nicht als
CI-Erfolg und werden nicht überschrieben. Der Git-HTTP-Dienst ist ein schreibgeschütztes
Fixture mit eingefrorenen Repository-Objekten; er ersetzt keine Gitea-Funktionsprüfung.

Die Abschlussprüfung bestätigt 110 heruntergeladene Leroy-Artefakte mit passender
Größe und SHA-256, keine OOM-Ereignisse während des Leroy-Laufs, entfernte Job- und
Hilfscontainer sowie entferntes Arbeitsvolume. Test-Jenkins ist gestoppt und sein
ursprünglicher Ressourcenrahmen wiederhergestellt. Der NAS-Controller ist bereit,
automatische Trigger bleiben deaktiviert. Alle 13 Produktionshistorien sind auch
nach beiden Läufen unverändert. Sechs Ergebnisansichten sind automatisiert und
visuell auf Desktop/Mobil geprüft; der UI-Artefaktdownload besteht die SHA-Prüfung.
Nachweise: `candidates/antares/58da3ef5d112f58bc0a3d1cbd75179eb71d421c1/comparison.json`
und `linux-pool/complete-pair.json` unter `test-results/nas-parity/followup/`.

Ein Produktionswechsel ist weiterhin nicht erfolgt. Die Anwendungspatches sind
separat zu bewerten; der erfolgreiche Vergleich gilt für genau diese eingefrorenen
Kandidaten. Die reine NAS-Kapazität ist nicht erfolgreich abgenommen. Der neue
Linux-Testpool besitzt noch keine eigene Neustart-/Sicherungsabnahme für einen
dauerhaften Produktivbetrieb; die bisherigen NAS-Betriebsnachweise gelten für
den NAS-Teststack.
