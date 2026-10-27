# NAS-Steuerung der ursprünglichen Abnahme

Stand: 17. Oktober 2026. Jenkins bleibt produktiv. Die vollständige Release-Abnahme
ist weiterhin Voraussetzung für den Wechsel; die hier beschriebenen Proben ersetzen sie nicht.

**Abschluss am 26. Oktober:** Die NAS-Abnahme ist auf Nutzerwunsch beendet.
Jenkins #31 ist fehlgeschlagen; die sieben Dienste laufen gesund. Testdienste
und VM sind gestoppt, automatische Neustarts deaktiviert. Alte Koordinatoren,
Wartungsfenster und Dispatch-Anfragen werden nicht erneut verwendet.
Der [Checkpoint](checkpoint-2026-10-26.md) beschreibt den gesicherten Stand.

Der ursprüngliche Graphato-Stand bleibt `0ad540dd578033d45e4d0c25d89fbe57b32102a4`.

Quellen, Tests, Fixture-Grenzen, Rust-/Builder-Grenzen und die Lease-Fristen werden
durch die neue Beobachtungssteuerung nicht verändert.

## Ausführung

Die Steuerung liegt im geschützten NAS-Verzeichnis
`/volume1/docker/leroy-nas-parity/acceptance-operator-20261017-v1/workspace`.

`nas_native.py` erlaubt die lokale Ausführung nur als Linux-root, mit kanonischem
Verzeichnis, Eigentumsmarker und einer privaten Identität, die Host und Boot-ID bindet.

Windows verwendet weiterhin den vorhandenen SSH-Pfad. SSH-Zugangsdaten werden nicht
auf das NAS übertragen. Die reine Python-Laufzeit liegt privat im Arbeitsverzeichnis;
NAS-Python und globale Pakete werden nicht verändert. Git für die eingefrorene
Quellenprüfung stammt aus dem bereits vorhandenen, nach Image-ID gebundenen
Jenkins-Image. Es erhält ausschließlich den schreibgeschützt eingebundenen Checkout
und keinen Netzwerkzugang.

`nas_acceptance_service.py` führt vier getrennte systemd-Einheiten nacheinander aus:

ursprüngliches Rust unter Leroy, ursprüngliches Rust unter Jenkins, vollständiges
Release unter Leroy, vollständiges Release unter Jenkins. Jede Phase behält den
unabhängigen Wiederherstellungswächter, höchstens vier Stunden Laufzeit und
15 Minuten Reserve. Dieselben sieben Dienste werden zwischen den Phasen
wiederhergestellt und auf Gesundheit und Stabilität geprüft.

Das atomare Journal hält Startabsicht und systemd-Invocation-ID fest. Ein bereits
bekannter Phasenprozess wird weiter beobachtet. Ein unklarer Start, ein ersetzter
Prozess oder ein fehlgeschlagener Originallauf berechtigt nicht zu einem erneuten
CI-Start. Der Verlust der Windows-Sitzung beendet die NAS-Einheiten nicht.

Die Freigabe des nächsten Schritts verlangt die unveränderten ursprünglichen
Ergebnisnachweise und den vollständigen vorherigen Fensterabschluss. Es gibt keine
automatische Produktionsumschaltung.

Der erzwungene Neustart des Koordinators während der ersten Vorbereitungsphase
ist ebenfalls geprüft: neue Koordinator-Invocation-ID, unveränderte Phasen-ID
`d06a0c8f7ef6478aa23582bfe2fa5dc1`, kein erneuter Phasenstart. Die Belege liegen im
Journal `nas-execution-20261017-v/coordinator-restart-*.json`.

## Diagnose und belegte Proben

Der Lease-Beobachter folgt genau dem eigenen Worker, bevor der Runner ihn entfernt.

Er übernimmt nur begrenzte, geprüfte numerische Transport-/Zeitdaten und Fehlerklassen.

Der Prozessbeobachter hält Thread-Zustände, Speicher-/I/O-Druck sowie ausschließlich
klassifizierte Datenbankzustände fest. Request-Header, Tokens und SQL-Texte gehören
nicht in diese Diagnose.

Die realen Proben auf dem NAS verwenden den vorhandenen Worker und einen zusätzlichen
deaktivierten Diagnoseauftrag ohne Graphato oder externe Änderungen:

| Eingriff | Belegter Ausgang |

| --- | --- |

| 18 Sekunden Worker-Verbindungsverlust, anschließend Neustart des Testcontrollers | Derselbe Run `a2972720d30c4086afb4efa2bd78e301` erfolgreich |

| 110 Sekunden Worker-Verbindungsverlust | Lokaler Lease-Abbruch nach 47,008 Sekunden; Run `64d5c429eb7b4cd1b9b0bb486f72514e` anschließend `interrupted` |

| Start aus kurzlebiger Windows-SSH-Sitzung | NAS-Einheit führt beide Proben nach Sitzungsende zu Ende |

Genau zwei Diagnoseaufträge, kein doppelter Start, keine pausierten NAS-Dienste,
kein produktiver Jenkins-Build im geprüften Zeitraum. Die 45-Sekunden-Grenze des
Workers und die 90-Sekunden-Lease des Servers bleiben gleich. Der lokale Abbruch
wird beim nächsten Prüftakt erkannt; die gemessenen 47 Sekunden verlängern die
konfigurierte Grenze nicht.

Belege liegen unter `test-results/nas-parity/followup/resident-control-probe-20261017/`.

Die Linux-Qualifikation der Steuerung liegt unter
`original-workload-resident-qualification-20261017/`; vorherige fehlgeschlagene
Laufzeitvorbereitungen bleiben dort erhalten.

Die erste neue Zulassung scheiterte vor dem Anlegen des Wächterzustands: Die neue
Fensterbezeichnung war in der Freigabepolitik, aber nicht in der Ausführungsregistrierung
eingetragen. Es waren weder Dienste pausiert noch eine VM oder ein Graphato-Auftrag
gestartet. Diese unbenutzte Zulassung wurde samt Plänen und Prozessidentitäten unter
`admission-failure-20261017-v1/` gesichert. Die Korrektur registriert die Fenster auch
für den Ausführungseinstieg und übernimmt deren exakte genehmigte Endzeit in das
Wächterjournal. Vier zusätzliche Prüfungen sichern diese Verbindung zwischen
Freigabepolitik und Ausführung.

## Abgrenzung zu #182

Die Ursache des ursprünglichen Lease-Verlusts in #182 ist noch nicht abschließend
lokalisiert. Die gesicherten NAS-Samples um den Ausfall zeigen erheblichen Speicher-
und I/O-Wartedruck, trotz hoher gemeldeter `MemAvailable`-Werte und ohne neuen OOM.

Dies ist ein zeitlicher Zusammenhang, kein Nachweis einer einzelnen Ursache.

Die neue Steuerung beseitigt belegte Beobachtungsfehler und sichert beim nächsten
Originallauf die bisher fehlende Worker-/Controller-Diagnose.

## Ergebnis von V und weitere Korrektur

Leroy #185 wurde am 17. Oktober um 10:10:37 Berliner Zeit wegen Lease-Verlust
unterbrochen. Der NAS-Koordinator blieb aktiv; es gab keinen automatischen Neustart
des CI-Laufs und keinen Start der Folgephasen. Die sieben Dienste waren bis zum
Fensterabschluss um 10:41:51 wieder gesund, die VM gestoppt. RAM-Datei und SSD-Kopie
der inzwischen bytegeprüft archivierten Platte sind freigegeben.

Der Hauptthread des Controllers war während des Ausfalls in `anon_pipe_write`

blockiert. Seine eigene cgroup zeigte keinen OOM oder nennenswerten I/O-Wartedruck,
PostgreSQL war im Leerlauf; der Host zeigte dagegen starken globalen Wartedruck.

Die dauerhafte Lease-Aufzeichnung bewahrt den lokalen Worker-Abbruch nach 48,076
Sekunden und die zugehörigen Transportfehler. Dass der Docker-Logleser zeitweise
keine Daten auslieferte, erklärt auch verspätete Diagnosezeilen; die ursprünglichen
Docker-Zeitstempel bleiben erhalten.

Die neue begrenzte Console-Ausgabe verschiebt Formatierung und potenziell blockierende
OS-Schreibzugriffe in einen Hintergrundthread. Die Request-Schleife wartet nicht
auf die Ausgabe. Bei Rückstau können Console-Diagnosezeilen entfallen; CI-Schrittlogs,
Artefakte und Audit-Ereignisse verwenden weiterhin ihre dauerhaften Speicherwege.

Sechs Linux-Tests vergleichen echtes Uvicorn mit alter/neuer Protokollierung bei
ungelesenen OS-Pipes. Die tatsächliche Installation und ein neuer Originallauf
benötigen zusätzlich den NAS-Vergleich mit echtem Worker.

## Versuch W mit korrigiertem Controller

Die geprüfte Steuerung liegt nun separat unter
`/volume1/docker/leroy-nas-parity/acceptance-operator-20261017-w1/workspace`.

Die bisherige V-Steuerung und ihre Pläne bleiben erhalten. **650 native Linux-Tests**
bestehen ohne übersprungene Fälle; Eingangspaket SHA-256
`60a24c531201cf0c21348f6f1c8f21fd51c5144ab787bf9a108c1db29845ad7b`.

Das Journal heißt `nas-execution-20261017-w`, die eindeutige Koordinatoreinheit
`leroy-nas-acceptance-20261017-w`.

Die erste W-Zulassung stoppte vor Dienstpause, Wächterzustand, VM- und CI-Start,
weil ein nachgelagerter Kapazitätscheck noch die alte Controller-Image-ID verlangte.

Die unbenutzte Zulassung samt Prozessidentitäten, ursprünglichen Plänen und Quellen
ist unter `admission-failure-20261017-w1/` gesichert. Die korrigierte Bindung akzeptiert
ausschließlich die Linux- und Worker-geprüfte Logging-Ergänzung auf dem zuvor
qualifizierten Engine-Image. Ein anderer Engine-Unterbau oder eine abweichende
Freigabebindung wird weiterhin abgelehnt. Es wurde kein CI-Lauf wiederholt.

Leroy #186 (`f4af042f894b422bbeda50a8b07c8d98`) startete den ursprünglichen
`server-test` am 17. Oktober um 11:23:08 Berliner Zeit. Die Quellen sind weiterhin
`0ad540dd578033d45e4d0c25d89fbe57b32102a4`; dieselben Tests, Ressourcenprofile
und Fristen bleiben verbindlich. Die ersten Lastaufnahmen zeigen hohen globalen
Speicher-/I/O-Wartedruck, dabei frische Lease-Erneuerungen, erreichbare API und einen
regulär auf Ereignisse wartenden Controller-Hauptthread. Dies ist laufende
Beobachtung, kein erfolgreicher ursprünglicher Rust- oder Release-Nachweis.

## Längere Folgefenster für die vollständigen Releases (vorbereitet)

Die unbegrenzte Freigabe erlaubt neue vollständige Release-Fenster mit einer festen
Obergrenze von zwölf Stunden und weiterhin 15 Minuten Wiederherstellungsreserve.

Die ursprünglichen Jenkins-Suiten erlauben bereits mehrstündige Aufträge; ein
zusätzliches Vierstundenlimit der Abnahmesteuerung soll diese nicht vorzeitig
abbrechen. Dies gilt ausschließlich für neue Release-Fenster X. Laufende und
bereits geschlossene W-Fenster behalten ihre ursprünglichen Fristen.

Die neue Steuerung ist lokal vorbereitet, noch nicht auf dem NAS installiert.

Sie verlangt zunächst beide vollständig erfolgreichen W-Rust-Aufträge einschließlich
Originalarchiven, unverändertem vollständigem Testinventar, passender Runtime und
Quellarchividentität, geschlossenen Fenstern und bytegeprüften Plattenarchiven.

Die ursprünglichen Ausführungsquellen und die fünf relevanten Leroy-Module müssen
gegen das auf Linux qualifizierte W-Paket bytegleich bleiben. Unterstützende
Rust-Qualifikation wird referenziert; keine vollständigen Release-Ergebnisse werden
übernommen. Beide vollständigen Releases verlangen frische Ausgangsumgebungen.

Ein einmaliger Anschlusswächter wartet auf den erfolgreichen laufenden Leroy-Rust-
Auftrag. Danach hält er nur den übergeordneten W-Koordinator an, sobald die
Jenkins-Rust-Phase läuft. Der ursprüngliche Phasenprozess und sein unabhängiger
Wiederherstellungswächter werden nicht gestoppt. So starten die vollständigen
Releases erst mit geprüften längeren Folgefenstern.

Der Diagnose-/Sammelprozess der vollständigen Releases erhält höchstens 1 GiB,
ohne Swap, um die bereits begrenzten Original-Reportpakete einzulesen. Dies ist
keine Vorbelegung und keine Änderung an Graphato-Buildern, Testcontainern,
Leases oder deren Fristen. Die lokale Gesamtsuite besteht mit 770 Tests;
43 Tests sind umgebungsbedingt übersprungen. Die neue NAS-Qualifikation und beide
Rust-Erfolge stehen noch aus.

## Abschluss W und Jenkins-Gegenlauf Y

W/Leroy #186 endete am 17. Oktober um 13:15:37 Berliner Zeit mit `failed`.
Die korrigierte Console-Ausgabe hielt Controller und Lease stabil. Der originale
Pruefschritt verlor Gast-SSH; die Offline-Quittung bestaetigt einen Kompilierabbruch
am unveraenderten 90-Minuten-Limit, vollstaendige Bereinigung und null Rust-Tests.
Alle sieben Dienste waren um 13:29:03 wieder gesund. Das Fenster ist geschlossen,
die Platte bytegeprueft archiviert und die RAM-Datei frei. Der vorbereitete
Anschlusswaechter hat deshalb keine W-Folgephase angehalten: W startete weder
den Jenkins-Gegenlauf noch vollstaendige Releases.

Y verwendet eine eigene unveraenderliche Steuerung, genau eine originale
Jenkins-Rust-Phase und dasselbe physische Profil wie W. Seine Zulassung bindet
Originalfehler, geschlossene Wiederherstellung, Archivhash und unveraenderte
Ausfuehrungsmodule. Der Offline-Beleg wird ausdruecklich nicht zum originalen
CI-Artefakt erklaert. Die Qualifikation eines vollstaendigen Releases verlangt
weiterhin beide tatsaechlich erfolgreichen originalen Rust-Auftraege.


Der erste Y-Zulassungsversuch wurde vor jeder Dienstpause, VM- oder CI-Ausfuehrung
angehalten: Der erneut importierte Tages-Validator verwendete noch die globale
alte Fehlerreferenz. Die Uebergabe des im Plan gebundenen Versuchs behebt dies.
Y1 samt Quellen, Tests, Journal und Invocation-ID bleibt erhalten. Y2 liegt unter
`acceptance-operator-20261017-y2/workspace`; die 678 NAS-Tests bestehen ohne Skips.
Paket SHA-256 `ac9bbd4bff501c4ee63169a8e25494e08febd20c2bfd49531a4aff42fa65b7af`.
Die neue Koordinatoreinheit heisst `leroy-nas-acceptance-20261017-y2`, ihre einzige
Phase `leroy-acceptance-20261017-y2-rust-jenkins`, Invocation-ID
`5e01875f94484285b21885c516857103`. Das erstmals pausierte Y-Fenster endet fest
um 17:42:31 Berliner Zeit, mit Wiederherstellungsbeginn spaetestens 17:27:31.
Die unbegrenzte Gesamtfreigabe hebt diese einzelne Frist nicht auf.

## Fehlender Netzwerkzugang am 24. Oktober

Die Anschlussprüfung erreicht weder NAS-SSH noch Portainer oder Leroys
Gesundheitsendpunkte. Der Windows-Rechner hat derzeit keine reguläre Adresse
im NAS-Heimnetz: WLAN nutzt ein anderes Netz, Ethernet nur eine Link-Local-Adresse.
Dies belegt keinen Ausfall der NAS-Steuerung. Der bestehende Originalauftrag
#31 und die Wiederherstellung der sieben Dienste bleiben unbestätigt.

Nach Wiederherstellung des Zugangs werden zuerst die unveränderten Journale
und der vorhandene CI-Abschluss gelesen. Ein möglicher NAS-Neustart berechtigt
nicht zum Wiederholen der ursprünglichen Dispatch-Anfrage. Das abgelaufene
Y-Fenster wird nicht erneut geöffnet; Quellen, Tests und Ressourcen bleiben
bis zum belegten Abschluss unverändert.
