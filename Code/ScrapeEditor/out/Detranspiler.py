"""
Detranspiler.py  v1.3
══════════════════════════════════════════════
Scratch 3 / TurboWarp .sb3  →  Java-ähnliche Syntax

Unterstützt alle Blöcke aus Transpiler.py v5.3:
  • Alle Erweiterungen: Pen, Music, Video Sensing,
    Text2Speech, Translate, MakeyMakey, Microbit,
    EV3, Boost, WeDo 2.0, GDX FOR
  • Motion, Looks, Sound, Events, Control
  • Sensing, Operators, Data (Variablen, Listen)
  • Custom Blocks (define / void)
  • Kommentare (Scratch Comments → // Kommentare)
  • Watch-Modus (--watch)
  • --output <datei.scrape>  (Standard: output.scrape)

Neu in v1.1:
  • Identifier-Sanitisierung: ungültige Zeichen (z.B. #, -, Leerzeichen)
    werden durch _ ersetzt, damit der Output immer gültiges Scrape ist.
  • Variablen- und Sprites-Namen die mit einer Ziffer beginnen erhalten
    ein führendes _ (z.B. "2fast" → "_2fast").
  • Bei umbenannten Namen wird ein Kommentar-Header ausgegeben.
  • Alle Stellen die auf den Originalnamen verweisen (Blöcke, Felder,
    Custom-Block-Argumente) werden über eine zentrale Name-Map übersetzt.
"""

import json, zipfile, sys, time, re
from pathlib import Path


# ═══════════════════════════════════════════════════════
#  Identifier-Sanitisierung
# ═══════════════════════════════════════════════════════

def sanitize_identifier(name: str) -> str:
    """
    Macht einen beliebigen String zu einem gültigen Scrape-Bezeichner.

    Regeln (entsprechen dem Transpiler-Lexer):
      • Erlaubt:  [A-Za-z_][A-Za-z0-9_]*
      • Ungültige Zeichen → _
      • Beginnt mit Ziffer → führendes _ anhängen
      • Leerstring → "_var"

    Beispiele:
      "Song#"       → "Song_"
      "my-var"      → "my_var"
      "2fast"       → "_2fast"
      "hello world" → "hello_world"
      "#hash"       → "_hash"
    """
    if not name:
        return "_var"
    result = re.sub(r'[^A-Za-z0-9_]', '_', name)
    if result[0].isdigit():
        result = '_' + result
    return result


def build_name_map(names: list[str]) -> dict[str, str]:
    """
    Erstellt ein Mapping original_name → sanitized_name für eine Liste von Namen.
    Stellt sicher dass sanitized-Namen eindeutig sind (Suffix _2, _3, … bei Kollision).
    """
    used: set[str] = set()
    mapping: dict[str, str] = {}
    for name in names:
        clean = sanitize_identifier(name)
        if clean in used:
            # Kollision → Suffix anhängen
            i = 2
            while f"{clean}_{i}" in used:
                i += 1
            clean = f"{clean}_{i}"
        used.add(clean)
        mapping[name] = clean
    return mapping


# ═══════════════════════════════════════════════════════
#  Hilfsfunktionen
# ═══════════════════════════════════════════════════════

def _num(v) -> str:
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else str(f)
    except (TypeError, ValueError):
        return str(v)

def _str(v) -> str:
    return f'"{v}"'

def _looks_num(s) -> bool:
    try:
        float(str(s)); return True
    except (TypeError, ValueError):
        return False


# ═══════════════════════════════════════════════════════
#  SB3 lesen
# ═══════════════════════════════════════════════════════

def read_sb3(path: str) -> dict:
    with zipfile.ZipFile(path, "r") as zf:
        with zf.open("project.json") as f:
            return json.loads(f.read().decode("utf-8"))


# ═══════════════════════════════════════════════════════
#  Block-Resolver
# ═══════════════════════════════════════════════════════

class BlockResolver:
    def __init__(self, blocks: dict, comments: dict = None,
                 name_map: dict = None):
        self.blocks   = blocks
        self.comments = comments or {}
        self.name_map = name_map or {}   # original → sanitized
        self._cmap = {
            c["blockId"]: c["text"]
            for c in self.comments.values()
            if c.get("blockId")
        }

    def sanitize(self, name: str) -> str:
        """Übersetzt einen Originalnamen in den sanitisierten Bezeichner."""
        return self.name_map.get(name, sanitize_identifier(name))

    def comment_for(self, bid) -> str | None:
        return self._cmap.get(bid)

    def input_block(self, block, key) -> str | None:
        inp = block.get("inputs", {}).get(key)
        if not inp or len(inp) < 2:
            return None
        val = inp[1]
        if isinstance(val, str) and val in self.blocks:
            return val
        return None

    def field(self, block, key) -> str | None:
        f = block.get("fields", {}).get(key)
        return f[0] if f else None

    def next_chain(self, bid) -> list:
        chain = []
        cur = bid
        while cur:
            chain.append(cur)
            b = self.blocks.get(cur)
            if not b:
                break
            cur = b.get("next")
        return chain


# ═══════════════════════════════════════════════════════
#  Ausdruck-Generator
# ═══════════════════════════════════════════════════════

class ExprGen:
    def __init__(self, resolver: BlockResolver):
        self.r = resolver

    def from_input(self, block, key, paren=False) -> str:
        inp = block.get("inputs", {}).get(key)
        if not inp or len(inp) < 2:
            return '""'
        val = inp[1]
        if isinstance(val, list):
            kind = val[0] if val else 10
            raw  = val[1] if len(val) >= 2 else ""
            if kind in (4, 5, 6, 7, 8):
                return _num(raw)
            if kind in (10, 9):
                return _str(raw) if not _looks_num(raw) else raw
            if kind == 11:
                return _str(raw)
            if kind in (12, 13):
                # Variable/List reference — sanitize the name
                return self.r.sanitize(str(raw))
            return _str(str(raw))
        if isinstance(val, str) and val in self.r.blocks:
            return self.from_block(val, paren)
        return '""'

    def from_block(self, bid, paren=False) -> str:
        b = self.r.blocks.get(bid)
        if not b:
            return '""'
        op = b.get("opcode", "")
        result = self._dispatch(b, op)
        compound = op in (
            "operator_add", "operator_subtract", "operator_multiply",
            "operator_divide", "operator_mod", "operator_lt", "operator_gt",
            "operator_equals", "operator_and", "operator_or",
        )
        if paren and compound:
            return f"({result})"
        return result

    def _i(self, b, key, paren=False) -> str:
        return self.from_input(b, key, paren)

    def _dispatch(self, b, op) -> str:
        r = self.r

        # Literals
        if op == "math_number":           return _num(r.field(b, "NUM"))
        if op == "math_positive_number":  return _num(r.field(b, "NUM"))
        if op == "math_whole_number":     return _num(r.field(b, "NUM"))
        if op == "math_angle":            return _num(r.field(b, "NUM"))
        if op == "text":                  return _str(r.field(b, "TEXT") or "")
        if op == "colour_picker":         return _str(r.field(b, "COLOUR") or "#000000")

        # Variables / Lists — Namen sanitizen!
        if op == "data_variable":
            raw = r.field(b, "VARIABLE") or "?"
            return r.sanitize(raw)
        if op == "data_itemoflist":
            raw = r.field(b, "LIST") or "?"
            return f"{r.sanitize(raw)}[{self._i(b,'INDEX')}]"
        if op == "data_lengthoflist":
            raw = r.field(b, "LIST") or "?"
            return f"{r.sanitize(raw)}.length()"
        if op == "data_listcontainsitem":
            raw = r.field(b, "LIST") or "?"
            return f"{r.sanitize(raw)}.contains({self._i(b,'ITEM')})"
        if op == "data_itemnumoflist":
            raw = r.field(b, "LIST") or "?"
            return f"{r.sanitize(raw)}.indexOf({self._i(b,'ITEM')})"

        # Operators
        ARITH = {
            "operator_add":      ("+",  "NUM1",    "NUM2"),
            "operator_subtract": ("-",  "NUM1",    "NUM2"),
            "operator_multiply": ("*",  "NUM1",    "NUM2"),
            "operator_divide":   ("/",  "NUM1",    "NUM2"),
            "operator_mod":      ("%",  "NUM1",    "NUM2"),
            "operator_lt":       ("<",  "OPERAND1","OPERAND2"),
            "operator_gt":       (">",  "OPERAND1","OPERAND2"),
            "operator_equals":   ("==", "OPERAND1","OPERAND2"),
        }
        if op in ARITH:
            sym, lk, rk = ARITH[op]
            return f"{self._i(b,lk,True)} {sym} {self._i(b,rk,True)}"
        if op == "operator_and":
            return f"{self._i(b,'OPERAND1',True)} && {self._i(b,'OPERAND2',True)}"
        if op == "operator_or":
            return f"{self._i(b,'OPERAND1',True)} || {self._i(b,'OPERAND2',True)}"
        if op == "operator_not":
            oid = r.input_block(b, "OPERAND")
            if oid:
                inner = r.blocks.get(oid, {})
                if inner.get("opcode") == "operator_equals":
                    l = self.from_input(inner, "OPERAND1", True)
                    rr = self.from_input(inner, "OPERAND2", True)
                    return f"{l} != {rr}"
                return f"!({self.from_block(oid)})"
            return f"!({self._i(b,'OPERAND')})"
        if op == "operator_random":
            return f"Math.random({self._i(b,'FROM')}, {self._i(b,'TO')})"
        if op == "operator_round":
            return f"Math.round({self._i(b,'NUM')})"
        if op == "operator_mathop":
            fn = r.field(b, "OPERATOR") or "abs"
            fn = "ceil" if fn == "ceiling" else fn
            return f"Math.{fn}({self._i(b,'NUM')})"
        if op == "operator_length":
            return f"{self._i(b,'STRING')}.length()"
        if op == "operator_letter_of":
            return f"{self._i(b,'STRING')}.letter({self._i(b,'LETTER')})"
        if op == "operator_contains":
            return f"{self._i(b,'STRING1')}.contains({self._i(b,'STRING2')})"
        if op == "operator_join":
            return f"{self._i(b,'STRING1')}.join({self._i(b,'STRING2')})"

        # Motion reporters
        if op == "motion_xposition": return "xPosition"
        if op == "motion_yposition": return "yPosition"
        if op == "motion_direction":  return "direction"

        # Sensing reporters
        if op == "sensing_answer":    return "answer"
        if op == "sensing_mousex":    return "mouseX"
        if op == "sensing_mousey":    return "mouseY"
        if op == "sensing_mousedown": return "mouseDown"
        if op == "sensing_timer":     return "timer"
        if op == "sensing_loudness":  return "loudness"
        if op == "sensing_username":  return "username"
        if op == "sensing_current":
            fm = {
                "YEAR":"currentYear","MONTH":"currentMonth","DATE":"currentDate",
                "DAYOFWEEK":"currentDayOfWeek","HOUR":"currentHour",
                "MINUTE":"currentMinute","SECOND":"currentSecond",
            }
            return fm.get(r.field(b,"CURRENTMENU") or "", "currentSecond")
        if op == "sensing_keypressed":
            mid = r.input_block(b, "KEY_OPTION")
            key = r.field(r.blocks.get(mid, {}), "KEY_OPTION") or "" if mid else ""
            return f'keyPressed("{key}")'
        if op == "sensing_touchingobject":
            mid = r.input_block(b, "TOUCHINGOBJECTMENU")
            tgt = r.field(r.blocks.get(mid,{}), "TOUCHINGOBJECTMENU") or "" if mid else ""
            return f'touching("{tgt}")'
        if op == "sensing_touchingcolor":
            return f"touchingColor({self._i(b,'COLOR')})"
        if op == "sensing_distanceto":
            mid = r.input_block(b, "DISTANCETOMENU")
            tgt = r.field(r.blocks.get(mid,{}), "DISTANCETOMENU") or "" if mid else ""
            return f'distanceTo("{tgt}")'

        # Custom block argument reporters — Namen sanitizen
        if op in ("argument_reporter_string_number", "argument_reporter_boolean"):
            raw = r.field(b, "VALUE") or "?"
            return r.sanitize(raw)

        # Looks reporters
        if op == "looks_costumenumbername":
            return f"/* costume {r.field(b,'NUMBER_NAME') or 'number'} */"
        if op == "looks_backdropnumbername":
            return f"/* backdrop {r.field(b,'NUMBER_NAME') or 'number'} */"
        if op == "looks_size":
            return "/* size */"

        # ── Music reporters ────────────────────────────
        if op == "music_getTempo":
            return "getTempo"

        # ── Video Sensing reporters ────────────────────
        if op == "videoSensing_videoOn":
            attr = ""
            mid_a = r.input_block(b, "ATTRIBUTE")
            if mid_a:
                attr = r.field(r.blocks.get(mid_a, {}), "ATTRIBUTE") or "motion"
            mid_s = r.input_block(b, "SUBJECT")
            subj = r.field(r.blocks.get(mid_s, {}), "SUBJECT") or "this sprite" if mid_s else "this sprite"
            fn = "videoDirection" if attr == "direction" else "videoMotion"
            return f'{fn}("{subj}")'

        # ── Translate reporters ────────────────────────
        if op == "translate_getTranslate":
            lang = ""
            mid_l = r.input_block(b, "LANGUAGE")
            if mid_l:
                lang = r.field(r.blocks.get(mid_l, {}), "LANGUAGE") or "en"
            return f'translate({self._i(b,"WORDS")}, "{lang}")'
        if op == "translate_getViewerLanguage":
            return "viewerLanguage"

        # ── Hardware extension reporters (generic) ─────
        if any(op.startswith(p) for p in
               ("microbit_","ev3_","boost_","wedo2_","gdxfor_")):
            return f"/* {op} */"

        return f"/* {op} */"


# ═══════════════════════════════════════════════════════
#  Statement-Generator
# ═══════════════════════════════════════════════════════

class StmtGen:
    def __init__(self, resolver: BlockResolver, expr: ExprGen):
        self.r = resolver
        self.e = expr

    def chain_to_lines(self, start_id, level=1) -> list[str]:
        lines = []
        chain = self.r.next_chain(start_id)
        for bid in chain:
            b = self.r.blocks.get(bid)
            if not b:
                continue
            op = b.get("opcode", "")
            cmt = self.r.comment_for(bid)
            result = self._dispatch(b, op, level)
            if result is None:
                continue
            if cmt:
                lines.append("    " * level + f"// {cmt}")
            if isinstance(result, list):
                lines.extend(result)
            else:
                lines.append(result)
        return lines

    def _inp(self, b, key, paren=False) -> str:
        return self.e.from_input(b, key, paren)

    def _fld(self, b, key) -> str:
        return self.r.field(b, key) or "?"

    def _sub(self, b, key, level) -> list[str]:
        sid = self.r.input_block(b, key)
        if not sid:
            return []
        return self.chain_to_lines(sid, level)

    def _menu_field(self, b, input_key, field_key) -> str:
        mid = self.r.input_block(b, input_key)
        if mid:
            return self.r.field(self.r.blocks.get(mid, {}), field_key) or ""
        return ""

    def _dispatch(self, b, op, level) -> str | list | None:
        pad = "    " * level
        r   = self.r  # shorthand

        # Hat blocks → handled separately
        if op in (
            "event_whenflagclicked", "event_whenkeypressed",
            "event_whenthisspriteclicked", "event_whenstageclicked",
            "event_whenbackdropswitchesto", "event_whenbroadcastreceived",
            "procedures_definition", "control_start_as_clone",
        ):
            return None

        # Shadow / prototype blocks
        if op in ("procedures_prototype",):
            return None

        # ── Motion ────────────────────────────────────
        if op == "motion_movesteps":
            return f"{pad}move({self._inp(b,'STEPS')});"
        if op == "motion_turnleft":
            return f"{pad}turnLeft({self._inp(b,'DEGREES')});"
        if op == "motion_turnright":
            return f"{pad}turnRight({self._inp(b,'DEGREES')});"
        if op == "motion_gotoxy":
            return f"{pad}goTo({self._inp(b,'X')}, {self._inp(b,'Y')});"
        if op == "motion_goto":
            tgt = self._menu_field(b, "TO", "TO")
            return f'{pad}goToSprite("{tgt}");'
        if op == "motion_glidesecstoxy":
            return f"{pad}glide({self._inp(b,'SECS')}, {self._inp(b,'X')}, {self._inp(b,'Y')});"
        if op == "motion_glideto":
            tgt = self._menu_field(b, "TO", "TO")
            return f'{pad}glideToSprite({self._inp(b,"SECS")}, "{tgt}");'
        if op == "motion_pointindirection":
            return f"{pad}pointDir({self._inp(b,'DIRECTION')});"
        if op == "motion_pointtowards":
            tgt = self._menu_field(b, "TOWARDS", "TOWARDS")
            return f'{pad}pointTowards("{tgt}");'
        if op == "motion_setx":
            return f"{pad}setX({self._inp(b,'X')});"
        if op == "motion_sety":
            return f"{pad}setY({self._inp(b,'Y')});"
        if op == "motion_changexby":
            return f"{pad}changeX({self._inp(b,'DX')});"
        if op == "motion_changeyby":
            return f"{pad}changeY({self._inp(b,'DY')});"
        if op == "motion_ifonedgebounce":
            return f"{pad}bounceOnEdge();"
        if op == "motion_setrotationstyle":
            return f'{pad}setRotationStyle("{self._fld(b,"STYLE")}");'

        # ── Looks ─────────────────────────────────────
        if op == "looks_say":
            return f"{pad}say({self._inp(b,'MESSAGE')});"
        if op == "looks_sayforsecs":
            return f"{pad}sayFor({self._inp(b,'MESSAGE')}, {self._inp(b,'SECS')});"
        if op == "looks_think":
            return f"{pad}think({self._inp(b,'MESSAGE')});"
        if op == "looks_thinkforsecs":
            return f"{pad}thinkFor({self._inp(b,'MESSAGE')}, {self._inp(b,'SECS')});"
        if op == "looks_switchcostumeto":
            costume = self._menu_field(b, "COSTUME", "COSTUME")
            return f'{pad}switchCostume("{costume}");'
        if op == "looks_nextcostume":
            return f"{pad}nextCostume();"
        if op == "looks_switchbackdropto":
            bd = self._menu_field(b, "BACKDROP", "BACKDROP")
            return f'{pad}switchBackdrop("{bd}");'
        if op == "looks_nextbackdrop":
            return f"{pad}nextBackdrop();"
        if op == "looks_setsizeto":
            return f"{pad}setSize({self._inp(b,'SIZE')});"
        if op == "looks_changesizeby":
            return f"{pad}changeSize({self._inp(b,'CHANGE')});"
        if op == "looks_show":
            return f"{pad}show();"
        if op == "looks_hide":
            return f"{pad}hide();"
        if op == "looks_gotofrontback":
            which = self._fld(b, "FRONT_BACK")
            return f"{pad}goTo{'Front' if which == 'front' else 'Back'}();"
        if op == "looks_goforwardbackwardlayers":
            cmd = "goForwardLayers" if self._fld(b,"FORWARD_BACKWARD") == "forward" else "goBackwardLayers"
            return f"{pad}{cmd}({self._inp(b,'NUM')});"
        if op == "looks_seteffectto":
            effect = (self._fld(b,"EFFECT") or "").lower()
            return f'{pad}setEffect("{effect}", {self._inp(b,"VALUE")});'
        if op == "looks_changeeffectby":
            effect = (self._fld(b,"EFFECT") or "").lower()
            return f'{pad}changeEffect("{effect}", {self._inp(b,"CHANGE")});'
        if op == "looks_cleargraphiceffects":
            return f"{pad}clearEffects();"

        # ── Sound ─────────────────────────────────────
        if op == "sound_play":
            sname = self._menu_field(b, "SOUND_MENU", "SOUND_MENU")
            return f'{pad}playSound("{sname}");'
        if op == "sound_playuntildone":
            sname = self._menu_field(b, "SOUND_MENU", "SOUND_MENU")
            return f'{pad}playSoundUntilDone("{sname}");'
        if op == "sound_stopallsounds":
            return f"{pad}stopAllSounds();"
        if op == "sound_setvolumeto":
            return f"{pad}setVolume({self._inp(b,'VOLUME')});"
        if op == "sound_changevolumeby":
            return f"{pad}changeVolume({self._inp(b,'CHANGE')});"

        # ── Events ────────────────────────────────────
        if op == "event_broadcast":
            raw = b.get("inputs",{}).get("BROADCAST_INPUT")
            msg = ""
            if raw and len(raw) >= 2 and isinstance(raw[1], list) and len(raw[1]) >= 2:
                msg = raw[1][1]
            return f'{pad}broadcast("{msg}");'
        if op == "event_broadcastandwait":
            raw = b.get("inputs",{}).get("BROADCAST_INPUT")
            msg = ""
            if raw and len(raw) >= 2 and isinstance(raw[1], list) and len(raw[1]) >= 2:
                msg = raw[1][1]
            return f'{pad}broadcastAndWait("{msg}");'

        # ── Control ───────────────────────────────────
        if op == "control_wait":
            return f"{pad}wait({self._inp(b,'DURATION')});"
        if op == "control_repeat":
            body = self._sub(b, "SUBSTACK", level + 1)
            return [f"{pad}repeat({self._inp(b,'TIMES')}) {{"] + body + [f"{pad}}}"]
        if op == "control_forever":
            body = self._sub(b, "SUBSTACK", level + 1)
            return [f"{pad}forever {{"] + body + [f"{pad}}}"]
        if op == "control_if":
            cond = self._inp(b, "CONDITION")
            body = self._sub(b, "SUBSTACK", level + 1)
            return [f"{pad}if ({cond}) {{"] + body + [f"{pad}}}"]
        if op == "control_if_else":
            cond = self._inp(b, "CONDITION")
            then = self._sub(b, "SUBSTACK", level + 1)
            else_ = self._sub(b, "SUBSTACK2", level + 1)
            out = [f"{pad}if ({cond}) {{"] + then
            if else_:
                out += [f"{pad}}} else {{"] + else_
            out.append(f"{pad}}}")
            return out
        if op == "control_repeat_until":
            cond = self._inp(b, "CONDITION")
            body = self._sub(b, "SUBSTACK", level + 1)
            return [f"{pad}repeatUntil ({cond}) {{"] + body + [f"{pad}}}"]
        if op == "control_wait_until":
            return f"{pad}waitUntil({self._inp(b,'CONDITION')});"
        if op == "control_stop":
            return f'{pad}stop("{self._fld(b,"STOP_OPTION")}");'
        if op == "control_create_clone_of":
            tgt = self._menu_field(b, "CLONE_OPTION", "CLONE_OPTION") or "_myself_"
            return f'{pad}createClone("{tgt}");'
        if op == "control_delete_this_clone":
            return f"{pad}deleteClone();"

        # ── Sensing ───────────────────────────────────
        if op == "sensing_askandwait":
            return f"{pad}askAndWait({self._inp(b,'QUESTION')});"
        if op == "sensing_setdragmode":
            return f'{pad}setDragMode("{self._fld(b,"DRAG_MODE")}");'
        if op == "sensing_resettimer":
            return f"{pad}resetTimer();"

        # ── Data: Variables ───────────────────────────
        if op == "data_setvariableto":
            name = r.sanitize(self._fld(b, "VARIABLE"))
            val  = self._inp(b, "VALUE")
            return f"{pad}{name} = {val};"
        if op == "data_changevariableby":
            name = r.sanitize(self._fld(b, "VARIABLE"))
            val  = self._inp(b, "VALUE")
            if val == "1":   return f"{pad}{name}++;"
            if val == "-1":  return f"{pad}{name}--;"
            try:
                fv = float(val)
                if fv < 0:
                    return f"{pad}{name} -= {_num(-fv)};"
            except (ValueError, TypeError):
                pass
            return f"{pad}{name} += {val};"
        if op == "data_showvariable":
            name = r.sanitize(self._fld(b, "VARIABLE"))
            return f'{pad}showVar("{name}");'
        if op == "data_hidevariable":
            name = r.sanitize(self._fld(b, "VARIABLE"))
            return f'{pad}hideVar("{name}");'

        # ── Data: Lists ───────────────────────────────
        if op == "data_addtolist":
            lname = r.sanitize(self._fld(b, "LIST"))
            return f"{pad}{lname}.add({self._inp(b,'ITEM')});"
        if op == "data_deleteoflist":
            lname = r.sanitize(self._fld(b, "LIST"))
            return f"{pad}{lname}.delete({self._inp(b,'INDEX')});"
        if op == "data_insertatlist":
            lname = r.sanitize(self._fld(b, "LIST"))
            return f"{pad}{lname}.insert({self._inp(b,'INDEX')}, {self._inp(b,'ITEM')});"
        if op == "data_replaceitemoflist":
            lname = r.sanitize(self._fld(b, "LIST"))
            return f"{pad}{lname}.replace({self._inp(b,'INDEX')}, {self._inp(b,'ITEM')});"
        if op == "data_showlist":
            lname = r.sanitize(self._fld(b, "LIST"))
            return f"{pad}{lname}.show();"
        if op == "data_hidelist":
            lname = r.sanitize(self._fld(b, "LIST"))
            return f"{pad}{lname}.hide();"

        # ── Pen ───────────────────────────────────────
        if op == "pen_penDown":             return f"{pad}penDown();"
        if op == "pen_penUp":               return f"{pad}penUp();"
        if op == "pen_setPenColorToColor":  return f"{pad}setPenColor({self._inp(b,'COLOR')});"
        if op == "pen_changePenColorBy":    return f"{pad}changePenColor({self._inp(b,'COLOR')});"
        if op == "pen_setPenSizeTo":        return f"{pad}setPenSize({self._inp(b,'SIZE')});"
        if op == "pen_changePenSizeBy":     return f"{pad}changePenSize({self._inp(b,'SIZE')});"
        if op == "pen_stamp":               return f"{pad}stampPen();"
        if op == "pen_clear":               return f"{pad}erasePen();"
        # Pen colour-param variant (setPenColorParamTo / changePenColorParam)
        if op == "pen_setPenColorParamTo":
            param = self._menu_field(b, "COLOR_PARAM", "colorParam")
            return f"{pad}/* setPenColorParam(\"{param}\", {self._inp(b,'VALUE')}); */"
        if op == "pen_changePenColorParamBy":
            param = self._menu_field(b, "COLOR_PARAM", "colorParam")
            return f"{pad}/* changePenColorParam(\"{param}\", {self._inp(b,'VALUE')}); */"

        # ── Music extension ───────────────────────────
        if op == "music_playDrumForBeats":
            drum = self._menu_field(b, "DRUM", "DRUM")
            return f"{pad}playDrum({drum}, {self._inp(b,'BEATS')});"
        if op == "music_restForBeats":
            return f"{pad}restForBeats({self._inp(b,'BEATS')});"
        if op == "music_playNoteForBeats":
            note = self._menu_field(b, "NOTE", "NOTE")
            return f"{pad}playNote({note}, {self._inp(b,'BEATS')});"
        if op == "music_setInstrument":
            instr = self._menu_field(b, "INSTRUMENT", "INSTRUMENT")
            return f"{pad}setInstrument({instr});"
        if op == "music_setTempo":
            return f"{pad}setTempo({self._inp(b,'TEMPO')});"
        if op == "music_changeTempo":
            return f"{pad}changeTempo({self._inp(b,'TEMPO')});"
        if op in ("music_midiPlayDrumForBeats",):
            return f"{pad}/* {op} */"

        # ── Video Sensing extension ───────────────────
        if op == "videoSensing_videoToggle":
            state = self._menu_field(b, "VIDEO_STATE", "VIDEO_STATE")
            if state == "on":         return f"{pad}videoOn();"
            if state == "off":        return f"{pad}videoOff();"
            if state == "on-flipped": return f"{pad}videoFlipped();"
            return f'{pad}/* videoSensing_videoToggle("{state}") */'
        if op == "videoSensing_setVideoTransparency":
            return f"{pad}setVideoTransparency({self._inp(b,'TRANSPARENCY')});"

        # ── Text2Speech extension ─────────────────────
        if op == "text2speech_speakAndWait":
            return f"{pad}speak({self._inp(b,'WORDS')});"
        if op == "text2speech_setVoice":
            voice = self._menu_field(b, "VOICE", "VOICE")
            return f'{pad}setVoice("{voice}");'
        if op == "text2speech_setLanguage":
            lang = self._menu_field(b, "LANGUAGE", "LANGUAGE")
            return f'{pad}setLanguage("{lang}");'

        # ── Translate extension ───────────────────────
        # (translate_getTranslate is a reporter, not a statement – handled in ExprGen)

        # ── MakeyMakey extension ──────────────────────
        # No new statement blocks (uses standard events)

        # ── Microbit extension ────────────────────────
        if op.startswith("microbit_"):
            return f"{pad}/* {op} */"

        # ── EV3 extension ─────────────────────────────
        if op.startswith("ev3_"):
            return f"{pad}/* {op} */"

        # ── Boost extension ───────────────────────────
        if op.startswith("boost_"):
            return f"{pad}/* {op} */"

        # ── WeDo 2.0 extension ────────────────────────
        if op.startswith("wedo2_"):
            return f"{pad}/* {op} */"

        # ── GDX FOR extension ─────────────────────────
        if op.startswith("gdxfor_"):
            return f"{pad}/* {op} */"

        # ── Custom Block Call ─────────────────────────
        if op == "procedures_call":
            mutation  = b.get("mutation", {})
            proccode  = mutation.get("proccode", "?")
            try:
                arg_ids = json.loads(mutation.get("argumentids", "[]"))
            except Exception:
                arg_ids = []
            # Prozedurname sanitizen
            pname_raw = re.split(r' %[snb]', proccode)[0].strip()
            pname = sanitize_identifier(pname_raw)
            args = []
            for aid in arg_ids:
                raw = b.get("inputs", {}).get(aid)
                if not raw or len(raw) < 2:
                    args.append('""')
                    continue
                val = raw[1]
                if isinstance(val, list):
                    kind = val[0] if val else 10
                    rv   = val[1] if len(val) >= 2 else ""
                    args.append(_num(rv) if kind in (4,5,6,7,8) else _str(rv))
                elif isinstance(val, str) and val in self.r.blocks:
                    args.append(self.e.from_block(val))
                else:
                    args.append('""')
            return f"{pad}{pname}({', '.join(args)});"

        # Unknown block → comment
        return f"{pad}/* {op} */"


# ═══════════════════════════════════════════════════════
#  Target-Decompiler
# ═══════════════════════════════════════════════════════

class TargetDecompiler:
    def __init__(self, target: dict, global_name_map: dict = None):
        """
        global_name_map: Mapping für globale (Stage-)Variablen, damit
        Sprites die Stage-Variablen unter dem sanitisierten Namen referenzieren.
        """
        self.target = target

        # Alle Namen die sanitisiert werden müssen sammeln:
        # Variablen, Listen, Custom-Block-Argumente, Sprite-/Stage-Name
        all_names: list[str] = []
        for var_id, var_data in target.get("variables", {}).items():
            all_names.append(var_data[0])
        for lst_id, lst_data in target.get("lists", {}).items():
            all_names.append(lst_data[0])
        for bid, b in target.get("blocks", {}).items():
            if b.get("opcode") == "procedures_prototype":
                m = b.get("mutation", {})
                try:
                    param_names = json.loads(m.get("argumentnames", "[]"))
                    all_names.extend(param_names)
                except Exception:
                    pass
                # Auch der Prozedurname selbst
                proccode = m.get("proccode", "")
                pname_raw = re.split(r' %[snb]', proccode)[0].strip()
                if pname_raw:
                    all_names.append(pname_raw)

        self._local_name_map = build_name_map(all_names)

        # Globale Namen (Stage-Variablen) übernehmen und lokale hinzufügen
        combined_map = dict(global_name_map or {})
        combined_map.update(self._local_name_map)

        self.resolver = BlockResolver(
            target.get("blocks", {}),
            target.get("comments", {}),
            name_map=combined_map,
        )
        self.expr = ExprGen(self.resolver)
        self.stmt = StmtGen(self.resolver, self.expr)

    @property
    def name_map(self) -> dict:
        return self._local_name_map

    def decompile(self) -> str:
        t        = self.target
        is_stage = t.get("isStage", False)
        kind     = "Stage" if is_stage else "Sprite"
        raw_name = t.get("name", "Unbekannt")
        name     = sanitize_identifier(raw_name)

        # ── Körper vorgenerieren (für Rename-Erkennung) ──────
        # Assets
        asset_lines = []
        for c in t.get("costumes", []):
            tag = "addBackdrop" if is_stage else "addCostume"
            asset_lines.append(f'    {tag}("{c.get("name","?")}");')
        for s in t.get("sounds", []):
            asset_lines.append(f'    addSound("{s.get("name","?")}");')

        # Variables + Lists
        var_lines = []
        scope_tag = "public" if is_stage else "private"
        for var_id, var_data in t.get("variables", {}).items():
            vname_raw = var_data[0]
            vname     = self.resolver.sanitize(vname_raw)
            vval      = var_data[1]
            val_str   = _num(vval) if _looks_num(vval) else _str(str(vval))
            suffix    = f"  // war: {repr(vname_raw)}" if vname != vname_raw else ""
            var_lines.append(f"    {scope_tag} var {vname} = {val_str};{suffix}")
        for lst_id, lst_data in t.get("lists", {}).items():
            lname_raw = lst_data[0]
            lname     = self.resolver.sanitize(lname_raw)
            suffix    = f"  // war: {repr(lname_raw)}" if lname != lname_raw else ""
            var_lines.append(f"    // var {lname} = [];  // Liste{suffix}")

        # Custom defs + scripts
        def_lines = []
        for cdef in self._find_custom_defs():
            for l in cdef: def_lines.append("    " + l)
            def_lines.append("")
        script_lines = []
        for script in self._find_scripts():
            for l in script: script_lines.append("    " + l)
            script_lines.append("")

        body_text = "\n".join(var_lines + def_lines + script_lines)

        # ── Welche Renames sind wirklich relevant? ───────────
        # Lokale Renames (Vars/Lists/Params dieses Targets): immer zeigen
        # Globale Renames (Stage-Vars in Sprites): nur wenn sanitisierter Name im Body vorkommt
        all_renames = {orig: san for orig, san in self.resolver.name_map.items() if orig != san}
        local_originals = set(self._local_name_map.keys())

        relevant_renames = {}
        for orig, san in all_renames.items():
            if orig in local_originals:
                relevant_renames[orig] = san          # lokale Rename → immer
            elif re.search(r'\b' + re.escape(san) + r'\b', body_text):
                relevant_renames[orig] = san          # globale Rename → nur wenn verwendet

        # Auch Sprite-/Stage-Name selbst
        if name != raw_name:
            relevant_renames[raw_name] = name

        # ── Ausgabe zusammenbauen ────────────────────────────
        lines = []
        if relevant_renames:
            lines.append("// ⚠  Folgende Namen wurden für Scrape sanitisiert (ungültige Zeichen ersetzt):")
            for orig, san in sorted(relevant_renames.items()):
                lines.append(f"//    {repr(orig)} → {san}")
            lines.append("")

        lines.append(f"public {kind} {name} {{")
        if asset_lines:
            lines.extend(asset_lines)
            lines.append("")
        if var_lines:
            lines.extend(var_lines)
            lines.append("")
        lines.extend(def_lines)
        lines.extend(script_lines)
        lines.append("}")
        return "\n".join(lines)

    # ── Custom Defs ───────────────────────────────────

    def _find_custom_defs(self) -> list[list[str]]:
        defs = []
        for bid, b in self.resolver.blocks.items():
            if b.get("opcode") == "procedures_definition" and b.get("topLevel"):
                defs.append(self._gen_custom_def(bid, b))
        return defs

    def _gen_custom_def(self, hat_id, hat_block) -> list[str]:
        r = self.resolver
        proto_id = r.input_block(hat_block, "custom_block")
        proto    = r.blocks.get(proto_id, {}) if proto_id else {}
        mutation = proto.get("mutation", {})
        proccode = mutation.get("proccode", "block")

        try:
            param_names = json.loads(mutation.get("argumentnames", "[]"))
        except Exception:
            param_names = []

        warp  = mutation.get("warp", "false") == "true"
        types = re.findall(r'%[snb]', proccode)
        pname_raw = re.split(r' %[snb]', proccode)[0].strip()
        pname = sanitize_identifier(pname_raw)

        type_prefix = {"%s": "", "%n": "number ", "%b": "boolean "}
        params = []
        for i, pn in enumerate(param_names):
            tc = types[i] if i < len(types) else "%s"
            # Parameternamen ebenfalls sanitizen
            pn_clean = r.sanitize(pn)
            params.append(f"{type_prefix.get(tc,'')}{pn_clean}")

        mod = "private " if warp else ""
        sig = f"{mod}void {pname}({', '.join(params)}) {{"

        body = []
        if hat_block.get("next"):
            body = self.stmt.chain_to_lines(hat_block["next"], level=1)

        return [sig] + body + ["}"]

    # ── Event Scripts ─────────────────────────────────

    def _find_scripts(self) -> list[list[str]]:
        scripts = []
        for bid, b in self.resolver.blocks.items():
            op = b.get("opcode", "")
            if not b.get("topLevel"):
                continue
            if op == "procedures_definition":
                continue
            s = self._gen_script(bid, b, op)
            if s:
                scripts.append(s)
        return scripts

    def _gen_script(self, hat_id, hat_block, op) -> list[str] | None:
        r = self.resolver

        if op == "event_whenflagclicked":
            header = "onFlagClicked {"
        elif op == "event_whenkeypressed":
            key = r.field(hat_block, "KEY_OPTION") or "space"
            header = f'onKeyPressed("{key}") {{'
        elif op in ("event_whenthisspriteclicked", "event_whenstageclicked"):
            header = "onSpriteClicked {"
        elif op == "event_whenbackdropswitchesto":
            bd = r.field(hat_block, "BACKDROP") or "?"
            header = f'onBackdropChanged("{bd}") {{'
        elif op == "event_whenbroadcastreceived":
            msg = r.field(hat_block, "BROADCAST_OPTION") or "?"
            header = f'onBroadcastReceived("{msg}") {{'
        elif op == "control_start_as_clone":
            header = "onCloneCreated {"
        else:
            body = []
            if hat_block.get("next"):
                body = self.stmt.chain_to_lines(hat_block["next"], level=1)
            comment_lines = [f"// [unbekannter Hat-Block: {op}]"]
            for line in body:
                comment_lines.append("// " + line)
            return comment_lines

        body = []
        if hat_block.get("next"):
            body = self.stmt.chain_to_lines(hat_block["next"], level=1)

        return [header] + body + ["}"]


# ═══════════════════════════════════════════════════════
#  Haupt-Decompiler
# ═══════════════════════════════════════════════════════

def decompile_sb3(sb3_path: str) -> str:
    project  = read_sb3(sb3_path)
    targets  = project.get("targets", [])
    exts     = project.get("extensions", [])

    lines = []

    # Extensions → imports
    EXT_REVERSE = {
        "pen": "pen", "music": "music", "videoSensing": "video",
        "text2speech": "text2speech", "translate": "translate",
        "makeymakey": "makey", "microbit": "microbit",
        "ev3": "ev3", "boost": "boost", "wedo2": "wedo", "gdxfor": "gdxfor",
    }
    for ext in exts:
        name = EXT_REVERSE.get(ext, ext)
        lines.append(f'import "{name}";')
    if exts:
        lines.append("")

    # Stage first, then sprites
    # Stage-Variablen global bekannt machen (damit Sprites sie sanitisiert referenzieren)
    stage   = next((t for t in targets if t.get("isStage")), None)
    sprites = [t for t in targets if not t.get("isStage")]

    global_name_map: dict[str, str] = {}
    if stage:
        # Stage-Variablen und -Listen vorberechnen
        all_global = [v[0] for v in stage.get("variables", {}).values()]
        all_global += [l[0] for l in stage.get("lists", {}).values()]
        global_name_map = build_name_map(all_global)

    for target in ([stage] if stage else []) + sprites:
        dc = TargetDecompiler(target, global_name_map=global_name_map)
        lines.append(dc.decompile())
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ═══════════════════════════════════════════════════════
#  Einmaliger Lauf
# ═══════════════════════════════════════════════════════

def compile_once(src_path: Path, out_path: Path, verbose=True) -> bool:
    try:
        if verbose:
            print(f"── [1] Lese {src_path.name} ──────────────────")
        code = decompile_sb3(str(src_path))

        if verbose:
            print(f"── [2] Schreibe {out_path.name} ────────────────")
        out_path.write_text(code, encoding="utf-8")

        lines = code.count("\n")
        size  = out_path.stat().st_size
        if verbose:
            print(f"✓  {out_path}  ({lines} Zeilen, {size:,} Bytes)")
        return True
    except zipfile.BadZipFile:
        print(f"  ✗  Keine gültige .sb3-Datei: {src_path}")
        return False
    except Exception as e:
        print(f"  ✗  Fehler: {e}")
        import traceback; traceback.print_exc()
        return False


# ═══════════════════════════════════════════════════════
#  Watch-Modus
# ═══════════════════════════════════════════════════════

def watch_mode(src_path: Path, out_path: Path):
    print(f"👁  Watch-Modus aktiv – beobachte: {src_path}")
    print("   Ctrl+C zum Beenden\n")
    last_mtime = None
    first_run  = True

    while True:
        try:
            mtime = src_path.stat().st_mtime
        except FileNotFoundError:
            print(f"  ⚠  Datei nicht gefunden: {src_path}")
            time.sleep(1)
            continue

        if mtime != last_mtime:
            last_mtime = mtime
            if not first_run:
                print(f"\n{'─'*45}")
                print(f"🔄  Änderung erkannt – {time.strftime('%H:%M:%S')}")
            first_run = False
            compile_once(src_path, out_path)
            print("\n   Warte auf Änderungen...")

        time.sleep(0.5)


# ═══════════════════════════════════════════════════════
#  Hilfe
# ═══════════════════════════════════════════════════════

def print_help():
    print("""
Detranspiler.py  v1.3
────────────────────────────────────────────────────────
VERWENDUNG:
  python detranspiler.py <eingabe.sb3> [Optionen]

OPTIONEN:
  --output <datei.scrape>   Ausgabedatei (Standard: output.scrape)
  --watch                    Watch-Modus: detranspiliert bei Dateiänderung neu
  --help                     Diese Hilfe anzeigen

BEISPIELE:
  python detranspiler.py spiel.sb3
  python detranspiler.py spiel.sb3 --output spiel.scrape
  python detranspiler.py spiel.sb3 --watch
  python detranspiler.py spiel.sb3 --output meinspiel.scrape --watch

ERWEITERUNGEN:
  Erweiterungsbefehle werden automatisch erkannt und als Scrape-Code ausgegeben.
  Unterstützte Erweiterungen: Pen, Music, Video Sensing, Text2Speech, Translate.
  Hardware-Erweiterungen (Microbit, EV3, Boost, WeDo, GDX FOR) werden als
  /* opcode */ Kommentare ausgegeben.

Identifier-Sanitisierung:
  Variablen- und Sprite-Namen die in Scratch gültig sind, aber ungültige
  Zeichen für Scrape enthalten (z.B. #, -, Leerzeichen), werden automatisch
  bereinigt:  Song# → Song_   my-var → my_var   2fast → _2fast
  Am Anfang jedes betroffenen Targets erscheint ein Kommentar mit dem Mapping.
""")


# ═══════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args    = sys.argv[1:]
    infile  = None
    outfile = "output.scrape"
    watch   = False

    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--output", "--out") and i + 1 < len(args):
            outfile = args[i + 1]; i += 2
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

    out_path = Path(outfile).resolve()
    print(f"Lese: {src_path}")

    if watch:
        try:
            watch_mode(src_path, out_path)
        except KeyboardInterrupt:
            print("\n👋  Watch-Modus beendet.")
        return

    success = compile_once(src_path, out_path)
    if not success:
        sys.exit(1)

    print("\n── Fertig! ──────────────────────────────────")
    print(f"   Öffne {out_path} in deinem Editor.")


if __name__ == "__main__":
    main()
