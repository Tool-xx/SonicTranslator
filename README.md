# SonicTranslator

AI-powered translator for your terminal and desktop. No API keys, no accounts, no quotas —
the text is translated through Duck.ai in a real (invisible) browser window.

`st.py` is a one-shot CLI built for integration: single stdout line, stderr for errors,
exit codes for control flow. `stgui.py` is a dark, distraction-free desktop GUI with a
persistent browser session.

> ⚠️ **Heads-up:** this automates a third-party chat UI. It can break when Duck.ai changes
> its layout, and it is subject to their Terms of Service. See [Limitations](#limitations).

---

## Features

- **20 target languages**, source language auto-detected
- **Integration-friendly CLI** — machine-readable stdout contract, exit codes
- **Desktop GUI** — dark theme, Copy / Clear, `Ctrl+Enter` to translate
- **Idiom-aware prompt** — tone, slang and technical terms are preserved
- **Clipboard** — result copied automatically
- **Debug dumps** — screenshot + page HTML on failure

## Quick start

Requires **Python 3.8+** and a [Playwright](https://playwright.dev/python/) Chromium build.

```bash
git clone https://github.com/Tool-xx/SonicTranslator.git
cd SonicTranslator

pip install -r requirements.txt
python -m playwright install chromium
```

First run launches a hidden Chrome window that downloads nothing and needs no login.

## CLI

```bash
# translate inline text
python st.py "Hello, how are you?" ru

# translate a file (prefix path with "-")
python st.py -notes.txt en

# help / list of language codes
python st.py --help
```

### Integration contract

| Condition                        | stdout                                              | stderr        | exit code |
|----------------------------------|-----------------------------------------------------|---------------|-----------|
| No arguments, `-h` / `--help`    | usage guide                                         | —             | `0`       |
| Success                          | `Everything has been translated and copied to the clipboard` | —      | `0`       |
| Too few arguments (one token)    | —                                                   | error message | `1`       |
| Unknown language                 | —                                                   | error message | `1`       |
| Translation failure              | —                                                   | error message | `1`       |

The exact text is printed to **stdout only on success** — check the return code, not the output.

### Language codes

```
ar Arabic     de German     en English    es Spanish    fr French
hi Hindi      id Indonesian it Italian    ja Japanese   ko Korean
nl Dutch      pl Polish     pt Portuguese ru Russian    sv Swedish
th Thai       tr Turkish    uk Ukrainian  vi Vietnamese zh Chinese
```

## GUI

```bash
python stgui.py
```

Type or paste text, pick a target language, hit **Translate** (or `Ctrl+Enter`).
The GUI keeps one browser open between requests, so consecutive translations are fast.

## How it works

```
┌──────────┐     ┌──────────────────────────────┐
│  st.py   │     │          st_core.py          │
│  CLI     │────▶│  languages · prompt · clean  │──▶ Duck.ai (browser)
│ stgui.py │     │  browser config · timings    │
│  GUI     │     └──────────────────────────────┘
```

| File               | Role                                                                 |
|--------------------|----------------------------------------------------------------------|
| `st_core.py`       | Shared core: language tables, prompt builder, response cleaning, browser launch config, page helpers |
| `st.py`            | CLI entry point — single-shot translate, spinner, clipboard copy     |
| `stgui.py`         | GUI entry point — worker thread + persistent browser, request queue  |

The browser runs in a real window positioned off-screen (`-10000,-10000`) — invisible to
you, but far less detectable as automation than headless mode. The persistent profile
lives in `~/.sonic_translator/browser_data`.

## Configuration

All timing knobs live in `st_core.py`:

| Constant                    | Default | Meaning                                |
|-----------------------------|---------|----------------------------------------|
| `GOTO_TIMEOUT_MS`           | 45000   | page load timeout                      |
| `COMPOSER_WAIT_MS`          | 15000   | wait for the input box                 |
| `SUBMIT_WAIT_MS`            | 5000    | wait for the submit button             |
| `RESPONSE_TIMEOUT_MS`       | 30000   | wait for the response element          |
| `STABILITY_POLL_MS`         | 500     | poll interval while the answer streams |
| `STABILITY_TICKS_REQUIRED`  | 2       | identical reads before accepting       |
| `MAX_STABILITY_POLLS`       | 90      | hard cap on the polling loop           |

## Troubleshooting

On failure the app saves two files next to the script:

- `debug_screenshot.png` — what the page looked like
- `debug_page.html` — the raw page markup

Common causes: Duck.ai layout change, captcha, network block. Check the dump, then re-run.
If translation quality degrades (artifacts like model labels leaking through), the artifact
patterns live in `st_core._ARTIFACT_PATTERNS`.

## Limitations

- **Third-party dependency** — the whole pipeline depends on Duck.ai's DOM and availability.
- **ToS risk** — automating the site may violate their terms; use at your own risk.
- **Privacy** — your text is sent to Duck.ai. Do not translate sensitive data.
- **Single browser profile** — CLI and GUI share `~/.sonic_translator/browser_data`;
  running both at the same time can collide on the profile lock.

---

[SonicTranslator](https://github.com/Tool-xx/SonicTranslator) · built with Python, Playwright, customtkinter
