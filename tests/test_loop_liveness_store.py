"""
M1 tests for the loop participant liveness store (#36).

Covers: schema allowlist and forbidden data, atomic persistence and
corrupt-file quarantine, state_key stability, classify boundaries,
retention/pruning, redaction, and store-dir resolution.
"""

import copy
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "src" / "gator_command" / "scripts"
LOOP_DIR = SCRIPTS_DIR / "loop"
for p in [str(SCRIPTS_DIR), str(LOOP_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import liveness as lv  # noqa: E402

LOOP_ID = "liveness-test-2026-09-29T00-00-00Z"
NOW = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
REG_ID = "0123456789abcdef0123456789abcdef"
KEY = "a" * 64


def _reg(**over):
    reg = {
        "registration_id": REG_ID,
        "generation": 1,
        "adapter": {"kind": "generic-watcher", "capabilities": ["poll", "ack"]},
        "registered_at": lv.iso(NOW),
        "last_seen_at": lv.iso(NOW),
        "heartbeat_seconds": 15,
        "state": "active",
    }
    reg.update(over)
    return reg


def _note(seq, **over):
    n = {
        "seq": seq, "kind": "turn-ready", "state_key": KEY,
        "stage": "plan_review", "round": 1,
        "created_at": lv.iso(NOW), "created_by": "projection",
        "delivered_at": None, "delivered_generation": None,
        "acked_at": None, "acked_generation": None,
        "expired_at": None, "expired_reason": None,
    }
    n.update(over)
    return n


def _populated():
    st = lv.empty_state(LOOP_ID)
    rec = st["roles"]["reviewer"]
    rec["registration"] = _reg()
    rec["notifications"] = [_note(1)]
    rec["next_seq"] = 2
    st["audit"] = [{"at": lv.iso(NOW), "action": "renotify",
                    "role": "reviewer", "seq": 1, "actor": "architect",
                    "reason": "nudge"}]
    return st


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class TestSchema:
    def test_empty_state_valid(self):
        lv.validate_state(lv.empty_state(LOOP_ID), loop_id=LOOP_ID)

    def test_populated_state_round_trips(self, tmp_path):
        store = lv.LivenessStore(tmp_path, LOOP_ID)
        st = _populated()
        store.with_lock(lambda _s: (st, None))
        assert store.read() == st
        assert store.last_error is None

    @pytest.mark.parametrize("where,key", [
        ("top", "token"),
        ("top", "nonce"),
        ("registration", "token"),
        ("registration", "model"),
        ("adapter", "provider"),
        ("notification", "prompt"),
        ("notification", "artifact"),
        ("notification", "turn_deadline"),
        ("audit", "token"),
    ])
    def test_forbidden_keys_rejected(self, where, key):
        st = _populated()
        target = {
            "top": st,
            "registration": st["roles"]["reviewer"]["registration"],
            "adapter": st["roles"]["reviewer"]["registration"]["adapter"],
            "notification": st["roles"]["reviewer"]["notifications"][0],
            "audit": st["audit"][0],
        }[where]
        target[key] = "x"
        with pytest.raises(lv.LivenessSchemaError):
            lv.validate_state(st)

    def test_token_shaped_value_rejected_anywhere(self):
        st = _populated()
        st["roles"]["reviewer"]["registration"]["adapter"]["label"] = \
            "glp_abcDEF123"
        with pytest.raises(lv.LivenessSchemaError):
            lv.validate_state(st)

    def test_architect_role_not_allowed(self):
        st = _populated()
        st["roles"]["architect"] = lv.empty_role()
        with pytest.raises(lv.LivenessSchemaError):
            lv.validate_state(st)

    @pytest.mark.parametrize("mutate", [
        lambda n: n.update(kind="auto-submit"),
        lambda n: n.update(created_by="participant"),
        lambda n: n.update(state_key="not-a-digest"),
        lambda n: n.update(stage="Plan Review!"),
        lambda n: n.update(seq=0),
        lambda n: n.update(round=True),
        lambda n: n.update(acked_at="yesterday"),
        lambda n: n.update(expired_reason="because"),
    ])
    def test_notification_values_checked(self, mutate):
        st = _populated()
        mutate(st["roles"]["reviewer"]["notifications"][0])
        with pytest.raises(lv.LivenessSchemaError):
            lv.validate_state(st)

    @pytest.mark.parametrize("mutate", [
        lambda r: r.update(registration_id="short"),
        lambda r: r.update(state="working"),
        lambda r: r.update(heartbeat_seconds=0),
        lambda r: r["adapter"].update(kind="codex"),
        lambda r: r["adapter"].update(capabilities=["submit"]),
        lambda r: r["adapter"].update(label="x" * 41),
        lambda r: r["adapter"].update(label="tab\there"),
        lambda r: r.update(released_reason="bored"),
    ])
    def test_registration_values_checked(self, mutate):
        st = _populated()
        mutate(st["roles"]["reviewer"]["registration"])
        with pytest.raises(lv.LivenessSchemaError):
            lv.validate_state(st)

    def test_duplicate_or_future_seq_rejected(self):
        st = _populated()
        st["roles"]["reviewer"]["notifications"].append(_note(1))
        with pytest.raises(lv.LivenessSchemaError):
            lv.validate_state(st)
        st = _populated()
        st["roles"]["reviewer"]["notifications"][0]["seq"] = 2  # == next_seq
        with pytest.raises(lv.LivenessSchemaError):
            lv.validate_state(st)

    def test_loop_id_mismatch_rejected(self):
        with pytest.raises(lv.LivenessSchemaError):
            lv.validate_state(lv.empty_state(LOOP_ID), loop_id="other-loop")

    @pytest.mark.parametrize("bad", ["../x", "a/b", "a\\b", "", ".hidden",
                                     "a..b"])
    def test_store_rejects_bad_loop_ids(self, tmp_path, bad):
        with pytest.raises(ValueError):
            lv.LivenessStore(tmp_path, bad)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_missing_file_reads_empty(self, tmp_path):
        store = lv.LivenessStore(tmp_path / "nope", LOOP_ID)
        assert store.read() == lv.empty_state(LOOP_ID)
        assert not (tmp_path / "nope").exists()

    def test_fn_returning_none_does_not_write(self, tmp_path):
        store = lv.LivenessStore(tmp_path, LOOP_ID)
        assert store.with_lock(lambda s: (None, "v")) == "v"
        assert not store.path.exists()

    def test_written_file_is_lf_and_sorted_json(self, tmp_path):
        store = lv.LivenessStore(tmp_path, LOOP_ID)
        store.with_lock(lambda s: (_populated(), None))
        raw = store.path.read_bytes()
        assert b"\r\n" not in raw
        assert json.loads(raw) == _populated()

    def test_invalid_state_is_not_written(self, tmp_path):
        store = lv.LivenessStore(tmp_path, LOOP_ID)
        store.with_lock(lambda s: (_populated(), None))
        before = store.path.read_bytes()
        bad = _populated()
        bad["token"] = "x"
        with pytest.raises(lv.LivenessSchemaError):
            store.with_lock(lambda s: (bad, None))
        assert store.path.read_bytes() == before
        assert not list(tmp_path.glob("*.tmp"))

    def test_interrupted_write_keeps_old_file(self, tmp_path, monkeypatch):
        store = lv.LivenessStore(tmp_path, LOOP_ID)
        store.with_lock(lambda s: (_populated(), None))
        before = store.path.read_bytes()

        def boom(*a, **k):
            raise OSError("disk full")
        monkeypatch.setattr(lv.json, "dump", boom)
        with pytest.raises(OSError):
            store.with_lock(lambda s: (lv.empty_state(LOOP_ID), None))
        assert store.path.read_bytes() == before
        assert not list(tmp_path.glob("*.tmp"))

    def test_replace_retries_permission_error(self, tmp_path, monkeypatch):
        store = lv.LivenessStore(tmp_path, LOOP_ID)
        store.REPLACE_DELAY = 0
        real = lv.os.replace
        calls = {"n": 0}

        def flaky(src, dst):
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError("in use")
            return real(src, dst)
        monkeypatch.setattr(lv.os, "replace", flaky)
        store.with_lock(lambda s: (_populated(), None))
        assert calls["n"] == 3
        assert store.read() == _populated()

    @pytest.mark.parametrize("content", ["{not json", json.dumps({"schema": 1})])
    def test_corrupt_file_read_is_side_effect_free(self, tmp_path, content):
        store = lv.LivenessStore(tmp_path, LOOP_ID)
        store.path.write_text(content, encoding="utf-8")
        assert store.read() == lv.empty_state(LOOP_ID)
        assert store.last_error == "corrupt"
        assert store.path.read_text(encoding="utf-8") == content

    def test_corrupt_file_quarantined_under_lock(self, tmp_path):
        store = lv.LivenessStore(tmp_path, LOOP_ID)
        store.path.write_text("{not json", encoding="utf-8")
        seen = store.with_lock(lambda s: (None, s))
        assert seen == lv.empty_state(LOOP_ID)
        assert store.last_error == "corrupt"
        assert not store.path.exists()
        quarantined = list(tmp_path.glob(f"{LOOP_ID}.json.corrupt-*"))
        assert len(quarantined) == 1
        assert quarantined[0].read_text(encoding="utf-8") == "{not json"

    def test_failed_quarantine_blocks_mutation(self, tmp_path, monkeypatch):
        """P2 regression: if the corrupt file cannot be renamed aside, the
        mutating callback must not run and the original must survive."""
        store = lv.LivenessStore(tmp_path, LOOP_ID)
        store.REPLACE_DELAY = 0
        store.path.write_text("{not json", encoding="utf-8")

        real = lv.os.replace

        def locked(src, dst):
            # Only the quarantine rename fails; a save would succeed and
            # overwrite the corrupt original if mutation were allowed.
            if ".corrupt-" in str(dst):
                raise PermissionError("sharing violation")
            return real(src, dst)
        monkeypatch.setattr(lv.os, "replace", locked)

        called = []

        def mutate(state):
            called.append(True)
            return _populated(), None

        with pytest.raises(lv.LivenessUnavailableError):
            store.with_lock(mutate)
        assert called == []
        assert store.last_error == "quarantine_failed"
        assert store.path.read_text(encoding="utf-8") == "{not json"
        assert not list(tmp_path.glob("*.corrupt-*"))
        assert not list(tmp_path.glob("*.tmp"))

    def test_quarantine_retries_transient_failure(self, tmp_path, monkeypatch):
        store = lv.LivenessStore(tmp_path, LOOP_ID)
        store.REPLACE_DELAY = 0
        store.path.write_text("{not json", encoding="utf-8")
        real = lv.os.replace
        calls = {"n": 0}

        def flaky(src, dst):
            calls["n"] += 1
            if calls["n"] == 1:
                raise PermissionError("in use")
            return real(src, dst)
        monkeypatch.setattr(lv.os, "replace", flaky)
        store.with_lock(lambda s: (_populated(), None))
        assert store.read() == _populated()
        quarantined = list(tmp_path.glob(f"{LOOP_ID}.json.corrupt-*"))
        assert len(quarantined) == 1
        assert quarantined[0].read_text(encoding="utf-8") == "{not json"

    def test_read_transient_error_returns_none(self, tmp_path, monkeypatch):
        store = lv.LivenessStore(tmp_path, LOOP_ID)
        store.with_lock(lambda s: (_populated(), None))

        def denied(self, *a, **k):
            raise PermissionError("sharing violation")
        monkeypatch.setattr(lv.Path, "read_text", denied)
        assert store.read() is None
        assert store.last_error == "unavailable"

    def test_read_retries_transient_error(self, tmp_path, monkeypatch):
        store = lv.LivenessStore(tmp_path, LOOP_ID)
        store.REPLACE_DELAY = 0
        store.with_lock(lambda s: (_populated(), None))
        real = lv.Path.read_text
        calls = {"n": 0}

        def flaky(self, *a, **k):
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError("sharing violation")
            return real(self, *a, **k)
        monkeypatch.setattr(lv.Path, "read_text", flaky)
        assert store.read() == _populated()
        assert store.last_error is None

    def test_locked_read_error_does_not_call_fn(self, tmp_path, monkeypatch):
        store = lv.LivenessStore(tmp_path, LOOP_ID)
        store.with_lock(lambda s: (_populated(), None))
        before = store.path.read_bytes()

        def denied(self, *a, **k):
            raise PermissionError("sharing violation")
        monkeypatch.setattr(lv.Path, "read_text", denied)
        with pytest.raises(lv.LivenessUnavailableError):
            store.with_lock(lambda s: (lv.empty_state(LOOP_ID), None))
        monkeypatch.undo()
        assert store.path.read_bytes() == before

    def test_delete_removes_file(self, tmp_path):
        store = lv.LivenessStore(tmp_path, LOOP_ID)
        store.with_lock(lambda s: (_populated(), None))
        assert store.delete() is True
        assert not store.path.exists()
        assert store.read() == lv.empty_state(LOOP_ID)

    def test_lock_is_exclusive_across_threads(self, tmp_path):
        import threading
        store = lv.LivenessStore(tmp_path, LOOP_ID)
        inside = threading.Event()
        release = threading.Event()
        order = []

        def slow(state):
            order.append("a-in")
            inside.set()
            release.wait(5)
            order.append("a-out")
            return None, None

        def fast(state):
            order.append("b")
            return None, None

        ta = threading.Thread(target=lambda: store.with_lock(slow))
        ta.start()
        assert inside.wait(5)
        other = lv.LivenessStore(tmp_path, LOOP_ID)
        tb = threading.Thread(target=lambda: other.with_lock(fast))
        tb.start()
        tb.join(0.3)
        assert order == ["a-in"]
        release.set()
        ta.join(5)
        tb.join(5)
        assert order == ["a-in", "a-out", "b"]


# ---------------------------------------------------------------------------
# state_key
# ---------------------------------------------------------------------------

def _session(**status):
    base = {"round": 1, "stage": "plan_review", "next_role": "reviewer",
            "turn_deadline": "2026-09-29T12:05:00+00:00"}
    base.update(status)
    return {"status": base, "turns": [{"role": "draftor"}],
            "feature": "irrelevant"}


class TestStateKey:
    def test_stable_for_unchanged_state(self):
        assert lv.state_key(_session()) == lv.state_key(_session())
        assert len(lv.state_key(_session())) == 64

    def test_ignores_unrelated_fields(self):
        s = _session()
        s["feature"] = "changed"
        s["status"]["max_rounds"] = 9
        assert lv.state_key(s) == lv.state_key(_session())

    @pytest.mark.parametrize("change", [
        {"round": 2}, {"stage": "plan_revision"}, {"next_role": "draftor"},
        {"turn_deadline": "2026-09-29T12:10:00+00:00"},
    ])
    def test_changes_with_each_status_field(self, change):
        assert lv.state_key(_session(**change)) != lv.state_key(_session())

    def test_changes_with_turn_count(self):
        s = _session()
        s["turns"].append({"role": "reviewer"})
        assert lv.state_key(s) != lv.state_key(_session())


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------

class TestClassify:
    def _rec(self, age_seconds, state="active"):
        return {"registration": _reg(
            last_seen_at=lv.iso(NOW - timedelta(seconds=age_seconds)),
            state=state)}

    def test_not_registered(self):
        assert lv.classify(lv.empty_role(), NOW) == "not_registered"
        assert lv.classify(None, NOW) == "not_registered"

    def test_connected_at_threshold(self):
        assert lv.classify(self._rec(45), NOW) == "connected"

    def test_stale_past_threshold(self):
        assert lv.classify(self._rec(46), NOW) == "stale"

    @pytest.mark.parametrize("state", ["released", "closed"])
    def test_released_and_closed_never_stale(self, state):
        assert lv.classify(self._rec(3600, state), NOW) == state

    @pytest.mark.parametrize("state", ["active", "released", "closed"])
    def test_expired_after_24h(self, state):
        at_limit = lv.classify(self._rec(24 * 3600, state), NOW)
        assert at_limit == ("stale" if state == "active" else state)
        assert lv.classify(self._rec(24 * 3600 + 1, state), NOW) == "expired"


# ---------------------------------------------------------------------------
# prune
# ---------------------------------------------------------------------------

class TestPrune:
    def test_missing_loop_deletes(self):
        _, delete = lv.prune(_populated(), NOW, loop_exists=False)
        assert delete is True

    def test_terminal_retention_boundary(self):
        st = _populated()
        st["terminal_observed_at"] = lv.iso(NOW - timedelta(days=7))
        assert lv.prune(copy.deepcopy(st), NOW)[1] is False
        st["terminal_observed_at"] = lv.iso(NOW - timedelta(days=7, seconds=1))
        assert lv.prune(st, NOW)[1] is True

    def test_expired_registration_dropped(self):
        st = _populated()
        st["roles"]["reviewer"]["registration"]["last_seen_at"] = \
            lv.iso(NOW - timedelta(hours=25))
        st, _ = lv.prune(st, NOW)
        assert st["roles"]["reviewer"]["registration"] is None
        lv.validate_state(st)

    def test_turn_ready_ttl(self):
        st = _populated()
        n = st["roles"]["reviewer"]["notifications"][0]
        n["created_at"] = lv.iso(NOW - timedelta(hours=24, seconds=1))
        st, _ = lv.prune(st, NOW)
        assert n["expired_reason"] == "ttl"
        assert n["expired_at"] == lv.iso(NOW)

    def test_acked_turn_ready_not_ttl_expired(self):
        st = _populated()
        n = st["roles"]["reviewer"]["notifications"][0]
        n["created_at"] = lv.iso(NOW - timedelta(days=2))
        n["acked_at"] = lv.iso(NOW - timedelta(days=2))
        n["acked_generation"] = 1
        lv.prune(st, NOW)
        assert n["expired_at"] is None

    def test_cap_drops_oldest_non_pending_and_keeps_pending(self):
        st = lv.empty_state(LOOP_ID)
        rec = st["roles"]["draftor"]
        notes = []
        for seq in range(1, 61):
            acked = seq != 2  # seq 2 stays pending
            notes.append(_note(seq, kind="architect-block",
                               acked_at=lv.iso(NOW) if acked else None,
                               acked_generation=1 if acked else None))
        rec["notifications"] = notes
        rec["next_seq"] = 61
        st, _ = lv.prune(st, NOW)
        seqs = [n["seq"] for n in rec["notifications"]]
        assert len(seqs) == lv.MAX_NOTIFICATIONS_PER_ROLE
        assert 2 in seqs
        assert seqs[0] == 2 and seqs[1] == 12  # 1, 3..11 dropped
        lv.validate_state(st)

    def test_all_pending_may_exceed_cap(self):
        """Documented trade-off: delivery safety over the size bound."""
        st = lv.empty_state(LOOP_ID)
        rec = st["roles"]["draftor"]
        rec["notifications"] = [_note(s, kind="architect-block")
                                for s in range(1, 56)]
        rec["next_seq"] = 56
        st, _ = lv.prune(st, NOW)
        assert len(rec["notifications"]) == 55

    def test_audit_and_superseded_caps(self):
        st = _populated()
        st["audit"] = st["audit"] * 150
        st["roles"]["reviewer"]["superseded"] = [
            {"generation": g, "superseded_at": lv.iso(NOW)}
            for g in range(1, 21)]
        st, _ = lv.prune(st, NOW)
        assert len(st["audit"]) == lv.MAX_AUDIT_ENTRIES
        sup = st["roles"]["reviewer"]["superseded"]
        assert [s["generation"] for s in sup] == list(range(11, 21))


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

class TestRedaction:
    def test_redact_token(self):
        tok = "glp_bG9vcDpyZXZpZXdlcjoxMjM0NTY3OA"
        out = lv.redact(f"bad token {tok} here")
        assert tok not in out
        assert "glp_[REDACTED]" in out

    def test_sanitize_text(self):
        assert lv.sanitize_text("ok\tglp_abc\x00é" + "x" * 300, 20) == \
            "okglp_[REDACTED]xxxx"


# ---------------------------------------------------------------------------
# Store dir resolution
# ---------------------------------------------------------------------------

class TestResolveStoreDir:
    def test_real_git_repo(self, tmp_path):
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        d = lv.resolve_store_dir(tmp_path)
        assert d is not None
        assert d.is_absolute()
        assert d.name == lv.STORE_DIRNAME
        assert d.parent.resolve() == (tmp_path / ".git").resolve()

    def test_git_failure_is_unavailable(self, tmp_path):
        # Fake runner: a real non-repo check would depend on whether the
        # pytest basetemp happens to sit inside a Git worktree.
        def runner(*a, **k):
            return subprocess.CompletedProcess(a, 128, stdout="",
                                               stderr="not a git repository")
        assert lv.resolve_store_dir(tmp_path, runner=runner) is None

    def test_relative_git_path_anchored_at_repo_root(self, tmp_path):
        def runner(*a, **k):
            return subprocess.CompletedProcess(
                a, 0, stdout=".git/gator-loop-liveness\n", stderr="")
        d = lv.resolve_store_dir(tmp_path, runner=runner)
        assert d == tmp_path / ".git" / "gator-loop-liveness"

    def test_git_missing_is_unavailable(self, tmp_path):
        def runner(*a, **k):
            raise FileNotFoundError("git")
        assert lv.resolve_store_dir(tmp_path, runner=runner) is None
