#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SonicTranslator — minimal desktop GUI
Powered by Duck.ai via Playwright

A clean, dark, distraction-free translator window: type or paste text,
pick a target language, hit Translate. Source language is detected
automatically. No accounts, no API keys, no clutter.

Shared logic (languages, prompts, response cleaning, browser config) lives
in st_core.py so the CLI and GUI can never drift apart.
"""

import os
import sys
import threading
import queue

try:
    import customtkinter as ctk
except ImportError:
    print(
        "Error: missing dependency 'customtkinter'. "
        "Install with: pip install customtkinter",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print(
        "Error: missing dependency 'playwright'. Install with:\n"
        "    pip install playwright\n"
        "    python -m playwright install chromium",
        file=sys.stderr,
    )
    sys.exit(1)

from st_core import (
    LANG_NAMES_SORTED,
    build_prompt,
    clean_translation,
    clear_chat,
    dismiss_banners,
    dump_debug_info,
    fill_and_submit,
    get_browser_kwargs,
    get_stealth_init_script,
    get_user_data_dir,
    wait_for_response,
    DUCK_AI_URL,
    GOTO_TIMEOUT_MS,
    INITIAL_SETTLE_MS,
)

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


# ═══════════════════════════════════════════════════════════════════════════
#  TRANSLATION WORKER — one persistent hidden browser, serialized requests
#  Results are pushed onto a queue that the GUI polls from the main thread,
#  so no Tk call ever happens from the worker thread.
# ═══════════════════════════════════════════════════════════════════════════
class TranslationWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self._requests = queue.Queue()
        self._results = queue.Queue()
        self._stop_event = threading.Event()
        self._ready = threading.Event()
        self._fatal_error = None
        self._playwright = None
        self._browser = None
        self._page = None

    # ── public API (called from the GUI thread) ─────────────────────────
    def translate(self, text: str, target_lang: str, callback):
        self._requests.put((text, target_lang, callback))

    def poll_results(self):
        """Drain finished jobs: list of (callback, result, success)."""
        done = []
        while True:
            try:
                done.append(self._results.get_nowait())
            except queue.Empty:
                return done

    def wait_ready(self, timeout=0.5) -> bool:
        return self._ready.wait(timeout=timeout)

    def fatal_error(self):
        """Fatal worker error (startup failure or mid-run crash), if any."""
        return self._fatal_error

    def stop(self, timeout=2.0):
        """Ask the worker to shut down. Blocking is bounded so the window
        closes promptly; browser cleanup happens in run()'s finally."""
        self._stop_event.set()
        self.join(timeout=timeout)

    # ── worker thread ───────────────────────────────────────────────────
    def run(self):
        try:
            try:
                self._init_browser()
            except Exception as e:
                # Never pretend we are ready if the browser could not start.
                self._fatal_error = e
                self._ready.set()
                return
            self._ready.set()

            try:
                while not self._stop_event.is_set():
                    try:
                        text, target_lang, callback = self._requests.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    try:
                        result = self._do_translate(text, target_lang)
                        self._results.put((callback, result, True))
                    except Exception as e:
                        self._results.put((callback, str(e), False))
            except Exception as e:
                # A crash outside the per-request guards: tell the UI instead
                # of dying silently with the app stuck on "Ready" forever.
                self._fatal_error = e
        finally:
            self._cleanup()

    def _init_browser(self):
        user_data_dir = get_user_data_dir()
        os.makedirs(user_data_dir, exist_ok=True)

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            **get_browser_kwargs(),
        )
        self._page = self._browser.new_page()
        self._page.add_init_script(get_stealth_init_script())
        self._page.goto(DUCK_AI_URL, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
        self._page.wait_for_timeout(INITIAL_SETTLE_MS)
        dismiss_banners(self._page)

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

    def _do_translate(self, text: str, target_lang: str) -> str:
        prompt = build_prompt(text, target_lang)

        # Reuse the open page: reset the conversation, or reload as fallback.
        if not clear_chat(self._page):
            try:
                self._page.reload(wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
            except Exception:
                pass
            self._page.wait_for_timeout(2500)
            dismiss_banners(self._page)

        fill_and_submit(self._page, prompt)

        try:
            response_text = wait_for_response(self._page, prompt)
        except RuntimeError:
            dump_debug_info(self._page)
            raise

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
        self.after(100, self._poll_results)

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

    # ── worker readiness / results ──────────────────────────────────────
    def _poll_ready(self):
        if self._worker.wait_ready(timeout=0.3):
            err = self._worker.fatal_error()
            if err is not None:
                self._set_status("Startup failed", COLOR["danger"])
                self._set_output_text(
                    f"Could not start the translation engine.\n\n{err}"
                )
                self.translate_btn.configure(state="disabled")
            else:
                self._set_status("Ready", COLOR["text_muted"])
        else:
            self.after(200, self._poll_ready)

    def _poll_results(self):
        # Runs on the main thread, so callbacks may touch Tk freely.
        for callback, result, success in self._worker.poll_results():
            callback(result, success)
        # If the worker died after startup (ready was set), stop pretending
        # everything is fine: surface the error and disable the button.
        if (self._worker.fatal_error() is not None
                and not self._worker.is_alive()
                and self._worker.wait_ready(timeout=0)):
            self._set_status("Engine stopped", COLOR["danger"])
            self.translate_btn.configure(state="disabled")
            return
        self.after(100, self._poll_results)

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

        self._is_busy = True
        self._set_busy_ui(True)

        def callback(result, success):
            self._on_done(result, success)

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
        self._worker.stop(timeout=2)
        self.destroy()


if __name__ == "__main__":
    app = SonicTranslatorApp()
    app.mainloop()
