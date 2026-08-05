# SonicTranslator

**AI-powered translator for your terminal.** No API keys, no accounts, no quotas —
the text is translated through [Duck.ai](https://duck.ai) in a real (invisible) browser window.

> ⚠️ **Heads-up:** this automates a third-party chat UI. It can break when Duck.ai changes
> its layout, and it is subject to their Terms of Service. Use at your own risk.

---

## Quick Start

### Windows
```
Double-click start.bat
```

### Linux / macOS
```bash
./start.sh
```

The launcher will automatically:
- ✅ Check Python 3.8+ is installed
- ✅ Install all dependencies (`pip install -r requirements.txt`)
- ✅ Install Playwright Chromium browser
- ✅ Check for updates from GitHub and auto-update if available
- ✅ Start SonicTranslator

---

## Manual Install

```bash
git clone https://github.com/Tool-xx/SonicTranslator.git
cd SonicTranslator

pip install -r requirements.txt
python -m playwright install chromium

# Run
python src/st.py
```

---

## How to Use

### Interactive Menu (default)
```bash
python src/st.py
# or just double-click start.bat / run ./start.sh
```

You'll see a minimalist prompt:
```
> 
```

Type commands:
```
> help              — show all commands
> langs             — list 247 target languages
> langs port        — filter languages (e.g. Portuguese variants)
> hello world ru    — translate text to Russian
> example.txt en    — translate a file to English
> clip de           — translate clipboard content
> hist              — show translation history
> !1                — copy history entry #1
> new               — reset Duck.ai chat
> clear             — clean screen
> status            — show session info
> theme             — toggle dark/light
> exit              — quit
```

### One-Shot CLI (for integration)
```bash
python src/st.py "Hello, how are you?" ru
python src/st.py notes.txt en
python src/st.py --help
```

Output contract:
- **stdout** (success only): `Everything has been translated and copied to the clipboard`
- **stderr** (errors): descriptive error message
- **exit code**: `0` = success, `1` = error

---

## Features

- **247 target languages** — the full Duck.ai list, including regional variants (`pt-BR`, `zh-CN`, `ms-Arab`...)
- **Source language auto-detected** — you only specify the target
- **Idiom-aware prompt** — preserves tone, slang, and technical terms
- **Clipboard integration** — result copied automatically
- **Translation history** — survives restarts, `!<n>` re-copies any entry
- **Persistent browser session** — consecutive translations are fast (~4s vs ~11s cold start)
- **Debug dumps** — screenshot + HTML saved on failure for diagnosis

---

## Project Structure

```
SonicTranslator/
├── start.bat              ← Windows launcher (double-click to run)
├── start.sh               ← Linux/macOS launcher
├── README.md
├── requirements.txt
├── .gitignore
├── src/
│   ├── st_core.py         ← Core: languages, prompt, browser, translation
│   ├── st.py              ← Entry point: CLI one-shot + interactive menu
│   └── st_repl.py         ← Interactive menu: Rich + prompt_toolkit
└── tests/
    └── test_core.py       ← Unit tests (50 tests)
```

---

## Configuration

All timing knobs live in `src/st_core.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `GOTO_TIMEOUT_MS` | 45000 | Page load timeout |
| `COMPOSER_WAIT_MS` | 15000 | Wait for input box |
| `SUBMIT_WAIT_MS` | 5000 | Wait for submit button |
| `RESPONSE_TIMEOUT_MS` | 30000 | Wait for response |
| `STABILITY_POLL_MS` | 500 | Poll interval while streaming |
| `STABILITY_TICKS_REQUIRED` | 2 | Identical reads before accepting |
| `MAX_STABILITY_POLLS` | 90 | Hard cap on polling loop |

---

## Troubleshooting

On failure, debug files are saved next to `src/`:
- `debug_screenshot.png` — what the page looked like
- `debug_page.html` — raw page markup

Common issues:
- **Captcha/block** — Duck.ai may require human verification. Wait and retry.
- **Layout changed** — Duck.ai updated their UI. Check for project updates.
- **Slow first translation** — Browser cold start takes ~11s. Subsequent translations are ~4s.

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

---

## Updating

The launcher scripts auto-update from GitHub. To update manually:

```bash
git pull origin main
pip install -r requirements.txt
python -m playwright install chromium
```

---

## Limitations

- **Third-party dependency** — depends on Duck.ai's DOM and availability
- **ToS risk** — automating the site may violate their terms
- **Privacy** — your text is sent to Duck.ai; don't translate sensitive data
- **Single browser profile** — running multiple instances may conflict

---

## License

MIT

---

[SonicTranslator](https://github.com/Tool-xx/SonicTranslator) · built with Python, Playwright, Rich, prompt_toolkit
