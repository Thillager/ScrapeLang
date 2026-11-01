# Scrape Transpiler

**Transpiler.py – Scrape-Quellcode nach Scratch-/TurboWarp-Projekten (`.sb3`)**

Der Scrape Transpiler übersetzt die Java-ähnliche Scrape-Syntax in das Scratch-3-Projektformat. Eine erzeugte `.sb3`-Datei ist ein ZIP-Archiv mit `project.json` und den benötigten Asset-Dateien. Der Transpiler kann Projekte zusätzlich validieren, Änderungen einer Quelldatei beobachten und TurboWarp Desktop oder den Scratch Desktop Player starten.

> Die Dokumentation beschreibt den aktuellen Stand des bereitgestellten `Transpiler.py` (v5.0). Sie ist keine Zusicherung, dass jeder beliebige Scratch-Block oder jedes Scratch-Projekt verlustfrei unterstützt wird.

## Inhalt

- [Voraussetzungen](#voraussetzungen)
- [Installation und Dateien](#installation-und-dateien)
- [Schnellstart](#schnellstart)
- [Kommandozeile](#kommandozeile)
- [Aufbau eines Scrape-Projekts](#aufbau-eines-scrape-projekts)
- [Syntaxreferenz](#syntaxreferenz)
- [Assets: Kostüme, Hintergründe und Sounds](#assets-kostüme-hintergründe-und-sounds)
- [Variablen, Listen und eigene Blöcke](#variablen-listen-und-eigene-blöcke)
- [Validierung und Fehlersuche](#validierung-und-fehlersuche)
- [Watch-Modus und Desktop-Apps](#watch-modus-und-desktop-apps)
- [Ausgabe- und Cache-Dateien](#ausgabe--und-cache-dateien)
- [Grenzen und bekannte Hinweise](#grenzen-und-bekannte-hinweise)

## Voraussetzungen

- **Python 3.10 oder neuer.** Der Quellcode verwendet moderne Typannotationen wie `str | None`.
- Für Bildkonvertierungen ist **Pillow** optional:

  ```bash
  python -m pip install Pillow
  ```

  Ohne Pillow können PNG-Dateien weiterhin direkt eingebunden werden. Andere Rasterbildformate werden dann nicht zuverlässig konvertiert und können durch Platzhalter ersetzt werden. SVG-Dateien werden separat behandelt.
- Für den Start einer Desktop-App muss die betreffende App installiert sein und an einem der vom Skript gesuchten Standardpfade liegen. Die Erkennung ist abhängig vom Betriebssystem und der Installationsart.
- Für den ersten Abruf der Scratch-Bibliotheks-Metadaten ist eine Internetverbindung hilfreich. Der Transpiler speichert diese Metadaten lokal und verwendet den Cache bis zu sieben Tage.

## Installation und Dateien

Lege `Transpiler.py` in einen Arbeitsordner. Die `.scrape`-Datei ist die Eingabe. Dateien für Kostüme, Hintergründe und Sounds können relativ zum Ordner der `.scrape`-Datei angegeben werden.

Beispiel:

```text
MeinProjekt/
├── Transpiler.py
├── spiel.scrape
└── assets/
    ├── held.png
    └── musik.mp3
```

Der Transpiler benötigt keine weitere Python-Bibliothek für das reine Parsen und Erzeugen der `.sb3`-Datei. Pillow ist optional.

## Schnellstart

Projekt einmal übersetzen:

```bash
python Transpiler.py spiel.scrape
```

Mit eigenem Ausgabepfad:

```bash
python Transpiler.py spiel.scrape --out build/spiel.sb3
```

TurboWarp Desktop nach erfolgreicher Übersetzung starten:

```bash
python Transpiler.py spiel.scrape --turbowarp-new
```

Watch-Modus mit TurboWarp Desktop:

```bash
python Transpiler.py spiel.scrape --watch --turbowarp-replace
```

Die vollständige Hilfe ist jederzeit abrufbar:

```bash
python Transpiler.py --help
```

## Kommandozeile

```text
python Transpiler.py <eingabe.scrape> [Optionen]
```

| Option | Bedeutung |
|---|---|
| `--out <datei.sb3>` | Legt den Pfad der erzeugten Projektdatei fest. Standard: `output.sb3`. |
| `--watch` | Beobachtet die Quelldatei und übersetzt sie bei erkannten Änderungen erneut. |
| `--turbowarp-new` | Startet TurboWarp Desktop nach erfolgreicher Übersetzung, ohne vorherige Instanzen zu beenden. |
| `--turbowarp-replace` | Liest nach Möglichkeit die Fensterposition aus, beendet laufende TurboWarp-Instanzen und startet TurboWarp mit dem neuen Projekt erneut. |
| `--scratch-new` | Startet den Scratch Desktop Player, ohne vorherige Instanzen zu beenden. |
| `--scratch-replace` | Beendet laufende Scratch Desktop-Player-Instanzen und startet den Player mit dem neuen Projekt erneut. |
| `--help`, `-h` | Zeigt die Hilfe an. |

Die TurboWarp- und Scratch-Startoptionen sind als alternative Modi gedacht. Werden mehrere App-Optionen angegeben, meldet das Skript einen Hinweis und verwendet die zuletzt gelesene Option.

### Relative Pfade

Der Ausgabepfad wird relativ zum aktuellen Arbeitsverzeichnis des Prozesses interpretiert, sofern kein absoluter Pfad angegeben wird. Das ist besonders bei Aufrufen aus einer IDE oder einem Editor wichtig: Das aktuelle Arbeitsverzeichnis muss nicht automatisch der Ordner der Eingabedatei sein.

## Aufbau eines Scrape-Projekts

Ein Projekt besteht aus einer Stage (Bühne) und einem oder mehreren Sprites. Die Stage wird als `Stage`-Target im Scratch-Projekt erzeugt. Im Scrape-Quelltext ist `Stage` der Typ; der Name dahinter ist ein normaler Bezeichner. Für Projekte aus dem Detranspiler wird die Bühne `Buehne` genannt.

```java
public Stage Buehne {
    addBackdrop("Forest");

    onFlagClicked {
        broadcast("Start");
    }
}

public Sprite Spieler {
    addCostume("Mouse1-a");

    onFlagClicked {
        goTo(0, 0);
        show();
    }
}
```

Allgemeine Form:

```java
public Stage Buehne {
    // Bühnen-Inhalt
}

public Sprite SpriteName {
    // Sprite-Inhalt
}
```

Die Reihenfolge der Targets im Quelltext wird für die Sprite-Reihenfolge verwendet. Die Bühne wird beim Erstellen immer als erstes Target angelegt. Fehlt ein Stage-Block ganz, erzeugt der Transpiler trotzdem eine leere Standardbühne mit einem Hintergrund.

### Kommentare

Einzeilige Kommentare:

```java
// Das ist ein Kommentar
```

Mehrzeilige Kommentare:

```java
/*
   Mehrzeiliger Kommentar
*/
```

Kommentare, die direkt an einem Statement stehen, können als Scratch-Blockkommentare übernommen werden.

## Syntaxreferenz

Alle Statements stehen innerhalb eines Stage- oder Sprite-Blocks. Die meisten Befehle enden mit einem Semikolon. Kontrollstrukturen und Event-Blöcke verwenden geschweifte Klammern. Bezeichner (Stage-, Sprite-, Variablen- und Funktionsnamen) müssen dem aktuellen ASCII-Muster `[A-Za-z_][A-Za-z0-9_]*` entsprechen: Beginne mit einem englischen Buchstaben oder Unterstrich; danach sind Buchstaben, Ziffern und Unterstriche erlaubt. Umlaute und Leerzeichen gehören nicht in Bezeichner. Strings und Kommentare dürfen dagegen Text mit Leerzeichen und Umlauten enthalten.

### Events

| Scrape-Syntax | Auslöser |
|---|---|
| `onFlagClicked { ... }` | Grüne Flagge |
| `onKeyPressed("space") { ... }` | Taste wurde gedrückt |
| `onSpriteClicked { ... }` | Sprite wurde angeklickt |
| `onBackdropChanged("Forest") { ... }` | Hintergrund wurde gewechselt |
| `onBroadcastReceived("Start") { ... }` | Nachricht wurde empfangen |

### Kontrollfluss und Ablauf

```java
wait(1.5);
waitUntil(xPosition > 0);

repeat(10) {
    move(10);
}

forever {
    turnRight(5);
}

if (xPosition > 100) {
    say("rechts");
} else if (xPosition < -100) {
    say("links");
} else {
    say("mitte");
}

// Gleichwertige Kurzform für else-if-Ketten:
if (punkte > 10) {
    say("Gewonnen");
} elseif (punkte == 10) {
    say("Gleichstand");
} else {
    say("Weiter versuchen");
}

repeatUntil(touching("edge")) {
    move(2);
}

stop("this script");
createClone("myself");
deleteClone();
```

Gültige `stop`-Optionen sind `"all"`, `"this script"` und `"other scripts in sprite"`. Für `createClone` kann `"myself"` oder der Name eines Sprites verwendet werden.

### Bewegung

| Befehl | Wirkung |
|---|---|
| `move(10);` | Bewegt um Schritte. |
| `turnLeft(15);`, `turnRight(15);` | Dreht um Grad. |
| `goTo(0, 0);` | Setzt x- und y-Position. |
| `goToSprite("Spieler");` | Geht zu einem Sprite oder einem speziellen Ziel wie `"_mouse_"` bzw. `"_random_"`. |
| `glide(1, 100, 50);` | Gleitet in Sekunden zu x/y. |
| `glideToSprite(1, "Spieler");` | Gleitet in Sekunden zu einem Sprite. |
| `pointDir(90);` | Setzt die Richtung. |
| `pointTowards("mouse-pointer");` | Zeigt zu einem Ziel. |
| `setX(10);`, `setY(20);` | Setzt eine Koordinate. |
| `changeX(5);`, `changeY(-5);` | Ändert eine Koordinate. |
| `bounceOnEdge();` | Prallt am Rand ab. |
| `setRotationStyle("left-right");` | Setzt den Drehstil. |

Gültige Drehstile: `"all around"`, `"left-right"`, `"don't rotate"`.

### Aussehen

```java
say("Hallo!");
sayFor("Hallo!", 2);
think("Hmm...");
thinkFor("Hmm...", 2);

switchCostume("Kostüm1");
nextCostume();
setSize(100);
changeSize(10);
show();
hide();
goToFront();
goToBack();
goForwardLayers(1);
goBackwardLayers(1);
setEffect("color", 25);
changeEffect("ghost", 10);
clearEffects();
```

Gültige Effekte: `"color"`, `"fisheye"`, `"whirl"`, `"pixelate"`, `"mosaic"`, `"brightness"`, `"ghost"`.

Auf der Stage sind zusätzlich `switchBackdrop("Forest");` und `nextBackdrop();` vorgesehen.

Der Helfer `animate` wechselt zwischen einer oder mehreren Kostümen:

```java
animate("Lauf1", "Lauf2", 0.1);
```

Die Kostüme müssen im selben Sprite mit `addCostume` definiert sein.

### Sound

```java
playSound("Meow");
playSoundUntilDone("Meow");
stopAllSounds();
setVolume(80);
changeVolume(-10);
```

Die Soundnamen müssen im selben Target mit `addSound` definiert sein.

### Variablen und Listen

```java
public var punkte = 0;
private var intern = 1;
shown var level = 1;
hidden var debugWert = 0;

punkte = 10;
punkte += 5;
punkte -= 1;
punkte *= 2;
punkte /= 2;
punkte++;
punkte--;

showVar("punkte");
hideVar("debugWert");
```

Listen werden bei ihrer Verwendung angelegt. Es gibt im aktuellen Quellformat keine eigene vollständige Listen-Deklaration mit Anfangswerten. Verfügbare Statements:

```java
inventar.add("Schlüssel");
inventar.delete(1);
inventar.insert(1, "Trank");
inventar.replace(1, "Münze");
inventar.show();
inventar.hide();
```

Listen-Ausdrücke:

```java
inventar[1]
inventar.length()
inventar.contains("Schlüssel")
```

Variablen-Scope:

- `public var` ist global und wird im Stage-Target gespeichert; alle Sprites können darauf zugreifen.
- `private var` wird lokal im jeweiligen Sprite gespeichert.
- Ohne Scope-Angabe ist `public` der Standard.
- Ohne Anzeige-Modifikator ist `shown` der Standard. `hidden` blendet den Variablenmonitor aus.
- `shown` und `hidden` können mit `public` bzw. `private` kombiniert werden.

### Eigene Blöcke (Custom Blocks)

```java
void begruesse(string name) {
    say(join("Hallo ", name));
}

begruesse("Mia");
```

`define` ist ebenfalls als Definitions-Schlüsselwort zugelassen:

```java
define zaehleHoch() {
    punkte++;
}
```

Ein `private void` bzw. ein `hidden void` wird im Generator als Warp-Custom-Block markiert:

```java
private void schnelleBerechnung() {
    punkte += 1;
}
```

**Hinweis zur Parametertypisierung:** Der Parser akzeptiert `number`, `int`, `float`, `string`, `str`, `boolean` und `bool` als optionale Parameterannotationen. Im aktuellen Code werden `number`/`int`/`float` jedoch wie String-Parameter (`%s`) abgebildet; `boolean`/`bool` wird als Boolean-Slot (`%b`) abgebildet. Die Typabbildung für numerische Custom-Block-Parameter sollte daher vor einer Verwendung in Zahlen-Slots geprüft bzw. im Code korrigiert werden. Nicht annotierte Parameter sind ebenfalls String-Parameter.

### Nachrichten, Klone und Eingabe

```java
broadcast("Start");
broadcastAndWait("Fertig");
askAndWait("Wie heißt du?");
setDragMode("draggable");
resetTimer();
```

`setDragMode` akzeptiert `"draggable"` und `"not draggable"`.

### Stift-Erweiterung

```java
import "pen";

penDown();
penUp();
setPenColor(255);
changePenColor(10);
setPenSize(3);
changePenSize(1);
stampPen();
erasePen();
```

Wenn Stift-Befehle vorkommen, fügt der Generator die `pen`-Extension außerdem automatisch hinzu. Andere bekannte Erweiterungen werden über `import` aktiviert:

```java
import "music";
import "video";
import "text2speech";
import "translate";
import "makey";
import "microbit";
import "ev3";
import "boost";
import "wedo";
import "gdxfor";
```

Die Erweiterungen werden in die Scratch-Projektmetadaten eingetragen. Das bedeutet nicht, dass sämtliche Blöcke dieser Erweiterungen bereits als Scrape-Befehle implementiert sind.

### Ausdrücke, Operatoren und Sensoren

Numerische und logische Operatoren:

```java
1 + 2 * 3
punkte >= 10
name == "Mia"
punkte != 0
xPosition > 0 && mouseDown
punkte < 5 || touching("edge")
!(punkte == 0)
```

Die Parser-Priorität lautet: `* / %`, danach `+ -`, danach Vergleiche, danach `&&`, danach `||`. Klammern können die Reihenfolge ändern.

Mathematikfunktionen:

```java
Math.random(1, 10)
Math.round(2.7)
Math.abs(-5)
Math.floor(2.7)
Math.ceil(2.1)
Math.sqrt(16)
Math.sin(90)
Math.cos(0)
Math.tan(45)
Math.asin(0.5)
Math.acos(0.5)
Math.atan(1)
Math.ln(10)
Math.log(100)
```

Der Parser akzeptiert zusätzlich die Kurzformen ohne `Math.` (z.B. `random(1, 10)`, `abs(-5)`, `round(2.7)`).

Textfunktionen:

```java
length("Hallo")
letter(1, "Hallo")
contains("Hallo", "all")
join("Hallo ", "Welt")
```

Sensoren und eingebaute Werte:

```java
answer
mouseX
mouseY
mouseDown
keyPressed("space")
touching("Sprite1")
touchingColor("#ff0000")
distanceTo("Sprite1")
timer
loudness
username
xPosition
yPosition
direction
currentYear
currentMonth
currentDate
currentDayOfWeek
currentHour
currentMinute
currentSecond
true
false
```

Zusätzlich werden die Scratch-Ausdrücke für Größe, Kostümnummer/-name und Hintergrundnummer/-name vom Generator unterstützt, soweit sie aus dem entsprechenden Block erzeugt werden.

## Assets: Kostüme, Hintergründe und Sounds

### Namen aus der Scratch-Bibliothek

```java
public Sprite Katze {
    addCostume("Cat");
    addSound("Meow");
}

public Stage Buehne {
    addBackdrop("Blue Sky");
}
```

Bei Aufrufen ohne Pfad sucht der Transpiler den Namen in den gecachten Scratch-Bibliotheks-Metadaten. Ist er nicht vorhanden, wird ein Platzhalterkostüm, ein weißer Hintergrund oder ein stiller Sound eingesetzt. Der Transpiler lädt nicht automatisch jede beliebige Datei aus dem Scratch-Asset-Server.

### Lokale Dateien

```java
public Sprite Spieler {
    addCostume("Held", "assets/held.png");
    addSound("Musik", "assets/musik.mp3");
}

public Stage Buehne {
    addBackdrop("Level", "assets/level.svg");
}
```

Dateipfade werden relativ zum Verzeichnis der `.scrape`-Quelldatei aufgelöst. Für lokale Assets sind eindeutige Pfade mit Verzeichnis oder Dateiendung zu empfehlen. Der Asset-Manager verarbeitet SVG separat und verwendet Pillow (falls installiert) für die Konvertierung unterstützter Rasterbilder nach PNG.

Für bestmögliche Kompatibilität Sounddateien als MP3 oder WAV verwenden. Der aktuelle Code liest andere Audioformate zwar ebenfalls ein, normalisiert deren Audiodaten aber nicht zuverlässig in ein anderes Format.

## Validierung und Fehlersuche

Der Übersetzungslauf besteht im Wesentlichen aus diesen Schritten:

1. Tokenisierung und Parsing der Scrape-Datei.
2. Validierung von Namen, Assets, Parametern und unterstützten Werten.
3. Generierung der Scratch-Blöcke und Projektstruktur.
4. Schreiben einer JSON-Datei und der `.sb3`-ZIP-Datei.

Syntaxfehler enthalten, soweit möglich, eine Zeilennummer und einen Fix-Hinweis. Die Validierung meldet Fehler und Warnungen, unter anderem:

- Kostüm- oder Soundname nicht im Target definiert.
- Ungültiger Effektname, Drehstil, `stop`-Wert oder Drag-Modus.
- Nicht vorhandenes Sprite bei `createClone`.
- Nicht definierter Custom Block oder falsche Argumentanzahl.
- Wahrscheinlicher String-Parameter in einem Zahlen-Slot.
- Bibliotheksnamen, die nur durch Platzhalter ersetzt werden können.

Ein Validierungsfehler verhindert das Schreiben einer neuen `.sb3`-Datei. Warnungen können die Erstellung zulassen, weisen aber auf mögliche Abweichungen im Ergebnis hin.

## Watch-Modus und Desktop-Apps

Im Watch-Modus prüft der Transpiler die Änderungszeit der Eingabedatei in einem Intervall von ungefähr **0,5 Sekunden**. Bei einer erkannten Änderung wird erneut kompiliert. Bei erfolgreicher Kompilierung wird eine mit `--turbowarp-*` oder `--scratch-*` ausgewählte Desktop-App entsprechend dem Modus gestartet.

Beispiel:

```bash
python Transpiler.py spiel.scrape --watch --turbowarp-replace
```

`--turbowarp-replace` ersetzt die laufende TurboWarp-Instanz durch einen Neustart mit der neu erzeugten `.sb3`-Datei. Es handelt sich damit um einen Prozess-Neustart mit neuer Projektdatei, nicht um eine Änderung der laufenden Scratch-VM ohne Neustart.

### Fensterposition

Bei einem `*-replace`-Start versucht der Transpiler, die Fensterposition und -größe der laufenden App auszulesen, sie zu speichern und nach dem Neustart wiederherzustellen. Die Positionen werden pro App in folgender Datei abgelegt:

```text
~/.scrape_transpiler_winstate.json
```

Die Unterstützung hängt vom Betriebssystem ab. Unter Windows verwendet der Code Win32-/PowerShell-Hilfen, unter macOS AppleScript und unter Linux `xdotool`. Unter Linux muss `xdotool` für die Fenstergeometrie installiert sein. Nicht jede App-Version bzw. Fensterkonfiguration erlaubt zuverlässiges Auslesen oder Setzen.

Zum Beenden des Watch-Modus `Ctrl+C` im Terminal verwenden.

## Ausgabe- und Cache-Dateien

- `.sb3`: Scratch-3-Projektdatei.
- `.json`: zusätzliche Projekt-JSON mit demselben Basisnamen wie die Ausgabedatei. Sie wird neben der `.sb3` erstellt.
- `~/.scrape_transpiler_library.json`: Cache für die Bibliotheks-Metadaten (bis zu sieben Tage).
- `~/.scrape_transpiler_winstate.json`: gespeicherte Fenstergeometrien für Desktop-Apps.

Die `project.json` und die Assets werden zusammen in das `.sb3`-ZIP-Archiv geschrieben.

## Grenzen und bekannte Hinweise

- Das Projektformat ist Scratch 3 (`.sb3`). Die Sprache ist ein eigener Scrape-Teilbereich und kein vollständiger Java-Compiler.
- `import` registriert bekannte Extension-IDs; nicht jede Extension-Funktion ist als Scrape-Statement verfügbar.
- Die Bibliotheks-Metadaten werden online bezogen und gecacht. Ohne Cache und ohne Internet sind Bibliotheksnamen nicht vollständig auflösbar.
- Fehlende Bibliotheksassets werden durch Platzhalter bzw. Stille ersetzt; das kann ein Projekt zwar kompilierbar halten, aber visuell oder akustisch vom erwarteten Ergebnis abweichen.
- Die Variable-/Listen- und Custom-Block-Unterstützung ist durch die implementierte Grammatik begrenzt. Insbesondere ist die numerische Custom-Block-Parametertypisierung im aktuellen Code nicht deckungsgleich mit dem erklärenden Kommentar im Parser.
- Die Positionen und der Layout-Zustand von Scratch-Blöcken werden beim Erzeugen neu angelegt; der Transpiler ist kein allgemeiner Editor für beliebige Scratch-Projekt-Metadaten.

