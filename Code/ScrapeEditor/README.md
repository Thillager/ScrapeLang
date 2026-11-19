# Scrape Editor

**Scrape Editor – Java-Swing-Editor für Scrape-Quellcode und Scratch-3-Projekte**

Der Scrape Editor ist eine Desktop-Anwendung zum Schreiben und Bearbeiten der Java-ähnlichen Scrape-Sprache. Er kann `.scrape`-Dateien direkt öffnen und speichern sowie `.sb3`-Projekte mit dem Detranspiler in Scrape-Code umwandeln. Der Transpiler erzeugt anschließend wieder `.sb3`-Dateien und kann TurboWarp Desktop im Watch-/Replace-Modus starten.

Der Editor ist die grafische Oberfläche für die beiden Python-Werkzeuge `Transpiler.py` und `Detranspiler.py`.

> Diese Anleitung beschreibt den bereitgestellten Stand von `Main.java` zusammen mit den gleichnamigen Python-Ressourcen. Für die Syntax der Scrape-Sprache und die vollständige Liste der Befehle siehe zusätzlich `README_Transpiler.md`.

## Inhalt

- [Funktionen](#funktionen)
- [Voraussetzungen](#voraussetzungen)
- [Projektstruktur](#projektstruktur)
- [Kompilieren und Starten](#kompilieren-und-starten)
- [Bedienung](#bedienung)
- [Dateitypen und Speichern](#dateitypen-und-speichern)
- [Hotswap und Watch-Modus](#hotswap-und-watch-modus)
- [Synchronisierung externer Änderungen](#synchronisierung-externer-änderungen)
- [Einstellungen und temporäre Dateien](#einstellungen-und-temporäre-dateien)
- [Fehlerbehebung](#fehlerbehebung)
- [Architektur und technische Hinweise](#architektur-und-technische-hinweise)

## Funktionen

- Scrape-Editor mit Java-Syntaxhervorhebung.
- Code-Folding und Einrückung mit Tabulatorgröße 4.
- Autovervollständigung für die in `Main.java` hinterlegten Scrape-Schlüsselwörter, Befehle und Ausdrücke.
- Manuelles Auslösen der Autovervollständigung.
- Öffnen und Speichern von `.scrape`-Dateien.
- Öffnen von `.sb3`-Dateien über `Detranspiler.py`.
- Speichern eines bearbeiteten `.sb3`-Projekts über `Transpiler.py`.
- Einmaliges Transpilieren und Watch-/Hotswap-Modus.
- Starten bzw. Ersetzen von TurboWarp Desktop über den Transpiler.
- Erkennung externer Änderungen mit Warn- oder automatischem Neulademodus.
- Dark Mode.
- Temporärer Arbeitsbereich außerhalb des Projektordners.

## Voraussetzungen

### Java

- Ein installiertes **JDK** zum Kompilieren und eine passende Java-Laufzeit zum Starten.
- Die folgenden Java-Bibliotheken müssen zur Compile- und Laufzeit im Klassenpfad liegen:
  - **FlatLaf** (`com.formdev.flatlaf.FlatDarkLaf` und `FlatLightLaf`)
  - **RSyntaxTextArea** einschließlich `RTextScrollPane` und der zugehörigen Theme-Ressourcen (`org.fife.ui.rsyntaxtextarea` und `org.fife.ui.rtextarea`)
- Die verwendeten Bibliotheksversionen sind in `Main.java` nicht festgeschrieben. Verwende zueinander kompatible JAR-Versionen und halte sie beim Kompilieren und Starten im Klassenpfad.

### Python

- **Python 3.10 oder neuer**.
- Unter Windows versucht der Editor zuerst `python` und bei einem Startfehler anschließend `python3`.
- Unter macOS und Linux wird `python3` verwendet.
- Für die normale Umwandlung sind keine weiteren Python-Pakete erforderlich. Pillow ist für bestimmte Bildkonvertierungen im Transpiler optional.

### Desktop-Player

- Für die Live-Vorschau wird **TurboWarp Desktop** benötigt.
- Der Transpiler sucht nach bekannten Installationspfaden. Eine abweichende portable Installation wird möglicherweise nicht automatisch erkannt.
- Für Fensterpositions-Unterstützung auf Linux benötigt der Transpiler `xdotool`.

## Projektstruktur

Die Python-Skripte müssen als Java-Classpath-Ressourcen verfügbar sein. Der Code lädt sie über die Ressourcenpfade `/Transpiler.py` und `/Detranspiler.py`.

Empfohlene Quellstruktur:

```text
ScrapeEditor/
├── Main.java
├── resources/
│   ├── Transpiler.py
│   └── Detranspiler.py
└── lib/
    ├── flatlaf-<version>.jar
    └── rsyntaxtextarea-<version>.jar
```

Beim Erstellen der Anwendung müssen die beiden Python-Dateien in das Wurzelverzeichnis der kompilierten Klassen kopiert werden, sodass sie später als `/Transpiler.py` und `/Detranspiler.py` gefunden werden.

## Kompilieren und Starten

Die folgenden Befehle sind Beispiele. Die Namen der JAR-Dateien und die Bibliotheksversionen müssen zu deiner lokalen Installation passen.

### Windows (PowerShell)

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -cp "lib/*" -d out Main.java
Copy-Item resources\Transpiler.py out\Transpiler.py
Copy-Item resources\Detranspiler.py out\Detranspiler.py
java -cp "out;lib/*" Main
```

Eine Datei direkt beim Start öffnen:

```powershell
java -cp "out;lib/*" Main "C:\Projekte\spiel.scrape"
```

### macOS / Linux

```bash
mkdir -p out
javac -cp 'lib/*' -d out Main.java
cp resources/Transpiler.py out/Transpiler.py
cp resources/Detranspiler.py out/Detranspiler.py
java -cp 'out:lib/*' Main
```

Eine Datei direkt beim Start öffnen:

```bash
java -cp 'out:lib/*' Main '/home/user/projekte/spiel.scrape'
```

Für eine produktive Distribution empfiehlt sich ein reproduzierbarer Build-Prozess, der die verwendeten JARs und die beiden Python-Ressourcen zusammen ausliefert.

## Bedienung

### Menüs

| Menü | Funktion |
|---|---|
| **Datei → Neu** | Erstellt ein neues Scrape-Grundgerüst mit `public Stage Buehne` und einem Beispiel-Sprite. |
| **Datei → Öffnen…** | Öffnet `.scrape` oder `.sb3`. |
| **Datei → Speichern** | Speichert eine `.scrape`-Datei direkt oder erzeugt bei einer `.sb3`-Datei ein aktualisiertes Scratch-Projekt. |
| **Transpiler → Ausführen** | Speichert die Quelle (bei `.scrape`) und führt den Transpiler einmal aus. |
| **Transpiler → Hotswap / Watch** | Startet den Transpiler mit `--watch` und `--turbowarp-replace`. |
| **Transpiler → Stoppen** | Beendet den vom Editor gestarteten Transpiler-Prozess. |
| **Ansicht → Dark Mode** | Schaltet das dunkle bzw. helle Farbschema um. |
| **Einstellungen → Dateiüberwachung…** | Legt das Verhalten bei externen Dateiänderungen fest. |

### Tastenkürzel

| Tastenkürzel | Funktion |
|---|---|
| `Strg+S` | Speichern |
| `Strg+R` | Transpiler einmal ausführen |
| `Strg+Shift+R` | Hotswap / Watch starten |
| `Strg+X` | Transpiler stoppen |
| `Strg+Leertaste` | Autovervollständigung manuell öffnen |

Die Autovervollständigung öffnet sich außerdem nach Eingabe von mindestens zwei passenden Zeichen. Mit den Pfeiltasten kann ein Vorschlag ausgewählt und übernommen werden.

## Dateitypen und Speichern

### `.scrape` öffnen

Eine `.scrape`-Datei wird als UTF-8-Text in den Editor geladen. Speichern schreibt den Editorinhalt direkt in diese Datei.

### `.sb3` öffnen

Beim Öffnen einer `.sb3`-Datei führt der Editor `Detranspiler.py` im Hintergrund aus. Der daraus erzeugte Scrape-Text wird in den Editor geladen. Das Zwischenresultat liegt im temporären Arbeitsbereich des Editors und nicht neben dem Originalprojekt.

### `.sb3` speichern

Beim Speichern einer geöffneten `.sb3`-Datei:

1. schreibt der Editor den aktuellen Text in eine temporäre `.scrape`-Quelldatei;
2. startet `Transpiler.py` mit dieser Datei und einer temporären `.sb3`-Ausgabe;
3. kopiert das erzeugte Projekt zurück auf die ursprünglich geöffnete `.sb3`-Datei.

Das Originalprojekt wird dabei ersetzt. Bewahre vor größeren Änderungen eine Sicherungskopie auf.

### Hintergrundverarbeitung

Längere `.sb3`-Import-, Export- und Synchronisierungsvorgänge werden über `SwingWorker` außerhalb des Swing-Event-Threads ausgeführt. Während der Verarbeitung zeigt die Oberfläche einen Warte-Cursor an. Bei Fehlern erscheint ein Dialog mit einer Fehlermeldung bzw. Prozessausgabe.

## Hotswap und Watch-Modus

### `.scrape`-Datei

Bei einer geöffneten `.scrape`-Datei speichert der Editor zunächst den aktuellen Quelltext. Danach startet er den Transpiler mit:

- der geöffneten `.scrape`-Datei als Watch-Eingabe,
- einer gleichnamigen `.sb3`-Datei als Vorschauausgabe,
- `--turbowarp-replace`,
- zusätzlich `--watch`, wenn der Watch-Modus gewählt wurde.

### `.sb3`-Datei

Bei einer geöffneten `.sb3`-Datei wird eine temporäre `live-<projektname>.scrape` als Watch-Quelle verwendet. Die erzeugte Vorschau wird auf die geöffnete `.sb3`-Datei geschrieben. Dadurch muss der Editor nicht versuchen, die `.sb3` selbst als Scrape-Quelltext zu überwachen.

Speichern während des Watch-Modus aktualisiert die temporäre Watch-Quelldatei, sodass der laufende Transpiler die Änderung erkennen und neu kompilieren kann.

### Was bedeutet Hotswap hier?

Der Watch-Prozess kompiliert Änderungen und verwendet `--turbowarp-replace`. Der Transpiler beendet dabei die laufende TurboWarp-Instanz und startet sie mit der neu erzeugten `.sb3`-Datei erneut. Das ist ein automatisierter Neustart, kein echtes Austauschen von Blöcken innerhalb einer unverändert laufenden TurboWarp-VM.

Der Watch-Prozess läuft in einem externen Terminal. Beende ihn über **Transpiler → Stoppen** bzw. `Strg+X` im Editor oder `Ctrl+C` im Terminal.

## Synchronisierung externer Änderungen

Der Editor prüft regelmäßig, ob sich die geöffnete Datei außerhalb des Editors geändert hat. Er nutzt Dateigröße, Änderungszeit und einen SHA-256-Fingerprint, um tatsächliche Änderungen zu erkennen und nicht nur Zeitstempeländerungen zu melden.

Wenn die Vorschau in TurboWarp Desktop gespeichert wird und deren `.sb3`-Datei vom Editor überwacht wird, kann der Editor diese externe Änderung erkennen und den Detranspiler ausführen, um den gespeicherten Stand wieder in Scrape-Code zu übersetzen.

Bei einer separaten Vorschau-Datei (z.B. wenn eine `.scrape`-Datei geöffnet ist) bietet der Dialog an:

- **Aktuellen Code kopieren** – kopiert den gerade im Editor befindlichen Text in die Zwischenablage.
- **TurboWarp-Version in .scrape übernehmen** – wandelt die externe `.sb3`-Änderung zurück nach Scrape und übernimmt sie in den Editor bzw. die zugehörige `.scrape`-Datei.
- **Änderung ignorieren** – lässt den Editorinhalt unverändert und aktualisiert den bekannten Dateistand.

Bei externen Änderungen der aktuell geöffneten Datei gibt es ebenfalls eine Rückfrage mit der Möglichkeit, den aktuellen Code vor dem Neuladen zu kopieren.

### Einstellung für externe Änderungen

Unter **Einstellungen → Dateiüberwachung…** kann festgelegt werden:

1. **Warnen und nachfragen** (Standard): Der Editor fragt vor dem Laden einer externen Version.
2. **Automatisch laden**: Der Editor übernimmt die neue Version ohne Rückfrage. Dabei kann ungespeicherter Editorinhalt überschrieben werden.

Die Auswahl wird in `java.util.prefs.Preferences` gespeichert und bleibt normalerweise über Programmneustarts hinweg erhalten.

## Einstellungen und temporäre Dateien

### Temporärer Arbeitsbereich

Der Editor legt einen eindeutigen Ordner im System-Temp-Verzeichnis an, üblicherweise mit dem Präfix:

```text
scrape-editor-...
```

Dort liegen unter anderem:

- extrahierte Kopien von `Transpiler.py` und `Detranspiler.py`,
- temporärer Scrape-Quellcode für `.sb3`-Import/-Export,
- die temporäre Live-Watch-Quelle,
- Zwischenergebnisse der TurboWarp-Synchronisierung.

Der Editor legt diese Hilfsdateien nicht neben der geöffneten Projektdatei an. Beim normalen Schließen versucht er, den Arbeitsordner rekursiv zu löschen; zusätzlich wird der Ordner für `deleteOnExit` registriert.

### Persistente Benutzereinstellungen

Die Präferenz `darkMode` speichert den Darstellungsmodus. `autoReloadExternalChanges` speichert die Einstellung zum automatischen oder bestätigungspflichtigen Laden externer Änderungen. Die Werte werden über die Java Preferences API verwaltet und liegen nicht in einer projektbezogenen Konfigurationsdatei.

## Fehlerbehebung

### `Transpiler.py` oder `Detranspiler.py` wurde nicht gefunden

- Prüfen, ob beide Skripte im Ordner `resources/` liegen.
- Prüfen, ob der Build sie in das Klassenpfad-Wurzelverzeichnis kopiert hat.
- Der Java-Code erwartet die Ressourcen exakt unter `/Transpiler.py` und `/Detranspiler.py`.

### Python kann nicht gestartet werden

- `python --version` bzw. `python3 --version` im Terminal testen.
- Python 3.10 oder neuer installieren.
- Unter Windows prüfen, ob Python im `PATH` eingetragen ist.
- Unter macOS/Linux muss `python3` verfügbar sein.

### Fehler beim Öffnen oder Speichern einer `.sb3`

- Prüfen, ob die `.sb3` eine gültige ZIP-Datei ist.
- Sicherstellen, dass `project.json` enthalten ist.
- In der Prozessausgabe nach Syntaxfehlern, fehlenden Assets oder Validator-Fehlern suchen.
- Schreibrechte auf die Originaldatei und das System-Temp-Verzeichnis prüfen.

### Autovervollständigung oder Syntaxhervorhebung fehlt

- Prüfen, ob RSyntaxTextArea und seine Theme-Ressourcen im Klassenpfad sind.
- Prüfen, ob die Anwendung tatsächlich mit der erwarteten `Main.class` gestartet wird.

### TurboWarp wird nicht gefunden

- TurboWarp Desktop installieren.
- Prüfen, ob die Installation in einem der vom Transpiler unterstützten Standardpfade liegt.
- Bei einer portablen oder benutzerdefinierten Installation muss die Pfaderkennung im `Transpiler.py` ggf. erweitert werden.

### Fensterposition wird nicht wiederhergestellt

Die Fensterpositionslogik liegt im Transpiler und ist betriebssystemabhängig. Unter Linux ist `xdotool` erforderlich. Wenn die Desktop-App beim Start ihre eigene Fenstergröße erneut setzt, kann die Position nicht zuverlässig erzwungen werden.

### TurboWarp-Änderung wird nicht übernommen

- Prüfen, ob tatsächlich die vom Editor überwachte `.sb3`-Datei in TurboWarp gespeichert wurde.
- Prüfen, ob der Watch-Modus noch läuft.
- Bei einer `.scrape`-Quelldatei kontrollieren, ob die zugehörige Vorschau-`.sb3` im Editor-Temp-/Projektpfad die erwartete Datei ist.
- Prüfen, ob die Einstellung auf Warnen oder automatisches Laden gesetzt ist.
- Bei offenen Rückfragedialogen den Dialog erst beantworten, bevor weitere Dateiänderungen ausgewertet werden.

## Architektur und technische Hinweise

### Java-Oberfläche

`Main.java` basiert auf Swing. Das Hauptfenster enthält eine `RSyntaxTextArea`, die für Java-Syntaxhervorhebung konfiguriert ist. FlatLaf steuert das helle/dunkle Look-and-Feel. Autovervollständigung und Tastaturaktionen werden in Java implementiert.

### Python-Prozesse

Der Editor startet die Python-Dateien als externe Prozesse über `ProcessBuilder`. Für `.sb3`-Import und -Export liest er die kombinierte Prozessausgabe und wertet den Exit-Code aus. Längere Import-/Export-Arbeiten laufen im Hintergrund, um die Swing-Oberfläche nicht zu blockieren.

### Verantwortlichkeiten

| Komponente | Aufgabe |
|---|---|
| `Main.java` | Benutzeroberfläche, Dateioperationen, Einstellungen, externe Dateiüberwachung, Start/Stop des Transpilers |
| `Detranspiler.py` | `.sb3`-Projekt in Scrape-Quelltext umwandeln |
| `Transpiler.py` | Scrape-Quelltext validieren und `.sb3` erzeugen; optional Desktop-App starten und Watch ausführen |

### Wichtige Einschränkungen

- Der Editor ersetzt keine vollständige Scratch-Projektverwaltung. Die eigentliche Übersetzung ist durch die unterstützten Funktionen der Python-Skripte begrenzt.
- `.sb3` → Scrape → `.sb3` ist kein garantierter verlustfreier Roundtrip. Beachte dazu die Hinweise im Detranspiler-README.
- Der Watch-/Hotswap-Mechanismus führt bei erfolgreicher Kompilierung einen Replace-Neustart von TurboWarp durch; die laufende VM wird nicht live gepatcht.
- Die Verfügbarkeit der Betriebssystem- und Fensterverwaltungsfunktionen hängt von den jeweiligen Desktop-App-Versionen, Pfaden und Berechtigungen ab.

