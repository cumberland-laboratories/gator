"""
Retired-claim regression guard for the gator-native entry point (2026-10-08).

Gator no longer creates, refreshes, backs up, or repairs CLAUDE.md /
AGENTS.md / GEMINI.md; sessions start from `gator init` -> GATOR_INIT.md.
Maintained guidance must not teach the retired ownership model.

Scope (maintained surfaces): every `.md` shipped in the starter template
(GATOR_INIT.md included), README.md, and the three user docs below.
Excluded by name, because they are historical or research material:
CHANGELOG.md (release history), docs/supporting-research.md and
docs/what-is-navigation-coding.md (external studies and bibliography).
Historical wording such as "older Gator versions wrote a GATOR:BEGIN block"
stays allowed; only the retired *claims* are matched.
"""

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent
TEMPLATES_DIR = REPO_ROOT / "src" / "gator_command" / "templates" / "gator-starter"
INCLUDES_DIR = REPO_ROOT / ".gator" / ".includes"

MAINTAINED_DOCS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "how-to-use-gator.md",
    REPO_ROOT / "docs" / "architecture.md",
    REPO_ROOT / "docs" / "custom-skills-and-team-workflow.md",
]

RETIRED_CLAIMS = [
    r"\.pre-gator-update",
    r"_ROLLBACK\.md",
    r"Pre-Gator Instructions",
    r"primary-agent entry ?point",
    r"Gator (manages|refreshes|updates) (a |the |its )?(managed )?(block|region)",
    r"(writes|installs|creates) (the )?entry[- ]points?",
    r"adds or updates .?(CLAUDE|AGENTS|GEMINI)\.md",
]

# Template files revised by this change whose dogfood copies must stay
# byte-identical (the starter template is the source of truth).
REVISED_PAIRS = [
    "procedures/enforcer-review.md",
    "reference-notes/enforcer-configuration.md",
    "reference-notes/concierge-responses.md",
    "reference-notes/local-agent-skills.md",
    "reference-notes/what-gator-requires-from-a-model.md",
    "procedures/gator-version-drift.md",
    "procedures/knowledge-capture.md",
]


def _maintained_surfaces():
    return sorted(TEMPLATES_DIR.rglob("*.md")) + MAINTAINED_DOCS


@pytest.mark.parametrize("pattern", RETIRED_CLAIMS)
def test_maintained_guidance_has_no_retired_claim(pattern):
    regex = re.compile(pattern, re.IGNORECASE)
    hits = []
    for path in _maintained_surfaces():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if regex.search(line):
                hits.append(f"{path.relative_to(REPO_ROOT).as_posix()}:{lineno}: {line.strip()[:120]}")
    assert hits == [], "retired native-file claim(s):\n" + "\n".join(hits)


@pytest.mark.parametrize("rel", REVISED_PAIRS)
def test_revised_dogfood_copy_matches_template(rel):
    assert (INCLUDES_DIR / rel).read_bytes() == (TEMPLATES_DIR / rel).read_bytes(), rel
