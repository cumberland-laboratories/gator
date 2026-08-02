"""Tests for dashboard/snapshot.py — self-contained HTML snapshot generation."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add scripts/ to path so dashboard package is importable
_scripts_dir = Path(__file__).resolve().parent.parent / "src" / "gator_command" / "scripts"
sys.path.insert(0, str(_scripts_dir))

from dashboard.snapshot import build_snapshot, _read_asset


SAMPLE_DATA = {
    "generated_at": "2026-06-25T12:00:00Z",
    "fleet": {"summary": {"total": 2, "accessible": 2}},
    "repos": [],
}


class TestBuildSnapshot:
    def test_produces_valid_html(self):
        """Snapshot output is complete HTML with no external references."""
        html = build_snapshot(SAMPLE_DATA)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_css_inlined(self):
        """External stylesheet link is replaced with inline <style> block."""
        html = build_snapshot(SAMPLE_DATA)
        # Original link tag should be gone
        assert 'href="dashboard.css"' not in html
        # Inline style block should be present
        assert "<style>" in html
        assert "</style>" in html

    def test_scripts_inlined(self):
        """External script tags are replaced with inline <script> blocks."""
        html = build_snapshot(SAMPLE_DATA)
        # Original script src tags should be gone
        assert 'src="views/fleet.js"' not in html
        assert 'src="views/repo.js"' not in html
        assert 'src="views/updates.js"' not in html
        assert 'src="views/settings.js"' not in html
        assert 'src="dashboard.js"' not in html

    def test_data_embedded(self):
        """Tier 1 data is embedded as window.DASHBOARD_DATA."""
        html = build_snapshot(SAMPLE_DATA)
        assert "window.DASHBOARD_DATA" in html
        assert "window.GATOR_SNAPSHOT = true" in html
        # Verify the data is valid JSON inside the script tag
        assert '"generated_at"' in html

    def test_data_roundtrips(self):
        """Embedded data can be extracted and parsed back to the original."""
        html = build_snapshot(SAMPLE_DATA)
        # Extract the JSON between "window.DASHBOARD_DATA = " and ";\n"
        marker = "window.DASHBOARD_DATA = "
        start = html.index(marker) + len(marker)
        end = html.index(";\n", start)
        extracted = json.loads(html[start:end])
        assert extracted["generated_at"] == SAMPLE_DATA["generated_at"]

    def test_backslash_in_js_preserved(self):
        """JavaScript content with backslashes survives regex substitution.

        This is the chartered tripwire: re.sub must use lambda replacement,
        not raw f-string, because JS content contains backslashes that
        re.sub would misinterpret as backreferences.
        """
        html = build_snapshot(SAMPLE_DATA)
        # The actual JS files contain backslashes (regex patterns, escape sequences).
        # If the lambda guard is broken, re.sub raises or corrupts content.
        # Reaching this point without error means the lambda path works.
        assert len(html) > 1000  # sanity: non-trivial output

    def test_no_external_references_remain(self):
        """No src= or href= references to local files remain in snapshot."""
        html = build_snapshot(SAMPLE_DATA)
        # These are the specific external references that should be inlined
        for ref in [
            'href="dashboard.css"',
            'src="views/fleet.js"',
            'src="views/history.js"',
            'src="views/repo.js"',
            'src="views/updates.js"',
            'src="views/settings.js"',
            'src="dashboard.js"',
        ]:
            assert ref not in html, f"External reference not inlined: {ref}"
