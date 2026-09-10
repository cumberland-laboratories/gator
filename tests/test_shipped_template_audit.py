"""Fast-matrix audit for shipped HTML blueprint templates.

Runs in the Python 3.9 + 3.13, Ubuntu + Windows fast matrix — no
Playwright dependency. Guards two invariants at the shipped-template
layer that B2's CSP relies on:

1. **No dynamic code execution.** The B2 CSP forbids `'unsafe-eval'`
   in the `script-src` directive (r14 §4.1 audit ratified nine
   shipped HTML files as clean 2026-09-09). If a future template
   introduces `Function(...)`, `eval(...)`, or a string-valued timer,
   the CSP would need `'unsafe-eval'` to render it — which we do not
   grant. The audit catches this before browsers do.

2. **Regex-coverage self-test.** Documents the exact set of patterns
   the audit matches and pins each spelling that must (or must not)
   trigger. Failing this test means the regex drifted from its
   documented coverage.

The Playwright-based CSP-compat integration pin lives in
`tests/test_dashboard_ui/test_html_preview.py` (Dashboard-UI matrix,
Python 3.12, Chromium). This module is deliberately Playwright-free
so it runs in the fast matrix — see r4 §L1 (relocation rationale).
"""

import re
from pathlib import Path


# ── The three-pattern set (r14 §M1 + r5 §M2, ratified) ───────────
#
# `Function(...)` catches bare/new/window./globalThis. forms in one
# rule; `\b` word-boundary correctly excludes `myFunction(` (no
# boundary between `y` and `F`). `eval(...)` catches direct eval.
# The timer pattern requires a string argument (either quote style,
# whitespace tolerant) — a function argument like
# `setTimeout(handler, 0)` is safe under CSP and MUST NOT flag.
#
# `document.write` was removed in r5 (belongs to a different policy
# family — `'unsafe-inline'` XSS hygiene, not `'unsafe-eval'` gate).
# Indirect-eval bypasses (`(0, eval)(...)`, `[]["constructor"]…`,
# `Reflect.apply(Function, ...)`, aliased identifiers) are OUT OF
# SCOPE per r6 — code review is the intended catch for a small
# editorially-controlled corpus.

_DYNAMIC_CODE_PATTERNS = [
    # Function constructor — catches every observed spelling in one
    # pattern: `Function("code")`, `new Function(...)`,
    # `window.Function(...)`, `globalThis.Function(...)`.
    r"\bFunction\s*\(",
    # Direct eval.
    r"\beval\s*\(",
    # Timer functions called with a string argument (any quote
    # style, any whitespace between name/paren/quote).
    r"\bset(?:Timeout|Interval|Immediate)\s*\(\s*['\"]",
]

_DYNAMIC_CODE_COMPILED = [re.compile(p) for p in _DYNAMIC_CODE_PATTERNS]


# ── The two audit roots B2 shipped-template CSP-compat depends on ─
#
# `.gator/blueprints/*.html`         — governance-namespace blueprints
# `src/gator_command/templates/gator-starter/blueprints/*.html`
#                                    — package-template blueprints
# per r14 §M2 audit inventory (nine files 2026-09-09; grow this list
# only when new HTML surfaces are added).

def _repo_root():
    """Walk up from this file to the repo root (the directory
    containing `.gator/`).  The audit uses filesystem discovery
    rather than a hard-coded path so it works from a source
    checkout of any layout.
    """
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / ".gator").is_dir():
            return parent
    raise RuntimeError(
        f"could not locate repo root (containing .gator/) from "
        f"{here}")


def _shipped_html_files():
    """Return the full list of shipped HTML files across both
    audit roots. Uses `Path.glob('*.html')` — not recursive; the
    surfaces are flat (see r4 §L1 design decision). Silently
    empty if a root does not exist (e.g. an installed wheel with
    only the package-template root); the audit then covers what
    is present.
    """
    root = _repo_root()
    files = []
    for rel in (
        ".gator/blueprints",
        "src/gator_command/templates/gator-starter/blueprints",
    ):
        directory = root / rel
        if directory.is_dir():
            files.extend(sorted(directory.glob("*.html")))
    return files


# ── Audit pin (primary): no shipped template uses dynamic code ────

def test_no_shipped_template_uses_dynamic_code_execution():
    """Guard the CSP `'unsafe-eval'` non-permission.

    Scans every shipped HTML file for the three documented dynamic-
    code patterns.  If a match is found, the audit fails with the
    filename, line number, and the offending line — the failure
    message is meant to be actionable in code review.
    """
    files = _shipped_html_files()
    assert files, (
        "no shipped HTML files found under either audit root — "
        "the fixture-discovery walk is broken")

    findings = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(
                f"{path}: could not read: {exc}")
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern in _DYNAMIC_CODE_COMPILED:
                if pattern.search(line):
                    findings.append(
                        f"{path}:{lineno}: matches "
                        f"{pattern.pattern!r}: {line.strip()!r}")
                    break  # one finding per line is enough
    assert not findings, (
        "shipped templates would require CSP 'unsafe-eval'. B2's "
        "CSP does NOT grant 'unsafe-eval'. Fix the template or "
        "route the pattern via a static-DOM alternative:\n"
        + "\n".join("  " + f for f in findings))


# ── Regex-coverage self-test (documents + pins the pattern shape) ─

_POSITIVE_FIXTURES = [
    'Function("return 1")()',
    "Function('return 1')()",
    'new Function("return 1")()',
    'window.Function("return 1")()',
    'globalThis.Function("return 1")()',
    'eval("1")',
    "eval('1')",
    'setTimeout("code", 0)',
    "setTimeout('code', 0)",
    'setInterval("code", 0)',
    'setImmediate("code")',
    "  setTimeout ( 'code' , 0 )",
]

# Documented indirect-eval / out-of-scope forms (informational; the
# audit does NOT try to catch these — see r6 §M1 out-of-scope list).
# Kept here as prose so a future contributor tempted to add regex
# coverage sees the design decision inline.
_OUT_OF_SCOPE_BYPASSES = [
    "(0, eval)('code')",
    "(0, Function)('code')()",
    "[][ 'constructor' ][ 'constructor' ]('code')()",
    "Reflect.apply(Function, null, ['code'])()",
    "const F = Function; F('code')()",
]

_NEGATIVE_FIXTURES = [
    'document.write("<b>x</b>")',   # `'unsafe-inline'` policy family
    "myFunction()",                  # user identifier ending Function
    "functional_test()",             # case-sensitive; lowercase safe
    "setTimeout(handler, 0)",        # function arg, not string
]


def test_dynamic_code_regex_matches_all_documented_patterns():
    """Pins each positive fixture triggers exactly one pattern and
    each negative fixture triggers none. If this test fails, the
    regex has drifted from its documented coverage.
    """
    for fixture in _POSITIVE_FIXTURES:
        matched = [p.pattern for p in _DYNAMIC_CODE_COMPILED
                   if p.search(fixture)]
        assert matched, (
            f"positive fixture failed to match any pattern: "
            f"{fixture!r}")

    for fixture in _NEGATIVE_FIXTURES:
        matched = [p.pattern for p in _DYNAMIC_CODE_COMPILED
                   if p.search(fixture)]
        assert not matched, (
            f"negative fixture unexpectedly matched: "
            f"{fixture!r} -> {matched}")


def test_out_of_scope_bypasses_documented():
    """Sanity pin — the out-of-scope inventory contains at least
    one representative of each family (comma-operator, property-
    string, Reflect, aliased identifier). A future contributor
    adding a new bypass family should extend the inventory here
    AND update the audit's r6-§M1 out-of-scope prose. Without this
    pin the inventory can silently drift.
    """
    joined = " ".join(_OUT_OF_SCOPE_BYPASSES)
    assert "(0, eval)" in joined, "comma-operator eval missing"
    assert "(0, Function)" in joined, "comma-operator Function missing"
    assert "'constructor'" in joined, "property-string bypass missing"
    assert "Reflect.apply" in joined, "Reflect.apply bypass missing"
    assert "const F = Function" in joined, "aliased-identifier missing"
