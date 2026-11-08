"""
Detranspiler.py  v1.0
══════════════════════════════════════════════
Scratch 3 / TurboWarp .sb3  →  Java-ähnliche Syntax

Unterstützt alle Blöcke aus Transpiler.py v5.0:
  • Motion, Looks, Sound, Events, Control
  • Sensing, Operators, Data (Variablen, Listen)
  • Pen-Erweiterung
  • Custom Blocks (define / void)
  • Kommentare (Scratch Comments → // Kommentare)
  • Watch-Modus (--watch)
  • --output <datei.scratch>
"""

import json, zipfile, sys, time, re
from pathlib import Path


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
    def __init__(self, blocks: dict, comments: dict = None):
        self.blocks = blocks
        self.comments = comments or {}
        self._cmap = {
            c["blockId"]: c["text"]
            for c in self.comments.values()
            if c.get("blockId")
        }

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
                return str(raw)
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

        # Variables / Lists
        if op == "data_variable":
            return r.field(b, "VARIABLE") or "?"
        if op == "data_itemoflist":
            return f"{r.field(b,'LIST') or '?'}[{self._i(b,'INDEX')}]"
        if op == "data_lengthoflist":
            return f"{r.field(b,'LIST') or '?'}.length()"
        if op == "data_listcontainsitem":
            return f"{r.field(b,'LIST') or '?'}.contains({self._i(b,'ITEM')})"
        if op == "data_itemnumoflist":
            return f"{r.field(b,'LIST') or '?'}.indexOf({self._i(b,'ITEM')})"

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

        # Custom block argument reporters
        if op in ("argument_reporter_string_number", "argument_reporter_boolean"):
            return r.field(b, "VALUE") or "?"

        # Looks reporters
        if op == "looks_costumenumbername":
            return f"/* costume {r.field(b,'NUMBER_NAME') or 'number'} */"
        if op == "looks_backdropnumbername":
            return f"/* backdrop {r.field(b,'NUMBER_NAME') or 'number'} */"
        if op == "looks_size":
            return "/* size */"

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
            name = self._fld(b, "VARIABLE")
            val  = self._inp(b, "VALUE")
            return f"{pad}{name} = {val};"
        if op == "data_changevariableby":
            name = self._fld(b, "VARIABLE")
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
            return f'{pad}showVar("{self._fld(b,"VARIABLE")}");'
        if op == "data_hidevariable":
            return f'{pad}hideVar("{self._fld(b,"VARIABLE")}");'

        # ── Data: Lists ───────────────────────────────
        if op == "data_addtolist":
            return f"{pad}{self._fld(b,'LIST')}.add({self._inp(b,'ITEM')});"
        if op == "data_deleteoflist":
            return f"{pad}{self._fld(b,'LIST')}.delete({self._inp(b,'INDEX')});"
        if op == "data_insertatlist":
            return f"{pad}{self._fld(b,'LIST')}.insert({self._inp(b,'INDEX')}, {self._inp(b,'ITEM')});"
        if op == "data_replaceitemoflist":
            return f"{pad}{self._fld(b,'LIST')}.replace({self._inp(b,'INDEX')}, {self._inp(b,'ITEM')});"
        if op == "data_showlist":
            return f"{pad}{self._fld(b,'LIST')}.show();"
        if op == "data_hidelist":
            return f"{pad}{self._fld(b,'LIST')}.hide();"

        # ── Pen ───────────────────────────────────────
        if op == "pen_penDown":             return f"{pad}penDown();"
        if op == "pen_penUp":               return f"{pad}penUp();"
        if op == "pen_setPenColorToColor":  return f"{pad}setPenColor({self._inp(b,'COLOR')});"
        if op == "pen_changePenColorBy":    return f"{pad}changePenColor({self._inp(b,'COLOR')});"
        if op == "pen_setPenSizeTo":        return f"{pad}setPenSize({self._inp(b,'SIZE')});"
        if op == "pen_changePenSizeBy":     return f"{pad}changePenSize({self._inp(b,'SIZE')});"
        if op == "pen_stamp":               return f"{pad}stampPen();"
        if op == "pen_clear":               return f"{pad}erasePen();"

        # ── Custom Block Call ─────────────────────────
        if op == "procedures_call":
            mutation  = b.get("mutation", {})
            proccode  = mutation.get("proccode", "?")
            try:
                arg_ids = json.loads(mutation.get("argumentids", "[]"))
            except Exception:
                arg_ids = []
            pname = re.split(r' %[snb]', proccode)[0].strip()
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
    def __init__(self, target: dict):
        self.target   = target
        self.resolver = BlockResolver(
            target.get("blocks", {}),
            target.get("comments", {})
        )
        self.expr = ExprGen(self.resolver)
        self.stmt = StmtGen(self.resolver, self.expr)

    def decompile(self) -> str:
        t        = self.target
        is_stage = t.get("isStage", False)
        kind     = "Stage" if is_stage else "Sprite"
        name     = t.get("name", "Unbekannt")

        lines = [f"public {kind} {name} {{"]

        # Assets
        for c in t.get("costumes", []):
            cname = c.get("name", "?")
            tag = "addBackdrop" if is_stage else "addCostume"
            lines.append(f'    {tag}("{cname}");')
        for s in t.get("sounds", []):
            lines.append(f'    addSound("{s.get("name","?")}");')

        if t.get("costumes") or t.get("sounds"):
            lines.append("")

        # Variables
        scope_tag = "public" if is_stage else "private"
        for var_id, var_data in t.get("variables", {}).items():
            vname = var_data[0]
            vval  = var_data[1]
            val_str = _num(vval) if _looks_num(vval) else _str(str(vval))
            lines.append(f"    {scope_tag} var {vname} = {val_str};")

        # Lists (just declare as comments — no init syntax in the language)
        for lst_id, lst_data in t.get("lists", {}).items():
            lines.append(f"    // var {lst_data[0]} = [];  // Liste")

        if t.get("variables") or t.get("lists"):
            lines.append("")

        # Custom block definitions
        for cdef in self._find_custom_defs():
            for l in cdef:
                lines.append("    " + l)
            lines.append("")

        # Event scripts
        for script in self._find_scripts():
            for l in script:
                lines.append("    " + l)
            lines.append("")

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
        pname = re.split(r' %[snb]', proccode)[0].strip()

        type_prefix = {"%s": "", "%n": "number ", "%b": "boolean "}
        params = []
        for i, pn in enumerate(param_names):
            tc = types[i] if i < len(types) else "%s"
            params.append(f"{type_prefix.get(tc,'')}{pn}")

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
            # Unbekannter Hat-Block: Body als Kommentar ausgeben, kein kaputtes { }
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
    stage   = next((t for t in targets if t.get("isStage")), None)
    sprites = [t for t in targets if not t.get("isStage")]
    for target in ([stage] if stage else []) + sprites:
        dc = TargetDecompiler(target)
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
Detranspiler.py  v1.0
────────────────────────────────────────────────────────
VERWENDUNG:
  python detranspiler.py <eingabe.sb3> [Optionen]

OPTIONEN:
  --output <datei.scratch>   Ausgabedatei (Standard: output.scratch)
  --watch                    Watch-Modus: detranspiliert bei Dateiänderung neu
  --help                     Diese Hilfe anzeigen

BEISPIELE:
  python detranspiler.py spiel.sb3
  python detranspiler.py spiel.sb3 --output spiel.scratch
  python detranspiler.py spiel.sb3 --watch
  python detranspiler.py spiel.sb3 --output meinspiel.scratch --watch

Keine temporären Dateien außerhalb des Ausgabepfads.
""")


# ═══════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args    = sys.argv[1:]
    infile  = None
    outfile = "output.scratch"
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
