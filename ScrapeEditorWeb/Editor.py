#!/usr/bin/env python3
"""Scrape-Webeditor mit Dateiliste, Syntaxfarben, Autocomplete und Transpiler-Ausgabe."""

import argparse
import hmac
import ipaddress
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


SCRIPT_DIR = Path(__file__).resolve().parent
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_BODY_BYTES = MAX_FILE_BYTES + 32 * 1024
PROCESS_TIMEOUT = 120
MAX_WATCH_OUTPUT = 100_000


# Jeder Eintrag: trigger, insert, label, description, cursorBack.
# Ein "|" in markiert die Cursorposition nach dem Einfügen.
AC_ENTRIES = [
    ("public", "public ", "public", "Öffentlicher Modifikator (global)", 0),
    ("private", "private ", "private", "Privater Modifikator (Sprite-lokal)", 0),
    ("shown", "shown ", "shown", "Variablenmonitor anzeigen", 0),
    ("hidden", "hidden ", "hidden", "Variablenmonitor verstecken", 0),
    ("Sprite", "Sprite ", "Sprite", "Sprite definieren", 0),
    ("Stage", "Stage ", "Stage", "Bühne definieren", 0),
    ("var", "var | = ;", "var", "Variable deklarieren", 0),
    ("void", "void |() {\n\t\n}", "void name()", "Eigenen Block definieren", 0),
    ("define", "define |() {\n\t\n}", "define name()", "Eigenen Block definieren", 0),
    ("import", 'import "|";', "import", "Erweiterung importieren", 0),

    ("onFlagClicked", "onFlagClicked {\n\t|\n}", "onFlagClicked", "Bei Klick auf die grüne Flagge", 0),
    ("onKeyPressed", 'onKeyPressed("space") {\n\t|\n}', 'onKeyPressed("key")', "Bei Tastendruck", 0),
    ("onSpriteClicked", "onSpriteClicked {\n\t|\n}", "onSpriteClicked", "Bei Sprite-Klick", 0),
    ("onBackdropChanged", 'onBackdropChanged("|") {\n\t\n}', "onBackdropChanged(name)", "Bei Bühnenbildwechsel", 0),
    ("onBroadcastReceived", 'onBroadcastReceived("|") {\n\t\n}', "onBroadcastReceived(message)", "Bei Nachricht", 0),
    ("onCloneCreated", "onCloneCreated {\n\t|\n}", "onCloneCreated", "Beim Klonstart", 0),

    ("repeat", "repeat (|) {\n\t\n}", "repeat(n)", "Block n-mal wiederholen", 0),
    ("forever", "forever {\n\t|\n}", "forever", "Endlosschleife", 0),
    ("if", "if (|) {\n\t\n}", "if (Bedingung)", "Bedingte Ausführung", 0),
    ("else", "else {\n\t|\n}", "else", "Sonst-Zweig", 0),
    ("elseif", "elseif (|) {\n\t\n}", "elseif (Bedingung)", "Sonst-wenn-Zweig", 0),
    ("repeatUntil", "repeatUntil (|) {\n\t\n}", "repeatUntil(Bedingung)", "Wiederholen bis Bedingung wahr ist", 0),
    ("wait", "wait(|);", "wait(secs)", "Warten", 0),
    ("waitUntil", "waitUntil(|);", "waitUntil(Bedingung)", "Warten bis Bedingung wahr ist", 0),
    ("stop", 'stop("|");', 'stop("all")', "Skript stoppen", 0),

    ("createClone", 'createClone("|");', "createClone(name)", "Klon erstellen", 0),
    ("deleteClone", "deleteClone();", "deleteClone()", "Aktuellen Klon löschen", 0),
    ("move", "move(|);", "move(steps)", "Sprite bewegen", 0),
    ("turnLeft", "turnLeft(|);", "turnLeft(degrees)", "Nach links drehen", 0),
    ("turnRight", "turnRight(|);", "turnRight(degrees)", "Nach rechts drehen", 0),
    ("goTo", "goTo(|, );", "goTo(x, y)", "Position setzen", 0),
    ("goToSprite", 'goToSprite("|");', "goToSprite(name)", "Zu Sprite gehen", 0),
    ("glide", "glide(|, , );", "glide(secs, x, y)", "Zu Position gleiten", 0),
    ("glideToSprite", 'glideToSprite(|, "");', "glideToSprite(secs, name)", "Zu Sprite gleiten", 0),
    ("pointDir", "pointDir(|);", "pointDir(degrees)", "Richtung setzen", 0),
    ("pointTowards", 'pointTowards("|");', "pointTowards(name)", "Zu Objekt zeigen", 0),
    ("setX", "setX(|);", "setX(x)", "X-Position setzen", 0),
    ("setY", "setY(|);", "setY(y)", "Y-Position setzen", 0),
    ("changeX", "changeX(|);", "changeX(dx)", "X-Position ändern", 0),
    ("changeY", "changeY(|);", "changeY(dy)", "Y-Position ändern", 0),
    ("bounceOnEdge", "bounceOnEdge();", "bounceOnEdge()", "Am Rand abprallen", 0),
    ("setRotationStyle", 'setRotationStyle("|");', "setRotationStyle(style)", "Drehstil ändern", 0),

    ("say", 'say("|");', 'say("text")', "Sprechblase anzeigen", 0),
    ("sayFor", 'sayFor("|", );', "sayFor(text, secs)", "Sprechblase mit Dauer", 0),
    ("think", 'think("|");', 'think("text")', "Denkblase anzeigen", 0),
    ("thinkFor", 'thinkFor("|", );', "thinkFor(text, secs)", "Denkblase mit Dauer", 0),
    ("animate", 'animate("|", "", );', "animate(costume1, costume2, secs)", "Kostüme animieren", 0),
    ("switchCostume", 'switchCostume("|");', "switchCostume(name)", "Kostüm wechseln", 0),
    ("nextCostume", "nextCostume();", "nextCostume()", "Nächstes Kostüm", 0),
    ("switchBackdrop", 'switchBackdrop("|");', "switchBackdrop(name)", "Hintergrund wechseln", 0),
    ("nextBackdrop", "nextBackdrop();", "nextBackdrop()", "Nächster Hintergrund", 0),
    ("setSize", "setSize(|);", "setSize(percent)", "Größe setzen", 0),
    ("changeSize", "changeSize(|);", "changeSize(delta)", "Größe ändern", 0),
    ("show", "show();", "show()", "Sprite anzeigen", 0),
    ("hide", "hide();", "hide()", "Sprite verstecken", 0),
    ("goToFront", "goToFront();", "goToFront()", "Ganz nach vorne", 0),
    ("goToBack", "goToBack();", "goToBack()", "Ganz nach hinten", 0),
    ("goForwardLayers", "goForwardLayers(|);", "goForwardLayers(n)", "Ebenen nach vorne", 0),
    ("goBackwardLayers", "goBackwardLayers(|);", "goBackwardLayers(n)", "Ebenen nach hinten", 0),
    ("setEffect", 'setEffect("|", );', "setEffect(name, value)", "Effekt setzen", 0),
    ("changeEffect", 'changeEffect("|", );', "changeEffect(name, value)", "Effekt ändern", 0),
    ("clearEffects", "clearEffects();", "clearEffects()", "Effekte löschen", 0),

    ("playSound", 'playSound("|");', "playSound(name)", "Sound abspielen", 0),
    ("playSoundUntilDone", 'playSoundUntilDone("|");', "playSoundUntilDone(name)", "Sound abspielen und warten", 0),
    ("stopAllSounds", "stopAllSounds();", "stopAllSounds()", "Sounds stoppen", 0),
    ("setVolume", "setVolume(|);", "setVolume(percent)", "Lautstärke setzen", 0),
    ("changeVolume", "changeVolume(|);", "changeVolume(delta)", "Lautstärke ändern", 0),
    ("broadcast", 'broadcast("|");', "broadcast(message)", "Nachricht senden", 0),
    ("broadcastAndWait", 'broadcastAndWait("|");', "broadcastAndWait(message)", "Nachricht senden und warten", 0),
    ("askAndWait", 'askAndWait("|");', "askAndWait(question)", "Frage stellen", 0),
    ("setDragMode", 'setDragMode("|");', "setDragMode(mode)", "Ziehmodus setzen", 0),
    ("resetTimer", "resetTimer();", "resetTimer()", "Timer zurücksetzen", 0),

    ("showVar", 'showVar("|");', "showVar(name)", "Variablenmonitor anzeigen", 0),
    ("hideVar", 'hideVar("|");', "hideVar(name)", "Variablenmonitor verstecken", 0),
    ("showList", 'showList("|");', "showList(name)", "Listenmonitor anzeigen", 0),
    ("hideList", 'hideList("|");', "hideList(name)", "Listenmonitor verstecken", 0),
    ("addCostume", 'addCostume("|");', "addCostume(name)", "Kostüm hinzufügen", 0),
    ("addBackdrop", 'addBackdrop("|");', "addBackdrop(name)", "Hintergrund hinzufügen", 0),
    ("addSound", 'addSound("|");', "addSound(name)", "Sound hinzufügen", 0),

    ("penDown", "penDown();", "penDown()", "Stift absenken", 0),
    ("penUp", "penUp();", "penUp()", "Stift anheben", 0),
    ("setPenColor", "setPenColor(|);", "setPenColor(color)", "Stiftfarbe setzen", 0),
    ("changePenColor", "changePenColor(|);", "changePenColor(delta)", "Stiftfarbe ändern", 0),
    ("setPenSize", "setPenSize(|);", "setPenSize(size)", "Stiftgröße setzen", 0),
    ("changePenSize", "changePenSize(|);", "changePenSize(delta)", "Stiftgröße ändern", 0),
    ("stampPen", "stampPen();", "stampPen()", "Abbild stempeln", 0),
    ("erasePen", "erasePen();", "erasePen()", "Stiftspuren löschen", 0),

    # Music extension (import "music";)
    ("playDrum", "playDrum(|, );", "playDrum(drum, beats)", "Schlagzeug spielen (1=Bass, 2=Snare, ...)", 0),
    ("restForBeats", "restForBeats(|);", "restForBeats(beats)", "Pause machen", 0),
    ("playNote", "playNote(|, );", "playNote(note, beats)", "Note spielen (60=Mittleres C)", 0),
    ("setInstrument", "setInstrument(|);", "setInstrument(num)", "Instrument setzen (1–21)", 0),
    ("setTempo", "setTempo(|);", "setTempo(bpm)", "Tempo setzen (Schläge pro Minute)", 0),
    ("changeTempo", "changeTempo(|);", "changeTempo(delta)", "Tempo ändern", 0),
    ("getTempo", "getTempo", "getTempo", "Aktuelles Tempo (Ausdruck)", 0),

    # Video Sensing extension (import "video";)
    ("videoOn", "videoOn();", "videoOn()", "Kamera einschalten", 0),
    ("videoOff", "videoOff();", "videoOff()", "Kamera ausschalten", 0),
    ("videoFlipped", "videoFlipped();", "videoFlipped()", "Kamera gespiegelt einschalten", 0),
    ("setVideoTransparency", "setVideoTransparency(|);", "setVideoTransparency(percent)", "Kamera-Transparenz setzen", 0),
    ("videoMotion", 'videoMotion("|")', 'videoMotion("this sprite")', "Videobewegung auf Objekt (Ausdruck)", 0),
    ("videoDirection", 'videoDirection("|")', 'videoDirection("this sprite")', "Videorichtung auf Objekt (Ausdruck)", 0),

    # Text2Speech extension (import "text2speech";)
    ("speak", 'speak("|");', 'speak("text")', "Text vorlesen", 0),
    ("setVoice", 'setVoice("|");', 'setVoice("Alto")', 'Stimme setzen: "Alto", "Tenor", "Squeak", "Giant", "Kitten"', 0),
    ("setLanguage", 'setLanguage("|");', 'setLanguage("de")', "Sprache setzen (z.B. \"de\", \"en\")", 0),

    # Translate extension (import "translate";)
    ("translate", 'translate(|, "de")', 'translate(text, "sprache")', "Text übersetzen (Ausdruck)", 0),
    ("viewerLanguage", "viewerLanguage", "viewerLanguage", "Sprache des Betrachters (Ausdruck)", 0),

    ("Math.random", "Math.random(|, )", "Math.random(a, b)", "Zufallszahl", 0),
    ("Math.round", "Math.round(|)", "Math.round(n)", "Runden", 0),
    ("Math.abs", "Math.abs(|)", "Math.abs(n)", "Betrag", 0),
    ("Math.floor", "Math.floor(|)", "Math.floor(n)", "Abrunden", 0),
    ("Math.ceil", "Math.ceil(|)", "Math.ceil(n)", "Aufrunden", 0),
    ("Math.sqrt", "Math.sqrt(|)", "Math.sqrt(n)", "Quadratwurzel", 0),
    ("Math.sin", "Math.sin(|)", "Math.sin(n)", "Sinus", 0),
    ("Math.cos", "Math.cos(|)", "Math.cos(n)", "Cosinus", 0),
    ("Math.tan", "Math.tan(|)", "Math.tan(n)", "Tangens", 0),
    ("Math.asin", "Math.asin(|)", "Math.asin(n)", "Arcussinus", 0),
    ("Math.acos", "Math.acos(|)", "Math.acos(n)", "Arcuscosinus", 0),
    ("Math.atan", "Math.atan(|)", "Math.atan(n)", "Arcustangens", 0),
    ("Math.ln", "Math.ln(|)", "Math.ln(n)", "Natürlicher Logarithmus", 0),
    ("Math.log", "Math.log(|)", "Math.log(n)", "Logarithmus Basis 10", 0),

    ("keyPressed", 'keyPressed("|")', "keyPressed(key)", "Taste gedrückt?", 0),
    ("touching", 'touching("|")', "touching(target)", "Berührt Objekt?", 0),
    ("touchingColor", "touchingColor(|)", "touchingColor(color)", "Berührt Farbe?", 0),
    ("distanceTo", 'distanceTo("|")', "distanceTo(target)", "Abstand zu Objekt", 0),
    (".add", '.add("|");', '.add("wert")', "Element zur Liste hinzufügen", 0),
    (".delete", ".delete(|);", ".delete(index)", "Listenelement löschen", 0),
    (".insert", '.insert(|, "");', ".insert(index, wert)", "Element einfügen", 0),
    (".replace", '.replace(|, "");', ".replace(index, wert)", "Element ersetzen", 0),
    (".length", ".length()", ".length()", "Länge von Text oder Liste", 0),
    (".contains", '.contains("|")', '.contains("wert")', "Enthält Wert?", 0),

    ("answer", "answer", "answer", "Letzte Antwort", 0),
    ("mouseX", "mouseX", "mouseX", "Maus-X-Position", 0),
    ("mouseY", "mouseY", "mouseY", "Maus-Y-Position", 0),
    ("mouseDown", "mouseDown", "mouseDown", "Maustaste gedrückt?", 0),
    ("timer", "timer", "timer", "Timerwert", 0),
    ("loudness", "loudness", "loudness", "Mikrofonlautstärke", 0),
    ("username", "username", "username", "Benutzername", 0),
    ("xPosition", "xPosition", "xPosition", "X-Position", 0),
    ("yPosition", "yPosition", "yPosition", "Y-Position", 0),
    ("direction", "direction", "direction", "Richtung", 0),
    ("currentYear", "currentYear", "currentYear", "Jahr", 0),
    ("currentMonth", "currentMonth", "currentMonth", "Monat", 0),
    ("currentDate", "currentDate", "currentDate", "Tag", 0),
    ("currentDayOfWeek", "currentDayOfWeek", "currentDayOfWeek", "Wochentag", 0),
    ("currentHour", "currentHour", "currentHour", "Stunde", 0),
    ("currentMinute", "currentMinute", "currentMinute", "Minute", 0),
    ("currentSecond", "currentSecond", "currentSecond", "Sekunde", 0),
    ("true", "true", "true", "Boolean wahr", 0),
    ("false", "false", "false", "Boolean falsch", 0),
]


HTML_TEMPLATE = r"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Scrape Editor</title>
<style>
:root {
  color-scheme:dark;
  --bg:#202124; --surface:#292a2d; --surface2:#333438; --text:#e8eaed;
  --muted:#aeb0b5; --border:#45464b; --accent:#4b91e2; --selection:#365d89;
  --popup:#303136; --keyword:#79b8ff; --string:#a5d6a7; --number:#d2a8ff;
  --comment:#8b949e; --operator:#ff9bce; --status:#292a2d;
}
:root[data-theme="light"] {
  color-scheme:light;
  --bg:#fff; --surface:#f3f3f3; --surface2:#e8e8e8; --text:#222;
  --muted:#65676a; --border:#c9cacf; --accent:#1670c5; --selection:#c9dfff;
  --popup:#fff; --keyword:#0550ae; --string:#116329; --number:#8250df;
  --comment:#6e7781; --operator:#a626a4; --status:#ececec;
}
* { box-sizing:border-box; }
html,body { height:100%; margin:0; color:var(--text); background:var(--bg);
  font:14px system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
body { display:grid; grid-template-rows:34px minmax(0,1fr) 25px; overflow:hidden; }
button { color:var(--text); font:inherit; }
#menubar { display:flex; align-items:stretch; gap:2px; padding:2px 6px;
  background:var(--surface); border-bottom:1px solid var(--border); }
.menu { position:relative; }
.menu>summary { cursor:pointer; list-style:none; padding:5px 10px; border-radius:4px; }
.menu>summary::-webkit-details-marker { display:none; }
.menu[open]>summary,.menu>summary:hover { background:var(--surface2); }
.menuitems { position:absolute; z-index:20; top:29px; left:0; min-width:220px;
  padding:4px; background:var(--popup); border:1px solid var(--border);
  border-radius:5px; box-shadow:0 6px 20px #0005; }
.menuitems button { display:block; width:100%; text-align:left; border:0;
  background:none; padding:7px 10px; border-radius:3px; cursor:pointer; }
.menuitems button:hover { background:var(--selection); }
kbd { border:1px solid var(--border); border-radius:3px; padding:1px 4px; font-size:11px; }
#layout { min-height:0; display:grid; grid-template-columns:235px minmax(0,1fr); }
#side { min-height:0; display:grid; grid-template-rows:auto 1fr;
  background:var(--surface); border-right:1px solid var(--border); }
#sidehead { padding:8px; border-bottom:1px solid var(--border); }
#crumb { color:var(--muted); font-size:12px; overflow-wrap:anywhere; margin-bottom:7px; }
.smallbutton { border:1px solid var(--border); border-radius:4px; background:var(--surface2);
  padding:4px 8px; cursor:pointer; }
.smallbutton:hover { border-color:var(--accent); }
#files { overflow:auto; padding:4px; }
.file { display:block; width:100%; border:0; border-radius:3px; padding:5px 7px;
  background:none; color:var(--text); text-align:left; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; cursor:pointer; }
.file:hover,.file.selected { background:var(--surface2); }
.file.dir { color:var(--accent); }
#main { min-width:0; min-height:0; display:grid; grid-template-rows:31px minmax(100px,1fr) 180px; }
#tabbar { display:flex; align-items:center; gap:8px; padding:0 10px;
  background:var(--surface); border-bottom:1px solid var(--border); }
#filename { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
#dirty { color:#e4ae49; }
.spacer { flex:1; }
#editorwrap { min-height:0; display:grid; grid-template-columns:48px minmax(0,1fr);
  position:relative; overflow:hidden; }
#lineNumbers { overflow:hidden; user-select:none; padding:10px 8px; text-align:right;
  color:var(--muted); background:var(--surface); white-space:pre;
  font:var(--editor-font,14px)/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }
#codeview,#editor { position:absolute; top:0; bottom:0; left:48px; right:0;
  margin:0; padding:10px; border:0; white-space:pre; overflow:auto;
  tab-size:4; font:var(--editor-font,14px)/1.55 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  letter-spacing:normal; }
#codeview { pointer-events:none; color:var(--text); background:var(--bg); }
#highlighted { margin:0; min-width:max-content; min-height:100%;
  white-space:pre; font:inherit; tab-size:4; }
#editor { resize:none; outline:none; color:transparent; caret-color:var(--text);
  background:transparent; }
#editor::selection { color:transparent; background:var(--selection); }
.token-keyword { color:var(--keyword); }
.token-string { color:var(--string); }
.token-number { color:var(--number); }
.token-comment { color:var(--comment); font-style:italic; }
.token-operator { color:var(--operator); }
#completion { display:none; position:absolute; z-index:10; width:min(570px,75vw);
  max-height:250px; overflow:auto; background:var(--popup); border:1px solid var(--border);
  border-radius:5px; box-shadow:0 5px 18px #0006; }
.suggestion { display:grid; grid-template-columns:190px 1fr; gap:10px;
  padding:5px 8px; cursor:pointer; }
.suggestion.active,.suggestion:hover { background:var(--selection); }
.suggestion-label { font-family:ui-monospace,monospace; font-weight:600; }
.suggestion-desc { color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
#outputpanel { min-height:0; display:grid; grid-template-rows:31px 1fr;
  border-top:1px solid var(--border); background:var(--surface); }
#outputhead { display:flex; align-items:center; gap:10px; padding:0 10px;
  border-bottom:1px solid var(--border); }
#output { margin:0; padding:8px 10px; overflow:auto; white-space:pre-wrap;
  overflow-wrap:anywhere; color:var(--text); background:var(--bg);
  font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }
#statusbar { display:flex; align-items:center; gap:15px; padding:2px 8px;
  color:var(--muted); background:var(--status); border-top:1px solid var(--border);
  font-size:12px; }
#status { overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
@media(max-width:700px) {
  #layout { grid-template-columns:140px minmax(0,1fr); }
  #main { grid-template-rows:31px minmax(100px,1fr) 145px; }
  .suggestion { grid-template-columns:1fr; gap:1px; }
  .suggestion-desc { display:none; }
}
</style>
</head>
<body>
<div id="menubar">
  <details class="menu"><summary>Datei</summary><div class="menuitems">
    <button data-action="new">Neu</button>
    <button data-action="open">Öffnen…</button>
    <button data-action="save">Speichern <kbd>Ctrl+S</kbd></button>
    <button data-action="saveas">Speichern unter…</button>
    <button data-action="quit">Beenden</button>
  </div></details>
  <details class="menu"><summary>Transpiler</summary><div class="menuitems">
    <button data-action="compile">Ausführen <kbd>Ctrl+R</kbd></button>
    <button data-action="watch">Watch-Modus</button>
    <button data-action="stopwatch">Watch beenden</button>
    <button data-action="compilefile">Eine Datei transpilieren…</button>
  </div></details>
  <details class="menu"><summary>Detranspiler</summary><div class="menuitems">
    <button data-action="detranspile">Eine .sb3-Datei öffnen…</button>
  </div></details>
  <details class="menu"><summary>Ansicht</summary><div class="menuitems">
    <button data-action="theme">Dark/Light Mode umschalten</button>
    <button data-action="fontminus">Schrift kleiner</button>
    <button data-action="fontplus">Schrift größer</button>
    <button data-action="autocomplete">Autocomplete an/aus</button>
  </div></details>
  <details class="menu"><summary>Einstellungen</summary><div class="menuitems">
    <button data-action="workspace">Workspace-Pfad anzeigen</button>
    <button data-action="shortcuts">Tastenkürzel</button>
  </div></details>
</div>

<div id="layout">
  <aside id="side">
    <div id="sidehead">
      <div id="crumb">/</div>
      <button class="smallbutton" id="up">↑ Übergeordnet</button>
      <button class="smallbutton" id="refresh">Aktualisieren</button>
    </div>
    <div id="files"></div>
  </aside>

  <main id="main">
    <div id="tabbar">
      <span id="filename">Keine Datei geöffnet</span>
      <span id="dirty"></span>
      <span class="spacer"></span><span>Scrape</span>
    </div>

    <div id="editorwrap">
      <div id="lineNumbers">1</div>
      <div id="codeview" aria-hidden="true"><pre id="highlighted"></pre></div>
      <textarea id="editor" wrap="off" spellcheck="false"
        autocapitalize="off" autocomplete="off" autocorrect="off"></textarea>
      <div id="completion" role="listbox"></div>
    </div>

    <section id="outputpanel">
      <div id="outputhead">
        <strong id="outputtitle">Transpiler-Ausgabe</strong>
        <span class="spacer"></span>
        <button class="smallbutton" id="clearoutput">Leeren</button>
      </div>
      <pre id="output">Die Transpiler-Ausgabe erscheint hier.</pre>
    </section>
  </main>
</div>

<div id="statusbar">
  <span id="status">Bereit</span><span class="spacer"></span>
  <span id="position">Zeile 1, Spalte 1</span>
</div>

<script>
"use strict";
const TOKEN = __TOKEN__;
const ENTRIES = __ENTRIES__;
const $ = id => document.getElementById(id);
const editor = $("editor");

let currentPath = null;
let currentDir = "";
let dirty = false;
let matches = [];
let selectedMatch = 0;
let tokenStart = -1;
let autocompleteEnabled = true;
let theme = "dark";
let fontSize = 14;
let watchPollTimer = null;

/* Show otherwise-hidden initialization errors in the page itself. */
window.addEventListener("error", event => {
  const message = event.message || "Unbekannter JavaScript-Fehler";
  $("status").textContent = "JavaScript-Fehler: " + message;
  $("outputtitle").textContent = "Editor-Fehler";
  $("output").textContent = message + (event.filename ? "\n" + event.filename + ":" + event.lineno : "");
});
window.addEventListener("unhandledrejection", event => {
  const message = event.reason && event.reason.message
    ? event.reason.message
    : String(event.reason || "Unbehandelte Promise-Ablehnung");
  $("status").textContent = "Fehler: " + message;
  $("outputtitle").textContent = "Editor-Fehler";
  $("output").textContent = message;
});

function setStatus(text) {
  $("status").textContent = text;
}

async function api(url, options = {}) {
  const headers = Object.assign({"X-Editor-Token": TOKEN}, options.headers || {});
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(url, Object.assign({}, options, {headers}));
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function setTheme(value) {
  theme = value;
  document.documentElement.dataset.theme = value;
}

function setDirty(value) {
  dirty = value;
  $("dirty").textContent = value ? "●" : "";
  $("dirty").title = value ? "Ungespeicherte Änderungen" : "";
}

function updatePosition() {
  const before = editor.value.slice(0, editor.selectionStart).split("\n");
  $("position").textContent =
    `Zeile ${before.length}, Spalte ${before[before.length - 1].length + 1}`;
  $("lineNumbers").textContent = Array.from(
    {length: Math.max(1, editor.value.split("\n").length)},
    (_, i) => i + 1
  ).join("\n");
  $("lineNumbers").scrollTop = editor.scrollTop;
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, ch => ({
    "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
  })[ch]);
}

const KEYWORDS = new Set((
  "public private shown hidden Sprite Stage import var void define " +
  "onFlagClicked onKeyPressed onSpriteClicked onBackdropChanged " +
  "onBroadcastReceived onCloneCreated repeat forever if else elseif " +
  "repeatUntil wait waitUntil stop createClone deleteClone move turnLeft " +
  "turnRight goTo goToSprite glide glideToSprite pointDir pointTowards " +
  "setX setY changeX changeY bounceOnEdge setRotationStyle say sayFor " +
  "think thinkFor animate switchCostume nextCostume switchBackdrop " +
  "nextBackdrop setSize changeSize show hide goToFront goToBack " +
  "goForwardLayers goBackwardLayers setEffect changeEffect clearEffects " +
  "playSound playSoundUntilDone stopAllSounds setVolume changeVolume " +
  "askAndWait setDragMode resetTimer penDown penUp setPenColor " +
  "changePenColor setPenSize changePenSize stampPen erasePen broadcast " +
  "broadcastAndWait addCostume addBackdrop addSound " +
  "playDrum restForBeats playNote setInstrument setTempo changeTempo getTempo " +
  "videoOn videoOff videoFlipped setVideoTransparency videoMotion videoDirection " +
  "speak setVoice setLanguage translate viewerLanguage true false"
).split(/\s+/));

function makeHighlightedHtml(source) {
  const pattern = /(\/\/[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b\d+(?:\.\d+)?\b|\b[A-Za-z_][A-Za-z0-9_]*\b|==|!=|<=|>=|&&|\|\||[+\-*\/%<>=!])/g;
  let result = "";
  let last = 0;
  let match;

  while ((match = pattern.exec(source)) !== null) {
    result += escapeHtml(source.slice(last, match.index));
    const token = match[0];
    let cls = "";

    if (token.startsWith("//")) cls = "token-comment";
    else if (token.startsWith('"') || token.startsWith("'")) cls = "token-string";
    else if (/^\d/.test(token)) cls = "token-number";
    else if (KEYWORDS.has(token)) cls = "token-keyword";
    else if (/^(==|!=|<=|>=|&&|\|\||[+\-*\/%<>=!])$/.test(token)) cls = "token-operator";

    result += cls
      ? `<span class="${cls}">${escapeHtml(token)}</span>`
      : escapeHtml(token);
    last = pattern.lastIndex;
  }

  result += escapeHtml(source.slice(last));
  if (source.endsWith("\n")) result += " ";
  return result;
}

function updateHighlight() {
  $("highlighted").innerHTML = makeHighlightedHtml(editor.value);
  $("codeview").scrollTop = editor.scrollTop;
  $("codeview").scrollLeft = editor.scrollLeft;
  $("lineNumbers").scrollTop = editor.scrollTop;
  updatePosition();
}

function setText(text) {
  editor.value = text;
  updateHighlight();
  setDirty(false);
}

async function listFiles(path = currentDir) {
  setStatus("Lade Dateiliste …");

  const data = await api("/api/list?path=" + encodeURIComponent(path));
  if (!data || !Array.isArray(data.items)) {
    throw new Error("Dateilisten-API lieferte keine gültige Liste.");
  }

  currentDir = data.path || "";
  $("crumb").textContent = "/" + currentDir;

  const container = $("files");
  container.replaceChildren();

  for (const item of data.items) {
    const button = document.createElement("button");
    button.className = "file" + (item.is_dir ? " dir" : "");
    button.textContent = (item.is_dir ? "▸ " : "  ") + item.name;
    button.title = item.path;
    button.addEventListener("click", async () => {
      try {
        if (item.is_dir) await listFiles(item.path);
        else await openFile(item.path);
      } catch (error) {
        setStatus("Datei: " + error.message);
      }
    });
    container.appendChild(button);
  }

  setStatus(`${data.items.length} Einträge in /${currentDir}`);
}

async function openFile(path) {
  if (dirty && !confirm("Ungespeicherte Änderungen verwerfen?")) return;

  const data = await api("/api/read?path=" + encodeURIComponent(path));
  currentPath = data.path;
  $("filename").textContent = "/" + currentPath;
  setText(data.content);
  editor.focus();
  await listFiles(currentDir);
  setStatus("Geöffnet: /" + currentPath);
}

async function saveFile(saveAs = false) {
  let path = currentPath;

  if (saveAs || !path) {
    path = prompt("Workspace-relativer Dateipfad:", path || "");
    if (path === null || !path.trim()) return false;
    path = path.trim();
  }

  const data = await api("/api/save", {
    method:"POST",
    body:JSON.stringify({path, content:editor.value})
  });

  currentPath = data.path;
  $("filename").textContent = "/" + currentPath;
  setDirty(false);
  await listFiles(currentDir);
  setStatus("Gespeichert: /" + currentPath);
  return true;
}

function showOutput(title, text, failed = false) {
  $("outputtitle").textContent = title;
  $("output").textContent = text || (failed ? "Vorgang fehlgeschlagen." : "Fertig.");
  $("output").style.color = failed ? "var(--operator)" : "var(--text)";
}

async function compilePath(path) {
  showOutput("Transpiler-Ausgabe", "Kompiliere …");
  setStatus("Transpiler läuft …");

  const data = await api("/api/compile", {
    method:"POST",
    body:JSON.stringify({path})
  });

  showOutput(
    data.success ? "Transpiler-Ausgabe" : "Transpiler-Fehler",
    data.log,
    !data.success
  );
  setStatus(data.success ? `Ausgabe: ${data.output}` : "Kompilierung fehlgeschlagen.");
  if (data.output) await listFiles(currentDir);
}

async function compileCurrent() {
  if (!currentPath || !currentPath.toLowerCase().endsWith(".scrape")) {
    setStatus("Bitte zuerst eine .scrape-Datei öffnen oder speichern.");
    return;
  }
  if (dirty && !await saveFile()) return;
  await compilePath(currentPath);
}

function hideCompletion() {
  $("completion").style.display = "none";
  matches = [];
  tokenStart = -1;
}

function renderCompletion() {
  const popup = $("completion");
  popup.replaceChildren();

  matches.forEach((entry, index) => {
    const row = document.createElement("div");
    row.className = "suggestion" + (index === selectedMatch ? " active" : "");

    const label = document.createElement("span");
    label.className = "suggestion-label";
    label.textContent = entry[2];

    const description = document.createElement("span");
    description.className = "suggestion-desc";
    description.textContent = entry[3];

    row.append(label, description);
    row.addEventListener("mousedown", event => {
      event.preventDefault();
      selectedMatch = index;
      acceptCompletion();
    });
    popup.appendChild(row);
  });

  popup.style.display = matches.length ? "block" : "none";
}

/* Misst den Cursor statt seine Position anhand einer festen Zeichenbreite zu schätzen. */
function getCaretRect() {
  const rect = editor.getBoundingClientRect();
  const style = getComputedStyle(editor);
  const mirror = document.createElement("div");

  Object.assign(mirror.style, {
    position: "fixed",
    left: rect.left + "px",
    top: rect.top + "px",
    visibility: "hidden",
    pointerEvents: "none",
    boxSizing: "border-box",
    width: editor.clientWidth + "px",
    padding: style.padding,
    border: "0",
    margin: "0",
    font: style.font,
    letterSpacing: style.letterSpacing,
    lineHeight: style.lineHeight,
    tabSize: style.tabSize,
    whiteSpace: "pre",
    overflow: "visible",
    direction: style.direction
  });

  mirror.textContent = editor.value.slice(0, editor.selectionStart);

  const marker = document.createElement("span");
  marker.textContent = "\u200b";
  marker.style.display = "inline-block";
  marker.style.width = "0";
  marker.style.height = style.lineHeight;
  mirror.appendChild(marker);
  document.body.appendChild(mirror);

  const markerRect = marker.getBoundingClientRect();
  mirror.remove();

  const lineHeight = parseFloat(style.lineHeight) || 22;
  return {
    left: markerRect.left - editor.scrollLeft,
    top: markerRect.top - editor.scrollTop,
    bottom: markerRect.top - editor.scrollTop + lineHeight
  };
}

function updateCompletion() {
  if (!autocompleteEnabled) {
    hideCompletion();
    return;
  }

  const caret = editor.selectionStart;
  const match = /[A-Za-z0-9_.]+$/.exec(editor.value.slice(0, caret));
  if (!match) {
    hideCompletion();
    return;
  }

  const token = match[0].toLowerCase();
  tokenStart = caret - match[0].length;

  const prefix = [];
  const partial = [];
  for (const entry of ENTRIES) {
    const trigger = entry[0].toLowerCase();
    if (trigger.startsWith(token)) prefix.push(entry);
    else if (trigger.includes(token)) partial.push(entry);
  }

  matches = prefix.concat(partial).slice(0, 10);
  if (!matches.length) {
    hideCompletion();
    return;
  }

  selectedMatch = Math.min(selectedMatch, matches.length - 1);
  renderCompletion();

  const popup = $("completion");
  const wrap = $("editorwrap");
  const wrapRect = wrap.getBoundingClientRect();
  const caretRect = getCaretRect();

  const popupWidth = Math.min(570, Math.max(220, wrap.clientWidth - 10));
  popup.style.width = popupWidth + "px";

  const spaceBelow = wrapRect.bottom - caretRect.bottom - 6;
  const spaceAbove = caretRect.top - wrapRect.top - 6;
  const placeBelow = spaceBelow >= 130 || spaceBelow >= spaceAbove;
  const availableHeight = Math.max(48, placeBelow ? spaceBelow : spaceAbove);

  popup.style.maxHeight = Math.min(250, availableHeight) + "px";
  const popupHeight = Math.min(popup.scrollHeight, availableHeight, 250);

  const rawTop = placeBelow
    ? caretRect.bottom - wrapRect.top + 3
    : caretRect.top - wrapRect.top - popupHeight - 3;
  const maxTop = Math.max(4, wrap.clientHeight - popupHeight - 4);
  popup.style.top = Math.max(4, Math.min(rawTop, maxTop)) + "px";

  const rawLeft = caretRect.left - wrapRect.left;
  const maxLeft = Math.max(4, wrap.clientWidth - popupWidth - 4);
  popup.style.left = Math.max(4, Math.min(rawLeft, maxLeft)) + "px";
}

function acceptCompletion() {
  if (!matches.length || tokenStart < 0) return false;

  const entry = matches[selectedMatch];
  const raw = entry[1];
  const marker = raw.indexOf("|");
  const snippet = marker >= 0 ? raw.replace("|", "") : raw;
  const start = tokenStart;
  const end = editor.selectionStart;

  const lineStart = editor.value.lastIndexOf("\n", start - 1) + 1;
  const indent = /^[\t ]*/.exec(editor.value.slice(lineStart, start))[0]
    .replace(/ {4}/g, "\t");

  const formattedParts = snippet.split("\n").map((part, index) => {
    if (index === 0) return part;
    const spaces = /^ */.exec(part)[0].length;
    return indent + "\t".repeat(Math.floor(spaces / 4)) + part.slice(spaces);
  });
  const formatted = formattedParts.join("\n");

  let cursor;
  if (marker >= 0) {
    const beforeMarker = raw.slice(0, marker);
    const beforeParts = beforeMarker.split("\n");
    cursor = beforeParts[0].length;
    for (let i = 1; i < beforeParts.length; i++) {
      const part = beforeParts[i];
      const spaces = /^ */.exec(part)[0].length;
      cursor += 1 + indent.length + Math.floor(spaces / 4) + part.length - spaces;
    }
  } else {
    cursor = Math.max(0, formatted.length - (entry[4] || 0));
  }

  editor.setRangeText(formatted, start, end, "end");
  const position = start + Math.min(cursor, formatted.length);
  editor.setSelectionRange(position, position);

  setDirty(true);
  updateHighlight();
  hideCompletion();
  editor.focus();
  updateCompletion();
  return true;
}

function closeMenus() {
  document.querySelectorAll(".menu[open]").forEach(menu => menu.open = false);
}

async function pollWatchOutput() {
  try {
    const data = await api("/api/watch/log");
    if (data.log) showOutput("Transpiler-Watch-Ausgabe", data.log);

    if (!data.running) {
      clearInterval(watchPollTimer);
      watchPollTimer = null;
      setStatus("Transpiler-Watch-Prozess beendet.");
    }
  } catch (error) {
    showOutput("Watch-Fehler", error.message, true);
    clearInterval(watchPollTimer);
    watchPollTimer = null;
  }
}

async function action(name) {
  closeMenus();

  try {
    if (name === "new") {
      if (dirty && !confirm("Ungespeicherte Änderungen verwerfen?")) return;
      currentPath = null;
      $("filename").textContent = "Neue Datei";
      setText("");
      setDirty(true);
      editor.focus();
    } else if (name === "open") {
      if (dirty && !confirm("Ungespeicherte Änderungen verwerfen?")) return;
      const path = prompt("Workspace-relativer Pfad:");
      if (path) await openFile(path);
    } else if (name === "save") {
      await saveFile();
    } else if (name === "saveas") {
      await saveFile(true);
    } else if (name === "compile") {
      await compileCurrent();
    } else if (name === "compilefile") {
      const path = prompt("Workspace-relativer .scrape-Pfad:");
      if (path) await compilePath(path);
    } else if (name === "watch") {
      if (!currentPath || !currentPath.endsWith(".scrape")) {
        setStatus("Zuerst eine .scrape-Datei öffnen oder speichern.");
        return;
      }
      if (dirty && !await saveFile()) return;

      const data = await api("/api/watch/start", {
        method:"POST",
        body:JSON.stringify({path:currentPath})
      });
      showOutput("Transpiler-Watch-Ausgabe", data.message);
      setStatus(data.message);

      if (watchPollTimer) clearInterval(watchPollTimer);
      watchPollTimer = setInterval(pollWatchOutput, 1000);
      pollWatchOutput();
    } else if (name === "stopwatch") {
      const data = await api("/api/watch/stop", {
        method:"POST",
        body:JSON.stringify({})
      });
      showOutput("Transpiler-Watch-Ausgabe", data.message);
      setStatus(data.message);
    } else if (name === "detranspile") {
      const path = prompt("Workspace-relativer .sb3-Pfad:");
      if (!path) return;

      showOutput("Detranspiler-Ausgabe", "Dekomprimiere …");
      const data = await api("/api/detranspile", {
        method:"POST",
        body:JSON.stringify({path})
      });
      showOutput("Detranspiler-Ausgabe", data.log);
      await openFile(data.path);
    } else if (name === "theme") {
      setTheme(theme === "dark" ? "light" : "dark");
    } else if (name === "fontplus" || name === "fontminus") {
      fontSize = Math.max(10, Math.min(28, fontSize + (name === "fontplus" ? 1 : -1)));
      document.documentElement.style.setProperty("--editor-font", fontSize + "px");
      updateHighlight();
      updateCompletion();
    } else if (name === "autocomplete") {
      autocompleteEnabled = !autocompleteEnabled;
      if (autocompleteEnabled) updateCompletion();
      else hideCompletion();
      setStatus("Autocomplete " + (autocompleteEnabled ? "aktiviert." : "deaktiviert."));
    } else if (name === "workspace") {
      const data = await api("/api/info");
      alert("Workspace: " + data.root);
    } else if (name === "shortcuts") {
      alert(
        "Ctrl+S: Speichern\n" +
        "Ctrl+O: Öffnen\n" +
        "Ctrl+R oder Ctrl+Enter: Kompilieren\n" +
        "F1: Menü\n" +
        "Tab: Vorschlag übernehmen, sonst echtes Tab-Zeichen\n" +
        "Pfeile: Cursor bewegen bzw. Vorschlag auswählen"
      );
    } else if (name === "quit") {
      if (!dirty || confirm("Seite verlassen und Änderungen verwerfen?")) window.close();
    }
  } catch (error) {
    setStatus(error.message);
    showOutput("Fehler", error.message, true);
  }
}

document.addEventListener("click", event => {
  const button = event.target.closest("[data-action]");
  if (button) action(button.dataset.action);
});

$("refresh").addEventListener("click", () => {
  listFiles().catch(error => {
    setStatus("Dateiliste: " + error.message);
    showOutput("Dateilisten-Fehler", error.stack || error.message, true);
  });
});

$("up").addEventListener("click", () => {
  const parts = currentDir.split("/").filter(Boolean);
  parts.pop();
  listFiles(parts.join("/")).catch(error => {
    setStatus("Dateiliste: " + error.message);
    showOutput("Dateilisten-Fehler", error.stack || error.message, true);
  });
});

$("clearoutput").addEventListener("click", () => showOutput("Transpiler-Ausgabe", ""));

editor.addEventListener("input", () => {
  setDirty(true);
  updateHighlight();
  updateCompletion();
});
editor.addEventListener("click", () => {
  updatePosition();
  updateCompletion();
});
editor.addEventListener("keyup", event => {
  updatePosition();
  if (!["ArrowUp", "ArrowDown"].includes(event.key)) updateCompletion();
});
editor.addEventListener("scroll", () => {
  $("codeview").scrollTop = editor.scrollTop;
  $("codeview").scrollLeft = editor.scrollLeft;
  $("lineNumbers").scrollTop = editor.scrollTop;
  updateCompletion();
});
window.addEventListener("resize", updateCompletion);

editor.addEventListener("keydown", event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    action("save");
    return;
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "o") {
    event.preventDefault();
    action("open");
    return;
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "r") {
    event.preventDefault();
    action("compile");
    return;
  }
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    action("compile");
    return;
  }
  if (event.key === "F1") {
    event.preventDefault();
    const first = document.querySelector(".menu");
    first.open = !first.open;
    return;
  }

  if ($("completion").style.display === "block" && matches.length) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const direction = event.key === "ArrowDown" ? 1 : -1;
      selectedMatch = (selectedMatch + direction + matches.length) % matches.length;
      renderCompletion();
      return;
    }
    if (event.key === "Tab") {
      event.preventDefault();
      acceptCompletion();
      return;
    }
  }

  const pairs = {"(":")", "[":"]", "{":"}", '"':'"', "'":"'"};
  const start = editor.selectionStart;
  const end = editor.selectionEnd;
  const value = editor.value;

  // Enter erzeugt Einrückungen mit echten Tabs.
  if (event.key === "Enter" && start === end) {
    event.preventDefault();

    const lineStart = value.lastIndexOf("\n", start - 1) + 1;
    const before = value.slice(lineStart, start);
    const leading = (/^[\t ]*/.exec(before) || [""])[0];
    const indentTabs = leading.includes("\t")
      ? leading.replace(/ /g, "")
      : "\t".repeat(Math.floor(leading.length / 4));
    const innerIndent = indentTabs + (before.trimEnd().endsWith("{") ? "\t" : "");
    const after = value.slice(start);

    if (before.trimEnd().endsWith("{") && /^\s*}/.test(after)) {
      const insertion = "\n" + innerIndent + "\n" + indentTabs;
      editor.setRangeText(insertion, start, end, "end");
      const cursor = start + 1 + innerIndent.length;
      editor.setSelectionRange(cursor, cursor);
    } else {
      editor.setRangeText("\n" + innerIndent, start, end, "end");
    }

    setDirty(true);
    updateHighlight();
    updateCompletion();
    return;
  }

  // Klammern und Anführungszeichen paarweise ergänzen.
  if (pairs[event.key] && start === end) {
    event.preventDefault();
    editor.setRangeText(event.key + pairs[event.key], start, end, "end");
    editor.setSelectionRange(start + 1, start + 1);
    setDirty(true);
    updateHighlight();
    updateCompletion();
    return;
  }

  // Vorhandenes schließendes Zeichen überspringen.
  if ([")", "]", "}", '"', "'"].includes(event.key) &&
      start === end && value[start] === event.key) {
    event.preventDefault();
    editor.setSelectionRange(start + 1, start + 1);
    return;
  }

  // Tab übernimmt einen Vorschlag; sonst wird ein echtes Tab eingefügt.
  if (event.key === "Tab") {
    event.preventDefault();
    editor.setRangeText("\t", start, end, "end");
    setDirty(true);
    updateHighlight();
    updateCompletion();
  }
});

document.addEventListener("keydown", event => {
  if (event.key === "Escape") {
    document.querySelectorAll(".menu[open]").forEach(menu => menu.open = false);
  }
});

window.addEventListener("beforeunload", event => {
  if (dirty) {
    event.preventDefault();
    event.returnValue = "";
  }
});

function reportInitialListError(error) {
  const text = error && error.stack ? error.stack : String(error);
  setStatus("Dateiliste konnte nicht geladen werden: " + String(error.message || error));
  showOutput("Dateilisten-Fehler", text, true);
}

updateHighlight();
listFiles("").catch(reportInitialListError);
editor.focus();
</script>
"""


class Workspace:
    def __init__(self, root: Path, transpiler: Path, detranspiler: Path):
        self.root = root.resolve()
        self.transpiler = transpiler.resolve()
        self.detranspiler = detranspiler.resolve()
        self.watch_process = None
        self.watch_output = ""
        self.watch_lock = threading.Lock()

    def resolve(self, relative: str, must_exist=False) -> Path:
        if not isinstance(relative, str):
            raise ValueError("Ein relativer Workspace-Pfad ist erforderlich.")

        relative = relative.replace("\\", "/")
        if relative.startswith("/") or any(part == ".." for part in relative.split("/")):
            raise ValueError("Absolute Pfade und '..' sind nicht erlaubt.")

        path = self.root if relative in ("", ".") else (self.root / relative).resolve(strict=must_exist)

        try:
            path.relative_to(self.root)
        except ValueError:
            raise ValueError("Der Pfad liegt außerhalb des Workspace.") from None
        return path

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def list_dir(self, relative: str):
        folder = self.root if not relative else self.resolve(relative, must_exist=True)
        if not folder.is_dir():
            raise ValueError("Der Pfad ist kein Ordner.")

        items = []
        for child in folder.iterdir():
            try:
                resolved = child.resolve()
                resolved.relative_to(self.root)
            except (OSError, ValueError):
                continue

            if resolved.is_dir():
                is_dir, size = True, 0
            elif resolved.is_file():
                is_dir, size = False, resolved.stat().st_size
            else:
                continue

            items.append({
                "name": child.name,
                "path": self.relative(resolved),
                "is_dir": is_dir,
                "size": size,
            })

        items.sort(key=lambda item: (not item["is_dir"], item["name"].casefold()))
        return items[:2000]

    def read_file(self, relative: str):
        path = self.resolve(relative, must_exist=True)
        if not path.is_file():
            raise ValueError("Das ist keine reguläre Datei.")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("Datei überschreitet das 2-MB-Limit.")
        return path, path.read_text(encoding="utf-8")

    def save_file(self, relative: str, content: str):
        if not isinstance(content, str):
            raise ValueError("Dateiinhalt muss Text sein.")

        data = content.encode("utf-8")
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("Datei überschreitet das 2-MB-Limit.")

        path = self.resolve(relative)
        parent = path.parent.resolve(strict=True)

        try:
            parent.relative_to(self.root)
        except ValueError:
            raise ValueError("Zielordner liegt außerhalb des Workspace.") from None

        target = parent / path.name
        if target.exists() and not target.is_file():
            raise ValueError("Kann keine Datei über einen Ordner schreiben.")

        fd, temp_name = tempfile.mkstemp(prefix=".scrape-editor-", dir=str(parent))
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, target)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

        return self.relative(target)

    def compile(self, relative: str):
        source = self.resolve(relative, must_exist=True)
        if not source.is_file() or source.suffix.lower() != ".scrape":
            raise ValueError("Kompilierung benötigt eine vorhandene .scrape-Datei.")
        if not self.transpiler.is_file():
            raise ValueError(f"Transpiler nicht gefunden: {self.transpiler}")

        output = source.with_suffix(".sb3")

        try:
            result = subprocess.run(
                [sys.executable, str(self.transpiler), str(source), "--out", str(output)],
                cwd=str(source.parent),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=PROCESS_TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            return {
                "success": False,
                "output": self.relative(output) if output.exists() else "",
                "log": f"Kompilierung nach {PROCESS_TIMEOUT} Sekunden abgebrochen.\n{stdout}{stderr}",
            }

        log = ((result.stdout or "") + (result.stderr or "")).strip()
        success = result.returncode == 0 and output.is_file()

        if not log:
            log = "Kompilierung erfolgreich." if success else "Transpiler hat keine .sb3-Datei erzeugt."

        return {
            "success": success,
            "output": self.relative(output) if output.exists() else "",
            "log": log,
        }

    def start_watch(self, relative: str):
        """Startet direkt den Transpiler mit --watch; die Ausgabe wird live gesammelt."""
        source = self.resolve(relative, must_exist=True)
        if not source.is_file() or source.suffix.lower() != ".scrape":
            raise ValueError("Watch-Modus benötigt eine .scrape-Datei.")
        if not self.transpiler.is_file():
            raise ValueError(f"Transpiler nicht gefunden: {self.transpiler}")

        with self.watch_lock:
            if self.watch_process is not None and self.watch_process.poll() is None:
                raise ValueError("Es läuft bereits ein Watch-Prozess.")

            self.watch_output = ""
            output = source.with_suffix(".sb3")

            process = subprocess.Popen(
                [
                    sys.executable,
                    "-u",
                    str(self.transpiler),
                    str(source),
                    "--out",
                    str(output),
                    "--watch",
                ],
                cwd=str(source.parent),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            self.watch_process = process

        def collect_output():
            try:
                if process.stdout is not None:
                    for line in process.stdout:
                        with self.watch_lock:
                            self.watch_output = (self.watch_output + line)[-MAX_WATCH_OUTPUT:]
            finally:
                if process.stdout is not None:
                    process.stdout.close()

        threading.Thread(target=collect_output, daemon=True).start()
        return f"Transpiler-Watch-Modus gestartet für {self.relative(source)}."

    def watch_log(self):
        with self.watch_lock:
            process = self.watch_process
            running = process is not None and process.poll() is None
            return {"running": running, "log": self.watch_output}

    def stop_watch(self):
        with self.watch_lock:
            process = self.watch_process
            if process is None or process.poll() is not None:
                self.watch_process = None
                return "Kein Watch-Prozess läuft."
            process.terminate()

        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

        with self.watch_lock:
            self.watch_process = None
        return "Transpiler-Watch-Prozess beendet."

    def detranspile(self, relative: str):
        source = self.resolve(relative, must_exist=True)
        if not source.is_file() or source.suffix.lower() != ".sb3":
            raise ValueError("Bitte eine .sb3-Datei angeben.")
        if not self.detranspiler.is_file():
            raise ValueError(f"Detranspiler nicht gefunden: {self.detranspiler}")

        output = source.with_suffix(".scrape")
        result = subprocess.run(
            [sys.executable, str(self.detranspiler), str(source), "--output", str(output)],
            cwd=str(source.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PROCESS_TIMEOUT,
        )
        log = ((result.stdout or "") + (result.stderr or "")).strip()

        if result.returncode or not output.is_file():
            raise RuntimeError(log or "Detranspilieren fehlgeschlagen.")

        return self.relative(output), log or "Detranspilieren erfolgreich."


def normalize_ip(value):
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return address.ipv4_mapped
    return address


def make_handler(workspace, token, allowed_ips):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ScrapeWebEditor/3.2"

        def log_message(self, fmt, *args):
            print("[scrape-editor]", self.address_string(), fmt % args)

        def client_ip(self):
            try:
                return normalize_ip(self.client_address[0])
            except ValueError:
                return None

        def access_allowed(self):
            address = self.client_ip()
            return address is not None and address in allowed_ips

        def authorized(self):
            return hmac.compare_digest(
                self.headers.get("X-Editor-Token", ""),
                token,
            )

        def same_origin(self):
            origin = self.headers.get("Origin", "")
            host = self.headers.get("Host", "")
            return bool(origin) and urlsplit(origin).netloc.lower() == host.lower()

        def send_json(self, status, value):
            payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def error(self, status, message):
            self.send_json(status, {"error": str(message)})

        def read_body(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise ValueError("Ungültige Content-Length.") from None

            if length <= 0 or length > MAX_BODY_BYTES:
                raise ValueError("Request fehlt oder ist zu groß.")

            raw = self.rfile.read(length)
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ValueError("Request muss gültiges UTF-8-JSON enthalten.") from None

            if not isinstance(value, dict):
                raise ValueError("JSON muss ein Objekt sein.")
            return value

        def do_GET(self):
            if not self.access_allowed():
                return self.error(403, "Diese Client-IP ist nicht freigegeben.")

            parsed = urlsplit(self.path)

            if parsed.path == "/":
                page = HTML_TEMPLATE.replace(
                    "__TOKEN__", json.dumps(token)
                ).replace(
                    "__ENTRIES__", json.dumps(AC_ENTRIES, ensure_ascii=False)
                ).encode("utf-8")

                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(page)
                return

            if not parsed.path.startswith("/api/"):
                return self.error(404, "Nicht gefunden.")
            if not self.authorized():
                return self.error(403, "Nicht autorisiert.")

            params = parse_qs(parsed.query, keep_blank_values=True)
            relative = params.get("path", [""])[0]

            try:
                if parsed.path == "/api/list":
                    return self.send_json(200, {
                        "path": relative.strip("/"),
                        "items": workspace.list_dir(relative),
                    })

                if parsed.path == "/api/read":
                    path, content = workspace.read_file(relative)
                    return self.send_json(200, {
                        "path": workspace.relative(path),
                        "content": content,
                    })

                if parsed.path == "/api/info":
                    return self.send_json(200, {"root": str(workspace.root)})

                if parsed.path == "/api/watch/log":
                    return self.send_json(200, workspace.watch_log())

                return self.error(404, "Unbekannter API-Endpunkt.")
            except (OSError, UnicodeError, ValueError) as exc:
                return self.error(400, exc)

        def do_POST(self):
            if not self.access_allowed():
                return self.error(403, "Diese Client-IP ist nicht freigegeben.")
            if not self.authorized():
                return self.error(403, "Nicht autorisiert.")
            if not self.same_origin():
                return self.error(403, "Ungültige Origin.")

            try:
                data = self.read_body()
                path = data.get("path", "")

                if self.path == "/api/save":
                    saved = workspace.save_file(path, data.get("content", ""))
                    return self.send_json(200, {"path": saved})

                if self.path == "/api/compile":
                    return self.send_json(200, workspace.compile(path))

                if self.path == "/api/watch/start":
                    return self.send_json(200, {"message": workspace.start_watch(path)})

                if self.path == "/api/watch/stop":
                    return self.send_json(200, {"message": workspace.stop_watch()})

                if self.path == "/api/detranspile":
                    output, log = workspace.detranspile(path)
                    return self.send_json(200, {"path": output, "log": log})

                return self.error(404, "Unbekannter API-Endpunkt.")
            except subprocess.TimeoutExpired:
                return self.error(422, "Vorgang hat das Zeitlimit überschritten.")
            except RuntimeError as exc:
                return self.error(422, exc)
            except (OSError, ValueError, TypeError) as exc:
                return self.error(400, exc)

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Scrape-Dateien im Browser bearbeiten.")
    parser.add_argument("--root", default=".", help="Bearbeitbarer Workspace-Ordner.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind-Adresse (Standard: 0.0.0.0).")
    parser.add_argument("--port", type=int, default=8765, help="HTTP-Port.")
    parser.add_argument(
        "--ip", action="append", default=[], metavar="IP",
        help="Zusätzliche exakt erlaubte Client-IP; mehrfach verwendbar.",
    )
    parser.add_argument(
        "--transpiler", default=str(SCRIPT_DIR / "Transpiler.py"),
        help="Pfad zu Transpiler.py.",
    )
    parser.add_argument(
        "--detranspiler", default=str(SCRIPT_DIR / "Detranspiler.py"),
        help="Pfad zu Detranspiler.py.",
    )
    parser.add_argument("--no-browser", action="store_true", help="Browser nicht automatisch öffnen.")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        parser.error(f"Workspace-Ordner existiert nicht: {root}")
    if not 1 <= args.port <= 65535:
        parser.error("Port muss zwischen 1 und 65535 liegen.")

    try:
        # Loopback ist immer erlaubt; zusätzliche Clients müssen explizit mit --ip freigegeben werden.
        allowed_ips = {normalize_ip("127.0.0.1"), normalize_ip("::1")}
        for value in args.ip:
            allowed_ips.add(normalize_ip(value))
    except ValueError as exc:
        parser.error(f"Ungültige IP-Adresse für --ip: {exc}")

    workspace = Workspace(
        root,
        Path(args.transpiler).expanduser(),
        Path(args.detranspiler).expanduser(),
    )
    token = secrets.token_urlsafe(32)

    class Server(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    try:
        server = Server(
            (args.host, args.port),
            make_handler(workspace, token, allowed_ips),
        )
    except OSError as exc:
        parser.error(f"Server konnte nicht gestartet werden: {exc}")

    browser_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    url = f"http://{browser_host}:{args.port}/"

    print(f"Workspace: {root}")
    print(f"Editor:    {url}")
    print("Erlaubte Client-IPs:", ", ".join(sorted(str(ip) for ip in allowed_ips)))
    print("Mit Ctrl+C beenden.")

    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBeende Server …")
    finally:
        try:
            workspace.stop_watch()
        except Exception:
            pass
        server.server_close()


if __name__ == "__main__":
    main()
