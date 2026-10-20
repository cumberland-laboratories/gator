"""Commits view data: `get_repo_history()` commit records.

Each test proves a distinct parsing risk on a real temporary Git
repository: the trailer block is split off the description and only the
trailer block; Gator trailers (machine identity included, for the raw
view) are projected in order, without non-Gator trailers; folded values
unfold; legacy Gator-PI
still names the Architect; and the existing fields are unchanged.
"""

import subprocess

import pytest

from dashboard.data import HISTORY_LIMIT_MAX, get_repo_history


def _git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    _git(tmp_path, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    return tmp_path


def _commit(repo, message):
    n = len(list(repo.glob("f*.txt")))
    (repo / f"f{n}.txt").write_text(str(n), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--cleanup=verbatim", "-m", message)
    return get_repo_history(str(repo), 1)[0]


GATOR_BLOCK = (
    "Gator-Charters: 22\n"
    "Gator-Functions: 300\n"
    "Gator-Change-Type: feature\n"
    "Gator-Decision-Tags: dashboard,paper\n"
    "Gator-Significance: notable\n"
    "Gator-Agent: claude-opus-5-5\n"
    "Gator-Architect: Alan Gillette\n"
    "Gator-Machine-Id: c5c707f5-155a-422f-9b1b-d9e8a10fea08"
)


def test_trailers_parsed_in_order(repo):
    c = _commit(repo, "Subject\n\n- First change.\n- Second change.\n\n" + GATOR_BLOCK)
    assert [t["key"] for t in c["trailers"]] == [
        "Gator-Charters", "Gator-Functions", "Gator-Change-Type",
        "Gator-Decision-Tags", "Gator-Significance", "Gator-Agent", "Gator-Architect",
        "Gator-Machine-Id"]
    assert c["trailers"][3] == {"key": "Gator-Decision-Tags", "value": "dashboard,paper"}
    # Machine identity is projected for the view's Raw trailers, never the description.
    assert c["trailers"][-1] == {"key": "Gator-Machine-Id",
                                 "value": "c5c707f5-155a-422f-9b1b-d9e8a10fea08"}
    assert "c5c707f5" not in c["description"]
    assert c["description"] == "- First change.\n- Second change."


def test_existing_fields_unchanged(repo):
    c = _commit(repo, "Subject line\n\nBody text.\n\n" + GATOR_BLOCK)
    assert c["subject"] == "Subject line"
    assert c["body"] == "Body text.\n\n" + GATOR_BLOCK  # body still carries the block
    assert c["agent"] == "claude-opus-5-5"
    assert c["architect"] == "Alan Gillette"
    assert len(c["hash"]) == 40 and c["hash"].startswith(c["short_hash"])
    assert c["author"] == "test" and c["date"]


def test_prose_key_value_line_is_kept(repo):
    """A `Key: value` line inside prose is description, not a trailer."""
    msg = "Subject\n\nNote: this line looks like a trailer.\nBut it is prose.\n\n" + GATOR_BLOCK
    c = _commit(repo, msg)
    assert c["description"] == "Note: this line looks like a trailer.\nBut it is prose."
    assert all(t["key"] != "Note" for t in c["trailers"])


def test_final_paragraph_with_prose_is_not_removed(repo):
    """A last paragraph that Git does not treat as a trailer block stays."""
    msg = "Subject\n\nFirst paragraph.\n\nClosing remark: done here, and then\nsome more plain text that is not a trailer."
    c = _commit(repo, msg)
    assert c["trailers"] == []
    assert c["description"] == ("First paragraph.\n\nClosing remark: done here, and then\n"
                                "some more plain text that is not a trailer.")


def test_multi_paragraph_body(repo):
    c = _commit(repo, "Subject\n\nPara one.\n\nPara two.\n\n- a bullet\n\n" + GATOR_BLOCK)
    assert c["description"] == "Para one.\n\nPara two.\n\n- a bullet"


def test_no_body_and_no_trailers(repo):
    c = _commit(repo, "Just a subject")
    assert c["body"] == "" and c["description"] == "" and c["trailers"] == []
    assert c["agent"] == "" and c["architect"] == ""


def test_trailers_without_description(repo):
    c = _commit(repo, "Subject\n\n" + GATOR_BLOCK)
    assert c["description"] == ""
    assert c["trailers"][0] == {"key": "Gator-Charters", "value": "22"}


def test_folded_value_is_unfolded(repo):
    msg = ("Subject\n\nBody.\n\n"
           "Gator-Change-Type: fix\n"
           "Gator-Override-Reason: a long reason that\n  continues on the next line\n"
           "Gator-Agent: claude-opus-5-5")
    c = _commit(repo, msg)
    reason = [t["value"] for t in c["trailers"] if t["key"] == "Gator-Override-Reason"]
    assert reason == ["a long reason that continues on the next line"]
    assert c["description"] == "Body."


def test_legacy_gator_pi_names_the_architect(repo):
    c = _commit(repo, "Subject\n\nBody.\n\nGator-Change-Type: fix\nGator-PI: Alan Gillette")
    assert c["architect"] == "Alan Gillette"
    assert {"key": "Gator-PI", "value": "Alan Gillette"} in c["trailers"]


def test_non_gator_trailers_ignored(repo):
    c = _commit(repo, "Subject\n\nBody.\n\nGator-Change-Type: docs\n"
                      "Co-Authored-By: Someone <someone@example.com>")
    assert [t["key"] for t in c["trailers"]] == ["Gator-Change-Type"]
    assert c["description"] == "Body."


def test_limit_is_clamped(repo):
    for i in range(3):
        _commit(repo, f"c{i}")
    assert len(get_repo_history(str(repo), 0)) == 1
    assert len(get_repo_history(str(repo), "bogus")) == 3
    assert HISTORY_LIMIT_MAX == 200
