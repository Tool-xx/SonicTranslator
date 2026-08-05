#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SonicTranslator CLI - AI-powered translator for integration into other software
Powered by Duck.ai via Playwright

USAGE:
    python st.py <text to translate> <target language code>
    python st.py -<path_to_file.txt> <target language code>

Run "python st.py" with no arguments (or -h / --help) to see the full
usage guide and the list of supported language codes.

The source language is detected automatically - you only need to specify
the target language code. On success the translation is copied straight
to the clipboard and exactly one line is printed to stdout:

    Everything has been translated and copied to the clipboard

On failure, an error message is printed to stderr and the process exits
with a non-zero code (integrate by checking the return code, not stdout).
"""

import sys
import os
import time
import threading
import itertools

try:
    import pyperclip
except ImportError:
    print(
        "Error: missing dependency 'pyperclip'. Install with: pip install pyperclip",
        file=sys.stderr,
    )
    sys.exit(1)

from playwright.sync_api import sync_playwright

from st_core import (
    LANG_CODES,
    build_prompt,
    clean_translation,
    clear_chat,
    dismiss_banners,
    dump_debug_info,
    fill_and_submit,
    get_browser_kwargs,
    get_stealth_init_script,
    get_user_data_dir,
    resolve_target_lang,
    wait_for_response,
    DUCK_AI_URL,
    GOTO_TIMEOUT_MS,
    INITIAL_SETTLE_MS,
)

APP_NAME = "SonicTranslator"


# ═══════════════════════════════════════════════════════════════════════════
#  HELP / USAGE BANNER
# ═══════════════════════════════════════════════════════════════════════════
def print_help():
    codes = sorted(LANG_CODES.items())
    lines = []
    for i in range(0, len(codes), 3):
        row = codes[i:i + 3]
        formatted = "    ".join(f"{code} - {name}".ljust(20) for code, name in row)
        lines.append("    " + formatted.rstrip())
    lang_table = "\n".join(lines)

    banner = f"""
{APP_NAME} - AI-powered CLI translator (powered by Duck.ai)
{"=" * 60}

USAGE:
    python st.py <text to translate> <target language code>
    python st.py -<path_to_file.txt> <target language code>

EXAMPLES:
    python st.py Hello, how are you? ru
    python st.py "Bonjour tout le monde" en
    python st.py -notes.txt en

NOTES:
    - The source language is detected automatically.
      You only need to specify the TARGET language code.
    - The result is copied straight to your clipboard.
    - Nothing is printed except a short confirmation line on success.
    - To translate a file, prefix its path with "-":
          python st.py -text.txt ru
      (the file must exist and be readable as plain text)

AVAILABLE TARGET LANGUAGE CODES:
{lang_table}

Run "python st.py -h" or "python st.py --help" to see this guide again.
"""
    print(banner)


# ═══════════════════════════════════════════════════════════════════════════
#  SPINNER ANIMATION (runs while a background thread does the translation)
# ═══════════════════════════════════════════════════════════════════════════
def run_with_spinner(func, *args, **kwargs):
    result = {}
    error = {}
    done_event = threading.Event()

    def worker():
        try:
            result["value"] = func(*args, **kwargs)
        except Exception as e:
            error["value"] = e
        finally:
            done_event.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    frames = ["|", "/", "-", "\\"]
    spinner = itertools.cycle(frames)
    label = "Translating "

    sys.stdout.write(label)
    sys.stdout.flush()

    while not done_event.is_set():
        frame = next(spinner)
        sys.stdout.write(frame)
        sys.stdout.flush()
        time.sleep(0.15)
        sys.stdout.write("\b")

    # clear the spinner character and move to a clean line
    sys.stdout.write(" \n")
    sys.stdout.flush()

    thread.join()

    if "value" in error:
        raise error["value"]
    return result["value"]


# ═══════════════════════════════════════════════════════════════════════════
#  TRANSLATION ENGINE (single-shot)
# ═══════════════════════════════════════════════════════════════════════════
def translate(text: str, target_lang: str) -> str:
    prompt = build_prompt(text, target_lang)

    user_data_dir = get_user_data_dir()
    os.makedirs(user_data_dir, exist_ok=True)

    with sync_playwright() as p:
        # headless=True is detected far more easily by Duck.ai's anti-bot
        # layer than a real window, so we launch a real window but move it
        # off-screen (-10000,-10000) - invisible to the user, ordinary to
        # the site. The browser config lives in st_core.
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            **get_browser_kwargs(),
        )

        try:
            page = browser.new_page()
            page.add_init_script(get_stealth_init_script())

            page.goto(DUCK_AI_URL, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
            page.wait_for_timeout(INITIAL_SETTLE_MS)
            dismiss_banners(page)
            # The persistent profile keeps conversation history between runs;
            # always start from a clean slate so old replies can't interfere.
            clear_chat(page)

            fill_and_submit(page, prompt)

            try:
                response_text = wait_for_response(page, prompt)
            except RuntimeError:
                dump_debug_info(page)
                raise

            clean = clean_translation(response_text, text)
            if not clean:
                raise RuntimeError("Could not extract clean text from the response.")
            return clean
        finally:
            browser.close()


# ═══════════════════════════════════════════════════════════════════════════
#  ENTRYPOINT
# ═══════════════════════════════════════════════════════════════════════════
def main():
    argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help"):
        print_help()
        sys.exit(0)

    if len(argv) < 2:
        print(
            f"Error: not enough arguments.\nRun \"python st.py --help\" for {APP_NAME} usage.",
            file=sys.stderr,
        )
        sys.exit(1)

    *text_parts, lang_arg = argv

    # File mode: python st.py -text.txt ru
    # Only treated as a file if a single dash-prefixed token is given AND a
    # matching file actually exists - this avoids misinterpreting literal
    # text that happens to start with "-" (e.g. "-5 degrees outside").
    text = None
    if len(text_parts) == 1 and text_parts[0].startswith("-") and len(text_parts[0]) > 1:
        candidate_path = text_parts[0][1:]
        if os.path.isfile(candidate_path):
            try:
                with open(candidate_path, "r", encoding="utf-8") as f:
                    text = f.read().strip()
            except UnicodeDecodeError:
                # fallback for non-UTF-8 files (e.g. legacy Windows-1251 text)
                with open(candidate_path, "r", encoding="cp1251", errors="replace") as f:
                    text = f.read().strip()

    if text is None:
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
        result = run_with_spinner(translate, text, target_lang)
    except Exception as e:
        print(f"Error: translation failed - {e}", file=sys.stderr)
        sys.exit(1)

    pyperclip.copy(result)
    print("Everything has been translated and copied to the clipboard")


if __name__ == "__main__":
    main()
