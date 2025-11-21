"""
GUI Application for Converting Onshape CAM Studio G-code to WinCNC Format
=======================================================================

This module provides a simple graphical user interface (GUI) that allows
operators to select a G-code file exported from Onshape CAM Studio and
convert it to a WinCNC-compatible format for ShopSabre routers.  The
interface guides the user through selecting the input file, displays the
derived output file name (prefixed with ``SS23_``), and provides feedback
during the conversion process.  A confirmation dialog alerts the user
when the conversion succeeds or if an error occurs.

* Converts parentheses comments to WinCNC-friendly square brackets and
  removes semicolon comments.
* Splits spindle speed (``S``) and spindle start/stop commands
  (``M3``/``M4``/``M5``) onto separate lines.
* Inserts the last arc command (``G2``/``G3``) on subsequent lines
  containing arc parameters because arcs are not modal in WinCNC.
* Optionally removes tool changes (``M6``) for machines without
  automatic tool changers.
* Optionally removes mist coolant codes (``M7`` / ``M9``) if they are
  not relevant for the machine, or rewrites them to WinCNC's
  ``M11C<port>`` / ``M12C<port>`` mister control when configured.
"""

import json
import os
import re
import sys
import textwrap
import time
from dataclasses import dataclass, asdict
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional
from typing import List, Tuple, Any


# WindowsC:\Users\<YourUsername>\.onshape_to_wincnc_settings.json
# macOS/Users/<YourUsername>/.onshape_to_wincnc_settings.json
# Linux/home/<yourusername>/.onshape_to_wincnc_settings.json
SETTINGS_FILE = Path.home() / "AppData" / "Roaming" / "OnshapeToWinCNC" / '.onshape_to_wincnc_settings.json'

# Smart path: external file that users can edit
def get_external_data_file(filename: str) -> Path:
    """
    Returns a writable path for data files (like token_replacements.json)
    - Dev mode (.pyw): same folder as script
    - Frozen exe: %APPDATA%/OnshapeToWinCNC/filename
    Creates folder if needed.
    """
    if getattr(sys, 'frozen', False):
        # Running as compiled exe
        app_dir = Path.home() / "AppData" / "Roaming" / "OnshapeToWinCNC"
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir / filename
    else:
        # Running as .py script
        return Path(__file__).with_name(filename)


def ensure_token_file_exists():
    """Copy bundled token_replacements.json to external location on first run"""
    target = get_external_data_file("token_replacements.json")
    if target.exists():
        return target

    # Try to extract from bundled resources (PyInstaller)
    if getattr(sys, 'frozen', False):
        import tempfile
        bundled_path = Path(sys._MEIPASS) / "token_replacements.json"  # PyInstaller temp dir
        if bundled_path.exists():
            try:
                import shutil
                shutil.copy2(bundled_path, target)
                print(f"Extracted token_replacements.json to {target}")
                return target
            except Exception as e:
                print(f"Failed to extract token file: {e}")

    # Fallback: create minimal working version
    default_content = {
        "line_patterns": [
            {"match": "^[Oo]\\d+.*$", "action": "comment", "prefix": "[", "suffix": "]"},
            {"match": "^%.*$", "action": "comment", "prefix": "[", "suffix": ")"}
        ],
        "token_replacements": {
            "M6": "",
            "M7": "M11C8 [ ;Coolant On ]",
            "M8": "M11C8 [ ;Coolant On ]",
            "M9": "M12C8 [ ;Coolant Off ]",
            "G17": " [ G17 ;XY Plane Selection ]",
            "G40": "[ G40 ;Tool Radius Compensation Off ]",
            "G49": "[ G49 ;Tool Length Offset Cancel ]",
            "G80": "G80 [ ;Cancel Canned Cycle ]",
            "(T(?:[7-9]|1[0-6]))": "[\\1]"
        }
    }
    try:
        target.write_text(json.dumps(default_content, indent=2), encoding="utf-8")
        print(f"Created default token_replacements.json at {target}")
    except Exception as e:
        print(f"Could not create token file: {e}")
    return target


# THIS is the path you should use everywhere
TOKEN_REPLACEMENTS_FILE = ensure_token_file_exists()


BOILERPLATE_REPO_URL = "https://github.com/FRC7028/Onshape-to-WinCNC"


def build_boilerplate_header() -> list[str]:
    """Return a list of bracketed boilerplate comment lines for output files."""

    title_art = [
        "  ___  _   _ ____  _   _    _    ____  _____   _____ ___",
        " / _ \\| \\ | / ___|| | | |  / \\  |  _ \\| ____| |_   _/ _ \\",
        "| | | |  \\| \\___ \\| |_| | / _ \\ | |_) |  _|     | || | | |",
        "| |_| | |\\  |___) |  _  |/ ___ \\|  __/| |___    | || |_| |",
        " \\___/|_| \\_|____/|_| |_/_/   \\_\\_|   |_____|   |_| \\___/",
        "",
        "__        _____ _   _  ____ _   _  ____",
        "\\ \\      / /_ _| \\ | |/ ___| \\ | |/ ___|",
        " \\ \\ /\\ / / | ||  \\| | |   |  \\| | |",
        "  \\ V  V /  | || |\\  | |___| |\\  | |___",
        "   \\_/\\_/  |___|_| \\_|\\____|_| \\_|\\____|",
    ]

    team_art = [
        " _____ ___ ____  ___    _  _    __    ___ _____",
        "|___  / _ \\___ \\( _ )  | || |  / /_  / _ \\___  |",
        "   / / | | |__) / _ \\  | || |_| '_ \\| | | | / /",
        "  / /| |_| / __/ (_) | |__   _| (_) | |_| |/ /",
        " /_/  \\___/_____\\___/     |_|  \\___/ \\___//_/",
    ]

    info_lines = [
        "Developed by FRC 7028 Binary Battalion in collaboration with FRC 4607 CIS",
        BOILERPLATE_REPO_URL,
    ]

    def bracket(line: str) -> str:
        return f"[{line}]" if line else "[]"

    boilerplate = [bracket(line) for line in title_art]
    boilerplate.append("[]")
    boilerplate.extend(bracket(line) for line in team_art)
    boilerplate.append("[]")
    boilerplate.extend(bracket(line) for line in info_lines)
    boilerplate.append("")
    return boilerplate



# Cache the rules at startup
_LINE_RULES: List[dict] = []        # Full line processing rules
_TOKEN_RULES: List[Tuple[Any, str]] = []  # Token rules (regex or str, replacement)

def load_token_replacement_rules():
    """Load both line-level and token-level rules from token_replacements.json"""
    global _LINE_RULES, _TOKEN_RULES
    _LINE_RULES = []
    _TOKEN_RULES = []

    if not TOKEN_REPLACEMENTS_FILE.exists():
        print(f"Warning: {TOKEN_REPLACEMENTS_FILE} not found. Using minimal defaults.")
        # Minimal fallback
        _LINE_RULES = [
            {"regex": re.compile(r"^[Oo]\d+.*$", re.IGNORECASE), "action": "comment", "prefix": "[", "suffix": "]"},
            {"regex": re.compile(r"^%.*$", re.IGNORECASE), "action": "comment", "prefix": "[", "suffix": "]"}
        ]
        return

    try:
        raw_data = TOKEN_REPLACEMENTS_FILE.read_text(encoding="utf-8")
        data = json.loads(raw_data)
    except Exception as e:
        print(f"Error reading {TOKEN_REPLACEMENTS_FILE}: {e}")
        return

    # -------------------------------------------------------------
    # 1. Load full-line rules (comment out O-lines, %, etc.)
    # -------------------------------------------------------------
    line_patterns = data.get("line_patterns") or []
    for item in line_patterns:
        if isinstance(item, str):
            # Old format: just a regex → remove
            try:
                regex = re.compile(item, re.IGNORECASE)
                _LINE_RULES.append({"regex": regex, "action": "remove"})
            except re.error as e:
                print(f"Invalid line_pattern regex '{item}': {e}")

        elif isinstance(item, dict):
            match_pat = item.get("match", "").strip()
            if not match_pat:
                continue
            action = str(item.get("action", "remove")).lower()
            prefix = item.get("prefix", "")
            suffix = item.get("suffix", "")

            try:
                regex = re.compile(match_pat, re.IGNORECASE)
                _LINE_RULES.append({
                    "regex": regex,
                    "action": action if action in ("remove", "comment") else "remove",
                    "prefix": prefix,
                    "suffix": suffix
                })
            except re.error as e:
                print(f"Invalid line_pattern regex '{match_pat}': {e}")

    # -------------------------------------------------------------
    # 2. Load token replacement rules (supports regex + backreferences)
    # -------------------------------------------------------------
    token_data = data.get("token_replacements") or data  # backward compat

    for pattern, replacement in token_data.items():
        if not pattern or pattern.strip() == "":
            continue

        repl = "" if replacement is None else str(replacement)

        # Detect if pattern contains regex metacharacters or capture groups
        if any(c in pattern for c in r".+*^$[]\()|?{}") or pattern.startswith("("):
            # This is a regex pattern
            try:
                # Compile with anchors for full token match unless user specifies otherwise
                if not (pattern.startswith("^") or pattern.startswith(r"\b")):
                    pattern = "^" + pattern
                if not (pattern.endswith("$") or pattern.endswith(r"\b")):
                    pattern += "$"

                regex = re.compile(pattern, re.IGNORECASE)
                _TOKEN_RULES.append((regex, repl))
            except re.error as e:
                print(f"Invalid regex in token_replacements: '{pattern}' → {e}")
        else:
            # Simple literal match (e.g. "M6": "")
            _TOKEN_RULES.append((pattern.upper(), repl))

    print(f"Loaded {len(_LINE_RULES)} line rule(s) and {len(_TOKEN_RULES)} token rule(s) from {TOKEN_REPLACEMENTS_FILE.name}")

# Load rules on import
load_token_replacement_rules()


def apply_token_replacements(tokens: list[str]) -> list[str]:
    """
    Apply token replacement rules, including regex with capture groups like (N\\d+) → [\\1]
    """
    result = []

    for tok in tokens:
        original = tok
        replaced = False

        for rule, replacement in _TOKEN_RULES:
            if isinstance(rule, re.Pattern):
                # Full match with capture groups
                m = rule.fullmatch(tok)
                if m:
                    if replacement == "":
                        replaced = True
                        break
                    else:
                        # Expand \\1, \\2 etc. in replacement
                        try:
                            new_tok = m.expand(replacement)
                            tok = new_tok
                            replaced = True
                            break
                        except re.error:
                            # fallback: treat as literal
                            tok = replacement
                            replaced = True
                            break
            else:
                # Simple string match (old behavior)
                up = tok.upper()
                if up == rule or up.startswith(rule + " "):
                    if replacement == "":
                        replaced = True
                        break
                    else:
                        tok = replacement + (tok[len(rule):] if len(tok) > len(rule) else "")
                        replaced = True
                        break

        if not replaced:
            result.append(original)
        elif replacement != "":  # Only append if not removed
            result.append(tok)

    return result

def _env_int(name: str, default: Optional[int]) -> Optional[int]:
    """Helper to safely parse integer environment overrides."""

    raw = os.environ.get(name)
    if raw is None:
        return default
    raw = raw.strip()
    if not raw:
        return default
    try:
        value = int(raw, 10)
    except ValueError:
        return default
    return value if value > 0 else None


@dataclass
class MachineSettings:
    """Represents user-editable ShopSabre integration parameters."""

    output_directory: Optional[str] = None
    output_name_mode: str = 'prefix'
    output_name_value: str = 'SS23_'

    @staticmethod
    def _coerce_bool(value, fallback: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {'true', '1', 'yes', 'on'}:
                return True
            if normalized in {'false', '0', 'no', 'off'}:
                return False
        return fallback

    @staticmethod
    def _coerce_channel(value, fallback: Optional[int]) -> Optional[int]:
        if value in (None, ''):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return fallback
        return parsed if parsed > 0 else fallback

    @classmethod
    def load(cls) -> 'MachineSettings':
        defaults = {
            'output_directory': None,
            'output_name_mode': 'prefix',
            'output_name_value': 'SS23_',
        }
        data = {}
        if SETTINGS_FILE.exists():
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
            except Exception:
                data = {}
        raw_directory = data.get('output_directory')
        directory = str(raw_directory).strip() if raw_directory else ''
        directory = os.path.abspath(os.path.expanduser(directory)) if directory else None
        mode_raw = str(data.get('output_name_mode', defaults['output_name_mode'])).strip().lower()
        mode = mode_raw if mode_raw in ('prefix', 'suffix') else defaults['output_name_mode']
        name_value = str(data.get('output_name_value', defaults['output_name_value']))
        return cls(
            output_directory=directory,
            output_name_mode=mode,
            output_name_value=name_value,
        )

    def save(self) -> None:
        SETTINGS_FILE.write_text(json.dumps(asdict(self), indent=2), encoding='utf-8')


SETTINGS = MachineSettings.load()

def parentheses_to_bracket_lines(line: str) -> tuple[str, list[str]]:
    """Convert inline parentheses comments into bracket-only lines.

    The returned content line excludes parentheses segments. Each
    extracted comment is converted to a standalone ``[comment]`` line to
    satisfy WinCNC's preference for bracketed comments on their own
    lines. Nested parentheses are supported; unmatched parentheses leave
    the remainder untouched to avoid dropping user data.
    """

    content_chars = []
    bracket_comments: list[str] = []
    i = 0
    length = len(line)
    while i < length:
        char = line[i]
        if char == '(':
            i += 1
            depth = 1
            comment_start = i
            while i < length and depth > 0:
                if line[i] == '(':
                    depth += 1
                elif line[i] == ')':
                    depth -= 1
                    if depth == 0:
                        comment = line[comment_start:i].strip()
                        if comment:
                            bracket_comments.append(f'[{comment}]')
                        break
                i += 1
            if depth == 0:
                i += 1  # Skip the closing parenthesis
            else:
                # Unmatched parentheses; keep the raw remainder
                content_chars.append('(')
                content_chars.append(line[comment_start:])
                break
        else:
            content_chars.append(char)
            i += 1
    content_line = ''.join(content_chars).strip()
    return content_line, bracket_comments


def remove_semicolon_comments(line: str) -> str:
    """Remove everything after a semicolon comment."""
    if ';' in line:
        return line.split(';', 1)[0]
    return line


def split_spindle_speed_and_m(line: str):
    """Split S-word from M3/M4/M5 if they appear together in one block."""
    tokens = line.strip().split()
    s_index = None
    m_index = None
    for i, token in enumerate(tokens):
        if token.upper().startswith('S') and token[1:].replace('.', '').isdigit():
            s_index = i
        if token.upper() in ('M3', 'M4', 'M5'):
            m_index = i
    if s_index is not None and m_index is not None and m_index > s_index:
        return [' '.join(tokens[:m_index]), ' '.join(tokens[m_index:])]
    return [line]


def process_arc_line(line: str, last_g: str):
    """Maintain non-modal behaviour for G2/G3.

    If a line contains no G-code but has arc centre parameters (I/J/K/R)
    following a G2/G3, prefix the previous G-code.
    """
    stripped = line.strip()
    if not stripped:
        return line, last_g
    tokens = stripped.split()
    gcode_pattern = re.compile(r'G0?\d+(\.\d+)?', re.IGNORECASE)
    g_found = None
    for t in tokens:
        if gcode_pattern.match(t):
            g_found = t.upper()
            break
    if g_found:
        last_g = g_found
        return line, last_g
    # If the last G was G2/G3 and arc params present, prefix it
    if last_g in ('G2', 'G02', 'G3', 'G03'):
        if any(tok[0].upper() in ('I', 'J', 'K', 'R') for tok in tokens):
            # Sequence numbers (N words) are removed in the improved converter,
            # so we can simply prefix without worrying about them.
            return f"{last_g} {line.lstrip()}", last_g
    return line, last_g


def split_by_multiple_commands(tokens):
    """Divide tokens into groups with at most one G or M command."""
    lines = []
    current = []
    has_command = False
    for tok in tokens:
        if not tok:
            continue
        up = tok.upper()
        is_command = up.startswith('G') or up.startswith('M')
        if is_command:
            if has_command and current:
                lines.append(current)
                current = []
                has_command = False
            current.append(tok)
            has_command = True
        else:
            current.append(tok)
    if current:
        lines.append(current)
    return lines


def get_g_code(token: str):
    m = re.match(r'^G\d+(\.\d+)?', token, re.IGNORECASE)
    if m:
        return m.group(0).upper()
    return None


def convert_lines(lines):
    converted = []
    last_motion = None

    """
    Convert a list of G-code lines into WinCNC-friendly format using JSON config.
    """
    for original_line in lines:
        line = original_line.rstrip('\n').rstrip('\r')

        # 1. Full-line handling: comment out or remove lines based on JSON rules
        handled = False
        for rule in _LINE_RULES:
            if rule["regex"].match(line):
                action = rule["action"]
                if action == "remove":
                    handled = True
                    break
                elif action == "comment":
                    commented = f"{rule['prefix']}{line.strip()}{rule['suffix']}"
                    converted.append(commented)
                    handled = True
                    break
        if handled:
            continue

        # 2. Remove semicolon comments
        line = remove_semicolon_comments(line)

        # 3. Convert (comments) → [comments] and extract them
        content_line, bracket_comments = parentheses_to_bracket_lines(line)
        if not content_line.strip() and not bracket_comments:
            converted.append('')
            continue

        # 4. Split S-word from M3/M4/M5 if combined
        split_lines = []
        for sm_line in split_spindle_speed_and_m(content_line.strip()):
            tokens = sm_line.split()
            if not tokens:
                continue

            # ===== FIXED ORDER: SPLIT COMMANDS FIRST =====
            grouped = split_by_multiple_commands(tokens)
            for group in grouped:
                if not group:
                    continue
                # Temporarily join to apply arc/modal logic correctly
                temp_line = ' '.join(group)
                split_lines.append((group, temp_line))

        # Now process each pre-split group
        for raw_tokens, temp_line in split_lines:
            # Re-determine motion mode from original tokens
            g_code_in_line = None
            for tok in raw_tokens:
                g_code = get_g_code(tok)
                if g_code:
                    g_code_in_line = g_code
                    break

            if g_code_in_line:
                m = re.match(r'^G0?([0123])', g_code_in_line)
                if m:
                    last_motion = f"G{m.group(1)}"

            # Insert modal motion code if needed (non-modal G2/G3 support)
            if not g_code_in_line and last_motion:
                has_arc = any(tok[0].upper() in ('I', 'J', 'K', 'R') for tok in raw_tokens)
                has_lin = any(tok[0].upper() in ('X', 'Y', 'Z', 'A', 'B', 'C') for tok in raw_tokens)
                if last_motion in ('G2', 'G3') and has_arc:
                    raw_tokens.insert(0, last_motion)
                elif last_motion in ('G0', 'G1') and has_lin:
                    raw_tokens.insert(0, last_motion)

            # ===== NOW APPLY TOKEN REPLACEMENTS (after splitting!) =====
            final_tokens = apply_token_replacements(raw_tokens)
            if final_tokens:
                converted.append(' '.join(final_tokens))

        # Add extracted bracket comments (from parentheses)
        converted.extend(bracket_comments)

    # ------------------------------------------------------------------
    # Post-processing: G49 handling (tool length compensation cancel)
    # ------------------------------------------------------------------
    m5_index = None
    for idx, ln in enumerate(converted):
        if ln.strip().upper().startswith('M5'):
            m5_index = idx
            break

    final_lines = []
    if m5_index is None:
        # No M5 → keep only the last G49
        g49_indices = [i for i, ln in enumerate(converted) if ln.strip().upper() == 'G49']
        remove_set = set(g49_indices[:-1])
        for i, ln in enumerate(converted):
            if i in remove_set and ln.strip().upper() == 'G49':
                continue
            final_lines.append(ln)
    else:
        seen_m5 = False
        for ln in converted:
            stripped = ln.strip().upper()
            if stripped.startswith('M5'):
                seen_m5 = True
            if stripped == 'G49':
                if not seen_m5:
                    continue  # Remove G49 before first M5
            final_lines.append(ln)

    # ------------------------------------------------------------------
    # Ensure two blank lines after first G90
    # ------------------------------------------------------------------
    for idx, line in enumerate(final_lines):
        if line.strip().upper() == 'G90':
            blank_count = 0
            j = idx + 1
            while j < len(final_lines) and not final_lines[j].strip():
                blank_count += 1
                j += 1
            while blank_count < 2:
                final_lines.insert(idx + 1, '')
                blank_count += 1
            break

    return final_lines


def convert_file(
    input_path: str,
    output_path: str
) -> None:
    """Convert the input G-code file and write to the given output path.

    Parameters
    ----------
    input_path : str
        Input G-code file path.
    output_path : str
        Output G-code file path.
    Raises
    ------
    IOError
        On file errors.
    """
    with open(input_path, 'r', encoding='utf-8', errors='ignore') as f_in:
        lines = f_in.readlines()
    converted = convert_lines(
        lines
    )
    boilerplate = build_boilerplate_header()
    with open(output_path, 'w', encoding='utf-8') as f_out:
        for cl in boilerplate:
            f_out.write(cl.rstrip() + '\n')
        for cl in converted:
            f_out.write(cl.rstrip() + '\n')


class ConverterGUI:
    """Graphical interface for Onshape to WinCNC conversion."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title('Onshape to WinCNC Converter')
        self.palette = {
            'primary': '#001489',
            'accent': '#ffd400',
            'accent_active': '#e6be00',
            'background': '#001489',
            'card': '#ffffff',
            'border': '#ffd400',
            'text': '#0f172a',
            'muted_text': '#4b5563',
            'on_primary_text': '#ffffff',
            'muted_on_primary': '#e2e8f0',
        }
        self.root.configure(bg=self.palette['background'])
        self.settings = SETTINGS
        self.output_settings_window: Optional[tk.Toplevel] = None

        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            # Fallback to default theme if clam is unavailable.
            pass
        style.configure('TFrame', background=self.palette['background'])
        style.configure(
            'Card.TFrame',
            background=self.palette['card'],
            borderwidth=1,
            relief='solid',
            bordercolor=self.palette['border'],
        )
        style.configure(
            'Card.TLabel',
            background=self.palette['card'],
            foreground=self.palette['text'],
            font=('Segoe UI', 10),
        )
        style.configure(
            'Heading.TLabel',
            background=self.palette['card'],
            foreground=self.palette['accent'],
            font=('Segoe UI Semibold', 11),
        )
        style.configure(
            'Body.TLabel',
            background=self.palette['background'],
            foreground=self.palette['on_primary_text'],
            font=('Segoe UI', 10),
        )
        style.configure(
            'Status.TLabel',
            background=self.palette['background'],
            foreground=self.palette['accent'],
            font=('Segoe UI', 10),
        )
        style.configure(
            'ToolbarHeading.TLabel',
            background=self.palette['background'],
            foreground=self.palette['accent'],
            font=('Segoe UI Semibold', 13),
        )
        style.configure(
            'MutedOnPrimary.TLabel',
            background=self.palette['background'],
            foreground=self.palette['muted_on_primary'],
            font=('Segoe UI', 9, 'italic'),
        )
        style.configure(
            'Accent.TButton',
            font=('Segoe UI Semibold', 11),
            padding=(12, 6),
            foreground='#000000',
            background=self.palette['accent'],
            bordercolor=self.palette['accent'],
            focusthickness=1,
        )
        style.map(
            'Accent.TButton',
            background=[('active', self.palette['accent_active'])],
            foreground=[('disabled', '#6b7280')],
            bordercolor=[('active', self.palette['accent_active'])],
        )

        self.main_frame = ttk.Frame(root, padding=20)
        self.main_frame.grid(row=0, column=0, sticky='nsew')
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        # Instruction card
        instructions = (
            "This program converts Onshape CAM Studio g-code to Shop Sabre WinCNC compatible g-code.\n"
            "To prepare your file for this operation, post from Onshape with these settings:\n"
            "  • Machine = 3-Axis Generic Milling - Fanuc\n"
            "  • Fixed Cycles = All options turned OFF\n"
        )
        info_card = ttk.Frame(self.main_frame, style='Card.TFrame', padding=15)
        info_card.grid(row=0, column=0, sticky='ew')
        info_label = ttk.Label(
            info_card,
            text=instructions,
            style='Card.TLabel',
            justify='left',
            anchor='w',
            wraplength=580
        )
        info_label.grid(row=0, column=0, sticky='w')

        # File selection card
        file_card = ttk.Frame(self.main_frame, style='Card.TFrame', padding=15)
        file_card.grid(row=1, column=0, pady=15, sticky='ew')
        file_card.columnconfigure(1, weight=1)

        ttk.Label(file_card, text='Input G-code file', style='Heading.TLabel').grid(
            row=0, column=0, columnspan=3, sticky='w', pady=(0, 10)
        )
        ttk.Label(file_card, text='Location', style='Card.TLabel').grid(row=1, column=0, sticky='w')
        self.input_entry = ttk.Entry(file_card)
        self.input_entry.grid(row=1, column=1, padx=10, sticky='ew')
        ttk.Button(file_card, text='Browse…', command=self.select_input).grid(row=1, column=2)

        ttk.Label(file_card, text='Output file name', style='Card.TLabel').grid(
            row=2, column=0, sticky='w', pady=(12, 0)
        )
        self.output_entry = ttk.Entry(file_card)
        self.output_entry.grid(row=2, column=1, padx=10, pady=(12, 0), sticky='ew')
        self.output_entry.configure(state='readonly')

        ttk.Button(
            file_card,
            text='Output Settings…',
            command=self.open_output_settings_dialog,
        ).grid(row=3, column=0, columnspan=3, sticky='w', pady=(12, 0))

        ttk.Button(
            file_card,
            text='Edit Token Rules (Advanced)…',
            command=self.open_token_rules_editor,
        ).grid(row=4, column=0, columnspan=3, sticky='w', pady=(8, 0))

        # Actions and status
        action_frame = ttk.Frame(self.main_frame, style='TFrame', padding=(0, 15, 0, 0))
        action_frame.grid(row=3, column=0, sticky='ew')
        action_frame.columnconfigure(0, weight=1)

        self.convert_button = ttk.Button(
            action_frame,
            text='Convert File',
            style='Accent.TButton',
            command=self.convert
        )
        self.convert_button.grid(row=0, column=0, pady=(0, 10))

        self.status_var = tk.StringVar()
        self.status_var.set('Select a file to convert.')
        self.status_label = ttk.Label(action_frame, textvariable=self.status_var, style='Status.TLabel', wraplength=560)
        self.status_label.grid(row=1, column=0, sticky='w')

    def select_input(self) -> None:
        """Handle the file selection dialog for the input file."""
        path = filedialog.askopenfilename(
            title='Select Onshape G-code file',
            filetypes=[
                ('G-code Files', '*.nc *.tap *.gcode *.txt'),
                ('All Files', '*.*')
            ]
        )
        if not path:
            return
        self.input_entry.delete(0, tk.END)
        self.input_entry.insert(0, path)
        out_path = self._derive_output_path(path)
        self._set_output_entry(out_path)
        self.status_var.set('Ready to convert.')

    def _set_output_entry(self, value: str) -> None:
        self.output_entry.configure(state='normal')
        self.output_entry.delete(0, tk.END)
        self.output_entry.insert(0, value)
        self.output_entry.configure(state='readonly')

    def _derive_output_path(self, input_path: str) -> str:
        directory = self.settings.output_directory or os.path.dirname(input_path)
        directory = os.path.abspath(os.path.expanduser(directory))
        base_name = os.path.basename(input_path)
        name_root, _ = os.path.splitext(base_name)
        ext = '.tap'
        value = self.settings.output_name_value or ''
        if self.settings.output_name_mode == 'suffix':
            file_name = f"{name_root}{value}{ext}"
        else:
            file_name = f"{value}{name_root}{ext}"
        return os.path.join(directory, file_name)

    def _update_output_entry_for_current_input(self) -> None:
        input_path = self.input_entry.get().strip()
        if not input_path:
            return
        derived = self._derive_output_path(input_path)
        self._set_output_entry(derived)

    def convert(self) -> None:
        """Perform the conversion when the Convert button is clicked."""
        input_path = self.input_entry.get().strip()
        output_path = self.output_entry.get().strip()

        if not input_path:
            messagebox.showerror('Error', 'No input file selected.')
            return
        if not os.path.isfile(input_path):
            messagebox.showerror('Error', 'Input file does not exist.')
            return
        try:
            self.status_var.set('Checking file...')
            self.root.update_idletasks()

            # If no issue detected, perform conversion
            self.status_var.set('Converting...')
            self.root.update_idletasks()
            convert_file(
                input_path,
                output_path,
            )

            self.status_var.set(f'Conversion complete: {output_path}')
            messagebox.showinfo('Conversion Complete', f'Converted file saved to:\n{output_path}')
        except Exception as e:
            self.status_var.set('Conversion failed.')
            messagebox.showerror('Error', f'An error occurred during conversion:\n{e}')

    def open_output_settings_dialog(self) -> None:
        """Open dialog for configuring output directory and file naming."""

        if self.output_settings_window and tk.Toplevel.winfo_exists(self.output_settings_window):
            self.output_settings_window.lift()
            self.output_settings_window.focus_set()
            return

        win = tk.Toplevel(self.root)
        win.title('Customize Output Settings')
        win.configure(bg=self.palette['background'])
        win.resizable(False, False)
        win.transient(self.root)
        self.output_settings_window = win
        self.output_settings_window.protocol('WM_DELETE_WINDOW', self._close_output_settings_window)

        container = ttk.Frame(win, padding=20)
        container.grid(row=0, column=0, sticky='nsew')

        card = ttk.Frame(container, style='Card.TFrame', padding=15)
        card.grid(row=0, column=0, sticky='ew')
        card.columnconfigure(1, weight=1)

        ttk.Label(card, text='Default Output Location', style='Heading.TLabel').grid(
            row=0, column=0, columnspan=3, sticky='w'
        )
        ttk.Label(card, text='Folder', style='Card.TLabel').grid(row=1, column=0, sticky='w', pady=(8, 0))
        self.output_dir_var = tk.StringVar(value=self.settings.output_directory or '')
        dir_entry = ttk.Entry(card, textvariable=self.output_dir_var)
        dir_entry.grid(row=1, column=1, padx=(10, 0), pady=(8, 0), sticky='ew')
        ttk.Button(card, text='Browse…', command=self._browse_output_directory).grid(
            row=1, column=2, padx=(10, 0), pady=(8, 0)
        )
        ttk.Label(
            card,
            text='Leave blank to save next to the selected input file.',
            style='Card.TLabel',
            wraplength=360,
        ).grid(row=2, column=0, columnspan=3, sticky='w')

        ttk.Label(card, text='File Name Format', style='Heading.TLabel').grid(
            row=3, column=0, columnspan=3, sticky='w', pady=(20, 0)
        )
        ttk.Label(card, text='Mode', style='Card.TLabel').grid(row=4, column=0, sticky='w', pady=(8, 0))
        self.output_mode_var = tk.StringVar(
            value='Prefix' if self.settings.output_name_mode == 'prefix' else 'Suffix'
        )
        ttk.Combobox(
            card,
            textvariable=self.output_mode_var,
            values=['Prefix', 'Suffix'],
            state='readonly',
            width=10,
        ).grid(row=4, column=1, padx=(10, 0), pady=(8, 0), sticky='w')

        ttk.Label(card, text='Text', style='Card.TLabel').grid(row=5, column=0, sticky='w', pady=(8, 0))
        self.output_value_var = tk.StringVar(value=self.settings.output_name_value)
        ttk.Entry(card, textvariable=self.output_value_var).grid(
            row=5, column=1, columnspan=2, padx=(10, 0), pady=(8, 0), sticky='ew'
        )
       

        button_frame = ttk.Frame(container, padding=(0, 15, 0, 0))
        button_frame.grid(row=1, column=0, sticky='ew')
        button_frame.columnconfigure(0, weight=1)

        ttk.Button(
            button_frame,
            text='Save Output Settings',
            style='Accent.TButton',
            command=self._save_output_settings
        ).grid(row=0, column=0, sticky='ew')

        ttk.Button(
            button_frame,
            text='Cancel',
            command=self._close_output_settings_window
        ).grid(row=1, column=0, sticky='ew', pady=(10, 0))

    def _browse_output_directory(self) -> None:
        directory = filedialog.askdirectory(title='Select output directory')
        if not directory:
            return
        self.output_dir_var.set(directory)

    def _close_output_settings_window(self) -> None:
        if self.output_settings_window:
            self.output_settings_window.destroy()
            self.output_settings_window = None

    def _save_output_settings(self) -> None:
        directory = self.output_dir_var.get().strip()
        normalized_dir = os.path.abspath(os.path.expanduser(directory)) if directory else None
        if normalized_dir and not os.path.isdir(normalized_dir):
            messagebox.showerror('Invalid Directory', 'The selected directory does not exist. Create it first or leave blank.')
            return

        mode = self.output_mode_var.get().strip().lower()
        mode = 'prefix' if mode not in ('prefix', 'suffix') else mode
        value = self.output_value_var.get()

        self.settings.output_directory = normalized_dir
        self.settings.output_name_mode = mode
        self.settings.output_name_value = value

        try:
            self.settings.save()
        except OSError as exc:
            messagebox.showerror('Save Failed', f'Unable to save settings:\n{exc}')
            return

        self._update_output_entry_for_current_input()
        messagebox.showinfo('Settings Saved', 'Output settings saved successfully.')
        self._close_output_settings_window()

    def _parse_channel_value(self, raw: str, label: str) -> Optional[int]:
        value = (raw or '').strip()
        if not value:
            return None
        try:
            parsed = int(value)
        except ValueError:
            raise ValueError(f'{label} must be a positive integer or left blank.')
        if parsed <= 0:
            raise ValueError(f'{label} must be greater than zero.')
        return parsed
    
    def open_token_rules_editor(self):
        """Open a modal window with a live editor for token_replacements.json"""
        if not TOKEN_REPLACEMENTS_FILE.exists():
            messagebox.showerror("File Not Found", f"Cannot find token rules file:\n{TOKEN_REPLACEMENTS_FILE}")
            return

        editor_win = tk.Toplevel(self.root)
        editor_win.title(f"Edit Token Rules — {TOKEN_REPLACEMENTS_FILE.name}")
        editor_win.geometry("1000x740")
        editor_win.minsize(800, 600)
        editor_win.configure(bg=self.palette['background'])
        editor_win.transient(self.root)
        editor_win.grab_set()
        editor_win.focus_set()

        # Center the window
        editor_win.update_idletasks()
        x = (editor_win.winfo_screenwidth() // 2) - (editor_win.winfo_width() // 2)
        y = (editor_win.winfo_screenheight() // 2) - (editor_win.winfo_height() // 2)
        editor_win.geometry(f"+{x}+{y-30}")

        # Main container
        main = ttk.Frame(editor_win, padding=15)
        main.pack(fill='both', expand=True)

        # Header
        header_frame = ttk.Frame(main, style='TFrame')
        header_frame.pack(fill='x', pady=(0, 10))

        ttk.Label(
            header_frame,
            text="Edit token_replacements.json",
            style='ToolbarHeading.TLabel'
        ).pack(side='left')

        # Status bar at top-right
        status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(header_frame, textvariable=status_var, style='Status.TLabel')
        status_label.pack(side='right')

        # Instructions
        ttk.Label(
            main,
            text="Changes take effect immediately after clicking 'Save & Reload Rules'",
            style='MutedOnPrimary.TLabel'
        ).pack(anchor='w', pady=(0, 10))

        # Text editor with scrollbars
        text_frame = ttk.Frame(main)
        text_frame.pack(fill='both', expand=True, pady=(0, 10))

        text_widget = tk.Text(
            text_frame,
            wrap='none',
            font=('Consolas', 11),
            undo=True,
            autoseparators=True,
            maxundo=-1,
            insertwidth=2,
            padx=8,
            pady=8
        )
        v_scroll = ttk.Scrollbar(text_frame, orient='vertical', command=text_widget.yview)
        h_scroll = ttk.Scrollbar(text_frame, orient='horizontal', command=text_widget.xview)
        text_widget.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        text_widget.grid(row=0, column=0, sticky='nsew')
        v_scroll.grid(row=0, column=1, sticky='ns')
        h_scroll.grid(row=1, column=0, sticky='ew')
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        # Load current content (pretty-print if valid JSON)
        try:
            raw_content = TOKEN_REPLACEMENTS_FILE.read_text(encoding='utf-8')
            try:
                data = json.loads(raw_content)
                pretty = json.dumps(data, indent=4, ensure_ascii=False)
                text_widget.insert('1.0', pretty)
            except:
                text_widget.insert('1.0', raw_content)
        except Exception as e:
            text_widget.insert('1.0', f"; ERROR READING FILE: {e}\n\n{raw_content}")

        # Button frame at bottom
        button_frame = ttk.Frame(main)
        button_frame.pack(fill='x')

        # Left side buttons
        left_buttons = ttk.Frame(button_frame)
        left_buttons.pack(side='left')

        ttk.Button(
            left_buttons,
            text="Save & Reload Rules",
            style='Accent.TButton',
            command=lambda: save_and_reload()
        ).pack(side='left', padx=(0, 8))

        ttk.Button(
            left_buttons,
            text="Restore Default",
            command=lambda: restore_default()
        ).pack(side='left')

        # Right side: Close button
        right_buttons = ttk.Frame(button_frame)
        right_buttons.pack(side='right')

        ttk.Button(
            right_buttons,
            text="Close",
            command=editor_win.destroy
        ).pack(side='right')

        # Functions used in buttons
        def save_and_reload():
            content = text_widget.get('1.0', 'end-1c').rstrip()
            if not content.strip():
                messagebox.showwarning("Empty File", "The file is empty. Save aborted.")
                return

            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as e:
                messagebox.showerror("Invalid JSON", f"JSON syntax error:\n\n{e}")
                return

            # Optional regex validation (warnings only)
            warnings = []
            for item in parsed.get("line_patterns", []):
                if isinstance(item, dict) and item.get("match"):
                    try:
                        re.compile(item["match"])
                    except re.error as e:
                        warnings.append(f"line_patterns → '{item['match']}' → {e}")

            for pat in parsed.get("token_replacements", {}).keys():
                if any(c in pat for c in ".+*^$[]()|?{}"):
                    try:
                        test = pat if pat.startswith('^') else '^' + pat
                        test = test if test.endswith('$') else test + '$'
                        re.compile(test)
                    except re.error as e:
                        warnings.append(f"token_replacements → '{pat}' → {e}")

            if warnings:
                if not messagebox.askyesno("Regex Warnings",
                    "Some regex patterns may be invalid:\n\n" + "\n".join(warnings[:8]) +
                    "\n\nSave anyway?"):
                    return

            # === SAVE FILE ===
            try:
                TOKEN_REPLACEMENTS_FILE.write_text(content + "\n", encoding='utf-8')
            except Exception as e:
                messagebox.showerror("Save Failed", f"Could not write file:\n{e}")
                return

            # === RELOAD RULES ===
            try:
                load_token_replacement_rules()
                save_time = time.strftime('%H:%M:%S')
                full_path = str(TOKEN_REPLACEMENTS_FILE.resolve())

                status_var.set(f"Saved & reloaded • {save_time}")
                
                try:
                    import subprocess
                    import platform
                    full_path = str(TOKEN_REPLACEMENTS_FILE.resolve())
                    if platform.system() == "Windows":
                        # Make path clickable in messagebox (using HTML-like trick in title)
                        messagebox.showinfo(
                            "Success ✓",
                            f"Token rules saved and reloaded!\n\n"
                            f"Location:\n{full_path}\n\n"
                            f"Click the path above and press Ctrl+C to copy.\n"
                            f"Time: {save_time}",
                            parent=editor_win
                        )
                        # Auto-copy path to clipboard
                        editor_win.clipboard_clear()
                        editor_win.clipboard_append(full_path)
                        editor_win.update()
                        status_var.set(f"Saved • Path copied to clipboard • {save_time}")
                    else:
                        messagebox.showinfo("Success ✓", 
                            f"Saved & reloaded!\n\nLocation:\n{full_path}\n\nTime: {save_time}")
                except:
                    messagebox.showinfo("Success ✓", 
                        f"Saved & reloaded!\n\nLocation:\n{full_path}\n\nTime: {save_time}")
            except Exception as e:
                status_var.set("Reload failed")
                messagebox.showerror("Reload Error", 
                    f"File was saved, but failed to reload rules:\n\n{e}\n\n"
                    f"Location:\n{TOKEN_REPLACEMENTS_FILE.resolve()}")

        def restore_default():
            if messagebox.askyesno("Restore Default", "Replace current content with the default token rules?"):
                default_json = {
                    "line_patterns": [
                        {"match": "^[Oo]\\d+.*$", "action": "comment", "prefix": "[", "suffix": "]"},
                        {"match": "^%.*$", "action": "comment", "prefix": "[", "suffix": "]"}
                    ],
                    "token_replacements": {
                        "M6": "",
                        "M7": "M11C8 [ ;Coolant On ]",
                        "M8": "M11C8 [ ;Coolant On ]",
                        "M9": "M12C8 [ ;Coolant Off ]",
                        "G17": " [ G17 ;XY Plane Selection ]",
                        "G40": "[ G40 ;Tool Radius Compensation Off ]",
                        "G49": "[ G49 ;Tool Length Offset Cancel ]",
                        "G80": "G80 [ ;Cancel Canned Cycle ]",
                        "G98": "[ G98 ;Return to Initial Point in Canned Cycle ]",
                        "(T(?:[7-9]|1[0-6]))": "[\\1]"
                    }
                }
                pretty = json.dumps(default_json, indent=4)
                text_widget.delete('1.0', 'end')
                text_widget.insert('1.0', pretty)
                status_var.set("Default rules loaded • click Save to apply")

        # Auto-save reminder on close
        def on_close():
            if text_widget.edit_modified():
                if messagebox.askyesno("Unsaved Changes", 
                    "You have unsaved changes in the token rules.\n\nSave before closing?"):
                    save_and_reload()
            editor_win.destroy()

        editor_win.protocol("WM_DELETE_WINDOW", on_close)


def main() -> None:
    root = tk.Tk()
    ConverterGUI(root)
    root.resizable(False, False)
    root.mainloop()


if __name__ == '__main__':
    main()
