#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SonicTranslator - AI-powered translator for integration into other software
Powered by Duck.ai via Playwright

TWO MODES:

1) INTERACTIVE MENU (no arguments):
       python st.py
   Opens a minimalist command menu in the terminal:
       > help             - every command, explained
       > example.txt ru   - translate a file to Russian
       > hello world ru   - translate inline text
       > clear            - clean screen, show the menu again
       > exit             - quit

2) ONE-SHOT (arguments) - unchanged integration contract:
       python st.py <text to translate> <target language code>
       python st.py example.txt ru          (file; no "-" needed)
       python st.py -example.txt ru         (legacy "-" prefix still works)

Run "python st.py -h" (or --help) to see the usage guide and language codes.

The source language is detected automatically - you only specify the target
language code. On success the translation is copied to the clipboard and
exactly one line is printed to stdout:

    Everything has been translated and copied to the clipboard

On failure, an error message is printed to stderr and the process exits
with a non-zero code (integrate by checking the return code, not stdout).
"""

import sys
import os
import textwrap

try:
    import pyperclip
except ImportError:
    print(
        "Error: missing dependency 'pyperclip'. Install with: pip install pyperclip",
        file=sys.stderr,
    )
    sys.exit(1)

from st_core import (
    LANG_CODES,
    TranslationSession,
    read_text_file,
    resolve_target_lang,
)

APP_NAME = "SonicTranslator"
SUCCESS_LINE = "Everything has been translated and copied to the clipboard"


# ═══════════════════════════════════════════════════════════════════════════
#  HELP / USAGE BANNER
# ═══════════════════════════════════════════════════════════════════════════
def print_help():
    all_codes = sorted(LANG_CODES)
    lang_table = textwrap.fill(" ".join(all_codes), width=96)

    banner = f"""
{APP_NAME} - AI-powered CLI translator (powered by Duck.ai)
{"=" * 60}

USAGE:
    python st.py                        interactive command menu
    python st.py <text> <lang>          translate inline text
    python st.py <file.txt> <lang>      translate a file (a "-" prefix is optional)
    python st.py -h / --help            this guide

EXAMPLES:
    python st.py "Hello, how are you?" ru
    python st.py "Bonjour tout le monde" en
    python st.py notes.txt en

INTERACTIVE MENU:
    Run without arguments to get the menu, then type commands at the "> " prompt:
        > help              every command, explained
        > langs             all {len(LANG_CODES)} target languages (try: langs port)
        > hello world ru    translate inline text
        > example.txt ru    translate a file (auto-detected)
        > exit              quit

NOTES:
    - The source language is detected automatically.
      You only need to specify the TARGET language code.
    - The result is copied straight to your clipboard.
    - In one-shot mode nothing is printed except a short confirmation line.
    - A file is used when it actually exists on disk; otherwise the
      argument is treated as literal text (no "-" prefix required).

AVAILABLE TARGET LANGUAGE CODES ({len(all_codes)}):
{lang_table}

Language names and regional variants (e.g. Portuguese (Brazil), Inuktut (Latin))
are accepted too. Full list with search: run "python st.py" and type "langs".

Run "python st.py -h" or "python st.py --help" to see this guide again.
"""
    print(banner)


# ═══════════════════════════════════════════════════════════════════════════
#  ONE-SHOT MODE
# ═══════════════════════════════════════════════════════════════════════════
def detect_file_arg(text_parts):
    """Return the path of an existing file if the args describe file mode.

    A single token that matches a file on disk (with or without the legacy
    "-" prefix) selects file mode; anything else is literal text.
    """
    if len(text_parts) != 1:
        return None
    token = text_parts[0]
    candidates = []
    if token.startswith("-") and len(token) > 1:
        candidates.append(token[1:])  # legacy "-notes.txt" style
    candidates.append(token)
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def translate_once(text, target_lang):
    """Single-shot translation: launch a browser, translate, close."""
    with TranslationSession() as session:
        if sys.stdout.isatty():
            try:
                from rich.console import Console

                with Console().status("[bold green]Translating…", spinner="dots"):
                    return session.translate(text, target_lang)
            except ImportError:
                pass
        return session.translate(text, target_lang)


# ═══════════════════════════════════════════════════════════════════════════
#  ENTRYPOINT
# ═══════════════════════════════════════════════════════════════════════════
def main():
    argv = sys.argv[1:]

    if not argv:
        # Interactive command menu
        from st_repl import run_repl

        try:
            run_repl()
        except KeyboardInterrupt:
            pass
        return

    if argv[0] in ("-h", "--help"):
        print_help()
        sys.exit(0)

    if len(argv) < 2:
        print(
            f"Error: not enough arguments.\nRun \"python st.py --help\" for {APP_NAME} usage.",
            file=sys.stderr,
        )
        sys.exit(1)

    *text_parts, lang_arg = argv

    path = detect_file_arg(text_parts)
    if path is not None:
        try:
            text = read_text_file(path)
        except OSError as e:
            print(f"Error: cannot read '{path}': {e}", file=sys.stderr)
            sys.exit(1)
    else:
        text = " ".join(text_parts).strip()

    if not text:
        print("Error: no text provided.", file=sys.stderr)
        sys.exit(1)

    try:
        target_lang = resolve_target_lang(lang_arg)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = translate_once(text, target_lang)
    except Exception as e:
        print(f"Error: translation failed - {e}", file=sys.stderr)
        sys.exit(1)

    pyperclip.copy(result)
    print(SUCCESS_LINE)


if __name__ == "__main__":
    main()
