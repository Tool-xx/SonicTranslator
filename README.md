<div align="center">

# ⚡ SonicTranslator

**Free, unlimited, AI-quality translation — straight from your terminal.**

No API keys. No monthly quotas. No signup forms.
Just Python, a hidden browser, and DuckDuckGo's free AI chat doing the heavy lifting.

[Features](#-features) •
[Installation](#-installation) •
[Usage](#-usage) •
[How it works](#%EF%B8%8F-how-it-works) •
[Troubleshooting](#-troubleshooting) •
[FAQ](#-faq)

</div>

---

## What is this?

SonicTranslator is a command-line tool that translates text using an AI model — for free — by driving a real (but invisible) browser session against [Duck.ai](https://duck.ai), DuckDuckGo's free AI chat product. No API key, no OpenAI/Google Cloud billing account, no rate-limited free tier that runs out on day two.

Feed it a sentence or a whole text file, tell it which language you want, and the translation lands directly in your clipboard — ready to paste anywhere.

```bash
python st.py Hello, how are you? ru
# → Привет, как дела? is now on your clipboard
```

---

## ✨ Features

| | |
|---|---|
| 🧠 **AI-quality translations** | Powered by an LLM, not a phrase-lookup table — it understands tone, slang, and context. |
| 🌍 **Auto language detection** | You never specify the source language. Just say where you want it translated *to*. |
| 📋 **Clipboard-first** | No cluttered terminal output. One clean confirmation line, and the result is ready to paste. |
| 📄 **File input support** | Translate an entire `.txt` file with one flag. |
| 🔑 **Zero API keys** | Nothing to sign up for, nothing to pay for, nothing to expire. |
| 🕵️ **Stealth browser session** | Persistent, fingerprint-hardened Chromium context designed to blend in as an ordinary desktop browser. |
| 🧩 **Script-friendly** | Clean exit codes and stderr-only errors make it trivial to call from other tools and pipelines. |
| 🎞️ **Minimal live feedback** | A lightweight spinner animation while translation is in progress — no dead silence, no noisy logs. |

---

## 📦 Installation

**Requirements:** Python 3.8+

```bash
git clone https://github.com/<your-username>/sonictranslator.git
cd sonictranslator

pip install playwright pyperclip
playwright install chromium
```

That's it — no `.env` file, no config, no API key to paste anywhere.

> **Linux users:** if the clipboard doesn't work out of the box, install `xclip` or `xsel`:
> ```bash
> sudo apt install xclip
> ```

---

## 🚀 Usage

### Basic translation

```bash
python st.py <text to translate> <target language code>
```

```bash
python st.py Hello, how are you? ru
python st.py "Bonjour tout le monde" en
python st.py Привет мир en
```

Quotes are optional — SonicTranslator treats everything except the last argument as the text to translate.

### Translate a file

Prefix the file path with `-`:

```bash
python st.py -notes.txt en
```

The file just needs to be plain text (UTF-8, with automatic fallback to Windows‑1251 for legacy files).

### Built-in help

```bash
python st.py
# or
python st.py --help
```

Prints the full usage guide along with the complete language table.

### On success

Exactly one line is printed, and the translation is already on your clipboard:

```
Everything has been translated and copied to the clipboard
```

### On failure

An error is printed to **stderr** and the process exits with a non-zero status — so scripts and other software can check `returncode` instead of parsing stdout.

---

## 🌐 Supported languages

| Code | Language | | Code | Language | | Code | Language |
|---|---|---|---|---|---|---|---|
| `en` | English | | `hi` | Hindi | | `sv` | Swedish |
| `es` | Spanish | | `tr` | Turkish | | `vi` | Vietnamese |
| `fr` | French | | `nl` | Dutch | | `th` | Thai |
| `de` | German | | `pl` | Polish | | `id` | Indonesian |
| `zh` | Chinese | | `ru` | Russian | | `uk` | Ukrainian |
| `ja` | Japanese | | `pt` | Portuguese | | `ar` | Arabic |
| `ko` | Korean | | `it` | Italian | | | |

You only ever pass the **target** code — the source language is detected automatically.

---

## ⚙️ How it works

SonicTranslator doesn't call a translation API. It automates a real browser session against Duck.ai's free AI chat and asks the model to translate for you.

```
your text  →  Playwright-controlled Chromium  →  duck.ai chat  →  AI response  →  cleaned & copied
```

A few deliberate design choices worth knowing about:

- **The browser window is real, not headless.** Headless Chromium is trivially detected by most anti-bot systems, so SonicTranslator launches an ordinary visible browser context — it's just moved off-screen (`window-position: -10000,-10000`) so it never appears on your desktop.
- **Session persistence.** A dedicated Chromium profile is kept under `~/.sonic_translator/`, so cookies and session state carry over between runs instead of starting from scratch every time.
- **Response stabilization.** Rather than guessing a fixed wait time, SonicTranslator polls the AI's response and waits for the text to stop changing before treating it as final — output is only returned once it's actually done streaming.
- **Automatic output cleanup.** UI artifacts that sometimes leak into the raw response (model name badges, "Send" labels, cookie-banner text, etc.) are filtered out before the result ever reaches your clipboard.

---

## 🛠️ Troubleshooting

<details>
<summary><strong>"Duck.ai did not respond within 30s"</strong></summary>

<br>

This usually means Duck.ai's anti-bot layer flagged the session, or the page layout changed. SonicTranslator automatically saves two debug files next to the script when this happens:

- `debug_screenshot.png` — a full-page screenshot at the moment of failure
- `debug_page.html` — the raw page HTML at that moment

Check the screenshot first — it's almost always a cookie banner, a CAPTCHA, or a UI change that needs a selector update.
</details>

<details>
<summary><strong>Nothing gets copied to my clipboard</strong></summary>

<br>

On Linux, make sure `xclip` or `xsel` is installed (`pyperclip` needs one of them to talk to the system clipboard). On Windows and macOS this should work out of the box.
</details>

<details>
<summary><strong>It's slow on the first run</strong></summary>

<br>

The very first launch has to spin up a fresh Chromium profile and load duck.ai from scratch. Subsequent runs reuse the same profile directory and are noticeably faster.
</details>

<details>
<summary><strong>Missing dependency errors</strong></summary>

<br>

```bash
pip install playwright pyperclip
playwright install chromium
```

If you see `Error: missing dependency 'pyperclip'`, it means the package installed above isn't visible to the Python interpreter you're running the script with — double check you're using the same environment.
</details>

---

## ❓ FAQ

**Is this against Duck.ai's terms of service?**
This tool automates a browser to interact with Duck.ai's public web chat rather than calling an official API. Duck.ai's terms may not permit automated use — this project is provided for educational purposes, and you're responsible for how you use it.

**Will this always work?**
It depends on Duck.ai's front-end staying reasonably stable and their anti-bot detection not tightening further. This is an inherent trade-off of any tool built on browser automation against a UI that isn't a stable, versioned API. If you need guaranteed uptime, an official paid translation API is the safer long-term choice.

**Can I use this in my own project?**
Yes — SonicTranslator is a plain CLI. Call it as a subprocess from any language, check the exit code, and read whatever you need from the clipboard or by wiring in your own output handling.

**Why not use Google Translate's API directly?**
Google's official Cloud Translation API requires billing setup and charges per character past a small free tier. SonicTranslator exists specifically for people who want zero-cost, zero-key translation without those constraints — with the trade-off of being slower and less guaranteed than a paid API.

---

<div align="center">

Made for people who are tired of API keys.

</div>
