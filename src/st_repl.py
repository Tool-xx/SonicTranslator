#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SonicTranslator — interactive command menu.

Launched by `python st.py` (no arguments). A minimalist menu driven by
typed commands at the "> " prompt:

    > help             — every command, explained
    > langs [filter]   — all target languages (e.g. "langs port")
    > example.txt ru   — translate that file to Russian
    > hello world ru   — translate inline text
    > clip ru          — translate what's in the clipboard
    > hist             — recent translations
    > !2               — copy history entry #2
    > clear            — clean screen (incl. scrollback), show the menu again
    > exit             — quit

Anything that is not a known command is treated as a translation request,
so `> example.txt ru` and `> hello world ru` just work. The browser session
stays alive for the whole run — consecutive translations are fast.

Long listings (``langs``, ``hist``, ``help``) are paged when they are taller
than the terminal: Enter shows the next page, q quits — nothing is ever
cut off, no terminal scrollback required.

When stdin is not a terminal (piped commands, tests) the same command set
runs on a plain input() loop.
"""

import os
import sys
import json
import queue
import shutil
import tempfile
import threading
import datetime

from st_core import (
    LANG_CODES,
    LANGUAGES,
    TranslationSession,
    get_config_dir,
    get_user_data_dir,
    read_text_file,
    resolve_target_lang,
)
from animations import TranslationAnimation, register_custom_spinners

try:
    import pyperclip
except ImportError:
    print(
        "Error: missing dependency 'pyperclip'. Install with: pip install pyperclip",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
except ImportError:
    print(
        "Error: missing dependency 'rich'. Install with: pip install rich",
        file=sys.stderr,
    )
    sys.exit(1)

VERSION = "1.1.0"
REPO_URL = "https://github.com/Tool-xx/SonicTranslator"
HISTORY_FILE = os.path.join(get_config_dir(), "history.json")
HISTORY_LIMIT = 50

# Project root — one level up from src/ where this file lives.
# start.bat / start.sh cd into src/ before launching, so CWD is src/;
# user files (abc.txt, notes.md …) live in the project root.
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

COMMANDS = [
    "help", "?", "h", "langs", "tr", "file", "clip", "hist", "copy", "new",
    "status", "theme", "clear", "about", "exit", "quit", "q", "bye",
]


# ═══════════════════════════════════════════════════════════════════════════
#  HISTORY (persisted between runs)
# ═══════════════════════════════════════════════════════════════════════════
def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_history(history):
    """Atomically save history to disk (tempfile + rename)."""
    try:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        data = json.dumps(history[-HISTORY_LIMIT:], ensure_ascii=False, indent=2)
        fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(HISTORY_FILE), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp_path, HISTORY_FILE)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
#  WORKER SESSION — the browser lives in a thread, not the main thread
# ═══════════════════════════════════════════════════════════════════════════
class WorkerSession:
    """TranslationSession driven from a background thread.

    Playwright's sync API keeps the main thread's asyncio event loop running
    while the browser session is alive. That makes prompt_toolkit's
    ``asyncio.run()`` raise "cannot be called from a running event loop" on
    the very next prompt after the first translation. Moving the whole
    session into a worker thread leaves the main thread's loop free, so the
    menu keeps working with the browser open.

    Calls are synchronous from the caller's point of view: a request is
    handed to the worker over a queue and the caller blocks until the result
    (or the error) comes back. The thread is daemonic, so an abandoned
    session dies with the process.

    If the user interrupts a translation (Ctrl+C), the request already being
    processed by the worker finishes in the background; requests that were
    still queued are marked cancelled and skipped, so the next translation
    does not wait behind an abandoned one.
    """

    def __init__(self):
        self._session = None
        self._startup_error = None
        self._requests = queue.Queue()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="sonic-session", daemon=True
        )
        self._thread.start()
        self._ready.wait(timeout=10)

    # ── worker thread ────────────────────────────────────────────────────
    def _run(self):
        try:
            self._session = TranslationSession()
        except Exception as e:
            self._startup_error = e
        self._ready.set()
        try:
            while not self._stop.is_set():
                try:
                    func, holder = self._requests.get(timeout=0.2)
                except queue.Empty:
                    continue
                if holder.get("cancelled"):
                    continue  # the caller gave up (Ctrl+C); skip the orphan
                try:
                    holder["result"] = func(self._session)
                except BaseException as e:
                    # BaseException, not Exception: a crash in the worker must
                    # surface in the caller, never be silently swallowed.
                    holder["error"] = e
                finally:
                    holder["done"].set()
        finally:
            try:
                if self._session is not None:
                    self._session.close()
            except Exception:
                pass
            # Fail any requests that queued up while we were stopping so the
            # caller can never hang on a dead worker.
            while True:
                try:
                    _, holder = self._requests.get_nowait()
                except queue.Empty:
                    break
                holder["error"] = RuntimeError("The translation session stopped.")
                holder["done"].set()

    # ── main-thread API ──────────────────────────────────────────────────
    def _call(self, func):
        if self._session is None:
            raise RuntimeError(
                "The browser session could not start."
                + (f" {self._startup_error}" if self._startup_error else "")
            )
        holder = {"done": threading.Event(), "result": None, "error": None}
        self._requests.put((func, holder))
        # Wait for the worker, but never forever: if the thread dies with a
        # request in flight (crash, close during a translation), fail fast
        # instead of hanging the menu. An interrupt marks the request as
        # cancelled so the worker skips it if it is still queued.
        try:
            while not holder["done"].wait(timeout=0.25):
                if not self._thread.is_alive():
                    holder["error"] = RuntimeError("The translation session stopped.")
                    break
        except KeyboardInterrupt:
            holder["cancelled"] = True
            raise
        if holder["error"] is not None:
            raise holder["error"]
        return holder["result"]

    def translate(self, text, target_lang):
        """Translate through the worker thread. Raises on failure."""
        return self._call(lambda s: s.translate(text, target_lang))

    def reset_chat(self):
        """Start a fresh Duck.ai chat ("New Chat")."""
        self._call(lambda s: s.reset_chat())

    def close(self):
        """Stop the worker; the session is closed inside the thread."""
        self._stop.set()
        self._thread.join(timeout=3)

    # ── state (read from the main thread; benignly stale at worst) ───────
    @property
    def alive(self):
        s = self._session
        return bool(s is not None and s.alive)

    @property
    def translation_count(self):
        s = self._session
        return s.translation_count if s is not None else 0

    @property
    def user_data_dir(self):
        s = self._session
        return s.user_data_dir if s is not None else get_user_data_dir()


# ═══════════════════════════════════════════════════════════════════════════
#  CONTEXT
# ═══════════════════════════════════════════════════════════════════════════
class ReplContext:
    def __init__(self, console):
        self.console = console
        self.session = WorkerSession()
        self.history = load_history()
        self.last_result = None
        self.dark = True

    def acc(self):
        """Accent color for the current theme."""
        return "cyan" if self.dark else "blue"


# ═══════════════════════════════════════════════════════════════════════════
#  MENU RENDERING
# ═══════════════════════════════════════════════════════════════════════════
def show_banner(console, ctx):
    console.print()
    console.print(
        Panel(
            "AI translator in your terminal — powered by Duck.ai\n\n"
            "[dim]commands:[/dim]  help  langs  clear  status  theme  about  exit\n"
            "[dim]translate:[/dim]  [cyan]> example.txt ru[/cyan]   [cyan]> hello world ru[/cyan]",
            title="SonicTranslator",
            title_align="left",
            border_style=ctx.acc(),
            padding=(1, 2),
        )
    )
    console.print()


def cmd_help(console, ctx):
    table = Table(box=box.SIMPLE_HEAD, border_style=ctx.acc(), expand=False)
    table.add_column("Command", style="bold", width=18)
    table.add_column("What it does")
    rows = [
        ("help / ?", "this guide"),
        ("langs [filter]", f"all {len(LANG_CODES)} target languages; filter, e.g. 'langs port'"),
        ("tr <text> <lang>", "translate inline text"),
        ("<text> <lang>", "shorthand — anything else is a translation"),
        ("file <path> <lang>", "translate a file (shows a preview first)"),
        ("clip <lang>", "translate the clipboard"),
        ("hist", "recent translations of this session"),
        ("!<n>", "copy history entry n (see: hist)"),
        ("copy", "copy the last result again"),
        ("new", "start a fresh Duck.ai chat"),
        ("status", "browser session, counts, config paths"),
        ("theme", "toggle dark / light"),
        ("clear", "clean the screen (incl. scrollback), show the menu"),
        ("about", "version and project info"),
        ("exit / quit / q", "leave the menu (Ctrl+D works too)"),
    ]
    for cmd, desc in rows:
        table.add_row(cmd, desc)
    _print_paged(
        console,
        [
            table,
            Panel(
                "[bold]Examples[/bold]\n"
                "> hello world ru\n"
                "> notes.txt en\n"
                "> file readme.md ru\n"
                "> clip de\n"
                "> !1",
                box=box.SIMPLE,
                border_style="dim",
                padding=(0, 2),
            ),
        ],
    )


def cmd_langs(console, ctx, filter_str=""):
    # Unique codes form the table. Duplicated codes (ach, iu) shadow a second
    # variant that is only reachable by name — a filtered search surfaces
    # those too, annotated, so "langs luo" doesn't look like a dead end.
    items = [(code, name, False) for code, name in LANG_CODES.items()]
    if filter_str:
        f = filter_str.strip().lower()
        items = [
            (code, name, shadowed)
            for code, name, shadowed in items
            if f in code.lower() or f in name.lower()
        ]
        for code, name in LANGUAGES:
            if code in ("ach", "iu") and name.lower() != LANG_CODES[code].lower():
                if f in code.lower() or f in name.lower():
                    items.append((code, name, True))
    table = Table(
        title=f"Target language codes ({len(items)})",
        box=box.SIMPLE_HEAD,
        border_style=ctx.acc(),
        expand=False,
    )
    table.add_column("Code", style="bold", width=12, no_wrap=True)
    table.add_column("Language")
    for code, name, shadowed in items:
        label = f"{name}  [dim](by name)[/]" if shadowed else name
        table.add_row(code, label)
    out = [table]
    if filter_str:
        out.append(
            f"[dim]{len(items)} match(es) for '{filter_str}' (codes + names). "
            "Type 'langs' without a filter to see all 247 codes.[/]"
        )
    _print_paged(console, out)


def cmd_about(console, ctx):
    console.print(
        Panel(
            f"SonicTranslator v{VERSION}\n"
            "AI translator for the terminal. No API keys, no accounts — the text is\n"
            "translated through Duck.ai in a real (invisible) browser window.\n\n"
            f"Repository: {REPO_URL}\n"
            "Stack: Python + Playwright, Rich + prompt_toolkit UI.\n\n"
            "[dim]Note: this automates a third-party chat UI. It can break if Duck.ai\n"
            "changes its layout and is subject to their Terms of Service.[/]",
            title="About",
            title_align="left",
            border_style=ctx.acc(),
            padding=(1, 2),
        )
    )


def cmd_status(console, ctx):
    session = ctx.session
    console.print(
        Panel(
            f"Browser session:  {'running' if session.alive else 'not started'}\n"
            f"Translations:     {session.translation_count}\n"
            f"History entries:  {len(ctx.history)}  (stored in {HISTORY_FILE})\n"
            f"Browser profile:  {session.user_data_dir}\n"
            f"Theme:            {'dark' if ctx.dark else 'light'}",
            title="Status",
            title_align="left",
            border_style=ctx.acc(),
            padding=(1, 2),
        )
    )


def cmd_hist(console, ctx):
    if not ctx.history:
        console.print("[dim]No translations yet.[/]")
        return
    table = Table(box=box.SIMPLE_HEAD, border_style=ctx.acc())
    table.add_column("#", style="bold", width=3, justify="right")
    table.add_column("Lang", width=14)
    table.add_column("Text", width=40, overflow="ellipsis")
    table.add_column("Result", width=60, overflow="ellipsis")
    for i, entry in enumerate(ctx.history, start=1):
        table.add_row(
            str(i),
            entry.get("lang", ""),
            (entry.get("text") or "").replace("\n", " "),
            (entry.get("result") or "").replace("\n", " "),
        )
    _print_paged(console, [table, "[dim]Copy any entry with !<n>[/]"])


# ═══════════════════════════════════════════════════════════════════════════
#  SCREEN HELPERS — robust clear & paging (any terminal, incl. legacy cmd.exe)
# ═══════════════════════════════════════════════════════════════════════════
def clear_screen():
    """Fully clear the terminal: screen + scrollback, with an OS-level fallback.

    ``console.clear()`` only emits ANSI escapes, which terminals without VT
    support (legacy cmd.exe) silently ignore — cls/clear cannot fail there.
    The extra ``\x1b[3J`` wipes the scrollback, so old output can't reappear
    when scrolling up after ``> clear``.
    """
    try:
        if sys.stdout.isatty():
            sys.stdout.write("\x1b[2J\x1b[3J\x1b[H")
            sys.stdout.flush()
            if os.name == "nt":
                os.system("cls")
            else:
                os.system("clear")
    except Exception:
        pass


def _write_safe(text, ensure_newline=False):
    """Write text to stdout without ever crashing on encoding.

    Direct ``sys.stdout.write`` raises ``UnicodeEncodeError`` on non-UTF-8
    pipes (e.g. cp1251) for box-drawing characters; Rich's own writes replace
    such characters instead. When the strict write fails, fall back to the
    binary stream with ``errors='replace'``.
    """
    if ensure_newline and not text.endswith("\n"):
        text += "\n"
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        sys.stdout.buffer.write(text.encode(encoding, errors="replace"))
    sys.stdout.flush()


_ansi_cache = {}  # (color_system, width, soft_wrap) -> Console prototype


def _render_ansi(console, renderables):
    """Render Rich renderables to a single ANSI string.

    color_system=None (pipes, tests) yields plain text; a real terminal
    yields ANSI colors. The width matches the live console so line wrapping
    is identical to a normal ``console.print()``.
    """
    from io import StringIO

    soft_wrap = getattr(console, "soft_wrap", False)
    key = (console.color_system, console.width, soft_wrap)
    if key not in _ansi_cache:
        buf = StringIO()
        _ansi_cache[key] = Console(
            file=buf,
            force_terminal=True,
            color_system=console.color_system,
            width=console.width,
            soft_wrap=soft_wrap,
        )
    tmp = _ansi_cache[key]
    tmp.file = StringIO()  # reset output buffer
    for renderable in renderables:
        tmp.print(renderable)
    return tmp.file.getvalue()


def _print_paged(console, renderables, pad=4):
    """Print renderables, paging anything taller than the terminal.

    In a real terminal long listings (``langs``, ``hist``) are shown page by
    page — Enter = next page, q = quit — so nothing is ever cut off and no
    terminal scrollback is needed. When stdin or stdout is not attached to a
    terminal the full output is printed at once (pipes, tests).
    """
    if not renderables:
        return
    try:
        height = max(8, shutil.get_terminal_size().lines - pad)
    except Exception:
        height = 24

    ansi = _render_ansi(console, renderables)
    lines = ansi.split("\n")

    # Pause only when the user can actually answer: both stdin and stdout must
    # be attached to a terminal. With piped stdin the next piped command would
    # be swallowed by input() as a "[more]" answer; with piped stdout the full
    # output is printed at once anyway.
    interactive = sys.stdin.isatty() and sys.stdout.isatty()

    if len(lines) <= height or not interactive:
        _write_safe(ansi, ensure_newline=True)
        return

    total = (len(lines) + height - 1) // height
    page = 1
    for start in range(0, len(lines), height):
        _write_safe("\n".join(lines[start:start + height]) + "\n")
        if start + height < len(lines):
            try:
                key = input(f"[more {page}/{total} - Enter, q to quit] ").strip().lower()
            except (EOFError, OSError, KeyboardInterrupt):
                break
            if key in ("q", "quit", "x", "exit"):
                break
        page += 1


# ═══════════════════════════════════════════════════════════════════════════
#  TRANSLATION ACTIONS
# ═══════════════════════════════════════════════════════════════════════════
def _run_translate(ctx, text, lang):
    try:
        return ctx.session.translate(text, lang)
    except Exception as e:
        ctx.console.print(f"[red]Translation failed: {e}[/]")
        return None


def do_translate(ctx, text, lang_arg):
    console = ctx.console
    try:
        lang = resolve_target_lang(lang_arg)
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        return
    if not text:
        console.print("[yellow]Nothing to translate.[/]")
        return

    if sys.stdout.isatty():
        animation = TranslationAnimation(console, lang)
        animation.start()
        try:
            result = _run_translate(ctx, text, lang)
        finally:
            animation.stop()
    else:
        result = _run_translate(ctx, text, lang)
    if result is None:
        return

    ctx.last_result = result
    try:
        pyperclip.copy(result)
        copied = True
    except Exception:
        copied = False

    ctx.history.append(
        {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "text": text[:200],
            "lang": lang,
            "result": result,
        }
    )
    save_history(ctx.history)

    console.print()
    console.print(
        Panel(result, title=f"→ {lang}", title_align="left", border_style=ctx.acc(), padding=(1, 2))
    )
    console.print("[dim]✓ copied to clipboard[/]" if copied else "[yellow]clipboard copy failed[/]")
    console.print()


def _resolve_file(path):
    """Resolve a file path: try CWD first, then PROJECT_ROOT."""
    if os.path.isfile(path):
        return path
    candidate = os.path.join(PROJECT_ROOT, path)
    if os.path.isfile(candidate):
        return candidate
    return None


def do_file(ctx, path, lang_arg):
    console = ctx.console
    resolved = _resolve_file(path)
    if resolved is None:
        console.print(f"[red]No such file: {path}[/]")
        return
    try:
        text = read_text_file(resolved)
    except OSError as e:
        console.print(f"[red]Cannot read '{path}': {e}[/]")
        return
    lines = text.splitlines()
    preview = "\n".join(line[:80] for line in lines[:8])
    if len(lines) > 8:
        preview += f"\n[dim]… {len(lines) - 8} more lines[/]"
    console.print(
        Panel(preview, title=f"File: {path}", title_align="left", border_style="dim", padding=(0, 2))
    )
    do_translate(ctx, text, lang_arg)


def do_clip(ctx, lang_arg):
    console = ctx.console
    try:
        text = pyperclip.paste().strip()
    except Exception as e:
        console.print(f"[red]Cannot read the clipboard: {e}[/]")
        return
    if not text:
        console.print("[yellow]Clipboard is empty.[/]")
        return
    console.print("[dim]Translating clipboard content…[/]")
    do_translate(ctx, text, lang_arg)


def copy_index(ctx, n_str):
    console = ctx.console
    try:
        n = int(n_str)
    except ValueError:
        console.print("[yellow]Usage: !<n> — copy history entry n (see: hist)[/]")
        return
    if not 1 <= n <= len(ctx.history):
        console.print(f"[yellow]No history entry {n}.[/]")
        return
    entry = ctx.history[n - 1]
    ctx.last_result = entry["result"]
    try:
        pyperclip.copy(entry["result"])
        console.print(f"[dim]✓ copied:[/] {(entry['result'] or '').replace(chr(10), ' ')[:80]}")
    except Exception:
        console.print("[red]Clipboard copy failed.[/]")


def cmd_copy(ctx):
    console = ctx.console
    if ctx.last_result is None:
        console.print("[yellow]Nothing to copy yet — translate something first.[/]")
        return
    try:
        pyperclip.copy(ctx.last_result)
        console.print("[dim]✓ copied the last result again[/]")
    except Exception:
        console.print("[red]Clipboard copy failed.[/]")


def cmd_theme(ctx):
    ctx.dark = not ctx.dark
    ctx.console.print(f"[dim]Theme:[/] {'dark' if ctx.dark else 'light'}")


def cmd_new(ctx):
    ctx.session.reset_chat()
    ctx.console.print("[dim]Duck.ai chat reset (new conversation).[/]")


# ═══════════════════════════════════════════════════════════════════════════
#  COMMAND DISPATCH
# ═══════════════════════════════════════════════════════════════════════════
def _tokenize(line):
    """Split a command line into tokens.

    Honors double quotes ("my file.txt" stays one token) but treats
    backslashes as plain characters, so Windows paths survive intact.
    Raises ValueError on an unbalanced quote.
    """
    toks = []
    cur = []
    in_quotes = False
    for ch in line:
        if ch == '"':
            in_quotes = not in_quotes
        elif ch.isspace() and not in_quotes:
            if cur:
                toks.append("".join(cur))
                cur = []
        else:
            cur.append(ch)
    if in_quotes:
        raise ValueError("Unbalanced quotes in the command.")
    if cur:
        toks.append("".join(cur))
    return toks


def dispatch(ctx, raw):
    """Run one command line. Returns False when the menu should exit."""
    console = ctx.console
    raw = raw.strip()
    if not raw:
        return True

    if raw.startswith("!"):
        copy_index(ctx, raw[1:])
        return True

    try:
        toks = _tokenize(raw)
    except ValueError as e:
        console.print(f"[yellow]{e}[/]")
        return True
    if not toks:
        return True

    cmd = toks[0].lower()
    rest = toks[1:]

    if cmd in ("help", "?", "h"):
        cmd_help(console, ctx)
    elif cmd == "langs":
        cmd_langs(console, ctx, " ".join(rest))
    elif cmd in ("exit", "quit", "q", "bye"):
        return False
    elif cmd == "clear":
        clear_screen()
        show_banner(console, ctx)
    elif cmd == "theme":
        cmd_theme(ctx)
    elif cmd == "about":
        cmd_about(console, ctx)
    elif cmd == "status":
        cmd_status(console, ctx)
    elif cmd == "hist":
        cmd_hist(console, ctx)
    elif cmd == "copy":
        cmd_copy(ctx)
    elif cmd == "new":
        cmd_new(ctx)
    elif cmd == "clip":
        if not rest:
            console.print("[yellow]Usage: clip <lang>[/]")
        else:
            do_clip(ctx, rest[-1])
    elif cmd == "file":
        if len(rest) < 2:
            console.print("[yellow]Usage: file <path> <lang>[/]")
        else:
            do_file(ctx, " ".join(rest[:-1]), rest[-1])
    elif cmd == "tr":
        if len(rest) < 2:
            console.print("[yellow]Usage: tr <text> <lang>[/]")
        else:
            do_translate(ctx, " ".join(rest[:-1]), rest[-1])
    else:
        # Default: anything that is not a command is a translation request.
        if len(toks) == 1:
            console.print(
                f"[yellow]Unknown command '{cmd}'. Type 'help' for the list of commands.[/]"
            )
        elif len(toks) == 2 and _resolve_file(toks[0]) is not None:
            do_file(ctx, toks[0], toks[1])
        else:
            do_translate(ctx, " ".join(toks[:-1]), toks[-1])
    return True


# ═══════════════════════════════════════════════════════════════════════════
#  LOOPS
# ═══════════════════════════════════════════════════════════════════════════
def _run_simple(ctx):
    """Plain input() loop — used when stdin is not a terminal."""
    console = ctx.console
    while True:
        try:
            raw = input("> ")
        except (EOFError, OSError):
            break
        except KeyboardInterrupt:
            console.print()
            break
        if not raw.strip():
            continue
        try:
            if not dispatch(ctx, raw):
                break
        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted.[/]")
            continue


def _run_fancy(ctx):
    """Full-featured loop with autocomplete, history and a styled prompt."""
    console = ctx.console
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import FuzzyCompleter, WordCompleter
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.styles import Style
    except ImportError:
        console.print(
            "[yellow]prompt_toolkit not installed — falling back to plain input. "
            "Install with: pip install prompt_toolkit[/]"
        )
        return _run_simple(ctx)

    words = COMMANDS + sorted(LANG_CODES.keys()) + sorted({name for _, name in LANGUAGES})
    completer = FuzzyCompleter(WordCompleter(words, ignore_case=True))
    history_file = os.path.join(get_config_dir(), "repl_history")
    try:
        os.makedirs(os.path.dirname(history_file), exist_ok=True)
    except Exception:
        pass

    session = PromptSession(
        completer=completer,
        history=FileHistory(history_file),
        style=Style.from_dict({"prompt": "bold cyan"}),
        complete_while_typing=True,
    )
    while True:
        try:
            raw = session.prompt("> ")
        except (KeyboardInterrupt, EOFError):
            console.print()
            break
        if not raw.strip():
            continue
        try:
            if not dispatch(ctx, raw):
                break
        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted.[/]")
            continue


def run_repl():
    """Entry point used by st.py when no arguments are given."""
    console = Console()
    ctx = ReplContext(console)
    show_banner(console, ctx)
    try:
        if sys.stdin.isatty():
            _run_fancy(ctx)
        else:
            _run_simple(ctx)
    finally:
        ctx.session.close()


if __name__ == "__main__":
    run_repl()
