# Scrape Editor Web

**Scrape Editor Web** ist ein browserbasierter Editor für Scrape-Quellcode. Er wird als lokaler Python-Webserver gestartet und bietet einen Editor mit Syntaxfarben und Autovervollständigung, eine Workspace-Dateiliste sowie die Anbindung an Scrape-Transpiler und -Detranspiler.

## Funktionen

- Scrape-Dateien im Browser öffnen, bearbeiten und speichern
- Workspace-Dateien und -Ordner durchsuchen
- Syntaxhervorhebung, Zeilennummern, automatische Einrückung und Klammerergänzung
- Autovervollständigung für Scrape-Schlüsselwörter und Befehle
- `.scrape`-Dateien nach `.sb3` kompilieren und die Transpiler-Ausgabe anzeigen
- Änderungen im Watch-Modus überwachen und neu kompilieren
- `.sb3`-Projekte mit dem Detranspiler in Scrape-Quelltext umwandeln
- Dunkles und helles Farbschema sowie anpassbare Schriftgröße

## Voraussetzungen

- Python 3.10 oder neuer
- Die Scrape-Skripte `Transpiler.py` und `Detranspiler.py` aus diesem Repository
- Ein aktueller Browser

Für den Editor selbst sind keine zusätzlichen Python-Pakete erforderlich. Der Transpiler kann für bestimmte Bildkonvertierungen optional Pillow verwenden.

## Starten

Führe den Editor vom Repository-Hauptverzeichnis aus. Übergib den Ordner, in dem du arbeiten möchtest, sowie die Pfade zu den beiden Werkzeugen:

```bash
python ScrapeEditorWeb/Editor.py \
  --root . \
  --transpiler Transpiler/Transpiler.py \
  --detranspiler Detranspiler/Detranspiler.py
```

Unter Windows kannst du denselben Befehl in einer einzigen Zeile in PowerShell ausführen:

```powershell
python ScrapeEditorWeb/Editor.py --root . --transpiler Transpiler/Transpiler.py --detranspiler Detranspiler/Detranspiler.py
```

Der Editor öffnet standardmäßig `http://127.0.0.1:8765/` im Browser. Falls der Browser nicht automatisch geöffnet werden soll, ergänze `--no-browser`. Mit `Ctrl+C` im Terminal wird der Server beendet.

### Eigenen Workspace verwenden

`--root` gibt den bearbeitbaren Workspace an. Zum Beispiel:

```bash
python ScrapeEditorWeb/Editor.py \
  --root ./MeineProjekte \
  --transpiler Transpiler/Transpiler.py \
  --detranspiler Detranspiler/Detranspiler.py
```

Der Workspace muss bereits existieren. Ohne `--root` wird das aktuelle Arbeitsverzeichnis verwendet. Relative Pfade für Transpiler und Detranspiler werden relativ zum aktuellen Arbeitsverzeichnis aufgelöst.

### Serveroptionen

| Option | Standard | Beschreibung |
|---|---|---|
| `--root <ordner>` | `.` | Workspace, in dem Dateien angezeigt und bearbeitet werden dürfen |
| `--host <adresse>` | `0.0.0.0` | Adresse, an die der HTTP-Server gebunden wird |
| `--port <port>` | `8765` | HTTP-Port (1–65535) |
| `--ip <IP>` | Loopback-Adressen | Zusätzliche Client-IP freigeben; kann mehrfach angegeben werden |
| `--ip all` | – | IP-Prüfung für alle Client-IPs deaktivieren |
| `--transpiler <datei>` | `ScrapeEditorWeb/Transpiler.py` | Pfad zu `Transpiler.py` |
| `--detranspiler <datei>` | `ScrapeEditorWeb/Detranspiler.py` | Pfad zu `Detranspiler.py` |
| `--no-browser` | aus | Browser nicht automatisch öffnen |

Die Standardpfade der Werkzeuge zeigen auf Dateien neben `Editor.py`. Da sich die Skripte in diesem Repository in den Ordnern `Transpiler/` und `Detranspiler/` befinden, solltest du beim Start aus dem Repository-Hauptverzeichnis die entsprechenden Optionen wie in den Beispielen angeben.

## Bedienung

### Dateien bearbeiten

Über die Seitenleiste navigierst du im Workspace. Dateien lassen sich per Klick öffnen. **Datei → Speichern** speichert unter dem aktuellen Pfad; **Speichern unter…** fragt nach einem Workspace-relativen Pfad. Ungespeicherte Änderungen sind mit einem Punkt markiert.

Die Dateiliste kann bis zu 2.000 Einträge pro Ordner anzeigen. Lesen und Speichern sind auf Dateien bis zu 2 MiB begrenzt. Es können nur UTF-8-Textdateien bearbeitet werden.

### Transpilieren

Öffne eine `.scrape`-Datei und wähle **Transpiler → Ausführen**. Bei Änderungen wird die Datei vor dem Kompilieren gespeichert. Die erzeugte `.sb3`-Datei erhält denselben Namen und wird neben der Quelldatei abgelegt.

Mit **Transpiler → Watch-Modus** startet der Editor den Transpiler im Watch-Modus. Änderungen an der Quelldatei werden vom Transpiler überwacht. **Watch beenden** stoppt den gestarteten Watch-Prozess.

### Detranspilieren

Wähle **Detranspiler → Eine .sb3-Datei öffnen…** und gib den Workspace-relativen Pfad zu einer `.sb3`-Datei ein. Der Detranspiler erzeugt eine gleichnamige `.scrape`-Datei im selben Ordner und öffnet sie im Editor.

### Tastenkürzel

| Tastenkürzel | Funktion |
|---|---|
| `Ctrl+S` | Speichern |
| `Ctrl+O` | Datei öffnen |
| `Ctrl+R` oder `Ctrl+Enter` | Aktuelle `.scrape`-Datei kompilieren |
| `F1` | Erstes Menü öffnen oder schließen |
| `Tab` | Autovervollständigung übernehmen, falls Vorschläge angezeigt werden; sonst Tabulator einfügen |
| Pfeiltasten | Cursor bewegen oder einen Autovervollständigungsvorschlag auswählen |

Auf macOS funktionieren `Cmd`-Kombinationen für Speichern, Öffnen und Kompilieren ebenfalls.

## Sicherheit und Zugriff

Der Editor kann Dateien im angegebenen Workspace lesen und überschreiben und startet die Transpiler als lokale Prozesse. Verwende ihn daher nur mit einem Workspace, dem du vertraust.

Der Server bindet standardmäßig an `0.0.0.0`, akzeptiert aber standardmäßig nur Verbindungen von Loopback-Adressen (`127.0.0.1` und `::1`). Mit `--ip <IP>` können weitere einzelne Client-Adressen zugelassen werden. **`--ip all` hebt diese Einschränkung vollständig auf und sollte nicht in einem nicht vertrauenswürdigen Netzwerk verwendet werden.** Der Server stellt HTTP bereit und ist nicht für eine ungeschützte Veröffentlichung im Internet ausgelegt.

Pfade in der Weboberfläche sind relativ zum Workspace. Absolute Pfade und Pfadbestandteile `..`, die aus dem Workspace herausführen würden, werden zurückgewiesen.

## Fehlerbehebung

- **Transpiler oder Detranspiler nicht gefunden:** Prüfe die Pfade in `--transpiler` und `--detranspiler`. Beim Start aus dem Repository-Hauptverzeichnis verwende die Beispiele oben.
- **Port belegt oder Server startet nicht:** Wähle mit `--port` einen freien Port.
- **Client-IP nicht freigegeben:** Verwende den Editor lokal oder füge die konkrete Adresse mit `--ip <IP>` hinzu.
- **Kompilierung schlägt fehl:** Prüfe die Ausgabe im unteren Transpiler-Bereich und stelle sicher, dass eine vorhandene `.scrape`-Datei geöffnet ist.
- **Datei kann nicht gespeichert oder geöffnet werden:** Prüfe UTF-8-Kodierung, Schreibrechte und das 2-MiB-Limit.

## Projektdatei

Der Webeditor ist in `Editor.py` implementiert; die HTML-Oberfläche und das JavaScript werden vom Python-Skript bereitgestellt. Die Scrape-Transpiler-Dokumentation findest du in [`Transpiler/README.md`](../Transpiler/README.md) und die Detranspiler-Dokumentation in [`Detranspiler/README.md`](../Detranspiler/README.md).
