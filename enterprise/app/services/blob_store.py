"""Blob storage contract — Enterprise transcript-body persistence.

Enterprise stores full transcript payloads out-of-DB in a swappable
blob substrate. The DB row (`transcript_sessions`) carries only
metadata + a reference to the blob (`blob_key`); this module owns
the put/get/exists/delete/list surface for the blob body.

Design contract (per 2026-08-08 transcripts-first MVP plan §6):
  - Narrow interface — only the operations MVP + expected post-MVP
    growth actually need
  - Reference implementation is filesystem-backed
    (`blob_store_filesystem.py`); customers can swap for S3, Azure
    Blob, or a customer-provided substrate post-MVP without touching
    the ingestion pipeline
  - Idempotent by convention — putting the same key twice with the
    same content is OK
  - Reentrant + safe for concurrent use across ingestion workers

Key namespacing convention (produced by ingestion, honored by
implementations as opaque):

    transcripts/{org_uuid}/{machine_id_short}/{vendor}/{yyyy-mm-dd}/{vendor_session_id}.jsonl

Human-inspectable, partitioning by date for retention/backup
automation, vendor-scoped for future adapter-specific handling.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class BlobNotFound(Exception):
    """Raised when :meth:`BlobStore.get` cannot find the requested key."""


@runtime_checkable
class BlobStore(Protocol):
    """Enterprise transcript-blob storage interface.

    Implementations must be reentrant + safe for concurrent use across
    ingestion workers. All methods take str keys; content is bytes.
    """

    def put(self, key: str, content: bytes) -> str:
        """Store ``content`` at ``key`` (namespaced path-like string).

        Returns the canonical stored-key (may equal ``key`` or be
        normalized by the implementation). Idempotent: putting the
        same key twice with the same content is OK; the store MAY
        raise or overwrite on differing content — implementations
        must document their choice.
        """
        ...

    def get(self, key: str) -> bytes:
        """Retrieve blob content. Raises :class:`BlobNotFound` if missing."""
        ...

    def exists(self, key: str) -> bool:
        """Check without fetching content."""
        ...

    def delete(self, key: str) -> None:
        """Remove blob. Idempotent — deleting a missing key is OK."""
        ...

    def list(self, prefix: str = "") -> list[str]:
        """List keys under ``prefix``.

        MVP returns the full list; production implementations MAY
        paginate. Callers should treat the return type as an
        unordered iterable.
        """
        ...


def build_blob_key(
    org_uuid: str,
    machine_id: str,
    vendor: str,
    started_at_iso: str,
    vendor_session_id: str,
    session_qualifier: str = "",
) -> str:
    """Construct the canonical blob key per the namespacing convention.

    All inputs are treated as strings; caller is responsible for
    supplying them in the expected shape. Returns a POSIX-style
    forward-slash key regardless of platform.

    ``started_at_iso`` may be a full ISO-8601 timestamp; only the
    ``YYYY-MM-DD`` prefix is used. If the input isn't parseable, the
    date component becomes ``"unknown-date"`` — caller has already
    stored the raw timestamp in the DB row, so this is a partitioning
    convenience, not a canonical value.

    ``session_qualifier`` (Migration 011, Phase 4 Gemini adapter): when
    non-empty, appended to the filename as ``__{qualifier}`` so two
    duplicate-raw-ID transcripts (distinct rows under the widened
    uniqueness constraint) get distinct blob keys instead of the second
    upload overwriting the first. Empty for all non-Gemini vendors —
    their keys are byte-identical to the pre-011 shape.
    """
    # First hyphen segment for readability (avoids mid-hyphen slicing);
    # falls back to first 12 chars if there's no hyphen in the input.
    if machine_id:
        machine_short = machine_id.split("-", 1)[0] or machine_id[:12]
    else:
        machine_short = "unknown"
    date_prefix = "unknown-date"
    if started_at_iso and len(started_at_iso) >= 10:
        candidate = started_at_iso[:10]
        # Very light validation — YYYY-MM-DD shape
        if len(candidate) == 10 and candidate[4] == "-" and candidate[7] == "-":
            date_prefix = candidate
    safe_session = (vendor_session_id or "unknown-session").replace("/", "_")
    if session_qualifier:
        safe_session = f"{safe_session}__{session_qualifier.replace('/', '_')}"
    return (
        f"transcripts/{org_uuid}/{machine_short}/{vendor}/"
        f"{date_prefix}/{safe_session}.jsonl"
    )
