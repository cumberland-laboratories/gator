"""Tests for FilesystemBlobStore — Phase 1 of the 2026-08-08 transcripts-first
MVP plan.

Uses pytest's ``tmp_path`` for isolated per-test roots; no shared state.
Covers:
- put/get/exists/delete/list happy paths
- Idempotent put (same key, same content, called twice)
- Overwrite (same key, different content)
- Delete of missing key is silent (idempotent)
- BlobNotFound on get of missing key
- List with prefix filters correctly
- Traversal rejection: keys with `..` segments raise ValueError
- Empty-key rejection
- Concurrent-put safety (multi-thread stress test)
- Key-shape helper (build_blob_key)
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from app.services.blob_store import BlobNotFound, BlobStore, build_blob_key
from app.services.blob_store_filesystem import FilesystemBlobStore


@pytest.fixture
def store(tmp_path):
    return FilesystemBlobStore(tmp_path / "blobs")


class TestProtocolCompliance:
    def test_filesystem_store_satisfies_protocol(self, store):
        # runtime_checkable Protocol lets isinstance work
        assert isinstance(store, BlobStore)


class TestPutGet:
    def test_put_then_get_roundtrip(self, store):
        key = "transcripts/o/m1/anthropic/2026-08-08/abc.jsonl"
        content = b'{"hello": "world"}\n'
        returned = store.put(key, content)
        assert returned == key
        assert store.get(key) == content

    def test_put_creates_parent_directories(self, store, tmp_path):
        # Deeply nested key — no error, directories materialize
        key = "a/b/c/d/e/f/deep.txt"
        store.put(key, b"content")
        assert store.get(key) == b"content"

    def test_put_same_key_same_content_is_ok(self, store):
        key = "k"
        store.put(key, b"c")
        store.put(key, b"c")  # no raise
        assert store.get(key) == b"c"

    def test_put_same_key_different_content_overwrites(self, store):
        """Filesystem impl allows overwrite (last-writer-wins).
        Documented behavior — S3 impl might behave differently and would
        need a distinct test."""
        key = "k"
        store.put(key, b"first")
        store.put(key, b"second")
        assert store.get(key) == b"second"

    def test_get_missing_key_raises_blob_not_found(self, store):
        with pytest.raises(BlobNotFound):
            store.get("does/not/exist.txt")

    def test_get_returns_bytes_not_str(self, store):
        key = "k"
        store.put(key, b"binary\x00data")
        got = store.get(key)
        assert isinstance(got, bytes)
        assert got == b"binary\x00data"


class TestExists:
    def test_exists_true_after_put(self, store):
        key = "k"
        store.put(key, b"c")
        assert store.exists(key) is True

    def test_exists_false_when_absent(self, store):
        assert store.exists("nope") is False


class TestDelete:
    def test_delete_removes_blob(self, store):
        key = "k"
        store.put(key, b"c")
        assert store.exists(key)
        store.delete(key)
        assert not store.exists(key)

    def test_delete_missing_key_is_silent(self, store):
        """Idempotent — deleting a key that isn't there is a no-op."""
        store.delete("never_existed")  # no raise


class TestList:
    def test_list_empty_store_returns_empty(self, store):
        assert store.list() == []

    def test_list_nonexistent_prefix_returns_empty(self, store):
        assert store.list("does/not/exist") == []

    def test_list_returns_keys_under_prefix(self, store):
        store.put("transcripts/o1/m1/anthropic/2026-08-08/a.jsonl", b"a")
        store.put("transcripts/o1/m1/anthropic/2026-08-08/b.jsonl", b"b")
        store.put("transcripts/o1/m2/openai/2026-08-08/c.jsonl", b"c")
        under_m1 = store.list("transcripts/o1/m1")
        assert set(under_m1) == {
            "transcripts/o1/m1/anthropic/2026-08-08/a.jsonl",
            "transcripts/o1/m1/anthropic/2026-08-08/b.jsonl",
        }
        under_all = store.list()
        assert len(under_all) == 3

    def test_list_uses_forward_slashes_on_all_platforms(self, store):
        # Windows path components use backslash internally; list returns
        # POSIX-style forward-slash keys for consistency.
        store.put("a/b/c.txt", b"x")
        (result,) = store.list()
        assert "/" in result
        assert "\\" not in result

    def test_list_ignores_temp_files(self, store, tmp_path):
        """The put path uses tempfile with prefix ``.blob-``; those must
        not show up in listing (they're implementation detail)."""
        store.put("real.txt", b"x")
        # Simulate a stray temp file that never got renamed
        stray = store.root / ".blob-abc123.tmp"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_bytes(b"orphan")
        listed = store.list()
        assert "real.txt" in listed
        assert not any(".blob-" in k for k in listed)


class TestSecurityConstraints:
    def test_empty_key_rejected(self, store):
        with pytest.raises(ValueError):
            store.put("", b"c")

    def test_traversal_dot_dot_rejected(self, store):
        """Keys containing '..' segments must not escape the store root."""
        with pytest.raises(ValueError):
            store.put("../escape.txt", b"c")
        with pytest.raises(ValueError):
            store.put("safe/../../still-escape.txt", b"c")

    def test_absolute_paths_are_treated_as_relative(self, store, tmp_path):
        """Leading slash is stripped — key stays under root, not at
        filesystem root. Defensive: even if caller messes up, no escape."""
        store.put("/looks/absolute/but/isnt.txt", b"c")
        # Written under root, not at literal /looks/...
        assert (store.root / "looks" / "absolute" / "but" / "isnt.txt").exists()

    def test_backslash_normalized_to_forward_slash(self, store):
        # Windows-shaped input should not create nested Windows-style paths
        store.put("a\\b\\c.txt", b"x")
        assert store.exists("a/b/c.txt")


class TestConcurrentPutSafety:
    def test_concurrent_puts_same_key_all_succeed(self, store):
        """N threads racing on the same key: all put() calls complete,
        no crashes, final content is one of the racing writes (last-writer-
        wins is acceptable; the invariant is 'no partial/corrupt file
        after the race')."""
        key = "concurrent"
        expected_values = [f"value-{i}".encode() for i in range(20)]
        errors = []

        def _put(i):
            try:
                store.put(key, expected_values[i])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_put, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"concurrent put raised: {errors!r}"
        # Final content must be ONE of the racing values, not a mangled mix
        final = store.get(key)
        assert final in expected_values


class TestBuildBlobKey:
    def test_canonical_shape(self):
        key = build_blob_key(
            org_uuid="abc12345-0000-0000-0000-000000000000",
            machine_id="c5c707f5-155a-422f-9b1b-d9e8a10fea08",
            vendor="anthropic",
            started_at_iso="2026-08-08T13:00:00Z",
            vendor_session_id="ba565a28-171b-4a8a-986d-b43a41bdbe2b",
        )
        # machine_short is the first hyphen-delimited segment of the UUID
        # (avoids mid-hyphen slicing that would leave a trailing dash)
        assert key == (
            "transcripts/abc12345-0000-0000-0000-000000000000/"
            "c5c707f5/anthropic/2026-08-08/"
            "ba565a28-171b-4a8a-986d-b43a41bdbe2b.jsonl"
        )

    def test_missing_date_becomes_unknown(self):
        key = build_blob_key(
            org_uuid="o",
            machine_id="m",
            vendor="v",
            started_at_iso="",
            vendor_session_id="s",
        )
        assert "unknown-date" in key

    def test_slash_in_session_id_gets_normalized(self):
        """Defensive against unexpected vendor session_id shapes."""
        key = build_blob_key(
            org_uuid="o", machine_id="m", vendor="v",
            started_at_iso="2026-08-08T00:00:00Z",
            vendor_session_id="path/like/session",
        )
        # No stray slashes in the terminal segment
        assert key.endswith("path_like_session.jsonl")
