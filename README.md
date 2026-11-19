# ScrapeLang

ScrapeLang ist ein Projekt für die Übersetzung einer Java-ähnlichen Skriptsprache in Scratch-/TurboWarp-Projekte (`.sb3`) sowie die Rückumwandlung von Scratch-Projekten in Scrape-Quellcode.

Das Repository enthält drei zentrale Komponenten:

- `Transpiler`: Übersetzt `.scrape`-Quellcode in ein Scratch-Projekt.
- `Detranspiler`: Wandelt `.sb3`-Dateien zurück in lesbaren Scrape-Code.
- `ScrapeEditor`: Entwicklungsumgebung bzw. Editor-Tooling rund um den Scrape-Workflow.

## Überblick

Scrape verbindet eine eigene Sprachsyntax mit der Scratch-Projektwelt. Damit lassen sich Projekte in einer textbasierten, Java-ähnlichen Form schreiben und anschließend als Scratch-3-Projekte exportieren.

Das Projekt ist primär in Python umgesetzt, ergänzt durch Java-basierte Sprach- und Projektstrukturen, die im Compiler/Interpreter und im Editor-Umfeld genutzt werden.

## Repository-Struktur

```text
Scrape/
├── Transpiler/
│   ├── Transpiler.py
│   └── README.md
├── Detranspiler/
│   ├── Detranspiler.py
│   └── README.md
├── ScrapeEditor/
│   ├── README.md
│   ├── src/
│   ├── libs/
│   ├── out/
│   └── ...
├── LICENSE
├── README.md
└── .gitignore
```

## Komponenten

### Transpiler

Der Transpiler liest `.scrape`-Dateien und erzeugt daraus Scratch-3-Projekte im `.sb3`-Format. Er unterstützt unter anderem:

- Ereignisse wie `onFlagClicked`, `onKeyPressed` oder `onBroadcastReceived`
- Variablen, Listen und Custom Blocks
- Bewegung, Aussehen, Sound, Pen- und UI-Operationen
- Ausgabe als `.sb3` mit optionalem Watch-Modus und Desktop-Integration

Mehr Details findest du in `Transpiler/README.md`.

### Detranspiler

Der Detranspiler nimmt `.sb3`-Projekte und versucht, sie wieder in lesbaren Scrape-Code zu rekonstruieren. Das ist besonders nützlich, um vorhandene Scratch-Projekte in den Scrape-Workflow zu überführen.

Mehr Details findest du in `Detranspiler/README.md`.

### ScrapeEditor

Der Editorbereich enthält die IDE/Workbench für das Scrape-Projekt, inklusive Projektdateien, Bibliotheken, Lizenzen und zusätzlichen Editor-Assets.

Mehr Details findest du in `ScrapeEditor/README.md`.

## Voraussetzungen

- Python 3.10 oder höher
- Optional: Pillow für Bildkonvertierungen im Transpiler
- Für spezielle Desktop-Integrationen müssen entsprechende Scratch-/TurboWarp-Apps lokal verfügbar sein

## Schnellstart

### Transpiler verwenden

```bash
python Transpiler/Transpiler.py dein_projekt.scrape
```

Oder mit eigener Ausgabedatei:

```bash
python Transpiler/Transpiler.py dein_projekt.scrape --out build/dein_projekt.sb3
```

### Detranspiler verwenden

```bash
python Detranspiler/Detranspiler.py dein_projekt.sb3
```

Mit eigener Zieldatei:

```bash
python Detranspiler/Detranspiler.py dein_projekt.sb3 --output quellcode/dein_projekt.scrape
```

## Verzweigung der Dokumentation

Die Projekt-Dokumentation ist auf die einzelnen Komponenten aufgeteilt:

- `Transpiler/README.md` – vollständige Syntax- und CLI-Dokumentation
- `Detranspiler/README.md` – Dekompilierung und SB3-Import
- `ScrapeEditor/README.md` – Editor-/IDE-Details und Umgebung

## Ziel des Projekts

Das Ziel von Scrape ist es, Scratch-Projekte über eine textbasierte, programmierbare und strukturell lesbare Sprache zu erstellen, zu bearbeiten und wieder in Scratch-Form zu exportieren. Dadurch entsteht eine Brücke zwischen Code-gestützter Projektentwicklung und dem Scratch-/TurboWarp-Ökosystem.

## Weitere Hinweise

- Das Projekt ist kein generischer Java-Compiler, sondern eine Scratch-orientierte Sprach- und Export-Umgebung.
- Die Genauerigkeit von Roundtrips hängt von den unterstützten Scratch-Blöcken und den jeweiligen Projektmerkmalen ab.
- Für die vollumfängliche Nutzung empfehlen sich die jeweiligen Modul-READMEs.

## Lizenz

Bitte prüfe die Repository-Dateien auf den jeweils verwendeten Lizenz- und Abhängigkeitshinweisen, falls du das Projekt weiterverwenden oder veröffentlichen möchtest.
