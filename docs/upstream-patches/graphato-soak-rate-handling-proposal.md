# Graphato: gesonderter Soak-Testtreiber-Vorschlag

Basis ist der eingefrorene Commit `0ad540dd578033d45e4d0c25d89fbe57b32102a4`.
Der [Patch](graphato-soak-rate-handling-proposal.patch) verändert zwei Dateien
des Browser-Testtreibers. Er wurde weder im eingefrorenen Checkout noch im
Graphato-Master angewendet. Die Anwendung und ihre Ratenlimits bleiben unverändert.

Nur die Prompt-Schleife des Soak-Tests darf eine Antwort mit HTTP 429,
`serverRateLimited` und konsistentem `Retry-After` wiederholen. Der Request-Body
einschließlich seiner ID bleibt gleich. Das Gesamtbudget bleibt 90 Sekunden pro
Aufruf; höchstens zwei Wiederholungen pro Prompt und elf im gesamten Lauf sind
zulässig. Alle übrigen Aufrufe und Fehler scheitern weiterhin sofort.

Der Test verlangt weiterhin vier Tabs, fünf Minuten Laufzeit und genau 120
eindeutige, gespeicherte Prompts. Die bisherigen Fehler-, Drosselungs- und
Erholungsprüfungen bleiben enthalten. Die Behandlung nativer Prompt-Drosselung
ändert bewusst eine Testannahme; sie zählt nicht als unveränderte Abnahme.

Acht gezielte Mock-Prüfungen bestehen. Zusätzlich besteht eine echte einzelne
NAS-Diagnose mit vier Ziel-CPUs, vier Tabs, 120 eindeutigen Prompts und 309,142
Sekunden Laufzeit. Sie erfasst zwei native Wiederholungen und 621 UI-Leseanfragen:
605 HTTP 200 und 16 zulässige HTTP 429, keine sonstigen Antwortfehler. Die letzte
UI-Drosselung liegt beim Abschluss 287,042 Sekunden zurück.

Diese Diagnose läuft am 6. Oktober von 21:30:39 bis 21:40:00 Uhr MESZ parallel
zum produktiven Graphato-CI-Build #27. Der funktionale Erfolg bleibt erhalten;
Laufzeit, Lastbedingungen und die Ursache der Engine-Abweichung lassen sich
daraus nicht vergleichen. Der neue Produktionslast-Wächter war vor diesem
historischen Lauf noch nicht aktiv.
[Einordnung der Produktionslast](../../test-results/nas-parity/followup/frozen-soak-rate-proposal-0ad540dd5780/historical-production-load-qualification.json).

Die unveränderten Basisdateien und die beiden Overlay-Dateien sind gegen ihre
Prüfsummen geprüft. Ein zusätzlicher Image-Layer enthält ausschließlich diese
Dateien; die Image-Konfiguration und die bisherigen Layer bleiben erhalten.
Die Quittung liegt in einem eigenen Diagnoseverzeichnis. Keine originale
Abnahmequittung wurde damit ersetzt.

[NAS-Nachweis](../../test-results/nas-parity/followup/frozen-soak-rate-proposal-0ad540dd5780/analysis.json).

Der vollständige originale Leroy-Lauf bleibt bei 28/29 bestandenen Gruppen.
Dieser Vorschlag ist keine belegte Voraussetzung für Leroy, keine Erklärung
der Engine-Abweichung und keine Produktionsfreigabe. Ein separater neuer
Graphato-Vergleichsstand muss danach unverändert unter Jenkins und Leroy die
vollständige Abnahme durchlaufen.
