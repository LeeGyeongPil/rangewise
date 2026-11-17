"""AC-5: English and Korean output, the language order, identical message keys, language-free JSON keys."""
from __future__ import annotations

import json
import re

import pytest

from conftest import run_subprocess

HANGUL = re.compile(r"[가-힣]")


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"{(\w+)}", text))


def test_message_tables_have_the_same_keys_and_placeholders(rw):
    en, ko = rw.MESSAGES["en"], rw.MESSAGES["ko"]
    assert set(en) == set(ko)
    for key in en:
        assert _placeholders(en[key]) == _placeholders(ko[key]), key


def test_english_messages_are_ascii_and_korean_ones_are_korean(rw):
    for key, text in rw.MESSAGES["en"].items():
        if key != "unsupported_line":
            assert text.isascii(), key
    untranslated = {k for k, v in rw.MESSAGES["ko"].items() if not HANGUL.search(v)}
    # error prefixes keep their fixed English shape so callers can match them; "best_line" is just a template
    assert untranslated <= {"err_prefix_invalid_range", "err_prefix_invalid_version", "err_prefix_generic",
                            "best_line", "isect_a"}, untranslated


@pytest.mark.parametrize("cli_value,env,expected", [
    ("ko", {"RANGEWISE_LANG": "en", "LANG": "en_US.UTF-8"}, "ko"),
    ("en", {"RANGEWISE_LANG": "ko", "LANG": "ko_KR.UTF-8"}, "en"),
    (None, {"RANGEWISE_LANG": "ko", "LANG": "en_US.UTF-8"}, "ko"),
    (None, {"RANGEWISE_LANG": "en", "LC_ALL": "ko_KR.UTF-8"}, "en"),
    (None, {"LC_ALL": "ko_KR.UTF-8", "LANG": "en_US.UTF-8"}, "ko"),
    (None, {"LC_MESSAGES": "ko_KR.UTF-8", "LANG": "en_US.UTF-8"}, "ko"),
    (None, {"LC_ALL": "C", "LC_MESSAGES": "ko_KR.UTF-8"}, "en"),
    (None, {"LANG": "ko_KR.UTF-8"}, "ko"),
    (None, {"LANG": "ko"}, "ko"),
    (None, {"LANG": "ja_JP.UTF-8"}, "en"),
    (None, {"RANGEWISE_LANG": "fr"}, "en"),
    (None, {}, "en"),
])
def test_language_resolution_order(rw, cli_value, env, expected):
    assert rw.resolve_lang(cli_value, env) == expected


def test_lang_flag_switches_the_explanation(cli):
    _, en_out, _ = cli("check", "npm", ">=0.9.0", "0.9.1-build.4", "--lang", "en", env={"LANG": "ko_KR.UTF-8"})
    _, ko_out, _ = cli("check", "npm", ">=0.9.0", "0.9.1-build.4", "--lang", "ko", env={"LANG": "en_US.UTF-8"})
    assert not HANGUL.search(en_out) and "prerelease gate" in en_out
    assert HANGUL.search(ko_out) and "사전 릴리스 게이트" in ko_out


def test_environment_variables_pick_the_language(cli):
    assert HANGUL.search(cli("explain", "npm", "^1", env={"RANGEWISE_LANG": "ko"})[1])
    assert HANGUL.search(cli("explain", "npm", "^1", env={"LANG": "ko_KR.UTF-8"})[1])
    assert not HANGUL.search(cli("explain", "npm", "^1", env={"LANG": "de_DE.UTF-8"})[1])
    assert not HANGUL.search(cli("explain", "npm", "^1", env={})[1])


def test_help_is_translated(cli, capsys):
    en = cli("--lang", "en", "--help")
    ko = cli("--lang", "ko", "--help")
    sub_en = cli("check", "--help", "--lang", "en")
    sub_ko = cli("check", "--help", "--lang", "ko")
    assert en[0] == ko[0] == sub_en[0] == sub_ko[0] == 0
    assert not HANGUL.search(en[1]) and HANGUL.search(ko[1])
    assert not HANGUL.search(sub_en[1]) and HANGUL.search(sub_ko[1])
    assert "--lang" in ko[1] or "--lang" in sub_ko[1]


def test_korean_explain_contains_the_exact_bound(cli):
    code, out, _ = cli("explain", "npm", "^0.2.3", "--lang", "ko")
    assert code == 0 and "0.3.0-0" in out and HANGUL.search(out)


def test_json_keys_do_not_depend_on_the_language(cli):
    def keys(value):
        if isinstance(value, dict):
            return {k: keys(v) for k, v in value.items()}
        if isinstance(value, list):
            return [keys(v) for v in value]
        return None

    for args in (("check", "pypi", ">=1.0", "2.0b1"), ("best", "pypi", ">=1.0", "1.0", "2.0b1"),
                 ("intersect", "npm", "^0.2.3", "^0.3.0"), ("explain", "composer", "~1.2")):
        en = json.loads(cli(*args, "--json", "--lang", "en")[1])
        ko = json.loads(cli(*args, "--json", "--lang", "ko")[1])
        assert keys(en) == keys(ko), args
        assert en["explanation"] != ko["explanation"]
        for stable in ("normalized", "ecosystem", "range", "policy"):
            assert en[stable] == ko[stable]


def test_error_lines_keep_their_english_shape_and_add_korean_detail(cli):
    _, _, err_en = cli("check", "npm", "^x.y", "1.0.0", "--lang", "en")
    _, _, err_ko = cli("check", "npm", "^x.y", "1.0.0", "--lang", "ko")
    assert err_en.startswith("rangewise: error: invalid npm range '^x.y': ")
    assert err_ko.startswith("rangewise: error: invalid npm range '^x.y': ") and HANGUL.search(err_ko)
    _, _, unsup = cli("check", "npm", "workspace:^1.0.0", "1.0.0", "--lang", "ko")
    lines = unsup.splitlines()
    assert lines[0].startswith("rangewise: unsupported: workspace: in npm range") and HANGUL.search(lines[1])


def test_real_process_language_from_the_environment():
    _, out, _ = run_subprocess("explain", "npm", "^0.2.3", env={"LANG": "ko_KR.UTF-8"})
    assert "0.3.0-0" in out and HANGUL.search(out)
    _, out, _ = run_subprocess("explain", "npm", "^0.2.3", env={"LANG": "C"})
    assert "0.3.0-0" in out and not HANGUL.search(out)


ENGLISH_ARGPARSE = ("usage:", "positional arguments", "options:", "show this help", "invalid choice",
                    "are required", "unrecognized arguments", "version number")


@pytest.mark.parametrize("args", [["--help"], ["check", "--help"], ["best", "--help"],
                                  ["check", "rubygems", "^1", "1.0"], ["intersect", "npm", "^1"],
                                  ["frobnicate"], ["check", "npm", "^1", "1.0.0", "--bogus"]])
def test_korean_help_and_argument_errors_have_no_english_argparse_phrases(rw, capsys, args):
    code = None
    try:
        code = rw.main(args + ["--lang", "ko"], environ={})
    except SystemExit as exc:  # pragma: no cover - main() already converts it
        code = exc.code
    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert code in (0, 2) and HANGUL.search(text)
    for phrase in ENGLISH_ARGPARSE:
        assert phrase not in text, (args, phrase)


def test_english_help_keeps_the_standard_phrases(rw, capsys):
    rw.main(["check", "--help", "--lang", "en"], environ={})
    out = capsys.readouterr().out
    assert "usage:" in out and "positional arguments" in out and "show this help message and exit" in out
