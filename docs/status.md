# Projektstand und nächste Schritte

Dokumentationsstand: 26. Oktober 2026. **Die Jenkins-Ablöse ist auf Nutzerwunsch
verschoben, bis ein geeigneter Build-Server außerhalb des NAS bereitsteht.**
Jenkins bleibt das produktive CI-System. Der NAS-Testbetrieb ist beendet;
die vollständige Produktionsfreigabe für Leroy bleibt offen.

## Gesicherter Zwischenstand und Rückkehr zum Jenkins-Betrieb

Der aktuelle [Checkpoint mit Wiederaufnahmeplan](checkpoint-2026-10-26.md) ist der
Einstieg für die weitere Arbeit. Die folgenden älteren Abschnitte sind Chronologie,
keine Anweisung zum Wiederöffnen eines Wartungsfensters oder Wiederholen eines Jobs.

Am 26. Oktober wurde der wieder erreichbare NAS-Zustand geprüft. Der produktive
Jenkins ist gesund und entspricht dem ursprünglichen Inventar vom 3. Oktober:
Image, Ressourcen, Benutzer, Mounts, Netzwerk und Ports stimmen überein. Er wurde
nicht neu gestartet, zurückgesetzt oder umkonfiguriert. Buildhistorie und produktive
Quellen bleiben erhalten. Alle sieben Anwendungen laufen gesund und unverändert.

Der vorhandene private Jenkins-Auftrag #31 ist mit `FAILURE` beendet. Originales
Build-XML und Console-Log sind gesichert; das ursprüngliche Artefaktverzeichnis
ist leer. Der Jenkins-Dateisystem-Heartbeat fiel unter Last aus; das Console-Log
endet mit einem Fehler beim Speichern des Pipeline-Zustands. Die getrennte,
unverändert gelesene Gastquittung belegt Abbruch, vollständige Bereinigung und
null Rust-Tests. Sie ersetzt kein originales CI-Artefakt. Der Wächter hatte die
sieben Dienste bereits am 17. Oktober um 15:18:45 Berliner Zeit wieder gestartet.
Ihre heutige Gesundheit ist belegt; der damals fehlende vollständige
Gesundheitsnachweis vor Fensterende wird nicht nachträglich erfunden.

Die 14.331.805.696 Byte große Jenkins-Testplatte ist bytegeprüft auf HDD archiviert,
SHA-256 `c16dfdee5a450cf62b7e915db88ab011457304304c36d0359131c919ceb56095`.
SSD-Kopie und die 7-GiB-RAM-Datei sind freigegeben. Das alte Koordinatorjournal
steht nach dem NAS-Neustart noch auf `running`; seine ursprüngliche Invocation
wird nicht wieder gestartet oder als erfolgreicher Abschluss gewertet.

Beim Wiederanlauf war die feste PostgreSQL-Adresse vom dynamisch adressierten
Runner belegt. Explizite Adressen für PostgreSQL, Docker-Testdaemon und Runner
beseitigen diesen Fehler im Teststack; ein Start mit Runner vor PostgreSQL ist
erfolgreich geprüft. Images, Container-IDs, Daten, Ressourcen und Datenbankbestand
blieben dabei gleich. Ein danach vorbereiteter SSD-Umzug des privaten Jenkins
wurde auf den neuen Nutzerwunsch hin vor Kopie und Umschaltung beendet; er ist
weder durchgeführt noch qualifiziert.

Der Leroy-Testbestand wurde logisch gesichert: 174 Runs, 476 Schritte und
610 Artefakte, kein aktiver Lauf. Alle fünf NAS-Testdienste und die Test-VM sind
gestoppt, Neustartpolicy jeweils `no`. Daten, Volumes, Konfigurationen und
Fehlernachweise bleiben erhalten. Die automatische Abnahmefortsetzung ist beendet;
das frühere unbegrenzte NAS-Wartungsfenster wird nicht weiter verwendet.

Die letzten sechs Desktop-/Mobilansichten von #186 sind technisch und direkt
visuell geprüft. Sie zeigen den ursprünglichen Fehler und das unveränderte
189-Byte-Artefakt. Der aktuelle Quellstand besteht die lokale Gesamtsuite mit
788 Tests bei 43 umgebungsbedingten Skips; dies ist keine vollständige
Graphato-Release-Abnahme.

## Zugang am 24. Oktober

Die rein lesenden Anschlussprüfungen gegen 17:48 Uhr Berliner Zeit erreichen
NAS-SSH, Portainer und beide Leroy-Gesundheitsendpunkte nicht; alle Verbindungen
enden bereits beim Verbindungsaufbau mit Zeitüberschreitung. Anders als beim
Lastzustand am 17. Oktober ist der Windows-Rechner derzeit nicht regulär mit dem
NAS-Heimnetz verbunden: WLAN liegt in einem anderen IPv4-Netz, Ethernet hat nur
eine selbst zugewiesene Link-Local-Adresse. Ein passender VPN-Zugang ist nicht
nachgewiesen. Die aktuelle Nichterreichbarkeit belegt daher keinen NAS-Ausfall.

Jenkins #31, Backend `20ba640fd3144335b3d9a24111577651`, bleibt ohne neu
eingesammelten Abschlussnachweis. Auch Wiederherstellung und Gesundheit der
sieben Dienste nach dem Y-Fenster sind noch nicht bestätigt. Dessen feste
Endzeit am 17. Oktober wird nicht verlängert oder erneut geöffnet. Es wurde
kein Auftrag wiederholt und kein NAS-Zustand geändert. Nach Wiederherstellung
der Netzwerkverbindung werden zuerst dieser bestehende Lauf, das Wächterjournal
und die Dienstzustände eingesammelt; ein möglicher NAS-Neustart muss dabei
gegen die ursprüngliche Boot- und Prozessidentität geprüft werden.

Die Anschlussbelege liegen unter
`test-results/nas-parity/followup/nas-execution-20261017-y2/`:
`current-readonly-observation.jsonl`, `management-health-20261024.json`,
`api-health-20261024.json` und `network-access-20261024.json`.
Die vollständige Release-Abnahme und die Produktionsfreigabe bleiben offen.

## Aktueller Stand am 17. Oktober

**Versuch V/Leroy #185 ist mit `interrupted` beendet.** Run
`2345e20443414bd580ec620118030baf` lief am 17. Oktober von **09:18:39 bis
10:10:37 Berliner Zeit** mit dem eingefrorenen Commit und `server-test`.

Der Worker meldete den lokalen Lease-Abbruch nach 48,076 Sekunden ohne erfolgreiche
Erneuerung. Der NAS-Koordinator lief trotz der externen SSH-Lücken weiter und sicherte
zusätzliche Prozess- und Lease-Daten. Alle sieben Dienste sind wieder gesund;
der Fensterabschluss ist um **10:41:51** belegt, vor der festen Endzeit 13:07:53.

Die offline gelesene Originalquittung bestätigt `Cancelled`, vollständige Bereinigung,
erfolgreichen Imagebau (1.347,541 Sekunden), abgebrochene Rust-Kompilierung
(1.694,136 Sekunden, Exit 130) und **null ausgeführte Rust-Tests**.

Dies sind nachträglich gesicherte Laufdaten, keine veröffentlichten CI-Artefakte.

Die RAM-Datei ist freigegeben. Die 14.082.965.504 Byte große Platte ist auf HDD
archiviert und zurückgelesen, SHA-256
`6cdc613dd52e35c98e8b56a9604ce9986bf01b59f96f0617eff450d864cf3810`;
die SSD-Kopie ist entfernt. Es wurde kein Jenkins-Rust- oder Release-Lauf gestartet.

Während des Ausfalls wartete der Uvicorn-Hauptthread in `anon_pipe_write`, während
PostgreSQL-Verbindungen im Leerlauf waren. Gleichzeitig bestand erheblicher globaler
Speicher-/I/O-Druck. Das vorhandene Docker-Logging mit `mode=non-blocking` verhindert
keine blockierende Ausgabe in die erste Prozess-Pipe. Eine begrenzte asynchrone
Console-Ausgabe beseitigt diesen reproduzierten Fehlerfall in sechs echten
Linux-Prozesstests auf dem NAS; API und geordnetes Beenden bleiben auch bei voller
ungelesener Pipe erreichbar. Der zusätzliche Vergleich mit echtem Worker bestätigt die Korrektur: alte Ausgabe
mit 20 API-Timeout-Samples und Lease-Abbruch, neue Ausgabe ohne API-Timeouts,
mit allen 21 Joblogtakten und geprüftem Abschlussartefakt. Der korrigierte
Controller ist im isolierten Abnahme-Stack installiert und gesund. Nur dieser
Container wurde ersetzt; Datenbankdump und vorheriges Image sind gesichert,
Datenbankbestand, Runner, Worker, Docker-Daemon und Konfigurationsdateien bleiben
nachweislich gleich. Die variierenden Reihenfolgen von Docker-Umgebungsvariablen
und Mounts wurden gegen die ursprünglich gesicherten Hashes exakt rekonstruiert;
es wurden keine Wertänderungen ausgeblendet.

Die historische Ursache ist damit eingegrenzt, nicht für jeden früheren Ausfall bewiesen.

**Versuch W/Leroy #186 ist mit `failed` beendet**, ohne Lease-Abbruch.
Run `f4af042f894b422bbeda50a8b07c8d98` lief am 17. Oktober von **11:23:08
bis 13:15:37 Berliner Zeit**. Der Controller blieb erreichbar und erneuerte die
Worker-Lease. Der originale Pruefschritt verlor die SSH-Verbindung zum Testgast.
Das einzige originale Ergebnisartefakt meldet unbestaetigte Bereinigung;
die spaetere Offline-Sicherung bleibt davon getrennt.

Die unveraendert gelesene Gastquittung bestaetigt fehlgeschlagenes `server-test`,
`cancelled=false`, vollstaendige Bereinigung und **null ausgefuehrte Rust-Tests**.
Imagebau: 1.660,558 Sekunden, erfolgreich. Die Kompilierung erreichte nach
5.427,39 Sekunden das unveraenderte originale 90-Minuten-Limit. Die VM ist
beendet; alle sieben Dienste sind seit **13:29:03** wieder gesund, vor Ablauf des
Fensters. Produktiver Jenkins und Controllerprozess blieben unveraendert.
Die 14.269.743.104 Byte grosse Platte ist auf HDD kopiert und zurueckgelesen,
SHA-256 `b85506cb036aa395ada45f5ade22eb2a8db4d8835e9128e778a4f6f5bc4b3d71`;
SSD-Kopie und RAM-Datei sind freigegeben.

Der naechste Vergleich ist ausschliesslich der originale Jenkins-Rust-Auftrag
in einem neuen Fenster Y mit identischem physischen Profil und frischer Baseline.
Die korrigierte Steuerung besteht 678 Tests nativ auf dem NAS ohne Fehler
oder Skips. Der importierte Validator verwendet jetzt den im Plan gebundenen
Versuch statt des Modul-Standardwerts. Der erste, vor Dienstpause und CI-Start
gestoppte Y-Zulassungsversuch bleibt separat erhalten. Y2 verwendet neue
Systemd-Invocation-IDs und ein neues Journal; das eigene Fenster Y ist erstmals
pausiert. Der private Jenkins-Auftrag `graphato-postdeploy-quality #31` laeuft seit
13:53 Uhr Berliner Zeit. Sein Gastlauf `20ba640fd3144335b3d9a24111577651`
kompiliert Rust-Abhaengigkeiten. Das komplette Release-Manifest und die
vorbereiteten Parameter sind bytegleich zu #186; ein Endergebnis liegt noch
nicht vor. Die lokale Gesamtsuite besteht mit 788 Tests und 43
umgebungsabhaengigen Skips. Dieser diagnostische Gegenlauf ersetzt keine erfolgreiche
Leroy-Rust-Abnahme und erlaubt keinen vollstaendigen Release-Start. Graphato-Quellen,
Tests, Runtime und originale Fixture-Grenzen bleiben unveraendert.

644 Operator-Tests bestehen nativ auf dem NAS ohne Fehler oder übersprungene Fälle;
759 lokale Tests bestehen, 43 umgebungsabhängige Tests sind übersprungen. Der echte
Diagnosejob überstand 18 Sekunden Verbindungsverlust und einen Neustart des
Testcontrollers mit derselben Run-ID. Bei 110 Sekunden Verbindungsverlust meldete
der Worker nach 47,008 Sekunden den lokalen Lease-Abbruch; der Controller beendete
den Auftrag als `interrupted`. Genau zwei Diagnoseaufträge, kein doppelter Start,
keine pausierten Dienste während dieser Proben und keine produktiven Jenkins-Builds.

Auch der erzwungene Neustart des neuen NAS-Koordinators führt denselben
Phasenprozess mit unveränderter Invocation-ID fort. Details:

[NAS-Steuerung der ursprünglichen Abnahme](nas-resident-execution.md).

**Leroy #182 ist beendet, aber nicht erfolgreich.** Der Originalauftrag
`fac4b92f061e4c6897ce0bc276399907` endete am 16. Oktober um **11:57:41 Berliner Zeit**
mit `interrupted`. Der Controller nennt für den Prüfschritt:

`Runner lease expired; external effects require reconciliation`.

Imagebau erfolgreich, Rust-Kompilierung zuvor beobachtet; **keine veröffentlichten
Ergebnisartefakte und kein qualifizierter vollständiger Rust-Abschluss**.

Die lokale Beobachtungssteuerung scheiterte zusätzlich an SSH-Verbindungsfehlern.

Ein vollständiger lokaler Fensterabschlussbericht fehlt. Die früheren Dateien mit Status `running` beziehungsweise `waiting` sind
veraltet. Die beiden lokalen Fortsetzungsprozesse laufen nicht mehr; **der neue
Jenkins-Rust-Vergleich und beide vollständigen Release-Abnahmen wurden nicht gestartet**.

Die angekündigte automatische Folge hat die Abnahme somit nicht weitergeführt.

Der unabhängige NAS-Wächter hat das Fenster geschlossen: Die VM endete am
16. Oktober um **14:34:56** mit Exitcode 0, ohne OOM. Alle sieben Dienste waren bis
**14:35:39** wieder gestartet, vor der festen Endzeit 14:49:01. Drei aktuelle
Kontrollen am 17. Oktober bestätigen alle sieben Dienste als gesund und stabil.

Die produktiven Jenkins-Buildstände waren bei dieser Nachprüfung unverändert; auch ältere parallele Builds
wurden lesend geprüft, keine aktiven Builds. Dabei wurde kein neuer Test gestartet.

Die frühere Wartungsfreigabe endete am 16. Oktober um 23:59:59 Berliner Zeit.

Am 17. Oktober hat der Anwender das Wartungsfenster ausdrücklich unbegrenzt
geöffnet. Einzelne Prüfphasen behalten eine feste Frist von höchstens vier Stunden
und 15 Minuten Wiederherstellungsreserve; geschlossene Fenster werden nicht verlängert.

Die Originalquittung von #182 wurde ohne Start der alten VM aus deren Platte
gelesen: `Cancelled`, vollständige Bereinigung, Imagebau erfolgreich, Rust-Kompilierung
abgebrochen, null ausgeführte Rust-Tests. Dies ersetzt keine veröffentlichten CI-Artefakte.

Die RAM-Datei ist freigegeben. Die 14.185.660.416 Byte große Platte wurde mit
SHA-256 `8a560026cceec282c46ab12d6bf31163ba1c0c779a2590e1c9e5251b42fc2135`

auf HDD archiviert, zurückgelesen und die SSD-Kopie entfernt.

Zwei belegte Beobachtungsfehler sind korrigiert: Ein bekannter Leroy-Lauf braucht
beim Wiederaufnehmen nach HTTP-Lesefehlern keine erneute SSH-Zulassungsprüfung;
die konkrete OpenSSH-Kombination aus `kex_exchange_identification` und NAS-`banner
exchange` mit `Unknown error` wird als Verbindungsabbruch erkannt. Authentisierungs-
und Hostschlüsselfehler bleiben Fehler. Ein eigenständiger NAS-Koordinator mit
eindeutigen systemd-Einheiten, dauerhaftem Journal und ergänzender Lease-/Prozess-
Diagnose ist auf Linux qualifiziert. Die tatsächliche Ursache der Lease-Überschreitung
von #182 ist damit noch nicht bewiesen. Seine nachträglich gesicherten NAS-Samples
zeigen um den Lease-Verlust erheblichen Speicher-/I/O-Wartedruck; dies belegt
noch keine einzelne Ursache.

Graphato bleibt unverändert auf `0ad540dd578033d45e4d0c25d89fbe57b32102a4`.

Die NAS-Abnahme und der vollständige Jenkins-/Leroy-Vergleich sind weiterhin offen.

Die nächste Prüfung verwendet den neuen NAS-Koordinator und die dauerhafte
Lease-Diagnose; ein Fehler der Graphato-Tests ist durch #182 nicht belegt.

Die Prüfung ist unter `test-results/nas-parity/followup/status-20261017-u/` gespeichert.

## Verlauf der Abnahme am 16. Oktober

**Historischer Zwischenstand: Versuch U/Leroy #182** (`fac4b92f061e4c6897ce0bc276399907`),
seit 10:59:43 Berliner Zeit im ursprünglichen Qualitätsauftrag. Neue Baseline,
unveränderte Graphato-Quellen und Tests, dieselbe DNS-Konfiguration und atomare
Fortschrittsübergabe. DNS-Vorprüfung und ursprünglicher Imagebau erfolgreich;
Rust-Kompilierung läuft seit etwa 11:28 Uhr, noch ohne abschließendes Testergebnis.

Die tatsächlichen DNS-Server des Builders und dessen ursprüngliche Grenzen von
6 GiB RAM, ohne Swap und zwei CPUs sind lesend bestätigt. Feste Endzeit
**14:49:01 Berliner Zeit**, Wiederherstellungsbeginn spätestens **14:34:01**.

82 native Linux-Prüfungen und 721 lokale Tests bestehen; 43 lokal übersprungen,
Ruff fehlerfrei. Ein erfolgreicher vollständiger ursprünglicher Rust-Lauf fehlt weiter.

Eine einmalige lokale Anschlusssteuerung wartet auf den laufenden Leroy-Auftrag.

Erst nach vollständigem Rust-Erfolg, gesunden wiederhergestellten Diensten und
bytegeprüftem Plattenarchiv darf sie den ursprünglichen Jenkins-Rust-Vergleich U
über dieselben unveränderten Abnahmeskripte starten. Acht Offline-Prüfungen der
Sperrbedingungen bestehen. Bei Fehlern, geänderten Skriptprüfsummen, vorhandenem
Jenkins-Plan oder unzureichender verbleibender Freigabezeit hält die Folge an.

Eine zweite einmalige lokale Folge wartet auf beide nachgewiesenen Rust-Erfolge
und deren vollständig geschlossene Fenster. Danach darf sie die bereits vorgesehenen
Release-Läufe Leroy → Jenkins über dieselben Abnahmeskripte ausführen und die
veröffentlichten Originalergebnisse vergleichen. Neun zusätzliche Offline-Prüfungen
bestätigen Sperrbedingungen und Reihenfolge; unvollständige Inventare bleiben negativ.

Jedes Fenster braucht ausreichende Restzeit bis 23:59:59 Berliner Zeit und eine
vollständige Wiederherstellung vor dem nächsten. Produktionsumschaltung und
automatische Produktionsfreigabe sind ausgeschlossen.

**Versuch T/Leroy ist vorzeitig beendet und nicht qualifiziert.** Ein gleichzeitiger
Schreib-/Lesezugriff auf die lokale Fortschrittsdatei löste `JSONDecodeError` aus.

Die Abnahmesteuerung begann daraufhin die Wiederherstellung, bevor das Ziel
fertig war. Die offline gelesene Originalquittung belegt `Cancelled`,
`cleanupComplete: true`: Imagebau erfolgreich in 1.311,774 Sekunden, danach
Rust-Kompilierung nach 14,189 Sekunden abgebrochen. Keine ausgeführten Rust-Tests.

Leroy #181 bleibt als `failed` mit seiner einzelnen veröffentlichten Abbruchquittung
erhalten; die Offline-Diagnose ersetzt keine CI-Artefakte. Alle sieben Dienste
sind wieder gesund und stabil, VM sauber beendet, eigene RAM-Datei freigegeben.

Die Testplatte mit 13.249.675.264 Byte ist bytegeprüft archiviert, SSD-Kopie entfernt;
SHA-256 `5a30608c8429b3719ce94931afd5b835f443ece923b7c0c4c399c8595b57aa90`.

Die Abnahmesteuerung veröffentlicht vollständige JSON-Snapshots nun atomar und
behält bei vorübergehend unvollständigen Beobachtungen dieselbe ursprüngliche
Run-ID. Der Fehler ist durch Gegenbeispiele abgedeckt: 82 native Linux-Prüfungen
und 721 lokale Tests bestehen, 43 lokal übersprungen, Ruff fehlerfrei. Ein frischer
Versuch U muss mit unveränderten Quellen, Tests, DNS und Ressourcen neu beginnen.

Die ursprünglich feste Endzeit von T war **13:57:34 Berliner Zeit**, spätestens
**13:42:34** wäre die Wiederherstellung begonnen worden; das Fenster bleibt geschlossen.

Nur im jeweiligen isolierten Gast wird der nachweislich fehlerhafte DNS-Weg
über QEMUs Proxy umgangen: direkte Upstreams `8.8.8.8` und `1.1.1.1`, identische
Konfiguration für den anschließenden frischen Jenkins-Vergleich. Die Einstellung
wird vor und nach dem Lauf geprüft; ein abweichender DNS-Stand qualifiziert nicht.

NAS-DNS, Firewall, SSH, Kernel und Swap bleiben unverändert. Graphato-Quellen,
Tests, ursprüngliche Fristen, Ressourcen und die 45-/90-Sekunden-Leases bleiben
unverändert. 68 native Linux-Prüfungen der Steuerung und 703 lokale Tests bestehen;
43 lokale Tests übersprungen, Ruff fehlerfrei. Das Worker-Image ist weiterhin das
mit 37 Linux-Prüfungen qualifizierte Image. Kein vollständiger Rust-Erfolg.

**Versuch S ist geschlossen.** Leroy #180 scheiterte wie Jenkins #30 beim
ursprünglichen npm-Schritt an `EAI_AGAIN registry.npmjs.org`, vor Rust.

Alle drei originalen Artefakte wurden veröffentlicht: Ergebnis, Abbruchquittung
und Diagnosearchiv. Der Zielauftrag meldet `cleanupComplete: true`,
`cancelled: false`; die Abbruchquittung ist passend zum Lauf `not-running`.

Die VM endete um 09:47:31 sauber, alle sieben Dienste sind seit spätestens
09:50:32 gesund und stabil. Keine produktiven Jenkins-Builds im Fenster, keine
geänderte Infrastruktur und kein neuer Controller-OOM. Eigene RAM-Datei freigegeben,
Testplatte mit 9.344.057.344 Byte bytegeprüft archiviert, SSD-Kopie entfernt;
SHA-256 `0ba24d063e98e08445de8fecf77b74132d31002fa390a14fd048ca9e36a15eef`.

Die direkte Gast-DNS-Probe während des Fehlers lieferte für den lokalen Resolver
und `10.90.0.3` jeweils einen Timeout nach zwei Sekunden; `8.8.8.8` antwortete
in 24 ms. Spätere Messungen im äußeren Namespace und auf dem NAS waren erfolgreich;
sie waren nicht gleichzeitig und beweisen keine ausschließliche Ursache.

Zusätzliche SSH-Leseabfragen fielen zeitweise aus, der Runner wurde als offline
gemeldet. Die abschließende Belegsammlung war deshalb unvollständig; der originale
CI-Abschluss und seine veröffentlichten Artefakte bleiben davon getrennt.

Die 72 Speicherproben enthalten 63 Zuordnungen und neun Lücken; kein beobachteter
neuer NAS-OOM. Die Steuerungsabweichungen werden nicht als behoben ausgegeben.

Jenkins **#30** endete als `FAILURE`: Beim unveränderten Imagebau schlug
`npm install --global pnpm@11.1.3` mit `EAI_AGAIN` für `registry.npmjs.org` fehl.

Rust wurde nicht ausgeführt. Das ist ein anderer Fehler als bei Leroy #179.

Ergebnis, Abbruchquittung und Diagnosearchiv wurden regulär veröffentlicht;
`cleanupComplete: true`, `cancelled: false`. Die VM endete sauber um **08:58:25**,
alle sieben Dienste waren um **08:58:59 Berliner Zeit** wieder gestartet und
vor 09:01 gesund und stabil geprüft. Keine produktive CI-Aktivität, keine
geänderte Infrastruktur oder neuer Controller-OOM. RAM-Datei freigegeben,
Testplatte mit 9.409.724.416 Byte bytegeprüft auf HDD archiviert; SHA-256
`a2fc698d08fe61c38022ca90d7f18e00abd61f833ec3c686e2cb83fd4e5868c3`.

Zwölf begrenzte DNS-Abfragen im bestehenden VM-Netznamespace und zwei
TLS-geprüfte HTTPS-Abrufe der npm-Metadaten waren im Leerlauf erfolgreich.

Der DNS-Fehler unter Buildlast bleibt damit ungeklärt. DNS- und
Firewall-Einstellungen wurden nicht geändert.

Für den frischen Vergleich ist eine belegte Transportabweichung korrigiert:

Leroy verwendet jetzt `ssh_options` des unveränderten Graphato-Checkouts.

Damit gelten dieselben Keepalives und unabhängigen Verbindungen für Auftrag,
laufgebundenen Abbruch, Ergebnis und Artefakte wie im ursprünglichen Skript.

Das genaue Worker-Image besteht 37 Linux-Prüfungen auf dem NAS, darunter
Original-Postdeploy mit Erfolg und simuliertem Verbindungsfehler; nur dieses
Image ist im isolierten Graphato-Profil installiert. Worker-Leases und
Graphato-Quellen, Tests, Fristen und Ressourcen bleiben gleich. Der erste
fehlgeschlagene Prüfansatz ist erhalten; seine SSH-Simulation wurde korrigiert.

Die Änderung ist kein bewiesener Ursachennachweis für #179 und kein erfolgreicher
ursprünglicher Rust-Lauf.

Q und R wurden vor der Dienstpause abgefangen: Eine importierte Funktion
verwendete die Standardreferenz; anschließend lehnte der NAS-Wächter den noch
nicht registrierten Fensternamen ab. Kein Graphato-Job und keine VM wurden
gestartet. Die Fehlversuche bleiben erhalten. Die Korrektur prüft die tatsächliche
Wächterrichtlinie bereits beim Erstellen des Plans; die explizite Zuordnung des
Versuchs ist durch Gegenbeispiele geprüft.

S/Leroy lief mit eigenem Journal und frischer Baseline. Seine feste Endzeit war:

**16. Oktober, 13:21:59 Berliner Zeit**, Wiederherstellungsbeginn spätestens
13:06:59. Die Steuerung besteht 54 Linux-Prüfungen auf dem NAS und insgesamt
687 lokale Tests; 43 lokal übersprungen, Ruff fehlerfrei. Vollständige Releases
benötigen weiterhin erfolgreiche ursprüngliche Rust-Tests beider Engines unter
den aktuellen Bedingungen; diagnostische P-Ergebnisse werden nicht übernommen.

Leroy **#179** (`e32366e7ffb249a4b7753d00ff6bd4c6`) endete am 16. Oktober
um **00:12:54 Berliner Zeit** als `failed`, mit Exitcode 1 im Prüfschritt.

Das unveränderte Graphato-Skript meldet einen Timeout der SSH-Verbindung zum
isolierten Ziel und konnte anschließend Ergebnis und Diagnosearchiv nicht
abrufen. Das einzige veröffentlichte Artefakt ist `cancellation.json` mit
`status: unconfirmed` und `errorType: JSONDecodeError`. Ein Testfehler, ein
Compilerfehler oder eine bestätigte Zielbereinigung folgt daraus nicht.

Ein Lease-Abbruch ist in diesem Abschluss nicht erfasst; es handelt sich
nicht um den Lease-Abbruch von #178. Um 00:27 antwortete die API weiterhin
schnell, meldete den Runner aber als offline. Dessen letzte Meldung stammte von
23:55:50 Berliner Zeit. Die Erreichbarkeit der API belegt keine gesunde Ausführung.

Der ursprüngliche BuildKit- und Rust-Container wurden unter den unveränderten
Grenzen von 6 GiB ohne Swap und zwei CPUs beobachtet. Der Imageexport endete
nach 372,9 Sekunden; die Rust-Kompilierung begann. Ein vollständiges
Rust-Testinventar fehlt. Der ergänzende synthetische Kapazitätstest bleibt
ausdrücklich unqualifiziert. Quellen, Tests und Fristen wurden nicht geändert.

Die Folgephasen sind gestoppt, kein weiterer Job wurde ausgelöst. Der unabhängige
NAS-Wächter begann die Wiederherstellung um **03:15:09**. Die VM endete um
**03:15:34** sauber, ohne erzwungene Beendigung oder Reserveabbruch. Um
**03:15:57** waren alle sieben Originalcontainer wieder gestartet, vor der
unveränderten Endzeit 03:30:03. Seit dem wieder verfügbaren SSH-Zugang am Morgen
sind ihre Gesundheit und Stabilität durch drei Kontrollen bestätigt. Ein
Gesundheitsnachweis vor 03:30 wird wegen der Beobachtungslücke nicht behauptet.

Infrastruktur und Controller-Prozess blieben unverändert; kein neuer NAS-OOM.

Die eigene 7-GiB-RAM-Datei ist nach dem bestätigten VM-Abschluss freigegeben.

Die Testplatte mit 14.496.432.128 Byte ist bytegeprüft auf HDD archiviert;
SHA-256 `00cc00d36928cf6723c40dcaa6f74c2cc6be5eda91a7b2ced9734e36c2feb87a`.

Ihre SSD-Kopie ist entfernt; die produktive CI blieb auch während des Archivierens ruhig.

Die gestoppte Platte enthält die gebundene Originalquittung: `TimeoutExpired`,
6.390,356 Sekunden, `cancelled: false`, vollständige Bereinigung. Der
Kompilierungsschritt dauerte 5.412,311 Sekunden, ohne ausgeführte Rust-Tests.

Das ist zusätzliche Plattendiagnostik, kein nachträglich veröffentlichtes
CI-Artefakt. Die Speicherreihe enthält 1.144 Proben, 707 zeitlich zugeordnet und
437 fehlend oder nicht zuordenbar. Kein beobachteter NAS-OOM; Gast-OOM nur
teilweise beobachtet. Der separate Worker-Beobachter endete selbst mit
`TimeoutExpired` beim Abschluss; seine Daten sind unvollständig und werden
nicht als erfolgreich abgeschlossene Diagnose ausgegeben.

Der native Musik-Sync-Zähler stieg zwischen der Vorbereitung und der verspäteten
Morgenkontrolle von 244 auf 245. Der zunächst negative Grenzvergleich bleibt
erhalten. Die ergänzende lesende Prüfung der ursprünglichen Build-XML ordnet

#245 dem Zeitpunkt **03:19:00** zu, nach dem Fensterabschluss um 03:15:57.

Alle anderen Jobstände blieben gleich. Damit ist die ruhige produktive CI für
das Testfenster nachträglich belegt; gleiche sonstige Hintergrundlast folgt
daraus nicht. Die Tagesfreigabe endet weiter am 16. Oktober um 23:59:59.

Weder dieser fehlgeschlagene Versuch noch die Wiederherstellung erlauben eine
Produktionsfreigabe oder das Überspringen ursprünglicher Rust-Tests.

## Aktueller Stand am 15. Oktober, abends

Der unveränderte ursprüngliche Jenkins-Job **#29** ist als `FAILURE` gesichert.

Die Rust-Kompilierung überschritt ihre ursprüngliche Frist; ein vollständiges
Testinventar fehlt. Die separat aus der Testplatte gelesene Quittung enthält
`TimeoutExpired`, vollständige Bereinigung und `cancelled: false`. Jenkins
veröffentlichte nur `cancellation.json`; die zusätzlichen Plattendiagnosen
ersetzen keine CI-Artefakte. Hinzu kommen die Warnung über einen nicht
aktualisierten Jenkins-Shell-Wrapper und erhebliches Auslagern des privaten
Java-Prozesses. Ein Fehler der Graphato-Testfälle ist dadurch nicht belegt.

Alle sieben Dienste waren um **18:29:35 Berliner Zeit** wieder gesund und stabil.

Die produktive CI und Infrastruktur blieben unverändert; kein neuer NAS-OOM.

Der Wächter musste die Test-VM zwangsweise beenden, deshalb wird kein sauberer
VM-Abschluss behauptet. Die Platte ist bytegeprüft auf HDD archiviert, ihre
SSD-Kopie und die eigene RAM-Datei sind freigegeben.

**Versuch I** ist geschlossen. Leroy **#178** endete um **20:16:18 Berliner Zeit**
als `interrupted`, weil die Worker-Lease nicht bestätigt werden konnte.

Die separat gelesene Originalquittung enthält `Cancelled`, 3.949,918 Sekunden
und vollständige Bereinigung. Kein vollständiges Rust-Testinventar; keine
veröffentlichten CI-Artefakte. Die direkten API-Proben blieben schnell, die
Worker-Anfragen hatten dagegen zuletzt fünf bis sieben Sekunden Laufzeit und
zahlreiche Major Page Faults bei wenig CPU-Zeit. Die genaue Kausalität bleibt offen.

Die VM endete sauber; alle sieben Dienste sind seit **20:21:07** gesund und stabil.

Kein neuer NAS-OOM. RAM-Datei freigegeben, Platte mit SHA-256
`295744389bcccc869bad02ff05a1145307915522d6840100da35f192dcd122ca`

bytegeprüft auf HDD archiviert; SSD-Kopie entfernt.

Der verschachtelte Test-Docker-Dienst hatte bisher keine wirksame übergeordnete
Speicherreservierung. Nach I wurde ausschließlich dieser Dienst mit derselben
persistent gespeicherten Engine und denselben inneren Containern in eine eigene
Gruppe direkt unter der Wurzel versetzt: 1.536 MiB weicher Speicherschutz,
rekursive Anwendung durch den bereits vorhandenen Kernel-Mount bestätigt.

Harte Grenzen, Images, Volumes und globale NAS-Einstellungen bleiben gleich.

Alle 28 Worker-/Transportprüfungen bestehen im unveränderten NAS-Image.

Die Änderung ist noch kein Nachweis erfolgreicher Ausführung unter Rust-Last.

**Versuch J** wurde vor dem CI-Auftrag durch einen SSH-Banner-Timeout in der
Abnahmesteuerung beendet. Es gibt keinen gestarteten Graphato-CI-Lauf und keinen
Testbefund. Alle sieben Dienste sind wieder gesund und stabil; VM sauber beendet,
RAM-Datei freigegeben, Testplatte bytegeprüft archiviert. Infrastruktur und
produktive CI blieben unverändert. Bekannte OpenSSH-Transportabbrüche erhalten
jetzt einen eigenen `OSError`-Typ: Die bereits vorhandenen Beobachtungs- und
Wiederherstellungsschleifen behandeln sie als unbekannte Antwort derselben Aktion.

Authentifizierung, Host-Key-Fehler und fehlgeschlagene Prüfungen bleiben fatal.

15 Gegenbeispiele bestehen lokal und im unveränderten Linux-Worker-Image.

**Versuch K** ist ebenfalls vor dem CI-Auftrag geschlossen. Der äußere Beobachter
behandelte den SSH-Ausfall korrekt als unbekannte Antwort; eine innere Leseabfrage
der produktiven Jobstände brach die Vorbereitung bei 2.048 MiB ab. Die sieben
Dienste sind wieder gesund und stabil, VM sauber beendet, RAM-Datei freigegeben
und Testplatte bytegeprüft archiviert. Die Zulassungsprüfungen wiederholen nun
ausschließlich bekannte verlorene Leseabfragen innerhalb eines gemeinsamen
60-Sekunden-Budgets vor jeder Zuteilung. Geänderte produktive Jobstände,
Identitätsfehler und ungültige Antworten bleiben Abbruchgründe. Zuteilungen werden
nicht wiederholt. 23 Linux-Gegenbeispiele bestehen im unveränderten Worker-Image;
Probe, Seitenmarker, NAS-Untergrenzen und ursprüngliche Fristen bleiben gleich.

**Versuch L** ist ebenfalls vor dem CI-Auftrag geschlossen. Bei 2.048 MiB
blieben die Leseabfragen länger als ihr festes Budget unbeantwortet; keine weitere
Zuteilung und kein Graphato-Auftrag wurden gestartet. Alle sieben Dienste sind
wieder gesund und stabil, VM sauber beendet, RAM-Datei freigegeben und Testplatte
bytegeprüft archiviert. Die gelesenen NAS-IPv4-Regeln zeigen keine SSH-Ratenregel;
die Ursache der Anmeldeverzögerungen bleibt offen. Sicherheitsregeln wurden nicht geändert.

Die Kapazitätssteuerung läuft im neuen **Versuch M** direkt auf dem NAS. Sie
liest denselben gepinnten Produktionsstand und dieselben NAS-Untergrenzen lokal,
verwendet unverändert den Gast-Speicherfüller und hält eine Gast-SSH-Verbindung.

Der temporäre Steuerprozess erhält innerhalb der vorhandenen eigenen Gruppe
32 MiB weichen Schutz, maximal 128 MiB ohne Swap und eine halbe CPU. Er endet
vor dem Original-CI-Auftrag. Die Windows-Seite holt nur Nachweise ab; ein verlorener
Startbeleg darf keinen zweiten Start auslösen. 18 Gegenbeispiele und die tatsächliche
Prozessbegrenzung bestehen auf dem NAS, zusätzlich 23 SSH-/Leseprüfungen im Worker-Image.

Die reale Lastprobe erreichte 3.584 MiB und endete um 22:12:23 Berliner Zeit
mit einem fehlgeschlagenen Gast-Steuerbefehl. Der genaue Fehler ist noch offen;
die Probe und der ursprüngliche Rust-Auftrag sind nicht qualifiziert.

M ist seit **22:16:36 Berliner Zeit** geschlossen. Alle sieben Dienste sind
gesund und stabil, produktive CI und Infrastruktur unverändert. Die VM endete
sauber, die 7-GiB-RAM-Datei ist freigegeben; die Testplatte ist mit SHA-256
`1f43a6d2b9d556660d1d6965fd257ef90a50edf503885be155f2fdb0173d4229`

bytegeprüft archiviert und ihre SSD-Kopie entfernt.

22 Trace-Proben enthalten nur zwei zeitlich zugeordnete Gastwerte und 20 Lücken;
kein neuer NAS-OOM. Es wurde kein Graphato-CI-Auftrag gestartet.

Die ausdrückliche zusätzliche Freigabe
gilt bis zum Ende des 16. Oktober; alte Endzeiten und Journale wurden nicht verlängert.

Erforderlich bleiben eine frische Kapazitätsprobe und derselbe unveränderte
Original-Rust-Auftrag. Die eigene
Controller-Reservierung bleibt 256 MiB, die Seitenrückgabe 64 KiB.

Graphato-Quelle `0ad540dd…`, Tests, Fixture-Limits und 45-/90-Sekunden-Lease-Fristen
bleiben unverändert. Jenkins und vollständige Releases benötigen weiterhin
erfolgreiche neue Rust-Nachweise; eine Produktionsfreigabe fehlt.

**Fenster N** prüft denselben Ressourcenstand mit ergänzter Fehlerdiagnose.

Bei einem Gastfehler werden Exit-Code, Laufzeit, bekannte Fehlerklassen und
Prüfsummen der Ausgabe erhalten; beliebige Logtexte werden nicht übernommen.

Eine zusätzliche reine Leseabfrage der Docker-Ereignisse bindet sich an genau
den Probe-Container und erfasst vorhandene Exit-/OOM-/Signal-Metadaten.

Fehlende Ereignisse beweisen keinen fehlerfreien Ablauf. 29 Prüfungen bestehen
in einer tatsächlich begrenzten NAS-Prozessgruppe ohne VM oder Speicherlast;
lokal bestehen 586 Tests, 43 sind übersprungen, Ruff ist sauber.

N endet spätestens am **16. Oktober um 02:24:48 Berliner Zeit**, mit
Wiederherstellungsbeginn spätestens **02:09:48**. Keine Ressourcen- oder
Friständerung, kein Wiederöffnen von M und kein erneuter Start einer verlorenen Aktion.

N ist seit **22:44:28 Berliner Zeit** geschlossen; alle sieben Dienste sind
gesund und stabil, produktive CI und Infrastruktur unverändert, kein neuer NAS-OOM.

Der Gastlog belegt `TimeoutError` in `server.accept()`: Die Zusatzprobe lief
während einer Steuerungspause in ihre 120-Sekunden-Leerlaufgrenze. Docker erfasste
Exit-Code 1, anschließend scheiterte der nächste Befehl mit `ConnectionRefusedError`.

Die genaue langsame Zwischenoperation ist noch nicht zugeordnet. Kein Graphato-CI-Auftrag.

VM sauber beendet, RAM-Datei freigegeben und 4.342.480.896 Byte Testplatte
bytegeprüft archiviert, SHA-256
`3bf06d6c5818368b7dfe0ebdb066919fb2733c2b9b16bc3fa949ce8de3782fc2`;
SSD-Kopie entfernt.

**Fenster O** ergänzt ausschließlich aktive Statusabfragen der Zusatzprobe über
die bestehende private Gast-SSH-Verbindung. Die vollständigen Identitäts-,
Produktions- und Reserveprüfungen bleiben vor weiteren Zuteilungen erforderlich.

Statusabfragen zählen nicht als Halte- oder Markerprüfung und enden vor dem
abschließenden Beleg. Speicherfüller, 120 Sekunden Leerlauf, 1.200 Sekunden
Gesamtzeit, CPU-Grenze und ursprüngliche Fixture-Limits bleiben gleich.

41 Prüfungen bestehen in der tatsächlichen NAS-Prozessgruppe ohne VM oder Last,
605 lokale Tests bestehen, 43 sind übersprungen; Ruff ist sauber.

O endet spätestens am **16. Oktober um 02:51:58 Berliner Zeit**, mit
Wiederherstellung ab spätestens **02:36:58**. Die reale Kapazitäts- und
Original-CI-Abnahme bleibt offen.

O ist seit **23:19:36 Berliner Zeit** geschlossen. Die Statussteuerung lieferte
21 zusätzliche Antworten, die Speicherzuteilung blieb jedoch bei 3.072 MiB.

Eine spätere Statusanfrage dauerte 101 Sekunden und traf auf den bereits beendeten
Probe-Prozess. Der Gastlog bestätigt erneut den Leerlauf-Timeout, Docker Exit-Code 1.

Die genaue lange Zwischenoperation der Hauptsteuerung bleibt offen.

Alle sieben Dienste sind gesund und stabil; produktive CI und Infrastruktur
unverändert, kein neuer NAS-OOM. VM sauber beendet, RAM-Datei freigegeben,
4.361.027.584 Byte Testplatte bytegeprüft archiviert, SHA-256
`dbd9a4f9e95528710682dfb67cb77721de63130756e4ad5b5be1c57c7731bfb3`;
SSD-Kopie entfernt. Kein ursprünglicher Graphato-Auftrag wurde gestartet.

**Fenster P** prüft die vollständigen unveränderten Originalaufträge aus frischem
Zustand direkt. Die zusätzliche synthetische Füllprobe wird dafür getrennt
bewertet: Ihr negatives Ergebnis bleibt samt Prüfsummen erhalten, sie wird weder
als bestanden noch als Ressourcenqualifikation behauptet. Der neue Modus schreibt
einen eigenen Beleg mit `synthetic_capacity_qualified: false`; er erzeugt keinen
positiven Kapazitätsbeleg. Originalquellen, Tests, Parameter, 6-GiB-Fixture ohne Swap
mit zwei CPUs, Lease-Fristen und NAS-Wächter bleiben gleich. Erst der erfolgreiche
Original-Rust-Lauf mit allen 1.657 Testidentitäten erlaubt den neuen Jenkins-Lauf;
beide bleiben Voraussetzung für die vollständigen Releases. Die fehlende
synthetische Vollkapazitätsqualifikation bleibt eine gesonderte Betriebsgrenze.

19 Prüfungen und alle geänderten Operatorprogramme sind auf dem NAS unter Linux
geprüft, ohne VM oder Speicherlast. Lokal bestehen 632 Tests, 43 sind übersprungen,
Ruff ist sauber. P endet spätestens am **16. Oktober, 03:30:03 Berliner Zeit**,
mit Wiederherstellung ab spätestens **03:15:03**. Keine Produktionsfreigabe.

Die Abnahmesteuerung beobachtet bei verlorenen Registrierungsantworten denselben
Lauf weiter. Geprüfte Stoppsignale gehen einem möglicherweise blockierenden
Journal-Schreibzugriff voraus. **568 lokale Tests bestehen, 43 sind
umgebungsabhängig übersprungen; Ruff und die Linux-Prüfung des Wächters bestehen.**
Die Linux-Prüfung simuliert Signale und Journal-Ausfälle. Erfolgreiche neue
Original-Rust-Läufe beider Engines und die vollständige Release-Abnahme bleiben
Voraussetzung für eine Produktionsfreigabe.

## Abschluss der Nachtabnahme am 15. Oktober

**Fortsetzung am 15. Oktober tagsüber:** Die ausdrückliche Antwort „den ganzen
Tag“ erweitert die Freigabe ausschließlich für dieselben sieben NAS-Dienste
bis 23:59:59 Berliner Zeit. Die geschlossenen Nachtjournale bleiben geschlossen.

Neue Fenster sind einzeln auf höchstens vier Stunden begrenzt, jeweils mit
15 Minuten Wiederherstellungsreserve und gesunden Diensten zwischen den Fenstern.

Zunächst wird das separate Profil `nas-8g-ssd-guest-swap-3840` geprüft: gleiche
8 GiB Gast-RAM, gleiches äußeres RAM-/Swap-Budget und dieselben NAS-Untergrenzen,
zusätzlich 4 GiB Swap ausschließlich auf der SSD-Testplatte im Gast. Der
ursprüngliche Builder behält 6 GiB und sein Swap-Verbot; Quellen und Tests
bleiben unverändert. Dieses Profil ist nur unter Leroy erfolgreich qualifiziert.

Der vollständige Original-Rust-Schritt muss erst unter beiden Engines bestehen,
bevor neue vollständige Release-Läufe zugelassen werden. Lokal bestehen
500 Tests, 43 sind umgebungsabhängig übersprungen; Ruff besteht.

Der Original-Rust-Lauf der Serie A unter Leroy ist vollständig
bestanden: 1.625 erfolgreiche und dieselben 32 ignorierten Tests, unverändertes
Inventar mit insgesamt 1.657 Fällen, vollständige Bereinigung und an dieselbe
unveränderte Quelle/Runtime gebundene Originalartefakte. Die NAS-Untergrenzen
blieben gewahrt, mit nur rund 77 MiB Reserve beim kleinsten beobachteten
Swapwert. Der separate Jenkins-Rust-Nachweis und die vollständige Paarabnahme
bleiben offen. Das Leroy-Fenster ist mit bytegeprüfter Archivierung und sieben
gesunden, stabilen Originaldiensten abgeschlossen. Die anschließende
Jenkins-Prüfung verwendete dasselbe Ressourcenprofil. Die Swap-Dateivorbereitung fordert nach jeweils 64 MiB für
geschriebene und synchronisierte Cache-Seiten die Freigabe an; diese
Vorbereitungskorrektur ist auf dem tatsächlichen NAS-Linux bytegeprüft.

Die fertige Swap-Konfiguration und ursprünglichen Fixture-Limits bleiben gleich.

Die danach erfasste Abweichung bei den Ausführungsplätzen ist inzwischen
angeglichen: produktiver Jenkins und beide Testsysteme haben zwei Plätze.

Details und Belegpfade stehen in `docs/nas-rust-memory.md`.

Die Jenkins-Referenz `graphato-postdeploy-quality #27` erreicht die ursprüngliche
Rust-Kompilierung ohne den früheren Runtime-Importfehler, wird jedoch vom
NAS-Swap-Schutz beendet. Der Wächter erfasst 2.006.128 KiB freien Swap bei
2.359.296 KiB Untergrenze und beendet ausschließlich die verifizierte Test-VM.

Der Originaljob bleibt als `FAILURE` erhalten. Kein neuer NAS-OOM; die sieben
Dienste sind seit **09:52:39 Berliner Zeit** wieder gesund und stabil. Die
produktive CI blieb unverändert. Die Rust-Prüfung ist damit unvollständig;
ein Fehler in den Graphato-Tests ist dadurch nicht nachgewiesen.

Die getrennte Serie `day-b-*` verwendete einen auf 7 GiB begrenzten Gast,
weiterhin 4 GiB Gast-Swap und dieselben äußeren Budgets, NAS-Untergrenzen sowie
ursprünglichen Builder-Limits. Beide CI-Controller bleiben während beider
Messungen aktiv. Zwei erfolgreiche Original-Rust-Läufe im neuen Profil sind
Voraussetzung für neue vollständige Release-Läufe. Das Profil ist noch nicht
praktisch qualifiziert worden; die älteren Ergebnisse bleiben erhalten.

Die Angleichung auf zwei Plätze ist inzwischen im eigenen NAS-Testpool live
gegen beide APIs geprüft. Die produktive Jenkins-Konfiguration, alle geprüften
Images und der Controller-Prozess blieben unverändert; nur der eigene Runner
wurde im Leerlauf neu gestartet. Die folgende Qualifikation unter Leroy lief im
separaten Fenster `resource-window-day-20261015-b-rust-leroy`.

Dieses Fenster ist inzwischen ebenfalls geschlossen: Der 7-GiB-Gast mit beiden
aktiven CI-Controllern erreicht erneut die NAS-Swap-Untergrenze. Leroy-Lauf #176
bleibt fehlgeschlagen erhalten; die Rust-Tests wurden nicht vollständig ausgeführt.

Alle sieben Dienste sind seit **10:41:13 Berliner Zeit** gesund und stabil.

Der NAS-OOM-Zähler blieb bei 3, die produktive CI unverändert. Die Testplatte
ist unabhängig bytegeprüft archiviert; das Jenkins-Gegenstück dieser Serie
wurde wegen der fehlenden Qualifikation nicht gestartet.

Die Serie `day-c-*` verwendete eine eigene SSD-Datei als Ablage für den
VM-Arbeitsspeicher (`nas-7g-ssd-file-memory-3840`). Die Gastkapazität und
ursprünglichen Fixture-Limits bleiben gleich; NAS-Swap und globale
Kernelparameter werden nicht verändert. QEMU 8.2.2 hat diesen Modus in einem
begrenzten 128-MiB-KVM-Probelauf bestätigt. Linux-Dateiprüfungen weisen offene
Rechte, Symlinks, Hardlinks und falsche Größen zurück. Vor jedem ursprünglichen
CI-Lauf muss zusätzlich ein separater 5.888-MiB-Speicherprobelauf innerhalb
6 GiB ohne Swap, zwei CPUs und 60 Sekunden Haltezeit alle Seitenmarker erhalten.

Dieser Probelauf ersetzt keine Graphato-Prüfung. C erreichte die vollständige
Belegung, scheiterte aber beim zusätzlichen Speicherlesen am eigenen
Diagnose-Timeout. Es wurde kein Graphato-Auftrag gestartet. Die nachträglich
ohne Boot oder Mount gelesenen Originaldiagnosen bestätigen intakte Stichproben,
aber keine vollständige Seitenprüfung. Alle sieben Dienste waren um
**11:30:13 Berliner Zeit** wieder gesund und stabil; die Testplatte ist
bytegeprüft archiviert. NAS-OOM-Zähler weiterhin 3.

Das Fenster `resource-window-day-20261015-d-rust-leroy` ist ebenfalls geschlossen.

Die zusätzliche Probe erreichte 3.072 MiB, bevor `docker inspect jenkins` bei
der lesenden Produktionsbeobachtung nach 20 Sekunden abbrach. Kein ursprünglicher
Graphato-Auftrag wurde gestartet. Alle sieben Dienste sind seit
**12:19:20 Berliner Zeit** gesund und stabil; der NAS-OOM-Zähler blieb bei 3,
die produktive CI und die Testinfrastruktur unverändert. Die Testplatte ist
bytegeprüft archiviert. Nach geordnetem VM-Stopp war die RAM-Datei vollständig
freigegeben; nur diese leere eigene Datei wurde entfernt.

Das Fenster `resource-window-day-20261015-e-rust-leroy` ist geschlossen.

Die zusätzliche Speicherprobe bestand vollständig: 5.888 MiB, mindestens
60 Sekunden gehalten, alle Seitenmarker intakt und der Prozess beendet.

Während dieser eigenen Zusatzlast verlor Graphato jedoch um 12:37:07 Berliner
Zeit seine PostgreSQL-Laufzeitsperre. Die offline gelesenen Originalprotokolle
zeigen vorher Datenbank-Pool-Timeouts, danach 35 Server-Neustarts und die
verwaiste Laufzeitsperre. Kein ursprünglicher CI-Auftrag wurde gestartet.

Alle sieben NAS-Dienste waren um **12:53:44 Berliner Zeit** wieder gesund und
stabil; Testplatte bytegeprüft archiviert, NAS-OOM unverändert bei 3.

Der Versuch F trennte den bestandenen Kapazitätsnachweis vom eigentlichen
Originalauftrag. Dieselben acht Dateien der VM-Ressourcenkonfiguration und die
Kapazitätsartefakte müssen bytegleich bleiben. Der neue CI-Lauf bekommt eine
frische Kopie der unveränderlichen Ausgangsplatte und keine vorherige
zusätzliche Speicherlast auf seine Anwendungsinstanz. Der Referenzbeleg nennt
ausdrücklich die fehlgeschlagene Anwendungsgesundheit in E; er ist kein
wiederverwendetes Graphato-Ergebnis. Die unveränderten Originaltests müssen
weiterhin unter beiden Engines vollständig neu laufen.

F ist ebenfalls geschlossen, alle sieben Dienste waren um **13:19:42 Berliner
Zeit** gesund und stabil. Ohne die große Speicher-Zusatzprobe verlor die frische
Anwendung dennoch um 13:14:06 ihre Laufzeitsperre: während der eigenen
1-GiB-/128-fsync-Datenträgerprüfung. Der gespeicherte Ausgangszustand zeigt fünf
Server-Neustarts und einen gestoppten Wartungscontainer; bis zum Stopp waren es
zwölf Server-Neustarts. Auch hier startete kein ursprünglicher CI-Auftrag.

Die Testplatte ist bytegeprüft archiviert, die leere RAM-Datei entfernt.

Das Leroy-Fenster `resource-window-day-20261015-g-rust-leroy` ist geschlossen;
die sieben Dienste waren um **14:24:48 Berliner Zeit** wieder gesund und stabil.

Die Testplatte ist bytegeprüft archiviert und vom SSD-Testbereich entfernt.

Das separate
Profil `nas-7g-ssd-file-memory-disk-qos` behält 7 GiB Gast-RAM, alle ursprünglichen
Builder-Limits und NAS-Schutzreserven. Nur die eigene VM erhält einen
bestmöglichen Schutz von 4 GiB gegen Cache-Verdrängung (`memory.low`) und eine
weiche Grenze von 5 GiB; die Testplatte verwendet direkten Host-I/O.

Globale NAS-Parameter bleiben unverändert. Die bisherigen 128 MiB/s Lesen und
32 MiB/s Schreiben werden jetzt direkt am virtuellen Laufwerk begrenzt. Die
SSD-RAM-Datei teilt sich dadurch nicht mehr dieselbe künstliche I/O-Drossel mit
der Datenbank. Die vorhandene QEMU-Version 8.2.2 bestätigt diese getrennte
Begrenzung in einer kleinen angehaltenen KVM-Instanz ohne Gast-OS. Der neue
Launcher liegt separat; Rechte und zulässige Optionen sind auf Linux geprüft.

Die vermutete Wirkung muss noch unter Last bestätigt werden.

Wegen des geänderten physischen Profils zählt der alte Kapazitätsbeleg hier
nicht. Beide Engines benötigen neue vollständige Speicher- und
Datenträgerprüfungen; dabei müssen die vier Anwendungscontainer gesund und
ihre Neustartzähler gleich bleiben. Erst danach darf der ursprüngliche
CI-Auftrag starten. Beide CI-Controller laufen mit
denselben zwei Ausführungsplätzen; die produktive CI wird weiter überwacht.

G hat diese Vorbereitung inzwischen bestanden: Speicherprobe vollständig,
Datenträgerprüfung bestanden, danach dieselben vier gesunden Container mit
weiterhin null Neustarts sowie HTTP/HTTPS 200. Die tatsächlichen QEMU-Limits
und fehlenden äußeren I/O-Quoten sind erfasst. Der ursprüngliche Rust-Auftrag
unter Leroy läuft seit **13:45:17 Berliner Zeit** (`e9b8e76d…`), Checkout
erfolgreich. Dieser Lauf (#177) endete inzwischen als **interrupted**:

Die Runner-Lease konnte unter NAS-I/O-Druck 45,733 Sekunden lang nicht
bestätigt werden, worauf der Worker die ursprüngliche Prüfung abbrach.

Die originale Graphato-Quittung enthält `Cancelled`, vollständige Bereinigung
und kein abgeschlossenes Rust-Inventar. Es wurden keine CI-Artefakte
veröffentlicht. Offline gelesene Originaldateien bleiben als Diagnosen erhalten
und ersetzen diese fehlenden CI-Artefakte nicht.

Alle sieben Dienste waren um **14:24:48 Berliner Zeit** wieder gesund und stabil;
produktive CI, Infrastruktur und Controller-Prozess blieben unverändert. Die
nachträglich gesicherte ursprüngliche Speicheraufzeichnung enthält 177 Proben,
davon 155 streng zugeordnet. NAS-RAM mindestens 3.348.748 KiB, freier Swap
mindestens 5.605.664 KiB, kein neuer NAS-OOM. Die NAS-Schutzreserven griffen nicht.

Heartbeat-Transportdaten zeigen überwiegend Warten auf HTTP-Antwortheader;
eine alleinige Ursache sämtlicher I/O-Wartezeiten ist damit nicht bewiesen.

Der ursprüngliche Jenkins-Qualitätsjob **#28 startete um 14:58:27 Berliner Zeit**
im gleichen G-Profil. Seine neue vollständige
Speicherprobe bestand; vor und nach den Zusatzproben blieben dieselben vier
Graphato-Dienste gesund und ohne Neustart. Das Fenster
`resource-window-day-20261015-g-rust-jenkins` ist seit **15:50:41 Berliner Zeit**
geschlossen, alle sieben Dienste sind gesund und stabil. Eine eng begrenzte Ausnahme erlaubt nur diese
Referenz nach dem belegten Leroy-Lease-Abbruch, abgeschlossener Wiederherstellung
und Archivierung. Quellen, Tests, physische VM-Konfiguration und
Leroy-Lease-Fristen bleiben dafür gleich. Vollständige Release-Läufe benötigen
weiterhin erfolgreiche ursprüngliche Rust-Prüfungen unter beiden Engines.

Seit **15:19:36 Berliner Zeit** überschreiten auch während dieses Jenkins-Laufs
wiederholte Leroy-Gesundheitsproben ihre Fünf-Sekunden-Frist; zusätzliche SSH-
und SQL-Wrapper-Abfragen scheitern ebenfalls. Der originale Jenkins-Job bleibt
bis zum letzten frischen Status um 15:34:40 aktiv. Damit ist eine Störung der
unveränderten Leroy-Steuerung auch unter der durch Jenkins gestarteten Rust-Last
beobachtet. Danach scheiterte die Abnahmesteuerung selbst: Ein SSH-Timeout beim
Statuslesen wurde nicht als Beobachtungslücke behandelt. Ihr äußerer Ablauf leitete
die Wiederherstellung ein; auch dessen SSH-Abfrage überschritt ihre Frist.

Die verifizierte Test-VM wurde gezielt geordnet beendet. Quellen und Tests wurden
nicht verändert; der ursprüngliche Job #28 ist nach der Bereinigung als
**ABORTED** gesichert. Es gibt keinen vollständigen Rust-Nachweis dieses Jobs.

Die unveränderte ursprüngliche Speicheraufzeichnung ist nach dem Stopp geborgen:

182 Proben, 99 streng zugeordnet, mindestens 3.500.092 KiB NAS-RAM und
5.478.424 KiB freier Swap, kein neuer NAS-OOM. Die VM endete regulär ohne
Reserveauslösung. Die Steuerungs- und Beobachtungslücken bleiben ausdrücklich
erhalten. Leseausfälle beobachten nun dieselbe CI-ID weiter; die feste äußere
Fenstergrenze bleibt bestehen. Wiederherstellungsabfragen dürfen nur im festen
Zeitbudget erneut dieselbe Wiederherstellung anfordern. Gezielte Gegenbeispiele
prüfen Status-, Artefakt- und Kinderbeobachtung sowie Transportfehler bei der
Wiederherstellung. Ein frischer Jenkins-Gegenlauf ist weiterhin erforderlich,
bevor Ressourcen oder Lease-Fristen von Leroy geändert werden.

Das neue Referenzfenster `resource-window-day-20261015-h-rust-jenkins` verwendet
dieselben physischen VM-Einstellungen und unveränderten Controller-/Worker-
Konfigurationen. Es endet spätestens **20:04:14 Berliner Zeit**, mit
Wiederherstellung ab 19:49:14. Neue Original-CI-Ergebnisse sind erforderlich;
das abgebrochene Jenkins-Ergebnis wird nicht wiederverwendet. Die neue
Beobachtungskorrektur und die abgeschlossene Wiederherstellung/Archivierung des
Vorgängers sind an den vorbereiteten Plan gebunden. Das Linux-Verhalten des
Wächters einschließlich wiederverwendeter PID und kritischer Reserve ist erneut
mit simulierten Signalen geprüft. Die vollständige Release-Freigabe bleibt offen.

Wiederholte Lesezugriffe benötigen jetzt keine Docker-Metadatenabfrage: Die
zuvor geprüfte Container-PID wird mit Boot-ID, Startzeit, Kommando-Prüfsumme,
Cgroup und Namensräumen vor und nach jedem Zugriff verifiziert. Beim produktiven
Jenkins werden zusätzlich Quell- und eingebundenes Datenverzeichnis anhand von
Gerät und Inode geprüft. Eine geänderte Identität führt zum Abbruch; sie wird
nicht stillschweigend neu ausgewählt. Diese Prüfung und ihre Ablehnungsfälle
sind auf dem tatsächlichen NAS-Linux bestätigt.

Alle Nachtfenster sind geschlossen. Die sieben pausierten NAS-Anwendungen waren
nach F um **05:28:30 Berliner Zeit** wieder gesund und stabil, vor dem
unveränderten Ende um 06:00. Test-VM und privater Jenkins sind gestoppt.

Der produktive Jenkins blieb in F ruhig; E überlappte mit dem unveränderten
Musik-Timer #244. Keine Produktionsumschaltung.

Die originalen Webarchive von Jenkins #26 und Leroy E sind lokal unabhängig
gegen den eingefrorenen Quellstand geprüft: **jeweils 42/42 Fälle in allen
21 Gruppen bestanden**, vollständige Bereinigung, keine Wiederverwendung.

Beide verwenden Graphato `0ad540dd578033d45e4d0c25d89fbe57b32102a4`,
dasselbe Runtime-Image und dieselbe Quellenprüfsumme. Quellen, Tests,
Ratenbegrenzungen und Fixture-Limits sind unverändert.

Auch der unveränderte Soak bestand unter beiden Engines: vier Tabs und
120 Eingaben, Leroy 312,867 Sekunden mit 172 erfolgreichen Event-Antworten,
Jenkins 314,178 Sekunden mit 199; jeweils nur HTTP 200 und keine Fehler.

Die frühere Vermutung, dieser Test könne wegen der Ratenbegrenzungen
grundsätzlich nicht bestehen, ist damit widerlegt.

Beide Frontend-Läufe führten dieselben 98 Komponententests aus: 97 bestanden,
eine identische Fokusprüfung in `chat-presentation.test.mjs:24` scheiterte.

Das gemeinsame Inventar hat SHA-256
`1837d31b51404a78aaadfcc910a760be6e87a3e45401cef3d511c8069377557e`.

Das belegt denselben Testfehler unter beiden Engines, noch keine abschließend
nachgewiesene Anwendungsursache. Formatprüfung und Clippy bestanden unter
beiden. Das vollständige ursprüngliche Rust-Inventar mit 1.657 Tests,
die originalen Qualitätsarchive und die Release-Gesamtquittungen fehlen.

Die Elternläufe sind fehlgeschlagen und bleiben erhalten.

In F griff um **05:20:45 Berliner Zeit** der unveränderte Swap-Schutz bei
2.357.208 KiB gegenüber 2.359.296 KiB Untergrenze. Der VM-Stopp dauerte bis
05:23:49 und war als erzwungen markiert; dabei wurden mindestens
1.532.392 KiB freier NAS-Swap beobachtet. Ein QEMU-Exitcode 0 bestätigt bei
erzwungenem Stopp keine saubere Gast-Dateisystemabschaltung. Der NAS-OOM-Zähler
blieb bei 3. Die Gastmessungen sind lückenhaft; daraus folgt keine vollständige
OOM-Abwesenheitsbescheinigung. Die ruhige produktive CI in F trennt diesen
Ressourcenabbruch von der Produktivüberlappung in E.

Drei weitere Fehler des Abnahmewerkzeugs sind im Quellstand behoben:

VM-Prozessidentitäten werden nach jedem Boot unabhängig von neuen Leroy-Lauf-IDs
registriert; fehlende optionale Cache-Diagnosen nach VM-Stopp verhindern die
Auswertung nicht; der unabhängige NAS-Wächter prüft dieselben RAM-/Swap-Grenzen
selbst und wartet im Reserve-Notfall nicht auf die Docker-API. Nur der zuvor
verifizierte VM-Initprozess darf dann nach SIGTERM und zehn Sekunden mit
SIGKILL beendet werden. PID-Startzeit, Cgroup und Kommando-Prüfsumme werden
vor jedem Signal erneut geprüft. Außerhalb dieses Notfalls bleibt die
210-Sekunden-Schonfrist bestehen. Anwendungen starten erst nach VM-Ende.

Diese Nachkorrekturen wurden nicht rückwirkend in geschlossene Fenster
eingespielt und noch nicht durch einen weiteren Volllauf belastet.

Lokal bestehen **353 Tests**, 43 umgebungsabhängige Prüfungen sind übersprungen;
Ruff und Diff-Prüfung bestehen. Auf dem tatsächlichen NAS-Linux wurden der
Prozessparser und die Signalentscheidungen mit simulierten Signalen geprüft;
dabei wurden keine echten Signale gesendet. Geschlossene Testplatten werden
erst nach unabhängigem byteweisem Prüfsummenvergleich auf HDD von SSD entfernt.

Die anschließende Forensik liest ausgewählte Dateien ohne Boot, Mount oder
Journal-Wiederholung; solche Dateien ersetzen keine originalen CI-Artefakte.

Beide geschlossenen Testplatten sind inzwischen unabhängig bytegeprüft auf HDD
archiviert; die jeweiligen SSD-Kopien sind entfernt. Die ausgewählten
Qualitätslogs beider Platten stimmen bei den Frontend-Prüfsummen mit den zuvor
lesend gesicherten Logs überein und bestätigen denselben Komponententestfehler.

Die abschließende NAS-Prüfung um 05:56 Berliner Zeit bestätigt alle sieben
Dienste gesund, unveränderte Konfigurationen, keine zusätzlichen Neustarts und
keinen neuen NAS-OOM.

Offen bleiben eine sichere Ressourcenqualifikation für den vollständigen
Rust-Schritt, danach ein vollständiges unverändertes Jenkins-/Leroy-Paar ohne
Produktivüberlappung sowie die getrennte Ursachenklärung des gemeinsamen
Fokusfehlers. Ein weiterer Lauf allein mit mehr Zeit behebt den nachgewiesenen
Swap-Abbruch nicht. **Keine Produktionsfreigabe.** In dieser Nacht startet
kein weiterer schwerer Build.

Private Belege: `test-results/nas-parity/followup/original-night-e-release-20261014/analysis.json`,
die beiden `*-final-original-web-validation.json`, die ergänzenden Qualitätslogs
und `resource-window-original-night-20261014-f/window-result.json` samt
Wiederherstellungsnachweis. Frühere Ergebnisse bleiben unverändert erhalten.

## Verlauf der NAS-Abnahme in der Nacht 14./15. Oktober

Die drei Kapazitätsproben sind beendet; sie erreichten 5, 5 und 5,5 GiB
zusätzliche anonyme Last bei unveränderten NAS-Abbruchwerten. 6 GiB sind
nicht qualifiziert. Das Kapazitätsfenster und die folgende Vorbereitung
wurden jeweils mit sieben gesunden und stabilen NAS-Anwendungen beendet.

Ein Fehler im Abnahmewerkzeug verlangte noch Reporting-Order 4 trotz
expliziter Auswahl von Order 0. Er ist korrigiert; außerdem werden einzelne
Original-Rust-Läufe und verschachtelte Release-Läufe korrekt beim
Wiederherstellungswächter registriert. Drei Gegenbeispiele scheitern mit
dem alten Quellstand. Mit den Korrekturen bestehen 292 lokale Tests,
43 umgebungsabhängige Prüfungen sind übersprungen. Graphato-Quellen, Tests
und Fixture-Grenzen sind unverändert. Vor diesem Vorbereitungsabbruch
wurde noch kein neuer Originaljob gestartet.

Die Fortsetzung `resource-window-original-night-20261014-b` ist beendet.

Leroys ursprünglicher Rust-Job wurde nach einer 77 Sekunden dauernden
Lease-Anfrage unterbrochen. Beim privaten Jenkins-Build #25 griff später
der unveränderte NAS-RAM-Schutz: 83.276 KiB verfügbar gegenüber der
Untergrenze von 131.072 KiB. Beide Laufwerke sind nach unabhängigem
Prüfsummenvergleich archiviert. Alle sieben Anwendungen wurden gesund
und stabil wiederhergestellt; der produktive Jenkins blieb unverändert.

Die Fortsetzung `resource-window-original-night-20261014-c`

verwendete denselben 8-GiB-Gast mit niedrigerem `memory.high=3584 MiB`.

Eine zusätzliche Transportdiagnose im Worker und eine lesende Prozess-/SQL-
Beobachtung sollen den Lease-Stillstand erklären; eine schnelle allgemeine
API-Antwort allein belegt keine erfolgreiche Lease-Erneuerung.

Die bereits korrigierte Erneuerungsschleife ist jetzt auch im tatsächlichen
Runner installiert, der sie während des Jobstarts verwendet. Das Linux-Image
besteht alle 23 Tests; das frühere Image reproduziert fünf Gegenbeispiele.

Das diagnostische Jobimage besteht 28 Linux-Tests. Lease-Grenzen bleiben
45 Sekunden lokal und 90 Sekunden am Server; Quellen, Tests und Fixture-Limits
von Graphato bleiben unverändert. Lokal bestehen 309 Tests bei 43
umgebungsabhängigen Auslassungen. Erst zwei erfolgreiche vollständige
Original-Rust-Inventare erlauben die Release-Läufe.

C ist ebenfalls geschlossen, alle sieben Anwendungen sind gesund und
stabil. Leroy hielt seine Lease während des gut 21-minütigen Jobs.

Die VM wurde bei 2351552 KiB freiem NAS-Swap gegenüber 2359296 KiB
Untergrenze sauber heruntergefahren; 724860 KiB NAS-RAM waren dabei
verfügbar. Die anschließende Diagnoseverbindung fiel dadurch aus.

Jenkins und vollständige Releases wurden in C nicht gestartet.

Der Testimage-Bau bestand; die ursprüngliche Rust-Kompilierung erreichte
das Graphato-Paket, aber keinen vollständigen Testabschluss.

Die neue Diagnose belegt kurze PostgreSQL-WAL-Wartezeiten und bei anderen
Ausschlägen Btrfs-/Block-I/O-Wartezustände des tatsächlichen Heartbeat-
Threads samt zusätzlichen Page Faults. Das eigene Docker-Worker-Dateisystem
liegt noch auf `/volume1` (Btrfs); Controller/PostgreSQL liegen auf der SSD.

Diese Befunde erklären konkrete neue Verzögerungen, beweisen aber nicht
rückwirkend die Ursache der alten 77-Sekunden-Anfrage. Die zuerst versehentlich
beobachteten Init-Prozessdaten sind getrennt erhalten; die korrigierte
Beobachtung erfasst den Python-Worker. Neun Regressionstests sichern dessen
Auswahl ab. Die Testplatte wird außerhalb der CI-Last bytegeprüft archiviert.

Die C-Testplatte ist inzwischen unabhängig per SHA-256 geprüft archiviert.

Der eigene Docker-Testpool läuft jetzt mit einem frischen SSD-Laufzeitverzeichnis.

Das geprüfte Worker-Image bleibt identisch; alle 28 Linux-Tests bestehen auch
dort. Private Jenkins-/Gitea-Container wurden aus Sicherungen ihrer bisherigen
Dateisysteme mit denselben Einstellungen und Daten-Volumes übernommen.

Docker stellt lediglich den bisherigen OOM-Standardwert explizit als `false`

statt `null` dar. Der vollständige alte Pool bleibt erhalten und als benanntes
Volume referenziert. Controller, PostgreSQL und produktive Dienste blieben
aktiv. Die Fehlversuche der Vorbereitung und Rücknahmen sind separat erhalten.

Die neue Fortsetzung D verwendet auf beiden Seiten 3840 MiB `memory.high`,
die SSD-Laufzeit und erneut frische VM-Baselines. Sie bindet die tatsächlichen
RAM-/Swap-Schutzabbrüche von B/C und den SSD-Prüfbeleg. Lokal bestehen 319
Tests bei 43 umgebungsabhängigen Auslassungen. D ist weiterhin eine laufende
Abnahme, kein Nachweis erfolgreicher Original-Rust- oder Release-Läufe.

D ist vor jedem CI-Start durch eine veraltete Container-ID-Prüfung im
Abnahmewerkzeug beendet worden; alle sieben Dienste sind gesund wiederhergestellt.

Die aktive Prüfung bindet jetzt den belegten privaten Jenkins einschließlich
Image und unverändertem Daten-Volume. Sechs Tests prüfen insbesondere, dass
Name, fremde ID, fremdes Image oder andere Daten keine Ersatzidentität erlauben.

Die lokale Suite besteht mit 325 Tests bei 43 umgebungsabhängigen Auslassungen.

E führt beide vollständigen Original-Release-Pipelines direkt aus. Ihre Rust-
Prüfungen bleiben enthalten und für die Abnahme erforderlich; zusätzliche
separate Rust-Wiederholungen entfallen. Vor der externen E-Vorbereitung meldete
der Mail-Dienst vorübergehend einen IMAP-Routingfehler. Die Verbindung war
anschließend wieder erreichbar; derselbe Container bestand nach einem Neustart
einen tatsächlich erfolgreichen Poll bei unveränderter Konfiguration. Die rein
lesende fehlgeschlagene Vorbereitung bleibt separat erhalten. Endzeit und
Abbruchwerte bleiben unverändert; es liegt weiterhin kein vollständiger
erfolgreicher Release-Vergleich vor.

Die ausdrückliche Nachtfreigabe endet weiterhin spätestens am 15.10. um
06:00 Uhr Berlin; der NAS-Wächter beginnt um 05:45 Uhr mit der Wiederherstellung.

Es erfolgt keine Produktionsumschaltung.

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

- Technische und visuelle Prüfung von insgesamt 429 NAS-Ansichtsprüfungen auf Desktop
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

Die anschließende Kapazitätsdiagnose mit allen sieben NAS-Anwendungen aktiv
hält 4608 MiB zusätzlichen anonymen Gastspeicher. Reporting-Order 0 allein
qualifiziert das Ziel von 6144 MiB nicht: Der nächste Schritt wird vorsichtig
vor der ursprünglichen Swap-Schutzreserve verweigert. Die Testbelegungen sind
freigegeben und die VM ist aus. Lesende Plattenprüfungen bestätigen außerdem,
dass die Cachewächter während beider ursprünglicher Rust-Versuche aktiv waren.

Ein einmaliger, höchstens einstündiger Kapazitätstest mit pausierten sieben
Diensten und zusätzlich inaktivem privatem Jenkins ist konkret vorbereitet;
seine neue Freigabe ist inzwischen erteilt. Dieses einzelne Fenster läuft
seit 21:45:54 Uhr Berliner Zeit; seine absolute Frist ist 22:45:54 Uhr.

Ein abgeschlossenes Kapazitäts- oder Wiederherstellungsergebnis liegt dafür
noch nicht vor. Die beiden alten Fenster bleiben geschlossen.

Details: [Speicherdiagnose](nas-rust-memory.md) und
[vorbereiteter begrenzter Test](nas-resource-window.md).

Die aktuellen lokalen Prüfungen bestehen mit 266 erfolgreichen Tests und
43 Skips: 34 PostgreSQL-Tests benötigen die gesonderte Linux-Testdatenbank,
neun SCM-Prüfungen ihre isolierte Baseline. Der unveränderte Controller besitzt
weiter den früheren getrennten Nachweis aller 34 echten PostgreSQL-Tests.

Die neuen Diagnose-/Freigabehelfer bestehen Ruff; elf zusammengesetzte
Remote-Payloads sind auf Syntax und undefinierte Namen geprüft. Dies qualifiziert
die Vorbereitung, keine neue NAS-Dienstpause oder Graphato-Release-Abnahme.

Aktueller Stand nach den zwei neu genehmigten Fenstern vom 14. Oktober:

Beide sind geschlossen und alle sieben NAS-Dienste wieder gesund. Die neue
Rust-Vorprüfung besteht unter keiner Engine; deshalb wurde kein neuer
vollständiger Releasejob gestartet. Leroy verliert nach einer 44,071 Sekunden
langsamen Bestätigung seine lokale Lease; der private Jenkins erreicht die
unveränderte NAS-Swap-Schutzreserve. Graphatos eingefrorener Commit, Quellen,
Tests und Fixture-Limits bleiben unverändert.

Der belegte zusätzliche Drei-Sekunden-Wartefehler im Worker ist anschließend
behoben und das qualifizierte Image ausschließlich im eigenen NAS-Teststack
installiert. 250 lokale Tests bestehen (neun Skips); unter NAS-Linux bestehen
22 Worker-Tests und ein gesonderter Runner-Test im jeweiligen Laufzeitimage.

Fünf Gegenbeispiele scheitern mit dem alten Worker. Die 45-/90-Sekunden-Fristen
bleiben gleich. Der neue Worker hat noch keinen ursprünglichen Rust- oder
vollständigen Releasejob bestanden. Details und Grenzen stehen in
[nas-rust-memory.md](nas-rust-memory.md) und
[nas-resource-window.md](nas-resource-window.md). Die folgenden Serien bleiben
historische Nachweise und ersetzen diese offene Abnahme nicht.

Neueste Fortsetzung am 12. Oktober: Die gemeinsame Serie `n` ist unter beiden
Engines terminal beendet und unvollständig abgenommen. Die zuvor gezielt
nachgestellte Blockade durch Systemdiagnosen ist korrigiert und im eigenen
NAS-Stack installiert; identische echte Probejobs belegen ihre Wirkung.

Unter ursprünglicher Clippy-Last treten bei beiden Engines trotzdem
Controller- und Docker-Exec-Timeouts sowie starker NAS-Speicher-/I/O-Druck auf.

Details: [nas-control-logging.md](nas-control-logging.md).

Der ausdrücklich eingefrorene Originalstand bleibt
`0ad540dd578033d45e4d0c25d89fbe57b32102a4`. Anwendung, Originaltests und Ratenlimits
werden für die aktuelle Ursachenuntersuchung nicht geändert. Der gesonderte
Soak-Testtreiber-Vorschlag ist zurückgestellt.

Beide neuen Ursprungsläufe verwenden jeweils eine frische Basis und das Profil
`nas-6g-ssd-soft-ram-3584`. Manifest, Gast-/Host-Ressourcen, I/O-Limits und
Speichergrenzen stimmen vor der Ausführung überein. Die abschließende Aufnahme
bestätigt unveränderte Controller-/Runner-/Docker-/PostgreSQL-Images,
Konfiguration, Mounts, Durabilität und sechs Ausführungshilfen innerhalb dieses
Paars. Der Supervisor ist jetzt bei beiden derselbe korrigierte Stand `620623…`.

| Originalnachweis | Jenkins | Leroy |

| --- | --- | --- |

| Web: 21 Gruppen / 42 Fälle | 42 bestanden; originales CI-Artefakt geprüft | 41 bestanden / einer fehlgeschlagen; vollständiges originales CI-Artefakt geprüft |

| Python: 195 Tests / sechs Suiten | bestanden, ergänzendes Zielprotokoll | bestanden, ergänzendes Zielprotokoll |

| Komponenten: 98 Fälle | 97 bestanden / einer fehlgeschlagen, ergänzendes Zielprotokoll | dieselben 97 bestanden / derselbe Fehler, ergänzendes Zielprotokoll |

| Formatprüfung | bestanden, Zielquittung | bestanden, Zielquittung |

| Clippy / Rust / übrige Qualität | VM-Abbruch; vollständiges Inventar fehlt | VM-Schutzstopp und Lease-Abbruch; vollständiges Inventar fehlt |

| Ursprünglicher Elternlauf | #20 fehlgeschlagen | `8379bdf2005a4ae8b01b7997c738b1f8` unterbrochen, Lease abgelaufen |

| Produktive Jenkins-Builds im vollständigen Fenster | keine | keine; vollständige Historienprüfung bestätigt |

Bei beiden Engines wird die unveränderte freie Swap-Schutzreserve unterschritten.

Ein vollständiger Original-CI-Qualitätsnachweis und die Release-Gesamtquittung
fehlen bei beiden; ergänzende Zielprotokolle ersetzen sie nicht. Leroy meldet
zusätzlich `Runner lease expired; external effects require reconciliation`.

Seine gemessenen API-Timeouts beginnen vor dem VM-Schutzstopp. Beide VMs werden
an der unveränderten Swap-Reserve zwangsweise beendet; ein sauberer
Gast-Dateisystemabschluss wird nicht behauptet.

Die zusätzliche Browserabweichung ist `dev-environments`: Unter Leroy fehlt
ein Expand/Collapse-Button innerhalb der ursprünglichen fünf Sekunden, unter
Jenkins besteht der Fall. Beide Originalabläufe enthalten 502-Antworten während
des geprüften Serverneustarts. Deren Anzahl beweist keine Ursache. Der Fehler
identifiziert den betroffenen Browser-Client nicht eindeutig; die Aufnahmen
enthalten Hauptseite und Kollaborator, keine Besitzer-Ansicht. Die Ursache bleibt
offen, und Anwendungspatches gelten weiterhin nicht als Voraussetzung für Leroy.

Die vollständigen produktiven Jenkins-Historien bestätigen ruhige Messfenster
einschließlich Wiederherstellung und Jenkins-Datenträgerarchivierung. Andere
NAS-Hintergrundlast ist nicht als identisch belegt. Produktiver Jenkins führt
Postdeploy-Qualität auf einem externen Linux-Ziel aus; unsere zusätzliche
Ziel-VM läuft auf dem NAS. Diese Isolation belegt keine Produktions-Performanceparität.

Alle ursprünglichen CI-Läufe sind terminal, VM und privater Test-Jenkins sind
aus, und kein Worker dieses Vergleichs läuft weiter. Jenkins-Datenträger und
frühere Fehler bleiben erhalten. 18 neue technische und direkt gesichtete
UI-Ansichten bestehen mit einem geprüften JSON-Download und Bildprüfsummen;
insgesamt sind 377 historische NAS-Ansichten geprüft. Die vollständige
Release-Abnahme bleibt offen. Details: [nas-full-release.md](nas-full-release.md).

Zusätzliche Nachprüfung am Abend des 12. Oktober: Die drei eigenen Steuerdienste
erhalten jetzt eine wirksame gemeinsame Speicherreservierung von 320 MiB in
einer eigenen obersten Cgroup. Ein echter ursprünglicher Clippy-Lauf endet nach
dem regulären Swap-Schutzstopp des Zielgasts als fehlgeschlagen, ohne den früheren
Lease-Abbruch. Seine vollständige Anwendungsprüfung fehlt weiterhin. 52
gespeicherte Gesundheitsmesspunkte haben keinen API-Timeout; die Beobachtung
enthält jedoch Docker-Exec-Lücken und einen echten HTTP-500-Anmeldungsfehler.

Als konkreter weiterer Mechanismus ist ein PostgreSQL-Namensauflösungsfehler
belegt. Eine begrenzte DNS-Ausfallprobe bestätigt die Wirkung eines Hosteintrags;
die eigene PostgreSQL-Adresse ist anschließend fest reserviert und der Eintrag
installiert. Images, Daten, Ressourcenlimits und Fristen bleiben gleich.

Die unveränderte einzelne `dev-environments`-Gruppe scheitert danach auch unter
Jenkins #23 an derselben ursprünglichen Fünf-Sekunden-Assertion des Expand-Buttons.

Ihr originales CI-Archiv, Quellenbindung, vollständiger einzelner Fall und Cleanup
sind geprüft. Der Zusatzbeobachter dieses ersten Versuchs ist unvollständig und
kein verlustfreier Netzwerknachweis. Danach bestehen Leroy #158 und Jenkins #24
denselben unveränderten Fall auf frischen Basen. Ihr Originalarchiv und Cleanup,
gleiche Infrastruktur und gleiche Beobachterquellen sind bestätigt. Die
wechselnden Ergebnisse sind damit unter beiden Engines vorhanden; eine
generelle Ursache des historischen Unterschieds wird nicht behauptet. Auch die
verbesserten Zusatzspuren enthalten Verluste und Neustartlücken.

Zwölf weitere Desktop-/Mobilansichten der tatsächlichen Fehler- und Erfolgsläufe
sind technisch und direkt visuell geprüft. Zusätzlich ist eine Unterdimensionierung
für den originalen Ressourcenvertrag festgestellt: Der Postdeploy-Builder hat
6 GiB ohne Swap, der gesamte Gast bisher nur etwa 5,8 GiB nutzbaren RAM.

Zwei tatsächliche Clippy-Versuche mit einem getrennten 10-GiB-Gast behalten
Quellen, Tests, ursprüngliche Builder-/Fixture-Limits und NAS-Schutzreserven.

Das Profil mit 4 GiB bevorzugtem QEMU-RAM unterschreitet die RAM-Reserve;
das Profil mit 3,5 GiB unterschreitet die Swap-Reserve. Beim zweiten verliert
Leroy zusätzlich seine Lease. Seine 57 erhaltenen Gesundheitsmesspunkte haben
keinen API-Timeout, enthalten aber 21 SQL-Wrapper-Lücken. Die vollständige
Ursache des Lease-Verlusts ist offen. Die Steuerdienste sind nach dem VM-Stopp
gesund; fünf direkte Datenbankproben bestehen mit höchstens 20 ms. Dies
belegt keine Stabilität über die gesamte ursprüngliche Last.

Alle begonnenen originalen CI-Läufe sind terminal, VM und privater Jenkins
aus, keine eigenen Jobworker aktiv. Produktive Jenkins-Historien sind ruhig.

Sechs weitere Desktop-/Mobilansichten des tatsächlichen Abbruchs bestehen
technisch und nach direkter Sichtprüfung; insgesamt 395 NAS-Ansichten.

78 gezielte lokale Tests und Ruff der geänderten Helfer bestehen. Für
zukünftige Einzelgruppen werden sichere zeitgestempelte Worker-Lease-Meldungen
automatisch vor der normalen Containerbereinigung gesichert. Ein begrenztes
Testfenster mit mehr NAS-Reserve wurde anschließend freigegeben und ausgeführt:

[nas-resource-window.md](nas-resource-window.md).

Die vollständige Release-Abnahme und Produktionsfreigabe bleiben offen. Details:

[nas-control-memory.md](nas-control-memory.md).

Das ausdrücklich freigegebene Ressourcenfenster am 13. Oktober (Berliner Zeit)

pausiert sieben NAS-Anwendungen innerhalb einer festen Zweistundenfrist.

Der erste Clippy-Versuch mit 4 GiB bevorzugtem VM-RAM unterschreitet weiterhin
die RAM-Reserve. Alle sieben unveränderten Container werden danach gesund
wiederhergestellt. Eine gezielte Folgeprobe mit 3,5 GiB bevorzugtem VM-RAM
läuft innerhalb derselben ursprünglichen Endzeit 02:20:24 Uhr.

Leroy #162 besteht dabei erstmals die vollständige unveränderte einzelne
Originalgruppe `server-clippy` auf der NAS-Ziel-VM. Die Originalquittung und ihr
Archiv sind in Quellenbindung und Prüfsumme verifiziert; vollständiger Cleanup,
kein wiederverwendeter Erfolg, kein Lease-Verlust. Alle vier Basisdienste sind
nachher gesund und ohne Neustart. Die Originalarchive und Diagnoselücken bleiben
erhalten. Der private Jenkins #21 besteht anschließend dieselbe Originalgruppe.

Runtime-/Quellen-/Bauzeitpunkt-Identität, VM-Profil, fünf aufgelöste Build-Basis-
Image-Digests, Steuerinfrastruktur und sechs Ausführungshilfen stimmen überein.

Auch nach Jenkins bleiben alle vier Basisdienste gesund.

Die Nachprüfung belegt allerdings einen Controller-OOM am 256-MiB-Limit während
der Jenkins-Gegenprüfung, mit automatischem Neustart und kurzzeitiger äußerer
API-Unerreichbarkeit. Die Zusatz-SQL-Diagnose teilte dieses Budget mit dem API-
Prozess. Sie läuft künftig im PostgreSQL-Container; `/health/ready` prüft weiter
den tatsächlichen Controller-DB-Pfad. Das eigene Controllerlimit ist nach einer
getrennten Grundqualifikation auf 512 MiB ohne Swap erhöht, ohne Container-
Neuerstellung, weiteren Neustart oder Änderungen anderer Dienste. Zehn parallele
authentifizierte Metadaten-Abfragesequenzen bestehen ohne neuen OOM. Dies ist
keine erneute vollständige NAS-Lastabnahme. Die vorbereitete Produktions-
Konfiguration ist entsprechend korrigiert, weiterhin nicht aktiviert.

Die sieben Dienste laufen mit unveränderten Containern, Images und Konfigurationen
um 02:07 Uhr wieder und sind vor 02:10 Uhr gesund und stabil geprüft. Das feste
Zweistundenfenster bleibt mit insgesamt rund 107 Minuten eingehalten, einschließlich
der zwischenzeitlichen Wiederherstellung. Alle CI-Läufe sind terminal, Test-VM
und privater Jenkins aus, kein eigener Jobworker oder Probecontainer aktiv.

Die vollständigen nativen Jenkins-Historien bestätigen ruhige Fenster.

88 gezielte lokale Tests bestehen. Zwölf weitere Desktop-/Mobilansichten der
tatsächlichen Fehler- und Erfolgsläufe sind technisch und direkt visuell geprüft;
insgesamt 407 historische NAS-Ansichten. Der einzelne Clippy-Erfolg ist keine
vollständige Qualitäts- oder Release-Abnahme. Ablauf und Originalbelege:

[nas-resource-window.md](nas-resource-window.md).

Die folgenden Ergebnisse beschreiben frühere Vergleiche:

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

Der Vergleich **Jenkins, Leroy, Leroy, Jenkins** läuft direkt
im vorhandenen isolierten NAS-Testdaemon, mit frischer Fixture pro Probe,
originalem CI-#23-Runtime-Inhalt und einem gemeinsamen Browser-Worker aus dem
unveränderten Original-Dockerfile. Ein separater passiver Beobachter erfasst
ausschließlich HTTP-Metadaten; sein Aufwand bleibt eine Messgrenze.

Am 11. Oktober ist der Runtime-Importfehler reproduziert und behoben: Der
Vorbereitungshelfer leitete das Archiv ohne `docker exec -i` weiter. Ein
Transportversuch empfängt damit null statt 1.152 Bytes; das unveränderte Archiv
liefert beim ursprünglichen Aufruf `unrecognized image format`. Mit weitergeleiteter
Standardeingabe wird dasselbe Archiv erfolgreich importiert. Alle 20 ursprünglichen
RootFS-Schichten, das Image-Config-Digest und das Serverprogramm sind bestätigt.

Das unter Docker 29 angezeigte Manifest-Digest unterscheidet sich erwartungsgemäß
vom ursprünglichen Config-Digest; beide Inhalte sind separat geprüft.

Alle 2.339 Quelldateien sind gegenüber dem Originalarchiv verifiziert. Der
gemeinsame Browser-Worker ist auf dem NAS aus dem unveränderten Original-Dockerfile
gebaut; dessen ursprüngliche Prüfungen bestehen. Alle 53 zuvor festgehaltenen
Test-/Treiberdateien sowie Node 24.14.1 und Playwright 1.63.0 stimmen überein.

Das Originalprofil wird nur vorübergehend und ohne Änderungen an anderen
AppArmor-Profilen geladen. Der vollständige passive Beobachter besteht auch
Dateischreiben und geordnetes Beenden; eine frühere Vorprüfung prüfte nur den
Namespace-Eintritt und Paketfilter.

Die erste Jenkins-Probe scheitert beim PostgreSQL-Zugriff während des Fixture-
Starts, bevor der Soak-Test ausgeführt wird. Cleanup ist bestätigt; dieser
Infrastrukturfehler zählt nicht als ausgeführte Soak-Probe. Ein separater
Startversuch mit dem ursprünglichen Fixture-Helfer bringt PostgreSQL und Graphato
erfolgreich in den gesunden Zustand. Die Ursache des ersten Startfehlers ist
noch offen. Neue Serien verwenden eigene Kennungen, sodass frühere Quittungen,
Jenkins-Builds und Testverzeichnisse erhalten bleiben.

Die erste vollständige Serie `20261011-c` führt alle vier Original-Soaks aus:

Jenkins scheitert nach 18,427 Sekunden und besteht später nach 316,356 Sekunden;
Leroy besteht zunächst nach 310,389 Sekunden und scheitert danach nach 31,288
Sekunden. Beide kurzen Fehler liegen beim Senden eines Prompts. Alle vier
Cleanups und ruhigen Produktionsfenster sind bestätigt; beide CI-Systeme
übernehmen das Originalergebnis korrekt. Die Abweichung tritt damit in dieser
Serie innerhalb beider Engines auf und ist nicht ausschließlich Leroy zugeordnet.

Die HTTP-Auswertung dieser Serie ist unvollständig: Der Beobachter verwendet
zunächst `ETH_P_IP` und verpasst ausgehende Bridge-Antworten. Die ursprünglichen
positiven Qualifikationsflags prüfen nur Paketverluste und Parserfehler und sind
für vollständige HTTP-Statusaussagen zu weit gefasst. Die ergänzte Qualifikation
weist alle vier Antwortspuren als unvollständig aus; die Rohdaten bleiben erhalten.

Eine separate NAS-Transportprobe reproduziert fünf Anfragen ohne Antworten.

Mit alleiniger Änderung auf `ETH_P_ALL` werden dieselben fünf Antworten samt
kontrollierter 429 erkannt. Die korrigierte Fassung besteht ebenfalls, hält
keine Rohpakete oder Authentifizierungswerte fest und verwendet Kernel-Zeitstempel.

Die Serie `20261011-d` scheitert vor dem ersten Originalfall. Ihre Startdiagnose
belegt einen Fehler in der unveränderten Fixture-Startbedingung: Der Unix-Socket-
Healthcheck akzeptiert den temporären Initialisierungsserver um 10:12:05,202 UTC.

Graphato startet während dessen Abschaltung und meldet den Datenbankfehler um
10:12:11,702 UTC; der endgültige TCP-Listener startet erst um 10:12:12,419 UTC.

Das ist ein belegter Start-Race dieses Jenkins-Versuchs, keine ausgeführte
Soak-Probe. Der ursprüngliche Healthcheck wird nicht gepatcht. Der Fehler wird
erhalten. In `20261011-e` besteht die erste Jenkins-Probe nach 308,510 Sekunden;
alle 120 Prompt-Antworten sind als HTTP 200 zugeordnet. Die folgende Leroy-Fixture
scheitert vor dem Soak erneut beim Datenbankstart. `20261011-f` übernimmt nur die
bereits ausgeführte, geprüfte Jenkins-Probe und setzt die Reihe fort. Quellen,
Images und Helferprüfsummen stimmen dabei überein; kein ausgeführter Test wird
wiederholt. Der Test-Jenkins wird zwischen diesen Versuchen neu gestartet, was
als Messgrenze festgehalten wird. Die Jenkins-HTTP-Spur hat 122 verlorene Pakete
und unvollständig zugeordnete Antworten; sie belegt die 120 Prompt-Antworten,
aber keine vollständige Abwesenheit von 429 in sämtlichen API-Anfragen.

Anwendung, Originaltests, Images und Grenzwerte bleiben unverändert.

Die fortgesetzte Serie `20261011-f` ist abgeschlossen:

| Probe | Originalergebnis | Soak-Dauer |

| --- | --- | --- |

| Jenkins 1, übernommen aus `20261011-e` | Bestanden | 308,510 s |

| Leroy 1 | Bestanden | 315,857 s |

| Leroy 2 | Bestanden | 309,201 s |

| Jenkins 2 | Bestanden | 309,814 s |

Alle vier Läufe verarbeiten 120 Prompts mit vier Tabs. Ihre CI-Ergebnisse stimmen
mit den Originaltests überein, ihre Fixtures sind vollständig bereinigt, und die
Produktionswächter bestätigen ruhige Jenkins-Fenster. Runtime- und Worker-Inhalte
sind identisch. Bei der letzten Probe verliert die lokale Überwachung eine
lesende SSH-Abfrage; der bereits gestartete Jenkins-Build läuft weiter und wird
ohne erneuten Teststart vollständig gesammelt. Der abschließende Produktions-
wächter bestätigt das gesamte Zeitfenster. Test-Jenkins ist wieder gestoppt,
das temporäre AppArmor-Profil entfernt; andere Profile bleiben unverändert.

Der korrigierte Beobachter erfasst in allen vier Spuren sämtliche 120 Prompt-
Antworten als HTTP 200. Er verliert jedoch 122/117/155/159 Kernel-Pakete; die
Gesamtspuren sind deshalb für vollständige Status- oder Rate-Limit-Aussagen
weiterhin unqualifiziert. Die früheren kurzen Soak-Fehler und die historische
Qualitätsabweichung sind damit nicht ursächlich erklärt. Die neue erfolgreiche
Serie ist ein Nachweis des originalen Soak-Aufrufs durch beide Engines, keine
erneute vollständige Release-Abnahme und kein Beweis identischer Hintergrundlast.

Die Ergebnisdarstellung wird anschließend mit echten Leroy-Läufen erneut geprüft:

zwei Erfolge, ein ausgeführter Soak-Fehler und ein Fixture-Startfehler, jeweils
Graph/Konsole, Ergebnisse und Artefakte auf Desktop und Mobilgerät. Alle 24
Screenshots sind technisch und visuell geprüft; Statusfarben und Zeitachsen
stimmen, kein Seitenüberlauf oder Browserfehler tritt auf. Alle 16 Artefakt-
Downloads stimmen in Größe und SHA-256. Damit sind insgesamt 251 NAS-Ansichten
geprüft. Die Berichte stehen im [NAS-Vergleich](nas-parity.md).

Die lokale Leroy-Docker-Umgebung und die zuvor durch OOM beendete Windows-Test-VM
bleiben gestoppt. Bei der Bereinigung am 7. Oktober blieb gemäß Nutzerwunsch
lokal ausschließlich NameFinder aktiv. Am 9. Oktober sind bei der abschließenden
Veröffentlichungsprüfung zusätzlich zwei Graphato-Entwicklungscontainer aktiv;
die Aussage zur Bereinigung ist deshalb eine datierte Momentaufnahme.

Volumes, Images und bisherige Nachweise sind erhalten.

## Weiterer Plan

Am 11. Oktober läuft die zusätzliche vollständige Release-Abnahme auf einem
eigenen Linux-Kernel direkt auf dem NAS. Der unveränderte vorbereitete Snapshot
ist exportiert und mit SHA-256 geprüft; die Windows-Test-VM bleibt ausgeschaltet.

Jenkins und Leroy erhalten getrennte neue Overlays derselben Basis. Die erste
NAS-VM-Serie ist vor Abschluss der Prüfgruppen wegen eines Gast-Datenträgerfehlers
gescheitert; Jenkins #9, Web #12 und Qualität #10 bleiben als unvollständiger
Fehlversuch erhalten. Leroy wurde darin nicht gestartet. Eine neue Serie mit
symmetrisch angepasster VM-Speicher-/Cache-Konfiguration und zusätzlicher
Flush-Fehlerprotokollierung scheitert ebenfalls vor den Browserfällen: Der NAS-
Schutzdienst `earlyoom` beendet QEMU bei fast erschöpftem Swap. Jenkins #10, Web #13
und Qualität #11 bleiben rot; Leroy ist darin nicht gestartet. `earlyoom` beendet
außerdem den NAS-Prozess `taskmgr_serv`, der bereits automatisch neu gestartet
und geprüft ist. Produktive Jenkins-Buildstände bleiben unverändert. Die nächste
Serie mit sechs GiB bricht der eigene Guard bei knapp 512 MiB verfügbarem RAM
und noch rund 3,5 GiB freiem Swap ab. Serie `d` begrenzt beide Gäste
auf 4,5 GiB und richtet den Guard an der tatsächlich geprüften NAS-Konfiguration
aus: 128 MiB verfügbarem RAM und 2,25 GiB freiem Swap bleiben als Mindestreserve.

Freie Gastseiten werden weiterhin zurückgegeben. Die ursprünglichen Fixture-
Limits bleiben unverändert; ein Guard-Abbruch zählt nicht als ausgeführte
Release-Abnahme. Die
konkrete Ursache des ersten Flush-Ausfalls ist noch offen. Vorbereitung, Schutz vor
produktiver Jenkins-Last und Wiederaufnahme stehen in
[nas-full-release.md](nas-full-release.md). Die Rohbelege liegen unter
`test-results/nas-parity/followup/full-release-nas-20261011-a` und
`test-results/nas-parity/followup/full-release-nas-20261011-b` sowie
`test-results/nas-parity/followup/full-release-nas-20261011-c` und
`test-results/nas-parity/followup/full-release-nas-20261011-d`.

In Serie `full-release-nas-20261011-d` sind Jenkins #12, Web #15 und Qualität #13
fehlgeschlagen. Web enthält 28 von 42 Originalfällen, davon 27 bestanden;
14 Fälle fehlen nach frühen Abbrüchen. Qualität führt die 195 Python- und
98 Komponententests aus (97 Komponententests bestanden), aber der Gastkernel
beendet Clippy und den Rust-Compiler wegen Speichermangels. Rust-Testfälle und
vier Smoke-Gruppen fehlen. Die ursprüngliche CI-Ergebnisabholung scheitert;
zusätzliche Zielhost-Diagnosen werden ausdrücklich getrennt aufbewahrt.

Die ursprüngliche Release-Quittung fehlt. Der 4,5-GiB-Gast ist damit keine
ausreichend dimensionierte Infrastruktur für die vollständige Originalsuite.

Das geprüfte Produktionsfenster enthält keine überlappenden Jenkins-Builds.

Leroys ursprünglicher Elternlauf `a2378ef710bd468c8c9021f8e60f788c` wurde danach
mit einer eigenen Kopie derselben gesunden Basis gestartet. Quellen, Tests,
Images und Fixture-Limits bleiben unverändert. Die Gastkerne melden um eine
4-KiB-Seite abweichendes `MemTotal`; beide VMs sind mit 4.608 MiB konfiguriert.

Auch dieser Vergleich endet unvollständig: Im Jenkins-Gast werden Clippy und
Rustc durch den Kernel wegen Speichermangels beendet; Rust-Testfälle und vier
Smoke-Gruppen werden nicht ausgeführt. Leroy verliert seine Runner-Lease
während der Web-Vorbereitung, bevor Browserfälle oder Qualität starten.

Die Datenbank protokolliert gleichzeitig lange Checkpoint-Synchronisationen;
eine ausschließliche Ursache des Lease-Verlusts ist damit nicht bewiesen.

Beide ursprünglichen Elternläufe sind beendet, die eigene VM ist sauber
gestoppt, und die vollständigen Produktionswächter bestätigen ruhige
Jenkins-Fenster. Fehlende CI-Artefakte werden nicht durch nachträgliche
Gastdiagnosen ersetzt.

Zwölf zusätzliche Desktop-/Mobilansichten der tatsächlich unterbrochenen
Leroy-Läufe sind manuell geprüft. Übersprungene Schritte und fehlende Artefakte
werden korrekt dargestellt; die Qualitäts-Pipeline wurde nicht gestartet.

Der Worker übernimmt bei künftigen Kindlaufabbrüchen die tatsächliche
Abbruchursache statt einer allgemeinen Fehlermeldung. 16 gezielte Tests bestehen;
das geprüfte Worker-Image ist ausschließlich im Graphato-Testprofil des NAS
eingespielt. Historische Ergebnisse bleiben erhalten.

Die neue Serie `full-release-nas-20261011-e` startet mit Leroy. Beide Engines
erhalten sechs GiB Gast-RAM, dieselbe unveränderte Basis und identische Grenzen.

Nur die eigene VM wird auf 24 MiB/s Lesen und acht MiB/s Schreiben begrenzt;
die Kernel-Cgroup bestätigt diese Grenzen. Leroy wird dennoch erneut unterbrochen:

Die Worker erfassen Heartbeat-`ReadTimeout`s bis etwa 49 Sekunden seit der letzten
Bestätigung. Die lesende Datenbankmessung belegt vorübergehende WAL-Commit-
Verzögerungen mit nachgelagerten Sperrketten. Der Gast meldet keinen OOM,
das RAID ruht und ist vollständig. Der Web-Schritt zeigt die tatsächliche
Abbruchursache; Qualität und Release-Quittung sind übersprungen. Zusatzdiagnosen
halten auch die noch nicht abgeschlossene Bereinigung offen fest.

Jenkins #13 mit Web #16 und Qualität #14 endet ebenfalls mit `FAILURE`:

Nach bestandener Datenträgerprobe beendet der eigene Swapreserve-Guard die
Test-VM. Ihr Zielzustand nach dem Versuch ist nicht mehr lesbar; der Bericht
ersetzt ihn nicht durch den Zustand davor. Alle vier Produktionsfenster der
Serie sind ruhig; gleiche übrige Hintergrundlast wird nicht behauptet.

Ein zusätzlicher SSD-Testmodus trennt die eigene VM vom HDD-Pool der
Controller-Datenbank. Er erhält 128/32 MiB/s Lese-/Schreibgrenzen, einen
40-GiB-Diskreserve-Guard und eine gemeinsame, protokollierte Freigabe sauberen
Dateicaches ausschließlich im bereiten KVM-Testgast bei knapper NAS-Swapreserve.

Host-Kernel und Original-Fixture-Limits werden dabei nicht geändert. Die
Basiskopie wird erst bei inaktiven Tests angelegt. 36 gezielte Worker-,
Disk-, Speicher- und Gastschutzprüfungen bestehen. Zwölf weitere tatsächliche
Abbruchansichten sind geprüft; die sichtbare Ursache ist jetzt `ReadTimeout`.

Graphato-Quellen und Originaltests bleiben unverändert. Der vollständige
Release-Vergleich und die Produktionsfreigabe sind weiterhin offen.

Details und ursprüngliche Fehlversuche stehen in [nas-full-release.md](nas-full-release.md).

Die SSD-Kopie ist anschließend identisch gehasht vorbereitet. Serie `g` endet
ebenfalls unvollständig: Leroy verliert seine Lease, Jenkins #14 mit Web #17 und
Qualität #15 scheitert nach Abschaltung der eigenen Test-VM durch den
Swapreserve-Guard. Originalinventare fehlen; Zusatzdiagnosen ersetzen sie nicht.

Alle vier Produktionsfenster sind ruhig. Serie `h` endet ebenfalls unvollständig:

Leroy verliert erneut seine Lease. Jenkins besteht diesmal alle 21 Webgruppen
und 42 Browserfälle einschließlich Soak, bytegenau belegt durch das originale
CI-Archiv. Während Clippy beendet der eigene Schutz die Test-VM wegen knappen
NAS-RAMs; Rust-Inventar, Smoke-Gruppen und Release-Quittung fehlen. Ein zuvor
ausgeführter Komponentenfall scheitert am erwarteten Fokus nach `Show in chat`;
97 weitere Komponentenfälle und alle 195 Python-Tests bestehen laut ursprünglichem
Zielprotokoll. Dieses Teilprotokoll ersetzt kein fehlendes Qualitätsarchiv.

Die vier vollständigen Produktionsfenster sind ruhig.

Bei inaktiven CI-Leases ist die UI-Korrektur ausschließlich im Testcontroller
eingespielt. Die zuvor beanstandeten 18 Ansichten der Serie `g` sind neu erzeugt
und vollständig visuell geprüft; zwölf weitere Ansichten der Serie `h` bestehen
ebenfalls. Die alten beanstandeten Bilder bleiben als Fehlernachweis erhalten.

PostgreSQL- und Controller-Daten des eigenen Teststacks liegen inzwischen auf
SSD. Logische Tabelleninhalte, physische Bytes, Rechte und ursprüngliche Images
sind geprüft; alte Volumes und Sicherung bleiben erhalten. Zwei behebbare
Vorbereitungsfehler sind dokumentiert, einschließlich des zusätzlichen Neustarts
des eigenen Docker-Testdienstes. Das nächste gemeinsame VM-Profil meldet kleinere
freie Gast-Speicherblöcke zurück, ohne Gast-RAM, Originaltests oder Schutzreserven
zu ändern. Seine Wirksamkeit ist noch offen. 56 verschiedene gezielte Prüfungen
bestehen aus getrennten Aufrufen; dies ist kein vollständiger Anwendungstestlauf.

Serie `i` scheitert vor jedem ursprünglichen Graphato-Test: Der interne Gitea-
Container war nach dem eigenen Docker-Neustart gestoppt, sodass Jenkins beim
Checkout keine interne DNS-Adresse erhält. Elternjob #16 und sein Original-
Protokoll bleiben erhalten; Kindjobs und Leroy wurden nicht gestartet. Die
eigene VM und der private Jenkins sind anschließend sauber gestoppt. Gitea ist
im selben Container mit unveränderten Mounts, Einstellungen und Image wieder
gestartet; der eingefrorene Commit ist vorhanden. Die Vorprüfung kontrolliert
diesen Dienst und das Git-Objekt nun vor VM-/CI-Start. Zwei weitere gezielte
Beobachterprüfungen verhindern das Warten auf nicht gestartete Kindjobs eines
bereits gescheiterten Elternlaufs. Die neue Serie `j` startet mit Jenkins;
alle Graphato-Quellen und Tests bleiben unverändert.

Serie `j` endet anschließend unvollständig: Alle 42 ursprünglichen Browserfälle
bestehen, die Formatgruppe ebenfalls. Clippy-Last unterschreitet jedoch die
128-MiB-NAS-RAM-Reserve; die eigene VM wird zwangsweise gestoppt. Qualitätsarchiv,
vollständiges Rust-Inventar und Elternquittung fehlen. Leroy wird in dieser Serie
nicht gestartet. Die vollständigen Produktionsfenster sind ruhig; vorhandene
Beobachtungslücken und Originalfehler bleiben erhalten. Ein neues gemeinsames
Testprofil für Serie `k` soll Speicherrückgewinnung allein in der eigenen VM-
Cgroup früher auslösen. 18 neue Schutz-/Wiederaufnahme-/Profilprüfungen bestehen;
79 verschiedene gezielte Prüfungen sind insgesamt aus getrennten Aufrufen
bestanden, einschließlich fünf zusätzlicher Prüfungen des rein lesenden
Vergleichs einzelner Testausgänge. Die reale NAS-Vorbereitung von Serie `k` bestätigt inzwischen drei
GiB `memory.high` ausschließlich für die eigene VM, unveränderte harte Grenzen,
Gastkapazität und Fixture-Limits sowie vier gesunde Zieldienste. Die Datenträger-
probe besteht. Jenkins-Web #20 endet mit `SUCCESS`; das Originalarchiv bestätigt
alle 21 Gruppen und 42 Fallidentitäten einschließlich Soak bei unveränderten
Runtime-/Quell-/Zeitstempelidentitäten. Qualität #18 und Elternjob #18 enden
anschließend mit `FAILURE`: Unter Clippy-Last unterschreitet der freie NAS-Swap
die unveränderte 2.304-MiB-Reserve. Die VM fährt regulär herunter, ohne OOM-Kill.

Formatprüfung und 195 Python-Tests bestehen; von 98 Komponententests scheitern
Fokusprüfung und zusätzlich die Renderer-Neustart-Schaltfläche. Qualitätsarchiv,
vollständiges Rust-Inventar und Elternquittung fehlen. Das vollständige
Produktionsfenster ist ruhig. Vor Leroy wird die Jenkins-Platte mit Originalbytes
archiviert; der geplante zweite Motor erhält dieselbe Basis und dasselbe Profil.

Die Originalplatte ist anschließend bytegenau archiviert; auch dieses vollständige
Produktionsfenster ist ruhig. Leroy startet um 00:52 UTC am 12. Oktober mit
verifizierter frischer Basis und denselben Ressourcen-/Release-Identitäten.

Leroys Original-Webjob besteht anschließend ebenfalls vollständig: Beide
Original-CI-Archive bestätigen dieselben 42 erfolgreichen Fallausgänge und
unveränderte Runtime-/Quell-/Zeitstempelidentitäten. Auch Leroys Qualitäts- und
Elternjob enden anschließend mit Fehler: Während Clippy unterschreitet der NAS
erneut die freie Swap-Reserve. 195 Python-Tests und Formatprüfung bestehen;
97/98 Komponententests bestehen, nur der bei Jenkins ebenfalls fehlgeschlagene
Fokusfall scheitert. Der Startup-Fall besteht bei Leroy und scheitert bei Jenkins;
dieser Vergleich stammt aus ergänzenden Zielprotokollen. Die Ursache ist offen.

Die Leroy-VM muss nach der regulären Shutdown-Frist zwangsweise beendet werden,
ohne äußeren Docker-OOM-Kill. Bei beiden fehlen vollständige Qualitätsarchive,
Rust-Inventare, weitere Qualitätsgruppen und Elternquittungen. Serie `k` ist
geschlossen; kein Originaljob oder Zielgast läuft weiter. 18 neue Desktop-/
Mobilansichten des tatsächlichen Laufbaums bestehen technisch und nach direkter
visueller Prüfung, einschließlich zweier prüfsummenverifizierter Downloads.

Während seines vorherigen Webfensters wurde produktive Musik-Synchronisation

#241 beobachtet; das gesamte Leroy-Fenster ist daher für einen unverfälschten

Lastvergleich ungeeignet. Produktionsjob und Trigger wurden nicht verändert.

Der vollständige NAS-Vergleich und eine bestandene Release-Abnahme bleiben offen.

Im neuen gemeinsamen Versuch `l` sind Jenkins-Elternjob #19 und Qualität #19
fehlgeschlagen abgeschlossen; Web #21 besteht alle 42 ursprünglichen Fälle.

195 Python-Tests und Formatprüfung bestehen, 96/98 Komponententests bestehen.

Während Clippy unterschreitet der NAS erneut seine freie Swap-Reserve; die
Test-VM wird nach der Shutdown-Frist zwangsweise beendet. Rust-Inventar,
vollständiges Qualitätsarchiv und Elternquittung fehlen. Das gesamte Jenkins-
Produktionsfenster ist anhand der vollständigen Historien ruhig. Die abgeschaltete
Jenkins-Platte bleibt bytegenau archiviert. Leroy startete um 03:49 UTC aus einer
frischen Kopie derselben Basis; seine tatsächlichen Voraufnahmen bestätigen
dasselbe Manifest und sämtliche Ressourcenwerte. Auch seine Wiederherstellung
ist ruhig. Beide Leroy-Kindjobs scheitern an der 30-Sekunden-Frist der Runner-
Vorbereitung vor Checkout und Tests. Docker legt die Container erst später an;
keiner startet. Der ursprüngliche Elternlauf ist fehlgeschlagen abgeschlossen,
die Test-VM regulär gestoppt. Alle Infrastrukturaufnahmen bleiben unverändert;
die Originalnachweise werden nicht durch einen erneuten Versuch ersetzt.

Die frische Wiederherstellung ist ruhig, die Datenträgerprobe besteht. Nur der frühe
Speicherrückgewinnungspunkt der eigenen Test-VM wird von drei GiB auf 3.328 MiB
angehoben; Gastkapazität, harte Limits, Quellen, Tests, Fixture-Limits und NAS-
Schutzreserven bleiben gleich. Dies verschiebt die beabsichtigte RAM-/Swap-
Verteilung, ohne die Ursache oder einen erfolgreichen Lauf vorwegzunehmen.

Die alten Originalplatten und Nachweise bleiben erhalten. Die gezielte Prüfung
der betroffenen Hilfen besteht mit 60 Tests; Ruff besteht. Der vorherige Stand
hatte insgesamt 79 verschiedene gezielte Prüfungen, vier zusätzliche
Profilprüfungen erhöhen diese Zahl auf 83; das ist kein vollständiger App-Testlauf.

Die anschließende Leroy-Nachprüfung `m` ist ebenfalls terminal abgeschlossen:

vollständige Websuite bestanden, Qualität und Elternlauf nach Lease-Ausfall
abgebrochen, VM bei der freien Swap-Schutzreserve regulär gestoppt. Die aktuelle
Vergleichstabelle oben und [nas-full-release.md](nas-full-release.md) sind maßgeblich.

1. Vor einer weiteren vollständigen Abnahme die Verfügbarkeit des eigenen
   Control-Stacks unter NAS-Speicher-/I/O-Druck nachweislich absichern. Die
   gepufferte Diagnosezustellung besteht ihre begrenzte Probe, reicht aber
   unter der realen Last der abgeschlossenen Serie `n` nicht aus. HDD-Zugriffe
   auf Laufzeit-/Image-Dateien und vorhandene Cgroup-Reservierungen sind
   konkrete weitere Ansatzpunkte. Die historischen Ursachen sind nicht
   vollständig bewiesen. Quellen, Tests und ursprüngliche Fristen bleiben
   unverändert; sämtliche abgebrochenen Nachweise bleiben erhalten.

2. Vor und nach jeder weiteren Probe produktive
   Jenkins-Aktivität lesend prüfen; Überschneidungen kennzeichnen den Lauf als
   ungeeignet für einen Lastvergleich. Jenkins darf parallel weiterarbeiten.

3. Für weitere Ursachenmessungen zuerst die verlustfreie HTTP-Erfassung unter
   realer Last nachweisen. Null beobachtete 429 sind bei lückenhaften Spuren keine
   Entwarnung. Beobachtereinfluss und Hintergrundlast bleiben Grenzen. Bei einer
   CI-Abweichung zuerst Leroys Ausführung und Konfiguration
   untersuchen; Anwendungspatches und Teständerungen separat bewerten.

4. Nach dem vollständigen Vergleich die zwölfteilige NAS-Abnahmematrix erneut
   bewerten. Einzelproben und erfolgreiche Infrastrukturtests ersetzen die
   vollständigen Anwendungsläufe nicht.

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

Am 11. Oktober zusätzlich geprüft: Ruff für die geänderten Diagnosehelfer;
Selbstprüfungen für TCP-/HTTP-Erfassung und strenge Metadatenqualifikation;
echter NAS-Import, Original-Worker-Bau, kontrollierte Netzwerkprobe, erhaltene
originale Soak-Vergleiche sowie die genannten 24 UI-Ansichten. Die lokale
Docker-/VM-Umgebung wurde dafür nicht gestartet. Die Änderungen dieser
Fortsetzung liegen im Arbeitsbaum; die Veröffentlichung vom 9. Oktober wird
dadurch nicht rückwirkend geändert.

## Neue vollständige Abnahme mit korrigiertem Controller

Der Nutzer hat zwei getrennte Wartungsfenster von jeweils höchstens vier
Stunden zum Pausieren der sieben geprüften NAS-Dienste freigegeben. Das erste
Fenster für Leroy ist nach rund 92 Minuten abgeschlossen; alle sieben Dienste
sind wieder gesund und unverändert. Der Controller bleibt bei 512 MiB im selben
Prozess, ohne neuen OOM oder Neustart. Der vollständige Originaljob erreicht
eine bestandene Format- und Clippy-Prüfung. 20 der 21 Browsergruppen bestehen;
Core scheitert vor den Fällen am Docker-Hub-Abruf. Die Frontend-Komponentenprüfung
bleibt bei 97/98. Während der Rust-Testphase beendet die NAS-Swap-Schutzgrenze
die eigene Ziel-VM; nach Abschalt-Timeout wird QEMU zwangsweise beendet.

Die vollständige Qualitäts- und Release-Abnahme bleibt unvollständig.

233 API-Gesundheitsmesspunkte sind erfolgreich. 21 zusätzliche SQL-Wrapperfehler,
13 Worker-Beobachtungslücken und sechs vorübergehende Lease-Erneuerungsfehler
bleiben erhalten; die begrenzten Logs enthalten keinen Lease-Stopp. Die
Messpunkte werden nicht als lückenlose Verfügbarkeitsmessung dargestellt.

129 gezielte lokale Tests und 22 neue technische sowie direkte visuelle
Ansichtsprüfungen bestehen. Die UI wird nicht verändert. Das getrennte
Jenkins-Fenster ist inzwischen nach rund 94 Minuten abgeschlossen; alle sieben
Dienste sind vor der Frist wieder gesund und unverändert. Ziel-VM, privater
Jenkins, eigene Worker und beide Wächter sind aus. Vollständige native
Jenkins-Historien sind ruhig. Auch unter Jenkins bleibt der Controller im
selben Prozess ohne neuen Neustart oder Cgroup-OOM.

Jenkins besteht 42/42 ursprüngliche Browserfälle sowie Format und Clippy.

Der gleiche Komponententest endet mit 97/98. Auch seine Rust-Phase wird
durch die gleiche NAS-Swap-Schutzgrenze beendet; nach Abschalt-Timeout ist
die QEMU-Beendigung erzwungen. Die vollständigen Qualitätsarchive, späteren
Gruppen und Release-Quittungen fehlen in diesem Paar. Gleiche fehlgeschlagene
Gesamtstatus belegen keine vollständige Release-Abnahme. Quellen, Tests,
Release-Identität, Steuerungsinfrastruktur und Ressourcen sind gebunden;
die erzeugten Verifikations-Image-IDs unterscheiden sich, deren vollständige
Inhaltsgleichheit bleibt ungeprüft. Allgemeine Leistungsgleichheit wird nicht
behauptet. Beide freigegebenen Wartungsfenster sind abgeschlossen.

Details und Abschlussbelege: [nas-full-release.md](nas-full-release.md) und
[nas-resource-window.md](nas-resource-window.md). Eine Produktionsfreigabe
ist damit weiterhin nicht belegt.

## 14.10.2026: Ursache der Laufzeitsperren eingegrenzt und Testumgebung abgesichert

Die [NAS-Nachanalyse](nas-release-forensics.md) belegt eine interne PostgreSQL-
Neuinitialisierung nach einem unbekannten Kindprozess mit Exit 2 unter beiden
Engines. Danach verliert Graphato seine Eigentümerverbindung. Zwei kleine
Kontrollcontainer mit demselben ursprünglichen PostgreSQL-Image reproduzieren
den Fehler ohne Init; mit Init bleibt die Neuinitialisierung aus. Beide
Diagnosecontainer sind entfernt. Leroys eigene NAS-Testdatenbank ist mit
gesicherter Datenhaltung auf `init: true` umgestellt. Controller, Runner und
Testdaemon behalten ihre Prozesse; die API ist bereit. Die Produktionsvorlage
enthält dieselbe Absicherung. Produktive Dienste bleiben unberührt.

Die optionale Graphato-Testbaseline mit Init wurde anschließend mit einer neuen
ursprünglichen Frontend-Gruppe geprüft. Alle 98 Komponentenfälle wurden
ausgeführt; 96 bestehen. Der bekannte Fokusfall und zusätzlich die Sichtbarkeit
von `Retry renderer` scheitern. Alle Basisdienste bleiben gesund, ohne internen
PostgreSQL-Neustart oder Graphato-Lease-Verlust. Das vollständige Originalarchiv
und die Bereinigung sind belegt. Direkte Einzelbeobachtung ohne Leroy-Steuerung
zeigt: Der Artikel erhält den Fokus; unmittelbar danach übernimmt die Textarea.

Diese Diagnose verändert keine ursprüngliche Quelle oder Prüfung und ersetzt
keinen fehlgeschlagenen Lauf. Neun ausgewählte Dateien und alle 264
Debian-Paketstände stimmen zwischen den erzeugten Test-Images überein;
vollständige Inhaltsgleichheit bleibt offen. Der Abnahmehelfer behandelt eine
gestoppte Ziel-VM jetzt als explizit fehlenden Abschlussbeleg und kann die
vorhandenen Originalfehler auswerten, ohne erneut CI zu starten. Die Auswertung
aller 58 ursprünglichen Vergleichsdateien auf einer getrennten Kopie bestätigt
weiterhin fehlende Vollabnahme. 115 gezielte lokale Tests und Ruff bestehen.

Alle sieben NAS-Dienste sind gesund und unverändert; die Ziel-VM ist aus.

Graphatos eingefrorene Quellen und Tests sind unverändert. Offen bleiben
Host-/Gast-Speicherzuordnung, die separate Bewertung der nachgewiesenen
Fokusübernahme und der Retry-Renderer-Abweichung sowie die vollständigen
Originalinventare und Archive. Eine Produktionsfreigabe wird weiterhin nicht erteilt.

## 14.10.2026: Controller-Sperrfehler behoben, Rust-Ressourcengrenze bleibt offen

Die neue [Rust-Ressourcenqualifikation](nas-rust-memory.md) mit unveränderten
Graphato-Quellen und Tests ist unter beiden Engines unvollständig: Zwei
Leroy-Versuche verlieren ihre Runner-Lease; der private Jenkins-Gegenlauf
erreicht ebenfalls die NAS-Swap-Schutzgrenze. Das kleinere 8-GiB-Gastprofil
ist mit allen sieben NAS-Anwendungen aktiv noch nicht qualifiziert. Die
Speicherproben trennen Host, Gast und VM-Cgroup; Beobachtungslücken und eine
zeitweise gemessene RAM-Reserveunterschreitung bleiben sichtbar.

Im Leroy-Controller ist ein konkreter Fehler beseitigt: Die Zustandsprüfung
sperrt gesunde Runs nicht mehr und lädt bei fälligen Eingriffen den aktuellen
Lease-Zustand unter Sperre erneut. Zwei parallele PostgreSQL-Gegenbeispiele
scheitern mit dem alten Code; alle 34 echten Linux/PostgreSQL-Tests bestehen
mit der Korrektur ohne Skip. 240 weitere lokale Tests bestehen, neun werden
übersprungen. Genau das geprüfte Controllerimage ist mit geschützter Sicherung
im eigenen NAS-Teststack installiert; Runs, Schritte und Artefakte sind erhalten.

Lease-Fristen, Fencing, Datenbank-Haltbarkeit und Laufzeitabhängigkeiten bleiben
gleich. Der Fix erklärt noch nicht jede historische Verzögerung und ersetzt
keine Abnahme unter CI-Last.

Die vollständigen Rust-Prüfimage-Inventare binden gleiche Compiler-, Bibliotheks-
und Quellstände. Die verbleibenden Unterschiede betreffen erzeugte Caches und
Logs sowie ausschließlich die Reihenfolge identischer Git-LFS-Einstellungen.

Bytegleiche Images und gleiche Laufzeiten werden weiterhin nicht behauptet.

Bei Sonarr und SABnzbd sind zwischenzeitlich neue Prozesse in denselben
unverändert konfigurierten Containern beobachtet; beide sind gesund. Der
Anforderer dieser Neustarts ist aus den begrenzt erhaltenen Ereignissen nicht
belegt. Auch deshalb ist unveränderte Hintergrundlast keine nachgewiesene
Vergleichsbedingung.

Die drei abgeschlossenen Rust-Testplatten sind außerhalb jeder Original-CI-Ausführung
bytegeprüft auf HDD archiviert; rund 80 GiB SSD sind frei. Alle sieben NAS-Anwendungen laufen; die früheren
Wartungsfenster sind beendet. Neue Fenster werden erst nach ausdrücklicher
Freigabe gestartet. Ihr Ablauf enthält eine originale Rust-Vorprüfung vor
jedem Volllauf und eine automatische Wiederherstellung nach jedem Fenster.

Die vollständige Release-Abnahme und die Produktionsfreigabe bleiben offen.

Aktualisierung 14.10.2026, 22:12 Uhr Berlin: Das neue einstündige
Kapazitätsfenster ist geschlossen. Alle sieben Anwendungen sind seit
21:57 Uhr wieder gestartet und anschließend gesund und stabil geprüft.

Die Probe hielt 5120 MiB zusätzliche anonyme Last; die nächste Zuteilung
wurde vorsichtig verweigert. 6144 MiB sind damit nicht qualifiziert.

Kein ursprünglicher Graphato-Job lief in diesem Fenster.

Die anschließende ausdrückliche Freigabe für die ganze Nacht erhält ein
eigenes Journal mit fester Wiederherstellung spätestens am 15.10. um
06:00 Uhr Berlin (Wächterbeginn 05:45). Nach geprüftem VM-Start folgen
höchstens drei getrennte Kapazitätsprofile und nur bei Erfolg ursprüngliche
Rust-Prüfungen beider Engines. Erst deren Erfolg erlaubt die vollständigen
Release-Läufe. Der VM-Start prüft weiter die gesamte Snapshot-Prüfsumme,
gibt gelesene Dateiseiten aber zur Cachefreigabe frei; die eigene
weiche VM-Speichergrenze kann nun bereits vor dem Gaststart greifen.

Quellen, Tests, ursprüngliche Fixture-Grenzen und NAS-Schutzgrenzen bleiben
gleich. Die neue lokale Gesamtsuite besteht mit 276 Tests und 43 Skips
(34 separate PostgreSQL-, neun SCM-Baseline-Prüfungen).


Sechs weitere Ansichten von #186 wurden technisch und direkt visuell auf Desktop
und Mobilgeraet geprueft, einschliesslich des bytegeprueften originalen
189-Byte-Artefakts. Sie zeigen den Fehlerstatus und keine erfolgreichen Rust-Ergebnisse.
Beleg: `test-results/nas-parity/w-rust-186-terminal-ui/visual-review.json`.


Die weitere rein lesende Aufnahme des Jenkins-Gegenlaufs findet den NAS-Operator
und Jenkins-Heartbeat zeitweise in Btrfs-Transaktionswartezeiten, bei nicht
ausgelagertem Jenkins-Hauptprozess. Operator und Fensterjournale liegen auf
`/volume1` (Btrfs/HDD), VM und Docker-Testengine auf `/overlay` (ext4/NVMe).
Diese Beobachtungsstockung ist kein CI-Endzustand: Der direkte Gastbeleg zeigt
weiter fortschreitende Rust-Kompilierung. Das laufende Vergleichsprofil bleibt
unveraendert. Die verlaengerte reine Beobachtungsverbindung ueberwacht denselben
Lauf bis Fensterabschluss; kein erneuter CI-Start wurde ausgefuehrt.


Die automatische Fortsetzung dieses Chats ist aktiv (`leroy-nas-abnahme-fortsetzen`).
Sie prueft den bestehenden Originalauftrag, sichert nach dessen Ende die Belege,
prueft die Wiederherstellung der sieben Dienste und setzt die fehlende Abnahme
fort. Sie startet bei unklarem Status keinen CI-Auftrag erneut und meldet keine
unveraenderten Zwischenstaende. Nach der letzten gesicherten laufenden Aufnahme
rissen Verwaltungs-SSH-Verbindungen unter Last ab; ein spaeterer Neuaufbau scheiterte
bereits am Banner-Zeitlimit. Leroy /health/live und /health/ready antworteten am
17. Oktober um 14:25 Uhr weiterhin mit HTTP 200. Daraus folgt kein Endzustand von
Jenkins #31; der NAS-seitige Abschluss muss weiterhin eingesammelt werden.
