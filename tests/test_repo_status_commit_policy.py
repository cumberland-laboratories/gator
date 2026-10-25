"""#75: `gator-repo-status.py` reports `enterprise_managed` so the Dashboard
can show the read-only commit policy as "Managed by Enterprise" instead of
reading `.gator/config.json`.

The script runs in a clean interpreter, as the Dashboard's `run_json()`
does, so it imports the package `gator_core` (not a starter copy).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parent.parent / "src" / "gator_command"
          / "scripts" / "gator-repo-status.py")


def _repo(tmp_path, marker):
    root = tmp_path / "repo"
    (root / ".gator").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / ".gator" / "config.json").write_text(
        '{"enforcement_level": "warn"}\n', encoding="utf-8")
    if marker is not None:
        (root / ".gator" / "enterprise.json").write_text(marker, encoding="utf-8")
    return root


@pytest.mark.parametrize("marker,expected", [
    (None, False),
    ('{"enabled": true}', True),
    ('{"enabled": false}', False),
    ("{not json", False),  # fail closed, as is_enterprise_active() does
])
def test_enterprise_managed_follows_the_marker(tmp_path, marker, expected):
    root = _repo(tmp_path, marker)
    r = subprocess.run([sys.executable, str(SCRIPT), "--path", str(root), "--json"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["enterprise_managed"] is expected
    assert data["config"] == {"enforcement_level": "warn"}
