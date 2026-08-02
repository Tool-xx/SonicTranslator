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
import re
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

APP_NAME = "SonicTranslator"

# ═══════════════════════════════════════════════════════════════════════════
#  LANGUAGE CODES
# ═══════════════════════════════════════════════════════════════════════════
LANG_CODES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "ru": "Russian",
    "pt": "Portuguese", "it": "Italian", "ar": "Arabic", "hi": "Hindi",
    "tr": "Turkish", "nl": "Dutch", "pl": "Polish", "sv": "Swedish",
    "vi": "Vietnamese", "th": "Thai", "id": "Indonesian", "uk": "Ukrainian",
}

_ARTIFACT_PATTERNS = [
    re.compile(r"^GPT-\d+(\.\d+)?\s*nano\s*$", re.IGNORECASE),
    re.compile(r"^\s*Private\s*$", re.IGNORECASE),
    re.compile(r"^\s*\u00b7\s*$"),
    re.compile(r"^\s*Send\s*$", re.IGNORECASE),
    re.compile(r"^\s*Switch model\s*$", re.IGNORECASE),
    re.compile(r"^\s*Search the web\s*$", re.IGNORECASE),
    re.compile(r"^\s*Positive feedback\s*$", re.IGNORECASE),
    re.compile(r"^\s*Negative feedback\s*$", re.IGNORECASE),
    re.compile(r"^\s*Ask anything privately\s*$", re.IGNORECASE),
    re.compile(r"^\s*Duck\.ai is temporarily unavailable\s*$", re.IGNORECASE),
    re.compile(r"^\s*Nous ne vous pistons pas.*", re.IGNORECASE),
    re.compile(r"^\s*Politique de confidentialite.*", re.IGNORECASE),
    re.compile(r"^\s*Continuer\s*$", re.IGNORECASE),
    re.compile(r"^\s*Continue\s*$", re.IGNORECASE),
    re.compile(r"^\s*New Chat\s*$", re.IGNORECASE),
    re.compile(r"^\s*Clear conversation\s*$", re.IGNORECASE),
]


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
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════
def resolve_target_lang(code_or_name: str) -> str:
    key = code_or_name.strip().lower()
    if key in LANG_CODES:
        return LANG_CODES[key]
    # fallback: the user may have passed the full language name instead of a code
    for name in LANG_CODES.values():
        if name.lower() == key:
            return name
    raise ValueError(
        f"Unknown target language '{code_or_name}'. "
        f"Supported codes: {', '.join(sorted(LANG_CODES.keys()))}"
    )


def clean_translation(raw: str, original: str) -> str:
    if not raw:
        return ""

    cleaned = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(p.search(stripped) for p in _ARTIFACT_PATTERNS):
            continue
        if stripped.lower() == original.strip().lower():
            continue
        cleaned.append(stripped)

    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    text = text.strip()

    orig_stripped = original.strip().lower()
    if orig_stripped and orig_stripped in text.lower():
        idx = text.lower().find(orig_stripped)
        after = text[idx + len(original.strip()):].strip()
        if after:
            text = after

    return text


def dump_debug_info(page):
    """Saves a screenshot and the current page HTML next to the script,
    so the failure cause (captcha, banner, layout change) can be inspected."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        page.screenshot(path=os.path.join(base_dir, "debug_screenshot.png"), full_page=True)
    except Exception:
        pass
    try:
        with open(os.path.join(base_dir, "debug_page.html"), "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception:
        pass


def dismiss_banners(page):
    for btn_text in ["Continuer", "Continue", "Accept", "Agree", "OK", "Got it", "I Agree"]:
        try:
            btn = page.locator(f'button:has-text("{btn_text}")').first
            if btn.is_visible(timeout=2000):
                btn.click()
                page.wait_for_timeout(1000)
        except Exception:
            continue


# ═══════════════════════════════════════════════════════════════════════════
#  TRANSLATION ENGINE (single-shot)
# ═══════════════════════════════════════════════════════════════════════════
def translate(text: str, target_lang: str) -> str:
    prompt = (
        f"You are an expert translator with 20 years of experience in software localization. "
        f"Your native language is {target_lang}. You specialize in preserving nuance, "
        f"idioms, sarcasm, technical terminology, and cultural context.\n\n"
        f"TASK: Detect the source language of the text below automatically, then translate "
        f"it into {target_lang}.\n\n"
        f"═══════════════════════════════════════════════════════════════\n"
        f"MANDATORY RULES — follow strictly:\n"
        f"═══════════════════════════════════════════════════════════════\n\n"
        f"1. IDIOMS & METAPHORS: Never translate idioms word-for-word. "
        f"Use an equivalent {target_lang} idiom that carries the SAME meaning and tone. "
        f"If no equivalent exists, translate the MEANING naturally and keep the original "
        f"idiom in parentheses, e.g. (lit. 'barking up the wrong tree').\n\n"
        f"2. TECHNICAL TERMS: Use ONLY standard, industry-accepted terminology in "
        f"{target_lang}. Do not invent new terms, and do not translate acronyms like "
        f"CI/CD, API, or product/platform names.\n\n"
        f"3. PROPER NOUNS: Never translate brand names, product names, platforms, "
        f"or programming languages (e.g. Kubernetes, AWS, Slack, PHP).\n\n"
        f"4. TONE & REGISTER: Preserve the original tone exactly. "
        f"If the source is sarcastic, informal, or vulgar — the translation must be "
        f"equally sarcastic, informal, or vulgar. Do NOT sanitize, do NOT make it "
        f"corporate-friendly, do NOT add politeness that wasn't there.\n\n"
        f"5. SLANG & COLLOQUIALISMS: Translate slang into natural {target_lang} slang "
        f"of the same intensity — not a weaker, watered-down equivalent.\n\n"
        f"6. OUTPUT FORMAT: Reply with ONLY the translated text. "
        f"NO headers, NO markdown, NO bullet points, NO explanations, NO notes about "
        f"the detected language, NO repetition of the source text, NO 'Here is the "
        f"translation:' prefixes, NO model names, NO 'Private' labels.\n\n"
        f"7. ACCURACY CHECK: Before outputting, verify that:\n"
        f"   - No source-language words remain untranslated (except proper nouns from Rule 3).\n"
        f"   - No word-for-word idiom translations exist.\n"
        f"   - No technical terms were invented or butchered.\n"
        f"   - The tone matches the original.\n\n"
        f"═══════════════════════════════════════════════════════════════\n"
        f"FEW-SHOT EXAMPLES (learn the style from these, target language may differ):\n"
        f"═══════════════════════════════════════════════════════════════\n\n"
        f"Example 1 — Idiom:\n"
        f"EN: We are not just barking up the wrong tree here.\n"
        f"RU: Мы тут не просто лаем не на то дерево — мы действуем совсем не по адресу.\n\n"
        f"Example 2 — Technical + Sarcasm:\n"
        f"EN: The logs are a dumpster fire: cascading failures and memory leaks the size of Texas.\n"
        f"RU: Логи — это полный пожар в мусорном баке: каскадные отказы, утечки памяти размером с Техас.\n\n"
        f"Example 3 — Slang + Metaphor:\n"
        f"EN: It's like asking a one-legged man to win an ass-kicking contest.\n"
        f"RU: Это как посадить одноногого на турнир по пинанию задниц.\n\n"
        f"Example 4 — Cultural reference:\n"
        f"EN: Refactoring it is a Sisyphean task.\n"
        f"RU: Рефакторить это — сизифов труд.\n\n"
        f"Example 5 — Tone preservation:\n"
        f"EN: And don't even get me started on the documentation.\n"
        f"RU: И даже не начинайте мне про документацию.\n\n"
        f"═══════════════════════════════════════════════════════════════\n"
        f"TEXT TO TRANSLATE:\n"
        f"═══════════════════════════════════════════════════════════════\n\n"
        f"{text}"
    )

    user_data_dir = os.path.join(os.path.expanduser("~"), ".sonic_translator", "browser_data")
    os.makedirs(user_data_dir, exist_ok=True)

    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1280,800",
        "--window-position=-10000,-10000",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-site-isolation-trials",
        "--disable-web-security",
        "--disable-infobars",
        "--disable-extensions",
        "--disable-plugins",
        "--no-first-run",
        "--no-default-browser-check",
        "--password-store=basic",
        "--use-mock-keychain",
        "--lang=en-US",
    ]

    with sync_playwright() as p:
        # IMPORTANT: headless=True is detected far more easily by Duck.ai's
        # anti-bot layer than a real window. So we launch a real window but
        # move it off-screen (-10000,-10000) - invisible to the user, but
        # the site sees an ordinary desktop Chrome.
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            args=args,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            timezone_id="America/New_York",
            java_script_enabled=True,
            bypass_csp=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
        )

        try:
            page = browser.new_page()
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [
                    {name: 'Chrome PDF Plugin'}, {name: 'Chrome PDF Viewer'},
                    {name: 'Native Client'}, {name: 'Widevine Content Decryption Module'}
                ]});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                window.chrome = { runtime: {} };
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications'
                        ? Promise.resolve({ state: Notification.permission })
                        : originalQuery(parameters)
                );
                Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});
                Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
                Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) return 'Intel Inc.';
                    if (parameter === 37446) return 'Intel Iris Xe Graphics';
                    return getParameter(parameter);
                };
            """)

            page.goto("https://duck.ai", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3500)
            dismiss_banners(page)

            textarea = page.locator("textarea").first
            textarea.click()
            textarea.fill(prompt)
            page.wait_for_timeout(400)

            # Some chat UIs only enable the submit button after a real input
            # event; .fill() usually covers this, but we defend against it
            # by falling back to pressing Enter if the button never becomes
            # available or stays disabled.
            submit = page.locator('button[type="submit"]').first
            submitted = False
            try:
                submit.wait_for(state="visible", timeout=5000)
                if submit.is_enabled():
                    submit.click()
                    submitted = True
            except Exception:
                submitted = False

            if not submitted:
                try:
                    textarea.press("Enter")
                except Exception:
                    pass

            try:
                page.wait_for_selector('div[data-activeresponse="true"]', timeout=30000)
            except Exception:
                dump_debug_info(page)
                raise RuntimeError(
                    "Duck.ai did not respond within 30s - likely a captcha, block, or "
                    "layout change. Screenshot and HTML saved next to the script "
                    "(debug_screenshot.png, debug_page.html) for diagnosis."
                )

            last_text = ""
            stable_ticks = 0
            response_text = ""

            for _ in range(90):
                page.wait_for_timeout(500)
                try:
                    count = page.locator('div[data-activeresponse="true"]').count()
                    if count == 0:
                        continue
                    container = page.locator('div[data-activeresponse="true"]').nth(count - 1)
                    current = container.inner_text().strip()

                    if current and current != prompt:
                        if current == last_text and len(current) > 3:
                            stable_ticks += 1
                            if stable_ticks >= 2:
                                response_text = current
                                break
                        else:
                            stable_ticks = 0
                        last_text = current
                except Exception:
                    continue

            if not response_text:
                dump_debug_info(page)
                raise RuntimeError(
                    "Duck.ai did not produce a stable response in time. Screenshot and "
                    "HTML saved next to the script for diagnosis."
                )

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
