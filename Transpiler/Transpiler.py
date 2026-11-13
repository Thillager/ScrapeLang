"""
Transpiler.py  v5.3
════════════════════════════
Scrape (Java-ähnliche Syntax) → .sb3-Projektdatei

Neu in v5.3:
  • Vollständige Erweiterungsbefehle für alle unterstützten Extensions:
    – music:       playDrum, restForBeats, playNote, setInstrument,
                   setTempo, changeTempo
    – video:       setVideoTransparency, videoOn/videoOff/videoFlipped
    – text2speech: speak, setVoice, setLanguage
    – translate:   translate() (Ausdruck)
    – makey:       keine neuen Statements (nutzt onKeyPressed)
  • Detranspiler erkennt alle Extension-Opcodes korrekt

Neu in v5.1:
  • switchCostume/playSound/animate: Validierung gibt Warnung statt Fehler
    (Referenzen auf nicht vorhandene Kostüme/Sounds kompilieren trotzdem,
    da sie auch im Original-sb3 vorkommen können)
  • Identifier-Sanitisierung im Tokenizer:
    Bezeichner mit ungültigen Zeichen (z.B. Song#, my-var) werden automatisch
    bereinigt (# → _, - → _) und eine Warnung wird ausgegeben.
    Dadurch können .scrape-Dateien die vom Detranspiler v1.0 erzeugt wurden
    (vor der Sanitisierung) direkt kompiliert werden.

Neu in v4/v5:
  • Zeilennummern in allen Fehlermeldungen
  • elseif-Ketten (else if { } else if { } else { })
  • import "Erweiterung";  für Erweiterungen
  • animate("kos1","kos2", secs);  – Animations-Helfer
  • Watch-Modus  (--watch)
  • TurboWarp-Flags  (--turbowarp-new / --turbowarp-replace)
  • Verbesserter Validator mit klaren Fehlermeldungen
"""

import re, json, uuid, zipfile, sys, hashlib, io, os, time, subprocess, platform
from pathlib import Path

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ═══════════════════════════════════════════════════════
#  0.  Hilfsfunktionen
# ═══════════════════════════════════════════════════════
def new_id() -> str:
    return uuid.uuid4().hex[:20]

def md5hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()

def _sanitize_ident(name: str) -> str:
    """
    Bereinigt einen Bezeichner der ungültige Zeichen enthält.
    Wird im Tokenizer aufgerufen wenn ein IDENT-Token Zeichen enthält
    die außerhalb von [A-Za-z0-9_] liegen (z.B. Song# → Song_).

    Regeln:
      • Ungültige Zeichen → _
      • Beginnt mit Ziffer → führendes _ anhängen
      • Leerstring → "_var"
    """
    if not name:
        return "_var"
    result = re.sub(r'[^A-Za-z0-9_]', '_', name)
    if result[0].isdigit():
        result = '_' + result
    return result


# ═══════════════════════════════════════════════════════
#  A.  ASSET-MANAGER
# ═══════════════════════════════════════════════════════
class AssetManager:
    PLACEHOLDER_COSTUME_SVG = (
        b'<svg version="1.1" xmlns="http://www.w3.org/2000/svg" '
        b'width="64" height="64" viewBox="0 0 64 64">'
        b'<circle cx="32" cy="32" r="28" fill="#4C97FF" stroke="#3373CC" stroke-width="3"/>'
        b'<text x="32" y="37" text-anchor="middle" font-size="14" fill="white" '
        b'font-family="sans-serif">?</text>'
        b'</svg>'
    )
    SILENT_WAV = (
        b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00'
        b'\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00'
        b'\x10\x00data\x00\x00\x00\x00'
    )
    _LIBRARY_URLS = {
        "costumes":  "https://raw.githubusercontent.com/scratchfoundation/scratch-gui/develop/src/lib/libraries/costumes.json",
        "backdrops": "https://raw.githubusercontent.com/scratchfoundation/scratch-gui/develop/src/lib/libraries/backdrops.json",
        "sounds":    "https://raw.githubusercontent.com/scratchfoundation/scratch-gui/develop/src/lib/libraries/sounds.json",
    }
    _ASSET_SERVER = "https://assets.scratch.mit.edu/internalapi/asset/{md5ext}/get/"
    _CACHE_FILE   = Path.home() / ".scrape_transpiler_library.json"
    _library: dict = {}

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self._files: dict[str, bytes] = {}
        if not AssetManager._library:
            AssetManager._library = self._load_library()

    def _load_library(self) -> dict:
        import urllib.request as _req
        if self._CACHE_FILE.exists():
            age = time.time() - self._CACHE_FILE.stat().st_mtime
            if age < 7 * 86400:
                try:
                    lib = json.loads(self._CACHE_FILE.read_text(encoding="utf-8"))
                    print(f"  📚 Bibliothek aus Cache ({len(lib.get('costumes',{}))} Kostüme, "
                          f"{len(lib.get('backdrops',{}))} Hintergründe, "
                          f"{len(lib.get('sounds',{}))} Sounds)")
                    return lib
                except Exception:
                    pass
        print("  📚 Lade Bibliothek von GitHub...", end=" ", flush=True)
        result = {"costumes": {}, "backdrops": {}, "sounds": {}}
        try:
            for kind, url in self._LIBRARY_URLS.items():
                with _req.urlopen(url, timeout=10) as r:
                    data = json.loads(r.read())
                for item in data:
                    name = item.get("name", ""); md5 = item.get("md5ext", "")
                    if not md5 or not name: continue
                    fmt = md5.rsplit(".", 1)[-1]; asset_id = md5.rsplit(".", 1)[0]
                    result[kind][name.lower()] = {
                        "name": name, "md5ext": md5, "assetId": asset_id,
                        "dataFormat": fmt,
                        "rotationCenterX": item.get("rotationCenterX", 0),
                        "rotationCenterY": item.get("rotationCenterY", 0),
                        "bitmapResolution": item.get("bitmapResolution", 1),
                    }
            print(f"{sum(len(v) for v in result.values())} Assets ✓")
            try:
                self._CACHE_FILE.write_text(json.dumps(result, separators=(",",":")), encoding="utf-8")
            except Exception:
                pass
        except Exception as e:
            print(f"fehlgeschlagen ({e})")
        return result

    def _lookup(self, name: str, kind: str) -> dict | None:
        return AssetManager._library.get(kind, {}).get(name.lower())

    def _register(self, data: bytes, ext: str) -> tuple[str, str]:
        asset_id = md5hex(data); filename = f"{asset_id}.{ext}"
        self._files[filename] = data
        return asset_id, filename

    def _png_costume(self, data: bytes, name: str) -> dict:
        asset_id, _ = self._register(data, "png")
        cx = cy = 0
        if HAS_PIL:
            try:
                img = PILImage.open(io.BytesIO(data))
                cx, cy = img.width // 2, img.height // 2
            except Exception:
                pass
        return {"assetId": asset_id, "name": name, "bitmapResolution": 2,
                "md5ext": f"{asset_id}.png", "dataFormat": "png",
                "rotationCenterX": cx, "rotationCenterY": cy}

    def load_image(self, path_str: str | None, name: str) -> dict:
        search = name if path_str is None else (
            path_str if ("/" not in path_str and "." not in path_str) else None)
        if search:
            entry = self._lookup(search, "costumes")
            if entry:
                print(f"      → Bibliothek: '{entry['name']}' ({entry['md5ext']})")
                return {"assetId": entry["assetId"], "name": name,
                        "bitmapResolution": entry["bitmapResolution"],
                        "md5ext": entry["md5ext"], "dataFormat": entry["dataFormat"],
                        "rotationCenterX": entry["rotationCenterX"],
                        "rotationCenterY": entry["rotationCenterY"]}
            if path_str is None:
                print(f"      ⚠ '{name}' nicht in Bibliothek → Platzhalter")
                return self._fallback_costume(name)
        if path_str is None:
            return self._fallback_costume(name)
        path = (self.base_dir / path_str).resolve()
        if not path.exists():
            print(f"      ⚠ Bild nicht gefunden: {path}")
            print(f"         Lege '{path.name}' neben dein Script.")
            return self._fallback_costume(name)
        suffix = path.suffix.lower()
        if suffix == ".svg":
            data = path.read_bytes(); asset_id, _ = self._register(data, "svg")
            cx = cy = 0
            try:
                import re as _re; txt = data.decode("utf-8", errors="ignore")
                w = _re.search(r'width="([0-9.]+)"', txt)
                h = _re.search(r'height="([0-9.]+)"', txt)
                if w and h: cx = int(float(w.group(1)))//2; cy = int(float(h.group(1)))//2
            except Exception:
                pass
            return {"assetId": asset_id, "name": name, "bitmapResolution": 1,
                    "md5ext": f"{asset_id}.svg", "dataFormat": "svg",
                    "rotationCenterX": cx, "rotationCenterY": cy}
        if HAS_PIL:
            try:
                img = PILImage.open(path).convert("RGBA")
                buf = io.BytesIO(); img.save(buf, "PNG")
                return self._png_costume(buf.getvalue(), name)
            except Exception as e:
                print(f"      ⚠ Bildfehler ({path.name}): {e} → Platzhalter")
                return self._fallback_costume(name)
        if suffix == ".png":
            return self._png_costume(path.read_bytes(), name)
        print(f"      ⚠ Pillow nicht installiert → Platzhalter")
        return self._fallback_costume(name)

    def _fallback_costume(self, name: str) -> dict:
        asset_id, _ = self._register(self.PLACEHOLDER_COSTUME_SVG, "svg")
        return {"assetId": asset_id, "name": name, "bitmapResolution": 1,
                "md5ext": f"{asset_id}.svg", "dataFormat": "svg",
                "rotationCenterX": 32, "rotationCenterY": 32}

    def load_backdrop(self, path_str: str | None, name: str) -> dict:
        search = name if path_str is None else (
            path_str if ("/" not in path_str and "." not in path_str) else None)
        if search:
            entry = self._lookup(search, "backdrops")
            if entry:
                print(f"      → Bibliothek: '{entry['name']}' ({entry['md5ext']})")
                return {"assetId": entry["assetId"], "name": name,
                        "bitmapResolution": entry["bitmapResolution"],
                        "md5ext": entry["md5ext"], "dataFormat": entry["dataFormat"],
                        "rotationCenterX": entry["rotationCenterX"],
                        "rotationCenterY": entry["rotationCenterY"]}
            if path_str is None:
                WHITE = b'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="360"><rect width="480" height="360" fill="white"/></svg>'
                asset_id, _ = self._register(WHITE, "svg")
                return {"assetId": asset_id, "name": name, "bitmapResolution": 1,
                        "md5ext": f"{asset_id}.svg", "dataFormat": "svg",
                        "rotationCenterX": 240, "rotationCenterY": 180}
        c = self.load_image(path_str, name)
        if HAS_PIL and path_str and Path(path_str).suffix.lower() != ".svg":
            try:
                img = PILImage.open((self.base_dir / path_str).resolve())
                c["rotationCenterX"] = img.width // 2
                c["rotationCenterY"] = img.height // 2
            except Exception:
                c["rotationCenterX"] = 240; c["rotationCenterY"] = 180
        return c

    def load_sound(self, path_str: str | None, name: str) -> dict:
        search = name if path_str is None else (
            path_str if ("/" not in path_str and "." not in path_str) else None)
        if search:
            entry = self._lookup(search, "sounds")
            if entry:
                print(f"      → Bibliothek: '{entry['name']}' ({entry['md5ext']})")
                return {"assetId": entry["assetId"], "name": name,
                        "dataFormat": entry["dataFormat"], "format": "",
                        "rate": 44100, "sampleCount": 0, "md5ext": entry["md5ext"]}
            if path_str is None:
                return self._fallback_sound(name)
        if path_str is None:
            return self._fallback_sound(name)
        path = (self.base_dir / path_str).resolve()
        if not path.exists():
            print(f"      ⚠ Sound nicht gefunden: {path} → Stille")
            return self._fallback_sound(name)
        suffix = path.suffix.lower().lstrip(".")
        fmt = {"wav":"wav","mp3":"mp3","ogg":"wav","flac":"wav"}.get(suffix, "wav")
        try:
            data = path.read_bytes(); asset_id, _ = self._register(data, fmt)
            return {"assetId": asset_id, "name": name, "dataFormat": fmt,
                    "format": "", "rate": 44100, "sampleCount": 0,
                    "md5ext": f"{asset_id}.{fmt}"}
        except Exception as e:
            print(f"      ⚠ Soundfehler: {e} → Stille")
            return self._fallback_sound(name)

    def _fallback_sound(self, name: str) -> dict:
        asset_id, _ = self._register(self.SILENT_WAV, "wav")
        return {"assetId": asset_id, "name": name, "dataFormat": "wav",
                "format": "", "rate": 44100, "sampleCount": 0,
                "md5ext": f"{asset_id}.wav"}

    def all_files(self) -> dict:
        return dict(self._files)


# ═══════════════════════════════════════════════════════
#  1.  LEXER
# ═══════════════════════════════════════════════════════
KEYWORDS = {
    "public","Sprite","Stage","import",
    "onFlagClicked","onKeyPressed","onSpriteClicked",
    "onBackdropChanged","onBroadcastReceived",
    "repeat","forever","if","else","elseif","repeatUntil",
    "wait","waitUntil","stop","createClone","deleteClone",
    "var","showVar","hideVar","showList","hideList",
    "move","turnLeft","turnRight","goTo","goToSprite",
    "glide","glideToSprite","pointDir","pointTowards",
    "setX","setY","changeX","changeY","bounceOnEdge","setRotationStyle",
    "say","sayFor","think","thinkFor","switchCostume","nextCostume",
    "switchBackdrop","nextBackdrop","setSize","changeSize","animate",
    "show","hide","goToFront","goToBack","goForwardLayers","goBackwardLayers",
    "setEffect","changeEffect","clearEffects",
    "playSound","playSoundUntilDone","stopAllSounds","setVolume","changeVolume",
    "askAndWait","setDragMode","resetTimer",
    "penDown","penUp","setPenColor","changePenColor",
    "setPenSize","changePenSize","stampPen","erasePen",
    # Music extension
    "playDrum","restForBeats","playNote","setInstrument",
    "setTempo","changeTempo",
    # Video extension
    "setVideoTransparency","videoOn","videoOff","videoFlipped",
    # Text2Speech extension
    "speak","setVoice","setLanguage",
    "broadcast","broadcastAndWait",
    "onCloneCreated",
    "define","void","public","private","shown","hidden",
    "addCostume","addBackdrop","addSound",
    "random","abs","floor","ceil","sqrt",
    "sin","cos","tan","asin","acos","atan","ln","log","round",
    "length","letter","contains","join",
    "getTempo","translate","viewerLanguage","videoMotion","videoDirection",
    "answer","mouseX","mouseY","mouseDown","keyPressed",
    "touching","touchingColor","distanceTo","timer",
    "currentYear","currentMonth","currentDate","currentDayOfWeek",
    "currentHour","currentMinute","currentSecond",
    "loudness","username","true","false",
    "xPosition","yPosition","direction","Math",
}

# ═══════════════════════════════════════════════════════
#  Fehler-Sammlung  (wird vom Parser befüllt)
# ═══════════════════════════════════════════════════════
class ErrorCollector:
    """Sammelt alle Syntax-/Validierungsfehler und gibt sie am Ende aus."""
    def __init__(self):
        self.errors: list[tuple[int, str, str]] = []  # (line, message, fix_hint)

    def add(self, line: int, message: str, fix: str = ""):
        self.errors.append((line, message, fix))

    def has_errors(self) -> bool:
        return bool(self.errors)

    def print_all(self):
        if not self.errors:
            return
        print(f"\n  ✗  {len(self.errors)} Syntaxfehler gefunden:\n")
        for i, (line, msg, fix) in enumerate(self.errors, 1):
            prefix = f"  [{i}]" if len(self.errors) > 1 else "  ✗ "
            print(f"{prefix} Zeile {line}: {msg}")
            if fix:
                print(f"       💡 Fix: {fix}")
        print()

# Bekannte Fix-Hinweise für häufige Fehler
_FIX_HINTS: dict[str, str] = {
    "LBRACE":    "Geschweifte Klammer '{{' erwartet – fehlt das öffnende '{{' am Blockbeginn?",
    "RBRACE":    "Geschweifte Klammer '}}' erwartet – fehlt das schließende '}}' am Blockende?",
    "LPAREN":    "Öffnende Klammer '(' erwartet – Syntax: befehl(argumente);",
    "RPAREN":    "Schließende Klammer ')' erwartet – Klammer nicht geschlossen?",
    "SEMI":      "Semikolon ';' fehlt am Zeilenende.",
    "STRING":    "String in Anführungszeichen erwartet, z.B. \"text\".",
    "IDENT":     "Bezeichner (Name) erwartet – kein Schlüsselwort oder Zahl verwenden.",
    "COMMA":     "Komma ',' zwischen Argumenten erwartet.",
    "LBRACKET":  "Eckige Klammer '[' erwartet.",
    "RBRACKET":  "Eckige Klammer ']' erwartet.",
}

# ── Extended IDENT: absorbs trailing non-syntax chars (z.B. Song# → als ein Token erkannt)
# Zeichen die NICHT absorbiert werden: Whitespace und alle Syntaxzeichen von Scrape
_IDENT_EXTRA = r'[^A-Za-z0-9_\s\(\)\{\}\[\];,=+\-\*/<>!&|.%\"\'\\]'
_EXTENDED_IDENT = r'[A-Za-z_][A-Za-z0-9_]*(?:' + _IDENT_EXTRA + r'[A-Za-z0-9_]*)*'

TOKEN_PATTERNS = [
    ("COMMENT",  r'//[^\n]*'),
    ("COMMENT2", r'/\*.*?\*/'),
    ("NEWLINE",  r'\n'),
    ("NUMBER",   r'\d+(\.\d+)?'),
    ("STRING",   r'"[^"]*"'),
    ("OP2",      r'==|!=|<=|>=|&&|\|\||\+\+|--|\+=|-=|\*=|/='),
    ("OP",       r'[+\-*/%<>!]'),
    ("ASSIGN",   r'='),
    ("DOT",      r'\.'),
    ("LPAREN",   r'\('),
    ("RPAREN",   r'\)'),
    ("LBRACE",   r'\{'),
    ("RBRACE",   r'\}'),
    ("LBRACKET", r'\['),
    ("RBRACKET", r'\]'),
    ("SEMI",     r';'),
    ("COMMA",    r','),
    ("IDENT",    _EXTENDED_IDENT),   # ← v5.1: extended, sanitized in tokenize()
    ("SKIP",     r'[ \t\r]+'),
    ("MISMATCH", r'.'),
]
MASTER_RE = re.compile(
    '|'.join(f'(?P<{name}>{pat})' for name, pat in TOKEN_PATTERNS),
    re.DOTALL
)

def tokenize(source: str) -> list:
    """
    Gibt Liste von (kind, value, line) zurück.
    line = Zeilennummer (1-basiert).
    COMMENT-Token werden als ("COMMENT", text_ohne_slashes, line) durchgereicht,
    damit der Parser sie Blöcken als Kommentare zuordnen kann.

    v5.1: IDENT-Token mit ungültigen Zeichen (z.B. Song#) werden automatisch
    sanitisiert (# → _) und eine Warnung wird ausgegeben.
    """
    tokens = []
    line = 1
    for m in MASTER_RE.finditer(source):
        kind = m.lastgroup; value = m.group()
        if kind == "NEWLINE":
            line += 1; continue
        if kind == "SKIP":
            continue
        if kind == "COMMENT":
            text = value[2:].strip()
            tokens.append(("COMMENT", text, line))
            continue
        if kind == "COMMENT2":
            text = value[2:-2].strip()
            line += value.count("\n")
            tokens.append(("COMMENT", text, line))
            continue
        if kind == "MISMATCH":
            raise SyntaxError(
                f"Zeile {line}: Unbekanntes Zeichen: {value!r}\n"
                f"     💡 Fix: Sonderzeichen entfernen oder durch gültige Syntax ersetzen."
            )
        if kind == "IDENT":
            # v5.1: Sanitisierung ungültiger Zeichen in Bezeichnern
            sanitized = _sanitize_ident(value)
            if sanitized != value:
                print(f"  ⚠  Zeile {line}: Bezeichner {value!r} enthält ungültige Zeichen "
                      f"→ automatisch zu {sanitized!r} sanitisiert")
                value = sanitized
            if value in KEYWORDS:
                kind = "KEYWORD"
        tokens.append((kind, value, line))
    return tokens


# ═══════════════════════════════════════════════════════
#  2.  PARSER
# ═══════════════════════════════════════════════════════

# Alle bekannten Erweiterungen mit ihren Extension-IDs
KNOWN_EXTENSIONS = {
    # Name (lowercase) → extension_id für project.json
    "pen":          "pen",
    "music":        "music",
    "video":        "videoSensing",
    "text2speech":  "text2speech",
    "translate":    "translate",
    "makey":        "makeymakey",
    "microbit":     "microbit",
    "ev3":          "ev3",
    "boost":        "boost",
    "wedo":         "wedo2",
    "gdxfor":       "gdxfor",
    "tts":          "text2speech",
    "text to speech": "text2speech",
    "video sensing": "videoSensing",
    "makey makey":  "makeymakey",
}

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens   # list of (kind, value, line)
        self.pos    = 0
        self.vars:          set  = set()
        self.lists:         set  = set()
        self.custom_blocks: dict = {}
        self.extensions:    list = []   # gesammelte import-Erweiterungen
        self.collector = ErrorCollector()   # sammelt alle Fehler

    def peek(self, offset=0):
        """Liefert das nächste Nicht-COMMENT-Token (offset=0) oder überspringt entsprechend viele."""
        skipped = 0
        idx = self.pos
        while idx < len(self.tokens):
            if self.tokens[idx][0] != "COMMENT":
                if skipped == offset:
                    return self.tokens[idx]
                skipped += 1
            idx += 1
        return ("EOF", "", 0)

    def _peek_raw(self, offset=0):
        """Liefert das Token an Position pos+offset OHNE COMMENT-Filterung."""
        idx = self.pos + offset
        return self.tokens[idx] if idx < len(self.tokens) else ("EOF", "", 0)

    def current_line(self) -> int:
        return self.peek()[2]

    def _collect_pending_comment(self) -> str | None:
        """Gibt den Text des nächsten COMMENT-Tokens zurück falls es VOR dem
        nächsten Nicht-COMMENT steht, und konsumiert es. Sonst None."""
        if self.pos < len(self.tokens) and self.tokens[self.pos][0] == "COMMENT":
            _, text, _ = self.tokens[self.pos]
            self.pos += 1
            return text
        return None

    def _collect_inline_comment(self) -> str | None:
        """Gibt den Text eines COMMENT-Tokens zurück, das NACH einem Statement
        auf derselben Zeile steht (Inline-Kommentar). Konsumiert es ebenfalls."""
        return self._collect_pending_comment()

    def consume(self, kind=None, value=None):
        # COMMENT-Token transparent überspringen
        while self.pos < len(self.tokens) and self.tokens[self.pos][0] == "COMMENT":
            self.pos += 1
        if self.pos >= len(self.tokens):
            ln = 0
            if kind:
                fix = _FIX_HINTS.get(kind, "")
                self.collector.add(ln, f"Unerwartetes Dateiende, erwartet {kind!r}", fix)
                raise SyntaxError("__collected__")
            return ""
        k, v, ln = self.tokens[self.pos]
        if kind and k != kind:
            fix = _FIX_HINTS.get(kind, "")
            self.collector.add(ln, f"Erwartet {kind!r} ({value or ''}), gefunden {k!r} ({v!r})", fix)
            raise SyntaxError("__collected__")
        if value and v != value:
            fix = _FIX_HINTS.get(value, "")
            self.collector.add(ln, f"Erwartet '{value}', gefunden '{v}'", fix)
            raise SyntaxError("__collected__")
        self.pos += 1
        return v

    def expect_semi(self) -> str | None:
        """Konsumiert ';' (falls vorhanden) und gibt danach stehenden
        Inline-Kommentar zurück (oder None)."""
        if self.peek()[1] == ";":
            self.consume()
        return self._collect_inline_comment()

    def _stmt(self, node: dict, comment: str | None) -> dict:
        """Hängt einen Kommentar ans Statement-Dict, wenn vorhanden."""
        if comment:
            node["comment"] = comment
        return node

    def _recover_to_next_statement(self):
        """Überspringt Token bis zum nächsten sicheren Wiedereintrittspunkt."""
        SAFE_VALUES = {
            "}", ";", "var", "if", "else", "elseif", "repeat", "forever",
            "repeatUntil", "wait", "waitUntil", "stop", "return",
            "onFlagClicked", "onKeyPressed", "onSpriteClicked",
            "onBackdropChanged", "onBroadcastReceived",
            "void", "define", "addCostume", "addBackdrop", "addSound",
            "public", "private",
        }
        start_pos = self.pos
        while self.peek()[0] != "EOF":
            k, v, _ = self.peek()
            if v in SAFE_VALUES or k == "RBRACE":
                if v == ";":
                    self.consume()
                elif self.pos == start_pos:
                    self.pos += 1
                return
            self.pos += 1

    # ── Top-Level ─────────────────────────────────────
    def parse_program(self):
        targets = []
        while self.peek()[0] != "EOF":
            try:
                if self.peek()[1] == "import":
                    self._parse_import()
                else:
                    targets.append(self.parse_target())
            except SyntaxError as e:
                if str(e) != "__collected__":
                    _, _, ln = self.peek()
                    self.collector.add(ln, str(e))
                self._recover_to_next_statement()
        if self.collector.has_errors():
            self.collector.print_all()
            raise SyntaxError("__all_reported__")
        return {"type": "Program", "targets": targets,
                "extensions": list(dict.fromkeys(self.extensions))}

    def _parse_import(self):
        _, _, ln = self.peek()
        self.consume(value="import")
        raw = self.consume("STRING").strip('"')
        self.expect_semi()
        ext_id = KNOWN_EXTENSIONS.get(raw.lower())
        if ext_id:
            if ext_id not in self.extensions:
                self.extensions.append(ext_id)
            print(f"  📦 Import: {raw} → Extension '{ext_id}'")
        else:
            self.collector.add(
                ln,
                f"Unbekannte Erweiterung: \"{raw}\"",
                f"Bekannte Erweiterungen: {', '.join(sorted(KNOWN_EXTENSIONS.keys()))}"
            )

    def parse_target(self):
        ln = self.current_line()
        self.consume(value="public")
        kind = self.consume("KEYWORD")
        if kind not in ("Sprite", "Stage"):
            raise SyntaxError(f"Zeile {ln}: Erwartet 'Sprite' oder 'Stage', gefunden '{kind}'")
        name_kind = self.peek()[0]
        if name_kind in ("IDENT", "KEYWORD"):
            name = self.consume()
        else:
            name = self.consume("IDENT")
        self.consume("LBRACE")

        costumes, backdrops, sounds = [], [], []
        scripts, custom_defs = [], []

        while self.peek()[1] != "}":
            if self.peek()[0] == "EOF":
                _, _, ln_eof = self.peek()
                self.collector.add(ln_eof,
                    f"Geschweifte Klammer '{{' für '{name}' nie geschlossen",
                    "Prüfe ob jede öffnende '{' auch eine schließende '}' hat.")
                break
            v = self.peek()[1]
            try:
                if v == "import":
                    self._parse_import()
                elif v == "addCostume":
                    self.consume(); self.consume("LPAREN")
                    cname = self.consume("STRING").strip('"'); path = None
                    if self.peek()[1] == ",": self.consume("COMMA"); path = self.consume("STRING").strip('"')
                    self.consume("RPAREN"); self.expect_semi()
                    costumes.append({"name": cname, "path": path})
                elif v == "addBackdrop":
                    self.consume(); self.consume("LPAREN")
                    bname = self.consume("STRING").strip('"'); path = None
                    if self.peek()[1] == ",": self.consume("COMMA"); path = self.consume("STRING").strip('"')
                    self.consume("RPAREN"); self.expect_semi()
                    backdrops.append({"name": bname, "path": path})
                elif v == "addSound":
                    self.consume(); self.consume("LPAREN")
                    sname = self.consume("STRING").strip('"'); path = None
                    if self.peek()[1] == ",": self.consume("COMMA"); path = self.consume("STRING").strip('"')
                    self.consume("RPAREN"); self.expect_semi()
                    sounds.append({"name": sname, "path": path})
                elif v in ("public", "private", "shown", "hidden", "var", "void", "define"):
                    scope   = None
                    display = None
                    while self.peek()[1] in ("public","private","shown","hidden"):
                        mod = self.consume()
                        if mod in ("public","private"):
                            if scope is not None:
                                self.collector.add(self.current_line(),
                                    f"Doppelter Scope-Modifier: '{mod}'",
                                    "Nur einen von 'public' oder 'private' angeben.")
                            else:
                                scope = mod
                        else:
                            if display is not None:
                                self.collector.add(self.current_line(),
                                    f"Doppelter Display-Modifier: '{mod}'",
                                    "Nur einen von 'shown' oder 'hidden' angeben.")
                            else:
                                display = mod
                    nv = self.peek()[1]
                    if nv == "var":
                        scope   = scope   or "public"
                        display = display or "shown"
                        decl = self.parse_var_decl()
                        decl["scope"]   = scope
                        decl["display"] = display
                        scripts.append({"event": {"type": "EventFlagClicked"}, "body": [decl]})
                    elif nv in ("void", "define"):
                        scope   = scope   or "public"
                        warp = (scope == "private") or (display == "hidden")
                        cd = self.parse_custom_def()
                        cd["scope"] = scope
                        cd["warp"]  = warp
                        custom_defs.append(cd)
                        raw = cd["params"]
                        self.custom_blocks[cd["name"]] = (
                            [p[0] for p in raw] if raw and not isinstance(raw[0], str) else raw
                        )
                    else:
                        mods = " ".join(filter(None, [scope, display]))
                        _, _, ln_mod = self.peek()
                        self.collector.add(ln_mod,
                            f"Nach '{mods}' erwartet 'var', 'void' oder 'define', gefunden '{nv}'",
                            "Beispiel: public var punkte = 0;  oder  private void hilfsBlock() {}")
                        self._recover_to_next_statement()
                elif v in ("onFlagClicked","onKeyPressed","onSpriteClicked",
                           "onBackdropChanged","onBroadcastReceived","onCloneCreated"):
                    event, body = self.parse_script()
                    scripts.append({"event": event, "body": body})
                else:
                    body = self.parse_block()
                    scripts.append({"event": {"type": "EventFlagClicked"}, "body": body})
            except SyntaxError as e:
                if str(e) != "__collected__":
                    _, _, ln_e = self.peek()
                    self.collector.add(ln_e, str(e))
                self._recover_to_next_statement()

        self.consume("RBRACE")
        return {"type": kind, "name": name,
                "costumes": costumes, "backdrops": backdrops, "sounds": sounds,
                "scripts": scripts, "customDefs": custom_defs}

    def parse_script(self):
        v = self.consume("KEYWORD"); ln = self.current_line()
        if v == "onFlagClicked":
            return {"type": "EventFlagClicked"}, self.parse_block()
        if v == "onKeyPressed":
            self.consume("LPAREN"); key = self.consume("STRING").strip('"'); self.consume("RPAREN")
            return {"type": "EventKeyPressed", "key": key}, self.parse_block()
        if v == "onSpriteClicked":
            return {"type": "EventSpriteClicked"}, self.parse_block()
        if v == "onBackdropChanged":
            self.consume("LPAREN"); bd = self.consume("STRING").strip('"'); self.consume("RPAREN")
            return {"type": "EventBackdropChanged", "backdrop": bd}, self.parse_block()
        if v == "onBroadcastReceived":
            self.consume("LPAREN"); msg = self.consume("STRING").strip('"'); self.consume("RPAREN")
            return {"type": "EventBroadcastReceived", "message": msg}, self.parse_block()
        if v == "onCloneCreated":
            return {"type": "EventCloneStarted"}, self.parse_block()
        raise SyntaxError(f"Zeile {ln}: Unbekanntes Event: {v!r}")

    def parse_block(self):
        ln = self.current_line()
        self.consume("LBRACE")
        stmts = []
        while self.peek()[1] != "}":
            if self.peek()[0] == "EOF":
                self.collector.add(ln,
                    "Geschweifte Klammer '{' nie geschlossen",
                    "Prüfe ob jede öffnende '{' auch eine schließende '}' hat.")
                break
            try:
                stmts.append(self.parse_statement())
            except SyntaxError as e:
                if str(e) != "__collected__":
                    _, _, ln_e = self.peek()
                    self.collector.add(ln_e, str(e))
                self._recover_to_next_statement()
        self.consume("RBRACE")
        return stmts

    def parse_custom_def(self):
        self.consume()   # consume 'define' oder 'void'
        name = self.consume("IDENT")
        self.consume("LPAREN")
        params      = []
        TYPE_MAP = {
            "number": "%s", "int": "%s", "float": "%s",
            "string": "%s", "str": "%s",
            "boolean": "%b", "bool": "%b",
        }
        while self.peek()[1] != ")":
            pk0, pv0, _ = self.peek(0)
            pk1, pv1, _ = self.peek(1)
            if pv0 in TYPE_MAP and pk1 == "IDENT":
                self.consume()
                type_code = TYPE_MAP[pv0]
            else:
                type_code = "%s"
            pname = self.consume("IDENT")
            params.append((pname, type_code))
            if self.peek()[1] == ",": self.consume("COMMA")
        self.consume("RPAREN")
        self.custom_blocks[name] = [p[0] for p in params]
        return {"type": "CustomDef", "name": name, "params": params, "body": self.parse_block()}

    # ── Statements ────────────────────────────────────
    def parse_statement(self):
        k, v, ln = self.peek()
        if v == "var":          return self.parse_var_decl()
        if k == "IDENT":
            if self.peek(1)[1] == ".":  return self.parse_list_method()
            _, nv, _ = self.peek(1)
            if nv in ("=","+=","-=","*=","/=","++","--"): return self.parse_assignment()
            if v in self.custom_blocks: return self.parse_custom_call()
            self.collector.add(ln,
                f"Unbekannter Bezeichner: {v!r}",
                f"Meintest du 'var {v} = ...;'  oder fehlt eine 'void {v}(){{}}'-Definition?")
            raise SyntaxError("__collected__")
        if v == "repeat":         return self.parse_repeat()
        if v == "forever":        return self.parse_forever()
        if v == "if":             return self.parse_if()
        if v == "repeatUntil":    return self.parse_repeat_until()
        if v == "wait":           return self.parse_wait()
        if v == "waitUntil":      return self.parse_wait_until()
        if v == "stop":           return self.parse_stop()
        if v == "createClone":    return self.parse_create_clone()
        if v == "deleteClone":    return self.parse_delete_clone()
        if v == "showVar":        return self.parse_simple_str_cmd("ShowVar")
        if v == "hideVar":        return self.parse_simple_str_cmd("HideVar")
        if v == "showList":       return self.parse_simple_str_cmd("ShowList")
        if v == "hideList":       return self.parse_simple_str_cmd("HideList")
        if v == "move":           return self.parse_motion_1num("Move")
        if v == "turnLeft":       return self.parse_motion_1num("TurnLeft")
        if v == "turnRight":      return self.parse_motion_1num("TurnRight")
        if v == "goTo":           return self.parse_goto_xy()
        if v == "goToSprite":     return self.parse_simple_str_cmd("GoToSprite")
        if v == "glide":          return self.parse_glide()
        if v == "glideToSprite":  return self.parse_glide_to_sprite()
        if v == "pointDir":       return self.parse_motion_1num("PointDir")
        if v == "pointTowards":   return self.parse_simple_str_cmd("PointTowards")
        if v == "setX":           return self.parse_motion_1num("SetX")
        if v == "setY":           return self.parse_motion_1num("SetY")
        if v == "changeX":        return self.parse_motion_1num("ChangeX")
        if v == "changeY":        return self.parse_motion_1num("ChangeY")
        if v == "bounceOnEdge":   return self.parse_no_arg("BounceOnEdge")
        if v == "setRotationStyle": return self.parse_simple_str_cmd("SetRotationStyle")
        if v == "say":            return self.parse_say()
        if v == "sayFor":         return self.parse_say_for()
        if v == "think":          return self.parse_say(think=True)
        if v == "thinkFor":       return self.parse_say_for(think=True)
        if v == "animate":        return self.parse_animate()
        if v == "switchCostume":  return self.parse_simple_str_cmd("SwitchCostume")
        if v == "nextCostume":    return self.parse_no_arg("NextCostume")
        if v == "switchBackdrop": return self.parse_simple_str_cmd("SwitchBackdrop")
        if v == "nextBackdrop":   return self.parse_no_arg("NextBackdrop")
        if v == "setSize":        return self.parse_motion_1num("SetSize")
        if v == "changeSize":     return self.parse_motion_1num("ChangeSize")
        if v == "show":           return self.parse_no_arg("Show")
        if v == "hide":           return self.parse_no_arg("Hide")
        if v == "goToFront":      return self.parse_no_arg("GoToFront")
        if v == "goToBack":       return self.parse_no_arg("GoToBack")
        if v == "goForwardLayers":  return self.parse_motion_1num("GoForwardLayers")
        if v == "goBackwardLayers": return self.parse_motion_1num("GoBackwardLayers")
        if v == "setEffect":      return self.parse_effect_cmd("SetEffect")
        if v == "changeEffect":   return self.parse_effect_cmd("ChangeEffect")
        if v == "clearEffects":   return self.parse_no_arg("ClearEffects")
        if v == "playSound":          return self.parse_simple_str_cmd("PlaySound")
        if v == "playSoundUntilDone": return self.parse_simple_str_cmd("PlaySoundUntilDone")
        if v == "stopAllSounds":      return self.parse_no_arg("StopAllSounds")
        if v == "setVolume":          return self.parse_motion_1num("SetVolume")
        if v == "changeVolume":       return self.parse_motion_1num("ChangeVolume")
        if v == "askAndWait":         return self.parse_simple_str_cmd("AskAndWait")
        if v == "setDragMode":        return self.parse_simple_str_cmd("SetDragMode")
        if v == "resetTimer":         return self.parse_no_arg("ResetTimer")
        if v == "penDown":        return self.parse_no_arg("PenDown")
        if v == "penUp":          return self.parse_no_arg("PenUp")
        if v == "setPenColor":    return self.parse_motion_1num("SetPenColor")
        if v == "changePenColor": return self.parse_motion_1num("ChangePenColor")
        if v == "setPenSize":     return self.parse_motion_1num("SetPenSize")
        if v == "changePenSize":  return self.parse_motion_1num("ChangePenSize")
        if v == "stampPen":       return self.parse_no_arg("StampPen")
        if v == "erasePen":       return self.parse_no_arg("ErasePen")
        if v == "broadcast":         return self.parse_simple_str_cmd("Broadcast")
        if v == "broadcastAndWait":  return self.parse_simple_str_cmd("BroadcastAndWait")
        # ── Music extension ───────────────────────────
        if v == "playDrum":          return self.parse_music_2num("MusicPlayDrum")
        if v == "restForBeats":      return self.parse_motion_1num("MusicRestForBeats")
        if v == "playNote":          return self.parse_music_2num("MusicPlayNote")
        if v == "setInstrument":     return self.parse_motion_1num("MusicSetInstrument")
        if v == "setTempo":          return self.parse_motion_1num("MusicSetTempo")
        if v == "changeTempo":       return self.parse_motion_1num("MusicChangeTempo")
        # ── Video extension ───────────────────────────
        if v == "setVideoTransparency": return self.parse_motion_1num("VideoSetTransparency")
        if v == "videoOn":           return self.parse_no_arg("VideoOn")
        if v == "videoOff":          return self.parse_no_arg("VideoOff")
        if v == "videoFlipped":      return self.parse_no_arg("VideoFlipped")
        # ── Text2Speech extension ─────────────────────
        if v == "speak":             return self.parse_simple_expr_cmd("TtsSpeakAndWait")
        if v == "setVoice":          return self.parse_simple_str_cmd("TtsSetVoice")
        if v == "setLanguage":       return self.parse_simple_str_cmd("TtsSetLanguage")
        self.collector.add(ln,
            f"Unbekanntes Statement: {v!r}",
            f"Gültige Befehle: move, say, if, repeat, forever, var, void, ... – "
            f"Tippfehler in '{v}'?")
        raise SyntaxError("__collected__")

    # ── Kleine Helfer ─────────────────────────────────
    def parse_no_arg(self, t):
        self.consume()
        if self.peek()[1] == "(": self.consume("LPAREN"); self.consume("RPAREN")
        cmt = self.expect_semi()
        return self._stmt({"type": t}, cmt)

    def parse_simple_str_cmd(self, t):
        ln = self.current_line(); self.consume(); self.consume("LPAREN")
        if self.peek()[0] != "STRING":
            _, bad_v, _ = self.peek()
            self.collector.add(ln,
                f"{t} erwartet einen String in Anführungszeichen, gefunden: {bad_v!r}",
                f'Anführungszeichen setzen: {t.lower()}("{bad_v}");')
            raise SyntaxError("__collected__")
        val = self.consume("STRING").strip('"')
        self.consume("RPAREN"); cmt = self.expect_semi()
        return self._stmt({"type": t, "value": val}, cmt)

    def parse_motion_1num(self, t):
        ln = self.current_line(); self.consume(); self.consume("LPAREN")
        expr = self.parse_expr()
        if self.peek()[1] == ",":
            extra_count = 0
            while self.peek()[1] == ",":
                self.consume(); self.parse_expr(); extra_count += 1
            self.consume("RPAREN"); self.expect_semi()
            cmd = t[0].lower() + t[1:]
            self.collector.add(ln,
                f"{cmd}() erwartet 1 Argument, aber {extra_count + 1} wurden übergeben",
                f"Syntax: {cmd}(wert);  – z.B. {cmd}(10);")
            raise SyntaxError("__collected__")
        self.consume("RPAREN"); cmt = self.expect_semi()
        return self._stmt({"type": t, "value": expr}, cmt)

    def parse_effect_cmd(self, t):
        ln = self.current_line(); self.consume(); self.consume("LPAREN")
        if self.peek()[0] != "STRING":
            _, bad_v, _ = self.peek()
            self.collector.add(ln,
                f"{t} erwartet Effektname als String, gefunden: {bad_v!r}",
                f'{t.lower()}("color", 50);  – Gültige Effekte: "color", "fisheye", "whirl", "pixelate", "mosaic", "brightness", "ghost"')
            raise SyntaxError("__collected__")
        effect = self.consume("STRING").strip('"')
        self.consume("COMMA"); val = self.parse_expr()
        self.consume("RPAREN"); cmt = self.expect_semi()
        return self._stmt({"type": t, "effect": effect, "value": val}, cmt)

    def parse_music_2num(self, t):
        """Parses commands with 2 numeric arguments, e.g. playDrum(drum, beats)."""
        ln = self.current_line(); self.consume(); self.consume("LPAREN")
        a = self.parse_expr(); self.consume("COMMA"); b = self.parse_expr()
        self.consume("RPAREN"); cmt = self.expect_semi()
        return self._stmt({"type": t, "a": a, "b": b}, cmt)

    def parse_simple_expr_cmd(self, t):
        """Parses commands with one arbitrary expression argument."""
        ln = self.current_line(); self.consume(); self.consume("LPAREN")
        val = self.parse_expr()
        self.consume("RPAREN"); cmt = self.expect_semi()
        return self._stmt({"type": t, "value": val}, cmt)

    def parse_var_decl(self):
        self.consume(value="var"); name = self.consume("IDENT"); value = None
        if self.peek()[1] == "=": self.consume(); value = self.parse_expr()
        cmt = self.expect_semi(); self.vars.add(name)
        return self._stmt({"type": "VarDecl", "name": name, "value": value}, cmt)

    def parse_assignment(self):
        ln = self.current_line(); name = self.consume("IDENT"); op = self.consume()
        if op in ("++","--"):
            cmt = self.expect_semi()
            return self._stmt({"type": "VarChange", "name": name,
                    "value": {"type": "Num", "value": 1 if op=="++" else -1}}, cmt)
        expr = self.parse_expr(); cmt = self.expect_semi()
        if op == "=": return self._stmt({"type": "VarSet", "name": name, "value": expr}, cmt)
        op_map = {"+=":"add","-=":"sub","*=":"mul","/=":"div"}
        if op not in op_map:
            self.collector.add(ln, f"Unbekannter Zuweisungsoperator: {op!r}",
                "Gültige Operatoren: =  +=  -=  *=  /=  ++  --")
            raise SyntaxError("__collected__")
        return self._stmt({"type": "VarChange", "name": name, "value": expr, "compound": op_map[op]}, cmt)

    def parse_list_method(self):
        ln = self.current_line(); name = self.consume("IDENT"); self.consume("DOT")
        method = self.consume(); self.lists.add(name)
        if method == "add":
            self.consume("LPAREN"); item = self.parse_expr()
            self.consume("RPAREN"); cmt = self.expect_semi()
            return self._stmt({"type": "ListAdd", "list": name, "item": item}, cmt)
        if method == "delete":
            self.consume("LPAREN"); idx = self.parse_expr()
            self.consume("RPAREN"); cmt = self.expect_semi()
            return self._stmt({"type": "ListDelete", "list": name, "index": idx}, cmt)
        if method == "insert":
            self.consume("LPAREN"); idx = self.parse_expr(); self.consume("COMMA")
            item = self.parse_expr(); self.consume("RPAREN"); cmt = self.expect_semi()
            return self._stmt({"type": "ListInsert", "list": name, "index": idx, "item": item}, cmt)
        if method == "replace":
            self.consume("LPAREN"); idx = self.parse_expr(); self.consume("COMMA")
            item = self.parse_expr(); self.consume("RPAREN"); cmt = self.expect_semi()
            return self._stmt({"type": "ListReplace", "list": name, "index": idx, "item": item}, cmt)
        if method == "show":
            if self.peek()[1] == "(": self.consume("LPAREN"); self.consume("RPAREN")
            cmt = self.expect_semi()
            return self._stmt({"type": "ShowList", "value": name}, cmt)
        if method == "hide":
            if self.peek()[1] == "(": self.consume("LPAREN"); self.consume("RPAREN")
            cmt = self.expect_semi()
            return self._stmt({"type": "HideList", "value": name}, cmt)
        self.collector.add(ln, f"Unbekannte Listen-Methode: {name}.{method}()",
            "Gültige Methoden: add, delete, insert, replace, show, hide")
        raise SyntaxError("__collected__")

    def parse_custom_call(self):
        name = self.consume("IDENT"); self.consume("LPAREN"); args = []
        while self.peek()[1] != ")":
            args.append(self.parse_expr())
            if self.peek()[1] == ",": self.consume("COMMA")
        self.consume("RPAREN"); cmt = self.expect_semi()
        return self._stmt({"type": "CustomCall", "name": name, "args": args}, cmt)

    # ── animate("kos1","kos2", secs) ──────────────────
    def parse_animate(self):
        ln = self.current_line(); self.consume(); self.consume("LPAREN")
        costumes = []
        while self.peek()[0] == "STRING":
            costumes.append(self.consume("STRING").strip('"'))
            if self.peek()[1] == ",": self.consume("COMMA")
        if not costumes:
            _, bad_v, _ = self.peek()
            self.collector.add(ln,
                f"animate() braucht mindestens einen Kostümnamen als String, gefunden: {bad_v!r}",
                'Beispiel: animate("kos1", "kos2", 0.1);')
            raise SyntaxError("__collected__")
        secs = self.parse_expr()
        self.consume("RPAREN"); self.expect_semi()
        return {"type": "Animate", "costumes": costumes, "secs": secs}

    # ── Control ───────────────────────────────────────
    def parse_repeat(self):
        self.consume(value="repeat"); self.consume("LPAREN")
        times = self.parse_expr(); self.consume("RPAREN")
        return {"type": "Repeat", "times": times, "body": self.parse_block()}

    def parse_forever(self):
        self.consume(value="forever")
        return {"type": "Forever", "body": self.parse_block()}

    def parse_if(self):
        self.consume(value="if"); self.consume("LPAREN")
        cond = self.parse_expr(); self.consume("RPAREN")
        then = self.parse_block()
        else_ = None
        nk, nv, _ = self.peek()
        if nv == "else":
            self.consume()
            if self.peek()[1] == "if":
                else_ = [self.parse_if()]
            else:
                else_ = self.parse_block()
        elif nv == "elseif":
            else_ = [self.parse_elseif()]
        return {"type": "If", "cond": cond, "then": then, "else": else_}

    def parse_elseif(self):
        self.consume(value="elseif"); self.consume("LPAREN")
        cond = self.parse_expr(); self.consume("RPAREN")
        then = self.parse_block()
        else_ = None
        nk, nv, _ = self.peek()
        if nv == "else":
            self.consume()
            if self.peek()[1] == "if":
                else_ = [self.parse_if()]
            else:
                else_ = self.parse_block()
        elif nv == "elseif":
            else_ = [self.parse_elseif()]
        return {"type": "If", "cond": cond, "then": then, "else": else_}

    def parse_repeat_until(self):
        self.consume(value="repeatUntil"); self.consume("LPAREN")
        cond = self.parse_expr(); self.consume("RPAREN")
        return {"type": "RepeatUntil", "cond": cond, "body": self.parse_block()}

    def parse_wait(self):
        self.consume(value="wait"); self.consume("LPAREN")
        expr = self.parse_expr(); self.consume("RPAREN"); cmt = self.expect_semi()
        return self._stmt({"type": "Wait", "value": expr}, cmt)

    def parse_wait_until(self):
        self.consume(value="waitUntil"); self.consume("LPAREN")
        cond = self.parse_expr(); self.consume("RPAREN"); cmt = self.expect_semi()
        return self._stmt({"type": "WaitUntil", "cond": cond}, cmt)

    def parse_stop(self):
        ln = self.current_line(); self.consume(value="stop"); self.consume("LPAREN")
        if self.peek()[0] != "STRING":
            self.collector.add(ln,
                'stop() erwartet einen String als Argument',
                'Gültige Werte: stop("all");  stop("this script");  stop("other scripts in sprite");')
            raise SyntaxError("__collected__")
        opt = self.consume("STRING").strip('"')
        self.consume("RPAREN"); cmt = self.expect_semi()
        return self._stmt({"type": "Stop", "option": opt}, cmt)

    def parse_create_clone(self):
        self.consume(value="createClone"); self.consume("LPAREN")
        target = self.consume("STRING").strip('"'); self.consume("RPAREN"); cmt = self.expect_semi()
        return self._stmt({"type": "CreateClone", "target": target}, cmt)

    def parse_delete_clone(self):
        self.consume(value="deleteClone")
        if self.peek()[1] == "(": self.consume("LPAREN"); self.consume("RPAREN")
        cmt = self.expect_semi()
        return self._stmt({"type": "DeleteClone"}, cmt)

    def parse_goto_xy(self):
        ln = self.current_line(); self.consume(value="goTo"); self.consume("LPAREN")
        x = self.parse_expr()
        if self.peek()[1] != ",":
            self.consume("RPAREN"); self.expect_semi()
            self._check_arg_count(ln, "goTo", 1, 2, "Syntax: goTo(x, y);  – z.B. goTo(0, 0);")
            raise SyntaxError("__collected__")
        self.consume("COMMA"); y = self.parse_expr()
        if self.peek()[1] == ",":
            extras, _ = self._consume_extra_args()
            self._check_arg_count(ln, "goTo", 2+len(extras), 2, "Syntax: goTo(x, y);")
            raise SyntaxError("__collected__")
        self.consume("RPAREN"); cmt = self.expect_semi()
        return self._stmt({"type": "GoToXY", "x": x, "y": y}, cmt)

    def parse_glide(self):
        ln = self.current_line(); self.consume(value="glide"); self.consume("LPAREN")
        secs = self.parse_expr()
        if self.peek()[1] != ",":
            self.consume("RPAREN"); self.expect_semi()
            self._check_arg_count(ln, "glide", 1, 3, "Syntax: glide(sekunden, x, y);")
            raise SyntaxError("__collected__")
        self.consume("COMMA"); x = self.parse_expr()
        if self.peek()[1] != ",":
            self.consume("RPAREN"); self.expect_semi()
            self._check_arg_count(ln, "glide", 2, 3, "Syntax: glide(sekunden, x, y);")
            raise SyntaxError("__collected__")
        self.consume("COMMA"); y = self.parse_expr()
        if self.peek()[1] == ",":
            extras, _ = self._consume_extra_args()
            self._check_arg_count(ln, "glide", 3+len(extras), 3, "Syntax: glide(sekunden, x, y);")
            raise SyntaxError("__collected__")
        self.consume("RPAREN"); cmt = self.expect_semi()
        return self._stmt({"type": "Glide", "secs": secs, "x": x, "y": y}, cmt)

    def parse_glide_to_sprite(self):
        ln = self.current_line(); self.consume(value="glideToSprite"); self.consume("LPAREN")
        secs = self.parse_expr()
        if self.peek()[1] != ",":
            self.consume("RPAREN"); self.expect_semi()
            self._check_arg_count(ln, "glideToSprite", 1, 2,
                'Syntax: glideToSprite(sekunden, "Sprite-Name");')
            raise SyntaxError("__collected__")
        self.consume("COMMA"); target = self.consume("STRING").strip('"')
        if self.peek()[1] == ",":
            extras, _ = self._consume_extra_args()
            self._check_arg_count(ln, "glideToSprite", 2+len(extras), 2,
                'Syntax: glideToSprite(sekunden, "Sprite-Name");')
            raise SyntaxError("__collected__")
        self.consume("RPAREN"); cmt = self.expect_semi()
        return self._stmt({"type": "GlideToSprite", "secs": secs, "target": target}, cmt)

    def _ast_repr(self, node) -> str:
        if node.get("type") == "Str": return f'"{node["value"]}"'
        if node.get("type") == "Num":
            v = node["value"]
            return str(int(v) if isinstance(v, float) and v.is_integer() else v)
        if node.get("type") == "Var": return node["name"]
        return "..."

    def _check_arg_count(self, ln, cmd, got, expected, suggestion=""):
        self.collector.add(ln,
            f"{cmd}() erwartet {expected} Argument{'e' if expected != 1 else ''}, "
            f"aber {got} {'wurden' if got != 1 else 'wurde'} übergeben",
            suggestion or f"Syntax: {cmd}({'text' if expected == 1 else 'text, sekunden'});")

    def _consume_extra_args(self) -> tuple[list, str | None]:
        extras = []
        while self.peek()[1] == ",":
            self.consume(); extras.append(self.parse_expr())
        self.consume("RPAREN")
        return extras, self.expect_semi()

    def parse_say(self, think=False):
        cmd = "think" if think else "say"
        ln = self.current_line(); self.consume(); self.consume("LPAREN")
        text = self.parse_expr()
        if self.peek()[1] == ",":
            self.consume()
            extra = self.parse_expr()
            extras, _ = self._consume_extra_args()
            total = 2 + len(extras)
            if total == 2:
                self._check_arg_count(ln, cmd, 2, 1,
                    f"Meintest du {cmd}For({self._ast_repr(text)}, {self._ast_repr(extra)})? "
                    f"→ {cmd}For(text, sekunden);")
            else:
                self._check_arg_count(ln, cmd, total, 1,
                    f"Syntax: {cmd}(text);  oder  {cmd}For(text, sekunden);")
            raise SyntaxError("__collected__")
        self.consume("RPAREN"); cmt = self.expect_semi()
        return self._stmt({"type": "Think" if think else "Say", "text": text}, cmt)

    def parse_say_for(self, think=False):
        cmd = "thinkFor" if think else "sayFor"
        ln = self.current_line(); self.consume(); self.consume("LPAREN")
        text = self.parse_expr()
        if self.peek()[1] != ",":
            self.consume("RPAREN"); self.expect_semi()
            self._check_arg_count(ln, cmd, 1, 2,
                f"Syntax: {cmd}(text, sekunden);  – z.B. {cmd}(\"Hallo!\", 3);")
            raise SyntaxError("__collected__")
        self.consume("COMMA"); secs = self.parse_expr()
        if self.peek()[1] == ",":
            extras, _ = self._consume_extra_args()
            self._check_arg_count(ln, cmd, 2 + len(extras), 2,
                f"Syntax: {cmd}(text, sekunden);  – z.B. {cmd}(\"Hallo!\", 3);")
            raise SyntaxError("__collected__")
        self.consume("RPAREN"); cmt = self.expect_semi()
        return self._stmt({"type": "ThinkFor" if think else "SayFor", "text": text, "secs": secs}, cmt)

    # ── Ausdrücke (Pratt-Parser) ──────────────────────
    def parse_expr(self, min_prec=0):
        if self.peek()[1] == "!" and min_prec == 0:
            self.consume()
            if self.peek()[1] == "(":
                self.consume("LPAREN"); operand = self.parse_expr(); self.consume("RPAREN")
            else:
                operand = self._parse_arithmetic_and_dot()
            left = {"type": "UnaryOp", "op": "!", "operand": operand}
        else:
            left = self.parse_unary()
            left = self._parse_dot_postfix(left)

        while True:
            _, op, _ = self.peek()
            prec = {"||":1,"&&":2,"==":3,"!=":3,"<":3,">":3,"<=":3,">=":3,
                    "+":4,"-":4,"*":5,"/":5,"%":5}.get(op, -1)
            if prec < min_prec: break
            self.consume()
            right = self.parse_expr(prec + 1)
            right = self._parse_dot_postfix(right)
            left = {"type": "BinOp", "op": op, "left": left, "right": right}
        return left

    def _parse_arithmetic_and_dot(self):
        node = self.parse_primary()
        while True:
            _, op, _ = self.peek()
            if op not in ("*","/","%","+","-"): break
            self.consume(); right = self.parse_primary()
            node = {"type": "BinOp", "op": op, "left": node, "right": right}
        return self._parse_dot_postfix(node)

    def _parse_dot_postfix(self, node):
        while self.peek()[1] == ".":
            method = self.peek(1)[1]
            if method not in ("length","contains","letter","join","indexOf"): break
            self.consume("DOT"); self.consume()
            if method == "length":
                if self.peek()[1] == "(": self.consume("LPAREN"); self.consume("RPAREN")
                if node["type"] == "Var" and node.get("name","") in self.lists:
                    node = {"type": "ListLength", "list": node["name"]}
                else:
                    node = {"type": "StrLength", "value": node}
            elif method == "contains":
                self.consume("LPAREN"); arg = self.parse_expr(); self.consume("RPAREN")
                if node["type"] == "Var" and node.get("name","") in self.lists:
                    node = {"type": "ListContains", "list": node["name"], "item": arg}
                else:
                    node = {"type": "StrContains", "str": node, "sub": arg}
            elif method == "letter":
                self.consume("LPAREN"); n = self.parse_expr(); self.consume("RPAREN")
                node = {"type": "LetterOf", "n": n, "str": node}
            elif method == "join":
                self.consume("LPAREN"); other = self.parse_expr(); self.consume("RPAREN")
                node = {"type": "Join", "a": node, "b": other}
            elif method == "indexOf":
                self.consume("LPAREN"); arg = self.parse_expr(); self.consume("RPAREN")
                node = {"type": "StrContains", "str": node, "sub": arg}
        return node

    def parse_unary(self):
        _, v, _ = self.peek()
        if v == "-":
            self.consume(); return {"type": "UnaryOp", "op": "-", "operand": self.parse_primary()}
        return self.parse_primary()

    def parse_primary(self):
        k, v, ln = self.peek()
        if k == "NUMBER":
            self.consume(); return {"type": "Num", "value": float(v)}
        if k == "STRING":
            self.consume(); return {"type": "Str", "value": v.strip('"')}
        if v == "true":  self.consume(); return {"type": "Bool", "value": True}
        if v == "false": self.consume(); return {"type": "Bool", "value": False}
        if v == "(":
            self.consume("LPAREN"); e = self.parse_expr(); self.consume("RPAREN"); return e
        if v == "Math":
            self.consume(); self.consume("DOT"); method = self.consume()
            self.consume("LPAREN")
            if method == "random":
                a = self.parse_expr(); self.consume("COMMA"); b = self.parse_expr()
                self.consume("RPAREN"); return {"type": "Random", "from": a, "to": b}
            if method == "round":
                x = self.parse_expr(); self.consume("RPAREN"); return {"type": "Round", "value": x}
            if method in ("abs","floor","ceil","sqrt","sin","cos","tan",
                          "asin","acos","atan","ln","log"):
                lbl = "ceiling" if method == "ceil" else method
                x = self.parse_expr(); self.consume("RPAREN")
                return {"type": "MathOp", "op": lbl, "value": x}
            self.collector.add(ln,
                f"Unbekannte Math-Methode: Math.{method}()",
                "Gültige Methoden: Math.random(a,b), Math.round(x), Math.abs(x), Math.floor(x), "
                "Math.ceil(x), Math.sqrt(x), Math.sin(x), Math.cos(x), Math.tan(x), "
                "Math.asin(x), Math.acos(x), Math.atan(x), Math.ln(x), Math.log(x)")
            raise SyntaxError("__collected__")
        if v in ("random","abs","floor","ceil","sqrt","sin","cos","tan",
                 "asin","acos","atan","ln","log","round","length","letter",
                 "contains","join"):
            return self.parse_operator_func(v)
        if v in ("answer","mouseX","mouseY","mouseDown","timer","loudness","username"):
            self.consume(); return {"type": "Sensing", "sense": v}
        if v in ("currentYear","currentMonth","currentDate","currentDayOfWeek",
                 "currentHour","currentMinute","currentSecond"):
            self.consume()
            fm = {"currentYear":"YEAR","currentMonth":"MONTH","currentDate":"DATE",
                  "currentDayOfWeek":"DAYOFWEEK","currentHour":"HOUR",
                  "currentMinute":"MINUTE","currentSecond":"SECOND"}
            return {"type": "CurrentDate", "field": fm[v]}
        if v == "keyPressed":
            self.consume(); self.consume("LPAREN"); key = self.consume("STRING").strip('"')
            self.consume("RPAREN"); return {"type": "KeyPressed", "key": key}
        if v == "touching":
            self.consume(); self.consume("LPAREN"); target = self.consume("STRING").strip('"')
            self.consume("RPAREN"); return {"type": "Touching", "target": target}
        if v == "touchingColor":
            self.consume(); self.consume("LPAREN"); color = self.parse_expr()
            self.consume("RPAREN"); return {"type": "TouchingColor", "color": color}
        if v == "distanceTo":
            self.consume(); self.consume("LPAREN"); target = self.consume("STRING").strip('"')
            self.consume("RPAREN"); return {"type": "DistanceTo", "target": target}
        if v in ("xPosition","yPosition","direction"):
            self.consume(); return {"type": "MotionVal", "val": v}
        # ── Music reporter ────────────────────────────
        if v == "getTempo":
            self.consume(); return {"type": "MusicGetTempo"}
        # ── Translate reporter ────────────────────────
        if v == "translate":
            self.consume(); self.consume("LPAREN")
            words = self.parse_expr(); self.consume("COMMA")
            lang = self.parse_expr()
            self.consume("RPAREN")
            return {"type": "TranslateGetTranslate", "words": words, "language": lang}
        # ── Viewer language reporter ──────────────────
        if v == "viewerLanguage":
            self.consume(); return {"type": "TtsViewerLanguage"}
        # ── Video reporters ───────────────────────────
        if v == "videoMotion":
            self.consume(); self.consume("LPAREN")
            subject = self.parse_expr()
            self.consume("RPAREN")
            return {"type": "VideoSensingMotion", "attribute": "motion", "subject": subject}
        if v == "videoDirection":
            self.consume(); self.consume("LPAREN")
            subject = self.parse_expr()
            self.consume("RPAREN")
            return {"type": "VideoSensingMotion", "attribute": "direction", "subject": subject}
        if k == "IDENT":
            name = self.consume("IDENT")
            if self.peek()[1] == "[":
                self.consume("LBRACKET"); idx = self.parse_expr(); self.consume("RBRACKET")
                return {"type": "ListItem", "list": name, "index": idx}
            return {"type": "Var", "name": name}
        self.collector.add(ln,
            f"Unerwartetes Token: {v!r} (Typ: {k}) – Ausdruck erwartet",
            "Gültige Ausdrücke: Zahlen (42), Strings (\"text\"), Variablen (meinVar), "
            "true/false, Math.random(1,10), xPosition, mouseX, ...")
        raise SyntaxError("__collected__")

    def parse_operator_func(self, name):
        self.consume(); self.consume("LPAREN")
        if name == "random":
            a = self.parse_expr(); self.consume("COMMA"); b = self.parse_expr()
            self.consume("RPAREN"); return {"type": "Random", "from": a, "to": b}
        if name == "length":
            s = self.parse_expr(); self.consume("RPAREN"); return {"type": "StrLength", "value": s}
        if name == "letter":
            n = self.parse_expr(); self.consume("COMMA"); s = self.parse_expr()
            self.consume("RPAREN"); return {"type": "LetterOf", "n": n, "str": s}
        if name == "contains":
            s = self.parse_expr(); self.consume("COMMA"); sub = self.parse_expr()
            self.consume("RPAREN"); return {"type": "StrContains", "str": s, "sub": sub}
        if name == "join":
            a = self.parse_expr(); self.consume("COMMA"); b = self.parse_expr()
            self.consume("RPAREN"); return {"type": "Join", "a": a, "b": b}
        if name == "round":
            x = self.parse_expr(); self.consume("RPAREN"); return {"type": "Round", "value": x}
        lbl = "ceiling" if name == "ceil" else name
        x = self.parse_expr(); self.consume("RPAREN")
        return {"type": "MathOp", "op": lbl, "value": x}


# ═══════════════════════════════════════════════════════
#  3.  CODE-GENERATOR
# ═══════════════════════════════════════════════════════
class BlockGenerator:
    def __init__(self):
        self.blocks:          dict = {}
        self.variables:       dict = {}
        self.lists:           dict = {}
        self.broadcasts:      dict = {}
        self.comments:        dict = {}
        self.custom_procs:    dict = {}
        self.custom_arg_ids:  dict = {}
        self.custom_warp:     dict = {}
        self.current_params:  dict = {}
        self._var_scope:      dict = {}

    def _add(self, bid, opcode, parent, nxt,
             inputs=None, fields=None, top=False, x=0, y=0, mutation=None):
        b = {"opcode": opcode, "next": nxt, "parent": parent,
             "inputs": inputs or {}, "fields": fields or {},
             "shadow": False, "topLevel": top}
        if top: b["x"] = x; b["y"] = y
        if mutation: b["mutation"] = mutation
        self.blocks[bid] = b; return bid

    def _attach_comment(self, block_id: str, text: str):
        cur = block_id
        bx, by = 0, 0
        depth = 0
        for _ in range(200):
            blk = self.blocks.get(cur, {})
            if blk.get("topLevel"):
                bx = blk.get("x", 0) + 300
                by = blk.get("y", 0) + depth * 60 - 40
                break
            parent = blk.get("parent")
            if not parent:
                break
            cur = parent
            depth += 1
        cid = new_id()
        self.comments[cid] = {
            "blockId": block_id,
            "x": bx, "y": by,
            "width": max(350, len(text) * 12),
            "height": 100,
            "minimized": False,
            "text": text,
        }
        if block_id in self.blocks:
            self.blocks[block_id]["comment"] = cid

    def _iv(self, node):
        if node["type"] == "Num":
            v = node["value"]
            return [4, str(int(v) if isinstance(v, float) and v.is_integer() else v)]
        if node["type"] == "Str":  return [10, node["value"]]
        return None

    def _input(self, node, parent_id, slot=1):
        iv = self._iv(node)
        if iv:
            return [slot, iv]
        child_id = self.gen_expr(node, parent_id)
        return [2, child_id]

    def _bool_input(self, node, parent_id):
        iv = self._iv(node)
        if iv:
            return [2, iv]
        child_id = self.gen_expr(node, parent_id)
        return [2, child_id]

    def _var_id(self, n):
        if n not in self.variables: self.variables[n] = new_id()
        return self.variables[n]

    def _list_id(self, n):
        if n not in self.lists: self.lists[n] = new_id()
        return self.lists[n]

    def _broadcast_id(self, n):
        if n not in self.broadcasts: self.broadcasts[n] = new_id()
        return self.broadcasts[n]

    def _num_input(self, node, parent_id):
        return self._input(node, parent_id)

    def _menu_shadow(self, opcode, field_name, value, parent_id):
        mid = new_id()
        self.blocks[mid] = {"opcode": opcode, "next": None, "parent": parent_id,
                            "inputs": {}, "fields": {field_name: [value, None]},
                            "shadow": True, "topLevel": False}
        return mid

    _TERMINATORS = {"Forever", "Stop"}

    def _gen_seq(self, stmts, parent_id):
        if not stmts: return None
        first_id = None
        seg_start = 0
        while seg_start < len(stmts):
            seg_end = seg_start
            while seg_end < len(stmts) and stmts[seg_end]["type"] not in self._TERMINATORS:
                seg_end += 1
            if seg_end < len(stmts):
                seg_end += 1
            seg = stmts[seg_start:seg_end]
            if not seg:
                break
            ids = [new_id() for _ in seg]
            for i, stmt in enumerate(seg):
                par = parent_id if i == 0 else ids[i-1]
                is_term = stmt["type"] in self._TERMINATORS
                nxt = None if is_term else (ids[i+1] if i+1 < len(ids) else None)
                real = self.gen_stmt(stmt, par, nxt)
                if real != ids[i]:
                    self.blocks[ids[i]] = self.blocks.pop(real)
                    b = self.blocks[ids[i]]
                    for f in ("next", "parent"):
                        if b[f] == real: b[f] = ids[i]
                    for sb in self.blocks.values():
                        for f in ("next", "parent"):
                            if sb.get(f) == real: sb[f] = ids[i]
                        for inp in sb.get("inputs", {}).values():
                            if isinstance(inp, list) and len(inp) > 1 and inp[1] == real:
                                inp[1] = ids[i]
                    for c in self.comments.values():
                        if c.get("blockId") == real:
                            c["blockId"] = ids[i]
            if first_id is None:
                first_id = ids[0]
            seg_start = seg_end
        return first_id

    def gen_hat(self, event, x=0, y=0):
        bid = new_id(); t = event["type"]
        if t == "EventFlagClicked":
            self._add(bid, "event_whenflagclicked", None, None, top=True, x=x, y=y)
        elif t == "EventKeyPressed":
            self._add(bid, "event_whenkeypressed", None, None,
                      fields={"KEY_OPTION": [event["key"], None]}, top=True, x=x, y=y)
        elif t == "EventSpriteClicked":
            self._add(bid, "event_whenthisspriteclicked", None, None, top=True, x=x, y=y)
        elif t == "EventBackdropChanged":
            self._add(bid, "event_whenbackdropswitchesto", None, None,
                      fields={"BACKDROP": [event["backdrop"], None]}, top=True, x=x, y=y)
        elif t == "EventBroadcastReceived":
            bid2 = self._broadcast_id(event["message"])
            self._add(bid, "event_whenbroadcastreceived", None, None,
                      fields={"BROADCAST_OPTION": [event["message"], bid2]}, top=True, x=x, y=y)
        elif t == "EventCloneStarted":
            self._add(bid, "control_start_as_clone", None, None, top=True, x=x, y=y)
        elif t == "CustomDefHat":
            self._add(bid, "procedures_definition", None, None,
                      inputs={"custom_block": [1, event["proto_id"]]}, top=True, x=x, y=y)
        return bid

    def _expand_animate(self, node, parent_id, next_id):
        stmts = []
        for cname in node["costumes"]:
            stmts.append({"type": "SwitchCostume", "value": cname})
            stmts.append({"type": "Wait", "value": node["secs"]})
        return self._gen_seq(stmts, parent_id)

    def gen_stmt(self, node, parent_id, next_id):
        result_bid = self._gen_stmt_inner(node, parent_id, next_id)
        cmt = node.get("comment")
        if cmt and result_bid:
            self._attach_comment(result_bid, cmt)
        return result_bid

    def _gen_stmt_inner(self, node, parent_id, next_id):
        t = node["type"]; bid = new_id()

        if t == "Animate":
            first = self._expand_animate(node, parent_id, next_id)
            if first:
                cur = first
                while self.blocks[cur]["next"]:
                    cur = self.blocks[cur]["next"]
                self.blocks[cur]["next"] = next_id
            return first or bid

        if t == "VarDecl":
            inp      = self._input(node["value"], bid) if node["value"] else [1,[10,""]]
            var_name = node["name"]
            scope    = node.get("scope",   "public")
            display  = node.get("display", "shown")
            self._var_scope[var_name] = scope
            self._add(bid, "data_setvariableto", parent_id, next_id,
                inputs={"VALUE": inp},
                fields={"VARIABLE": [var_name, self._var_id(var_name)]})
            if display == "hidden":
                hide_id = new_id()
                self._add(hide_id, "data_hidevariable", bid, next_id,
                    fields={"VARIABLE": [var_name, self._var_id(var_name)]})
                self.blocks[bid]["next"] = hide_id
            return bid
        if t == "VarSet":
            self._add(bid, "data_setvariableto", parent_id, next_id,
                inputs={"VALUE": self._input(node["value"], bid)},
                fields={"VARIABLE": [node["name"], self._var_id(node["name"])]})
            return bid
        if t == "VarChange":
            if node.get("compound") in (None, "add"):
                self._add(bid, "data_changevariableby", parent_id, next_id,
                    inputs={"VALUE": self._input(node["value"], bid)},
                    fields={"VARIABLE": [node["name"], self._var_id(node["name"])]})
            else:
                op_m = {"sub":"-","mul":"*","div":"/"}
                inner = {"type":"BinOp","op":op_m[node["compound"]],
                         "left":{"type":"Var","name":node["name"]},"right":node["value"]}
                self._add(bid, "data_setvariableto", parent_id, next_id,
                    inputs={"VALUE": self._input(inner, bid)},
                    fields={"VARIABLE": [node["name"], self._var_id(node["name"])]})
            return bid
        if t == "ShowVar":
            self._add(bid, "data_showvariable", parent_id, next_id,
                fields={"VARIABLE": [node["value"], self._var_id(node["value"])]}); return bid
        if t == "HideVar":
            self._add(bid, "data_hidevariable", parent_id, next_id,
                fields={"VARIABLE": [node["value"], self._var_id(node["value"])]}); return bid
        if t == "ListAdd":
            self._add(bid, "data_addtolist", parent_id, next_id,
                inputs={"ITEM": self._input(node["item"], bid)},
                fields={"LIST": [node["list"], self._list_id(node["list"])]}); return bid
        if t == "ListDelete":
            self._add(bid, "data_deleteoflist", parent_id, next_id,
                inputs={"INDEX": self._input(node["index"], bid)},
                fields={"LIST": [node["list"], self._list_id(node["list"])]}); return bid
        if t == "ListInsert":
            self._add(bid, "data_insertatlist", parent_id, next_id,
                inputs={"INDEX": self._input(node["index"],bid),"ITEM": self._input(node["item"],bid)},
                fields={"LIST": [node["list"], self._list_id(node["list"])]}); return bid
        if t == "ListReplace":
            self._add(bid, "data_replaceitemoflist", parent_id, next_id,
                inputs={"INDEX": self._input(node["index"],bid),"ITEM": self._input(node["item"],bid)},
                fields={"LIST": [node["list"], self._list_id(node["list"])]}); return bid
        if t == "ShowList":
            self._add(bid, "data_showlist", parent_id, next_id,
                fields={"LIST": [node["value"], self._list_id(node["value"])]}); return bid
        if t == "HideList":
            self._add(bid, "data_hidelist", parent_id, next_id,
                fields={"LIST": [node["value"], self._list_id(node["value"])]}); return bid
        if t == "Repeat":
            inner = self._gen_seq(node["body"], bid)
            self._add(bid, "control_repeat", parent_id, next_id,
                inputs={"TIMES": self._input(node["times"], bid),
                        "SUBSTACK": [2, inner] if inner else {}}); return bid
        if t == "Forever":
            inner = self._gen_seq(node["body"], bid)
            self._add(bid, "control_forever", parent_id, None,
                inputs={"SUBSTACK": [2, inner] if inner else {}})
            return bid
        if t == "If":
            cond = self._bool_input(node["cond"], bid)
            then = self._gen_seq(node["then"], bid)
            if node["else"]:
                else_ = self._gen_seq(node["else"], bid)
                self._add(bid, "control_if_else", parent_id, next_id,
                    inputs={"CONDITION": cond,
                            "SUBSTACK":  [2, then]  if then  else {},
                            "SUBSTACK2": [2, else_] if else_ else {}})
            else:
                self._add(bid, "control_if", parent_id, next_id,
                    inputs={"CONDITION": cond, "SUBSTACK": [2, then] if then else {}})
            return bid
        if t == "RepeatUntil":
            cond = self._bool_input(node["cond"], bid); inner = self._gen_seq(node["body"], bid)
            self._add(bid, "control_repeat_until", parent_id, next_id,
                inputs={"CONDITION": cond, "SUBSTACK": [2, inner] if inner else {}}); return bid
        if t == "Wait":
            self._add(bid, "control_wait", parent_id, next_id,
                inputs={"DURATION": self._input(node["value"], bid)}); return bid
        if t == "WaitUntil":
            self._add(bid, "control_wait_until", parent_id, next_id,
                inputs={"CONDITION": self._bool_input(node["cond"], bid)}); return bid
        if t == "Stop":
            self._add(bid, "control_stop", parent_id, next_id,
                fields={"STOP_OPTION": [node["option"], None]},
                mutation={"tagName":"mutation","children":[],"hasnext":"false"}); return bid
        if t == "CreateClone":
            mid = self._menu_shadow("control_create_clone_of_menu","CLONE_OPTION",node["target"],bid)
            self._add(bid, "control_create_clone_of", parent_id, next_id,
                inputs={"CLONE_OPTION": [1, mid]}); return bid
        if t == "DeleteClone":
            self._add(bid, "control_delete_this_clone", parent_id, next_id); return bid
        if t == "Move":
            self._add(bid,"motion_movesteps",parent_id,next_id,inputs={"STEPS":self._num_input(node["value"],bid)}); return bid
        if t == "TurnLeft":
            self._add(bid,"motion_turnleft",parent_id,next_id,inputs={"DEGREES":self._num_input(node["value"],bid)}); return bid
        if t == "TurnRight":
            self._add(bid,"motion_turnright",parent_id,next_id,inputs={"DEGREES":self._num_input(node["value"],bid)}); return bid
        if t == "GoToXY":
            self._add(bid,"motion_gotoxy",parent_id,next_id,
                inputs={"X":self._num_input(node["x"],bid),"Y":self._num_input(node["y"],bid)}); return bid
        if t == "GoToSprite":
            mid = self._menu_shadow("motion_goto_menu","TO",node["value"],bid)
            self._add(bid,"motion_goto",parent_id,next_id,inputs={"TO":[1,mid]}); return bid
        if t == "Glide":
            self._add(bid,"motion_glidesecstoxy",parent_id,next_id,
                inputs={"SECS":self._num_input(node["secs"],bid),
                        "X":self._num_input(node["x"],bid),"Y":self._num_input(node["y"],bid)}); return bid
        if t == "GlideToSprite":
            mid = self._menu_shadow("motion_glideto_menu","TO",node["target"],bid)
            self._add(bid,"motion_glideto",parent_id,next_id,
                inputs={"SECS":self._num_input(node["secs"],bid),"TO":[1,mid]}); return bid
        if t == "PointDir":
            self._add(bid,"motion_pointindirection",parent_id,next_id,
                inputs={"DIRECTION":self._num_input(node["value"],bid)}); return bid
        if t == "PointTowards":
            mid = self._menu_shadow("motion_pointtowards_menu","TOWARDS",node["value"],bid)
            self._add(bid,"motion_pointtowards",parent_id,next_id,inputs={"TOWARDS":[1,mid]}); return bid
        if t == "SetX":
            self._add(bid,"motion_setx",parent_id,next_id,inputs={"X":self._num_input(node["value"],bid)}); return bid
        if t == "SetY":
            self._add(bid,"motion_sety",parent_id,next_id,inputs={"Y":self._num_input(node["value"],bid)}); return bid
        if t == "ChangeX":
            self._add(bid,"motion_changexby",parent_id,next_id,inputs={"DX":self._num_input(node["value"],bid)}); return bid
        if t == "ChangeY":
            self._add(bid,"motion_changeyby",parent_id,next_id,inputs={"DY":self._num_input(node["value"],bid)}); return bid
        if t == "BounceOnEdge":
            self._add(bid,"motion_ifonedgebounce",parent_id,next_id); return bid
        if t == "SetRotationStyle":
            self._add(bid,"motion_setrotationstyle",parent_id,next_id,
                fields={"STYLE":[node["value"],None]}); return bid
        if t == "Say":
            self._add(bid,"looks_say",parent_id,next_id,inputs={"MESSAGE":self._input(node["text"],bid)}); return bid
        if t == "SayFor":
            self._add(bid,"looks_sayforsecs",parent_id,next_id,
                inputs={"MESSAGE":self._input(node["text"],bid),"SECS":self._num_input(node["secs"],bid)}); return bid
        if t == "Think":
            self._add(bid,"looks_think",parent_id,next_id,inputs={"MESSAGE":self._input(node["text"],bid)}); return bid
        if t == "ThinkFor":
            self._add(bid,"looks_thinkforsecs",parent_id,next_id,
                inputs={"MESSAGE":self._input(node["text"],bid),"SECS":self._num_input(node["secs"],bid)}); return bid
        if t == "SwitchCostume":
            mid = self._menu_shadow("looks_costume","COSTUME",node["value"],bid)
            self._add(bid,"looks_switchcostumeto",parent_id,next_id,inputs={"COSTUME":[1,mid]}); return bid
        if t == "NextCostume":
            self._add(bid,"looks_nextcostume",parent_id,next_id); return bid
        if t == "SwitchBackdrop":
            mid = self._menu_shadow("looks_backdrops","BACKDROP",node["value"],bid)
            self._add(bid,"looks_switchbackdropto",parent_id,next_id,inputs={"BACKDROP":[1,mid]}); return bid
        if t == "NextBackdrop":
            self._add(bid,"looks_nextbackdrop",parent_id,next_id); return bid
        if t == "SetSize":
            self._add(bid,"looks_setsizeto",parent_id,next_id,inputs={"SIZE":self._num_input(node["value"],bid)}); return bid
        if t == "ChangeSize":
            self._add(bid,"looks_changesizeby",parent_id,next_id,inputs={"CHANGE":self._num_input(node["value"],bid)}); return bid
        if t == "Show":
            self._add(bid,"looks_show",parent_id,next_id); return bid
        if t == "Hide":
            self._add(bid,"looks_hide",parent_id,next_id); return bid
        if t == "GoToFront":
            self._add(bid,"looks_gotofrontback",parent_id,next_id,fields={"FRONT_BACK":["front",None]}); return bid
        if t == "GoToBack":
            self._add(bid,"looks_gotofrontback",parent_id,next_id,fields={"FRONT_BACK":["back",None]}); return bid
        if t == "GoForwardLayers":
            self._add(bid,"looks_goforwardbackwardlayers",parent_id,next_id,
                inputs={"NUM":self._num_input(node["value"],bid)},fields={"FORWARD_BACKWARD":["forward",None]}); return bid
        if t == "GoBackwardLayers":
            self._add(bid,"looks_goforwardbackwardlayers",parent_id,next_id,
                inputs={"NUM":self._num_input(node["value"],bid)},fields={"FORWARD_BACKWARD":["backward",None]}); return bid
        if t == "SetEffect":
            self._add(bid,"looks_seteffectto",parent_id,next_id,
                inputs={"VALUE":self._input(node["value"],bid)},
                fields={"EFFECT":[node["effect"].upper(),None]}); return bid
        if t == "ChangeEffect":
            self._add(bid,"looks_changeeffectby",parent_id,next_id,
                inputs={"CHANGE":self._num_input(node["value"],bid)},
                fields={"EFFECT":[node["effect"].upper(),None]}); return bid
        if t == "ClearEffects":
            self._add(bid,"looks_cleargraphiceffects",parent_id,next_id); return bid
        if t == "PlaySound":
            mid = self._menu_shadow("sound_sounds_menu","SOUND_MENU",node["value"],bid)
            self._add(bid,"sound_play",parent_id,next_id,inputs={"SOUND_MENU":[1,mid]}); return bid
        if t == "PlaySoundUntilDone":
            mid = self._menu_shadow("sound_sounds_menu","SOUND_MENU",node["value"],bid)
            self._add(bid,"sound_playuntildone",parent_id,next_id,inputs={"SOUND_MENU":[1,mid]}); return bid
        if t == "StopAllSounds":
            self._add(bid,"sound_stopallsounds",parent_id,next_id); return bid
        if t == "SetVolume":
            self._add(bid,"sound_setvolumeto",parent_id,next_id,inputs={"VOLUME":self._num_input(node["value"],bid)}); return bid
        if t == "ChangeVolume":
            self._add(bid,"sound_changevolumeby",parent_id,next_id,inputs={"CHANGE":self._num_input(node["value"],bid)}); return bid
        if t == "AskAndWait":
            self._add(bid,"sensing_askandwait",parent_id,next_id,
                inputs={"QUESTION":[1,[10,node["value"]]]}); return bid
        if t == "SetDragMode":
            self._add(bid,"sensing_setdragmode",parent_id,next_id,
                fields={"DRAG_MODE":[node["value"],None]}); return bid
        if t == "ResetTimer":
            self._add(bid,"sensing_resettimer",parent_id,next_id); return bid
        if t == "PenDown":
            self._add(bid,"pen_penDown",parent_id,next_id); return bid
        if t == "PenUp":
            self._add(bid,"pen_penUp",parent_id,next_id); return bid
        if t == "SetPenColor":
            self._add(bid,"pen_setPenColorToColor",parent_id,next_id,
                inputs={"COLOR":self._num_input(node["value"],bid)}); return bid
        if t == "ChangePenColor":
            self._add(bid,"pen_changePenColorBy",parent_id,next_id,
                inputs={"COLOR":self._num_input(node["value"],bid)}); return bid
        if t == "SetPenSize":
            self._add(bid,"pen_setPenSizeTo",parent_id,next_id,
                inputs={"SIZE":self._num_input(node["value"],bid)}); return bid
        if t == "ChangePenSize":
            self._add(bid,"pen_changePenSizeBy",parent_id,next_id,
                inputs={"SIZE":self._num_input(node["value"],bid)}); return bid
        if t == "StampPen":
            self._add(bid,"pen_stamp",parent_id,next_id); return bid
        if t == "ErasePen":
            self._add(bid,"pen_clear",parent_id,next_id); return bid
        if t == "Broadcast":
            mid = self._broadcast_id(node["value"])
            self._add(bid,"event_broadcast",parent_id,next_id,
                inputs={"BROADCAST_INPUT":[1,[11,node["value"],mid]]}); return bid
        if t == "BroadcastAndWait":
            mid = self._broadcast_id(node["value"])
            self._add(bid,"event_broadcastandwait",parent_id,next_id,
                inputs={"BROADCAST_INPUT":[1,[11,node["value"],mid]]}); return bid
        # ── Music extension ────────────────────────────
        if t == "MusicPlayDrum":
            dmid = self._menu_shadow("music_menu_DRUM","DRUM",
                str(int(node["a"]["value"]) if node["a"]["type"]=="Num" else 1), bid)
            self._add(bid,"music_playDrumForBeats",parent_id,next_id,
                inputs={"DRUM":[1,dmid],"BEATS":self._num_input(node["b"],bid)}); return bid
        if t == "MusicRestForBeats":
            self._add(bid,"music_restForBeats",parent_id,next_id,
                inputs={"BEATS":self._num_input(node["value"],bid)}); return bid
        if t == "MusicPlayNote":
            nmid = self._menu_shadow("note","NOTE",
                str(int(node["a"]["value"]) if node["a"]["type"]=="Num" else 60), bid)
            self._add(bid,"music_playNoteForBeats",parent_id,next_id,
                inputs={"NOTE":[1,nmid],"BEATS":self._num_input(node["b"],bid)}); return bid
        if t == "MusicSetInstrument":
            imid = self._menu_shadow("music_menu_INSTRUMENT","INSTRUMENT",
                str(int(node["value"]["value"]) if node["value"]["type"]=="Num" else 1), bid)
            self._add(bid,"music_setInstrument",parent_id,next_id,
                inputs={"INSTRUMENT":[1,imid]}); return bid
        if t == "MusicSetTempo":
            self._add(bid,"music_setTempo",parent_id,next_id,
                inputs={"TEMPO":self._num_input(node["value"],bid)}); return bid
        if t == "MusicChangeTempo":
            self._add(bid,"music_changeTempo",parent_id,next_id,
                inputs={"TEMPO":self._num_input(node["value"],bid)}); return bid
        # ── Video extension ────────────────────────────
        if t == "VideoSetTransparency":
            self._add(bid,"videoSensing_setVideoTransparency",parent_id,next_id,
                inputs={"TRANSPARENCY":self._num_input(node["value"],bid)}); return bid
        if t == "VideoOn":
            mid = self._menu_shadow("videoSensing_menu_VIDEO_STATE","VIDEO_STATE","on",bid)
            self._add(bid,"videoSensing_videoToggle",parent_id,next_id,
                inputs={"VIDEO_STATE":[1,mid]}); return bid
        if t == "VideoOff":
            mid = self._menu_shadow("videoSensing_menu_VIDEO_STATE","VIDEO_STATE","off",bid)
            self._add(bid,"videoSensing_videoToggle",parent_id,next_id,
                inputs={"VIDEO_STATE":[1,mid]}); return bid
        if t == "VideoFlipped":
            mid = self._menu_shadow("videoSensing_menu_VIDEO_STATE","VIDEO_STATE","on-flipped",bid)
            self._add(bid,"videoSensing_videoToggle",parent_id,next_id,
                inputs={"VIDEO_STATE":[1,mid]}); return bid
        # ── Text2Speech extension ──────────────────────
        if t == "TtsSpeakAndWait":
            self._add(bid,"text2speech_speakAndWait",parent_id,next_id,
                inputs={"WORDS":self._input(node["value"],bid)}); return bid
        if t == "TtsSetVoice":
            mid = self._menu_shadow("text2speech_menu_voices","VOICE",node["value"],bid)
            self._add(bid,"text2speech_setVoice",parent_id,next_id,
                inputs={"VOICE":[1,mid]}); return bid
        if t == "TtsSetLanguage":
            mid = self._menu_shadow("text2speech_menu_languages","LANGUAGE",node["value"],bid)
            self._add(bid,"text2speech_setLanguage",parent_id,next_id,
                inputs={"LANGUAGE":[1,mid]}); return bid
        if t == "CustomCall":
            proccode = self.custom_procs.get(node["name"],
                           node["name"]+" "+" ".join(["%s"]*len(node["args"])))
            arg_ids = self.custom_arg_ids.get(node["name"], [])
            if len(arg_ids) != len(node["args"]):
                arg_ids = [new_id() for _ in node["args"]]
            inputs = {aid: self._input(arg, bid) for aid, arg in zip(arg_ids, node["args"])}
            mutation = {"tagName":"mutation","children":[],"proccode":proccode,
                        "argumentids":json.dumps(arg_ids),"warp":"false"}
            self._add(bid,"procedures_call",parent_id,next_id,inputs=inputs,mutation=mutation)
            return bid

        raise ValueError(f"Unbekannter Statement-Typ: {t!r}")

    def gen_expr(self, node, parent_id):
        bid = new_id(); t = node["type"]
        if t == "Num":
            v = node["value"]
            s = str(int(v) if isinstance(v,float) and v.is_integer() else v)
            self._add(bid,"math_number",parent_id,None,fields={"NUM":[s,None]})
            self.blocks[bid]["shadow"] = True; return bid
        if t == "Str":
            self._add(bid,"text",parent_id,None,fields={"TEXT":[node["value"],None]})
            self.blocks[bid]["shadow"] = True; return bid
        if t == "Bool":
            a, b = ("1", "1") if node["value"] else ("1", "0")
            self._add(bid, "operator_equals", parent_id, None,
                inputs={"OPERAND1": [1, [10, a]], "OPERAND2": [1, [10, b]]})
            return bid
        if t == "Var":
            name = node["name"]
            if name in self.current_params:
                _, ptype = self.current_params[name]
                opcode = ("argument_reporter_boolean"
                          if ptype == "%b"
                          else "argument_reporter_string_number")
                self._add(bid, opcode, parent_id, None,
                          fields={"VALUE": [name, None]})
                self.blocks[bid]["shadow"] = False
                self.blocks[bid]["topLevel"] = False
                return bid
            vid = self._var_id(name)
            self._add(bid,"data_variable",parent_id,None,
                fields={"VARIABLE":[name,vid]}); return bid
        if t == "MotionVal":
            op = {"xPosition":"motion_xposition","yPosition":"motion_yposition",
                  "direction":"motion_direction"}[node["val"]]
            self._add(bid,op,parent_id,None); return bid
        if t == "BinOp":
            op = node["op"]
            op_map = {"+":"operator_add","-":"operator_subtract","*":"operator_multiply",
                      "/":"operator_divide","%":"operator_mod","<":"operator_lt",
                      ">":"operator_gt","==":"operator_equals","&&":"operator_and","||":"operator_or"}
            l = self._input(node["left"],bid); r = self._input(node["right"],bid)
            if op == "!=":
                eq = new_id()
                self._add(eq,"operator_equals",bid,None,inputs={"OPERAND1":l,"OPERAND2":r})
                self._add(bid,"operator_not",parent_id,None,inputs={"OPERAND":[2,eq]}); return bid
            if op in ("&&","||"):
                self._add(bid,op_map[op],parent_id,None,inputs={"OPERAND1":l,"OPERAND2":r})
            elif op in ("+","-","*","/","%"):
                self._add(bid,op_map[op],parent_id,None,inputs={"NUM1":l,"NUM2":r})
            else:
                self._add(bid,op_map[op],parent_id,None,inputs={"OPERAND1":l,"OPERAND2":r})
            return bid
        if t == "UnaryOp":
            if node["op"] == "!":
                self._add(bid,"operator_not",parent_id,None,
                    inputs={"OPERAND":self._bool_input(node["operand"],bid)}); return bid
            self._add(bid,"operator_subtract",parent_id,None,
                inputs={"NUM1":[1,[4,"0"]],"NUM2":self._num_input(node["operand"],bid)}); return bid
        if t == "Random":
            self._add(bid,"operator_random",parent_id,None,
                inputs={"FROM":self._num_input(node["from"],bid),"TO":self._num_input(node["to"],bid)}); return bid
        if t == "Round":
            self._add(bid,"operator_round",parent_id,None,
                inputs={"NUM":self._num_input(node["value"],bid)}); return bid
        if t == "MathOp":
            self._add(bid,"operator_mathop",parent_id,None,
                inputs={"NUM":self._num_input(node["value"],bid)},
                fields={"OPERATOR":[node["op"],None]}); return bid
        if t == "StrLength":
            self._add(bid,"operator_length",parent_id,None,
                inputs={"STRING":self._input(node["value"],bid)}); return bid
        if t == "LetterOf":
            self._add(bid,"operator_letter_of",parent_id,None,
                inputs={"LETTER":self._input(node["n"],bid),"STRING":self._input(node["str"],bid)}); return bid
        if t == "StrContains":
            self._add(bid,"operator_contains",parent_id,None,
                inputs={"STRING1":self._input(node["str"],bid),"STRING2":self._input(node["sub"],bid)}); return bid
        if t == "Join":
            self._add(bid,"operator_join",parent_id,None,
                inputs={"STRING1":self._input(node["a"],bid),"STRING2":self._input(node["b"],bid)}); return bid
        if t == "Sensing":
            sm = {"answer":("sensing_answer",{}),"mouseX":("sensing_mousex",{}),"mouseY":("sensing_mousey",{}),
                  "mouseDown":("sensing_mousedown",{}),"timer":("sensing_timer",{}),
                  "loudness":("sensing_loudness",{}),"username":("sensing_username",{})}
            opcode, fields = sm[node["sense"]]
            self._add(bid,opcode,parent_id,None,fields=fields); return bid
        if t == "CurrentDate":
            self._add(bid,"sensing_current",parent_id,None,
                fields={"CURRENTMENU":[node["field"],None]}); return bid
        if t == "KeyPressed":
            mid = self._menu_shadow("sensing_keyoptions","KEY_OPTION",node["key"],bid)
            self._add(bid,"sensing_keypressed",parent_id,None,
                inputs={"KEY_OPTION":[1,mid]}); return bid
        if t == "Touching":
            mid = self._menu_shadow("sensing_touchingobjectmenu","TOUCHINGOBJECTMENU",node["target"],bid)
            self._add(bid,"sensing_touchingobject",parent_id,None,
                inputs={"TOUCHINGOBJECTMENU":[1,mid]}); return bid
        if t == "TouchingColor":
            self._add(bid,"sensing_touchingcolor",parent_id,None,
                inputs={"COLOR":self._num_input(node["color"],bid)}); return bid
        if t == "DistanceTo":
            mid = self._menu_shadow("sensing_distancetomenu","DISTANCETOMENU",node["target"],bid)
            self._add(bid,"sensing_distanceto",parent_id,None,
                inputs={"DISTANCETOMENU":[1,mid]}); return bid
        if t == "ListItem":
            self._add(bid,"data_itemoflist",parent_id,None,
                inputs={"INDEX":self._input(node["index"],bid)},
                fields={"LIST":[node["list"],self._list_id(node["list"])]}); return bid
        if t == "ListLength":
            self._add(bid,"data_lengthoflist",parent_id,None,
                fields={"LIST":[node["list"],self._list_id(node["list"])]}); return bid
        if t == "ListContains":
            self._add(bid,"data_listcontainsitem",parent_id,None,
                inputs={"ITEM":self._input(node["item"],bid)},
                fields={"LIST":[node["list"],self._list_id(node["list"])]}); return bid
        # ── Music reporter ─────────────────────────────
        if t == "MusicGetTempo":
            self._add(bid,"music_getTempo",parent_id,None); return bid
        # ── Translate reporter ─────────────────────────
        if t == "TranslateGetTranslate":
            lang_mid = self._menu_shadow("translate_menu_languages","LANGUAGE",
                node["language"]["value"] if node["language"]["type"]=="Str" else "en", bid)
            self._add(bid,"translate_getTranslate",parent_id,None,
                inputs={"WORDS":self._input(node["words"],bid),
                        "LANGUAGE":[1,lang_mid]}); return bid
        if t == "TtsViewerLanguage":
            self._add(bid,"translate_getViewerLanguage",parent_id,None); return bid
        # ── Video reporters ─────────────────────────────
        if t == "VideoSensingMotion":
            attr = node.get("attribute","motion")
            attr_mid = self._menu_shadow("videoSensing_menu_ATTRIBUTE","ATTRIBUTE",attr,bid)
            subj_raw = node["subject"]["value"] if node["subject"]["type"]=="Str" else "this sprite"
            subj_mid = self._menu_shadow("videoSensing_menu_SUBJECT","SUBJECT",subj_raw,bid)
            self._add(bid,"videoSensing_videoOn",parent_id,None,
                inputs={"ATTRIBUTE":[1,attr_mid],"SUBJECT":[1,subj_mid]}); return bid
        raise ValueError(f"Unbekannter Ausdrucks-Typ: {t!r}")

    def gen_custom_def(self, cdef, x=0, y=0):
        raw_params = cdef["params"]
        if raw_params and isinstance(raw_params[0], str):
            params = [(p, "%s") for p in raw_params]
        else:
            params = raw_params

        param_names = [p[0] for p in params]
        param_types = [p[1] for p in params]
        param_ids   = [new_id() for _ in params]

        proccode = cdef["name"] + "".join(f" {tc}" for tc in param_types)
        warp     = str(self.custom_warp.get(cdef["name"], False)).lower()
        self.custom_procs[cdef["name"]] = proccode

        REPORTER_OPCODE = {
            "%s": "argument_reporter_string_number",
            "%n": "argument_reporter_string_number",
            "%b": "argument_reporter_boolean",
        }
        DEFAULT_VAL = {"%s": "", "%n": "0", "%b": "false"}

        proto_id     = new_id()
        proto_inputs = {}
        for pid, pname, ptype in zip(param_ids, param_names, param_types):
            ab = new_id()
            self.blocks[ab] = {
                "opcode":  REPORTER_OPCODE[ptype],
                "next":    None, "parent": proto_id,
                "inputs":  {}, "fields": {"VALUE": [pname, None]},
                "shadow":  True, "topLevel": False,
            }
            proto_inputs[pid] = [1, ab]

        self.blocks[proto_id] = {
            "opcode": "procedures_prototype", "next": None, "parent": None,
            "inputs": proto_inputs, "fields": {}, "shadow": True, "topLevel": False,
            "mutation": {
                "tagName": "mutation", "children": [], "proccode": proccode,
                "argumentids":      json.dumps(param_ids),
                "argumentnames":    json.dumps(param_names),
                "argumentdefaults": json.dumps([DEFAULT_VAL[t] for t in param_types]),
                "warp": warp,
            },
        }

        hat_id = new_id()
        self._add(hat_id, "procedures_definition", None, None,
                  inputs={"custom_block": [1, proto_id]}, top=True, x=x, y=y)
        self.blocks[proto_id]["parent"] = hat_id
        self.custom_arg_ids[cdef["name"]] = list(param_ids)

        old_params = self.current_params
        self.current_params = {
            pname: (pid, ptype)
            for pname, pid, ptype in zip(param_names, param_ids, param_types)
        }
        first = self._gen_seq(cdef["body"], hat_id)
        self.current_params = old_params

        self.blocks[hat_id]["next"] = first
        return hat_id

    def gen_target(self, target_node):
        self.blocks = {}; self.variables = {}; self.lists = {}
        self.broadcasts = {}; self.comments = {}; self.custom_procs = {}; self.custom_arg_ids = {}
        self.current_params = {}; self._var_scope = {}
        self.custom_warp = {
            cdef["name"]: cdef.get("warp", False)
            for cdef in target_node.get("customDefs", [])
        }
        for cdef in target_node.get("customDefs", []):
            raw = cdef["params"]
            if raw and isinstance(raw[0], str):
                types = ["%s"] * len(raw)
            else:
                types = [p[1] for p in raw]
            self.custom_procs[cdef["name"]] = cdef["name"] + "".join(f" {t}" for t in types)
        x_off = 0
        for cdef in target_node.get("customDefs",[]):
            self.gen_custom_def(cdef, x=x_off, y=-300); x_off += 300
        x_off = 0
        for script in target_node.get("scripts",[]):
            hat_id = self.gen_hat(script["event"], x=x_off, y=0)
            first  = self._gen_seq(script["body"], hat_id)
            self.blocks[hat_id]["next"] = first
            x_off += 300
        return self.blocks, self.variables, self.lists, self.broadcasts, self._var_scope, self.comments


# ═══════════════════════════════════════════════════════
#  4.  project.json Zusammenbau
# ═══════════════════════════════════════════════════════
def build_project(ast: dict, asset_mgr: AssetManager) -> dict:
    gen = BlockGenerator(); targets = []; all_broadcasts = {}

    stage_node = next((t for t in ast["targets"] if t["type"]=="Stage"), None)
    stage_blocks, stage_vars, stage_lists = {}, {}, {}
    if stage_node:
        print(f"  Stage '{stage_node['name']}':")
        stage_blocks, stage_vars, stage_lists, bcast, _, stage_comments = gen.gen_target(stage_node)
        all_broadcasts.update(bcast)
        backdrops = []
        for bd in stage_node.get("backdrops",[]):
            print(f"    Hintergrund '{bd['name']}'" + (f" ← {bd['path']}" if bd["path"] else ""))
            backdrops.append(asset_mgr.load_backdrop(bd["path"], bd["name"]))
        if not backdrops: backdrops.append(asset_mgr.load_backdrop(None, "Hintergrund1"))
        sounds = [asset_mgr.load_sound(s["path"], s["name"]) for s in stage_node.get("sounds",[])]
    else:
        backdrops = [asset_mgr.load_backdrop(None, "Hintergrund1")]; sounds = []

    stage_target = {
        "isStage":True,"name":"Stage",
        "variables":{vid:[name,0] for name,vid in stage_vars.items()},
        "lists":    {lid:[name,[]] for name,lid in stage_lists.items()},
        "broadcasts":{},"blocks":stage_blocks,"comments":stage_comments,"currentCostume":0,
        "costumes":backdrops,"sounds":sounds,"layerOrder":0,"tempo":60,"volume":100,
        "videoTransparency":50,"videoState":"on","textToSpeechLanguage":None,
    }
    targets.append(stage_target)

    for i, snode in enumerate([t for t in ast["targets"] if t["type"]=="Sprite"]):
        print(f"  Sprite '{snode['name']}':")
        blocks, variables, lists, bcast, var_scope, sprite_comments = gen.gen_target(snode)
        all_broadcasts.update(bcast)

        sprite_vars = {}
        for var_name, vid in variables.items():
            scope = var_scope.get(var_name, "public")
            if scope == "private":
                sprite_vars[vid] = [var_name, 0]
                print(f"    var '{var_name}': private (Sprite-lokal)")
            else:
                stage_target["variables"][vid] = [var_name, 0]
                print(f"    var '{var_name}': public (global/Stage)")

        costumes = []
        for c in snode.get("costumes",[]):
            print(f"    Kostüm '{c['name']}'" + (f" ← {c['path']}" if c["path"] else ""))
            costumes.append(asset_mgr.load_image(c["path"], c["name"]))
        if not costumes: costumes.append(asset_mgr.load_image(None, "Kostüm1"))
        sounds = [asset_mgr.load_sound(s["path"], s["name"]) for s in snode.get("sounds",[])]
        targets.append({
            "isStage":False,"name":snode["name"],
            "variables":sprite_vars,
            "lists":    {lid:[name,[]] for name,lid in lists.items()},
            "broadcasts":{},"blocks":blocks,"comments":sprite_comments,"currentCostume":0,
            "costumes":costumes,"sounds":sounds,"layerOrder":i+1,
            "visible":True,"x":0,"y":0,"size":100,"direction":90,
            "draggable":False,"rotationStyle":"all around",
        })

    targets[0]["broadcasts"] = {bid:name for name,bid in all_broadcasts.items()}

    extensions = list(ast.get("extensions", []))
    _EXT_PREFIXES = {
        "pen_":               "pen",
        "music_":             "music",
        "videoSensing_":      "videoSensing",
        "text2speech_":       "text2speech",
        "translate_":         "translate",
        "makeymakey_":        "makeymakey",
        "microbit_":          "microbit",
        "ev3_":               "ev3",
        "boost_":             "boost",
        "wedo2_":             "wedo2",
        "gdxfor_":            "gdxfor",
    }
    for prefix, ext_id in _EXT_PREFIXES.items():
        if ext_id not in extensions:
            if any(any(b.get("opcode","").startswith(prefix)
                       for b in t["blocks"].values()) for t in targets):
                extensions.append(ext_id)

    return {"targets":targets,"monitors":[],"extensions":extensions,
            "meta":{"semver":"3.0.0","vm":"0.2.0","agent":"scrape-transpiler/5.2"}}


def write_sb3(project: dict, asset_mgr: AssetManager, path: str):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.json", json.dumps(project, indent=2, ensure_ascii=False))
        for filename, data in asset_mgr.all_files().items():
            zf.writestr(filename, data)
    print(f"  {len(asset_mgr.all_files())} Asset-Datei(en) eingepackt")


# ═══════════════════════════════════════════════════════
#  5.  VALIDATOR
# ═══════════════════════════════════════════════════════
class Validator:
    VALID_EFFECTS       = {"color","fisheye","whirl","pixelate","mosaic","brightness","ghost"}
    VALID_ROTATION      = {"all around","left-right","don't rotate"}
    VALID_STOP          = {"all","this script","other scripts in sprite"}
    VALID_DRAG          = {"draggable","not draggable"}

    def __init__(self, ast, library):
        self.ast = ast; self.library = library
        self.errors: list[str] = []; self.warnings: list[str] = []

    def validate(self) -> bool:
        sprite_names = {t["name"] for t in self.ast["targets"]}
        for target in self.ast["targets"]:
            ctx = f"{'Stage' if target['type']=='Stage' else 'Sprite'} '{target['name']}'"
            costume_names = {c["name"] for c in target.get("costumes",[])}
            sound_names   = {s["name"] for s in target.get("sounds",[])}
            for c in target.get("costumes",[]) + target.get("backdrops",[]):
                if not c.get("path") and self.library:
                    kind = "backdrops" if target["type"]=="Stage" else "costumes"
                    if c["name"].lower() not in self.library.get(kind,{}):
                        self.warnings.append(
                            f"{ctx}: Kostüm/Hintergrund '{c['name']}' nicht in Bibliothek – Platzhalter.")
            for s in target.get("sounds",[]):
                if not s.get("path") and self.library:
                    if s["name"].lower() not in self.library.get("sounds",{}):
                        self.warnings.append(f"{ctx}: Sound '{s['name']}' nicht in Bibliothek – Stille.")
            for script in target.get("scripts",[]):
                self._stmts(script["body"], ctx, costume_names, sound_names, sprite_names, target)
            for cdef in target.get("customDefs",[]):
                self._stmts(cdef["body"], f"{ctx} define {cdef['name']}",
                            costume_names, sound_names, sprite_names, target)
        return len(self.errors) == 0

    def _stmts(self, stmts, ctx, cn, sn, sp, target):
        for s in stmts: self._stmt(s, ctx, cn, sn, sp, target)

    def _stmt(self, node, ctx, cn, sn, sp, target):
        t = node["type"]
        if t == "SwitchCostume" and cn and node["value"] not in cn:
            self.warnings.append(f"{ctx}: switchCostume(\"{node['value']}\") – Kostüm nicht gefunden (wird zur Laufzeit ignoriert). Vorhanden: {sorted(cn)}")
        elif t in ("PlaySound","PlaySoundUntilDone") and sn and node["value"] not in sn:
            self.warnings.append(f"{ctx}: playSound(\"{node['value']}\") – Sound nicht gefunden (wird zur Laufzeit ignoriert). Vorhanden: {sorted(sn)}")
        elif t in ("SetEffect","ChangeEffect") and node["effect"].lower() not in self.VALID_EFFECTS:
            self.errors.append(f"{ctx}: setEffect(\"{node['effect']}\") – ungültig. Gültig: {sorted(self.VALID_EFFECTS)}")
        elif t == "SetRotationStyle" and node["value"] not in self.VALID_ROTATION:
            self.errors.append(f"{ctx}: setRotationStyle(\"{node['value']}\") – Gültig: {sorted(self.VALID_ROTATION)}")
        elif t == "Stop" and node["option"] not in self.VALID_STOP:
            self.errors.append(f"{ctx}: stop(\"{node['option']}\") – Gültig: {sorted(self.VALID_STOP)}")
        elif t == "SetDragMode" and node["value"] not in self.VALID_DRAG:
            self.errors.append(f"{ctx}: setDragMode(\"{node['value']}\") – Gültig: {sorted(self.VALID_DRAG)}")
        elif t == "SetVolume": self._range(node["value"], ctx, "setVolume", 0, 100)
        elif t == "GoToSprite" and node["value"] not in ("_mouse_","_random_") and node["value"] not in sp:
            self.warnings.append(f"{ctx}: Sprite '{node['value']}' nicht definiert.")
        elif t == "CreateClone" and node["target"] != "_myself_" and node["target"] not in sp:
            self.errors.append(f"{ctx}: createClone(\"{node['target']}\") – Sprite nicht gefunden.")
        elif t == "CustomCall":
            defined = {cd["name"] for cd in target.get("customDefs",[])}
            if node["name"] not in defined:
                self.errors.append(f"{ctx}: {node['name']}() – nicht definiert. Definiert: {sorted(defined) or '(keine)'}")
            else:
                cdef = next(cd for cd in target["customDefs"] if cd["name"]==node["name"])
                raw = cdef["params"]
                params = raw if raw and not isinstance(raw[0], str) else [(p,"%s") for p in raw]
                if len(node["args"]) != len(params):
                    self.errors.append(f"{ctx}: {node['name']}() – {len(params)} Arg(e) erwartet, {len(node['args'])} gegeben.")
        elif t == "Animate" and cn:
            for cname in node["costumes"]:
                if cname not in cn:
                    self.warnings.append(f"{ctx}: animate() – Kostüm '{cname}' nicht gefunden (wird zur Laufzeit ignoriert). Vorhanden: {sorted(cn)}")
        for sub in ("body","then","else"):
            if node.get(sub): self._stmts(node[sub], ctx, cn, sn, sp, target)

    def _range(self, expr, ctx, name, lo, hi):
        if expr and expr.get("type") == "Num":
            v = expr["value"]
            if lo is not None and v < lo: self.warnings.append(f"{ctx}: {name}({v}) unter Minimum ({lo}).")
            if hi is not None and v > hi: self.warnings.append(f"{ctx}: {name}({v}) über Maximum ({hi}).")

    _VALIDATOR_FIXES: dict[str, str] = {
        "switchCostume":    "Kostüm mit addCostume() im selben Sprite definieren.",
        "playSound":        "Sound mit addSound() im selben Sprite definieren.",
        "playSoundUntilDone": "Sound mit addSound() im selben Sprite definieren.",
        "setEffect":        'Gültige Effekte: "color", "fisheye", "whirl", "pixelate", "mosaic", "brightness", "ghost"',
        "changeEffect":     'Gültige Effekte: "color", "fisheye", "whirl", "pixelate", "mosaic", "brightness", "ghost"',
        "setRotationStyle": 'Gültige Werte: "all around", "left-right", "don\'t rotate"',
        "stop":             'Gültige Werte: "all", "this script", "other scripts in sprite"',
        "setDragMode":      'Gültige Werte: "draggable", "not draggable"',
        "createClone":      'Sprite-Name prüfen oder "_myself_" für sich selbst verwenden.',
        "animate":          "Kostüm mit addCostume() im selben Sprite definieren.",
        "nicht definiert":  "Funktion mit 'void name() {}' oder 'define name() {}' definieren.",
        "Arg":              "Anzahl der Argumente im Aufruf und in der Definition angleichen.",
    }

    def _fix_for_error(self, msg: str) -> str:
        for key, hint in self._VALIDATOR_FIXES.items():
            if key in msg:
                return hint
        return ""

    def print_report(self):
        if not self.errors and not self.warnings:
            print("    ✓ Keine Probleme gefunden.")
            return
        if self.warnings:
            print(f"\n    ⚠  {len(self.warnings)} Warnung(en):")
            for w in self.warnings:
                print(f"       ⚠  {w}")
        if self.errors:
            print(f"\n    ✗  {len(self.errors)} Fehler:")
            for i, e in enumerate(self.errors, 1):
                prefix = f"    [{i}]" if len(self.errors) > 1 else "    ✗ "
                print(f"{prefix} {e}")
                fix = self._fix_for_error(e)
                if fix:
                    print(f"           💡 Fix: {fix}")


# ═══════════════════════════════════════════════════════
#  6.  APP LAUNCHER  (TurboWarp + Desktop-Player)
# ═══════════════════════════════════════════════════════

APP_PROFILES = {
    "turbowarp": {
        "label": "TurboWarp",
        "download": "https://turbowarp.org/desktop",
        "Windows": {
            "candidates": [
                str(Path.home()/"AppData/Local/Programs/TurboWarp/TurboWarp Desktop.exe"),
                str(Path.home()/"AppData/Local/Programs/TurboWarp/TurboWarp.exe"),
                str(Path.home()/"AppData/Local/Programs/turbowarp-desktop/TurboWarp Desktop.exe"),
                str(Path.home()/"AppData/Local/Programs/turbowarp-desktop/TurboWarp.exe"),
                r"C:\Program Files\TurboWarp\TurboWarp Desktop.exe",
                r"C:\Program Files\TurboWarp\TurboWarp.exe",
                r"C:\Program Files (x86)\TurboWarp\TurboWarp Desktop.exe",
            ],
            "kill": "TurboWarp Desktop.exe",
            "launch": lambda exe, f: [exe, f],
        },
        "Darwin": {
            "candidates": [
                "/Applications/TurboWarp.app/Contents/MacOS/TurboWarp",
                str(Path.home()/"Applications/TurboWarp.app/Contents/MacOS/TurboWarp"),
            ],
            "kill": "TurboWarp",
            "launch": lambda exe, f: ["open", "-n", "-a", "TurboWarp", "--args", f],
        },
        "Linux": {
            "candidates": [
                "/usr/bin/turbowarp-desktop",
                "/usr/local/bin/turbowarp-desktop",
                str(Path.home()/".local/bin/turbowarp-desktop"),
                "/snap/bin/turbowarp-desktop",
            ],
            "kill": "turbowarp-desktop",
            "launch": lambda exe, f: [exe, f],
        },
    },
    "scratch": {
        "label": "Desktop-Player",
        "download": "https://scratch.mit.edu/download",
        "Windows": {
            "candidates": [
                r"C:\Program Files\Scratch Desktop\Scratch Desktop.exe",
                r"C:\Program Files (x86)\Scratch Desktop\Scratch Desktop.exe",
                str(Path.home()/"AppData/Local/Programs/scratch-desktop/Scratch Desktop.exe"),
                str(Path.home()/"AppData/Local/Scratch Desktop/Scratch Desktop.exe"),
            ],
            "kill": "Scratch Desktop.exe",
            "launch": lambda exe, f: [exe, f],
        },
        "Darwin": {
            "candidates": [
                "/Applications/Scratch Desktop.app/Contents/MacOS/Scratch Desktop",
                str(Path.home()/"Applications/Scratch Desktop.app/Contents/MacOS/Scratch Desktop"),
            ],
            "kill": "Scratch Desktop",
            "launch": lambda exe, f: ["open", "-n", "-a", "Scratch Desktop", "--args", f],
        },
        "Linux": {
            "candidates": [
                "/usr/bin/scratch-desktop",
                "/usr/local/bin/scratch-desktop",
                str(Path.home()/".local/bin/scratch-desktop"),
                "/snap/bin/scratch-desktop",
            ],
            "kill": "scratch-desktop",
            "launch": lambda exe, f: [exe, f],
        },
    },
}

_WIN_STATE_FILE = Path.home() / ".scrape_transpiler_winstate.json"

def _load_win_states() -> dict:
    try:
        return json.loads(_WIN_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_win_states(states: dict):
    try:
        _WIN_STATE_FILE.write_text(json.dumps(states, indent=2), encoding="utf-8")
    except Exception:
        pass

def _get_window_geometry_windows(process_name: str) -> dict | None:
    result = _windows_find_window(process_name)
    return result[2] if result else None

def _get_window_geometry_macos(app_name: str) -> dict | None:
    script = f"""
tell application "System Events"
    set p to first process whose displayed name contains "{app_name}"
    set w to first window of p
    set b to bounds of w
    return (item 1 of b) & "," & (item 2 of b) & "," & ((item 3 of b) - (item 1 of b)) & "," & ((item 4 of b) - (item 2 of b))
end tell
"""
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=6)
        line = result.stdout.strip()
        if not line: return None
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4: return None
        x, y, w, h = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
        if w < 200 or h < 200: return None
        return {"x": x, "y": y, "w": w, "h": h, "maximized": False}
    except Exception:
        return None

def _get_window_geometry_linux(process_name: str) -> dict | None:
    try:
        find = subprocess.run(["xdotool","search","--name",process_name], capture_output=True, text=True, timeout=4)
        wids = find.stdout.strip().split()
        if not wids:
            find2 = subprocess.run(["xdotool","search","--class",process_name], capture_output=True, text=True, timeout=4)
            wids = find2.stdout.strip().split()
        if not wids: return None
        wid = wids[0]
        geo = subprocess.run(["xdotool","getwindowgeometry","--shell",wid], capture_output=True, text=True, timeout=4)
        vals = {}
        for line in geo.stdout.strip().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1); vals[k.strip()] = v.strip()
        x=int(vals.get("X",0)); y=int(vals.get("Y",0)); w=int(vals.get("WIDTH",0)); h=int(vals.get("HEIGHT",0))
        if w < 200 or h < 200: return None
        return {"x": x, "y": y, "w": w, "h": h, "maximized": False}
    except Exception:
        return None

def save_window_state(app: str, process_name: str):
    system = platform.system(); geo = None
    if system == "Windows":
        geo = _get_window_geometry_windows(process_name)
    elif system == "Darwin":
        label = APP_PROFILES[app]["label"]
        geo = _get_window_geometry_macos(label)
    else:
        geo = _get_window_geometry_linux(process_name)
    if geo:
        states = _load_win_states(); states[app] = geo; _save_win_states(states)
        pos = "maximiert" if geo.get("maximized") else f"{geo['x']},{geo['y']}  {geo['w']}×{geo['h']}"
        print(f"  💾  Fensterposition gespeichert ({pos})")
    else:
        print(f"  ℹ  Fensterposition konnte nicht ausgelesen werden")

def restore_window_state(app: str, process_name: str):
    import threading
    states = _load_win_states(); geo = states.get(app)
    if not geo: return
    def _restore():
        system = platform.system(); pname = process_name.replace(".exe","")
        MAX_WAIT = 15; POLL = 0.4
        print(f"  🔄  Warte auf Fenster von {pname}...")
        deadline = time.time() + MAX_WAIT; hwnd = None
        while time.time() < deadline:
            hwnd = _get_hwnd_windows(pname) if system == "Windows" else True
            if hwnd: break
            time.sleep(POLL)
        if not hwnd:
            print(f"  ⚠  Fenster von {pname} nicht gefunden – Position nicht wiederhergestellt"); return
        load_deadline = time.time() + 2.0
        while time.time() < load_deadline:
            if system == "Windows":
                if _get_window_geometry_windows(pname) is not None: break
            time.sleep(0.05)
        tol = 12; success = False
        for attempt in range(5):
            if system == "Windows": ok = _apply_geometry_windows(pname, geo)
            elif system == "Darwin": ok = _apply_geometry_macos(APP_PROFILES[app]["label"], geo)
            else: ok = _apply_geometry_linux(pname, geo)
            time.sleep(0.8)
            if system == "Windows":
                actual = _get_window_geometry_windows(pname)
                if actual is None: continue
                if geo.get("maximized"):
                    if actual.get("maximized"): success = True; break
                else:
                    dx=abs(actual["x"]-geo["x"]); dy=abs(actual["y"]-geo["y"])
                    dw=abs(actual["w"]-geo["w"]); dh=abs(actual["h"]-geo["h"])
                    print(f"  ↳  Versuch {attempt+1}: ist ({actual['x']},{actual['y']} {actual['w']}×{actual['h']}) soll ({geo['x']},{geo['y']} {geo['w']}×{geo['h']})")
                    if dx<=tol and dy<=tol and dw<=tol and dh<=tol: success = True; break
                    time.sleep(0.5)
            else:
                success = ok; break
        pos = "maximiert" if geo.get("maximized") else f"{geo['x']},{geo['y']} {geo['w']}×{geo['h']}"
        if success: print(f"  ✓  Fensterposition wiederhergestellt ({pos})")
        else: print(f"  ⚠  Fenster springt zurück — Electron überschreibt Position")
    t = threading.Thread(target=_restore, daemon=True); t.start()

def _run_ps(script: str, timeout: int = 8) -> str:
    try:
        result = subprocess.run(
            ["powershell.exe","-NoLogo","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-Command",script],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode != 0 and not result.stdout.strip(): return ""
        return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""

def _windows_process_ids(process_name: str) -> set[int]:
    import csv, io
    wanted = {Path(process_name).stem.casefold(), Path(process_name).name.casefold()}
    if any("turbowarp" in name for name in wanted):
        wanted.update({"turbowarp.exe","turbowarp","turbowarp desktop.exe","turbowarp desktop",
                       "turbowarp-desktop.exe","turbowarp-desktop","turbowarpdesktop.exe","turbowarpdesktop"})
    try:
        result = subprocess.run(["tasklist","/FO","CSV","/NH"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=6)
        ids: set[int] = set()
        for row in csv.reader(io.StringIO(result.stdout)):
            if len(row) >= 2 and row[0].strip().strip('"').casefold() in wanted:
                try: ids.add(int(row[1].replace(",","").strip()))
                except ValueError: pass
        return ids
    except Exception:
        return set()

def _windows_find_window(process_name: str):
    if platform.system() != "Windows": return None
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]; user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]; user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]; user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]; user32.GetWindowRect.restype = wintypes.BOOL
    user32.IsZoomed.argtypes = [wintypes.HWND]; user32.IsZoomed.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]; user32.IsIconic.restype = wintypes.BOOL
    pids = _windows_process_ids(process_name)
    if not pids: return None
    found = []
    @EnumWindowsProc
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd): return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids: return True
        title_len = user32.GetWindowTextLengthW(hwnd)
        title_buf = ctypes.create_unicode_buffer(max(title_len + 1, 2))
        user32.GetWindowTextW(hwnd, title_buf, len(title_buf))
        if not title_buf.value.strip(): return True
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)): return True
        width = rect.right - rect.left; height = rect.bottom - rect.top
        if width < 200 or height < 200 or user32.IsIconic(hwnd): return True
        found.append((width*height, hwnd, {"x":int(rect.left),"y":int(rect.top),"w":int(width),"h":int(height),"maximized":bool(user32.IsZoomed(hwnd))}, user32))
        return True
    user32.EnumWindows(callback, 0)
    if not found: return None
    found.sort(key=lambda item: item[0], reverse=True)
    _, hwnd, geo, user32 = found[0]
    return hwnd, user32, geo

def _get_hwnd_windows(process_name: str) -> bool:
    return _windows_find_window(process_name) is not None

def _apply_geometry_windows(process_name: str, geo: dict) -> bool:
    result = _windows_find_window(process_name)
    if not result: return False
    import ctypes
    from ctypes import wintypes
    hwnd, user32, _current_geo = result
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]; user32.ShowWindow.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.SetWindowPos.restype = wintypes.BOOL
    SW_RESTORE=9; SW_MAXIMIZE=3; HWND_TOP=0; SWP_NOACTIVATE=0x0010; SWP_NOZORDER=0x0004; SWP_SHOWWINDOW=0x0040
    if geo.get("maximized"):
        user32.ShowWindow(hwnd, SW_RESTORE); time.sleep(0.15); user32.ShowWindow(hwnd, SW_MAXIMIZE); return True
    user32.ShowWindow(hwnd, SW_RESTORE); time.sleep(0.15)
    flags = SWP_NOACTIVATE | SWP_NOZORDER | SWP_SHOWWINDOW
    ok = user32.SetWindowPos(hwnd, wintypes.HWND(HWND_TOP), int(geo["x"]), int(geo["y"]), int(geo["w"]), int(geo["h"]), flags)
    time.sleep(0.15)
    actual = _get_window_geometry_windows(process_name)
    if not actual: return bool(ok)
    tol = 12
    return bool(ok) and all(abs(actual[k]-geo[k])<=tol for k in ("x","y","w","h"))

def _apply_geometry_macos(app_name: str, geo: dict) -> bool:
    x, y, w, h = geo["x"], geo["y"], geo["w"], geo["h"]
    script = f'tell application "System Events"\ntry\nset proc to first process whose displayed name contains "{app_name}"\nset win to first window of proc\nset bounds of win to {{{x}, {y}, {x+w}, {y+h}}}\nreturn "ok"\non error\nreturn "err"\nend try\nend tell'
    try:
        r = subprocess.run(["osascript","-e",script], capture_output=True, text=True, timeout=8)
        return "ok" in r.stdout
    except Exception:
        return False

def _apply_geometry_linux(pname: str, geo: dict) -> bool:
    x, y, w, h = geo["x"], geo["y"], geo["w"], geo["h"]
    try:
        find = subprocess.run(["xdotool","search","--name",pname], capture_output=True, text=True, timeout=4)
        wids = find.stdout.strip().split()
        if not wids:
            find2 = subprocess.run(["xdotool","search","--class",pname], capture_output=True, text=True, timeout=4)
            wids = find2.stdout.strip().split()
        if not wids: return False
        wid = wids[0]
        subprocess.run(["xdotool","windowmove",wid,str(x),str(y)], capture_output=True, timeout=4)
        subprocess.run(["xdotool","windowsize",wid,str(w),str(h)], capture_output=True, timeout=4)
        return True
    except Exception:
        return False

def _get_running_pname(candidates: list[str]) -> str | None:
    if platform.system() != "Windows": return None
    names = [c.replace(".exe","") for c in candidates]
    name_list = ", ".join(f'"{n}"' for n in names)
    script = (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"
        f"$names = @({name_list})\n"
        "foreach ($n in $names) {\n"
        "    $p = Get-Process -Name $n -ErrorAction SilentlyContinue | Select-Object -First 1\n"
        "    if ($p) { Write-Output \"$($p.ProcessName).exe\"; break }\n"
        "}"
    )
    result = _run_ps(script, timeout=5)
    return result if result else None

def _find_turbowarp_pname() -> str:
    candidates = ["TurboWarp Desktop","TurboWarp","turbowarp-desktop","turbowarpdesktop"]
    found = _get_running_pname([f"{c}.exe" for c in candidates])
    return found or "TurboWarp Desktop.exe"

def _find_scratch_store_aumid() -> str | None:
    family = _run_ps("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\nGet-AppxPackage *Scratch* | Select-Object -ExpandProperty PackageFamilyName", timeout=8)
    return f"{family}!App" if family else None

def _find_scratch_store_exe() -> str | None:
    import glob
    for pat in [r"C:\Program Files\WindowsApps\ScratchFoundation.Scratch3_*\Scratch Desktop.exe",
                r"C:\Program Files\WindowsApps\ScratchFoundation.Scratch3_*\Scratch*.exe"]:
        hits = glob.glob(pat)
        if hits: return hits[0]
    return None

def launch_app(sb3_path: str, app: str, replace: bool):
    sb3_abs = str(Path(sb3_path).resolve())
    system  = platform.system()
    sys_key = {"Windows":"Windows","Darwin":"Darwin"}.get(system, "Linux")
    profile     = APP_PROFILES[app]
    sys_profile = profile[sys_key]
    label       = profile["label"]
    if replace:
        if system == "Windows" and app == "turbowarp":
            kill = _find_turbowarp_pname(); print(f"  🔍  Prozessname: {kill}")
        else:
            kill = sys_profile["kill"]
        save_window_state(app, kill)
        print(f"  ⏹  Beende laufende {label}-Instanzen...")
        if system == "Windows":
            for pname in ["TurboWarp Desktop.exe","TurboWarp.exe","turbowarp-desktop.exe","turbowarpdesktop.exe"]:
                subprocess.run(["taskkill","/F","/IM",pname], capture_output=True, timeout=8)
        else:
            subprocess.run(["pkill","-f",kill], capture_output=True)
        time.sleep(0.8)
    mode = "Ersetze" if replace else "Starte neue"
    if system == "Windows" and app == "scratch":
        exe = next((c for c in sys_profile["candidates"] if Path(c).exists()), None)
        if exe:
            print(f"  ▶  {mode} {label}-Instanz: {Path(sb3_abs).name}")
            print(f"     (klassische Installation: {exe})")
            subprocess.Popen([exe, sb3_abs])
            if replace: restore_window_state(app, Path(exe).name)
            return
        print(f"  ℹ  Klassische Installation nicht gefunden.\n     Suche Microsoft Store-Version...")
        aumid = _find_scratch_store_aumid()
        if aumid:
            print(f"  ✓  Store-Version gefunden: {aumid}")
            print(f"  ▶  {mode} {label}-Instanz: {Path(sb3_abs).name}")
            print(f"\n  ⚠  HINWEIS: Die Microsoft Store-Version des Desktop-Players kann\n     .sb3-Dateien nicht direkt per CLI öffnen (Sandbox-Einschränkung).\n     Die App wird geöffnet — lade die Datei manuell über\n     Datei → Vom Computer laden:\n     {sb3_abs}\n")
            _run_ps(f'Start-Process "shell:AppsFolder\\{aumid}"', timeout=5)
            result = _run_ps(f'Set-Clipboard -Value "{sb3_abs}"; Write-Output "ok"', timeout=3)
            if result == "ok": print("  📋  Dateipfad wurde in die Zwischenablage kopiert.")
            return
        store_exe = _find_scratch_store_exe()
        if store_exe:
            print(f"  ✓  Store-Exe gefunden: {store_exe}")
            print(f"  ▶  {mode} {label}: {Path(sb3_abs).name}")
            try: subprocess.Popen([store_exe, sb3_abs])
            except PermissionError:
                print("  ✗  Zugriff verweigert (WindowsApps benötigt Admin-Rechte).\n     Starte ohne Dateiargument...")
                subprocess.Popen([store_exe])
            return
        print(f"  ✗  Desktop-Player nicht gefunden.\n     Store-Version:  apps.microsoft.com/detail/9pfgj25j6x3\n     Klassische Version:          {profile['download']}\n     Datei manuell öffnen: {sb3_abs}")
        return
    exe = next((c for c in sys_profile["candidates"] if Path(c).exists()), None)
    if exe is None:
        print(f"  ⚠  {label} nicht gefunden.\n     Download: {profile['download']}\n     Datei manuell öffnen: {sb3_abs}")
        return
    print(f"  ▶  {mode} {label}-Instanz: {Path(sb3_abs).name}")
    cmd = sys_profile["launch"](exe, sb3_abs)
    subprocess.Popen(cmd)
    if replace:
        exe_name = Path(exe).name
        restore_window_state(app, exe_name)


# ═══════════════════════════════════════════════════════
#  7.  KOMPILIER-PIPELINE
# ═══════════════════════════════════════════════════════
def compile_once(source: str, base_dir: Path, outfile: str,
                 asset_mgr: AssetManager, verbose=True) -> bool:
    try:
        if verbose: print("── [1] Tokenisierung & Parsing ────────────")
        tokens = tokenize(source)
        parser = Parser(tokens)
        ast    = parser.parse_program()
        if verbose:
            print(f"    {len(ast['targets'])} Target(s): "
                  + ", ".join(f"{t['type']} {t['name']}" for t in ast["targets"]))
            if ast.get("extensions"):
                print(f"    Extensions: {', '.join(ast['extensions'])}")
    except SyntaxError as e:
        msg = str(e)
        if msg == "__all_reported__":
            print("  ✗  Parsing abgebrochen – alle Fehler oben beheben.")
        elif msg == "__collected__":
            print("\n  ✗  Syntaxfehler beim Parsen.")
        else:
            print(f"\n  ✗  Syntaxfehler: {msg}")
        return False

    if verbose: print("── [2] Validierung ────────────────────────")
    validator = Validator(ast, AssetManager._library)
    ok = validator.validate()
    validator.print_report()
    if not ok:
        print(f"\n  ✗  Validierung fehlgeschlagen – {len(validator.errors)} Fehler oben beheben.")
        return False

    if verbose: print("── [3] Code-Generierung & Assets ──────────")
    project = build_project(ast, asset_mgr)
    total   = sum(len(t["blocks"]) for t in project["targets"])
    if verbose: print(f"    {total} Blöcke")

    if verbose: print("── [4] Ausgabe ─────────────────────────────")
    json_path = Path(outfile).with_suffix(".json")
    json_path.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")
    if verbose: print(f"✓  {json_path}  ({json_path.stat().st_size:,} Bytes)")
    write_sb3(project, asset_mgr, outfile)
    if verbose: print(f"✓  {outfile}  ({Path(outfile).stat().st_size:,} Bytes)")
    return True


# ═══════════════════════════════════════════════════════
#  8.  WATCH-MODUS
# ═══════════════════════════════════════════════════════
def watch_mode(src_path: Path, outfile: str, app_mode: tuple | None):
    print(f"👁  Watch-Modus aktiv – beobachte: {src_path}")
    print("   Ctrl+C zum Beenden\n")
    last_mtime = None; first_run = True
    while True:
        try:
            mtime = src_path.stat().st_mtime
        except FileNotFoundError:
            print(f"  ⚠  Datei nicht gefunden: {src_path}"); time.sleep(1); continue
        if mtime != last_mtime:
            last_mtime = mtime
            if not first_run:
                print(f"\n{'─'*45}\n🔄  Änderung erkannt – {time.strftime('%H:%M:%S')}")
            first_run = False
            source    = src_path.read_text(encoding="utf-8")
            base_dir  = src_path.parent
            asset_mgr = AssetManager(base_dir)
            try:
                success = compile_once(source, base_dir, outfile, asset_mgr)
            except Exception as exc:
                print(f"  ✗  Unerwarteter Fehler beim Kompilieren: {exc}"); success = False
            if success and app_mode:
                app, mode = app_mode
                label = APP_PROFILES[app]["label"]
                print(f"── [5] {label} ───────────────────────────")
                launch_app(outfile, app=app, replace=(mode=="replace"))
            print("\n   Warte auf Änderungen...")
        time.sleep(0.5)


# ═══════════════════════════════════════════════════════
#  9.  MAIN
# ═══════════════════════════════════════════════════════
def print_help():
    print("""
Transpiler.py  v5.2
────────────────────────────────────────────────────────
VERWENDUNG:
  python transpiler.py <eingabe.scrape> [Optionen]

OPTIONEN:
  --out <datei.sb3>         Ausgabedatei (Standard: output.sb3)
  --watch                   Watch-Modus: kompiliert bei Dateiänderung neu

  TurboWarp Desktop:
  --turbowarp-new           Startet TurboWarp nach Kompilierung
  --turbowarp-replace       Beendet laufende TurboWarp-Instanz, startet neu

  Desktop-Player:
  --scratch-new             Startet den Desktop-Player nach Kompilierung
  --scratch-replace         Beendet laufende Desktop-Player-Instanz, startet neu

  --help                    Diese Hilfe anzeigen

ERWEITERUNGSBEFEHLE (nach import "ext";):
  Music:        playDrum(drum, beats);  restForBeats(beats);
                playNote(note, beats);  setInstrument(num);
                setTempo(bpm);  changeTempo(delta);
                getTempo  (Ausdruck)
  Video:        videoOn();  videoOff();  videoFlipped();
                setVideoTransparency(percent);
                videoMotion("this sprite")  (Ausdruck)
                videoDirection("this sprite")  (Ausdruck)
  Text2Speech:  speak(text);  setVoice("Alto");
                setLanguage("de");
  Translate:    translate(text, "de")  (Ausdruck)
                viewerLanguage  (Ausdruck)
  Pen:          penDown();  penUp();  stampPen();  erasePen();
                setPenColor(color);  changePenColor(delta);
                setPenSize(size);  changePenSize(delta);

NEU in v5.1:
  Bezeichner mit ungültigen Zeichen (Song#, my-var, ...) werden automatisch
  sanitisiert (→ Song_, my_var) mit einer Warnung in der Ausgabe.
  Damit sind .scrape-Dateien vom Detranspiler v1.0 direkt kompilierbar.

BEISPIELE:
  python transpiler.py spiel.scrape
  python transpiler.py spiel.scrape --out spiel.sb3
  python transpiler.py spiel.scrape --watch --turbowarp-replace
  python transpiler.py spiel.scrape --scratch-replace
""")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args     = sys.argv[1:]
    infile   = None
    outfile  = "output.sb3"
    app_mode = None
    watch    = False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--out" and i+1 < len(args):
            outfile = args[i+1]; i += 2
        elif a == "--turbowarp-new":
            if app_mode: print("⚠  Mehrere App-Flags angegeben – letztes gewinnt.")
            app_mode = ("turbowarp", "new"); i += 1
        elif a == "--turbowarp-replace":
            if app_mode: print("⚠  Mehrere App-Flags angegeben – letztes gewinnt.")
            app_mode = ("turbowarp", "replace"); i += 1
        elif a == "--scratch-new":
            if app_mode: print("⚠  Mehrere App-Flags angegeben – letztes gewinnt.")
            app_mode = ("scratch", "new"); i += 1
        elif a == "--scratch-replace":
            if app_mode: print("⚠  Mehrere App-Flags angegeben – letztes gewinnt.")
            app_mode = ("scratch", "replace"); i += 1
        elif a == "--watch":
            watch = True; i += 1
        elif a in ("--help", "-h"):
            print_help(); sys.exit(0)
        else:
            infile = a; i += 1

    if not infile:
        print("Fehler: Kein Eingabefile angegeben.")
        print_help(); sys.exit(1)

    src_path = Path(infile).resolve()
    if not src_path.exists():
        print(f"Fehler: Datei nicht gefunden: {src_path}"); sys.exit(1)

    if watch:
        try:
            watch_mode(src_path, outfile, app_mode)
        except KeyboardInterrupt:
            print("\n👋  Watch-Modus beendet.")
        return

    source    = src_path.read_text(encoding="utf-8")
    base_dir  = src_path.parent
    asset_mgr = AssetManager(base_dir)
    print(f"Lese: {src_path}")
    success = compile_once(source, base_dir, outfile, asset_mgr)
    if not success:
        sys.exit(1)

    if app_mode:
        app, mode = app_mode
        label = APP_PROFILES[app]["label"]
        print(f"── [5] {label} ───────────────────────────")
        launch_app(outfile, app=app, replace=(mode=="replace"))

    print("\n── Fertig! ─────────────────────────────────")
    if not app_mode:
        print(f"   Öffne {outfile} in TurboWarp oder dem Desktop-Player.")


if __name__ == "__main__":
    main()
