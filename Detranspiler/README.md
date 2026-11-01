# Scrape Detranspiler

**Detranspiler.py – Scratch-/TurboWarp-Projekte (`.sb3`) in Scrape-Quellcode umwandeln**

Der Detranspiler liest eine `.sb3`-Datei, entpackt daraus die `project.json` im Arbeitsspeicher und rekonstruiert daraus eine lesbare Scrape-Datei. Dabei werden Scratch-Targets, Events, unterstützte Blöcke, Variablen, Custom Blocks und Block-Kommentare in die Java-ähnliche Scrape-Syntax übertragen.

Der Detranspiler ist als Gegenstück zu `Transpiler.py` gedacht. Er ermöglicht, bestehende Scratch-Projekte im Scrape Editor weiterzubearbeiten. Die Umwandlung ist strukturell und nicht in jedem Fall verlustfrei.

> Diese Dokumentation beschreibt den bereitgestellten `Detranspiler.py`-Stand v1.0.

## Inhalt

- [Voraussetzungen](#voraussetzungen)
- [Installation](#installation)
- [Schnellstart](#schnellstart)
- [Kommandozeile](#kommandozeile)
- [Was wird aus einer SB3-Datei gelesen?](#was-wird-aus-einer-sb3-datei-gelesen)
- [Wie sieht der erzeugte Scrape-Code aus?](#wie-sieht-der-erzeugte-scrape-code-aus)
- [Unterstützte Scratch-Blöcke](#unterstützte-scratch-blöcke)
- [Watch-Modus](#watch-modus)
- [Grenzen und mögliche Informationsverluste](#grenzen-und-mögliche-informationsverluste)
- [Fehlerbehebung](#fehlerbehebung)

## Voraussetzungen

- **Python 3.10 oder neuer.**
- Keine externen Python-Pakete sind für die Konvertierung erforderlich. Verwendet werden Python-Standardbibliotheken (`json`, `zipfile`, `sys`, `time`, `re` und `pathlib`).
- Die Eingabedatei muss ein gültiges Scratch-3-Projekt im `.sb3`-Format sein und im ZIP-Archiv eine `project.json` enthalten.

## Installation

Lege `Detranspiler.py` in einen Ordner oder verwende den Ordner, in dem deine `.sb3`-Datei liegt. Die Ausgabedatei wird standardmäßig im aktuellen Arbeitsverzeichnis abgelegt.

```text
Projekt/
├── Detranspiler.py
└── spiel.sb3
```

## Schnellstart

Eine `.sb3`-Datei in `output.scrape` umwandeln:

```bash
python Detranspiler.py spiel.sb3
```

Einen eigenen Ausgabepfad angeben:

```bash
python Detranspiler.py spiel.sb3 --output quellcode/spiel.scrape
```

Die vollständige Hilfe anzeigen:

```bash
python Detranspiler.py --help
```

## Kommandozeile

```text
python Detranspiler.py <eingabe.sb3> [Optionen]
```

| Option | Bedeutung |
|---|---|
| `--output <datei.scrape>` | Legt die Zieldatei fest. Standard: `output.scrape`. |
| `--out <datei.scrape>` | Alias für `--output`. |
| `--watch` | Beobachtet die `.sb3`-Datei und dekompiliert sie bei erkannter Änderung erneut. |
| `--help`, `-h` | Zeigt die Hilfe an. |

Die Eingabedatei muss angegeben werden. Relative Eingabe- und Ausgabepfade werden relativ zum aktuellen Arbeitsverzeichnis aufgelöst.

## Was wird aus einer SB3-Datei gelesen?

Eine `.sb3`-Datei ist ein ZIP-Archiv. Der Detranspiler öffnet daraus `project.json` und liest unter anderem:

- `targets` mit Stage und Sprites,
- Block-Dictionaries und deren `opcode`, Inputs, Fields und Verbindungen,
- Variablen und Listen,
- Scratch-Events,
- Custom-Block-Definitionen und Aufrufe,
- Extension-IDs aus `extensions`,
- an Blöcken gespeicherte Kommentare,
- Namen von Kostümen, Hintergründen und Sounds.

Die Asset-Dateien selbst werden nicht in einzelne Quelldateien exportiert. In den erzeugten Code kommen nur die Asset-Namen. Der Transpiler muss diese Namen beim späteren Kompilieren erneut einer Bibliothek oder lokalen Datei zuordnen.

## Wie sieht der erzeugte Scrape-Code aus?

Die Bühne wird zuerst ausgegeben, danach folgen die Sprites. Der Typ der Bühne bleibt `Stage`; ihr Scrape-Bezeichner lautet fest `Buehne`, weil `Stage` im Scrape-Parser ein reserviertes Schlüsselwort ist.

Beispiel:

```java
public Stage Buehne {
    addBackdrop("Forest");

    onFlagClicked {
        broadcast("Start");
    }
}

public Sprite Cat {
    addCostume("costume1");

    onSpriteClicked {
        say("Hallo!");
    }
}
```

### Erweiterungen

Bekannte Scratch-Extension-IDs werden in Scrape-Imports umgewandelt. Beispiele:

| Scratch-Extension-ID | Scrape-Import |
|---|---|
| `pen` | `import "pen";` |
| `music` | `import "music";` |
| `videoSensing` | `import "video";` |
| `text2speech` | `import "text2speech";` |
| `translate` | `import "translate";` |
| `makeymakey` | `import "makey";` |
| `microbit` | `import "microbit";` |
| `ev3` | `import "ev3";` |
| `boost` | `import "boost";` |
| `wedo2` | `import "wedo";` |
| `gdxfor` | `import "gdxfor";` |

Nicht erkannte IDs werden als Import-Text übernommen. Der Scrape Transpiler kann solche unbekannten Importe anschließend allerdings als ungültige Erweiterung zurückweisen.

### Bühne und Sprites

- Die Stage wird als `public Stage Buehne { ... }` ausgegeben.
- Sprites werden als `public Sprite <Scratch-Name> { ... }` ausgegeben.
- Kostüme bzw. Bühnenbilder werden als `addCostume("...");` bzw. `addBackdrop("...");` ausgegeben.
- Sounds werden als `addSound("...");` ausgegeben.
- Stage-Variablen werden als `public var` dargestellt.
- Sprite-Variablen werden als `private var` dargestellt.

### Kommentare

Kommentare, die im Scratch-Projekt an einem Block hängen, werden als Scrape-Kommentare wiedergegeben. Kommentare ohne zugeordneten Block oder andere projektweite Notizen werden nicht notwendigerweise übernommen.

### Custom Blocks

Custom-Block-Definitionen werden als `void`-Definition ausgegeben. Ein Scratch-Custom-Block mit Warp-Einstellung wird als `private void` wiedergegeben. Die Parameter werden anhand der Scratch-Prozedur-Signatur möglichst mit `number`, `boolean` oder ohne Typpräfix rekonstruiert.

### Listen

Listen werden aktuell nur als Kommentar ausgegeben, zum Beispiel:

```java
// var inventar = [];  // Liste
```

Zugriffe und Listenbefehle können an anderer Stelle in den generierten Statements vorkommen. Die auskommentierte Zeile ist aber keine aktive Listen-Deklaration und enthält keine ursprünglichen Anfangswerte. Das erneute Erzeugen der Liste hängt daher von den tatsächlich verwendeten Listenoperationen und der Unterstützung im Transpiler ab.

## Unterstützte Scratch-Blöcke

Die folgenden Gruppen werden im Detranspiler explizit abgebildet. Die genaue Verfügbarkeit einzelner Opcode-Varianten hängt vom tatsächlichen Scratch-Blockformat ab.

### Bewegung

- `motion_movesteps` → `move(...)`
- `motion_turnleft`, `motion_turnright` → `turnLeft(...)`, `turnRight(...)`
- `motion_gotoxy`, `motion_goto` → `goTo(...)` bzw. `goToSprite(...)`
- `motion_glidesecstoxy`, `motion_glideto` → `glide(...)`, `glideToSprite(...)`
- `motion_pointindirection`, `motion_pointtowards` → `pointDir(...)`, `pointTowards(...)`
- `motion_setx`, `motion_sety`, `motion_changexby`, `motion_changeyby`
- `motion_ifonedgebounce`, `motion_setrotationstyle`

### Aussehen

- Sagen und Denken: `say`, `sayFor`, `think`, `thinkFor`
- Kostüm- und Hintergrundwechsel: `switchCostume`, `nextCostume`, `switchBackdrop`, `nextBackdrop`
- Größe, Sichtbarkeit und Ebenenreihenfolge
- Grafikeffekte: `setEffect`, `changeEffect`, `clearEffects`

### Sound

- Sound abspielen bzw. bis zum Ende abspielen
- Alle Sounds stoppen
- Lautstärke setzen und ändern

### Events und Steuerung

- Grüne Flagge
- Taste gedrückt
- Sprite bzw. Stage angeklickt
- Hintergrundwechsel
- Broadcast empfangen und senden
- Warten, Wiederholen, für immer wiederholen, `if`, `if/else`, `repeatUntil`, `waitUntil`, `stop`
- Klon erstellen und aktuellen Klon löschen

### Sensing und Daten

- Frage stellen und auf Antwort warten
- Drag-Modus und Timer zurücksetzen
- Variablen setzen, ändern und Monitor zeigen/verstecken
- Listenoperationen: Element hinzufügen, löschen, einfügen, ersetzen, Monitor zeigen/verstecken
- Variablen, Listenwerte, Listenlänge und Listenabfragen in Ausdrücken
- Maus-, Tastatur-, Timer-, Lautstärke-, Benutzername-, Positions-, Richtungs- und Datumswerte
- Berührung, Berührung einer Farbe und Abstand zu einem Ziel

### Operatoren

- Zahlen, Text und Farben
- Addition, Subtraktion, Multiplikation, Division und Modulo
- Vergleiche und logische Verknüpfungen
- Zufallszahl, Rundung und mathematische Operatoren
- Textlänge, Buchstabe, Enthält-Prüfung und Textverknüpfung

### Pen-Erweiterung

Die Standard-Pen-Operationen `penDown`, `penUp`, Stiftfarbe setzen/ändern, Stiftgröße setzen/ändern, `stampPen` und `erasePen` werden in Scrape-Befehle übersetzt.

### Nicht erkannte Blöcke und Events

Ein nicht explizit unterstützter Statement-Opcode wird als Kommentar in den generierten Quellcode geschrieben:

```java
/* unbekannter_opcode */
```

Nicht unterstützte Events werden ebenfalls als Kommentar-Hinweis ausgegeben. Ein Scratch-Clone-Start-Event wird beispielsweise als Kommentar markiert, da es im aktuellen Scrape-Eventmodell nicht implementiert ist.

Ein Kommentar bedeutet, dass der betreffende Block nicht als ausführbarer Scrape-Befehl rekonstruiert wurde.

## Watch-Modus

Beispiel:

```bash
python Detranspiler.py spiel.sb3 --output spiel.scrape --watch
```

Der Detranspiler prüft die Änderungszeit der `.sb3`-Datei ungefähr alle **0,5 Sekunden**. Wenn sie sich ändert, wird sie erneut gelesen und die angegebene `.scrape`-Datei überschrieben.

Beenden:

- Im Terminal `Ctrl+C` drücken.
- Die Ausgabe bestätigt anschließend, dass der Watch-Modus beendet wurde.

**Achtung:** Wird die Ausgabedatei gerade im Editor bearbeitet, kann ein Watch-Lauf diese Datei überschreiben. Wähle eine Ausgabe, die nicht gleichzeitig unabhängig bearbeitet wird, oder beende den Watch-Modus vor manuellen Änderungen.

## Grenzen und mögliche Informationsverluste

Der Detranspiler rekonstruiert Scrape-Code, keine vollständige Kopie der ursprünglichen Scratch-Projektdatei. Insbesondere gilt:

1. **Assets werden nicht extrahiert.** Kostüm-, Hintergrund- und Soundnamen bleiben erhalten, aber die eigentlichen Bild- und Audiodateien werden nicht neben die `.scrape`-Datei geschrieben.
2. **Sprite-Eigenschaften werden nicht vollständig abgebildet.** Position, Richtung, Größe, Sichtbarkeit, aktuelles Kostüm, Layerzustand und weitere Target-Eigenschaften sind nicht Teil des erzeugten Scrape-Blocks. Beim erneuten Transpilieren können dafür Standardwerte verwendet werden.
3. **Blocklayout wird nicht erhalten.** Die Positionen der Scratch-Blöcke in der visuellen Arbeitsfläche werden nicht in Scrape-Code überführt.
4. **Listen werden nicht vollständig deklariert.** Die Namen werden als Kommentare notiert; Anfangswerte und vollständiger Monitorzustand sind damit nicht wiederhergestellt.
5. **Unbekannte Blöcke bleiben Kommentare.** Sie sind dadurch dokumentiert, aber nicht ausführbar.
6. **Erweiterte Scratch-Funktionen sind nur teilweise abgedeckt.** Spezialblöcke, Drittanbieter-Extensions und neue Scratch-VM-Blocktypen können fehlen.
7. **Roundtrip ist nicht garantiert.** Eine `.sb3` → `.scrape` → `.sb3`-Konvertierung kann in Inhalt, Assets, Sprite-Eigenschaften und Blocklayout vom Original abweichen.

Vor einer Weiterbearbeitung sollte immer eine Kopie der ursprünglichen `.sb3`-Datei aufbewahrt werden.

## Fehlerbehebung

### `Keine gültige Projektdatei (.sb3)`

- Prüfen, ob die Datei eine echte Scratch-3-`.sb3` ist.
- Die Datei testweise in Scratch oder TurboWarp öffnen.
- Prüfen, ob das Archiv `project.json` enthält.

### `File is not a zip file` oder ZIP-Fehler

Die Datei kann beschädigt sein oder nur eine umbenannte Datei mit `.sb3`-Endung sein. Eine `.sb3` muss ein gültiges ZIP-Archiv sein.

### Ausgabedatei wird nicht erstellt

- Prüfen, ob der Zielordner existiert.
- Schreibrechte im Zielordner prüfen.
- Einen absoluten Ausgabepfad testen.

### Quellcode enthält `/* opcode */`

Der entsprechende Scratch-Block ist in der aktuellen Detranspiler-Version nicht als ausführbarer Scrape-Befehl implementiert. Der Kommentar ist ein Hinweis auf die fehlende Abbildung.

