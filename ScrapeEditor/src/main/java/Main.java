import com.formdev.flatlaf.FlatDarkLaf;
import com.formdev.flatlaf.FlatLightLaf;
import org.fife.ui.rsyntaxtextarea.RSyntaxTextArea;
import org.fife.ui.rsyntaxtextarea.SyntaxConstants;
import org.fife.ui.rsyntaxtextarea.Theme;
import org.fife.ui.rtextarea.RTextScrollPane;

import javax.swing.*;
import javax.swing.text.*;
import javax.swing.event.DocumentEvent;
import javax.swing.event.DocumentListener;
import java.awt.*;
import java.awt.event.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.awt.datatransfer.StringSelection;
import java.util.*;
import java.util.List;
import java.util.prefs.Preferences;

public class Main extends JFrame {

    // ═══════════════════════════════════════════════════════
    //  AUTOCOMPLETE DATEN
    //  Jeder Eintrag: { trigger, insertText, displayLabel, description, cursorOffset }
    //  cursorOffset = wie viele Zeichen vom Ende zurück der Cursor gesetzt wird
    // ═══════════════════════════════════════════════════════
    static class AcEntry {
        final String trigger;      // Was getippt wird (für Matching)
        final String insert;       // Was eingefügt wird (vollständiger Text)
        final String label;        // Anzeige im Popup
        final String description;  // Beschreibung rechts
        final int    cursorBack;   // Cursor X Zeichen vom Ende zurücksetzen (0 = am Ende)

        AcEntry(String trigger, String insert, String label, String description, int cursorBack) {
            this.trigger     = trigger;
            this.insert      = insert;
            this.label       = label;
            this.description = description;
            this.cursorBack  = cursorBack;
        }
    }

    private static final List<AcEntry> AC_ENTRIES = new ArrayList<>();

    static {
        // ── Struktur & Deklaration ────────────────────────────────────
        ac("public",        "public ",                          "public",              "Öffentlicher Modifikator (global, alle Sprites)",  0);
        ac("private",       "private ",                         "private",             "Privater Modifikator (nur dieser Sprite)",          0);
        ac("shown",         "shown ",                           "shown",               "Variablen-Monitor anzeigen",                        0);
        ac("hidden",        "hidden ",                          "hidden",              "Variablen-Monitor verstecken",                      0);
        ac("Sprite",        "Sprite ",                          "Sprite",              "Definiert einen neuen Sprite",                      0);
        ac("Stage",         "Stage ",                           "Stage",               "Definiert die Stage (Bühne)",                       0);
        ac("var",           "var  = ;",                         "var",                 "Variable deklarieren: var name = wert;",            3);
        ac("void",          "void () {\n\t\n}",                 "void name()",         "Eigenen Block definieren (ohne Warp)",               6);
        ac("define",        "define () {\n\t\n}",               "define name()",       "Eigenen Block definieren",                          6);
        ac("import",        "import \"\";",                     "import",              "Erweiterung importieren",                   2);

        // ── Events ────────────────────────────────────────────────────
        ac("onFlagClicked",       "onFlagClicked {\n\t\n}",                         "onFlagClicked",              "Wird bei Klick auf grüne Flagge ausgeführt",       3);
        ac("onKeyPressed",        "onKeyPressed(\"space\") {\n\t\n}",               "onKeyPressed(\"key\")",       "Wird bei Tastenklick ausgeführt",                  11);
        ac("onSpriteClicked",     "onSpriteClicked {\n\t\n}",                       "onSpriteClicked",            "Wird bei Klick auf diesen Sprite ausgeführt",       3);
        ac("onBackdropChanged",   "onBackdropChanged(\"Backdrop1\") {\n\t\n}",      "onBackdropChanged(\"name\")", "Wird bei Hintergrundwechsel ausgeführt",            11);
        ac("onBroadcastReceived", "onBroadcastReceived(\"message\") {\n\t\n}",      "onBroadcastReceived(\"msg\")", "Wird bei Nachrichtenempfang ausgeführt",           11);

        // ── Kontrollfluss ─────────────────────────────────────────────
        ac("repeat",       "repeat () {\n\t\n}",               "repeat(n)",           "Wiederholt einen Block n-mal",                      7);
        ac("forever",      "forever {\n\t\n}",                 "forever",             "Wiederholt einen Block für immer",                   3);
        ac("if",           "if () {\n\t\n}",                   "if (bedingung)",      "Bedingte Ausführung",                               7);
        ac("else",         "else {\n\t\n}",                    "else",                "Alternative bei falscher if-Bedingung",              3);
        ac("elseif",       "elseif () {\n\t\n}",               "elseif (bedingung)",  "Sonst-wenn-Bedingung",                              7);
        ac("repeatUntil",  "repeatUntil () {\n\t\n}",          "repeatUntil(bedg.)",  "Wiederholt bis Bedingung wahr ist",                 7);
        ac("waitUntil",    "waitUntil ();",                     "waitUntil(bedg.)",    "Wartet bis Bedingung wahr ist",                     2);
        ac("stop",         "stop(\"all\");",                    "stop(\"all\")",        "Stoppe: all / this script / other scripts",          6);
        ac("deleteClone",  "deleteClone();",                    "deleteClone()",       "Löscht den aktuellen Klon",                         0);

        // ── Warten ────────────────────────────────────────────────────
        ac("wait",         "wait();",                           "wait(secs)",          "Wartet n Sekunden",                                 2);

        // ── Klone ─────────────────────────────────────────────────────
        ac("createClone",  "createClone(\"myself\");",          "createClone(\"name\")", "Erstellt einen Klon: myself oder Sprite-Name",     10);

        // ── Bewegung ──────────────────────────────────────────────────
        ac("move",         "move();",                           "move(steps)",         "Bewegt Sprite um n Schritte",                       2);
        ac("turnLeft",     "turnLeft();",                       "turnLeft(degrees)",   "Dreht Sprite links um n Grad",                      2);
        ac("turnRight",    "turnRight();",                      "turnRight(degrees)",  "Dreht Sprite rechts um n Grad",                     2);
        ac("goTo",         "goTo(, );",                         "goTo(x, y)",          "Setzt Position auf x, y",                           3);
        ac("goToSprite",   "goToSprite(\"\");",                 "goToSprite(\"name\")", "Geht zu einem anderen Sprite",                     3);
        ac("glide",        "glide(, , );",                      "glide(secs, x, y)",   "Gleitet in secs Sekunden zu x, y",                  3);
        ac("glideToSprite","glideToSprite(\"\", );",            "glideToSprite(\"name\", secs)", "Gleitet zu einem Sprite",                 4);
        ac("pointDir",     "pointDir();",                       "pointDir(degrees)",   "Setzt Richtung auf n Grad (0=oben, 90=rechts)",     2);
        ac("pointTowards", "pointTowards(\"\");",               "pointTowards(\"name\")", "Zeigt zum Mauszeiger oder Sprite",               3);
        ac("setX",         "setX();",                           "setX(x)",             "Setzt X-Position",                                  2);
        ac("setY",         "setY();",                           "setY(y)",             "Setzt Y-Position",                                  2);
        ac("changeX",      "changeX();",                        "changeX(dx)",         "Ändert X-Position um dx",                           2);
        ac("changeY",      "changeY();",                        "changeY(dy)",         "Ändert Y-Position um dy",                           2);
        ac("bounceOnEdge", "bounceOnEdge();",                   "bounceOnEdge()",      "Prallt am Rand ab",                                 0);
        ac("setRotationStyle", "setRotationStyle(\"left-right\");", "setRotationStyle(\"..\")", "Drehstil: left-right / don't rotate / all around", 14);

        // ── Aussehen ──────────────────────────────────────────────────
        ac("say",            "say(\"\");",                      "say(\"text\")",          "Sprechblase anzeigen (dauerhaft)",               3);
        ac("sayFor",         "sayFor(\"\", );",                 "sayFor(\"text\", secs)", "Sprechblase für n Sekunden",                     4);
        ac("think",          "think(\"\");",                    "think(\"text\")",        "Denkblase anzeigen (dauerhaft)",                 3);
        ac("thinkFor",       "thinkFor(\"\", );",               "thinkFor(\"text\", secs)", "Denkblase für n Sekunden",                     4);
        ac("animate",        "animate(\"\", \"\", );",          "animate(\"k1\", \"k2\", secs)", "Animiert zwischen zwei Kostümen",          4);
        ac("switchCostume",  "switchCostume(\"\");",            "switchCostume(\"name\")", "Wechselt zu einem bestimmten Kostüm",           3);
        ac("nextCostume",    "nextCostume();",                  "nextCostume()",           "Wechselt zum nächsten Kostüm",                  0);
        ac("switchBackdrop", "switchBackdrop(\"\");",           "switchBackdrop(\"name\")", "Wechselt zu einem bestimmten Hintergrund",     3);
        ac("nextBackdrop",   "nextBackdrop();",                 "nextBackdrop()",           "Wechselt zum nächsten Hintergrund",             0);
        ac("setSize",        "setSize();",                      "setSize(percent)",         "Setzt Größe in Prozent",                        2);
        ac("changeSize",     "changeSize();",                   "changeSize(delta)",        "Ändert Größe um delta",                         2);
        ac("show",           "show();",                         "show()",                   "Zeigt den Sprite an",                           0);
        ac("hide",           "hide();",                         "hide()",                   "Versteckt den Sprite",                          0);
        ac("goToFront",      "goToFront();",                    "goToFront()",              "Bringt Sprite in den Vordergrund",              0);
        ac("goToBack",       "goToBack();",                     "goToBack()",               "Schickt Sprite in den Hintergrund",             0);
        ac("goForwardLayers","goForwardLayers();",              "goForwardLayers(n)",        "Bewegt Sprite n Ebenen nach vorne",            2);
        ac("goBackwardLayers","goBackwardLayers();",            "goBackwardLayers(n)",       "Bewegt Sprite n Ebenen nach hinten",           2);
        ac("setEffect",      "setEffect(\"color\", );",         "setEffect(\"name\", val)",  "Setzt Grafikeffekt: color/fisheye/whirl/...",  4);
        ac("changeEffect",   "changeEffect(\"color\", );",      "changeEffect(\"name\", val)","Ändert Grafikeffekt",                         4);
        ac("clearEffects",   "clearEffects();",                 "clearEffects()",            "Entfernt alle Grafikeffekte",                  0);

        // ── Sound ─────────────────────────────────────────────────────
        ac("playSound",          "playSound(\"\");",            "playSound(\"name\")",         "Startet Sound (ohne warten)",                3);
        ac("playSoundUntilDone", "playSoundUntilDone(\"\");",   "playSoundUntilDone(\"name\")", "Spielt Sound und wartet bis fertig",        3);
        ac("stopAllSounds",      "stopAllSounds();",            "stopAllSounds()",              "Stoppt alle Sounds",                        0);
        ac("setVolume",          "setVolume();",                "setVolume(percent)",           "Setzt Lautstärke in Prozent",               2);
        ac("changeVolume",       "changeVolume();",             "changeVolume(delta)",          "Ändert Lautstärke um delta",                2);

        // ── Nachrichten & Interaktion ─────────────────────────────────
        ac("broadcast",        "broadcast(\"\");",           "broadcast(\"msg\")",          "Sendet eine Nachricht",                         3);
        ac("broadcastAndWait", "broadcastAndWait(\"\");",    "broadcastAndWait(\"msg\")",   "Sendet Nachricht und wartet bis alle fertig",   3);
        ac("askAndWait",       "askAndWait(\"\");",          "askAndWait(\"frage\")",        "Fragt und wartet auf Antwort (→ answer)",      3);
        ac("setDragMode",      "setDragMode(\"draggable\");","setDragMode(\"draggable\")",   "Ziehmodus: draggable / not draggable",         12);
        ac("resetTimer",       "resetTimer();",              "resetTimer()",                 "Setzt den Timer zurück",                       0);

        // ── Variablen-Monitor ─────────────────────────────────────────
        ac("showVar",  "showVar(\"\");",                     "showVar(\"name\")",   "Zeigt Variablen-Monitor an",                           3);
        ac("hideVar",  "hideVar(\"\");",                     "hideVar(\"name\")",   "Versteckt Variablen-Monitor",                          3);
        ac("showList", "showList(\"\");",                    "showList(\"name\")",  "Zeigt Listen-Monitor an",                              3);
        ac("hideList", "hideList(\"\");",                    "hideList(\"name\")",  "Versteckt Listen-Monitor",                             3);

        // ── Assets ────────────────────────────────────────────────────
        ac("addCostume",  "addCostume(\"\");",               "addCostume(\"name\")",            "Fügt Kostüm hinzu (aus Bibliothek oder Datei)", 3);
        ac("addBackdrop", "addBackdrop(\"\");",              "addBackdrop(\"name\")",           "Fügt Hintergrund hinzu",                        3);
        ac("addSound",    "addSound(\"\");",                 "addSound(\"name\")",              "Fügt Sound hinzu",                              3);

        // ── Stift ─────────────────────────────────────────────────────
        ac("penDown",         "penDown();",                  "penDown()",           "Stift absenken",                                        0);
        ac("penUp",           "penUp();",                    "penUp()",             "Stift anheben",                                         0);
        ac("setPenColor",     "setPenColor();",              "setPenColor(color)",  "Setzt Stiftfarbe (Zahl oder Hex)",                      2);
        ac("changePenColor",  "changePenColor();",           "changePenColor(d)",   "Ändert Stiftfarbe",                                     2);
        ac("setPenSize",      "setPenSize();",               "setPenSize(size)",    "Setzt Stiftgröße",                                      2);
        ac("changePenSize",   "changePenSize();",            "changePenSize(d)",    "Ändert Stiftgröße",                                     2);
        ac("stampPen",        "stampPen();",                 "stampPen()",          "Stempelt Abbild des Sprites",                           0);
        ac("erasePen",        "erasePen();",                 "erasePen()",          "Löscht alle Stiftspuren",                               0);

        // ── Math-Funktionen ───────────────────────────────────────────
        ac("Math.random",  "Math.random(, )",              "Math.random(von, bis)",  "Zufallszahl zwischen von und bis",                 2);
        ac("Math.round",   "Math.round()",                 "Math.round(n)",           "Rundet auf nächste ganze Zahl",                   1);
        ac("Math.abs",     "Math.abs()",                   "Math.abs(n)",             "Absolutwert (Betrag)",                            1);
        ac("Math.floor",   "Math.floor()",                 "Math.floor(n)",           "Rundet ab",                                       1);
        ac("Math.ceil",    "Math.ceil()",                  "Math.ceil(n)",            "Rundet auf",                                      1);
        ac("Math.sqrt",    "Math.sqrt()",                  "Math.sqrt(n)",            "Quadratwurzel",                                   1);
        ac("Math.sin",     "Math.sin()",                   "Math.sin(n)",             "Sinus (Grad)",                                    1);
        ac("Math.cos",     "Math.cos()",                   "Math.cos(n)",             "Cosinus (Grad)",                                  1);
        ac("Math.tan",     "Math.tan()",                   "Math.tan(n)",             "Tangens (Grad)",                                  1);
        ac("Math.asin",    "Math.asin()",                  "Math.asin(n)",            "Arcussinus",                                      1);
        ac("Math.acos",    "Math.acos()",                  "Math.acos(n)",            "Arcuscosinus",                                    1);
        ac("Math.atan",    "Math.atan()",                  "Math.atan(n)",            "Arcustangens",                                    1);
        ac("Math.ln",      "Math.ln()",                    "Math.ln(n)",              "Natürlicher Logarithmus",                         1);
        ac("Math.log",     "Math.log()",                   "Math.log(n)",             "Logarithmus (Basis 10)",                          1);

        // ── Listen-Methoden ───────────────────────────────────────────
        ac(".add",       ".add(\"\");",                     ".add(\"wert\")",           "Fügt Element zur Liste hinzu",                    3);
        ac(".delete",    ".delete();",                      ".delete(index)",           "Löscht Element an Position",                      2);
        ac(".insert",    ".insert(, \"\");",                ".insert(index, \"wert\")", "Fügt Element an Position ein",                   4);
        ac(".replace",   ".replace(, \"\");",               ".replace(index, \"wert\")","Ersetzt Element an Position",                    4);
        ac(".length",    ".length()",                       ".length()",                "Anzahl der Elemente in der Liste",                1);
        ac(".contains",  ".contains(\"\")",                 ".contains(\"wert\")",      "Prüft ob Liste den Wert enthält",                 2);

        // ── Sensoren / Werte (read-only, oft in Ausdrücken) ──────────
        ac("answer",          "answer",                    "answer",           "Antwort der letzten askAndWait()",              0);
        ac("mouseX",          "mouseX",                    "mouseX",           "Aktuelle X-Position der Maus",                  0);
        ac("mouseY",          "mouseY",                    "mouseY",           "Aktuelle Y-Position der Maus",                  0);
        ac("mouseDown",       "mouseDown",                 "mouseDown",        "Ist die Maustaste gedrückt?",                   0);
        ac("timer",           "timer",                     "timer",            "Wert des Timers in Sekunden",                   0);
        ac("loudness",        "loudness",                  "loudness",         "Lautstärke des Mikrofons (0–100)",              0);
        ac("username",        "username",                  "username",         "Benutzername",                          0);
        ac("xPosition",       "xPosition",                 "xPosition",        "Aktuelle X-Position dieses Sprites",            0);
        ac("yPosition",       "yPosition",                 "yPosition",        "Aktuelle Y-Position dieses Sprites",            0);
        ac("direction",       "direction",                 "direction",        "Aktuelle Richtung dieses Sprites",              0);
        ac("currentYear",     "currentYear",               "currentYear",      "Aktuelles Jahr",                                0);
        ac("currentMonth",    "currentMonth",              "currentMonth",     "Aktueller Monat (1–12)",                        0);
        ac("currentDate",     "currentDate",               "currentDate",      "Aktueller Tag (1–31)",                          0);
        ac("currentHour",     "currentHour",               "currentHour",      "Aktuelle Stunde (0–23)",                        0);
        ac("currentMinute",   "currentMinute",             "currentMinute",    "Aktuelle Minute (0–59)",                        0);
        ac("currentSecond",   "currentSecond",             "currentSecond",    "Aktuelle Sekunde (0–59)",                       0);
        ac("currentDayOfWeek","currentDayOfWeek",          "currentDayOfWeek", "Aktueller Wochentag (1=Mo, 7=So)",             0);
        ac("true",            "true",                      "true",             "Boolean wahr",                                  0);
        ac("false",           "false",                     "false",            "Boolean falsch",                                0);
    }

    /** Hilfsmethode zum Befüllen der Liste */
    private static void ac(String trigger, String insert, String label, String description, int cursorBack) {
        AC_ENTRIES.add(new AcEntry(trigger, insert, label, description, cursorBack));
    }

    // ═══════════════════════════════════════════════════════
    //  AUTOCOMPLETE POPUP
    // ═══════════════════════════════════════════════════════
    static class AutocompletePopup {
        private final JWindow        popup;
        private final JList<AcEntry> list;
        private final DefaultListModel<AcEntry> model;
        private final RSyntaxTextArea textArea;

        // Position im Dokument, an der der aktuelle Token beginnt
        private int tokenStart = -1;

        AutocompletePopup(RSyntaxTextArea textArea, JFrame owner) {
            this.textArea = textArea;

            popup = new JWindow(owner);
            popup.setFocusable(false);
            popup.setType(Window.Type.POPUP);

            model = new DefaultListModel<>();
            list  = new JList<>(model);
            list.setSelectionMode(ListSelectionModel.SINGLE_SELECTION);
            list.setFocusable(false);
            list.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 13));
            list.setFixedCellHeight(22);

            // Renderer: label links, description rechts (gedimmt)
            list.setCellRenderer(new DefaultListCellRenderer() {
                @Override
                public Component getListCellRendererComponent(JList<?> l, Object value,
                        int index, boolean isSelected, boolean hasFocus) {
                    AcEntry e = (AcEntry) value;
                    JPanel  p = new JPanel(new BorderLayout(8, 0));

                    JLabel lbl = new JLabel(e.label);
                    lbl.setFont(l.getFont());
                    lbl.setBorder(BorderFactory.createEmptyBorder(0, 6, 0, 0));

                    JLabel desc = new JLabel(e.description);
                    desc.setFont(l.getFont().deriveFont(Font.PLAIN, 11f));
                    desc.setForeground(isSelected ? Color.WHITE : new Color(130, 130, 130));
                    desc.setBorder(BorderFactory.createEmptyBorder(0, 0, 0, 8));

                    p.add(lbl,  BorderLayout.WEST);
                    p.add(desc, BorderLayout.EAST);

                    if (isSelected) {
                        p.setBackground(new Color(60, 110, 200));
                        lbl.setForeground(Color.WHITE);
                    } else {
                        p.setBackground(l.getBackground());
                        lbl.setForeground(l.getForeground());
                    }
                    p.setOpaque(true);
                    return p;
                }
            });

            JScrollPane scroll = new JScrollPane(list,
                JScrollPane.VERTICAL_SCROLLBAR_AS_NEEDED,
                JScrollPane.HORIZONTAL_SCROLLBAR_NEVER);
            scroll.setBorder(BorderFactory.createLineBorder(new Color(100, 100, 100)));

            popup.getContentPane().add(scroll);
            popup.setSize(520, 200);
        }

        /** Zeigt Popup mit den gefilterten Vorschlägen */
        void show(List<AcEntry> entries, int tokenStart, Point screenPos) {
            this.tokenStart = tokenStart;
            model.clear();
            for (AcEntry e : entries) model.addElement(e);
            if (model.isEmpty()) { hide(); return; }
            list.setSelectedIndex(0);
            popup.setLocation(screenPos.x, screenPos.y);
            popup.setSize(560, Math.min(entries.size(), 10) * 22 + 4);
            popup.setVisible(true);
        }

        void hide() {
            popup.setVisible(false);
            tokenStart = -1;
        }

        boolean isVisible() {
            return popup.isVisible();
        }

        /** Selektion einen nach unten */
        void selectNext() {
            int i = list.getSelectedIndex();
            if (i < model.getSize() - 1) list.setSelectedIndex(i + 1);
            list.ensureIndexIsVisible(list.getSelectedIndex());
        }

        /** Selektion einen nach oben */
        void selectPrev() {
            int i = list.getSelectedIndex();
            if (i > 0) list.setSelectedIndex(i - 1);
            list.ensureIndexIsVisible(list.getSelectedIndex());
        }

        /**
         * Fügt den ausgewählten Eintrag in das TextArea ein.
         * Ersetzt den bereits getippten Token (ab tokenStart).
         * Einrückung der aktuellen Zeile wird auf alle Folgezeilen übertragen.
         */
        boolean confirmSelection() {
            AcEntry sel = list.getSelectedValue();
            if (sel == null) return false;

            try {
                int      caretPos = textArea.getCaretPosition();
                Document doc      = textArea.getDocument();
                String   fullText = doc.getText(0, caretPos);

                // Einrückung der aktuellen Zeile bestimmen
                int lineStart = fullText.lastIndexOf('\n') + 1; // 0 wenn erste Zeile
                String linePrefix = fullText.substring(lineStart);
                StringBuilder indent = new StringBuilder();
                for (char c : linePrefix.toCharArray()) {
                    if (c == ' ' || c == '\t') indent.append(c);
                    else break;
                }
                String baseIndent = indent.toString();
                String innerIndent = baseIndent + "\t";

                // Insert-Text aufbereiten:
                // \n           → \n + baseIndent   (schließende } auf selber Ebene)
                // \n\t         → \n + innerIndent   (Inhalt eine Ebene tiefer)
                // \n\t\n       → \n + innerIndent + \n + baseIndent  (leere Zeile im Block)
                String raw = sel.insert;
                StringBuilder built = new StringBuilder();
                int i = 0;
                while (i < raw.length()) {
                    char c = raw.charAt(i);
                    if (c == '\n') {
                        built.append('\n');
                        i++;
                        // Führende Tabs aus dem Template zählen
                        int tabs = 0;
                        while (i < raw.length() && raw.charAt(i) == '\t') { tabs++; i++; }
                        // baseIndent immer, dann tabs-mal \t drauf
                        built.append(baseIndent);
                        for (int t = 0; t < tabs; t++) built.append('\t');
                    } else {
                        built.append(c);
                        i++;
                    }
                }
                String finalInsert = built.toString();

                // Token ersetzen und Text einfügen
                int replaceLen = caretPos - tokenStart;
                doc.remove(tokenStart, replaceLen);
                doc.insertString(tokenStart, finalInsert, null);

                // Cursor positionieren (cursorBack zählt Zeichen vom Ende)
                int newPos = tokenStart + finalInsert.length() - sel.cursorBack;
                textArea.setCaretPosition(newPos);

            } catch (BadLocationException ex) {
                ex.printStackTrace();
            }

            hide();
            return true;
        }

        int getTokenStart() { return tokenStart; }
    }

    // ═══════════════════════════════════════════════════════
    //  AUTOCOMPLETE CONTROLLER
    // ═══════════════════════════════════════════════════════
    static class AutocompleteController {
        private final RSyntaxTextArea  textArea;
        private final AutocompletePopup popup;
        private javax.swing.Timer      debounce;
        private static final int       DEBOUNCE_MS = 120;

        AutocompleteController(RSyntaxTextArea textArea, JFrame owner) {
            this.textArea = textArea;
            this.popup    = new AutocompletePopup(textArea, owner);

            // Dokument-Listener: bei jeder Texteingabe Vorschläge neu berechnen
            textArea.getDocument().addDocumentListener(new DocumentListener() {
                public void insertUpdate(DocumentEvent e) { scheduleUpdate(); }
                public void removeUpdate(DocumentEvent e) { scheduleUpdate(); }
                public void changedUpdate(DocumentEvent e) {}
            });

            // Tastatur-Shortcuts im Popup
            textArea.addKeyListener(new KeyAdapter() {
                @Override
                public void keyPressed(KeyEvent e) {
                    if (!popup.isVisible()) return;
                    switch (e.getKeyCode()) {
                        case KeyEvent.VK_DOWN:
                            popup.selectNext();
                            e.consume();
                            break;
                        case KeyEvent.VK_UP:
                            popup.selectPrev();
                            e.consume();
                            break;
                        case KeyEvent.VK_ENTER:
                        case KeyEvent.VK_TAB:
                            popup.confirmSelection();
                            e.consume();
                            break;
                        case KeyEvent.VK_ESCAPE:
                            popup.hide();
                            e.consume();
                            break;
                    }
                }
            });

            // Mausklick im Popup bestätigt Auswahl
            popup.list.addMouseListener(new MouseAdapter() {
                @Override
                public void mouseClicked(MouseEvent e) {
                    if (e.getClickCount() == 1) {
                        int idx = popup.list.locationToIndex(e.getPoint());
                        if (idx >= 0) popup.list.setSelectedIndex(idx);
                    }
                    if (e.getClickCount() == 2) {
                        popup.confirmSelection();
                    }
                }
            });

            // Klick außerhalb schließt Popup
            Toolkit.getDefaultToolkit().addAWTEventListener(event -> {
                if (event instanceof MouseEvent) {
                    MouseEvent me = (MouseEvent) event;
                    if (me.getID() == MouseEvent.MOUSE_PRESSED) {
                        Component src = me.getComponent();
                        if (src != popup.popup && src != popup.list) {
                            popup.hide();
                        }
                    }
                }
            }, AWTEvent.MOUSE_EVENT_MASK);
        }

        private void scheduleUpdate() {
            if (debounce != null && debounce.isRunning()) debounce.stop();
            debounce = new javax.swing.Timer(DEBOUNCE_MS, e -> updatePopup());
            debounce.setRepeats(false);
            debounce.start();
        }

        private void updatePopup() {
            try {
                int caretPos = textArea.getCaretPosition();
                // Aktuellen Token rückwärts lesen
                Document doc  = textArea.getDocument();
                String   text = doc.getText(0, caretPos);

                // Token beginnt am letzten Whitespace/Symbol
                int start = caretPos;
                while (start > 0) {
                    char c = text.charAt(start - 1);
                    // Punkt gehört zu "Math.xxx" → miteinschließen
                    if (Character.isLetterOrDigit(c) || c == '_' || c == '.') {
                        start--;
                    } else {
                        break;
                    }
                }
                String token = text.substring(start, caretPos);
                // Minimum 1 Zeichen
                if (token.isEmpty()) { popup.hide(); return; }

                // Passende Einträge suchen (case-sensitive Prefix + Substring)
                List<AcEntry> matches = new ArrayList<>();
                String lower = token.toLowerCase();
                // Erst Prefix-Matches (oben), dann Substring-Matches (darunter)
                for (AcEntry e : AC_ENTRIES) {
                    if (e.trigger.startsWith(token) || e.trigger.toLowerCase().startsWith(lower)) {
                        matches.add(e);
                    }
                }
                for (AcEntry e : AC_ENTRIES) {
                    if (!matches.contains(e)) {
                        if (e.trigger.contains(token) || e.trigger.toLowerCase().contains(lower)) {
                            matches.add(e);
                        }
                    }
                }

                if (matches.isEmpty()) { popup.hide(); return; }

                // Popup-Position berechnen (direkt unterhalb des Carets)
                Rectangle caretRect = textArea.modelToView2D(caretPos).getBounds();
                Point     screen    = caretRect.getLocation();
                SwingUtilities.convertPointToScreen(screen, textArea);
                screen.y += caretRect.height + 2;

                popup.show(matches, start, screen);

            } catch (BadLocationException ex) {
                popup.hide();
            }
        }

        /** Manuell auslösen (z.B. per Strg+Leertaste) */
        void triggerManually() {
            updatePopup();
        }

        AutocompletePopup getPopup() { return popup; }
    }

    // ═══════════════════════════════════════════════════════
    //  HAUPTFENSTER
    // ═══════════════════════════════════════════════════════
    private RSyntaxTextArea       textArea;
    private File                  currentFile;
    private Preferences           prefs;
    private boolean               isDarkMode;
    private JLabel                statusLabel;
    private JCheckBoxMenuItem     itemDarkMode;
    private Process               runningProcess;
    private AutocompleteController acController;
    private File                  tempWorkspace;
    private boolean               currentFileIsSb3;
    private String                lastKnownFileFingerprint;
    private long                  lastKnownFileModified;
    private long                  lastKnownFileLength;
    private String                pendingExternalFingerprint;
    private long                  pendingFingerprintSince;
    private boolean               externalChangePromptOpen;
    private javax.swing.Timer     externalFileCheckTimer;
    private volatile boolean      sb3LoadInProgress;
    // Aktive TurboWarp-Vorschau: genau diese .sb3-Datei wird von der Desktop-App geöffnet.
    private File                  activePreviewSb3File;
    private File                  activeWatchInput;
    private boolean               watchModeActive;
    private long                  lastSeenWatchInputModified = -1L;
    private boolean               previewFirstCompilePending;
    private boolean               watchSourceChangedSincePreview;
    private String                lastKnownPreviewFingerprint;
    private long                  lastKnownPreviewModified;
    private long                  lastKnownPreviewLength;
    private String                pendingPreviewFingerprint;
    private long                  pendingPreviewSince;

    public Main(String[] args) {
        setTitle("Scrape Editor");
        setSize(1100, 720);
        setDefaultCloseOperation(JFrame.DO_NOTHING_ON_CLOSE);
        setLocationRelativeTo(null);

        prefs      = Preferences.userNodeForPackage(Main.class);
        isDarkMode = prefs.getBoolean("darkMode", false);

        initComponents();
        // Autocomplete initialisieren (nach initComponents, damit textArea existiert)
        acController = new AutocompleteController(textArea, this);
        setupKeyBindings();
        applyTheme(isDarkMode);
        startExternalFileWatcher();
        addWindowListener(new WindowAdapter() {
            @Override public void windowClosing(WindowEvent e) {
                stopTranspiler();
                if (externalFileCheckTimer != null) externalFileCheckTimer.stop();
                deleteTempWorkspace();
                dispose();
                System.exit(0);
            }
        });

        if (args != null && args.length > 0) {
            loadFile(new File(args[0]));
        } else {
            newFile();
        }
    }

    private void applyTheme(boolean dark) {
        try {
            if (dark) {
                UIManager.setLookAndFeel(new FlatDarkLaf());
                loadRSyntaxTheme("/org/fife/ui/rsyntaxtextarea/themes/dark.xml");
            } else {
                UIManager.setLookAndFeel(new FlatLightLaf());
                loadRSyntaxTheme("/org/fife/ui/rsyntaxtextarea/themes/default.xml");
            }
            SwingUtilities.updateComponentTreeUI(this);
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private void loadRSyntaxTheme(String themePath) {
        try {
            Theme theme = Theme.load(getClass().getResourceAsStream(themePath));
            theme.apply(textArea);
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private void initComponents() {
        setLayout(new BorderLayout());

        textArea = new RSyntaxTextArea(25, 60);
        textArea.setSyntaxEditingStyle(SyntaxConstants.SYNTAX_STYLE_JAVA);
        textArea.setCodeFoldingEnabled(true);
        textArea.setAntiAliasingEnabled(true);
        textArea.setTabSize(4);

        RTextScrollPane scrollPane = new RTextScrollPane(textArea);
        add(scrollPane, BorderLayout.CENTER);

        // Statusleiste
        JPanel statusBar = new JPanel(new FlowLayout(FlowLayout.LEFT, 10, 3));
        statusLabel = new JLabel("Bereit");
        statusBar.add(statusLabel);

        // Kleiner Tipp
        JLabel hint = new JLabel("Autocomplete: tippen (2+ Zeichen) oder Strg+Leerzeichen");
        hint.setForeground(Color.GRAY);
        hint.setFont(hint.getFont().deriveFont(Font.PLAIN, 11f));
        statusBar.add(hint);
        add(statusBar, BorderLayout.SOUTH);

        // Menüleiste
        JMenuBar menuBar = new JMenuBar();

        // Datei-Menü
        JMenu menuFile = new JMenu("Datei");
        addItem(menuFile, "Neu",          e -> newFile());
        addItem(menuFile, "Öffnen...",    e -> openFileDialog());
        addItem(menuFile, "Speichern (Strg+S)", e -> saveFile());
        menuFile.addSeparator();
        addItem(menuFile, "Beenden",      e -> System.exit(0));
        menuBar.add(menuFile);

        // Transpiler-Menü
        JMenu menuTranspiler = new JMenu("Transpiler");
        addItem(menuTranspiler, "Ausführen (Strg+R)",              e -> runTranspiler(false));
        addItem(menuTranspiler, "Hotswap / Watch (Strg+Shift+R)",  e -> runTranspiler(true));
        addItem(menuTranspiler, "Stoppen (Strg+X)",                e -> stopTranspiler());
        menuBar.add(menuTranspiler);

        // Ansicht-Menü
        JMenu menuView = new JMenu("Ansicht");
        itemDarkMode = new JCheckBoxMenuItem("Dark Mode", isDarkMode);
        itemDarkMode.addActionListener(e -> {
            isDarkMode = itemDarkMode.isSelected();
            prefs.putBoolean("darkMode", isDarkMode);
            applyTheme(isDarkMode);
        });
        menuView.add(itemDarkMode);
        menuBar.add(menuView);

        JMenu menuSettings = new JMenu("Einstellungen");
        addItem(menuSettings, "Dateiüberwachung...", e -> showSettingsDialog());
        menuBar.add(menuSettings);

        setJMenuBar(menuBar);
    }

    private void addItem(JMenu menu, String label, java.awt.event.ActionListener action) {
        JMenuItem item = new JMenuItem(label);
        item.addActionListener(action);
        menu.add(item);
    }

    private void setupKeyBindings() {
        InputMap  im = getRootPane().getInputMap(JComponent.WHEN_IN_FOCUSED_WINDOW);
        ActionMap am = getRootPane().getActionMap();

        bind(im, am, KeyEvent.VK_S, InputEvent.CTRL_DOWN_MASK, "saveFile",
             e -> saveFile());
        bind(im, am, KeyEvent.VK_R, InputEvent.CTRL_DOWN_MASK, "runTranspiler",
             e -> runTranspiler(false));
        bind(im, am, KeyEvent.VK_R, InputEvent.CTRL_DOWN_MASK | InputEvent.SHIFT_DOWN_MASK, "runWatch",
             e -> runTranspiler(true));
        bind(im, am, KeyEvent.VK_X, InputEvent.CTRL_DOWN_MASK, "stopTranspiler",
             e -> stopTranspiler());

        // Strg+Leertaste: Autocomplete manuell auslösen
        bind(im, am, KeyEvent.VK_SPACE, InputEvent.CTRL_DOWN_MASK, "triggerAC",
             e -> acController.triggerManually());
    }

    private void bind(InputMap im, ActionMap am, int key, int mod, String name,
                      java.awt.event.ActionListener action) {
        im.put(KeyStroke.getKeyStroke(key, mod), name);
        am.put(name, new AbstractAction() {
            @Override public void actionPerformed(java.awt.event.ActionEvent e) { action.actionPerformed(e); }
        });
    }

    // ── Temporärer Arbeitsbereich und Python-Werkzeuge ──────
    // Alle Hilfsdateien liegen ausschließlich im System-Temp-Verzeichnis,
    // niemals neben der vom Benutzer geöffneten Projektdatei.
    private File ensureTempWorkspace() throws IOException {
        if (tempWorkspace == null || !tempWorkspace.isDirectory()) {
            tempWorkspace = Files.createTempDirectory("scrape-editor-").toFile();
            tempWorkspace.deleteOnExit();
        }
        return tempWorkspace;
    }

    private File extractResourceToWorkspace(String resourceName) {
        try {
            File destination = new File(ensureTempWorkspace(), resourceName);
            try (InputStream in = getClass().getResourceAsStream("/" + resourceName)) {
                if (in == null) {
                    JOptionPane.showMessageDialog(this,
                        resourceName + " wurde nicht im resources-Ordner gefunden!",
                        "Ressource fehlt", JOptionPane.ERROR_MESSAGE);
                    return null;
                }
                Files.copy(in, destination.toPath(), StandardCopyOption.REPLACE_EXISTING);
            }
            return destination;
        } catch (IOException e) {
            JOptionPane.showMessageDialog(this,
                "Die Ressource " + resourceName + " konnte nicht in den Temp-Ordner kopiert werden:\n"
                    + e.getMessage(), "Fehler", JOptionPane.ERROR_MESSAGE);
            return null;
        }
    }

    private File extractDetranspilerFromResources() {
        return extractResourceToWorkspace("Detranspiler.py");
    }

    private File extractTranspilerFromResources() {
        return extractResourceToWorkspace("Transpiler.py");
    }

    private static class ProcessResult {
        final int exitCode;
        final String output;
        ProcessResult(int exitCode, String output) {
            this.exitCode = exitCode;
            this.output = output;
        }
    }

    private ProcessResult runPython(File script, List<String> arguments, File workingDirectory)
            throws IOException, InterruptedException {
        List<String> command = new ArrayList<>();
        String os = System.getProperty("os.name", "").toLowerCase(Locale.ROOT);
        command.add(os.contains("win") ? "python" : "python3");
        command.add(script.getAbsolutePath());
        command.addAll(arguments);

        Process process;
        try {
            process = new ProcessBuilder(command).directory(workingDirectory)
                .redirectErrorStream(true).start();
        } catch (IOException first) {
            // Auf Windows ist je nach Installation auch python3 statt python vorhanden.
            if (!os.contains("win")) throw first;
            command.set(0, "python3");
            process = new ProcessBuilder(command).directory(workingDirectory)
                .redirectErrorStream(true).start();
        }

        StringBuilder output = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) output.append(line).append(System.lineSeparator());
        }
        return new ProcessResult(process.waitFor(), output.toString());
    }

    private String fileStem(File file) {
        String name = file.getName();
        int dot = name.lastIndexOf('.');
        return dot > 0 ? name.substring(0, dot) : name;
    }

    private boolean isSb3File(File file) {
        return file != null && file.getName().toLowerCase(Locale.ROOT).endsWith(".sb3");
    }

    private boolean loadSb3File(File file) {
        if (SwingUtilities.isEventDispatchThread()) {
            if (sb3LoadInProgress) return true;
            sb3LoadInProgress = true;
            statusLabel.setText(".sb3-Projekt wird geladen...");
            setSb3Busy(true);
            new SwingWorker<Boolean, Void>() {
                @Override protected Boolean doInBackground() { return loadSb3FileBlocking(file); }
                @Override protected void done() {
                    setSb3Busy(false);
                    sb3LoadInProgress = false;
                    try { get(); } catch (Exception ex) {
                        JOptionPane.showMessageDialog(Main.this,
                            "Fehler beim Laden der .sb3-Datei: " + ex.getMessage(),
                            "Fehler", JOptionPane.ERROR_MESSAGE);
                    }
                }
            }.execute();
            return true;
        }
        return loadSb3FileBlocking(file);
    }

    private void setSb3Busy(boolean busy) {
        setCursor(busy ? Cursor.getPredefinedCursor(Cursor.WAIT_CURSOR) : Cursor.getDefaultCursor());
    }

    private boolean loadSb3FileBlocking(File file) {
        try {
            File workspace = ensureTempWorkspace();
            File script = extractDetranspilerFromResources();
            if (script == null) return false;

            File outputFile = new File(workspace, "opened-project.scrape");
            Files.deleteIfExists(outputFile.toPath());
            ProcessResult result = runPython(script,
                Arrays.asList(file.getAbsolutePath(), "--output", outputFile.getAbsolutePath()), workspace);

            if (result.exitCode != 0 || !outputFile.isFile()) {
                JOptionPane.showMessageDialog(this,
                    "Die .sb3-Datei konnte nicht mit dem Detranspiler geöffnet werden.\n\n"
                        + result.output,
                    "Detranspiler-Fehler", JOptionPane.ERROR_MESSAGE);
                return false;
            }

            String source = new String(Files.readAllBytes(outputFile.toPath()), StandardCharsets.UTF_8);
            // Falls TurboWarp die gerade überwachte .sb3-Datei gespeichert hat,
            // wird der neue Stand auch in die vom Watch-Transpiler gelesene
            // .scrape-Quelldatei übernommen.
            if (watchModeActive && activeWatchInput != null) {
                writeTextAtomically(activeWatchInput, source);
                lastSeenWatchInputModified = activeWatchInput.lastModified();
                watchSourceChangedSincePreview = true;
            }
            textArea.setText(source);
            currentFile = file.getAbsoluteFile();
            currentFileIsSb3 = true;
            updateTitle();
            statusLabel.setText(".sb3-Projekt geöffnet: " + currentFile.getAbsolutePath());
            refreshFileFingerprint();
            return true;
        } catch (Exception e) {
            JOptionPane.showMessageDialog(this,
                "Fehler beim Öffnen der .sb3-Datei: " + e.getMessage(),
                "Fehler", JOptionPane.ERROR_MESSAGE);
            return false;
        }
    }

    private File writeTemporaryScrapeSource(String name) throws IOException {
        File workspace = ensureTempWorkspace();
        File source = new File(workspace, name);
        writeTextAtomically(source, textArea.getText());
        return source;
    }

    private void writeTextAtomically(File target, String content) throws IOException {
        Path targetPath = target.toPath();
        Path parent = targetPath.toAbsolutePath().getParent();
        if (parent != null) Files.createDirectories(parent);
        Path temp = targetPath.resolveSibling(targetPath.getFileName().toString() + ".tmp");
        Files.write(temp, content.getBytes(StandardCharsets.UTF_8));
        try {
            Files.move(temp, targetPath, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException ex) {
            Files.move(temp, targetPath, StandardCopyOption.REPLACE_EXISTING);
        }
    }

    private boolean sameFilePath(File a, File b) {
        return a != null && b != null && a.getAbsoluteFile().toPath().normalize()
            .equals(b.getAbsoluteFile().toPath().normalize());
    }

    private File findGeneratedSb3(File workspace) throws IOException {
        try (java.util.stream.Stream<Path> paths = Files.walk(workspace.toPath(), 4)) {
            return paths.filter(Files::isRegularFile)
                .filter(path -> path.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".sb3"))
                .map(Path::toFile)
                .filter(file -> file.length() > 0)
                .max(Comparator.comparingLong(File::lastModified))
                .orElse(null);
        }
    }

    private boolean saveSb3File() {
        if (SwingUtilities.isEventDispatchThread()) {
            statusLabel.setText(".sb3-Projekt wird gespeichert...");
            setSb3Busy(true);
            new SwingWorker<Boolean, Void>() {
                @Override protected Boolean doInBackground() { return saveSb3FileBlocking(); }
                @Override protected void done() {
                    setSb3Busy(false);
                    try {
                        if (!get()) statusLabel.setText("Speichern fehlgeschlagen.");
                    } catch (Exception ex) {
                        JOptionPane.showMessageDialog(Main.this,
                            "Fehler beim Speichern der .sb3-Datei: " + ex.getMessage(),
                            "Fehler", JOptionPane.ERROR_MESSAGE);
                    }
                }
            }.execute();
            return true;
        }
        return saveSb3FileBlocking();
    }

    private boolean saveSb3FileBlocking() {
        try {
            File workspace = ensureTempWorkspace();
            // Alte Exportdateien entfernen, damit garantiert das Ergebnis dieses Laufs verwendet wird.
            try (java.util.stream.Stream<Path> paths = Files.walk(workspace.toPath(), 4)) {
                paths.filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString().toLowerCase(Locale.ROOT).endsWith(".sb3"))
                    .forEach(path -> {
                        try { Files.deleteIfExists(path); } catch (IOException ignored) {}
                    });
            }

            File source = writeTemporaryScrapeSource("export-" + fileStem(currentFile) + ".scrape");
            File script = extractTranspilerFromResources();
            if (script == null) return false;

            statusLabel.setText("Erzeuge .sb3-Projekt...");
            // Speichern erzeugt nur die .sb3-Datei. Das Starten/Ersetzen von
            // TurboWarp übernimmt ausschließlich runTranspiler().
            ProcessResult result = runPython(script,
                Arrays.asList(source.getAbsolutePath(), "--out", new File(workspace, "output.sb3").getAbsolutePath()), workspace);
            if (result.exitCode != 0) {
                JOptionPane.showMessageDialog(this,
                    "Der Transpiler konnte die .sb3-Datei nicht erzeugen.\n\n" + result.output,
                    "Transpiler-Fehler", JOptionPane.ERROR_MESSAGE);
                return false;
            }

            File generated = findGeneratedSb3(workspace);
            if (generated == null) {
                JOptionPane.showMessageDialog(this,
                    "Der Transpiler wurde beendet, aber im Temp-Ordner wurde keine .sb3-Datei gefunden.\n\n"
                        + result.output,
                    "Ausgabedatei fehlt", JOptionPane.ERROR_MESSAGE);
                return false;
            }

            Files.copy(generated.toPath(), currentFile.toPath(), StandardCopyOption.REPLACE_EXISTING);
            currentFileIsSb3 = true;
            refreshFileFingerprint();
            updateTitle();
            statusLabel.setText(".sb3-Projekt gespeichert: " + currentFile.getAbsolutePath());
            return true;
        } catch (Exception e) {
            JOptionPane.showMessageDialog(this,
                "Fehler beim Speichern der .sb3-Datei: " + e.getMessage(),
                "Fehler", JOptionPane.ERROR_MESSAGE);
            return false;
        }
    }

    private void deleteTempWorkspace() {
        if (tempWorkspace == null || !tempWorkspace.exists()) return;
        try (java.util.stream.Stream<Path> paths = Files.walk(tempWorkspace.toPath())) {
            paths.sorted(Comparator.reverseOrder()).forEach(path -> {
                try { Files.deleteIfExists(path); } catch (IOException ignored) {}
            });
        } catch (IOException ignored) {}
        tempWorkspace = null;
    }

    private void runTranspiler(boolean watch) {
        if (currentFile == null) {
            JFileChooser chooser = new JFileChooser();
            chooser.setFileFilter(new javax.swing.filechooser.FileNameExtensionFilter(
                "Scrape- und Scratch-Projekte (*.scrape, *.sb3)", "scrape", "sb3"));
            if (chooser.showSaveDialog(this) != JFileChooser.APPROVE_OPTION) return;
            currentFile = chooser.getSelectedFile().getAbsoluteFile();
            String lower = currentFile.getName().toLowerCase(Locale.ROOT);
            if (lower.endsWith(".sb3")) {
                currentFileIsSb3 = true;
            } else {
                currentFileIsSb3 = false;
                if (!lower.endsWith(".scrape"))
                    currentFile = new File(currentFile.getAbsolutePath() + ".scrape");
            }
        }
        boolean openingFromSb3 = currentFileIsSb3 || isSb3File(currentFile);
        // Bei .sb3 wird nicht separat gespeichert: Das würde TurboWarp bereits
        // einmal starten. Der Watch-Prozess erstellt die Datei und startet es
        // anschließend genau ein einziges Mal (mit korrekter Fensterposition).
        if (!openingFromSb3 && !saveFile()) return;

        stopTranspiler();
        File script = extractTranspilerFromResources();
        if (script == null) return;

        try {
            File transpilerInput = openingFromSb3
                ? writeTemporaryScrapeSource("live-" + fileStem(currentFile) + ".scrape")
                : currentFile;

            File workDirectory = transpilerInput.getParentFile();
            if (workDirectory == null) workDirectory = new File(System.getProperty("user.dir"));

            // Die Desktop-App öffnet dieselbe Projektdatei, die der Editor anschließend
            // überwacht. Bei .scrape entsteht eine gleichnamige .sb3 daneben;
            // bei einer geöffneten .sb3 wird genau diese Datei aktualisiert.
            File previewFile = openingFromSb3
                ? currentFile.getAbsoluteFile()
                : new File(workDirectory, fileStem(currentFile) + ".sb3").getAbsoluteFile();

            String python = System.getProperty("os.name", "").toLowerCase(Locale.ROOT).contains("win")
                ? "python" : "python3";
            String pyCmd = "\"" + python + "\" \"" + script.getAbsolutePath() + "\""
                + " \"" + transpilerInput.getAbsolutePath() + "\""
                + " --out \"" + previewFile.getAbsolutePath() + "\""
                + " --turbowarp-replace"
                + (watch ? " --watch" : "");

            String workDir = workDirectory.getAbsolutePath();
            List<String> cmd = new ArrayList<>();
            String os = System.getProperty("os.name", "").toLowerCase(Locale.ROOT);

            if (os.contains("win")) {
                cmd.add("cmd");
                cmd.add("/c");
                cmd.add("start");
                cmd.add("\"Scrape Transpiler\"");
                cmd.add("cmd");
                cmd.add("/k");
                cmd.add(pyCmd);
            } else if (os.contains("mac")) {
                String escaped = pyCmd.replace("\\", "\\\\").replace("\"", "\\\"");
                cmd.add("osascript");
                cmd.add("-e");
                cmd.add("tell application \"Terminal\" to do script \"cd \\\""
                    + workDir.replace("\"", "\\\"") + "\\\" && " + escaped + "\"");
            } else {
                String terminal = resolveLinuxTerminal();
                if (terminal.equals("gnome-terminal")) {
                    cmd.add("gnome-terminal"); cmd.add("--"); cmd.add("bash"); cmd.add("-c");
                    cmd.add(pyCmd + "; exec bash");
                } else {
                    cmd.add(terminal); cmd.add("-e");
                    cmd.add("bash -c '" + pyCmd.replace("'", "'\\''") + "; exec bash'");
                }
            }

            if (watch) {
                activeWatchInput = transpilerInput;
                activePreviewSb3File = previewFile;
                watchModeActive = true;
                lastSeenWatchInputModified = activeWatchInput.lastModified();
                watchSourceChangedSincePreview = false;
                previewFirstCompilePending = true;
                refreshPreviewFingerprint();
            }

            ProcessBuilder pb = new ProcessBuilder(cmd);
            pb.directory(workDirectory);
            runningProcess = pb.start();
            statusLabel.setText("Transpiler läuft (" + (watch ? "--watch" : "Normal") + ")");
        } catch (IOException e) {
            clearWatchTracking();
            JOptionPane.showMessageDialog(this,
                "Fehler beim Starten des Transpilers: " + e.getMessage(),
                "Fehler", JOptionPane.ERROR_MESSAGE);
            statusLabel.setText("Fehler beim Starten des Transpilers");
        }
    }

    /** Findet einen verfügbaren Terminal-Emulator unter Linux. */
    private String resolveLinuxTerminal() {
        for (String t : new String[]{"gnome-terminal", "x-terminal-emulator", "xfce4-terminal", "konsole", "xterm"}) {
            try {
                Process p = Runtime.getRuntime().exec(new String[]{"which", t});
                if (p.waitFor() == 0) return t;
            } catch (Exception ignored) {}
        }
        return "xterm"; // letzter Fallback
    }

    private void clearWatchTracking() {
        activePreviewSb3File = null;
        activeWatchInput = null;
        watchModeActive = false;
        lastSeenWatchInputModified = -1L;
        previewFirstCompilePending = false;
        watchSourceChangedSincePreview = false;
        lastKnownPreviewFingerprint = null;
        lastKnownPreviewModified = 0L;
        lastKnownPreviewLength = 0L;
        pendingPreviewFingerprint = null;
    }

    private void stopTranspiler() {
        if (runningProcess != null && runningProcess.isAlive()) {
            runningProcess.destroyForcibly();
            runningProcess = null;
            statusLabel.setText("Transpiler gestoppt.");
        } else {
            statusLabel.setText("Kein aktiver Transpiler gefunden.");
        }
        clearWatchTracking();
    }

    // ── Datei-Operationen ───────────────────────────────────
    private static final String NEW_FILE_TEMPLATE =
        "public Stage Buehne {\n" +
        "    addBackdrop(\"Forest\");\n" +
        "}\n" +
        "\n" +
        "public Sprite Mouse {\n" +
        "    addCostume(\"Mouse1-a\");\n" +
        "\n" +
        "    onFlagClicked {\n" +
        "        \n" +
        "    }\n" +
        "}\n";

    private void newFile() {
        currentFile = null;
        currentFileIsSb3 = false;
        lastKnownFileFingerprint = null;
        pendingExternalFingerprint = null;
        textArea.setText(NEW_FILE_TEMPLATE);
        // Cursor in den onFlagClicked-Block setzen (leere Zeile, 8 Leerzeichen tief)
        int pos = NEW_FILE_TEMPLATE.indexOf("    onFlagClicked {") + "    onFlagClicked {\n        ".length();
        textArea.setCaretPosition(pos);
        updateTitle();
        statusLabel.setText("Neue Datei erstellt");
    }

    private boolean loadFile(File file) {
        if (isSb3File(file)) return loadSb3File(file);
        try {
            String source = new String(Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8);
            textArea.setText(source);
            currentFile = file.getAbsoluteFile();
            currentFileIsSb3 = false;
            updateTitle();
            statusLabel.setText("Geladen: " + currentFile.getAbsolutePath());
            refreshFileFingerprint();
            return true;
        } catch (IOException e) {
            JOptionPane.showMessageDialog(this,
                "Fehler beim Laden: " + e.getMessage(), "Fehler", JOptionPane.ERROR_MESSAGE);
            return false;
        }
    }

    private boolean saveFile() {
        if (currentFile == null) {
            JFileChooser chooser = new JFileChooser();
            chooser.setFileFilter(new javax.swing.filechooser.FileNameExtensionFilter(
                "Scrape- und Scratch-Projekte (*.scrape, *.sb3)", "scrape", "sb3"));
            if (chooser.showSaveDialog(this) == JFileChooser.APPROVE_OPTION) {
                currentFile = chooser.getSelectedFile();
                String lower = currentFile.getName().toLowerCase(Locale.ROOT);
                if (lower.endsWith(".sb3")) {
                    currentFileIsSb3 = true;
                } else {
                    currentFileIsSb3 = false;
                    if (!lower.endsWith(".scrape"))
                        currentFile = new File(currentFile.getAbsolutePath() + ".scrape");
                }
            } else {
                return false;
            }
        }

        if (currentFileIsSb3 || isSb3File(currentFile)) {
            currentFileIsSb3 = true;
            if (watchModeActive && activeWatchInput != null) {
                try {
                    writeTextAtomically(activeWatchInput, textArea.getText());
                    lastSeenWatchInputModified = activeWatchInput.lastModified();
                    watchSourceChangedSincePreview = true;
                    statusLabel.setText("Watch-Quelle gespeichert – TurboWarp wird aktualisiert.");
                    return true;
                } catch (IOException e) {
                    JOptionPane.showMessageDialog(this,
                        "Die Watch-Quelldatei konnte nicht gespeichert werden: " + e.getMessage(),
                        "Speicherfehler", JOptionPane.ERROR_MESSAGE);
                    return false;
                }
            }
            return saveSb3File();
        }

        try {
            writeTextAtomically(currentFile, textArea.getText());
            updateTitle();
            statusLabel.setText("Gespeichert: " + currentFile.getAbsolutePath());
            refreshFileFingerprint();
            return true;
        } catch (IOException e) {
            JOptionPane.showMessageDialog(this,
                "Fehler beim Speichern: " + e.getMessage(), "Fehler", JOptionPane.ERROR_MESSAGE);
            return false;
        }
    }

    private void updateTitle() {
        String name = (currentFile != null) ? currentFile.getName() : "Unbenannt.scrape";
        setTitle("Scrape Editor – " + name);
    }

    private void openFileDialog() {
        JFileChooser chooser = new JFileChooser();
        chooser.setFileFilter(new javax.swing.filechooser.FileNameExtensionFilter(
            "Scrape- und Scratch-Projekte (*.scrape, *.sb3)", "scrape", "sb3"));
        if (chooser.showOpenDialog(this) == JFileChooser.APPROVE_OPTION)
            loadFile(chooser.getSelectedFile());
    }

    // ── Erkennung externer Dateiänderungen ───────────────────
    private String fingerprint(File file) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream in = Files.newInputStream(file.toPath())) {
                byte[] buffer = new byte[8192];
                int count;
                while ((count = in.read(buffer)) != -1) digest.update(buffer, 0, count);
            }
            return Arrays.toString(digest.digest());
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 wird von dieser Java-Installation nicht unterstützt", impossible);
        }
    }

    private void refreshFileFingerprint() {
        pendingExternalFingerprint = null;
        if (currentFile == null || !currentFile.isFile()) {
            lastKnownFileFingerprint = null;
            lastKnownFileModified = 0L;
            lastKnownFileLength = 0L;
            return;
        }
        try {
            lastKnownFileFingerprint = fingerprint(currentFile);
            lastKnownFileModified = currentFile.lastModified();
            lastKnownFileLength = currentFile.length();
        } catch (IOException e) {
            lastKnownFileFingerprint = null;
        }
    }

    private void startExternalFileWatcher() {
        externalFileCheckTimer = new javax.swing.Timer(900, e -> checkExternalFileForChanges());
        externalFileCheckTimer.setRepeats(true);
        externalFileCheckTimer.start();
    }

    private void refreshPreviewFingerprint() {
        pendingPreviewFingerprint = null;
        if (activePreviewSb3File == null || !activePreviewSb3File.isFile()) {
            lastKnownPreviewFingerprint = null;
            lastKnownPreviewModified = 0L;
            lastKnownPreviewLength = 0L;
            return;
        }
        try {
            lastKnownPreviewFingerprint = fingerprint(activePreviewSb3File);
            lastKnownPreviewModified = activePreviewSb3File.lastModified();
            lastKnownPreviewLength = activePreviewSb3File.length();
        } catch (IOException e) {
            lastKnownPreviewFingerprint = null;
        }
    }

    private void observeActiveWatchInput() {
        if (!watchModeActive || activeWatchInput == null || !activeWatchInput.isFile()) return;
        long modified = activeWatchInput.lastModified();
        if (lastSeenWatchInputModified >= 0 && modified != lastSeenWatchInputModified) {
            watchSourceChangedSincePreview = true;
        }
        lastSeenWatchInputModified = modified;
    }

    private void rememberPreviewFingerprint(String value, long modified, long length) {
        lastKnownPreviewFingerprint = value;
        lastKnownPreviewModified = modified;
        lastKnownPreviewLength = length;
        pendingPreviewFingerprint = null;
    }

    private void checkExternalFileForChanges() {
        if (externalChangePromptOpen || sb3LoadInProgress) return;
        observeActiveWatchInput();

        // Die aktive TurboWarp-Datei wird separat überwacht, wenn sie nicht
        // identisch mit der im Editor geöffneten Quelldatei ist.
        if (watchModeActive && activePreviewSb3File != null
                && !sameFilePath(activePreviewSb3File, currentFile)) {
            checkPreviewSb3ForChanges();
        }

        if (currentFile == null || !currentFile.isFile()) return;
        try {
            long modified = currentFile.lastModified();
            long length = currentFile.length();
            if (modified == lastKnownFileModified && length == lastKnownFileLength) return;
            String currentFingerprint = fingerprint(currentFile);
            if (lastKnownFileFingerprint == null) {
                lastKnownFileFingerprint = currentFingerprint;
                lastKnownFileModified = modified;
                lastKnownFileLength = length;
                return;
            }
            if (currentFingerprint.equals(lastKnownFileFingerprint)) {
                lastKnownFileModified = modified;
                lastKnownFileLength = length;
                pendingExternalFingerprint = null;
                return;
            }

            if (!currentFingerprint.equals(pendingExternalFingerprint)) {
                pendingExternalFingerprint = currentFingerprint;
                pendingFingerprintSince = System.currentTimeMillis();
                return;
            }
            if (System.currentTimeMillis() - pendingFingerprintSince < 700) return;

            // Änderungen an der .sb3-Datei, die durch den eigenen Watch-Compiler
            // entstanden sind, nicht als externe Desktop-Speicherung behandeln.
            if (watchModeActive && sameFilePath(currentFile, activePreviewSb3File)
                    && (previewFirstCompilePending || watchSourceChangedSincePreview)) {
                lastKnownFileFingerprint = currentFingerprint;
                lastKnownFileModified = modified;
                lastKnownFileLength = length;
                pendingExternalFingerprint = null;
                previewFirstCompilePending = false;
                watchSourceChangedSincePreview = false;
                return;
            }

            File changedFile = currentFile;
            if (prefs.getBoolean("autoReloadExternalChanges", false)) {
                if (loadFile(changedFile)) {
                    statusLabel.setText("Externe Änderung automatisch geladen: " + changedFile.getName());
                } else {
                    lastKnownFileFingerprint = currentFingerprint;
                    lastKnownFileModified = modified;
                    lastKnownFileLength = length;
                    pendingExternalFingerprint = null;
                }
            } else {
                showExternalChangeDialog(changedFile, currentFingerprint);
            }
        } catch (IOException e) {
            statusLabel.setText("Dateiüberwachung: " + e.getMessage());
        }
    }

    private void checkPreviewSb3ForChanges() {
        if (activePreviewSb3File == null || !activePreviewSb3File.isFile()) return;
        try {
            long modified = activePreviewSb3File.lastModified();
            long length = activePreviewSb3File.length();
            if (modified == lastKnownPreviewModified && length == lastKnownPreviewLength) return;
            String currentFingerprint = fingerprint(activePreviewSb3File);
            if (lastKnownPreviewFingerprint == null) {
                rememberPreviewFingerprint(currentFingerprint, modified, length);
                previewFirstCompilePending = false;
                return;
            }
            if (currentFingerprint.equals(lastKnownPreviewFingerprint)) {
                lastKnownPreviewModified = modified;
                lastKnownPreviewLength = length;
                pendingPreviewFingerprint = null;
                return;
            }
            if (!currentFingerprint.equals(pendingPreviewFingerprint)) {
                pendingPreviewFingerprint = currentFingerprint;
                pendingPreviewSince = System.currentTimeMillis();
                return;
            }
            if (System.currentTimeMillis() - pendingPreviewSince < 700) return;

            if (previewFirstCompilePending || watchSourceChangedSincePreview) {
                rememberPreviewFingerprint(currentFingerprint, modified, length);
                previewFirstCompilePending = false;
                watchSourceChangedSincePreview = false;
                return;
            }

            if (prefs.getBoolean("autoReloadExternalChanges", false)) {
                reloadFromPreviewSb3(activePreviewSb3File);
            } else {
                showPreviewChangeDialog(activePreviewSb3File, currentFingerprint);
            }
        } catch (IOException e) {
            statusLabel.setText("TurboWarp-Dateiüberwachung: " + e.getMessage());
        }
    }

    private void showPreviewChangeDialog(File changedFile, String changedFingerprint) {
        externalChangePromptOpen = true;
        JPanel panel = new JPanel(new BorderLayout(0, 10));
        panel.add(new JLabel("Die von TurboWarp Desktop gespeicherte Projektdatei wurde geändert:"), BorderLayout.NORTH);
        JLabel path = new JLabel(changedFile.getAbsolutePath());
        path.setFont(path.getFont().deriveFont(Font.PLAIN, 11f));
        panel.add(path, BorderLayout.CENTER);
        JButton copyButton = new JButton("Aktuellen Code kopieren");
        copyButton.addActionListener(e -> {
            Toolkit.getDefaultToolkit().getSystemClipboard()
                .setContents(new StringSelection(textArea.getText()), null);
            statusLabel.setText("Aktueller Editor-Code wurde in die Zwischenablage kopiert");
        });
        panel.add(copyButton, BorderLayout.SOUTH);
        Object[] options = {"TurboWarp-Version in .scrape übernehmen", "Änderung ignorieren"};
        int choice;
        try {
            choice = JOptionPane.showOptionDialog(this, panel, "TurboWarp-Projekt extern gespeichert",
                JOptionPane.DEFAULT_OPTION, JOptionPane.WARNING_MESSAGE, null, options, options[0]);
        } finally {
            externalChangePromptOpen = false;
        }
        if (choice == 0) {
            reloadFromPreviewSb3(changedFile);
        } else {
            refreshPreviewFingerprint();
            statusLabel.setText("TurboWarp-Änderung vorerst ignoriert");
        }
    }

    private void reloadFromPreviewSb3(File previewFile) {
        externalChangePromptOpen = true;
        setSb3Busy(true);
        new SwingWorker<String, Void>() {
            @Override protected String doInBackground() throws Exception {
                File workspace = ensureTempWorkspace();
                File script = extractDetranspilerFromResources();
                if (script == null) throw new IOException("Detranspiler.py konnte nicht geladen werden.");
                File output = new File(workspace, "turbowarp-saved-project.scrape");
                ProcessResult result = runPython(script,
                    Arrays.asList(previewFile.getAbsolutePath(), "--output", output.getAbsolutePath()), workspace);
                if (result.exitCode != 0 || !output.isFile()) {
                    throw new IOException("Die gespeicherte TurboWarp-Datei konnte nicht umgewandelt werden.\n" + result.output);
                }
                return new String(Files.readAllBytes(output.toPath()), StandardCharsets.UTF_8);
            }
            @Override protected void done() {
                setSb3Busy(false);
                try {
                    String source = get();
                    textArea.setText(source);
                    if (currentFileIsSb3 || isSb3File(currentFile)) {
                        File workspace = ensureTempWorkspace();
                        writeTextAtomically(new File(workspace, "opened-project.scrape"), source);
                        if (activeWatchInput != null) writeTextAtomically(activeWatchInput, source);
                    } else if (currentFile != null) {
                        writeTextAtomically(currentFile, source);
                    }
                    if (activeWatchInput != null && activeWatchInput.isFile()) {
                        lastSeenWatchInputModified = activeWatchInput.lastModified();
                        watchSourceChangedSincePreview = true;
                    }
                    refreshFileFingerprint();
                    refreshPreviewFingerprint();
                    statusLabel.setText("TurboWarp-Speicherung wurde in den Scrape-Code übernommen.");
                } catch (Exception ex) {
                    JOptionPane.showMessageDialog(Main.this,
                        "Fehler beim Übernehmen der TurboWarp-Version: " + ex.getMessage(),
                        "Synchronisierung fehlgeschlagen", JOptionPane.ERROR_MESSAGE);
                    refreshPreviewFingerprint();
                } finally {
                    externalChangePromptOpen = false;
                }
            }
        }.execute();
    }

    private void showExternalChangeDialog(File changedFile, String changedFingerprint) {
        externalChangePromptOpen = true;
        JPanel panel = new JPanel(new BorderLayout(0, 10));
        panel.add(new JLabel("Die aktuell geöffnete Datei wurde außerhalb des Editors geändert:"), BorderLayout.NORTH);
        JLabel path = new JLabel(changedFile.getAbsolutePath());
        path.setFont(path.getFont().deriveFont(Font.PLAIN, 11f));
        panel.add(path, BorderLayout.CENTER);
        JButton copyButton = new JButton("Aktuellen Code kopieren");
        copyButton.addActionListener(e -> {
            Toolkit.getDefaultToolkit().getSystemClipboard()
                .setContents(new StringSelection(textArea.getText()), null);
            statusLabel.setText("Aktueller Editor-Code wurde in die Zwischenablage kopiert");
        });
        panel.add(copyButton, BorderLayout.SOUTH);

        Object[] options = {"Neue Version laden", "Änderung ignorieren"};
        int choice;
        try {
            choice = JOptionPane.showOptionDialog(this, panel, "Datei extern geändert",
                JOptionPane.DEFAULT_OPTION, JOptionPane.WARNING_MESSAGE,
                null, options, options[0]);
        } finally {
            externalChangePromptOpen = false;
        }

        if (choice == 0) {
            if (!loadFile(changedFile)) {
                lastKnownFileFingerprint = changedFingerprint;
                lastKnownFileModified = changedFile.lastModified();
                lastKnownFileLength = changedFile.length();
                pendingExternalFingerprint = null;
            }
        } else {
            // Während des Dialogs kann es bereits eine weitere Änderung gegeben haben.
            refreshFileFingerprint();
            statusLabel.setText("Externe Änderung vorerst ignoriert");
        }
    }

    private void showSettingsDialog() {
        boolean autoReload = prefs.getBoolean("autoReloadExternalChanges", false);
        JRadioButton warnButton = new JRadioButton(
            "Bei externen Änderungen warnen und vor dem Laden nachfragen", !autoReload);
        JRadioButton autoButton = new JRadioButton(
            "Neue Version automatisch laden (Editorinhalt wird überschrieben)", autoReload);
        ButtonGroup group = new ButtonGroup();
        group.add(warnButton);
        group.add(autoButton);

        JPanel panel = new JPanel();
        panel.setLayout(new BoxLayout(panel, BoxLayout.Y_AXIS));
        panel.add(new JLabel("Wenn die aktuell geöffnete Datei von einem anderen Programm geändert wird:"));
        panel.add(Box.createVerticalStrut(8));
        panel.add(warnButton);
        panel.add(autoButton);

        int result = JOptionPane.showConfirmDialog(this, panel, "Einstellungen – Dateiüberwachung",
            JOptionPane.OK_CANCEL_OPTION, JOptionPane.PLAIN_MESSAGE);
        if (result == JOptionPane.OK_OPTION) {
            prefs.putBoolean("autoReloadExternalChanges", autoButton.isSelected());
            try { prefs.flush(); } catch (java.util.prefs.BackingStoreException ignored) {}
            statusLabel.setText(autoButton.isSelected()
                ? "Einstellung gespeichert: externe Änderungen automatisch laden"
                : "Einstellung gespeichert: vor externen Änderungen warnen");
        }
    }

    // ── Main ────────────────────────────────────────────────
    public static void main(String[] args) {
        Preferences p = Preferences.userNodeForPackage(Main.class);
        if (p.getBoolean("darkMode", false)) FlatDarkLaf.setup();
        else                                  FlatLightLaf.setup();

        SwingUtilities.invokeLater(() -> {
            Main editor = new Main(args);
            editor.setVisible(true);
        });
    }
}