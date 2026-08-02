"""Reusable managed-block inspection helpers.

Owns the sentinel-delimited managed region inside entry-point files
(CLAUDE.md, AGENTS.md, GEMINI.md). Extracted from entry_points.py so
`gator state status` / `gator state repair` / `gator update`'s block
refresh (Stages 4, 4b of the local-agent-overrides + managed-state plan)
can share the same parser and byte-format contract.

Stage 3 of `gator-command/artifacts/2026-07-28-local-agent-overrides-and-managed-state-plan.md`.
"""

from dataclasses import dataclass
from enum import Enum

from gatorize.helpers import GATOR_MARKER, COMMAND_POST_MARKER


# Sentinel bytes are the ownership contract with every gatorized repo.
# Do NOT mutate — whitespace, casing, or attributes. See Invariant #1 of
# the Stage plan.
GATOR_BEGIN = "<!-- GATOR:BEGIN -->"
GATOR_END = "<!-- GATOR:END -->"

# Legacy fingerprints — recognizable Gator content in files that predate
# the sentinel format. Keep in sync with `action_install_entry_points()`
# case-2 detection.
_LEGACY_FINGERPRINTS = (
    GATOR_MARKER,
    COMMAND_POST_MARKER,
    "gator-init.py",
    ".gator/constitution.md",
)


class BlockState(Enum):
    """Canonical six-state vocabulary for entry-point files.

    Defined once here; all API constants, JSON schema values, human output,
    and test fixtures must use these exact lowercase spellings (via `.value`).
    See "Canonical State Vocabulary" in the Stage plan.
    """
    CLEAN = "clean"
    MODIFIED = "modified"
    LEGACY = "legacy"
    CORRUPTED = "corrupted"
    ABSENT = "absent"
    FOREIGN = "foreign"


@dataclass(frozen=True)
class ManagedBlockLocation:
    """Slices and byte offsets of a well-formed managed block in a file's text."""
    before: str
    block_content: str
    after: str
    begin_index: int
    end_index: int


def render_managed_region(baseline_content: str) -> str:
    """Exact bytes that should appear between GATOR_BEGIN and GATOR_END.

    Centralizes the newline wrapping so installer, `gator update` block-refresh
    (Stage 4b), and `gator state repair` (Stage 4) all produce byte-identical
    managed regions given the same baseline content.
    """
    return f"\n{baseline_content}\n"


def find_managed_block(text):
    """Return a ManagedBlockLocation for a well-formed sentinel pair, else None.

    "Well-formed" means exactly one GATOR_BEGIN and one GATOR_END, in that order.
    Returns None for any deviation (no sentinels, dangling, reversed, duplicated).
    Callers that need to distinguish "corrupted" from "no sentinels" should use
    `classify_managed_block()` instead.
    """
    if text.count(GATOR_BEGIN) != 1 or text.count(GATOR_END) != 1:
        return None
    begin = text.index(GATOR_BEGIN)
    end = text.index(GATOR_END)
    if end < begin:
        return None
    block_content = text[begin + len(GATOR_BEGIN):end]
    return ManagedBlockLocation(
        before=text[:begin],
        block_content=block_content,
        after=text[end + len(GATOR_END):],
        begin_index=begin,
        end_index=end,
    )


def _has_sentinel_bytes(text):
    """True if either sentinel appears at all in the text."""
    return GATOR_BEGIN in text or GATOR_END in text


def _sentinels_are_malformed(text):
    """True if sentinel bytes appear but do not form exactly one valid pair.

    Malformed = dangling BEGIN, dangling END, reversed order, duplicated BEGIN,
    or duplicated END. Returns False when there are no sentinels at all (that
    is LEGACY or FOREIGN, not CORRUPTED) and False when there is a valid pair.
    """
    if not _has_sentinel_bytes(text):
        return False
    n_begin = text.count(GATOR_BEGIN)
    n_end = text.count(GATOR_END)
    if n_begin != 1 or n_end != 1:
        return True
    return text.index(GATOR_END) < text.index(GATOR_BEGIN)


def detect_legacy_gator_content(text):
    """True if the file has no sentinel pair but matches recognizable Gator content.

    Mirrors the fingerprint checks previously inline in `action_install_entry_points()`
    (pre-Stage-3 entry_points.py:114-120). Sentinels alone do not count as legacy —
    only the fingerprint strings do.
    """
    return any(fp in text for fp in _LEGACY_FINGERPRINTS)


def classify_managed_block(text, baseline_content, *, file_exists):
    """Classify the state of an entry-point file relative to a baseline.

    Dispatch order:
      1. `file_exists=False` → ABSENT
      2. valid sentinel pair → CLEAN or MODIFIED (byte-compare against baseline)
      3. malformed sentinel bytes → CORRUPTED
      4. no sentinels + legacy fingerprint → LEGACY
      5. no sentinels + no fingerprint → FOREIGN

    `baseline_content` is the raw content that should appear between the
    sentinels (i.e., the return value of `render_entry_content()`). The
    function internally wraps it via `render_managed_region()` for the
    byte-compare so callers do not need to know the newline contract.
    """
    if not file_exists:
        return BlockState.ABSENT
    location = find_managed_block(text)
    if location is not None:
        expected = render_managed_region(baseline_content)
        return BlockState.CLEAN if location.block_content == expected else BlockState.MODIFIED
    if _sentinels_are_malformed(text):
        return BlockState.CORRUPTED
    if detect_legacy_gator_content(text):
        return BlockState.LEGACY
    return BlockState.FOREIGN
