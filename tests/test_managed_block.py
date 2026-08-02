"""
Tests for gatorize/managed_block.py — Stage 3 of the local-agent-overrides
+ managed-state plan (2026-07-28).
"""

from gatorize.managed_block import (
    GATOR_BEGIN, GATOR_END,
    BlockState, ManagedBlockLocation,
    find_managed_block,
    detect_legacy_gator_content,
    classify_managed_block,
    render_managed_region,
)


BASELINE = "hello world"
WRAPPED = f"{GATOR_BEGIN}\n{BASELINE}\n{GATOR_END}"


class TestSentinelBytes:
    """The sentinel byte contract is Invariant #1 — pin it in tests."""

    def test_begin_exact_bytes(self):
        assert GATOR_BEGIN == "<!-- GATOR:BEGIN -->"

    def test_end_exact_bytes(self):
        assert GATOR_END == "<!-- GATOR:END -->"


class TestRenderManagedRegion:
    def test_wraps_with_leading_and_trailing_newlines(self):
        assert render_managed_region("x") == "\nx\n"

    def test_empty_content_still_wraps(self):
        assert render_managed_region("") == "\n\n"


class TestFindManagedBlock:
    def test_valid_pair_returns_location(self):
        text = f"prefix\n{WRAPPED}\nsuffix"
        loc = find_managed_block(text)
        assert isinstance(loc, ManagedBlockLocation)
        assert loc.before == "prefix\n"
        assert loc.block_content == f"\n{BASELINE}\n"
        assert loc.after == "\nsuffix"
        assert loc.begin_index == text.index(GATOR_BEGIN)
        assert loc.end_index == text.index(GATOR_END)

    def test_no_sentinels_returns_none(self):
        assert find_managed_block("just some plain content") is None

    def test_dangling_begin_returns_none(self):
        assert find_managed_block(f"lead\n{GATOR_BEGIN}\ncontent without end") is None

    def test_dangling_end_returns_none(self):
        assert find_managed_block(f"content without begin\n{GATOR_END}\ntail") is None

    def test_reversed_sentinels_returns_none(self):
        text = f"one {GATOR_END} then {GATOR_BEGIN} in wrong order"
        assert find_managed_block(text) is None

    def test_duplicated_begin_returns_none(self):
        text = f"{GATOR_BEGIN}\na\n{GATOR_END}\nlater\n{GATOR_BEGIN}\nb\n{GATOR_END}"
        assert find_managed_block(text) is None

    def test_duplicated_end_returns_none(self):
        text = f"{GATOR_BEGIN}\na\n{GATOR_END}\nspurious {GATOR_END} tail"
        assert find_managed_block(text) is None

    def test_reconstructing_from_slices_is_byte_identical(self):
        """before + BEGIN + block_content + END + after must equal input."""
        text = f"# Header\n\nintro\n{WRAPPED}\n\ntail\n"
        loc = find_managed_block(text)
        assert loc is not None
        reconstructed = f"{loc.before}{GATOR_BEGIN}{loc.block_content}{GATOR_END}{loc.after}"
        assert reconstructed == text


class TestDetectLegacyGatorContent:
    """The four fingerprint strings that indicate pre-sentinel Gator content."""

    def test_gator_marker_matches(self):
        assert detect_legacy_gator_content("prose\n# --- Gator Navigation Coding ---\n") is True

    def test_command_post_marker_matches(self):
        assert detect_legacy_gator_content("prose\n# --- Gator Command Post ---\n") is True

    def test_gator_init_py_fingerprint_matches(self):
        assert detect_legacy_gator_content("run gator-init.py at session start") is True

    def test_constitution_path_fingerprint_matches(self):
        assert detect_legacy_gator_content("read .gator/constitution.md before starting") is True

    def test_clean_non_gator_returns_false(self):
        assert detect_legacy_gator_content("# My Project\n\nJust a plain readme.\n") is False

    def test_sentinels_alone_do_not_count_as_legacy(self):
        """Sentinels with no fingerprint text are not legacy — they are a
        (possibly corrupted) sentinel-format file."""
        text = f"{GATOR_BEGIN}\nsome content\n{GATOR_END}"
        assert detect_legacy_gator_content(text) is False


class TestClassifyManagedBlock:
    """Six-state matrix from the canonical vocabulary."""

    def test_absent_when_file_does_not_exist(self):
        state = classify_managed_block("", BASELINE, file_exists=False)
        assert state is BlockState.ABSENT

    def test_clean_when_block_matches_baseline_exactly(self):
        text = f"header\n{WRAPPED}\nfooter"
        state = classify_managed_block(text, BASELINE, file_exists=True)
        assert state is BlockState.CLEAN

    def test_modified_when_block_differs_from_baseline(self):
        text = f"header\n{GATOR_BEGIN}\ndifferent content\n{GATOR_END}\nfooter"
        state = classify_managed_block(text, BASELINE, file_exists=True)
        assert state is BlockState.MODIFIED

    def test_corrupted_dangling_begin(self):
        text = f"lead\n{GATOR_BEGIN}\ncontent with no end sentinel"
        state = classify_managed_block(text, BASELINE, file_exists=True)
        assert state is BlockState.CORRUPTED

    def test_corrupted_dangling_end(self):
        text = f"content with no begin sentinel\n{GATOR_END}\ntail"
        state = classify_managed_block(text, BASELINE, file_exists=True)
        assert state is BlockState.CORRUPTED

    def test_corrupted_reversed_sentinels(self):
        text = f"{GATOR_END} then {GATOR_BEGIN}"
        state = classify_managed_block(text, BASELINE, file_exists=True)
        assert state is BlockState.CORRUPTED

    def test_corrupted_duplicated_begin(self):
        text = f"{GATOR_BEGIN}\na\n{GATOR_END}\n{GATOR_BEGIN}\nb\n{GATOR_END}"
        state = classify_managed_block(text, BASELINE, file_exists=True)
        assert state is BlockState.CORRUPTED

    def test_legacy_gator_marker(self):
        text = "# --- Gator Navigation Coding ---\n\nsome legacy prose\n"
        state = classify_managed_block(text, BASELINE, file_exists=True)
        assert state is BlockState.LEGACY

    def test_legacy_command_post_marker(self):
        text = "# --- Gator Command Post ---\n\nthin link prose\n"
        state = classify_managed_block(text, BASELINE, file_exists=True)
        assert state is BlockState.LEGACY

    def test_legacy_init_fingerprint(self):
        text = "at session start run gator-init.py\n"
        state = classify_managed_block(text, BASELINE, file_exists=True)
        assert state is BlockState.LEGACY

    def test_legacy_constitution_fingerprint(self):
        text = "always read .gator/constitution.md first\n"
        state = classify_managed_block(text, BASELINE, file_exists=True)
        assert state is BlockState.LEGACY

    def test_foreign_when_no_sentinels_and_no_fingerprints(self):
        state = classify_managed_block("# My Project\n\nJust a readme.\n", BASELINE, file_exists=True)
        assert state is BlockState.FOREIGN

    def test_baseline_value_wire_format(self):
        """`.value` strings are the wire format — pin them."""
        assert BlockState.CLEAN.value == "clean"
        assert BlockState.MODIFIED.value == "modified"
        assert BlockState.LEGACY.value == "legacy"
        assert BlockState.CORRUPTED.value == "corrupted"
        assert BlockState.ABSENT.value == "absent"
        assert BlockState.FOREIGN.value == "foreign"
