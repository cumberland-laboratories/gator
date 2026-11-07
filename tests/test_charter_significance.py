"""Shared charter significance policy (`charter_significance.py`, #105).

Each test proves one risk named by the approved plan: the default policy
documents only real seams (entry points and cross-charter imports) and
never a helper because of its name; grouped and dotted charter headings
name every function they list; and `File:` lines are read in both the
README's plain form and the backticked form.
"""

import pytest

import charter_significance as sig

PY_HELPERS = '''
import argparse
from fastapi import APIRouter

router = APIRouter()
__all__ = ["exported"]


@router.get("/items")
def list_items():
    return []


@click.command()
def cli_cmd():
    pass


def exported():
    pass


def handler():
    pass


def build_everything(a, b, c, d):
    """Docstring, many args and a verb prefix: still not a seam by name."""


def _private():
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.set_defaults(func=handler)
'''

JS_SOURCE = '''
export function exportedFn() {}
export const exportedConst = () => 1;
function local() {}
function shared() {}
function render() {}
export { local as aliasName };
module.exports = { alpha, beta: gamma };
module.exports.delta = deltaImpl;
window.GatorViews.thing = function (data) {};
window.GatorViews.thing.helper = shared;
window.GatorViews = window.GatorViews || {};
const api = {
  configure: function (opts) {},
  later(x) { return x; },
};
'''


def _py_entries():
    return sig.python_signals(PY_HELPERS)["entries"]


def _js():
    return sig.javascript_signals(JS_SOURCE)


# (name, is_private, entries, importer_owners, file_owners, expected decision, reason)
DECISIONS = [
    # Python entry points
    ("list_items", False, _py_entries(), [], ["a"], "document", "entry"),     # route decorator
    ("cli_cmd", False, _py_entries(), [], ["a"], "document", "entry"),        # click command
    ("handler", False, _py_entries(), [], ["a"], "document", "entry"),        # set_defaults(func=)
    ("exported", False, _py_entries(), [], ["a"], "document", "entry"),       # __all__
    # JavaScript entry points
    ("exportedFn", False, _js()["entries"], [], ["a"], "document", "entry"),
    ("exportedConst", False, _js()["entries"], [], ["a"], "document", "entry"),
    ("local", False, _js()["entries"], [], ["a"], "document", "entry"),       # export { local as x }
    ("gamma", False, _js()["entries"], [], ["a"], "document", "entry"),       # module.exports value
    ("deltaImpl", False, _js()["entries"], [], ["a"], "document", "entry"),
    ("shared", False, _js()["entries"], [], ["a"], "document", "entry"),      # window.<path> = shared
    # Cross-module
    ("helper", False, set(), [["b"]], ["a"], "document", "cross-module"),     # another charter imports it
    ("helper", False, set(), [["a"]], ["a"], "internal", "local"),            # same charter only
    ("helper", False, set(), [["a", "b"]], ["a"], "internal", "local"),       # importer shares an owner
    ("helper", False, set(), [[]], ["a"], "internal", "local"),               # unowned importer ignored
    # Names alone never qualify
    ("build_everything", False, _py_entries(), [], ["a"], "internal", "local"),
    ("render", False, _js()["entries"], [], ["a"], "internal", "local"),
    # Not applicable
    ("_private", True, _py_entries(), [["b"]], ["a"], "not-applicable", "private"),
    ("main", False, {"main"}, [["b"]], ["a"], "not-applicable", "conventional"),
]


@pytest.mark.parametrize("name,private,entries,importers,owners,decision,reason", DECISIONS)
def test_decide(name, private, entries, importers, owners, decision, reason):
    assert sig.decide(name, private, entries, importers, owners) == (decision, reason)


def test_python_imports_are_resolved_by_module_stem():
    source = (
        "from charter_covers import coverage_index\n"
        "from .session import load as _load\n"
        "import pkg.tools as tools\n"
        "_draft = import_sibling('gator-charter-draft')\n"
        "x = tools.run(); y = _draft.discover_files\n"
    )
    imports = sig.python_signals(source)["imports"]
    assert {("charter_covers", "coverage_index"), ("session", "load"),
            ("tools", "run"), ("gator-charter-draft", "discover_files")} <= imports


def test_signals_register_existing_non_function_code():
    """Module bindings and JS registrations exist as code for stale checks."""
    py = sig.python_signals("from x import rebound\nLOCK = object()\n")["registered"]
    assert {"rebound", "LOCK"} <= py
    js = _js()["registered"]
    assert {"GatorViews.thing", "thing", "GatorViews.thing.helper", "configure", "later"} <= js
    assert "window" not in _js()["entries"]          # `window.X = window.X || {}` is not an entry


def test_javascript_imports():
    imports = sig.javascript_signals('import { a, b as c } from "./views/repo.js";\n')["imports"]
    assert imports == {("repo", "a"), ("repo", "b")}


def test_unparseable_python_gives_empty_signals():
    assert sig.python_signals("def broken(:\n") == {"entries": set(), "imports": set(), "registered": set()}


@pytest.mark.parametrize("line,names", [
    ("### build(x)", ["build"]),
    ("### parse_charter() / validate_charter()", ["parse_charter", "validate_charter"]),
    ("### a() / b(x, y=f()) / Cls.meth()", ["a", "b", "Cls.meth"]),       # args never become names
    ("### `quoted()` — prose", ["quoted"]),
    ("#### method_entry(self)", ["method_entry"]),
    ("### class Widget", ["Widget"]),
    ("### single_name", ["single_name"]),
    ("### coverage and stale checks", []),                                # prose names nothing
    ("## Owns", []),
])
def test_heading_names(line, names):
    assert sig.heading_names(line) == names


@pytest.mark.parametrize("line,path", [
    ("File: src/a.py", "src/a.py"),                      # README canonical form
    ("File: `src/a.py`", "src/a.py"),
    ("File: `src/a.py` (mirrored in the template copy)", "src/a.py"),
    ("File: src/a.py (and starter copy)", "src/a.py"),
    ("Filesystem: x", None),
    ("  File: src/a.py", None),                          # only at line start, as before
])
def test_parse_file_line(line, path):
    assert sig.parse_file_line(line) == path


@pytest.mark.parametrize("text,names,codes", [
    ("# Charter: x\n\n**Covers**: `a.py`\n**Internal**: `one`, `two`\n\n## Owns\n",
     ["one", "two"], []),
    ("**Internal**: `one`, `one`\n", ["one"], ["duplicate"]),
    ("**Internal**: `ok`, `bad*`, words here\n", ["ok"], ["malformed", "malformed"]),
    ("**Internal**:\n", [], ["malformed"]),
    ("**Internal**: `one`\n**Internal**: `two`\n", ["one"], ["multiple-lines"]),
    ("## Owns\n\n**Internal**: `late`\n", [], ["misplaced"]),          # suppresses nothing
    ("# Charter: x\n\nNo exclusions.\n", [], []),
])
def test_parse_internal(text, names, codes):
    got_names, problems = sig.parse_internal(text)
    assert got_names == names
    assert [p["code"] for p in problems] == codes
