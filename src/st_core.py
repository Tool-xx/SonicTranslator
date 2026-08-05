#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SonicTranslator — shared core.

Everything both entry points (CLI ``st.py`` and interactive menu
``st_repl.py``) need to keep in sync: language tables, prompt building,
response cleaning, browser launch configuration and the anti-detection
init script. If Duck.ai changes its layout, this is the single place to
fix it.
"""

import os
import re
import threading

from playwright.sync_api import sync_playwright, Error as PlaywrightError

# ═══════════════════════════════════════════════════════════════════════════
#  LANGUAGE CODES — full Duck.ai list
# ═══════════════════════════════════════════════════════════════════════════
# (code, name) pairs exactly as Duck.ai lists them. Two codes are duplicated
# in their source list on purpose — Duck.ai itself ships both variants:
#   ach -> Acholi and Luo,  iu -> Inuktut (Latin) and Inuktut (Syllabics)
# ``LANG_CODES`` below keeps the first occurrence of each duplicate so the
# code always resolves deterministically (ach = Acholi, iu = Inuktut (Latin));
# the other variants stay addressable by their full name (e.g. "> text Luo").
LANGUAGES = [
    ("ab", "Abkhaz"),
    ("ace", "Acehnese"),
    ("ach", "Acholi"),
    ("aa", "Afar"),
    ("af", "Afrikaans"),
    ("sq", "Albanian"),
    ("alz", "Alur"),
    ("am", "Amharic"),
    ("ar", "Arabic"),
    ("hy", "Armenian"),
    ("as", "Assamese"),
    ("av", "Avar"),
    ("awa", "Awadhi"),
    ("ay", "Aymara"),
    ("az", "Azerbaijani"),
    ("ban", "Balinese"),
    ("bal", "Balochi"),
    ("bm", "Bambara"),
    ("bci", "Baoulé"),
    ("ba", "Bashkir"),
    ("eu", "Basque"),
    ("btx", "Batak Karo"),
    ("bts", "Batak Simalungun"),
    ("bbc", "Batak Toba"),
    ("be", "Belarusian"),
    ("bem", "Bemba"),
    ("bn", "Bengali"),
    ("bew", "Betawi"),
    ("bho", "Bhojpuri"),
    ("bik", "Bikol"),
    ("bs", "Bosnian"),
    ("br", "Breton"),
    ("bg", "Bulgarian"),
    ("bxr", "Buryat"),
    ("yue", "Cantonese"),
    ("ca", "Catalan"),
    ("ceb", "Cebuano"),
    ("ch", "Chamorro"),
    ("ce", "Chechen"),
    ("ny", "Chichewa"),
    ("zh-CN", "Chinese (Simplified)"),
    ("zh-TW", "Chinese (Traditional)"),
    ("chk", "Chuukese"),
    ("cv", "Chuvash"),
    ("co", "Corsican"),
    ("crh-Cyrl", "Crimean Tatar (Cyrillic)"),
    ("crh-Latn", "Crimean Tatar (Latin)"),
    ("hr", "Croatian"),
    ("cs", "Czech"),
    ("da", "Danish"),
    ("prs", "Dari"),
    ("dv", "Dhivehi"),
    ("dik", "Dinka"),
    ("doi", "Dogri"),
    ("dam", "Dombe"),
    ("nl", "Dutch"),
    ("dyu", "Dyula"),
    ("dz", "Dzongkha"),
    ("en", "English"),
    ("eo", "Esperanto"),
    ("et", "Estonian"),
    ("ee", "Ewe"),
    ("fo", "Faroese"),
    ("fj", "Fijian"),
    ("tl", "Filipino"),
    ("fi", "Finnish"),
    ("fon", "Fon"),
    ("fr", "French"),
    ("fr-CA", "French (Canada)"),
    ("fy", "Frisian"),
    ("fur", "Friulian"),
    ("ff", "Fulani"),
    ("gaa", "Ga"),
    ("gl", "Galician"),
    ("ka", "Georgian"),
    ("de", "German"),
    ("el", "Greek"),
    ("gn", "Guarani"),
    ("gu", "Gujarati"),
    ("ht", "Haitian Creole"),
    ("cnh", "Hakha Chin"),
    ("ha", "Hausa"),
    ("haw", "Hawaiian"),
    ("he", "Hebrew"),
    ("hil", "Hiligaynon"),
    ("hi", "Hindi"),
    ("hmn", "Hmong"),
    ("hu", "Hungarian"),
    ("hns", "Hunsrik"),
    ("iba", "Iban"),
    ("is", "Icelandic"),
    ("ig", "Igbo"),
    ("ilo", "Ilocano"),
    ("id", "Indonesian"),
    ("iu", "Inuktut (Latin)"),
    ("iu", "Inuktut (Syllabics)"),
    ("ga", "Irish"),
    ("it", "Italian"),
    ("jam", "Jamaican Patois"),
    ("ja", "Japanese"),
    ("jv", "Javanese"),
    ("jpn", "Jingpo"),
    ("kl", "Kalaallisut"),
    ("kn", "Kannada"),
    ("kr", "Kanuri"),
    ("pam", "Kapampangan"),
    ("kk", "Kazakh"),
    ("kha", "Khasi"),
    ("km", "Khmer"),
    ("cgg", "Kiga"),
    ("kg", "Kikongo"),
    ("rw", "Kinyarwanda"),
    ("ktu", "Kituba"),
    ("kok", "Kokborok"),
    ("kv", "Komi"),
    ("gom", "Konkani"),
    ("ko", "Korean"),
    ("kri", "Krio"),
    ("ku", "Kurdish (Kurmanji)"),
    ("ckb", "Kurdish (Sorani)"),
    ("ky", "Kyrgyz"),
    ("lo", "Lao"),
    ("ltg", "Latgalian"),
    ("la", "Latin"),
    ("lv", "Latvian"),
    ("lij", "Ligurian"),
    ("li", "Limburgish"),
    ("ln", "Lingala"),
    ("lt", "Lithuanian"),
    ("lmo", "Lombard"),
    ("lg", "Luganda"),
    ("ach", "Luo"),
    ("lb", "Luxembourgish"),
    ("mk", "Macedonian"),
    ("mad", "Madurese"),
    ("mai", "Maithili"),
    ("mak", "Makassar"),
    ("mg", "Malagasy"),
    ("ms", "Malay"),
    ("ms-Arab", "Malay (Jawi)"),
    ("ml", "Malayalam"),
    ("mt", "Maltese"),
    ("mam", "Mam"),
    ("gv", "Manx"),
    ("mi", "Maori"),
    ("mr", "Marathi"),
    ("mh", "Marshallese"),
    ("mrw", "Marwadi"),
    ("acf", "Mauritian Creole"),
    ("mhr", "Meadow Mari"),
    ("mni", "Meiteilon (Manipuri)"),
    ("min", "Minang"),
    ("lus", "Mizo"),
    ("mn", "Mongolian"),
    ("my", "Myanmar (Burmese)"),
    ("nci", "Nahuatl (Eastern Huasteca)"),
    ("nd", "Ndau"),
    ("nr", "Ndebele (South)"),
    ("new", "Nepalbhasa (Newari)"),
    ("ne", "Nepali"),
    ("nko", "NKo"),
    ("nb", "Norwegian (Bokmål)"),
    ("nus", "Nuer"),
    ("oc", "Occitan"),
    ("or", "Odia (Oriya)"),
    ("om", "Oromo"),
    ("os", "Ossetian"),
    ("pag", "Pangasinan"),
    ("pap", "Papiamento"),
    ("ps", "Pashto"),
    ("fa", "Persian"),
    ("pl", "Polish"),
    ("pt-BR", "Portuguese (Brazil)"),
    ("pt-PT", "Portuguese (Portugal)"),
    ("pa-Guru", "Punjabi (Gurmukhi)"),
    ("pa-Arab", "Punjabi (Shahmukhi)"),
    ("qu", "Quechua"),
    ("keq", "Qʼeqchiʼ"),
    ("rom", "Romani"),
    ("ro", "Romanian"),
    ("rn", "Rundi"),
    ("ru", "Russian"),
    ("sme", "Sami (North)"),
    ("sm", "Samoan"),
    ("sg", "Sango"),
    ("sa", "Sanskrit"),
    ("sat", "Santali (Latin)"),
    ("sci", "Santali (Ol Chiki)"),
    ("gd", "Scots Gaelic"),
    ("nso", "Sepedi"),
    ("sr", "Serbian"),
    ("st", "Sesotho"),
    ("crs", "Seychellois Creole"),
    ("shn", "Shan"),
    ("sn", "Shona"),
    ("sc", "Sicilian"),
    ("szl", "Silesian"),
    ("sd", "Sindhi"),
    ("si", "Sinhala"),
    ("sk", "Slovak"),
    ("sl", "Slovenian"),
    ("so", "Somali"),
    ("es", "Spanish"),
    ("su", "Sundanese"),
    ("sus", "Susu"),
    ("sw", "Swahili"),
    ("ss", "Swati"),
    ("sv", "Swedish"),
    ("ty", "Tahitian"),
    ("tg", "Tajik"),
    ("tzm", "Tamazight"),
    ("tzm-Tfng", "Tamazight (Tifinagh)"),
    ("ta", "Tamil"),
    ("tt", "Tatar"),
    ("te", "Telugu"),
    ("tet", "Tetum"),
    ("th", "Thai"),
    ("bo", "Tibetan"),
    ("ti", "Tigrinya"),
    ("tiv", "Tiv"),
    ("tpi", "Tok Pisin"),
    ("to", "Tongan"),
    ("lu", "Tshiluba"),
    ("ts", "Tsonga"),
    ("tn", "Tswana"),
    ("tcy", "Tulu"),
    ("tum", "Tumbuka"),
    ("tr", "Turkish"),
    ("tk", "Turkmen"),
    ("tyv", "Tuvan"),
    ("ak", "Twi"),
    ("udm", "Udmurt"),
    ("uk", "Ukrainian"),
    ("ur", "Urdu"),
    ("ug", "Uyghur"),
    ("uz", "Uzbek"),
    ("ve", "Venda"),
    ("vec", "Venetian"),
    ("vi", "Vietnamese"),
    ("war", "Waray"),
    ("cy", "Welsh"),
    ("wo", "Wolof"),
    ("xh", "Xhosa"),
    ("sah", "Yakut"),
    ("yi", "Yiddish"),
    ("yo", "Yoruba"),
    ("yua", "Yucatec Maya"),
    ("zap", "Zapotec"),
    ("zu", "Zulu"),
]

# Unique code -> canonical name. Duplicate codes keep their first entry
# (ach -> Acholi, iu -> Inuktut (Latin)); the shadowed variants remain
# reachable by name via resolve_target_lang().
LANG_CODES = {}
for _code, _name in LANGUAGES:
    LANG_CODES.setdefault(_code, _name)

# Case-insensitive code lookup. Regional codes carry capitals (zh-CN, pt-BR,
# crh-Cyrl…) and users type them either way, so lookups go through here.
_CODE_LOOKUP = {}
for _code, _name in LANGUAGES:
    _CODE_LOOKUP.setdefault(_code.lower(), _name)

# Codes that existed in older versions of the app but were split or renamed
# in the full Duck.ai list — kept so existing invocations keep working.
_LEGACY_ALIASES = {
    "zh": "Chinese (Simplified)",  # was "zh" -> "Chinese"
    "pt": "Portuguese (Brazil)",   # was "pt" -> "Portuguese"
}

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

    Case-insensitive. Regional codes (zh-CN, pt-BR) work in any case.
    Legacy aliases (zh → Chinese (Simplified), pt → Portuguese (Brazil))
    are preserved for backward compatibility.

    Raises ValueError for anything unknown.
    """
    stripped = code_or_name.strip()
    key = stripped.lower()
    if key in _LEGACY_ALIASES:
        return _LEGACY_ALIASES[key]
    # Exact name match first: the name "Ga" must not be hijacked by the
    # Irish code "ga" (same letters, different case).
    for _code, name in LANGUAGES:
        if name == stripped:
            return name
    if key in _CODE_LOOKUP:
        return _CODE_LOOKUP[key]
    # Case-insensitive full-name lookup over the complete list (incl.
    # duplicated codes, so "luo" and "inuktut (syllabics)" resolve even
    # though they share a code with another entry).
    for _code, name in LANGUAGES:
        if name.lower() == key:
            return name
    raise ValueError(
        f"Unknown target language '{code_or_name}'. {len(LANG_CODES)} languages "
        f"are supported - see 'python st.py -h' or type 'langs' in the menu "
        f"(e.g. ru, es, zh-cn, pt-br, sw)."
    )


# Static part of the translation prompt (shared across all calls).
# Only the target language and the text change per invocation.
_PROMPT_HEADER = (
    "You are an expert translator with 20 years of experience in software localization. "
    "Your native language is {target_lang}. You specialize in preserving nuance, "
    "idioms, sarcasm, technical terminology, and cultural context.\n\n"
    "TASK: Detect the source language of the text below automatically, then translate "
    "it into {target_lang}.\n\n"
    "═══════════════════════════════════════════════════════════════\n"
    "MANDATORY RULES — follow strictly:\n"
    "═══════════════════════════════════════════════════════════════\n\n"
    "1. IDIOMS & METAPHORS: Never translate idioms word-for-word. "
    "Use an equivalent {target_lang} idiom that carries the SAME meaning and tone. "
    "If no equivalent exists, translate the MEANING naturally and keep the original "
    "idiom in parentheses, e.g. (lit. 'barking up the wrong tree').\n\n"
    "2. TECHNICAL TERMS: Use ONLY standard, industry-accepted terminology in "
    "{target_lang}. Do not invent new terms, and do not translate acronyms like "
    "CI/CD, API, or product/platform names.\n\n"
    "3. PROPER NOUNS: Never translate brand names, product names, platforms, "
    "or programming languages (e.g. Kubernetes, AWS, Slack, PHP).\n\n"
    "4. TONE & REGISTER: Preserve the original tone exactly. "
    "If the source is sarcastic, informal, or vulgar — the translation must be "
    "equally sarcastic, informal, or vulgar. Do NOT sanitize, do NOT make it "
    "corporate-friendly, do NOT add politeness that wasn't there.\n\n"
    "5. SLANG & COLLOQUIALISMS: Translate slang into natural {target_lang} slang "
    "of the same intensity — not a weaker, watered-down equivalent.\n\n"
    "6. OUTPUT FORMAT: Reply with ONLY the translated text. "
    "NO headers, NO markdown, NO bullet points, NO explanations, NO notes about "
    "the detected language, NO repetition of the source text, NO 'Here is the "
    "translation:' prefixes, NO model names, NO 'Private' labels.\n\n"
    "7. ACCURACY CHECK: Before outputting, verify that:\n"
    "   - No source-language words remain untranslated (except proper nouns from Rule 3).\n"
    "   - No word-for-word idiom translations exist.\n"
    "   - No technical terms were invented or butchered.\n"
    "   - The tone matches the original.\n\n"
)

_PROMPT_EXAMPLES = (
    "═══════════════════════════════════════════════════════════════\n"
    "FEW-SHOT EXAMPLES (learn the style from these, target language may differ):\n"
    "═══════════════════════════════════════════════════════════════\n\n"
    "Example 1 — Idiom:\n"
    "EN: We are not just barking up the wrong tree here.\n"
    "RU: Мы тут не просто лаем не на то дерево — мы действуем совсем не по адресу.\n\n"
    "Example 2 — Technical + Sarcasm:\n"
    "EN: The logs are a dumpster fire: cascading failures and memory leaks the size of Texas.\n"
    "RU: Логи — это полный пожар в мусорном баке: каскадные отказы, утечки памяти размером с Техас.\n\n"
    "Example 3 — Slang + Metaphor:\n"
    "EN: It's like asking a one-legged man to win an ass-kicking contest.\n"
    "RU: Это как посадить одноногого на турнир по пинанию задниц.\n\n"
    "Example 4 — Cultural reference:\n"
    "EN: Refactoring it is a Sisyphean task.\n"
    "RU: Рефакторить это — сизифов труд.\n\n"
    "Example 5 — Tone preservation:\n"
    "EN: And don't even get me started on the documentation.\n"
    "RU: И даже не начинайте мне про документацию.\n\n"
)


def build_prompt(text: str, target_lang: str) -> str:
    """Build the translation prompt for Duck.ai.

    The prompt instructs the model to preserve idioms, tone, slang and
    technical terms. A few-shot section teaches the desired style.
    """
    return (
        f"{_PROMPT_HEADER.format(target_lang=target_lang)}"
        f"{_PROMPT_EXAMPLES}"
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
def get_config_dir() -> str:
    """Per-user config directory (~/.sonic_translator): browser profile and REPL state."""
    return os.path.join(os.path.expanduser("~"), ".sonic_translator")


def get_user_data_dir() -> str:
    """Persistent Chromium profile (keeps the Duck.ai session)."""
    return os.path.join(get_config_dir(), "browser_data")


def read_text_file(path: str) -> str:
    """Read a text file, handling BOM and legacy encodings.

    Tries UTF-8 first (with BOM stripping), then falls back to cp1251.
    Raises OSError for unreadable paths.
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        # Fallback to cp1251 (common on legacy Windows)
        with open(path, "r", encoding="cp1251", errors="replace") as f:
            return f.read().strip()


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
def dump_debug_info(page, base_dir: str = None) -> str:
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


def dismiss_banners(page, settle_ms: int = 800, probe_timeout_ms: int = 1500):
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


def fill_and_submit(page, prompt: str) -> None:
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


# ═══════════════════════════════════════════════════════════════════════════
#  TRANSLATION SESSION — one browser, many translations
# ═══════════════════════════════════════════════════════════════════════════
class TranslationSession:
    """A reusable Duck.ai session backed by one persistent browser.

    The interactive menu (st_repl) keeps one session alive for the whole run
    so consecutive translations skip the ~5-10s browser startup. The one-shot
    CLI (st.py) uses a short-lived session and closes it after the result.

    The session survives transient browser crashes: if the page dies mid-
    translation ("Target closed"), the browser is restarted and the request
    is retried once. Layout/captcha failures surface as RuntimeError and are
    never retried.

    Thread safety: a single lock serialises translate/reset/close.
    """
    """A reusable Duck.ai session backed by one persistent browser.

    The interactive menu (st_repl) keeps one session alive for the whole run
    so consecutive translations skip the ~5-10s browser startup. The one-shot
    CLI (st.py) uses a short-lived session and closes it after the result.

    The session survives transient browser crashes: if the page dies mid-
    translation ("Target closed"), the browser is restarted and the request
    is retried once. Layout/captcha failures surface as RuntimeError and are
    never retried.

    Thread safety: a single lock serialises translate/reset/close. The REPL
    is sequential, so contention is never visible in practice.
    """

    def __init__(self, user_data_dir=None):
        self._user_data_dir = user_data_dir or get_user_data_dir()
        self._playwright = None
        self._browser = None
        self._page = None
        self._lock = threading.Lock()
        self.translation_count = 0

    # ── lifecycle ────────────────────────────────────────────────────────
    def _ensure_started(self):
        """Launch the browser and open Duck.ai on first use."""
        if self._page is not None:
            return
        os.makedirs(self._user_data_dir, exist_ok=True)
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch_persistent_context(
                user_data_dir=self._user_data_dir,
                **get_browser_kwargs(),
            )
            self._page = self._browser.new_page()
            self._page.add_init_script(get_stealth_init_script())
            self._page.goto(
                DUCK_AI_URL, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS
            )
            self._page.wait_for_timeout(INITIAL_SETTLE_MS)
            dismiss_banners(self._page)
            clear_chat(self._page)
        except Exception:
            self._teardown()
            raise

    def _teardown(self):
        """Close everything and reset state so the session can be restarted."""
        browser, page, pw = self._browser, self._page, self._playwright
        self._browser = self._page = self._playwright = None
        # Page first, then the context/browser — avoids "target closed"
        # exceptions on every teardown. All wrapped, never raises.
        for obj in (page, browser):
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
        if pw is not None:
            try:
                pw.stop()
            except Exception:
                pass

    def close(self):
        """Shut the session down. Safe to call multiple times."""
        with self._lock:
            self._teardown()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @property
    def alive(self) -> bool:
        """True once the browser is up (or still believed to be)."""
        return self._page is not None

    @property
    def user_data_dir(self) -> str:
        """The browser profile directory this session uses."""
        return self._user_data_dir

    def reset_chat(self):
        """Start a fresh Duck.ai conversation ("New Chat")."""
        with self._lock:
            if self._page is None:
                return
            try:
                clear_chat(self._page)
            except Exception:
                pass

    # ── translation ──────────────────────────────────────────────────────
    def translate(self, text: str, target_lang: str) -> str:
        """Translate one text. Retries once if the browser died mid-request.

        Only a page that was alive and then died is restarted. Launch-level
        failures (no network, profile lock, missing browser) surface
        immediately — retrying them would only double the startup delay.
        """
        with self._lock:
            for attempt in (0, 1):
                try:
                    return self._translate_once(text, target_lang)
                except PlaywrightError:
                    # A page that existed but died mid-request -> restart once.
                    # A page that never started (_page is None) -> launch
                    # failure, raise immediately (no pointless relaunch).
                    if self._page is not None and self._page.is_closed():
                        self._teardown()
                        if attempt == 1:
                            raise
                    else:
                        raise
                except RuntimeError as e:
                    # Captcha / layout / extraction issues keep the browser
                    # alive and are never retried. A dead page is restarted.
                    if self._page is not None and not self._page.is_closed():
                        raise
                    self._teardown()
                    if attempt == 1:
                        raise

    def _translate_once(self, text: str, target_lang: str) -> str:
        self._ensure_started()
        page = self._page
        prompt = build_prompt(text, target_lang)
        try:
            clear_chat(page)
            fill_and_submit(page, prompt)
            response = wait_for_response(page, prompt)
        except RuntimeError:
            if not page.is_closed():
                dump_debug_info(page)
            raise
        clean = clean_translation(response, text)
        if not clean:
            raise RuntimeError("Could not extract clean text from the response.")
        self.translation_count += 1
        return clean
