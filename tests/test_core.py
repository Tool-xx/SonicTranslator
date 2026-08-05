#!/usr/bin/env python3
"""Unit tests for st_core.py."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from st_core import (
    LANG_CODES, LANGUAGES, _LEGACY_ALIASES, _CODE_LOOKUP,
    _PROMPT_HEADER, _PROMPT_EXAMPLES,
    build_prompt, clean_translation, read_text_file, resolve_target_lang,
)

# Cyrillic test strings (avoid raw Cyrillic in source to prevent encoding issues)
RU = "\u041f\u0440\u0438\u0432\u0435\u0442"  # Привет


class TestResolveTargetLang:
    def test_code_lowercase(self):
        assert resolve_target_lang("ru") == "Russian"

    def test_code_uppercase(self):
        assert resolve_target_lang("RU") == "Russian"

    def test_code_whitespace(self):
        assert resolve_target_lang("  ru  ") == "Russian"

    def test_name_exact(self):
        assert resolve_target_lang("Russian") == "Russian"

    def test_name_lowercase(self):
        assert resolve_target_lang("russian") == "Russian"

    def test_regional_zh_cn(self):
        assert resolve_target_lang("zh-cn") == "Chinese (Simplified)"

    def test_regional_zh_tw(self):
        assert resolve_target_lang("zh-TW") == "Chinese (Traditional)"

    def test_regional_pt_br(self):
        assert resolve_target_lang("pt-br") == "Portuguese (Brazil)"

    def test_legacy_zh(self):
        assert resolve_target_lang("zh") == "Chinese (Simplified)"

    def test_legacy_pt(self):
        assert resolve_target_lang("pt") == "Portuguese (Brazil)"

    def test_ga_name_vs_code(self):
        assert resolve_target_lang("Ga") == "Ga"
        assert resolve_target_lang("ga") == "Irish"

    def test_shadowed_luo(self):
        assert resolve_target_lang("Luo") == "Luo"
        assert resolve_target_lang("ach") == "Acholi"

    def test_shadowed_inuktut(self):
        assert resolve_target_lang("Inuktut (Syllabics)") == "Inuktut (Syllabics)"
        assert resolve_target_lang("iu") == "Inuktut (Latin)"

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown target language"):
            resolve_target_lang("xx")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            resolve_target_lang("")

    def test_all_codes_resolve(self):
        for code, name in LANG_CODES.items():
            assert resolve_target_lang(code) == name

    def test_all_names_resolve(self):
        for _code, name in LANGUAGES:
            assert resolve_target_lang(name) == name

    def test_lang_codes_count(self):
        assert len(LANG_CODES) == 247

    def test_languages_count(self):
        assert len(LANGUAGES) == 249


class TestCleanTranslation:
    def test_empty(self):
        assert clean_translation("", "hello") == ""

    def test_none(self):
        assert clean_translation(None, "hello") == ""

    def test_removes_gpt_nano(self):
        result = clean_translation("GPT-4o nano\n" + RU, "Hello")
        assert "GPT" not in result
        assert RU in result

    def test_removes_private(self):
        result = clean_translation("Private\n" + RU, "Hello")
        assert "Private" not in result

    def test_removes_send(self):
        result = clean_translation(RU + "\nSend", "Hello")
        assert "Send" not in result

    def test_removes_switch_model(self):
        result = clean_translation(RU + "\nSwitch model", "Hello")
        assert "Switch" not in result

    def test_removes_feedback(self):
        result = clean_translation(RU + "\nPositive feedback", "Hello")
        assert "feedback" not in result.lower()

    def test_removes_new_chat(self):
        result = clean_translation(RU + "\nNew Chat", "Hello")
        assert "New Chat" not in result

    def test_collapses_blanks(self):
        result = clean_translation(RU + "\n\n\n\n" + RU, "Hello")
        assert "\n\n\n" not in result

    def test_collapses_spaces(self):
        result = clean_translation(RU + "   " + RU, "Hello")
        assert "   " not in result

    def test_echo_removal(self):
        result = clean_translation("Hello, world!\n" + RU, "Hello, world!")
        assert RU in result

    def test_short_translation_preserved(self):
        result = clean_translation(RU, RU + "?")
        assert result == RU

    def test_multiline(self):
        raw = "Line 1\nLine 2\nLine 3"
        result = clean_translation(raw, "Original")
        assert "Line 1" in result and "Line 3" in result


class TestBuildPrompt:
    def test_contains_language(self):
        assert "Russian" in build_prompt("Hello", "Russian")

    def test_contains_text(self):
        assert "Hello, world!" in build_prompt("Hello, world!", "Russian")

    def test_contains_rules(self):
        assert "MANDATORY RULES" in build_prompt("test", "Russian")

    def test_contains_examples(self):
        assert "FEW-SHOT EXAMPLES" in build_prompt("test", "Russian")

    def test_different_languages(self):
        for lang in ["Russian", "Spanish", "Japanese", "Arabic"]:
            assert lang in build_prompt("test", lang)

    def test_empty_text(self):
        assert "TEXT TO TRANSLATE" in build_prompt("", "Russian")

    def test_constants_exist(self):
        assert isinstance(_PROMPT_HEADER, str) and len(_PROMPT_HEADER) > 100
        assert isinstance(_PROMPT_EXAMPLES, str) and len(_PROMPT_EXAMPLES) > 100


class TestReadTextFile:
    def test_utf8(self, tmp_path):
        f = tmp_path / "t.txt"
        f.write_text("Hello!", encoding="utf-8")
        assert read_text_file(str(f)) == "Hello!"

    def test_bom_stripped(self, tmp_path):
        f = tmp_path / "t.txt"
        with open(f, "wb") as fh:
            fh.write(b"\xef\xbb\xbf")
            fh.write("Hello!".encode("utf-8"))
        assert read_text_file(str(f)) == "Hello!"

    def test_bom_cyrillic(self, tmp_path):
        f = tmp_path / "t.txt"
        with open(f, "wb") as fh:
            fh.write(b"\xef\xbb\xbf")
            fh.write(RU.encode("utf-8"))
        assert read_text_file(str(f)) == RU

    def test_cp1251_fallback(self, tmp_path):
        f = tmp_path / "t.txt"
        with open(f, "wb") as fh:
            fh.write(RU.encode("cp1251"))
        result = read_text_file(str(f))
        assert RU in result

    def test_strips_whitespace(self, tmp_path):
        f = tmp_path / "t.txt"
        f.write_text("  Hello  \n", encoding="utf-8")
        assert read_text_file(str(f)) == "Hello"

    def test_nonexistent_raises(self):
        with pytest.raises(OSError):
            read_text_file("/nonexistent/file.txt")

    def test_empty_file(self, tmp_path):
        f = tmp_path / "t.txt"
        f.write_text("", encoding="utf-8")
        assert read_text_file(str(f)) == ""


class TestLanguageData:
    def test_duplicate_codes(self):
        code_counts = {}
        for code, _ in LANGUAGES:
            code_counts[code] = code_counts.get(code, 0) + 1
        dupes = {c for c, n in code_counts.items() if n > 1}
        assert dupes == {"ach", "iu"}

    def test_all_names_unique(self):
        names = [name for _, name in LANGUAGES]
        assert len(names) == len(set(names))

    def test_code_lookup_lowercase(self):
        for key in _CODE_LOOKUP:
            assert key == key.lower()

    def test_legacy_aliases_valid(self):
        real_names = {name for _, name in LANGUAGES}
        for alias, mapped in _LEGACY_ALIASES.items():
            assert mapped in real_names
