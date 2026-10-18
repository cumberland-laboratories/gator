"""
#61: session.json saves and loads survive transient Windows sharing
violations.

On Windows, os.replace() onto session.json fails with PermissionError
(winerror 5) while any reader holds the file open. save_session() and
load_session() retry that briefly; if the file stays in use, the save
raises SessionBusyError with the old file intact. Real-handle tests run on
Windows only; the retry policy is also pinned with injected errors, which
run everywhere (POSIX never sets winerror, so its behavior is unchanged).
"""

import errno
import json
import sys
import threading
import time
from pathlib import Path

import pytest

from conftest import SCRIPTS_DIR

LOOP_DIR = SCRIPTS_DIR / "loop"
for p in [str(SCRIPTS_DIR), str(LOOP_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import session as loop_session  # noqa: E402

windows_only = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows sharing semantics: POSIX allows replacing an open file")


def _sharing_error(winerror=5):
    exc = PermissionError(errno.EACCES, "Access is denied")
    exc.winerror = winerror
    return exc


@pytest.fixture
def loop_dir(tmp_path):
    d = tmp_path / "loop"
    d.mkdir()
    loop_session.save_session(d, {"v": 1})
    return d


def _temp_files(d):
    return sorted(p.name for p in Path(d).glob("session-*.tmp"))


# ── real handles (Windows) ──────────────────────────────────────────────────


@windows_only
def test_save_waits_out_a_reader_holding_the_file(loop_dir):
    """A reader holds session.json open; the save retries and succeeds once
    the reader closes it. Without the retry this is #61's failure."""
    target = loop_dir / loop_session.SESSION_FILENAME
    reader = open(target, "r", encoding="utf-8")
    closer = threading.Timer(0.15, reader.close)
    closer.start()
    try:
        start = time.monotonic()
        loop_session.save_session(loop_dir, {"v": 2})
        elapsed = time.monotonic() - start
    finally:
        closer.join(5)
        reader.close()
    assert loop_session.load_session(loop_dir) == {"v": 2}
    assert elapsed >= 0.1, "the save should have had to wait for the reader"
    assert _temp_files(loop_dir) == []


@windows_only
def test_save_gives_up_cleanly_when_the_file_stays_in_use(loop_dir, monkeypatch):
    """A reader holds the file past the whole retry window: SessionBusyError
    (EBUSY, not PermissionError), the old content intact, no temp file."""
    monkeypatch.setattr(loop_session, "SHARING_RETRY_ATTEMPTS", 3)
    target = loop_dir / loop_session.SESSION_FILENAME
    with open(target, "r", encoding="utf-8"):
        with pytest.raises(loop_session.SessionBusyError) as info:
            loop_session.save_session(loop_dir, {"v": 2})
    assert info.value.errno == errno.EBUSY
    assert not isinstance(info.value, PermissionError)
    assert json.loads(target.read_text(encoding="utf-8")) == {"v": 1}
    assert _temp_files(loop_dir) == []


@windows_only
def test_concurrent_readers_never_break_saves_or_see_torn_json(loop_dir):
    """Four threads re-read session.json every 1 ms (far more often than any
    real reader: the Dashboard polls every 3 s) while 100 saves run: every
    save lands, and every read parses as a whole document. Readers with no
    pause at all can starve a save past its retry window (measured:
    95/100 SessionBusyError); that limit is recorded in scripts-loop.md."""
    stop = threading.Event()
    problems = []

    def reader():
        while not stop.is_set():
            try:
                data = loop_session.load_session(loop_dir)
                if set(data) != {"v"}:
                    problems.append(("shape", data))
            except Exception as exc:  # noqa: BLE001 — report everything
                problems.append(("read", repr(exc)))
            time.sleep(0.001)

    threads = [threading.Thread(target=reader, daemon=True) for _ in range(4)]
    for t in threads:
        t.start()
    try:
        for i in range(2, 102):
            loop_session.save_session(loop_dir, {"v": i})
    except Exception as exc:  # noqa: BLE001
        problems.append(("save", repr(exc)))
    finally:
        stop.set()
        for t in threads:
            t.join(5)
    assert not problems, problems[:5]
    assert loop_session.load_session(loop_dir) == {"v": 101}
    assert _temp_files(loop_dir) == []


# ── retry policy (all platforms, injected errors) ───────────────────────────


def test_retry_succeeds_after_transient_sharing_errors(tmp_path):
    calls = []
    sleeps = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise _sharing_error(32 if len(calls) == 1 else 5)
        return "done"

    assert loop_session._retry_sharing(fn, tmp_path, sleep=sleeps.append) == "done"
    assert len(calls) == 3
    assert sleeps == [0.01, 0.02]


def test_retry_is_bounded_and_raises_session_busy(tmp_path):
    sleeps = []

    def fn():
        raise _sharing_error()

    with pytest.raises(loop_session.SessionBusyError) as info:
        loop_session._retry_sharing(fn, tmp_path / "session.json",
                                    sleep=sleeps.append)
    assert len(sleeps) == loop_session.SHARING_RETRY_ATTEMPTS - 1
    assert max(sleeps) == loop_session.SHARING_RETRY_MAX_DELAY
    assert sum(sleeps) < 1.5
    assert isinstance(info.value.__cause__, PermissionError)


def test_windows_crt_eacces_counts_as_transient(monkeypatch):
    """open() during a replace raises EACCES with no winerror (C runtime);
    on Windows that is a sharing violation, elsewhere it is not."""
    exc = PermissionError(errno.EACCES, "Permission denied")
    monkeypatch.setattr(loop_session.sys, "platform", "win32")
    assert loop_session._is_sharing_violation(exc)
    monkeypatch.setattr(loop_session.sys, "platform", "linux")
    assert not loop_session._is_sharing_violation(exc)


@pytest.mark.parametrize("exc", [
    FileNotFoundError(errno.ENOENT, "gone"),
    OSError(errno.EIO, "I/O error"),
])
def test_other_errors_are_not_retried(tmp_path, exc, monkeypatch):
    monkeypatch.setattr(loop_session.sys, "platform", "linux")
    calls = []

    def fn():
        calls.append(1)
        raise exc

    with pytest.raises(type(exc)):
        loop_session._retry_sharing(fn, tmp_path, sleep=lambda s: None)
    assert calls == [1]


def test_save_never_writes_in_place_when_the_replace_fails(loop_dir, monkeypatch):
    """Even with every replace refused, save_session never touches the
    target directly: old content intact, temp file removed."""
    monkeypatch.setattr(loop_session, "SHARING_RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(loop_session.time, "sleep", lambda s: None)

    def refuse(src, dst):
        raise _sharing_error()

    monkeypatch.setattr(loop_session.os, "replace", refuse)
    with pytest.raises(loop_session.SessionBusyError):
        loop_session.save_session(loop_dir, {"v": 2})
    target = loop_dir / loop_session.SESSION_FILENAME
    assert json.loads(target.read_text(encoding="utf-8")) == {"v": 1}
    assert _temp_files(loop_dir) == []


def test_load_retries_a_transient_sharing_error(loop_dir, monkeypatch):
    monkeypatch.setattr(loop_session.time, "sleep", lambda s: None)
    original = Path.read_text
    calls = []

    def flaky(self, *a, **kw):
        if self.name == loop_session.SESSION_FILENAME and not calls:
            calls.append(1)
            raise _sharing_error(32)
        return original(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", flaky)
    assert loop_session.load_session(loop_dir) == {"v": 1}
    assert calls == [1]


def test_find_active_loop_fails_closed_when_session_is_busy(tmp_path, monkeypatch):
    """The single-active guard treats a session.json that stays in use as
    active, never as absent; a corrupt one is still skipped."""
    import host as loop_host
    loops = tmp_path / "loops"
    (loops / "corrupt").mkdir(parents=True)
    (loops / "corrupt" / loop_session.SESSION_FILENAME).write_text("{not json", encoding="utf-8")
    (loops / "busy").mkdir()
    (loops / "busy" / loop_session.SESSION_FILENAME).write_text("{}", encoding="utf-8")
    original = loop_host.load_session

    def load(entry):
        if Path(entry).name == "busy":
            raise loop_session.SessionBusyError(Path(entry) / "session.json",
                                                _sharing_error())
        return original(entry)

    monkeypatch.setattr(loop_host, "load_session", load)
    assert loop_host.find_active_loop(loops) == "busy"

    monkeypatch.setattr(loop_host, "load_session", original)
    (loops / "busy" / loop_session.SESSION_FILENAME).unlink()
    assert loop_host.find_active_loop(loops) is None

