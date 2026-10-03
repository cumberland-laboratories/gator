"""
#47 M4 (Dashboard server) — Architect attention interval.

Start accepts ``attention_interval`` (preferred) or the legacy
``turn_timeout`` alias; ``/status`` carries an explicit ``attention``
projection for attention-mode loops only; unblock refuses a timeout for them
with Dashboard wording; the copied join prompt contains no time language.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from test_dashboard_loop_brief import (  # noqa: F401  (env fixture)
    env, req, start, status, end_and_free, dashboard, loop_host, loop_session,
)

import events as loop_events  # noqa: E402


def _loop_dir(env, loop_id):
    return env["repo"] / ".gator" / "loops" / loop_id


def _age(d, seconds):
    s = loop_session.load_session(d)
    s["status"]["turn_started_at"] = (
        datetime.now(tz=timezone.utc) - timedelta(seconds=seconds)).isoformat()
    loop_session.save_session(d, s)
    return s["status"]["turn_started_at"]


class TestStartField:
    def test_attention_interval_preferred(self, env):
        code, text = start(env, attention_interval=900)
        assert code == 201, text
        d = _loop_dir(env, json.loads(text)["loop_id"])
        s = loop_session.load_session(d)
        assert s["status"]["turn_timeout_seconds"] == 900
        assert loop_session.attention_mode(s)

    def test_turn_timeout_alias(self, env):
        code, text = start(env, turn_timeout=600)
        assert code == 201, text
        d = _loop_dir(env, json.loads(text)["loop_id"])
        assert loop_session.load_session(d)["status"]["turn_timeout_seconds"] == 600

    def test_default(self, env):
        code, text = start(env)
        assert code == 201, text
        d = _loop_dir(env, json.loads(text)["loop_id"])
        assert loop_session.load_session(d)["status"]["turn_timeout_seconds"] == 300

    def test_both_rejected(self, env):
        code, text = start(env, attention_interval=600, turn_timeout=600)
        assert code == 400 and "not both" in text

    @pytest.mark.parametrize("bad", [5, 99999, "600", True, 1.5])
    def test_out_of_range_names_field(self, env, bad):
        code, text = start(env, attention_interval=bad)
        assert code == 400 and "attention_interval must be an integer" in text


class TestStatusProjection:
    def test_projection_shape_for_attention_loop(self, env):
        code, text = start(env)
        loop_id = json.loads(text)["loop_id"]
        body, _ = status(env, loop_id)
        att = body["attention"]
        assert set(att) == {"interval_seconds", "turn_started_at",
                            "notified_turn", "notified", "due", "host"}
        assert att["host"] is None  # not due: never probed
        assert att["interval_seconds"] == 300
        assert att["notified"] is False and att["due"] is False
        assert att["turn_started_at"] == body["status"]["turn_started_at"]
        assert body["status"]["turn_deadline"] is None

    def test_notified_after_recording(self, env):
        code, text = start(env)
        loop_id = json.loads(text)["loop_id"]
        d = _loop_dir(env, loop_id)
        key = _age(d, 400)
        loop_host._try_record_attention(d)  # a running watcher may also do it
        body, _ = status(env, loop_id)
        assert body["attention"]["notified"] is True
        assert body["attention"]["notified_turn"] == key
        assert body["attention"]["due"] is True

    def test_legacy_loop_has_no_attention_key(self, env):
        code, text = start(env)
        loop_id = json.loads(text)["loop_id"]
        d = _loop_dir(env, loop_id)
        s = loop_session.load_session(d)
        s["contract"].pop("attention_interval")
        s["status"].pop("turn_started_at")
        s["status"].pop("attention_notified_turn")
        s["status"]["turn_deadline"] = loop_session._deadline_from_now(300)
        loop_session.save_session(d, s)
        body, _ = status(env, loop_id)
        assert "attention" not in body
        assert body["status"]["turn_deadline"]


class TestAttentionStatusView:
    """The projection function itself (no watcher races)."""

    def _session(self, elapsed):
        s = loop_session.create_session("f", "f-loop", max_rounds=3, turn_timeout=300)
        s["status"]["turn_started_at"] = (
            datetime.now(tz=timezone.utc) - timedelta(seconds=elapsed)).isoformat()
        return s

    def _dir(self, tmp_path):
        d = tmp_path / "loop"
        d.mkdir()
        loop_events.create_events_file(d)
        return d

    def test_not_due(self, tmp_path):
        v = loop_host.attention_status_view(self._session(10), self._dir(tmp_path))
        assert v["due"] is False and v["notified"] is False

    def test_due_not_notified(self, tmp_path):
        v = loop_host.attention_status_view(self._session(400), self._dir(tmp_path))
        assert v["due"] is True and v["notified"] is False

    def test_event_before_marker_counts_as_notified(self, tmp_path):
        s = self._session(400)
        d = self._dir(tmp_path)
        loop_events.emit_event(d, {"event": loop_host.ATTENTION_EVENT,
                                   "attention_key": s["status"]["turn_started_at"]})
        assert s["status"]["attention_notified_turn"] is None
        assert loop_host.attention_status_view(s, d)["notified"] is True

    def test_no_scan_when_not_due(self, tmp_path, monkeypatch):
        calls = []
        monkeypatch.setattr(loop_host, "_find_attention_event",
                            lambda *a: calls.append(a) or True)
        loop_host.attention_status_view(self._session(10), self._dir(tmp_path))
        assert calls == []

    def test_no_scan_when_marker_matches(self, tmp_path, monkeypatch):
        s = self._session(400)
        s["status"]["attention_notified_turn"] = s["status"]["turn_started_at"]
        calls = []
        monkeypatch.setattr(loop_host, "_find_attention_event",
                            lambda *a: calls.append(a) or False)
        assert loop_host.attention_status_view(s, self._dir(tmp_path))["notified"] is True
        assert calls == []

    @pytest.mark.parametrize("field,value", [
        ("turn_timeout_seconds", True), ("turn_timeout_seconds", "300"),
        ("turn_started_at", "2000-01-01T00:00:00"), ("turn_started_at", 5),
        ("attention_notified_turn", ["x"]),
    ])
    def test_malformed_primitives_sanitized(self, tmp_path, field, value):
        s = self._session(400)
        s["status"][field] = value
        v = loop_host.attention_status_view(s, self._dir(tmp_path))
        assert set(v) == {"interval_seconds", "turn_started_at", "notified_turn",
                          "notified", "due", "host"}
        for k in ("interval_seconds", "turn_started_at", "notified_turn"):
            assert v[k] is None or isinstance(v[k], (int, str))
        assert not isinstance(v["interval_seconds"], bool)

    def test_legacy_returns_none(self, tmp_path):
        s = self._session(400)
        s["contract"].pop("attention_interval")
        assert loop_host.attention_status_view(s, self._dir(tmp_path)) is None


class TestUnblockRefusal:
    def test_timeout_refused_with_dashboard_wording(self, env):
        code, text = start(env)
        loop_id = json.loads(text)["loop_id"]
        d = _loop_dir(env, loop_id)
        code, text = req(env["base"] + f"/{loop_id}/pause", "POST", {"message": "hold"})
        assert code == 200, text
        before = (d / "session.json").read_bytes()
        code, text = req(env["base"] + f"/{loop_id}/unblock", "POST", {"timeout": 600})
        assert code == 400
        err = json.loads(text)["error"]
        assert "attention interval" in err and "--timeout" not in err
        assert (d / "session.json").read_bytes() == before
        code, text = req(env["base"] + f"/{loop_id}/unblock", "POST", {})
        assert code == 200, text


class TestPromptHasNoTime:
    @pytest.mark.parametrize("role", ["draftor", "reviewer"])
    def test_prompt_free_of_time_language(self, env, role):
        code, text = start(env)
        loop_id = json.loads(text)["loop_id"]
        code, text = req(env["base"] + f"/{loop_id}/prompt", "POST", {"role": role})
        assert code == 200, text
        prompt = json.loads(text)["prompt"].lower()
        for w in ("timeout", "deadline", "turn window", "time remaining", "minutes"):
            assert w not in prompt, w


class TestListMarker:
    def test_list_attention_notified(self, env):
        code, text = start(env)
        loop_id = json.loads(text)["loop_id"]
        d = _loop_dir(env, loop_id)
        code, text = req(env["base"])
        item = [l for l in json.loads(text)["loops"] if l["loop_id"] == loop_id][0]
        assert item["attention_notified"] is False
        _age(d, 400)
        loop_host._try_record_attention(d)
        code, text = req(env["base"])
        item = [l for l in json.loads(text)["loops"] if l["loop_id"] == loop_id][0]
        assert item["attention_notified"] is True


class TestHostProbe:
    """M5 P2: host state comes only from an authoritative host.lock probe,
    and only in the due-but-not-notified state."""

    def _session(self, elapsed=400):
        s = loop_session.create_session("f", "f-loop", max_rounds=3, turn_timeout=300)
        s["status"]["turn_started_at"] = (
            datetime.now(tz=timezone.utc) - timedelta(seconds=elapsed)).isoformat()
        return s

    def _dir(self, tmp_path):
        d = tmp_path / "loop"
        d.mkdir()
        loop_events.create_events_file(d)
        return d

    def test_no_host_is_none_and_lock_released(self, tmp_path):
        d = self._dir(tmp_path)
        assert loop_host.probe_host_state(d) == "none"
        fd = loop_host.acquire_host_lock(d)  # the probe did not keep it
        assert fd is not None
        loop_host.release_host_lock(fd)

    def test_held_lock_is_attached(self, tmp_path):
        d = self._dir(tmp_path)
        fd = loop_host.acquire_host_lock(d)
        try:
            assert loop_host.probe_host_state(d) == "attached"
            v = loop_host.attention_status_view(self._session(), d)
            assert v["due"] and not v["notified"] and v["host"] == "attached"
        finally:
            loop_host.release_host_lock(fd)

    def test_unopenable_is_unknown(self, tmp_path, monkeypatch):
        d = self._dir(tmp_path)
        monkeypatch.setattr(loop_host, "_try_host_lock",
                            lambda loop_dir: (None, "open failed: denied"))
        assert loop_host.probe_host_state(d) == "unknown"

    def test_due_unnotified_without_host_is_none(self, tmp_path):
        v = loop_host.attention_status_view(self._session(), self._dir(tmp_path))
        assert v["host"] == "none"

    def test_probe_raising_is_unknown(self, tmp_path):
        def boom(_d):
            raise OSError("x")
        v = loop_host.attention_status_view(self._session(), self._dir(tmp_path), probe=boom)
        assert v["host"] == "unknown"

    @pytest.mark.parametrize("case", ["not-due", "notified"])
    def test_never_probed_outside_due_unnotified(self, tmp_path, case):
        calls = []
        s = self._session(10 if case == "not-due" else 400)
        if case == "notified":
            s["status"]["attention_notified_turn"] = s["status"]["turn_started_at"]
        v = loop_host.attention_status_view(
            s, self._dir(tmp_path), probe=lambda d: calls.append(d) or "attached")
        assert calls == [] and v["host"] is None

    def test_bogus_probe_value_is_unknown(self, tmp_path):
        v = loop_host.attention_status_view(self._session(), self._dir(tmp_path),
                                            probe=lambda d: "maybe")
        assert v["host"] == "unknown"
