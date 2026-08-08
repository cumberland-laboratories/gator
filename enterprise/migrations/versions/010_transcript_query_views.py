"""010 — Operator query views for transcript custody.

Ships three views over the Phase 1 tables (`transcript_sessions`,
`commit_transcript_links`, `commits`) that the operator guide points
at for common ad-hoc queries. Views intentionally do NOT filter by
organization_id — the caller adds `WHERE organization_id = ...` at
query time so the same view definition works for every tenant.

Views:

- `recent_transcripts`      — session metadata + linked-commit count
                              (matches the shape the CLI's
                              `transcripts list` returns).
- `commits_with_transcript_coverage`
                            — one row per commit with the count of
                              linked transcripts and the strongest
                              linkage_basis observed.
- `unlinked_recent_transcripts`
                            — transcript sessions ingested in the
                              last 7 days with zero links; the
                              investigation queue for whoever runs
                              audit.

TRIPWIRE — the view definitions reference columns on the underlying
tables; any column rename in Migration 009's tables MUST be paired
with a follow-up view migration or these views break silently at
query time. The unique-constraint names on `commit_transcript_links`
and `transcript_sessions` are NOT referenced here, so those are safe
to rename.

Revision ID: 010
"""

from alembic import op


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


_RECENT_TRANSCRIPTS = """
CREATE VIEW recent_transcripts AS
SELECT
    ts.id                          AS transcript_session_id,
    ts.organization_id,
    ts.vendor,
    ts.vendor_session_id,
    ts.machine_id,
    ts.model,
    ts.workspace_hint,
    ts.blob_key,
    ts.blob_size_bytes,
    ts.started_at,
    ts.ended_at,
    ts.ingested_at,
    ts.retention_class,
    COUNT(ctl.id)                  AS linked_commit_count
FROM transcript_sessions ts
LEFT JOIN commit_transcript_links ctl
       ON ctl.transcript_session_id = ts.id
GROUP BY ts.id
"""

_COMMITS_WITH_COVERAGE = """
CREATE VIEW commits_with_transcript_coverage AS
SELECT
    c.id                           AS commit_id,
    c.organization_id,
    c.repo_identifier,
    c.commit_sha,
    c.author_identity,
    c.committed_at,
    c.machine_id,
    c.snippet_agent,
    c.transcript_session_id        AS snippet_transcript_session_id,
    COUNT(ctl.id)                  AS linked_transcript_count,
    -- The strongest linkage_basis observed on this commit, using the
    -- MVP vocabulary ordering (exact_sha > session_id > strong_machine_repo_time
    -- > orchestrator_declared > none). CASE-based rank because the
    -- string values don't sort correctly alphabetically.
    COALESCE(
        MIN(
            CASE ctl.linkage_basis
                WHEN 'exact_sha_in_transcript'   THEN 1
                WHEN 'session_id_in_snippet'     THEN 2
                WHEN 'strong_machine_repo_time'  THEN 3
                WHEN 'orchestrator_declared'     THEN 4
                ELSE 99
            END
        ),
        99
    )                              AS best_linkage_rank,
    -- Human-readable strongest basis (or NULL if unlinked).
    MIN(
        CASE
            WHEN ctl.linkage_basis = 'exact_sha_in_transcript'  THEN '1_exact_sha_in_transcript'
            WHEN ctl.linkage_basis = 'session_id_in_snippet'    THEN '2_session_id_in_snippet'
            WHEN ctl.linkage_basis = 'strong_machine_repo_time' THEN '3_strong_machine_repo_time'
            WHEN ctl.linkage_basis = 'orchestrator_declared'    THEN '4_orchestrator_declared'
            ELSE NULL
        END
    )                              AS best_linkage_basis_ranked
FROM commits c
LEFT JOIN commit_transcript_links ctl
       ON ctl.commit_id = c.id
GROUP BY c.id
"""

_UNLINKED_RECENT = """
CREATE VIEW unlinked_recent_transcripts AS
SELECT
    ts.id                          AS transcript_session_id,
    ts.organization_id,
    ts.vendor,
    ts.vendor_session_id,
    ts.machine_id,
    ts.model,
    ts.workspace_hint,
    ts.blob_key,
    ts.blob_size_bytes,
    ts.started_at,
    ts.ended_at,
    ts.ingested_at
FROM transcript_sessions ts
LEFT JOIN commit_transcript_links ctl
       ON ctl.transcript_session_id = ts.id
WHERE ctl.id IS NULL
  AND ts.ingested_at > NOW() - INTERVAL '7 days'
"""


def upgrade():
    op.execute(_RECENT_TRANSCRIPTS)
    op.execute(_COMMITS_WITH_COVERAGE)
    op.execute(_UNLINKED_RECENT)


def downgrade():
    op.execute("DROP VIEW IF EXISTS unlinked_recent_transcripts")
    op.execute("DROP VIEW IF EXISTS commits_with_transcript_coverage")
    op.execute("DROP VIEW IF EXISTS recent_transcripts")
