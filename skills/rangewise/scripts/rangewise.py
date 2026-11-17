#!/usr/bin/env python3
"""rangewise - decide version ranges the way each package ecosystem does.

Ecosystems: npm, cargo, pypi (PEP 440), composer, maven.
Commands:   check (is a version inside a range), best (which candidate gets picked),
            intersect (do two ranges overlap), explain (what does a range mean).

Every range is turned into a list of intervals (the "normalized" form) and a decision is
made in two steps: (1) is the version inside an interval, (2) does the ecosystem's
prerelease gate let it through. Standard library only, Python 3.10+, no network access.
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, Sequence

__version__ = "0.1.0"

ECOSYSTEMS = ("npm", "cargo", "pypi", "composer", "maven")
EXIT_OK, EXIT_NO_MATCH, EXIT_INVALID, EXIT_UNSUPPORTED = 0, 1, 2, 3

# --------------------------------------------------------------------------- messages
# All user-visible text lives in this table (en and ko must keep the same keys and the
# same {placeholders}; tests/test_i18n.py enforces that). JSON keys are never translated.
MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "help_desc": "Decide version ranges the way each package ecosystem does "
                     "(npm, cargo, pypi, composer, maven). Offline, standard library only.",
        "help_check": "is VERSION inside RANGE? (interval step + prerelease gate step)",
        "help_best": "which candidate version would be picked for RANGE?",
        "help_intersect": "do two ranges overlap? shows the shared interval",
        "help_explain": "show what RANGE means as exact intervals",
        "help_eco": "package ecosystem: npm | cargo | pypi | composer | maven",
        "help_range": "range string as written in the manifest, e.g. \"^0.2.3\"",
        "help_range2": "second range string",
        "help_version": "the version to test",
        "help_versions": "candidate versions (also accepts --from)",
        "help_from": "file with one candidate version per line ('-' reads stdin; blank lines and # comments ignored)",
        "help_json": "print one JSON object (keys are always English) instead of text",
        "help_lang": "language of explanations: en | ko (default: RANGEWISE_LANG, then LC_ALL/LC_MESSAGES/LANG, else en)",
        "help_exit_status": "also reflect the verdict in the exit code (1 = no match / no pick / no overlap)",
        "help_pre_policy": "pypi only: install = what pip picks and packaging<=24.2 contains(); "
                           "membership = packaging>=26 contains() (default: install)",
        "help_include_pre": "npm and cargo only: skip the prerelease gate (node-semver includePrerelease)",
        "help_min_stab": "composer only: minimum-stability (default: stable)",
        "err_empty_range": "the range is empty",
        "err_bad_token": "cannot read '{tok}'",
        "err_bad_version": "cannot read '{tok}' as a version",
        "err_wildcard_op": "a '.*' wildcard only works with == and !=",
        "err_tilde_short": "~= needs at least two release segments (for example ~=1.4)",
        "err_reversed": "the lower bound is above the upper bound",
        "err_maven_syntax": "malformed interval notation near '{tok}'",
        "err_no_operator": "'{tok}' has no operator (use == for an exact version)",
        "err_no_candidates": "no candidate versions given (pass them as arguments or with --from FILE)",
        "err_file_missing": "cannot read candidate file '{path}' - check the path",
        "err_all_candidates_bad": "none of the candidate versions could be parsed",
        "err_number_too_long": "a numeric part is too long to read (Python limits integers to 4300 digits) - shorten it",
        "ap_usage": "usage: ",
        "ap_positionals": "positional arguments",
        "ap_options": "options",
        "ap_help": "show this help message and exit",
        "ap_version": "show the program's version number and exit",
        "ap_err_choice": "argument {arg}: invalid choice: {value} (choose from {choices})",
        "ap_err_required": "the following arguments are required: {names}",
        "ap_err_unrecognized": "unrecognized arguments: {args}",
        "ap_err_expected": "argument {arg}: expected one argument",
        "ap_err_other": "{message}",
        "err_not_utf8": "candidate input '{path}' is not UTF-8 text - save it as UTF-8",
        "err_opt_eco": "option {opt} applies to {ecos} only, not to {eco}",
        "unsupported_line": "rangewise: unsupported: {feature} in {eco} range '{range}' - not evaluated",
        "unsupported_hint": "This form needs information outside the range string; report it as not evaluated "
                            "instead of guessing.",
        "reason_matched": "matched",
        "reason_outside_interval": "outside every interval of the range",
        "reason_excluded_prerelease_gate": "inside an interval, but the prerelease gate excludes it",
        "reason_excluded_stability": "inside an interval, but below the minimum stability",
        "reason_soft_requirement": "soft requirement: Maven treats it as a preference, not a restriction",
        "rule_not_pre": "the version is not a prerelease",
        "rule_npm_gate": "a prerelease only matches when a comparator with a prerelease on the same "
                         "major.minor.patch is in the same AND-set",
        "rule_cargo_gate": "a prerelease only matches when a comparator with a prerelease on the same "
                           "major.minor.patch is in the same requirement",
        "rule_include_prerelease": "--include-prerelease: prereleases are not gated",
        "rule_pypi_install": "install policy: prereleases are skipped unless the specifier names a prerelease "
                             "(pip also falls back to them when nothing else matches)",
        "rule_pypi_membership": "membership policy: contains() does not gate prereleases (packaging>=26)",
        "rule_composer_stability": "a version below the minimum stability ({floor}) is skipped unless "
                                   "the constraint names that stability (@flag or a suffix)",
        "rule_maven_none": "Maven has no prerelease gate; qualifiers only change the sort order",
        "chk_head": "{eco} range `{range}` vs version {version}  [policy: {policy}]",
        "chk_in": "Step 1 - interval: {version} is inside {human}",
        "chk_out": "Step 1 - interval: {version} is outside {human}",
        "chk_gate_na": "Step 2 - prerelease gate: not applied ({rule})",
        "chk_gate_pass": "Step 2 - prerelease gate: passed ({rule})",
        "chk_gate_block": "Step 2 - prerelease gate: BLOCKED ({rule})",
        "chk_gate_skip": "Step 2 - prerelease gate: not evaluated (outside the interval)",
        "chk_yes": "Result: {version} matches `{range}`",
        "chk_no": "Result: {version} does NOT match `{range}` - {reason}",
        "chk_other_policy": "Under the other pypi policy ({other}) the answer would be: {answer}",
        "yes": "yes",
        "no": "no",
        "best_head": "{eco} range `{range}` over {count} candidate(s)  [policy: {policy}]",
        "best_line": "  {version}: {verdict}",
        "best_selected": "Picked: {version}",
        "best_none": "Nothing is picked: no candidate satisfies the range",
        "best_skipped": "Skipped (not a valid {eco} version): {version}",
        "best_other_policy": "Under the other pypi policy ({other}) the pick would be: {pick}",
        "best_soft": "Soft requirement: Maven prefers {pref} if it is available; any other version is allowed.",
        "none": "none",
        "isect_head": "{eco} ranges `{a}` and `{b}`",
        "isect_yes": "They overlap: {human}",
        "isect_no": "They do not overlap: no version satisfies both.",
        "isect_a": "  `{range}` = {human}",
        "isect_note": "Note: only the intervals are intersected; prerelease gates are not considered.",
        "exp_head": "{eco} range `{range}` means: {human}",
        "exp_exact": "Exact interval bounds: {exact}",
        "exp_rule": "Rule: {rule}",
        "note_maven_soft": "No brackets: this is a soft requirement (a preferred version), not a restriction.",
        "note_prefix_bounds": "Prefix and ~= bounds are shown without the .dev0 suffix.",
        "note_composer_flag": "The minimum stability for this check is {floor} (range flag or default).",
        "rule_summary_npm": "npm: ^ keeps the left-most non-zero part, ~ allows patch-level changes (minor when only "
                            "a major is given), x/* wildcards, A - B hyphen ranges, || is OR, space is AND; "
                            "prereleases need a same-version prerelease comparator.",
        "rule_summary_cargo": "cargo: a bare version is a caret requirement, ^ keeps the left-most non-zero part, "
                              "~ allows patch-level changes, comma is AND; prereleases need a same-version "
                              "prerelease comparator.",
        "rule_summary_pypi": "pypi (PEP 440): ~=1.4.2 means >=1.4.2,==1.4.*, ==1.4.* is a prefix match, < and > "
                             "exclude prereleases/post-releases of the bound, local versions are ignored unless "
                             "the specifier has one; prerelease handling depends on --pre-policy.",
        "rule_summary_composer": "composer: ~1.2 means >=1.2.0 <2.0.0 (unlike npm), ~1.2.3 means <1.3.0, ^ keeps the "
                                 "left-most non-zero part, a bare version is exact, space or comma is AND, "
                                 "|| or | is OR; stability is filtered by minimum-stability and @flags.",
        "rule_summary_maven": "maven: [a,b) intervals with () exclusive and [] inclusive, a comma joins interval "
                              "sets, plain 1.0 is a soft preference; qualifiers sort alpha < beta < milestone < rc < "
                              "snapshot < release < sp; there is no prerelease gate.",
        "err_prefix_invalid_range": "rangewise: error: invalid {eco} range '{range}': {detail}",
        "err_prefix_invalid_version": "rangewise: error: invalid {eco} version '{version}': {detail}",
        "err_prefix_generic": "rangewise: error: {detail}",
    },
    "ko": {
        "help_desc": "패키지 생태계(npm, cargo, pypi, composer, maven)마다 다른 버전 범위 규칙대로 판정합니다. "
                     "오프라인, 표준 라이브러리만 사용.",
        "help_check": "VERSION 이 RANGE 안에 들어가는지 확인 (구간 단계 + 사전 릴리스 게이트 단계)",
        "help_best": "RANGE 에서 후보 중 어떤 버전이 선택되는지 확인",
        "help_intersect": "두 범위가 겹치는지와 겹치는 구간을 확인",
        "help_explain": "RANGE 가 정확히 어떤 구간인지 설명",
        "help_eco": "패키지 생태계: npm | cargo | pypi | composer | maven",
        "help_range": "매니페스트에 적힌 범위 문자열 (예: \"^0.2.3\")",
        "help_range2": "두 번째 범위 문자열",
        "help_version": "확인할 버전",
        "help_versions": "후보 버전들 (--from 도 가능)",
        "help_from": "한 줄에 버전 하나인 파일 ('-' 는 표준 입력, 빈 줄과 # 주석은 무시)",
        "help_json": "텍스트 대신 JSON 하나를 출력 (키는 항상 영어)",
        "help_lang": "설명 언어: en | ko (기본: RANGEWISE_LANG, 다음 LC_ALL/LC_MESSAGES/LANG, 아니면 en)",
        "help_exit_status": "판정 결과를 종료 코드에도 반영 (1 = 불일치 / 선택 없음 / 겹침 없음)",
        "help_pre_policy": "pypi 전용: install = pip 이 고르는 방식·packaging 24.2 이하 contains(), "
                           "membership = packaging 26 이상 contains() (기본: install)",
        "help_include_pre": "npm·cargo 전용: 사전 릴리스 게이트를 건너뜀 (node-semver includePrerelease)",
        "help_min_stab": "composer 전용: minimum-stability (기본: stable)",
        "err_empty_range": "범위가 비어 있습니다",
        "err_bad_token": "'{tok}' 을(를) 읽을 수 없습니다",
        "err_bad_version": "'{tok}' 을(를) 버전으로 읽을 수 없습니다",
        "err_wildcard_op": "'.*' 와일드카드는 == 와 != 에서만 쓸 수 있습니다",
        "err_tilde_short": "~= 는 릴리스 자리가 두 개 이상 필요합니다 (예: ~=1.4)",
        "err_reversed": "하한이 상한보다 큽니다",
        "err_maven_syntax": "'{tok}' 근처의 구간 표기가 올바르지 않습니다",
        "err_no_operator": "'{tok}' 에 연산자가 없습니다 (정확한 버전은 == 를 사용)",
        "err_no_candidates": "후보 버전이 없습니다 (인자로 주거나 --from FILE 로 지정)",
        "err_file_missing": "후보 파일 '{path}' 을(를) 읽을 수 없습니다 - 경로를 확인하세요",
        "err_all_candidates_bad": "해석할 수 있는 후보 버전이 하나도 없습니다",
        "err_number_too_long": "숫자 부분이 너무 길어 읽을 수 없습니다 (정수는 4300자리까지) - 줄여 주세요",
        "ap_usage": "사용법: ",
        "ap_positionals": "위치 인자",
        "ap_options": "옵션",
        "ap_help": "도움말을 보여 주고 종료합니다",
        "ap_version": "프로그램 버전을 보여 주고 종료합니다",
        "ap_err_choice": "인자 {arg}: 잘못된 값 {value} (선택 가능: {choices})",
        "ap_err_required": "필수 인자가 없습니다: {names}",
        "ap_err_unrecognized": "알 수 없는 인자: {args}",
        "ap_err_expected": "인자 {arg}: 값이 하나 필요합니다",
        "ap_err_other": "인자 오류: {message}",
        "err_not_utf8": "후보 입력 '{path}' 이(가) UTF-8 텍스트가 아닙니다 - UTF-8 로 저장하세요",
        "err_opt_eco": "{opt} 옵션은 {ecos} 에만 쓸 수 있고 {eco} 에는 쓸 수 없습니다",
        "unsupported_line": "rangewise: 판정 불가: {eco} 범위 '{range}' 의 {feature} - 평가하지 않음",
        "unsupported_hint": "이 형식은 범위 문자열만으로는 판단할 수 없습니다. 추측하지 말고 평가하지 못했다고 보고하세요.",
        "reason_matched": "일치",
        "reason_outside_interval": "범위의 어떤 구간에도 들어가지 않음",
        "reason_excluded_prerelease_gate": "구간 안이지만 사전 릴리스 게이트에서 제외됨",
        "reason_excluded_stability": "구간 안이지만 최소 안정성(minimum-stability) 미달로 제외됨",
        "reason_soft_requirement": "소프트 요구: Maven 은 제한이 아니라 선호값으로 취급",
        "rule_not_pre": "사전 릴리스가 아닌 버전",
        "rule_npm_gate": "사전 릴리스는 같은 AND 묶음에 같은 major.minor.patch 의 사전 릴리스 비교자가 있어야 통과",
        "rule_cargo_gate": "사전 릴리스는 같은 요구 안에 같은 major.minor.patch 의 사전 릴리스 비교자가 있어야 통과",
        "rule_include_prerelease": "--include-prerelease: 사전 릴리스를 거르지 않음",
        "rule_pypi_install": "install 정책: 지정자가 사전 릴리스를 명시하지 않으면 건너뜀 "
                             "(다른 선택지가 없으면 pip 은 사전 릴리스로 되돌아감)",
        "rule_pypi_membership": "membership 정책: contains() 가 사전 릴리스를 거르지 않음 (packaging 26 이상)",
        "rule_composer_stability": "최소 안정성({floor}) 미만 버전은 제약이 그 안정성을 명시(@플래그 또는 접미사)해야 통과",
        "rule_maven_none": "Maven 에는 사전 릴리스 게이트가 없고 한정어는 정렬 순서만 바꿈",
        "chk_head": "{eco} 범위 `{range}` 와 버전 {version}  [정책: {policy}]",
        "chk_in": "1단계 - 구간: {version} 은(는) {human} 안에 있음",
        "chk_out": "1단계 - 구간: {version} 은(는) {human} 밖에 있음",
        "chk_gate_na": "2단계 - 사전 릴리스 게이트: 적용 안 함 ({rule})",
        "chk_gate_pass": "2단계 - 사전 릴리스 게이트: 통과 ({rule})",
        "chk_gate_block": "2단계 - 사전 릴리스 게이트: 차단됨 ({rule})",
        "chk_gate_skip": "2단계 - 사전 릴리스 게이트: 평가 안 함 (구간 밖)",
        "chk_yes": "결과: {version} 은(는) `{range}` 에 일치함",
        "chk_no": "결과: {version} 은(는) `{range}` 에 일치하지 않음 - {reason}",
        "chk_other_policy": "다른 pypi 정책({other})에서는 답이 달라집니다: {answer}",
        "yes": "예",
        "no": "아니오",
        "best_head": "{eco} 범위 `{range}`, 후보 {count}개  [정책: {policy}]",
        "best_line": "  {version}: {verdict}",
        "best_selected": "선택: {version}",
        "best_none": "선택되는 버전 없음: 범위를 만족하는 후보가 없음",
        "best_skipped": "건너뜀 (올바른 {eco} 버전이 아님): {version}",
        "best_other_policy": "다른 pypi 정책({other})에서는 선택이 달라집니다: {pick}",
        "best_soft": "소프트 요구: {pref} 이(가) 있으면 Maven 이 그것을 선호하고, 다른 버전도 허용됩니다.",
        "none": "없음",
        "isect_head": "{eco} 범위 `{a}` 와 `{b}`",
        "isect_yes": "겹칩니다: {human}",
        "isect_no": "겹치지 않습니다: 두 범위를 모두 만족하는 버전이 없습니다.",
        "isect_a": "  `{range}` = {human}",
        "isect_note": "참고: 구간만 교차시키며 사전 릴리스 게이트는 고려하지 않습니다.",
        "exp_head": "{eco} 범위 `{range}` 의 뜻: {human}",
        "exp_exact": "정확한 구간 경계: {exact}",
        "exp_rule": "규칙: {rule}",
        "note_maven_soft": "대괄호가 없으면 제한이 아니라 선호 버전을 뜻하는 소프트 요구입니다.",
        "note_prefix_bounds": "접두 일치와 ~= 경계는 .dev0 접미사 없이 표시합니다.",
        "note_composer_flag": "이 판정의 최소 안정성은 {floor} 입니다 (범위의 플래그 또는 기본값).",
        "rule_summary_npm": "npm: ^ 는 가장 왼쪽 0 아닌 자리를 고정, ~ 는 패치 변경만 허용(major 만 쓰면 minor 까지), "
                            "x/* 와일드카드, A - B 하이픈 범위, || 는 OR, 공백은 AND. "
                            "사전 릴리스는 같은 버전의 사전 릴리스 비교자가 있어야 통과합니다.",
        "rule_summary_cargo": "cargo: 맨 버전은 캐럿 요구, ^ 는 가장 왼쪽 0 아닌 자리를 고정, ~ 는 패치 변경만 허용, "
                              "쉼표는 AND. 사전 릴리스는 같은 버전의 사전 릴리스 비교자가 있어야 통과합니다.",
        "rule_summary_pypi": "pypi (PEP 440): ~=1.4.2 는 >=1.4.2,==1.4.*, ==1.4.* 는 접두 일치, < 와 > 는 경계 버전의 "
                             "사전 릴리스·post 릴리스를 제외, 지정자에 local 이 없으면 local 은 무시합니다. "
                             "사전 릴리스 처리는 --pre-policy 에 따릅니다.",
        "rule_summary_composer": "composer: ~1.2 는 >=1.2.0 <2.0.0 (npm 과 다름), ~1.2.3 은 <1.3.0, ^ 는 가장 왼쪽 "
                                 "0 아닌 자리를 고정, 맨 버전은 정확히 일치, 공백·쉼표는 AND, || 또는 | 는 OR. "
                                 "안정성은 minimum-stability 와 @플래그로 거릅니다.",
        "rule_summary_maven": "maven: [a,b) 구간은 ()가 제외, []가 포함, 쉼표는 구간 집합을 합침, 괄호 없는 1.0 은 소프트 "
                              "선호값. 한정어 순서는 alpha < beta < milestone < rc < snapshot < 정식 < sp 이고 "
                              "사전 릴리스 게이트는 없습니다.",
        "err_prefix_invalid_range": "rangewise: error: invalid {eco} range '{range}': {detail}",
        "err_prefix_invalid_version": "rangewise: error: invalid {eco} version '{version}': {detail}",
        "err_prefix_generic": "rangewise: error: {detail}",
    },
}

_LANG = "en"


def t(key: str, **kw: object) -> str:
    """Look a message up in the active language (falls back to English)."""
    text = MESSAGES.get(_LANG, MESSAGES["en"]).get(key) or MESSAGES["en"][key]
    return text.format(**kw) if kw else text


def resolve_lang(cli_value: str | None, environ: Mapping[str, str]) -> str:
    """--lang > RANGEWISE_LANG > LC_ALL > LC_MESSAGES > LANG; only Korean is not English."""
    if cli_value:
        return "ko" if cli_value.lower().startswith("ko") else "en"
    for name in ("RANGEWISE_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = (environ.get(name) or "").strip()
        if value:
            return "ko" if value.lower().startswith("ko") else "en"
    return "en"


# --------------------------------------------------------------------------- errors
class RangewiseError(Exception):
    """Base class; .code is the process exit code."""
    code = EXIT_INVALID


class InvalidRange(RangewiseError):
    def __init__(self, eco: str, text: str, key: str, **params: object) -> None:
        super().__init__(key)
        self.eco, self.text, self.key, self.params = eco, text, key, params

    def message(self) -> str:
        return t("err_prefix_invalid_range", eco=self.eco, range=self.text,
                 detail=t(self.key, **self.params))


class InvalidVersion(RangewiseError):
    def __init__(self, eco: str, text: str, key: str = "err_bad_version", **params: object) -> None:
        super().__init__(key)
        self.eco, self.text, self.key, self.params = eco, text, key, params
        self.params.setdefault("tok", text)

    def message(self) -> str:
        return t("err_prefix_invalid_version", eco=self.eco, version=self.text,
                 detail=t(self.key, **self.params))


class UsageError(RangewiseError):
    def __init__(self, key: str, **params: object) -> None:
        super().__init__(key)
        self.key, self.params = key, params

    def message(self) -> str:
        return t("err_prefix_generic", detail=t(self.key, **self.params))


class Unsupported(RangewiseError):
    code = EXIT_UNSUPPORTED

    def __init__(self, eco: str, text: str, feature: str) -> None:
        super().__init__(feature)
        self.eco, self.text, self.feature = eco, text, feature

    def message(self) -> str:
        # The first line has a fixed English shape so callers can grep it; Korean adds a second line.
        line = (f"rangewise: unsupported: {self.feature} in {self.eco} range '{self.text}' "
                "— not evaluated")
        if _LANG == "ko":
            line += "\n" + t("unsupported_line", eco=self.eco, range=self.text, feature=self.feature)
        return line + "\n" + t("unsupported_hint")


# --------------------------------------------------------------------------- versions
@functools.total_ordering
class Ver:
    """Base class: subclasses define _key() (a comparable tuple) and __str__."""

    def _key(self) -> tuple:
        raise NotImplementedError

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Ver) and self._key() == other._key()

    def __lt__(self, other: "Ver") -> bool:
        return self._key() < other._key()

    def __hash__(self) -> int:
        return hash(self._key())

    def human(self, upper_exclusive: bool = False) -> str:
        return str(self)


# ----- SemVer (npm, cargo)
_NUM = r"(?:0|[1-9]\d*)"
_SEMVER_RX = re.compile(
    rf"^[v=]*\s*({_NUM})\.({_NUM})\.({_NUM})"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z.-]+)?$")


class SemVer(Ver):
    def __init__(self, t3: Sequence[int], pre: Sequence[str] = ()) -> None:
        self.t = tuple(t3)
        self.pre = tuple(pre)

    @classmethod
    def parse(cls, text: str, eco: str = "npm") -> "SemVer":
        m = _SEMVER_RX.match(text.strip())
        if not m:
            raise InvalidVersion(eco, text)
        pre = tuple(m[4].split(".")) if m[4] else ()
        for ident in pre:
            if ident.isdigit() and len(ident) > 1 and ident[0] == "0":
                raise InvalidVersion(eco, text)
        return cls((int(m[1]), int(m[2]), int(m[3])), pre)

    def _key(self) -> tuple:
        if not self.pre:
            return (self.t, (1,))
        return (self.t, (0, tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in self.pre)))

    def __str__(self) -> str:
        return ".".join(map(str, self.t)) + ("-" + ".".join(self.pre) if self.pre else "")

    def human(self, upper_exclusive: bool = False) -> str:
        if upper_exclusive and self.pre == ("0",):
            return ".".join(map(str, self.t))
        return str(self)


# ----- PEP 440 (pypi)
_PEP_RX = re.compile(
    r"^\s*v?(?:(\d+)!)?(\d+(?:\.\d+)*)"
    r"(?:[-_.]?(a|b|rc|c|alpha|beta|pre|preview)[-_.]?(\d+)?)?"
    r"(?:-(\d+)|[-_.]?(post|rev|r)[-_.]?(\d+)?)?"
    r"(?:[-_.]?(dev)[-_.]?(\d+)?)?"
    r"(?:\+([a-z0-9]+(?:[-_.][a-z0-9]+)*))?\s*$", re.I)
_PRE_ALIAS = {"alpha": "a", "a": "a", "beta": "b", "b": "b", "c": "rc", "rc": "rc",
              "pre": "rc", "preview": "rc"}


class Pep440(Ver):
    def __init__(self, epoch: int, release: Sequence[int], pre: tuple[str, int] | None = None,
                 post: int | None = None, dev: int | None = None, local: str | None = None) -> None:
        self.epoch, self.release, self.pre, self.post, self.dev, self.local = (
            epoch, tuple(release), pre, post, dev, local)

    @classmethod
    def parse(cls, text: str) -> "Pep440":
        m = _PEP_RX.match(text)
        if not m:
            raise InvalidVersion("pypi", text)
        pre = (_PRE_ALIAS[m[3].lower()], int(m[4] or 0)) if m[3] else None
        post = int(m[5]) if m[5] else (int(m[7] or 0) if m[6] else None)
        dev = int(m[9] or 0) if m[8] else None
        local = ".".join(re.split(r"[-_.]", m[10].lower())) if m[10] else None
        return cls(int(m[1] or 0), [int(x) for x in m[2].split(".")], pre, post, dev, local)

    @property
    def is_pre(self) -> bool:
        return self.pre is not None or self.dev is not None

    def trimmed(self) -> tuple[int, ...]:
        rel = list(self.release)
        while len(rel) > 1 and rel[-1] == 0:
            rel.pop()
        return tuple(rel)

    def base(self) -> tuple:
        return (self.epoch, self.trimmed())

    def _key(self) -> tuple:
        if self.pre is None and self.post is None and self.dev is not None:
            pre: tuple = (-1, "", 0)
        elif self.pre is None:
            pre = (1, "", 0)
        else:
            pre = (0,) + self.pre
        post = (-1,) if self.post is None else (0, self.post)
        dev = (1,) if self.dev is None else (0, self.dev)
        if self.local is None:
            local: tuple = ((-1,),)
        else:
            local = tuple((1, int(p), "") if p.isdigit() else (0, 0, p) for p in self.local.split("."))
        return (self.epoch, self.trimmed(), pre, post, dev, local)

    def public(self) -> "Pep440":
        return Pep440(self.epoch, self.release, self.pre, self.post, self.dev, None)

    def __str__(self) -> str:
        s = (f"{self.epoch}!" if self.epoch else "") + ".".join(map(str, self.release))
        if self.pre:
            s += f"{self.pre[0]}{self.pre[1]}"
        if self.post is not None:
            s += f".post{self.post}"
        if self.dev is not None:
            s += f".dev{self.dev}"
        return s + (f"+{self.local}" if self.local else "")


# ----- Composer
_COMPOSER_RANK = {"dev": 0, "alpha": 1, "beta": 2, "rc": 3, "stable": 4, "patch": 5}
_COMPOSER_RX = re.compile(
    r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?"
    r"(?:[._-]?(stable|beta|b|rc|alpha|a|patch|pl|p)[.-]?(\d+(?:[.-]?\d+)*)?)?"
    r"(?:[.-]?(dev))?(?:\+.*)?$", re.I)
_COMPOSER_ALIAS = {"stable": "stable", "beta": "beta", "b": "beta", "rc": "rc", "alpha": "alpha",
                   "a": "alpha", "patch": "patch", "pl": "patch", "p": "patch"}


class ComposerVer(Ver):
    def __init__(self, nums: Sequence[int], stab: str = "stable", num: int | None = None) -> None:
        self.nums = tuple((list(nums) + [0, 0, 0, 0])[:4])
        self.stab = stab
        self.num = num

    @classmethod
    def parse(cls, text: str) -> "ComposerVer":
        m = _COMPOSER_RX.match(text.strip())
        if not m:
            raise InvalidVersion("composer", text)
        nums = [int(g) for g in m.groups()[:4] if g is not None]
        stab, num = "stable", None
        if m[5]:
            stab = _COMPOSER_ALIAS[m[5].lower()]
            digits = re.findall(r"\d+", m[6] or "")
            num = int(digits[0]) if digits else None
        if m[7]:
            stab, num = "dev", (num if m[5] else None)
        return cls(nums, stab, num)

    @property
    def rank(self) -> int:
        return _COMPOSER_RANK[self.stab]

    def _key(self) -> tuple:
        return (self.nums, self.rank, -1 if self.num is None else self.num)

    def __str__(self) -> str:
        nums = list(self.nums)
        if nums[3] == 0:
            nums.pop()
        s = ".".join(map(str, nums))
        if self.stab != "stable":
            s += "-" + self.stab + ("" if self.num is None else str(self.num))
        return s

    def human(self, upper_exclusive: bool = False) -> str:
        if upper_exclusive and self.stab == "dev" and self.num is None:
            return str(ComposerVer(self.nums))
        return str(self)


# ----- Maven ComparableVersion (clean-room from the documented algorithm)
_MAVEN_QUALIFIERS = ["alpha", "beta", "milestone", "rc", "snapshot", "", "sp"]
_MAVEN_ALIASES = {"ga": "", "final": "", "release": "", "cr": "rc"}


def _mvn_qualifier(value: str, followed_by_digit: bool) -> str:
    if followed_by_digit and len(value) == 1:
        value = {"a": "alpha", "b": "beta", "m": "milestone"}.get(value, value)
    return _MAVEN_ALIASES.get(value, value)


def _mvn_comparable(q: str) -> str:
    if q in _MAVEN_QUALIFIERS:
        return str(_MAVEN_QUALIFIERS.index(q))
    return f"{len(_MAVEN_QUALIFIERS)}-{q}"


_MVN_RELEASE = str(_MAVEN_QUALIFIERS.index(""))


class _MvnInt:
    def __init__(self, n: int) -> None:
        self.n = n

    def is_null(self) -> bool:
        return self.n == 0


class _MvnStr:
    def __init__(self, q: str) -> None:
        self.q = q

    def is_null(self) -> bool:
        return _mvn_comparable(self.q) == _MVN_RELEASE


class _MvnList(list):
    def is_null(self) -> bool:
        return len(self) == 0


def _mvn_cmp(a: object, b: object) -> int:
    """Compare two items; b may be None (meaning 'missing', equal to a null item)."""
    if isinstance(a, _MvnInt):
        if b is None:
            return 0 if a.n == 0 else 1
        if isinstance(b, _MvnInt):
            return (a.n > b.n) - (a.n < b.n)
        return 1
    if isinstance(a, _MvnStr):
        if b is None:
            x, y = _mvn_comparable(a.q), _MVN_RELEASE
            return (x > y) - (x < y)
        if isinstance(b, _MvnInt):
            return -1
        if isinstance(b, _MvnStr):
            x, y = _mvn_comparable(a.q), _mvn_comparable(b.q)
            return (x > y) - (x < y)
        return -1
    # a is a list
    if b is None:
        return 0 if len(a) == 0 else _mvn_cmp(a[0], None)  # type: ignore[index, arg-type]
    if isinstance(b, _MvnInt):
        return -1
    if isinstance(b, _MvnStr):
        return 1
    for i in range(max(len(a), len(b))):  # type: ignore[arg-type]
        left = a[i] if i < len(a) else None  # type: ignore[arg-type, index]
        right = b[i] if i < len(b) else None  # type: ignore[arg-type, index]
        if left is None:
            result = 0 if right is None else -_mvn_cmp(right, None)
        else:
            result = _mvn_cmp(left, right)
        if result:
            return result
    return 0


def _mvn_normalize(items: _MvnList) -> None:
    for i in range(len(items) - 1, -1, -1):
        last = items[i]
        if last.is_null():
            del items[i]
        elif not isinstance(last, _MvnList):
            break


def _mvn_parse_item(is_digit: bool, text: str, followed_by_digit: bool = False) -> object:
    if is_digit:
        return _MvnInt(int(text))
    return _MvnStr(_mvn_qualifier(text, followed_by_digit))


class MavenVer(Ver):
    _RX_OK = re.compile(r"^[^\s\[\]()\",]+$")

    def __init__(self, text: str) -> None:
        self.text = text
        self.items = self._parse(text.lower())

    @classmethod
    def parse(cls, text: str) -> "MavenVer":
        text = text.strip()
        if not text or not cls._RX_OK.match(text):
            raise InvalidVersion("maven", text)
        return cls(text)

    @staticmethod
    def _parse(version: str) -> _MvnList:
        root = _MvnList()
        cur = root
        stack = [cur]
        is_digit = False
        start = 0
        after_dot = False  # the token being read followed a '.'

        def token(i: int) -> object:
            item = _mvn_parse_item(is_digit, version[start:i])
            # the Maven version-order spec: ".qualifier" sorts like "-qualifier"
            return _MvnList([item]) if (after_dot and not is_digit) else item

        for i, c in enumerate(version):
            if c == ".":
                cur.append(_MvnInt(0) if i == start else token(i))
                start = i + 1
                after_dot = True
            elif c in "-_":
                cur.append(_MvnInt(0) if i == start else token(i))
                start = i + 1
                after_dot = False
                nxt = _MvnList()
                cur.append(nxt)
                cur = nxt
                stack.append(cur)
            elif c.isdigit():
                if not is_digit and i > start:
                    cur.append(_mvn_parse_item(False, version[start:i], True))
                    start = i
                    after_dot = False
                    nxt = _MvnList()
                    cur.append(nxt)
                    cur = nxt
                    stack.append(cur)
                is_digit = True
            else:
                if is_digit and i > start:
                    cur.append(_mvn_parse_item(True, version[start:i]))
                    start = i
                    after_dot = False
                    nxt = _MvnList()
                    cur.append(nxt)
                    cur = nxt
                    stack.append(cur)
                is_digit = False
        if len(version) > start:
            cur.append(token(len(version)))
        while stack:
            _mvn_normalize(stack.pop())
        return root

    def _cmp(self, other: "MavenVer") -> int:
        return _mvn_cmp(self.items, other.items)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, MavenVer) and self._cmp(other) == 0

    def __lt__(self, other: "Ver") -> bool:
        return isinstance(other, MavenVer) and self._cmp(other) < 0

    def __hash__(self) -> int:
        return hash(str(self.items))

    def __str__(self) -> str:
        return self.text


# --------------------------------------------------------------------------- intervals
@dataclass(frozen=True)
class Interval:
    lower: Ver | None = None
    lower_inc: bool = False
    upper: Ver | None = None
    upper_inc: bool = False

    def contains(self, v: Ver) -> bool:
        if self.lower is not None and (v < self.lower or (v == self.lower and not self.lower_inc)):
            return False
        if self.upper is not None and (self.upper < v or (v == self.upper and not self.upper_inc)):
            return False
        return True

    def is_empty(self) -> bool:
        if self.lower is None or self.upper is None:
            return False
        if self.upper < self.lower:
            return True
        return self.lower == self.upper and not (self.lower_inc and self.upper_inc)

    def intersect(self, o: "Interval") -> "Interval":
        if self.lower is None:
            lo, li = o.lower, o.lower_inc
        elif o.lower is None:
            lo, li = self.lower, self.lower_inc
        elif self.lower == o.lower:
            lo, li = self.lower, self.lower_inc and o.lower_inc
        else:
            lo, li = (self.lower, self.lower_inc) if self.lower > o.lower else (o.lower, o.lower_inc)
        if self.upper is None:
            hi, ui = o.upper, o.upper_inc
        elif o.upper is None:
            hi, ui = self.upper, self.upper_inc
        elif self.upper == o.upper:
            hi, ui = self.upper, self.upper_inc and o.upper_inc
        else:
            hi, ui = (self.upper, self.upper_inc) if self.upper < o.upper else (o.upper, o.upper_inc)
        return Interval(lo, li, hi, ui)

    def to_json(self) -> dict:
        return {"lower": None if self.lower is None else str(self.lower),
                "lower_inclusive": self.lower_inc,
                "upper": None if self.upper is None else str(self.upper),
                "upper_inclusive": self.upper_inc}

    def human(self) -> str:
        if self.lower is None and self.upper is None:
            return "*"
        if (self.lower is not None and self.upper is not None and self.lower == self.upper
                and self.lower_inc and self.upper_inc):
            return f"={self.lower.human()}"
        parts = []
        if self.lower is not None:
            parts.append((">=" if self.lower_inc else ">") + self.lower.human())
        if self.upper is not None:
            parts.append(("<=" if self.upper_inc else "<") + self.upper.human(not self.upper_inc))
        return " ".join(parts)

    def exact(self) -> str:
        lo = "-inf" if self.lower is None else str(self.lower)
        hi = "+inf" if self.upper is None else str(self.upper)
        return f"{'[' if self.lower_inc and self.lower is not None else '('}{lo}, {hi}" \
               f"{']' if self.upper_inc and self.upper is not None else ')'}"


def intersect_lists(a: Sequence[Interval], b: Sequence[Interval]) -> list[Interval]:
    out = []
    for x in a:
        for y in b:
            z = x.intersect(y)
            if not z.is_empty():
                out.append(z)
    return out


def op_intervals(op: str, v: Ver) -> list[Interval]:
    if op == "*":
        return [Interval()]
    if op == "=":
        return [Interval(v, True, v, True)]
    if op == ">":
        return [Interval(lower=v)]
    if op == ">=":
        return [Interval(lower=v, lower_inc=True)]
    if op == "<":
        return [Interval(upper=v)]
    if op == "<=":
        return [Interval(upper=v, upper_inc=True)]
    if op == "!=":
        return [Interval(upper=v), Interval(lower=v)]
    raise ValueError(op)


def human_intervals(ivs: Sequence[Interval]) -> str:
    return " || ".join(i.human() for i in ivs) if ivs else "<empty>"


def exact_intervals(ivs: Sequence[Interval]) -> str:
    return " U ".join(i.exact() for i in ivs) if ivs else "<empty>"


# --------------------------------------------------------------------------- verdicts
@dataclass
class Verdict:
    in_interval: bool
    gate_applies: bool
    gate_passed: bool | None
    gate_rule: str          # key suffix of a rule_* message
    matches: bool
    reason: str             # matched | outside_interval | excluded_prerelease_gate | ...
    rule_params: dict | None = None


class Range:
    """Parsed range: .intervals is the normalized form, evaluate() decides one version."""
    eco = ""
    policy = ""

    def __init__(self, text: str, intervals: list[Interval]) -> None:
        self.text = text
        self.intervals = intervals
        self.notes: list[str] = []

    def parse_version(self, text: str) -> Ver:
        raise NotImplementedError

    def evaluate(self, v: Ver) -> Verdict:
        raise NotImplementedError

    def with_policy(self, policy: str) -> "Range":
        return self


# --------------------------------------------------------------------------- npm / cargo
_PART_RX = re.compile(
    r"^[v=]*(\d+|[xX*])(?:\.(\d+|[xX*]))?(?:\.(\d+|[xX*]))?"
    r"(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")
_ANYX = ("", "*", "x", "X")


def _partial(eco: str, text: str, whole: str, bare: bool = False) -> tuple[list[int], tuple[str, ...]]:
    m = _PART_RX.match(text)
    if not m:
        _raise_semver_token(eco, whole, text, bare)
    nums: list[int] = []
    for g in m.groups()[:3]:
        if g is None or g in ("x", "X", "*"):
            break
        nums.append(int(g))
    pre = tuple(m[4].split(".")) if m[4] and len(nums) == 3 else ()
    return nums, pre


def _raise_semver_token(eco: str, whole: str, tok: str, bare: bool) -> None:
    if ":" in tok or tok.startswith(("git", "http")) or "/" in tok:
        feature = tok.split(":")[0] + ":" if ":" in tok else "git or path source"
        raise Unsupported(eco, whole, feature)
    if eco == "npm" and bare and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", tok):
        raise Unsupported(eco, whole, "dist-tag")
    raise InvalidRange(eco, whole, "err_bad_token", tok=tok)


def _bump(nums: Sequence[int], idx: int, width: int = 3) -> list[int]:
    out = list(nums[: idx + 1]) + [0] * (width - idx - 1)
    out[idx] += 1
    return out


def _caret_index(nums: Sequence[int]) -> int:
    return next((i for i, n in enumerate(nums[:3]) if n != 0), len(nums) - 1)


def _semver_comparators(tok: str, eco: str, whole: str) -> list[tuple[str, SemVer]]:
    m = re.match(r"^(\^|~>|~|>=|<=|>|<|=)?(.*)$", tok)
    op, rest = m[1] or "", m[2]
    if eco == "cargo" and op == "~>":
        raise InvalidRange(eco, whole, "err_bad_token", tok=tok)
    zero = SemVer((0, 0, 0))
    if rest in _ANYX:
        if op in (">", "<"):
            return [("<", SemVer((0, 0, 0), ("0",)))]
        return [("*", zero)]
    nums, pre = _partial(eco, rest, whole, bare=(op == ""))
    lo = SemVer(nums + [0] * (3 - len(nums)), pre)
    upper_pre = ("0",) if eco == "npm" else ()
    if op == "" and eco == "cargo":
        op = "=" if re.search(r"[xX*]", rest) else "^"
    if op in ("", "=") and len(nums) < 3:
        if not nums:
            return [("*", zero)]
        return [(">=", lo), ("<", SemVer(_bump(nums, len(nums) - 1), upper_pre))]
    if op in ("", "="):
        return [("=", lo)]
    if not nums:
        return [("*", zero)]
    if op in ("~", "~>"):
        idx = 0 if len(nums) == 1 else 1
        return [(">=", lo), ("<", SemVer(_bump(nums, idx), upper_pre))]
    if op == "^":
        return [(">=", lo), ("<", SemVer(_bump(nums, _caret_index(nums)), upper_pre))]
    if len(nums) < 3:
        if op == ">":
            return [(">=", SemVer(_bump(nums, len(nums) - 1)))]
        if op == "<=":
            return [("<", SemVer(_bump(nums, len(nums) - 1), upper_pre))]
        if op == "<":
            return [("<", SemVer(nums + [0] * (3 - len(nums)), upper_pre))]
        return [(">=", lo)]
    return [(op, lo)]


def _semver_alternatives(text: str, eco: str) -> list[list[tuple[str, SemVer]]]:
    if not text.strip() and eco != "npm":  # node-semver treats an empty range as '*'
        raise InvalidRange(eco, text, "err_empty_range")
    out = []
    for alt in (text.split("||") if eco == "npm" else [text]):
        alt = alt.strip()
        if eco == "cargo" and alt == "":
            raise InvalidRange(eco, text, "err_bad_token", tok=",")
        hy = re.match(r"^(\S+)\s+-\s+(\S+)$", alt) if eco == "npm" else None
        comps: list[tuple[str, SemVer]] = []
        if hy:
            lo_n, lo_p = _partial(eco, hy[1], text)
            comps.append((">=", SemVer(lo_n + [0] * (3 - len(lo_n)), lo_p)))
            hi_n, hi_p = _partial(eco, hy[2], text)
            if len(hi_n) == 3:
                comps.append(("<=", SemVer(hi_n, hi_p)))
            elif hi_n:
                comps.append(("<", SemVer(_bump(hi_n, len(hi_n) - 1), ("0",))))
        else:
            alt = re.sub(r"(\^|~>|~|>=|<=|>|<|=)\s+", r"\1", alt)
            toks = [x for x in re.split(r"[\s,]+", alt) if x] if eco == "cargo" else alt.split()
            if eco == "cargo" and (alt.startswith(",") or alt.endswith(",") or ",," in alt):
                raise InvalidRange(eco, text, "err_bad_token", tok=",")
            for tok in toks or ["*"]:
                comps += _semver_comparators(tok, eco, text)
        out.append(comps)
    return out


class SemverRange(Range):
    def __init__(self, eco: str, text: str, include_pre: bool) -> None:
        self.eco = eco
        self.include_pre = include_pre
        self.policy = f"{eco}-include-prerelease" if include_pre else f"{eco}-default"
        self.alts = _semver_alternatives(text, eco)
        floor = SemVer((0, 0, 0), ("0",))  # the smallest SemVer; makes `<0.0.0-0` come out empty
        ivs: list[Interval] = []
        self.alt_intervals: list[list[Interval]] = []
        for comps in self.alts:
            cur = [Interval(floor, True)]
            for op, v in comps:
                cur = intersect_lists(cur, op_intervals(op, v))
            cur = [Interval(None if i.lower == floor and i.lower_inc else i.lower, i.lower_inc and
                            i.lower != floor, i.upper, i.upper_inc) for i in cur]
            self.alt_intervals.append(cur)
            ivs += cur
        super().__init__(text, ivs)

    def parse_version(self, text: str) -> Ver:
        return SemVer.parse(text, self.eco)

    def evaluate(self, v: Ver) -> Verdict:
        assert isinstance(v, SemVer)
        gate_key = f"{self.eco}_gate"
        in_iv = any(i.contains(v) for i in self.intervals)
        applies = bool(v.pre) and not self.include_pre
        if not applies:
            rule = "include_prerelease" if (v.pre and self.include_pre) else "not_pre"
            return Verdict(in_iv, False, True, rule, in_iv, "matched" if in_iv else "outside_interval")
        if not in_iv:
            return Verdict(False, True, None, gate_key, False, "outside_interval")
        for comps, cur in zip(self.alts, self.alt_intervals):
            if any(i.contains(v) for i in cur) and any(c.pre and c.t == v.t for _, c in comps):
                return Verdict(True, True, True, gate_key, True, "matched")
        return Verdict(True, True, False, gate_key, False, "excluded_prerelease_gate")


# --------------------------------------------------------------------------- pypi
_SPEC_RX = re.compile(r"^\s*(===|~=|==|!=|<=|>=|<|>)\s*(\S+)\s*$")
_NAME_RX = re.compile(r"^\s*[A-Za-z0-9][A-Za-z0-9._-]*\s*(?:\[[^\]]*\])?\s*(?=[~=!<>(])")


def _pep_specs(text: str) -> list[tuple[str, str]]:
    s = text.strip()
    if ";" in s:
        raise Unsupported("pypi", text, "environment marker")
    if re.search(r"@\s*\S", s) or "://" in s:
        raise Unsupported("pypi", text, "direct URL reference")
    s = _NAME_RX.sub("", s, count=1).strip()
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
    out = []
    for part in [p for p in s.split(",") if p.strip()]:
        m = _SPEC_RX.match(part)
        if not m:
            if re.match(r"^\s*\d", part):
                raise InvalidRange("pypi", text, "err_no_operator", tok=part.strip())
            raise InvalidRange("pypi", text, "err_bad_token", tok=part.strip())
        op, spec = m[1], m[2]
        if spec.endswith(".*"):
            if op not in ("==", "!="):
                raise InvalidRange("pypi", text, "err_wildcard_op")
            if not re.fullmatch(r"(?:\d+!)?\d+(?:\.\d+)*", spec[:-2]):
                raise InvalidRange("pypi", text, "err_bad_token", tok=spec)
        elif op != "===":
            try:
                Pep440.parse(spec)
            except InvalidVersion:
                raise InvalidRange("pypi", text, "err_bad_version", tok=spec) from None
        if op == "~=" and len(Pep440.parse(spec).release) < 2:
            raise InvalidRange("pypi", text, "err_tilde_short")
        out.append((op, spec))
    return out


def _prefix_version(spec: str) -> Pep440:
    return Pep440.parse(spec[:-2])


def _pep_bump_prefix(v: Pep440, keep: int) -> Pep440:
    rel = list(v.release[:keep])
    rel[-1] += 1
    return Pep440(v.epoch, rel)


def _pep_spec_intervals(op: str, spec: str) -> list[Interval]:
    if op == "===":
        try:
            p = Pep440.parse(spec)
        except InvalidVersion:
            return [Interval()]
        return [Interval(p, True, p, True)]
    if spec.endswith(".*"):
        lo = _prefix_version(spec)
        hi = _pep_bump_prefix(lo, len(lo.release))
        if op == "==":
            return [Interval(lo, True, hi, False)]
        return [Interval(upper=lo), Interval(lower=hi, lower_inc=True)]
    v = Pep440.parse(spec)
    if op == "~=":
        return [Interval(v, True, _pep_bump_prefix(v, len(v.release) - 1), False)]
    return op_intervals("=" if op == "==" else op, v)


def _pep_one(op: str, spec: str, v: Pep440, modern: bool = False) -> bool:
    if op == "===":
        return str(v) == spec.lower()
    if op == "~=":
        s = Pep440.parse(spec)
        prefix = ".".join(map(str, s.release[:-1])) + ".*"
        if s.epoch:
            prefix = f"{s.epoch}!" + prefix
        return _pep_one(">=", spec, v, modern) and _pep_one("==", prefix, v, modern)
    if op in ("==", "!=") and spec.endswith(".*"):
        pref_v = _prefix_version(spec)
        pref = list(pref_v.release)
        rel = list(v.release) + [0] * max(0, len(pref) - len(v.release))
        hit = pref_v.epoch == v.epoch and rel[: len(pref)] == pref
        return hit if op == "==" else not hit
    s = Pep440.parse(spec)
    vv = v if s.local else v.public()
    if op == "==":
        return vv == s
    if op == "!=":
        return vv != s
    if op == ">=":
        return vv >= s
    if op == "<=":
        return vv <= s
    if modern:  # packaging >= 26 (bounds based): the bound moves instead of special-casing versions
        if op == "<":
            bound = s if s.is_pre else Pep440(s.epoch, s.release, s.pre, s.post, 0)
            return vv < bound
        if s.dev is not None or s.post is not None:
            return vv > s
        same_family = (vv.epoch == s.epoch and vv.trimmed() == s.trimmed() and vv.pre == s.pre
                       and (vv.post is not None or vv.dev is None))
        return vv > s and not same_family
    if op == "<":
        return vv < s and not (not s.is_pre and vv.is_pre and vv.base() == s.base())
    if v.local is not None and v.base() == s.base():
        return False
    return vv > s and not (s.post is None and vv.post is not None and vv.base() == s.base())


class PypiRange(Range):
    eco = "pypi"

    def __init__(self, text: str, policy: str = "install") -> None:
        self.specs = _pep_specs(text)
        self.pre_policy = policy
        self.policy = f"pypi-{policy}"
        ivs = [Interval()]
        for op, spec in self.specs:
            ivs = intersect_lists(ivs, _pep_spec_intervals(op, spec))
        super().__init__(text, ivs)
        if any(s.endswith(".*") or op == "~=" for op, s in self.specs):
            self.notes.append(t("note_prefix_bounds"))

    def with_policy(self, policy: str) -> "PypiRange":
        return PypiRange(self.text, policy)

    def parse_version(self, text: str) -> Ver:
        return Pep440.parse(text)

    def names_prerelease(self) -> bool:
        for op, spec in self.specs:
            if op in ("==", ">=", "<=", "~=", "===", ">", "<"):
                base = spec[:-2] if spec.endswith(".*") else spec
                try:
                    if Pep440.parse(base).is_pre:
                        return True
                except InvalidVersion:  # === may carry an arbitrary string
                    continue
        return False

    def evaluate(self, v: Ver) -> Verdict:
        assert isinstance(v, Pep440)
        modern = self.pre_policy == "membership"
        in_iv = all(_pep_one(op, s, v, modern) for op, s in self.specs)
        if not v.is_pre:
            return Verdict(in_iv, False, True, "not_pre", in_iv, "matched" if in_iv else "outside_interval")
        rule = f"pypi_{self.pre_policy}"
        if self.pre_policy == "membership":
            return Verdict(in_iv, False, True, rule, in_iv, "matched" if in_iv else "outside_interval")
        if not in_iv:
            return Verdict(False, True, None, rule, False, "outside_interval")
        if self.names_prerelease():
            return Verdict(True, True, True, rule, True, "matched")
        return Verdict(True, True, False, rule, False, "excluded_prerelease_gate")


# --------------------------------------------------------------------------- composer
_STAB_NAMES = {"stable": "stable", "rc": "rc", "beta": "beta", "alpha": "alpha", "dev": "dev"}


class ComposerRange(Range):
    eco = "composer"

    def __init__(self, text: str, min_stability: str = "stable") -> None:
        self.min_stability = min_stability.lower() if min_stability.lower() in _STAB_NAMES else "stable"
        self.policy = f"composer-min-stability={self.min_stability}"
        s = text.strip()
        if not s:
            raise InvalidRange("composer", text, "err_empty_range")
        if re.search(r"\bas\b", s) or re.search(r"(^|[\s|,])dev-", s) or re.search(r"\.x-dev\b", s):
            raise Unsupported("composer", text, "branch or alias constraint")
        flags = [m.lower() for m in re.findall(r"@(stable|rc|beta|alpha|dev)\b", s, re.I)]
        if re.search(r"@(?!stable|rc|beta|alpha|dev)\w", s, re.I):
            raise InvalidRange("composer", text, "err_bad_token", tok=re.search(r"@\w+", s)[0])  # type: ignore[index]
        s = re.sub(r"@\w+", "", s)
        self.named: list[ComposerVer] = []
        ivs: list[Interval] = []
        for alt in re.split(r"\s*\|\|?\s*", s):
            alt = alt.strip()
            ivs += self._alt(alt, text)
        super().__init__(text, ivs)
        ranks = [_COMPOSER_RANK[f] for f in flags] + [v.rank for v in self.named if v.rank < 4]
        self.floor_rank = min([_COMPOSER_RANK[self.min_stability]] + ranks)
        self.floor_name = next(n for n, r in _COMPOSER_RANK.items() if r == self.floor_rank)
        if self.floor_rank != _COMPOSER_RANK[self.min_stability] or flags:
            self.notes.append(t("note_composer_flag", floor=self.floor_name))

    def _ver(self, tok: str, whole: str) -> ComposerVer:
        try:
            return ComposerVer.parse(tok)
        except InvalidVersion:
            if re.fullmatch(r"[A-Za-z][\w.-]*", tok):
                raise Unsupported("composer", whole, "branch or alias constraint") from None
            raise InvalidRange("composer", whole, "err_bad_token", tok=tok) from None

    def _alt(self, alt: str, whole: str) -> list[Interval]:
        if alt in ("", "*", "x", "X"):
            return [Interval()]
        hy = re.match(r"^(\S+)\s+-\s+(\S+)$", alt)
        if hy:
            lo = self._ver(hy[1], whole)
            self.named += [lo] if lo.stab != "stable" else []
            parts = [int(x) for x in re.match(r"^v?(\d+(?:\.\d+)*)", hy[2]).group(1).split(".")] \
                if re.match(r"^v?\d", hy[2]) else []
            if len(parts) < 3 and "-" not in hy[2]:
                up = Interval(lower=lo, lower_inc=True,
                              upper=ComposerVer(_bump(parts, len(parts) - 1, 4), "dev"))
            else:
                hi = self._ver(hy[2], whole)
                up = Interval(lower=lo, lower_inc=True, upper=hi, upper_inc=True)
            return [up]
        alt = re.sub(r"(\^|~>|~|>=|<=|<>|!=|==|=|>|<)\s+", r"\1", alt)
        cur = [Interval()]
        for tok in [x for x in re.split(r"[\s,]+", alt) if x]:
            cur = intersect_lists(cur, self._token(tok, whole))
        return cur

    def _token(self, tok: str, whole: str) -> list[Interval]:
        m = re.match(r"^(\^|~>|~|>=|<=|<>|!=|==|=|>|<)?(.*)$", tok)
        op, rest = m[1] or "", m[2]
        if rest in ("*", "x", "X", ""):
            return [Interval()]
        wm = re.match(r"^v?(\d+(?:\.\d+){0,2})\.[*xX]$", rest)
        if wm and not op:
            parts = [int(x) for x in wm[1].split(".")]
            return [Interval(ComposerVer(parts, "dev"), True, ComposerVer(_bump(parts, len(parts) - 1, 4), "dev"))]
        v = self._ver(rest, whole)
        if v.stab != "stable":
            self.named.append(v)
        nums = [int(x) for x in re.match(r"^v?(\d+(?:\.\d+)*)", rest).group(1).split(".")]  # type: ignore[union-attr]
        if op == "~" or op == "~>":
            idx = max(0, len(nums) - 2)
            return [Interval(v, True, ComposerVer(_bump(nums, idx, 4), "dev"))]
        if op == "^":
            return [Interval(v, True, ComposerVer(_bump(nums, _caret_index(nums), 4), "dev"))]
        if op in ("", "=", "=="):
            return [Interval(v, True, v, True)]
        if op in ("!=", "<>"):
            return op_intervals("!=", v)
        return op_intervals(op, v)

    def parse_version(self, text: str) -> Ver:
        v = ComposerVer.parse(text)
        return v

    def evaluate(self, v: Ver) -> Verdict:
        assert isinstance(v, ComposerVer)
        in_iv = any(i.contains(v) for i in self.intervals)
        params = {"floor": self.floor_name}
        if v.rank >= 4 or v.rank >= self.floor_rank:
            return Verdict(in_iv, v.rank < 4, True, "composer_stability" if v.rank < 4 else "not_pre",
                           in_iv, "matched" if in_iv else "outside_interval", params)
        if not in_iv:
            return Verdict(False, True, None, "composer_stability", False, "outside_interval", params)
        return Verdict(True, True, False, "composer_stability", False, "excluded_stability", params)


# --------------------------------------------------------------------------- maven
_MVN_SET_RX = re.compile(r"\s*([\[(])\s*([^,\[\]()]*?)\s*(?:(,)\s*([^,\[\]()]*?))?\s*([\])])\s*")


class MavenRange(Range):
    eco = "maven"
    policy = "maven-no-gate"

    def __init__(self, text: str) -> None:
        s = text.strip()
        if not s:
            raise InvalidRange("maven", text, "err_empty_range")
        if "${" in s:
            raise Unsupported("maven", text, "property reference ${...}")
        if s.upper() in ("LATEST", "RELEASE"):
            raise Unsupported("maven", text, f"meta version {s.upper()}")
        self.soft: MavenVer | None = None
        ivs: list[Interval] = []
        if s[0] not in "[(":
            if any(c in s for c in "[](),"):
                raise InvalidRange("maven", text, "err_maven_syntax", tok=s)
            self.soft = MavenVer.parse(s)
            ivs = [Interval()]
        else:
            pos = 0
            while pos < len(s):
                m = _MVN_SET_RX.match(s, pos)
                if not m:
                    raise InvalidRange("maven", text, "err_maven_syntax", tok=s[pos:])
                lo_b, lo, comma, hi, hi_b = m.groups()
                pos = m.end()
                if comma:
                    lo_v = MavenVer.parse(lo) if lo else None
                    hi_v = MavenVer.parse(hi) if hi else None
                    iv = Interval(lo_v, lo_b == "[", hi_v, hi_b == "]")
                    if lo_v is not None and hi_v is not None and hi_v < lo_v:
                        raise InvalidRange("maven", text, "err_reversed")
                else:
                    if not (lo_b == "[" and hi_b == "]" and lo):
                        raise InvalidRange("maven", text, "err_maven_syntax", tok=m.group(0).strip())
                    v = MavenVer.parse(lo)
                    iv = Interval(v, True, v, True)
                ivs.append(iv)
                if pos < len(s):
                    if s[pos] != ",":
                        raise InvalidRange("maven", text, "err_maven_syntax", tok=s[pos:])
                    pos += 1
                    if pos >= len(s):
                        raise InvalidRange("maven", text, "err_maven_syntax", tok=",")
        super().__init__(text, ivs)
        if self.soft is not None:
            self.notes.append(t("note_maven_soft"))

    def parse_version(self, text: str) -> Ver:
        return MavenVer.parse(text)

    def evaluate(self, v: Ver) -> Verdict:
        if self.soft is not None:
            return Verdict(True, False, True, "maven_none", True, "soft_requirement")
        in_iv = any(i.contains(v) for i in self.intervals)
        return Verdict(in_iv, False, True, "maven_none", in_iv, "matched" if in_iv else "outside_interval")


# --------------------------------------------------------------------------- options + dispatch
@dataclass
class Options:
    pre_policy: str | None = None
    include_prerelease: bool = False
    minimum_stability: str | None = None


def parse_range(eco: str, text: str, opts: Options | None = None) -> Range:
    try:
        return _parse_range(eco, text, opts)
    except ValueError:  # int() refuses absurdly long digit runs (4300+ digits)
        raise InvalidRange(eco, text[:60], "err_number_too_long") from None


def parse_version_of(rng: "Range", text: str) -> Ver:
    """rng.parse_version with huge numbers turned into the normal invalid-version error."""
    try:
        return rng.parse_version(text)
    except ValueError:
        raise InvalidVersion(rng.eco, text[:60], "err_number_too_long") from None


def _parse_range(eco: str, text: str, opts: Options | None = None) -> Range:
    opts = opts or Options()
    if eco in ("npm", "cargo"):
        return SemverRange(eco, text, opts.include_prerelease)
    if eco == "pypi":
        return PypiRange(text, opts.pre_policy or "install")
    if eco == "composer":
        return ComposerRange(text, opts.minimum_stability or "stable")
    if eco == "maven":
        return MavenRange(text)
    raise UsageError("err_bad_token", tok=eco)


def verdict_text(rng: Range, version: str, vd: Verdict) -> list[str]:
    human = human_intervals(rng.intervals)
    lines = [t("chk_head", eco=rng.eco, range=rng.text, version=version, policy=rng.policy)]
    lines.append(t("chk_in" if vd.in_interval else "chk_out", version=version, human=human))
    rule = t(f"rule_{vd.gate_rule}", **(vd.rule_params or {}))
    if vd.gate_passed is None:
        lines.append(t("chk_gate_skip"))
    elif not vd.gate_applies:
        lines.append(t("chk_gate_na", rule=rule))
    elif vd.gate_passed:
        lines.append(t("chk_gate_pass", rule=rule))
    else:
        lines.append(t("chk_gate_block", rule=rule))
    if vd.matches:
        lines.append(t("chk_yes", version=version, range=rng.text))
    else:
        lines.append(t("chk_no", version=version, range=rng.text, reason=t(f"reason_{vd.reason}")))
    return lines


def base_payload(rng: Range) -> dict:
    return {
        "ecosystem": rng.eco,
        "range": rng.text,
        "policy": rng.policy,
        "normalized": [i.to_json() for i in rng.intervals],
        "human": [i.human() for i in rng.intervals],
        "notes": list(rng.notes),
    }


# --------------------------------------------------------------------------- commands
def cmd_check(eco: str, range_text: str, version: str, opts: Options) -> tuple[dict, str, bool]:
    rng = parse_range(eco, range_text, opts)
    v = parse_version_of(rng, version)
    vd = rng.evaluate(v)
    out = base_payload(rng)
    out.update({
        "version": version,
        "normalized_version": str(v),
        "in_interval": vd.in_interval,
        "prerelease_gate": {"applies": vd.gate_applies, "passed": vd.gate_passed, "rule": vd.gate_rule},
        "matches": vd.matches,
        "reason": vd.reason,
    })
    lines = verdict_text(rng, version, vd)
    if isinstance(rng, PypiRange):
        by = {}
        for pol in ("install", "membership"):
            by[pol] = rng.with_policy(pol).evaluate(v).matches
        out["by_policy"] = by
        other = "membership" if rng.pre_policy == "install" else "install"
        if by[other] != by[rng.pre_policy]:
            lines.append(t("chk_other_policy", other=other, answer=t("yes" if by[other] else "no")))
    out["explanation"] = "\n".join(lines)
    return out, out["explanation"], vd.matches


def _soft_pick(rng: MavenRange, parsed: list[tuple[str, Ver]]) -> str | None:
    if rng.soft is None:
        return None
    for text, v in parsed:
        if v == rng.soft:
            return text
    return None


def _best_for(rng: Range, parsed: list[tuple[str, Ver]]) -> tuple[list[tuple[str, Ver]], str | None]:
    hits = [(s, v) for s, v in parsed if rng.evaluate(v).matches]
    if isinstance(rng, PypiRange) and rng.pre_policy == "install" and not hits:
        hits = [(s, v) for s, v in parsed if rng.evaluate(v).in_interval]
    hits.sort(key=functools.cmp_to_key(lambda a, b: -1 if a[1] < b[1] else (1 if b[1] < a[1] else 0)))
    selected = hits[-1][0] if hits else None
    if isinstance(rng, MavenRange):
        soft = _soft_pick(rng, parsed)
        if soft is not None:
            selected = soft
    return hits, selected


def cmd_best(eco: str, range_text: str, versions: Sequence[str], opts: Options) -> tuple[dict, str, bool]:
    rng = parse_range(eco, range_text, opts)
    parsed: list[tuple[str, Ver]] = []
    skipped = []
    for text in versions:
        try:
            parsed.append((text, parse_version_of(rng, text)))
        except InvalidVersion as exc:
            skipped.append({"version": text, "error": t(exc.key, **exc.params)})
    if not parsed:
        raise UsageError("err_all_candidates_bad")
    hits, selected = _best_for(rng, parsed)
    out = base_payload(rng)
    out.update({"candidates": list(versions), "selected": selected,
                "matching": [s for s, _ in hits], "skipped": skipped})
    lines = [t("best_head", eco=rng.eco, range=rng.text, count=len(versions), policy=rng.policy)]
    for s, v in parsed:
        vd = rng.evaluate(v)
        lines.append(t("best_line", version=s, verdict=t(f"reason_{vd.reason}")))
    for item in skipped:
        lines.append(t("best_skipped", eco=eco, version=item["version"]))
    lines.append(t("best_selected", version=selected) if selected else t("best_none"))
    if isinstance(rng, MavenRange) and rng.soft is not None:
        lines.append(t("best_soft", pref=rng.soft))
    if isinstance(rng, PypiRange):
        by = {}
        for pol in ("install", "membership"):
            _, sel = _best_for(rng.with_policy(pol), parsed)
            by[pol] = sel
        out["by_policy"] = by
        other = "membership" if rng.pre_policy == "install" else "install"
        if by[other] != by[rng.pre_policy]:
            lines.append(t("best_other_policy", other=other, pick=by[other] or t("none")))
    out["explanation"] = "\n".join(lines)
    return out, out["explanation"], selected is not None


def _exact_prerelease(comps: list) -> SemVer | None:
    if len(comps) == 1 and comps[0][0] == "=" and comps[0][1].pre:
        return comps[0][1]
    return None


def _gate_ok(v: SemVer, others: list) -> bool:
    # node-semver tests the exact version against every comparator of the other side on its own
    return all(op == "*" or (any(i.contains(v) for i in op_intervals(op, c)) and c.pre and c.t == v.t)
               for op, c in others)


def intersect_ranges(ra: Range, rb: Range) -> list[Interval]:
    """Intersect two ranges. For npm/cargo an exact prerelease version on one side must also pass
    the prerelease gate of every comparator on the other side (how node-semver intersects() behaves)."""
    if not (isinstance(ra, SemverRange) and isinstance(rb, SemverRange)):
        return intersect_lists(ra.intervals, rb.intervals)
    shared: list[Interval] = []
    for comps_a, ivs_a in zip(ra.alts, ra.alt_intervals):
        for comps_b, ivs_b in zip(rb.alts, rb.alt_intervals):
            found = intersect_lists(ivs_a, ivs_b)
            if found and not (ra.include_pre or rb.include_pre):
                for mine, other in ((comps_a, comps_b), (comps_b, comps_a)):
                    v = _exact_prerelease(mine)
                    if v is not None and not _gate_ok(v, other):
                        found = []
            shared += found
    return shared


def cmd_intersect(eco: str, a: str, b: str, opts: Options) -> tuple[dict, str, bool]:
    ra, rb = parse_range(eco, a, opts), parse_range(eco, b, opts)
    shared = intersect_ranges(ra, rb)
    out = base_payload(ra)
    out["range"] = a
    out["ranges"] = [{"range": r.text, "normalized": [i.to_json() for i in r.intervals]} for r in (ra, rb)]
    out["intersection"] = [i.to_json() for i in shared]
    out["overlaps"] = bool(shared)
    out["notes"] = list(dict.fromkeys(ra.notes + rb.notes))
    lines = [t("isect_head", eco=eco, a=a, b=b),
             t("isect_a", range=a, human=human_intervals(ra.intervals)),
             t("isect_a", range=b, human=human_intervals(rb.intervals))]
    lines.append(t("isect_yes", human=human_intervals(shared)) if shared else t("isect_no"))
    lines.append(t("isect_note"))
    out["explanation"] = "\n".join(lines)
    return out, out["explanation"], bool(shared)


def cmd_explain(eco: str, range_text: str, opts: Options) -> tuple[dict, str, bool]:
    rng = parse_range(eco, range_text, opts)
    out = base_payload(rng)
    out["rule_summary"] = t(f"rule_summary_{eco}")
    lines = [t("exp_head", eco=eco, range=range_text, human=human_intervals(rng.intervals)),
             t("exp_exact", exact=exact_intervals(rng.intervals)),
             t("exp_rule", rule=out["rule_summary"])]
    lines += rng.notes
    out["explanation"] = "\n".join(lines)
    return out, out["explanation"], True


# --------------------------------------------------------------------------- CLI
def read_candidates(path: str, stdin: Iterable[str]) -> list[str]:
    try:
        if path == "-":
            raw = list(stdin)
        else:
            with open(path, encoding="utf-8") as fh:
                raw = fh.readlines()
    except OSError:
        raise UsageError("err_file_missing", path=path) from None
    except UnicodeDecodeError:
        raise UsageError("err_not_utf8", path=("stdin" if path == "-" else path)) from None
    out = []
    for line in raw:
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def _prescan_lang(argv: Sequence[str]) -> str | None:
    for i, a in enumerate(argv):
        if a == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--lang="):
            return a.split("=", 1)[1]
    return None


class _Parser(argparse.ArgumentParser):
    """ArgumentParser whose fixed phrases (usage, group titles, errors) follow --lang."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        kwargs["add_help"] = False
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._positionals.title = t("ap_positionals")
        self._optionals.title = t("ap_options")
        self.add_argument("-h", "--help", action="help", help=t("ap_help"))

    def format_usage(self) -> str:
        return self._relabel(super().format_usage())

    def format_help(self) -> str:
        return self._relabel(super().format_help())

    @staticmethod
    def _relabel(text: str) -> str:
        return text.replace("usage: ", t("ap_usage"), 1) if text.startswith("usage: ") else text

    def error(self, message: str) -> "NoReturn":  # type: ignore[name-defined]
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {_translate_argparse(message)}\n")


def _translate_argparse(message: str) -> str:
    """Map argparse's English error text to the active language (English passes through)."""
    if _LANG != "ko":
        return message
    m = re.match(r"argument (.+?): invalid choice: (.+?)(?:, maybe you meant .+?)? \(choose from (.*)\)$", message)
    if m:
        return t("ap_err_choice", arg=m[1], value=m[2], choices=m[3])
    m = re.match(r"the following arguments are required: (.+)$", message)
    if m:
        return t("ap_err_required", names=m[1])
    m = re.match(r"unrecognized arguments: (.+)$", message)
    if m:
        return t("ap_err_unrecognized", args=m[1])
    m = re.match(r"argument (.+?): expected one argument$", message)
    if m:
        return t("ap_err_expected", arg=m[1])
    return t("ap_err_other", message=message)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", dest="as_json", help=t("help_json"))
    common.add_argument("--lang", choices=("en", "ko"), help=t("help_lang"))
    common.add_argument("--exit-status", action="store_true", help=t("help_exit_status"))
    common.add_argument("--pre-policy", choices=("install", "membership"), help=t("help_pre_policy"))
    common.add_argument("--include-prerelease", action="store_true", help=t("help_include_pre"))
    common.add_argument("--minimum-stability", choices=("stable", "RC", "beta", "alpha", "dev"),
                        help=t("help_min_stab"))
    parser = _Parser(prog="rangewise", description=t("help_desc"))
    parser.add_argument("--lang", choices=("en", "ko"), help=t("help_lang"))
    parser.add_argument("--version", action="version", version=f"rangewise {__version__}",
                        help=t("ap_version"))
    sub = parser.add_subparsers(dest="command", required=True, metavar="{check,best,intersect,explain}")

    def eco_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument("eco", choices=ECOSYSTEMS, metavar="ECO", help=t("help_eco"))

    p = sub.add_parser("check", parents=[common], help=t("help_check"), description=t("help_check"))
    eco_arg(p)
    p.add_argument("range", metavar="RANGE", help=t("help_range"))
    p.add_argument("version", metavar="VERSION", help=t("help_version"))
    p = sub.add_parser("best", parents=[common], help=t("help_best"), description=t("help_best"))
    eco_arg(p)
    p.add_argument("range", metavar="RANGE", help=t("help_range"))
    p.add_argument("versions", nargs="*", metavar="VERSION", help=t("help_versions"))
    p.add_argument("--from", dest="from_file", metavar="FILE", help=t("help_from"))
    p = sub.add_parser("intersect", parents=[common], help=t("help_intersect"), description=t("help_intersect"))
    eco_arg(p)
    p.add_argument("range", metavar="RANGE", help=t("help_range"))
    p.add_argument("range2", metavar="RANGE2", help=t("help_range2"))
    p = sub.add_parser("explain", parents=[common], help=t("help_explain"), description=t("help_explain"))
    eco_arg(p)
    p.add_argument("range", metavar="RANGE", help=t("help_range"))
    return parser


_OPT_ECOS = {"pre_policy": ("--pre-policy", ("pypi",)),
             "include_prerelease": ("--include-prerelease", ("npm", "cargo")),
             "minimum_stability": ("--minimum-stability", ("composer",))}


def options_from_args(args: argparse.Namespace) -> Options:
    for attr, (flag, ecos) in _OPT_ECOS.items():
        if getattr(args, attr) and args.eco not in ecos:
            raise UsageError("err_opt_eco", opt=flag, ecos="/".join(ecos), eco=args.eco)
    return Options(args.pre_policy, bool(args.include_prerelease), args.minimum_stability)


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None,
         stdin: Iterable[str] | None = None) -> int:
    global _LANG
    argv = list(sys.argv[1:] if argv is None else argv)
    environ = os.environ if environ is None else environ
    _LANG = resolve_lang(_prescan_lang(argv), environ)
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:  # argparse already printed its message (exit 2) or --help/--version (0)
        return int(exc.code or 0)
    try:
        opts = options_from_args(args)
        if args.command == "check":
            payload, text, ok = cmd_check(args.eco, args.range, args.version, opts)
        elif args.command == "best":
            versions = list(args.versions)
            if args.from_file:
                versions += read_candidates(args.from_file, sys.stdin if stdin is None else stdin)
            if not versions:
                raise UsageError("err_no_candidates")
            payload, text, ok = cmd_best(args.eco, args.range, versions, opts)
        elif args.command == "intersect":
            payload, text, ok = cmd_intersect(args.eco, args.range, args.range2, opts)
        else:
            payload, text, ok = cmd_explain(args.eco, args.range, opts)
    except RangewiseError as exc:
        print(exc.message(), file=sys.stderr)  # type: ignore[attr-defined]
        return exc.code
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(text)
    return EXIT_NO_MATCH if (args.exit_status and not ok) else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
