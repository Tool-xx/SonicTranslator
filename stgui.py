#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SonicTranslator — minimal desktop GUI
Powered by Duck.ai via Playwright

A clean, dark, distraction-free translator window: type or paste text,
pick a target language, hit Translate. Source language is detected
automatically. No accounts, no API keys, no clutter.
"""

import os
import re
import sys
import threading
import queue

import customtkinter as ctk
from playwright.sync_api import sync_playwright

# ═══════════════════════════════════════════════════════════════════════════
#  THEME — grayscale + a single muted accent, generous spacing, flat surfaces
# ═══════════════════════════════════════════════════════════════════════════
ctk.set_appearance_mode("dark")

COLOR = {
    "bg": "#101113",
    "surface": "#17181b",
    "surface_alt": "#1c1d21",
    "border": "#2a2c31",
    "border_focus": "#c9975a",
    "text": "#e8e9ea",
    "text_muted": "#84868c",
    "text_faint": "#54565c",
    "accent": "#c9975a",
    "accent_hover": "#b3854e",
    "danger": "#c76a63",
}

FONT_FAMILY = "Segoe UI" if sys.platform.startswith("win") else "Helvetica"

LANG_CODES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German",
    "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "ru": "Russian",
    "pt": "Portuguese", "it": "Italian", "ar": "Arabic", "hi": "Hindi",
    "tr": "Turkish", "nl": "Dutch", "pl": "Polish", "sv": "Swedish",
    "vi": "Vietnamese", "th": "Thai", "id": "Indonesian", "uk": "Ukrainian",
}
NAME_TO_CODE = {name: code for code, name in LANG_CODES.items()}
LANG_NAMES_SORTED = sorted(LANG_CODES.values())

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
    re.compile(r"^\s*Continuer\s*$", re.IGNORECASE),
    re.compile(r"^\s*Continue\s*$", re.IGNORECASE),
    re.compile(r"^\s*New Chat\s*$", re.IGNORECASE),
    re.compile(r"^\s*Clear conversation\s*$", re.IGNORECASE),
]


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


def build_prompt(text: str, target_lang: str) -> str:
    return (
        f"You are an expert translator with 20 years of experience in software localization. "
        f"Your native language is {target_lang}. You specialize in preserving nuance, "
        f"idioms, sarcasm, technical terminology, and cultural context.\n\n"
        f"TASK: Detect the source language of the text below automatically, then translate "
        f"it into {target_lang}.\n\n"
        f"MANDATORY RULES — follow strictly:\n\n"
        f"1. IDIOMS & METAPHORS: Never translate idioms word-for-word. Use an equivalent "
        f"{target_lang} idiom with the SAME meaning and tone, or translate the meaning "
        f"naturally if no equivalent exists.\n\n"
        f"2. TECHNICAL TERMS: Use ONLY standard, industry-accepted terminology in "
        f"{target_lang}. Do not invent new terms; keep acronyms like CI/CD or API as-is.\n\n"
        f"3. PROPER NOUNS: Never translate brand names, product names, platforms, or "
        f"programming languages.\n\n"
        f"4. TONE & REGISTER: Preserve the original tone exactly — sarcastic, informal, "
        f"or vulgar stays that way. Do not sanitize or add politeness that wasn't there.\n\n"
        f"5. SLANG: Translate slang into natural {target_lang} slang of the same intensity.\n\n"
        f"6. OUTPUT FORMAT: Reply with ONLY the translated text. NO headers, NO markdown, "
        f"NO explanations, NO notes about the detected language, NO repetition of the "
        f"source text, NO 'Here is the translation:' prefixes, NO model names.\n\n"
        f"7. ACCURACY CHECK before answering: no untranslated source words remain (except "
        f"proper nouns), no idiom was translated word-for-word, no term was invented, tone "
        f"matches the original.\n\n"
        f"TEXT TO TRANSLATE:\n\n{text}"
    )


# ═══════════════════════════════════════════════════════════════════════════
#  TRANSLATION WORKER — one persistent hidden browser, serialized requests
# ═══════════════════════════════════════════════════════════════════════════
class TranslationWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._ready = threading.Event()
        self._playwright = None
        self._browser = None
        self._page = None

    def translate(self, text: str, target_lang: str, callback):
        self._queue.put((text, target_lang, callback))

    def wait_ready(self, timeout=0.5) -> bool:
        return self._ready.wait(timeout=timeout)

    def stop(self, timeout=8.0):
        self._stop_event.set()
        self.join(timeout=timeout)
        self._cleanup()

    def run(self):
        try:
            self._init_browser()
            self._ready.set()
            while not self._stop_event.is_set():
                try:
                    text, target_lang, callback = self._queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                try:
                    result = self._do_translate(text, target_lang)
                    callback(result, True)
                except Exception as e:
                    callback(str(e), False)
        except Exception:
            self._ready.set()
        finally:
            self._cleanup()

    def _init_browser(self):
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

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch_persistent_context(
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
        self._page = self._browser.new_page()
        self._page.add_init_script("""
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
        self._page.goto("https://duck.ai", wait_until="domcontentloaded", timeout=45000)
        self._page.wait_for_timeout(3500)
        self._dismiss_banners()

    def _cleanup(self):
        for obj in (self._page, self._browser):
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass

    def _dismiss_banners(self):
        for btn_text in ["Continuer", "Continue", "Accept", "Agree", "OK", "Got it", "I Agree"]:
            try:
                btn = self._page.locator(f'button:has-text("{btn_text}")').first
                if btn.is_visible(timeout=1500):
                    btn.click()
                    self._page.wait_for_timeout(800)
            except Exception:
                continue

    def _clear_chat(self) -> bool:
        for sel in ['button:has-text("New Chat")', 'button[aria-label="New Chat"]',
                    'button:has-text("Clear conversation")']:
            try:
                btn = self._page.locator(sel).first
                if btn.is_visible(timeout=1500):
                    btn.click()
                    self._page.wait_for_timeout(1000)
                    return True
            except Exception:
                continue
        return False

    def _do_translate(self, text: str, target_lang: str) -> str:
        prompt = build_prompt(text, target_lang)

        if not self._clear_chat():
            self._page.reload(wait_until="domcontentloaded", timeout=45000)
            self._page.wait_for_timeout(2500)
            self._dismiss_banners()

        textarea = self._page.locator("textarea").first
        textarea.click()
        textarea.fill(prompt)
        self._page.wait_for_timeout(400)

        submit = self._page.locator('button[type="submit"]').first
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

        self._page.wait_for_selector('div[data-activeresponse="true"]', timeout=30000)

        last_text = ""
        stable_ticks = 0
        response_text = ""
        for _ in range(90):
            self._page.wait_for_timeout(500)
            try:
                count = self._page.locator('div[data-activeresponse="true"]').count()
                if count == 0:
                    continue
                container = self._page.locator('div[data-activeresponse="true"]').nth(count - 1)
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
            raise RuntimeError("No stable response from Duck.ai in time.")

        clean = clean_translation(response_text, text)
        if not clean:
            raise RuntimeError("Could not extract clean text from the response.")
        return clean


# ═══════════════════════════════════════════════════════════════════════════
#  UI
# ═══════════════════════════════════════════════════════════════════════════
class SonicTranslatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SonicTranslator")
        self.geometry("980x620")
        self.minsize(760, 480)
        self.configure(fg_color=COLOR["bg"])

        self._is_busy = False
        self._spinner_job = None
        self._spinner_frame = 0

        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        self._build_layout()

        self._worker = TranslationWorker()
        self._worker.start()
        self._set_status("Starting…", COLOR["text_muted"])
        self.after(200, self._poll_ready)

    # ── layout ───────────────────────────────────────────────────────────
    def _build_layout(self):
        root = ctk.CTkFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=28, pady=24)
        root.grid_rowconfigure(2, weight=1)
        root.grid_columnconfigure(0, weight=1)

        # ── header row: wordmark + status ──
        header = ctk.CTkFrame(root, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header, text="SonicTranslator",
            font=(FONT_FAMILY, 20, "normal"),
            text_color=COLOR["text"],
        ).grid(row=0, column=0, sticky="w")

        self.status_label = ctk.CTkLabel(
            header, text="", font=(FONT_FAMILY, 12),
            text_color=COLOR["text_muted"],
        )
        self.status_label.grid(row=0, column=1, sticky="e")

        # ── language row ──
        lang_row = ctk.CTkFrame(root, fg_color="transparent")
        lang_row.grid(row=1, column=0, sticky="ew", pady=(0, 16))

        ctk.CTkLabel(
            lang_row, text="Translate to",
            font=(FONT_FAMILY, 13), text_color=COLOR["text_muted"],
        ).pack(side="left", padx=(0, 10))

        self.lang_var = ctk.StringVar(value="Russian")
        self.lang_menu = ctk.CTkOptionMenu(
            lang_row,
            values=LANG_NAMES_SORTED,
            variable=self.lang_var,
            width=180,
            height=32,
            corner_radius=8,
            fg_color=COLOR["surface"],
            button_color=COLOR["surface_alt"],
            button_hover_color=COLOR["border"],
            dropdown_fg_color=COLOR["surface"],
            dropdown_hover_color=COLOR["surface_alt"],
            text_color=COLOR["text"],
            font=(FONT_FAMILY, 13),
            dropdown_font=(FONT_FAMILY, 13),
        )
        self.lang_menu.pack(side="left")

        # ── text panes ──
        panes = ctk.CTkFrame(root, fg_color="transparent")
        panes.grid(row=2, column=0, sticky="nsew", pady=(0, 16))
        panes.grid_columnconfigure(0, weight=1)
        panes.grid_columnconfigure(1, weight=1)
        panes.grid_rowconfigure(0, weight=1)

        self.input_box = self._make_textbox(panes, editable=True)
        self.input_box["frame"].grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.output_box = self._make_textbox(panes, editable=False)
        self.output_box["frame"].grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self.input_box["text"].bind("<Control-Return>", lambda e: self._trigger_translate())

        # ── toolbars under each pane ──
        in_tools = ctk.CTkFrame(panes, fg_color="transparent")
        in_tools.grid(row=1, column=0, sticky="w", pady=(8, 0), padx=(0, 8))
        self._make_ghost_button(in_tools, "Copy", lambda: self._copy(self.input_box["text"])).pack(side="left", padx=(0, 8))
        self._make_ghost_button(in_tools, "Clear", self._clear_all).pack(side="left")

        out_tools = ctk.CTkFrame(panes, fg_color="transparent")
        out_tools.grid(row=1, column=1, sticky="w", pady=(8, 0), padx=(8, 0))
        self._make_ghost_button(out_tools, "Copy", lambda: self._copy(self.output_box["text"])).pack(side="left")

        # ── translate button + progress bar ──
        action_row = ctk.CTkFrame(root, fg_color="transparent")
        action_row.grid(row=3, column=0, sticky="ew")
        action_row.grid_columnconfigure(0, weight=1)

        self.translate_btn = ctk.CTkButton(
            action_row,
            text="Translate",
            command=self._trigger_translate,
            height=40,
            corner_radius=8,
            fg_color=COLOR["accent"],
            hover_color=COLOR["accent_hover"],
            text_color="#17181b",
            font=(FONT_FAMILY, 14, "bold"),
        )
        self.translate_btn.grid(row=0, column=0, sticky="ew")

        self.progress = ctk.CTkProgressBar(
            action_row, mode="indeterminate", height=3,
            corner_radius=2, fg_color=COLOR["surface"],
            progress_color=COLOR["accent"],
        )
        self.progress.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.progress.grid_remove()

    def _make_textbox(self, parent, editable: bool):
        frame = ctk.CTkFrame(
            parent, fg_color=COLOR["surface"], corner_radius=12,
            border_width=1, border_color=COLOR["border"],
        )
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        text = ctk.CTkTextbox(
            frame,
            fg_color="transparent",
            text_color=COLOR["text"],
            font=(FONT_FAMILY, 14),
            wrap="word",
            border_width=0,
            padx=16,
            pady=16,
        )
        text.grid(row=0, column=0, sticky="nsew")
        if not editable:
            text.configure(state="disabled")
        return {"frame": frame, "text": text}

    def _make_ghost_button(self, parent, label, command):
        return ctk.CTkButton(
            parent, text=label, command=command,
            width=64, height=28, corner_radius=6,
            fg_color="transparent",
            hover_color=COLOR["surface_alt"],
            border_width=1, border_color=COLOR["border"],
            text_color=COLOR["text_muted"],
            font=(FONT_FAMILY, 12),
        )

    # ── worker readiness ─────────────────────────────────────────────────
    def _poll_ready(self):
        if self._worker.wait_ready(timeout=0.3):
            self._set_status("Ready", COLOR["text_muted"])
        else:
            self.after(200, self._poll_ready)

    # ── actions ──────────────────────────────────────────────────────────
    def _set_status(self, text, color):
        self.status_label.configure(text=text, text_color=color)

    def _set_output_text(self, text):
        box = self.output_box["text"]
        box.configure(state="normal")
        box.delete("0.0", "end")
        box.insert("0.0", text)
        box.configure(state="disabled")

    def _copy(self, widget):
        content = widget.get("0.0", "end").strip()
        if not content:
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        prev = self.status_label.cget("text")
        self._set_status("Copied", COLOR["accent"])
        self.after(1200, lambda: self._set_status(prev if prev != "Copied" else "Ready", COLOR["text_muted"]))

    def _clear_all(self):
        self.input_box["text"].delete("0.0", "end")
        self._set_output_text("")

    def _trigger_translate(self):
        if self._is_busy:
            return
        text = self.input_box["text"].get("0.0", "end").strip()
        if not text:
            return

        target_name = self.lang_var.get()
        target_code = NAME_TO_CODE.get(target_name, "en")

        self._is_busy = True
        self._set_busy_ui(True)

        def callback(result, success):
            self.after(0, lambda: self._on_done(result, success))

        self._worker.translate(text, target_name, callback)

    def _set_busy_ui(self, busy: bool):
        if busy:
            self.translate_btn.configure(state="disabled")
            self.progress.grid()
            self.progress.start()
            self._spinner_frame = 0
            self._animate_button()
            self._set_status("Translating", COLOR["accent"])
        else:
            self.translate_btn.configure(state="normal", text="Translate")
            self.progress.stop()
            self.progress.grid_remove()
            if self._spinner_job:
                self.after_cancel(self._spinner_job)
                self._spinner_job = None

    def _animate_button(self):
        dots = "." * ((self._spinner_frame % 3) + 1)
        self.translate_btn.configure(text=f"Translating{dots}")
        self._spinner_frame += 1
        self._spinner_job = self.after(400, self._animate_button)

    def _on_done(self, result, success):
        self._is_busy = False
        self._set_busy_ui(False)
        if success:
            self._set_output_text(result)
            self._set_status("Ready", COLOR["text_muted"])
        else:
            self._set_output_text(f"Translation failed: {result}")
            self._set_status("Error", COLOR["danger"])

    def _on_closing(self):
        self._worker.stop(timeout=8)
        self.destroy()


if __name__ == "__main__":
    app = SonicTranslatorApp()
    app.mainloop()