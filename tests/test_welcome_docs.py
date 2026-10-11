"""Welcome HTML documents: the shipped content contract and its delivery.

The four Welcome topics are standalone HTML documents in the starter
template's docs/ folder. The Dashboard serves them in sandboxed iframes
(tests/test_dashboard_ui/test_welcome_ui.py); these tests pin the files
themselves.

Each test proves a distinct risk:

- drift from the mandated Cumberland master template (shared style region,
  structure, placeholders left in, a loosened document policy);
- an external request, telemetry, or a diagram without a text equivalent;
- the session document's prompt drifting from the Dashboard's constant, or
  naming a layout-dependent path;
- gatorize or gator update silently no longer delivering the documents.
"""

import re
import subprocess
from pathlib import Path

import pytest

from conftest import load_script


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "src" / "gator_command" / "scripts"
STARTER = REPO_ROOT / "src" / "gator_command" / "templates" / "gator-starter"
DOCS = STARTER / "docs"
MASTER = STARTER / "reference-notes" / "cumberland-html-document-template.html"
WELCOME_JS = SCRIPTS_DIR / "dashboard" / "views" / "welcome.js"

NAMES = [
    "how-gator-works.html",
    "what-gator-can-do.html",
    "gatorize-a-repo.html",
    "start-a-session.html",
]

# Same delimiters as contracts/compatibility/test_cumberland_narrative_style_parity.py.
REGION_RE = re.compile(
    r'/\*\s*CUMBERLAND-NARRATIVE-STYLE:BEGIN'
    r'.*?'
    r'CUMBERLAND-NARRATIVE-STYLE:END[^*]*\*/',
    re.DOTALL,
)
META_CSP_RE = re.compile(
    r'<meta http-equiv="Content-Security-Policy" content="([^"]*)">')


def _read(name):
    return (DOCS / name).read_text(encoding="utf-8")


def _session_prompt_from_dashboard():
    """SESSION_PROMPT as welcome.js defines it (concatenated literals)."""
    src = WELCOME_JS.read_text(encoding="utf-8")
    m = re.search(r"var SESSION_PROMPT =(.*?);", src, re.DOTALL)
    assert m, "SESSION_PROMPT not found in welcome.js"
    return "".join(re.findall(r'"([^"]*)"', m.group(1)))


@pytest.mark.parametrize("name", NAMES)
def test_document_is_a_cumberland_master_copy(name):
    """Filled and cut down from the master: no placeholder left, the shared
    style region byte-identical, the master's structure present, and the
    master's own meta CSP still blocking scripts."""
    text = _read(name)
    assert "==TODO==" not in text
    master_region = REGION_RE.search(MASTER.read_text(encoding="utf-8")).group(0)
    region = REGION_RE.search(text)
    assert region is not None and region.group(0) == master_region
    for marker in ('<header class="doc-head">', '<div class="meta-grid">',
                   '<section id="summary">', '<div class="callout">'):
        assert marker in text, marker
    policies = META_CSP_RE.findall(text)
    assert len(policies) == 1
    # Only the Start-a-session document runs a script (its copy action),
    # and only its script-src directive differs from the master's.
    script_src = ("'unsafe-inline'" if name == "start-a-session.html"
                  else "'none'")
    master_policy = META_CSP_RE.findall(MASTER.read_text(encoding="utf-8"))[0]
    assert policies[0] == master_policy.replace(
        "script-src 'none'", "script-src " + script_src)
    if script_src == "'none'":
        assert "<script" not in text.lower()


@pytest.mark.parametrize("name", NAMES)
def test_document_is_standalone_and_accessible(name):
    """No external resource or request; every diagram has a text title."""
    text = _read(name)
    lower = text.lower()
    assert "<head>" in text and "<title>" in text
    for banned in ("<link", "<script src", "@import", "<img", "<iframe",
                   "<object", "<embed", "url("):
        assert banned not in lower, banned
    urls = re.findall(r"https?://[^\s\"'<>]+", text)
    assert set(urls) <= {"http://www.w3.org/2000/svg"}, urls
    for svg in re.findall(r"<svg\b.*?</svg>", text, re.DOTALL):
        assert 'role="img"' in svg and "<title" in svg


def test_session_document_shows_the_dashboard_prompt():
    """The visible prompt is exactly the Dashboard's one-line constant, and
    the document names no layout-dependent path."""
    text = _read("start-a-session.html")
    prompt = _session_prompt_from_dashboard()
    assert "\n" not in prompt
    assert f'<pre id="session-prompt">{prompt}</pre>' in text
    # The copy request is the exact three-key message and never carries
    # the prompt; the prompt text appears once, in the visible <pre>.
    assert '{ type: TYPE, v: 1, action: "copy-session-prompt" }' in text
    assert text.count(prompt) == 1
    assert ".includes" not in text
    assert ".gator/GATOR_INIT.md" not in text


def test_gatorize_and_update_deliver_the_documents(tmp_path):
    """gatorize installs all four into .gator/docs/, and gator update plans
    each one back to .gator/docs/ when it is missing."""
    gatorize = load_script("gatorize", search_dir=SCRIPTS_DIR)
    update = load_script("gator-update", search_dir=SCRIPTS_DIR)
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=10)
    gatorize.action_install_gator(repo)
    docs = repo / ".gator" / "docs"
    for name in NAMES:
        assert (docs / name).read_bytes() == (DOCS / name).read_bytes(), name
        (docs / name).unlink()

    plan = update.plan_updates(STARTER, repo / ".gator", repo)
    planned = {Path(dest).resolve(): action for action, _src, dest in plan}
    for name in NAMES:
        assert planned.get((docs / name).resolve()) == "add", name
