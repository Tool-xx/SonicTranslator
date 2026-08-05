#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SonicTranslator — shared core.

Everything both entry points (CLI ``st.py`` and GUI ``stgui.py``) need to
keep in sync: language tables, prompt building, response cleaning, browser
launch configuration and the anti-detection init script. If Duck.ai changes
its layout, this is the single place to fix it.
"""

import os
import re

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

NAME_TO_CODE = {name: code for code, name in LANG_CODES.items()}
LANG_NAMES_SORTED = sorted(LANG_CODES.values())

# Lines Duck.ai renders around the answer (model label, UI hints, banners).
# These are dropped from the extracted response text.
_ARTIFACT_PATTERNS = [
    re.compile(r"^GPT-\d+(\.\d+)?o?\s*nano\s*$", re.IGNORECASE),  # covers GPT-4 nano, GPT-4o nano, GPT-4.1 nano
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
#  TIMING KNOBS — tune every wait in one place
# ═══════════════════════════════════════════════════════════════════════════
DUCK_AI_URL = "https://duck.ai"
GOTO_TIMEOUT_MS = 45000
INITIAL_SETTLE_MS = 3500
COMPOSER_WAIT_MS = 15000
SUBMIT_WAIT_MS = 5000
RESPONSE_TIMEOUT_MS = 30000
STABILITY_POLL_MS = 500
STABILITY_TICKS_REQUIRED = 2
MAX_STABILITY_POLLS = 90


# ═══════════════════════════════════════════════════════════════════════════
#  LANGUAGES / PROMPT / CLEANING
# ═══════════════════════════════════════════════════════════════════════════
def resolve_target_lang(code_or_name: str) -> str:
    """Accept a language code or a full language name, return the full name.

    Raises ValueError for anything unknown.
    """
    key = code_or_name.strip().lower()
    if key in LANG_CODES:
        return LANG_CODES[key]
    for name in LANG_CODES.values():
        if name.lower() == key:
            return name
    raise ValueError(
        f"Unknown target language '{code_or_name}'. "
        f"Supported codes: {', '.join(sorted(LANG_CODES.keys()))}"
    )


def build_prompt(text: str, target_lang: str) -> str:
    """The translation prompt. Richer than a plain 'translate X' so the
    model keeps idioms, tone, slang and technical terms intact."""
    return (
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


def clean_translation(raw: str, original: str) -> str:
    """Strip Duck.ai UI artifacts and any echo of the source text from the
    model's reply."""
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

    # The model sometimes echoes the source text before answering; cut
    # everything from the first case-insensitive occurrence of the source.
    # A regex match on the original string (not a lower-cased copy) keeps
    # the cut position exact even for length-changing case folds.
    orig = original.strip()
    if orig:
        match = re.search(re.escape(orig), text, re.IGNORECASE)
        if match:
            after = text[match.end():].strip()
            if after:
                text = after

    return text


# ═══════════════════════════════════════════════════════════════════════════
#  BROWSER CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════
def get_user_data_dir() -> str:
    """Persistent profile shared by CLI and GUI (keeps the Duck.ai session)."""
    return os.path.join(os.path.expanduser("~"), ".sonic_translator", "browser_data")


def get_browser_args() -> list:
    """Chromium launch flags.

    Deliberately minimal: no flags that weaken the page's security
    (--disable-web-security, site-isolation shutdown were removed) and no
    hardcoded user agent — Playwright reports its real bundled Chromium
    version, which is what anti-bot heuristics actually verify.
    """
    return [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1280,800",
        "--window-position=-10000,-10000",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-infobars",
        "--disable-extensions",
        "--no-first-run",
        "--no-default-browser-check",
        "--password-store=basic",
        "--use-mock-keychain",
        "--lang=en-US",
    ]


def get_browser_kwargs() -> dict:
    """Shared ``launch_persistent_context`` kwargs (mirrors get_browser_args).

    headless=False + an off-screen window (-10000,-10000): a real window is
    far harder for Duck.ai's anti-bot layer to detect than headless mode.
    """
    return {
        "headless": False,
        "args": get_browser_args(),
        "viewport": {"width": 1280, "height": 800},
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "java_script_enabled": True,
        "bypass_csp": True,
    }


def get_stealth_init_script() -> str:
    """Injected before any page script runs so the page sees an ordinary
    desktop Chrome instead of an automation target."""
    return """
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
"""


# ═══════════════════════════════════════════════════════════════════════════
#  PAGE HELPERS
# ═══════════════════════════════════════════════════════════════════════════
def dump_debug_info(page, base_dir=None) -> str:
    """Save a screenshot and the page HTML next to the script (or into
    base_dir) so a failure cause can be inspected. Returns the directory."""
    if base_dir is None:
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
    return base_dir


def dismiss_banners(page, settle_ms=800, probe_timeout_ms=1500):
    """Click consent/cookie banners if they appear (EN and FR variants)."""
    for btn_text in ["Continuer", "Continue", "Accept", "Agree", "OK", "Got it", "I Agree"]:
        try:
            btn = page.locator(f'button:has-text("{btn_text}")').first
            if btn.is_visible(timeout=probe_timeout_ms):
                btn.click()
                page.wait_for_timeout(settle_ms)
        except Exception:
            continue


def clear_chat(page) -> bool:
    """Reset the current conversation (the persistent profile keeps history).
    Returns True if a reset button was found and clicked."""
    for sel in ['button:has-text("New Chat")', 'button[aria-label="New Chat"]',
                'button:has-text("Clear conversation")']:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=1500):
                btn.click()
                page.wait_for_timeout(1000)
                return True
        except Exception:
            continue
    return False


def fill_and_submit(page, prompt: str):
    """Type the prompt into the composer and trigger submission.

    Waits for the composer to actually exist (slow networks, captchas) and
    falls back to Enter when the submit button is unavailable or disabled.
    Raises RuntimeError with a diagnostic hint if the composer is missing.
    """
    textarea = page.locator("textarea").first
    try:
        textarea.wait_for(state="visible", timeout=COMPOSER_WAIT_MS)
    except Exception:
        dump_debug_info(page)
        raise RuntimeError(
            "Could not find the Duck.ai input box. The page layout may have "
            "changed or a captcha/block appeared. Screenshot and HTML saved "
            "(debug_screenshot.png, debug_page.html) for diagnosis."
        ) from None

    try:
        textarea.click()
        textarea.fill(prompt)
        page.wait_for_timeout(400)
    except Exception:
        dump_debug_info(page)
        raise RuntimeError(
            "Could not type into the Duck.ai input box. The page layout may "
            "have changed or a captcha/block appeared. Screenshot and HTML "
            "saved (debug_screenshot.png, debug_page.html) for diagnosis."
        ) from None

    # Some chat UIs only enable the submit button after a real input event;
    # .fill() usually covers this, but we defend against it by falling back
    # to pressing Enter if the button never becomes available or stays disabled.
    submit = page.locator('button[type="submit"]').first
    submitted = False
    try:
        submit.wait_for(state="visible", timeout=SUBMIT_WAIT_MS)
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


def wait_for_response(page, prompt: str) -> str:
    """Wait until Duck.ai's answer stops changing, then return its text.

    Accepts short answers too (any non-empty text that stays stable), so
    one-word translations like 'Да' no longer time out. Raises RuntimeError
    on timeout — callers should dump debug info before surfacing it.
    """
    try:
        page.wait_for_selector('div[data-activeresponse="true"]', timeout=RESPONSE_TIMEOUT_MS)
    except Exception:
        raise RuntimeError(
            "Duck.ai did not respond within 30s — likely a captcha, block, or "
            "layout change. Screenshot and HTML saved (debug_screenshot.png, "
            "debug_page.html) for diagnosis."
        ) from None

    last_text = ""
    stable_ticks = 0
    response_text = ""

    for _ in range(MAX_STABILITY_POLLS):
        page.wait_for_timeout(STABILITY_POLL_MS)
        try:
            count = page.locator('div[data-activeresponse="true"]').count()
            if count == 0:
                continue
            container = page.locator('div[data-activeresponse="true"]').nth(count - 1)
            current = container.inner_text().strip()
            if not current or current == prompt:
                continue
            if current == last_text:
                stable_ticks += 1
                if stable_ticks >= STABILITY_TICKS_REQUIRED:
                    response_text = current
                    break
            else:
                stable_ticks = 0
            last_text = current
        except Exception:
            continue

    if not response_text:
        raise RuntimeError(
            "Duck.ai did not produce a stable response in time. Screenshot and "
            "HTML saved (debug_screenshot.png, debug_page.html) for diagnosis."
        )
    return response_text
