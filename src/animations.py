#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SonicTranslator — custom loading animations.

Provides beautiful, minimal terminal animations for the translation process.
Uses Rich's Live display with custom frame sequences.
"""

import itertools
import threading
import time


# ═══════════════════════════════════════════════════════════════════════════
#  SPINNER FRAMES — curated for elegance + Windows compatibility
# ═══════════════════════════════════════════════════════════════════════════
import sys

def _is_legacy_windows():
    """Detect legacy Windows terminal (cp1251, no VT)."""
    return (
        sys.platform == "win32"
        and hasattr(sys.stdout, "encoding")
        and sys.stdout.encoding
        and sys.stdout.encoding.lower() in ("cp1251", "cp437", "latin-1")
    )

LEGACY = _is_legacy_windows()

# Modern terminals (Linux, macOS, Windows Terminal)
BRAILLE_WAVE = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
MORPHING_STAR = ["·", "✻", "✽", "✶", "✳", "✢"]
BREATHING_DOTS = [".  ", ".. ", "...", " ..", " . ", "   "]
HORIZONTAL_GROWTH = ["▏", "▎", "▍", "▌", "▋", "⡊", "▉", "⡊", "▋", "▌", "▍", "▎"]

# Legacy Windows (ASCII-only fallback)
ASCII_SPINNER = ["|", "/", "-", "\\"]
ASCII_DOTS = [".  ", ".. ", "...", " ..", " . ", "   "]

# Choose frames based on terminal
BRAILLE = ASCII_SPINNER if LEGACY else BRAILLE_WAVE
STAR = ASCII_DOTS if LEGACY else MORPHING_STAR
DOTS = ASCII_DOTS if LEGACY else BREATHING_DOTS
GROW = ASCII_SPINNER if LEGACY else HORIZONTAL_GROWTH


# ═══════════════════════════════════════════════════════════════════════════
#  TRANSLATION PHASES — contextual status messages
# ═══════════════════════════════════════════════════════════════════════════

TRANSLATION_PHASES = [
    ("Connecting to Duck.ai", BRAILLE, 80),
    ("Preparing text", STAR, 100),
    ("Translating", BRAILLE, 80),
    ("Almost done", DOTS, 300),
]


# ═══════════════════════════════════════════════════════════════════════════
#  ANIMATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class TranslationAnimation:
    """Animated status display for translation operations.

    Shows a cycling spinner with phase-aware messages. The animation
    runs in a background thread and renders via Rich's Live display.
    """

    def __init__(self, console, target_lang: str):
        self.console = console
        self.target_lang = target_lang
        self._stop = threading.Event()
        self._thread = None
        self._phase = 0
        self._frame = 0

    def _get_renderable(self):
        """Build the current animation frame as a Rich renderable."""
        from rich.text import Text

        phase_msg, frames, _ = TRANSLATION_PHASES[self._phase % len(TRANSLATION_PHASES)]
        spinner = frames[self._frame % len(frames)]
        arrow = " -> " if LEGACY else " \u2192 "

        text = Text()
        text.append(f"  {spinner} ", style="bold cyan")
        text.append(f"{phase_msg}", style="bold green")
        text.append(f"{arrow}{self.target_lang}", style="bold yellow")
        text.append("  ", style="bold cyan")

        return text

    def _animate(self):
        """Background thread: cycle frames and phases."""
        from rich.live import Live

        with Live(self._get_renderable(), console=self.console, refresh_per_second=12) as live:
            phase_idx = 0
            phase_start = time.monotonic()
            phase_duration = 2.5  # seconds per phase

            while not self._stop.is_set():
                # Update frame
                self._frame += 1

                # Check if it's time to advance phase
                now = time.monotonic()
                if now - phase_start > phase_duration:
                    phase_idx = min(phase_idx + 1, len(TRANSLATION_PHASES) - 1)
                    self._phase = phase_idx
                    phase_start = now

                live.update(self._get_renderable())
                self._stop.wait(timeout=0.08)  # ~12 FPS

    def start(self):
        """Start the animation."""
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the animation and clear the line."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)


# ═══════════════════════════════════════════════════════════════════════════
#  SIMPLE SPINNER — for quick operations
# ═══════════════════════════════════════════════════════════════════════════

def register_custom_spinners():
    """Register custom spinner animations with Rich for use in console.status()."""
    try:
        from rich._spinners import SPINNERS

        SPINNERS["braille"] = {
            "interval": 80,
            "frames": BRAILLE,
        }
        SPINNERS["morph"] = {
            "interval": 100,
            "frames": STAR,
        }
        SPINNERS["grow"] = {
            "interval": 120,
            "frames": GROW,
        }
    except (ImportError, AttributeError):
        pass  # Rich version too old; custom spinners unavailable


# Auto-register on import
register_custom_spinners()
