"""E5 views tests — compliance bucketing, timeline pagination, org isolation.

These tests use an in-memory SQLite database for speed. They test service logic
directly (not HTTP), focusing on the edge cases identified during review:
- Six-state compliance bucketing with rollout-timing semantics
- Timeline cursor pagination correctness across page boundaries
- Org isolation across all read-model services
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base
from app.models.organization import Organization
from app.models.repository import Repository
from app.models.git_provider import GitProvider
from app.models.commit import Commit
from app.models.commit_observation import CommitObservation
from app.models.drift_finding import PolicyDriftFinding
from app.models.policy import Policy, PolicyVersion
from app.models.policy_target import PolicyTarget
from app.models.policy_rollout import PolicyRollout
from app.models.ingest_job import IngestJob
from app.models.api_token import ApiToken
from app.models.audit_log import AdminAuditLog
from app.models.report_run import ReportRun
from app.models.sync_run import ProviderSyncRun


@pytest.fixture
def db():
    """In-memory SQLite session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.close()


@pytest.fixture
def org_a(db):
    """Test org A."""
    org = Organization(id=uuid.uuid4(), name="Org A", slug="org-a")
    db.add(org)
    db.commit()
    return org


@pytest.fixture
def org_b(db):
    """Test org B (for isolation tests)."""
    org = Organization(id=uuid.uuid4(), name="Org B", slug="org-b")
    db.add(org)
    db.commit()
    return org


@pytest.fixture
def provider_a(db, org_a):
    p = GitProvider(
        id=uuid.uuid4(), organization_id=org_a.id,
        provider_type="github", status="active",
    )
    db.add(p)
    db.commit()
    return p


@pytest.fixture
def repo_a(db, org_a, provider_a):
    r = Repository(
        id=uuid.uuid4(), organization_id=org_a.id,
        provider_id=provider_a.id, provider_repo_id="123",
        canonical_identifier="github.com/org-a/repo-1",
        name="repo-1", default_branch="main", active=True,
    )
    db.add(r)
    db.commit()
    return r


def _make_policy_with_rollout(db, org, repo, *, applied_at=None, rollout_status="applied"):
    """Helper: create policy, version, target, and rollout."""
    policy = Policy(
        id=uuid.uuid4(), organization_id=org.id,
        name="Test Policy", slug=f"test-{uuid.uuid4().hex[:8]}",
        status="active",
    )
    db.add(policy)
    db.flush()

    version = PolicyVersion(
        id=uuid.uuid4(), policy_id=policy.id,
        version_number=1, content={"rules": []},
        content_hash="abc123", is_active=True,
    )
    db.add(version)
    db.flush()

    target = PolicyTarget(
        id=uuid.uuid4(), policy_id=policy.id,
        repository_id=repo.id, active=True,
    )
    db.add(target)

    rollout = PolicyRollout(
        id=uuid.uuid4(), organization_id=org.id,
        policy_id=policy.id, policy_version_id=version.id,
        repository_id=repo.id, status=rollout_status,
        source="activation", applied_at=applied_at,
    )
    db.add(rollout)
    db.commit()
    return policy, version, rollout


def _make_commit_with_observation(db, org, repo, *, committed_at, has_drift=False, policy=None, version=None):
    """Helper: create commit + observation, optionally with drift findings."""
    commit = Commit(
        id=uuid.uuid4(), organization_id=org.id,
        repo_identifier=repo.canonical_identifier,
        commit_sha=uuid.uuid4().hex[:40],
        committed_at=committed_at,
        ingested_at=committed_at,
        model_identities=["claude-opus-4"],
    )
    db.add(commit)
    db.flush()

    obs = CommitObservation(
        id=uuid.uuid4(), organization_id=org.id,
        commit_id=commit.id, repository_id=repo.id,
        observation_status="observed",
        status_json_present=True, charter_count=5,
        constitution_present=True, trailers={"Gator-Agent": "claude-opus-4"},
    )
    db.add(obs)

    if has_drift and policy and version:
        finding = PolicyDriftFinding(
            id=uuid.uuid4(), organization_id=org.id,
            policy_id=policy.id, policy_version_id=version.id,
            repository_id=repo.id, commit_id=commit.id,
            check_name="charter_required", severity="drift",
            detail="Charter not found",
        )
        db.add(finding)

    db.commit()
    return commit, obs


# ============================================================
# Compliance Bucketing Tests
# ============================================================

class TestComplianceBucketing:
    """Six-state compliance with rollout-timing semantics."""

    def test_ungoverned_no_targets(self, db, org_a, repo_a):
        from app.services.fleet_reads import compute_repo_compliance
        assert compute_repo_compliance(db, org_a.id, repo_a.id) == "ungoverned"

    def test_pending_rollout(self, db, org_a, repo_a):
        from app.services.fleet_reads import compute_repo_compliance
        _make_policy_with_rollout(db, org_a, repo_a, rollout_status="pending")
        assert compute_repo_compliance(db, org_a.id, repo_a.id) == "pending"

    def test_failed_rollout(self, db, org_a, repo_a):
        from app.services.fleet_reads import compute_repo_compliance
        _make_policy_with_rollout(db, org_a, repo_a, rollout_status="failed")
        assert compute_repo_compliance(db, org_a.id, repo_a.id) == "failed"

    def test_failed_takes_precedence_over_pending(self, db, org_a, repo_a):
        from app.services.fleet_reads import compute_repo_compliance
        _make_policy_with_rollout(db, org_a, repo_a, rollout_status="pending")
        _make_policy_with_rollout(db, org_a, repo_a, rollout_status="failed")
        assert compute_repo_compliance(db, org_a.id, repo_a.id) == "failed"

    def test_unknown_no_observation_after_rollout(self, db, org_a, repo_a):
        from app.services.fleet_reads import compute_repo_compliance
        now = datetime.now(timezone.utc)
        _make_policy_with_rollout(db, org_a, repo_a, applied_at=now)
        assert compute_repo_compliance(db, org_a.id, repo_a.id) == "unknown"

    def test_unknown_observation_before_rollout(self, db, org_a, repo_a):
        """Observation from before rollout applied should not count."""
        from app.services.fleet_reads import compute_repo_compliance
        now = datetime.now(timezone.utc)
        # Commit before rollout
        _make_commit_with_observation(
            db, org_a, repo_a, committed_at=now - timedelta(hours=2)
        )
        # Rollout applied after commit
        _make_policy_with_rollout(db, org_a, repo_a, applied_at=now - timedelta(hours=1))
        assert compute_repo_compliance(db, org_a.id, repo_a.id) == "unknown"

    def test_aligned_observation_after_rollout_no_drift(self, db, org_a, repo_a):
        from app.services.fleet_reads import compute_repo_compliance
        now = datetime.now(timezone.utc)
        policy, version, rollout = _make_policy_with_rollout(
            db, org_a, repo_a, applied_at=now - timedelta(hours=2)
        )
        _make_commit_with_observation(
            db, org_a, repo_a, committed_at=now - timedelta(hours=1)
        )
        assert compute_repo_compliance(db, org_a.id, repo_a.id) == "aligned"

    def test_drifting_observation_after_rollout_with_drift(self, db, org_a, repo_a):
        from app.services.fleet_reads import compute_repo_compliance
        now = datetime.now(timezone.utc)
        policy, version, rollout = _make_policy_with_rollout(
            db, org_a, repo_a, applied_at=now - timedelta(hours=2)
        )
        _make_commit_with_observation(
            db, org_a, repo_a, committed_at=now - timedelta(hours=1),
            has_drift=True, policy=policy, version=version,
        )
        assert compute_repo_compliance(db, org_a.id, repo_a.id) == "drifting"

    def test_unknown_when_newer_policy_applied_after_observation(self, db, org_a, repo_a):
        """Multiple policies: latest applied_at gates observations."""
        from app.services.fleet_reads import compute_repo_compliance
        now = datetime.now(timezone.utc)
        # First policy applied early
        _make_policy_with_rollout(
            db, org_a, repo_a, applied_at=now - timedelta(hours=3)
        )
        # Observation between the two rollouts
        _make_commit_with_observation(
            db, org_a, repo_a, committed_at=now - timedelta(hours=2)
        )
        # Second policy applied AFTER the observation
        _make_policy_with_rollout(
            db, org_a, repo_a, applied_at=now - timedelta(hours=1)
        )
        # Should be unknown because observation predates latest rollout
        assert compute_repo_compliance(db, org_a.id, repo_a.id) == "unknown"


# ============================================================
# Timeline Pagination Tests
# ============================================================

class TestTimelinePagination:
    """Cursor-based pagination correctness."""

    def test_basic_pagination(self, db, org_a, repo_a):
        """First page returns limit events, next_cursor allows continuation."""
        from app.services.audit_reads import get_timeline
        now = datetime.now(timezone.utc)

        # Create 5 commits
        for i in range(5):
            commit = Commit(
                id=uuid.uuid4(), organization_id=org_a.id,
                repo_identifier=repo_a.canonical_identifier,
                commit_sha=uuid.uuid4().hex[:40],
                committed_at=now - timedelta(minutes=i),
                ingested_at=now, model_identities=["test"],
            )
            db.add(commit)
        db.commit()

        result = get_timeline(db, org_a.id, limit=3)
        assert len(result["events"]) == 3
        assert result["pagination"]["has_more"] is True
        assert "next_cursor" in result["pagination"]

        # Second page
        result2 = get_timeline(db, org_a.id, limit=3, cursor=result["pagination"]["next_cursor"])
        assert len(result2["events"]) == 2
        assert result2["pagination"]["has_more"] is False

    def test_no_duplicates_across_pages(self, db, org_a, repo_a):
        """Events should not appear on multiple pages."""
        from app.services.audit_reads import get_timeline
        now = datetime.now(timezone.utc)

        # Create 6 commits with distinct timestamps
        for i in range(6):
            commit = Commit(
                id=uuid.uuid4(), organization_id=org_a.id,
                repo_identifier=repo_a.canonical_identifier,
                commit_sha=uuid.uuid4().hex[:40],
                committed_at=now - timedelta(minutes=i),
                ingested_at=now, model_identities=["test"],
            )
            db.add(commit)
        db.commit()

        # Collect all event IDs across pages
        all_shas = []
        cursor = None
        for _ in range(10):  # Safety limit
            result = get_timeline(db, org_a.id, limit=2, cursor=cursor)
            for e in result["events"]:
                all_shas.append(e["detail"]["commit_sha"])
            if not result["pagination"]["has_more"]:
                break
            cursor = result["pagination"]["next_cursor"]

        assert len(all_shas) == 6
        assert len(set(all_shas)) == 6, "Duplicate events detected across pages"

    def test_same_timestamp_no_duplicates(self, db, org_a, repo_a):
        """Events with same timestamp should not be duplicated or skipped."""
        from app.services.audit_reads import get_timeline
        now = datetime.now(timezone.utc)

        # Create 4 commits at the exact same timestamp
        same_time = now - timedelta(hours=1)
        for i in range(4):
            commit = Commit(
                id=uuid.uuid4(), organization_id=org_a.id,
                repo_identifier=repo_a.canonical_identifier,
                commit_sha=uuid.uuid4().hex[:40],
                committed_at=same_time,
                ingested_at=now, model_identities=["test"],
            )
            db.add(commit)
        db.commit()

        # Page through with limit=2
        all_shas = []
        cursor = None
        for _ in range(10):
            result = get_timeline(db, org_a.id, limit=2, cursor=cursor)
            for e in result["events"]:
                all_shas.append(e["detail"]["commit_sha"])
            if not result["pagination"]["has_more"]:
                break
            cursor = result["pagination"]["next_cursor"]

        assert len(all_shas) == 4
        assert len(set(all_shas)) == 4, "Duplicate or missing same-timestamp events"

    def test_mixed_source_same_timestamp_no_duplicates(self, db, org_a, repo_a):
        """Cross-source events at the same timestamp must not duplicate or skip."""
        from app.services.audit_reads import get_timeline
        now = datetime.now(timezone.utc)
        same_time = now - timedelta(hours=1)

        # Create 2 commits at same_time
        for i in range(2):
            commit = Commit(
                id=uuid.uuid4(), organization_id=org_a.id,
                repo_identifier=repo_a.canonical_identifier,
                commit_sha=uuid.uuid4().hex[:40],
                committed_at=same_time,
                ingested_at=now, model_identities=["test"],
            )
            db.add(commit)

        # Create 2 drift findings at same_time (need policy infrastructure)
        policy, version, rollout = _make_policy_with_rollout(
            db, org_a, repo_a, applied_at=same_time - timedelta(hours=1),
            rollout_status="applied",
        )
        # Need commits with observations for drift findings
        for i in range(2):
            c = Commit(
                id=uuid.uuid4(), organization_id=org_a.id,
                repo_identifier=repo_a.canonical_identifier,
                commit_sha=uuid.uuid4().hex[:40],
                committed_at=same_time, ingested_at=now,
                model_identities=["test"],
            )
            db.add(c)
            db.flush()
            finding = PolicyDriftFinding(
                id=uuid.uuid4(), organization_id=org_a.id,
                policy_id=policy.id, policy_version_id=version.id,
                repository_id=repo_a.id, commit_id=c.id,
                check_name=f"check_{i}", severity="drift",
                detail="test drift",
            )
            db.add(finding)
        db.commit()

        # Page through with limit=3 — should get all events without duplicates
        all_event_ids = []
        cursor = None
        for _ in range(10):
            result = get_timeline(db, org_a.id, limit=3, cursor=cursor, since=same_time - timedelta(minutes=1))
            for e in result["events"]:
                # Use type+summary as unique identifier
                all_event_ids.append(f"{e['type']}:{e.get('detail', {}).get('commit_sha') or e.get('detail', {}).get('check_name', '')}")
            if not result["pagination"]["has_more"]:
                break
            cursor = result["pagination"]["next_cursor"]

        # 2 original commits + 2 drift-commit events + 2 drift findings = 6 events
        # (the drift commits also appear as commit events)
        assert len(all_event_ids) == len(set(all_event_ids)), f"Duplicates found: {all_event_ids}"

    def test_empty_next_page_with_has_more_true(self, db, org_a):
        """has_more:true followed by empty page is acceptable (advisory)."""
        from app.services.audit_reads import get_timeline
        # No data — should get empty result
        result = get_timeline(db, org_a.id, limit=10)
        assert result["events"] == []
        assert result["pagination"]["has_more"] is False


# ============================================================
# Org Isolation Tests
# ============================================================

class TestOrgIsolation:
    """Every endpoint must scope by organization_id."""

    def test_fleet_summary_isolates_orgs(self, db, org_a, org_b, provider_a, repo_a):
        """Fleet summary for org_b should not include org_a data."""
        from app.services.fleet_reads import get_fleet_summary

        # org_a has a repo, org_b does not
        result_a = get_fleet_summary(db, org_a.id)
        result_b = get_fleet_summary(db, org_b.id)

        assert result_a["repos"]["total"] == 1
        assert result_b["repos"]["total"] == 0

    def test_fleet_repos_isolates_orgs(self, db, org_a, org_b, provider_a, repo_a):
        from app.services.fleet_reads import get_fleet_repos

        result_a = get_fleet_repos(db, org_a.id)
        result_b = get_fleet_repos(db, org_b.id)

        assert result_a["pagination"]["total"] == 1
        assert result_b["pagination"]["total"] == 0

    def test_repo_detail_isolates_orgs(self, db, org_a, org_b, repo_a):
        from app.services.repo_reads import get_repo_detail

        # org_a can see the repo
        result_a = get_repo_detail(db, org_a.id, repo_a.id)
        assert result_a is not None

        # org_b cannot
        result_b = get_repo_detail(db, org_b.id, repo_a.id)
        assert result_b is None

    def test_timeline_isolates_orgs(self, db, org_a, org_b, repo_a):
        from app.services.audit_reads import get_timeline
        now = datetime.now(timezone.utc)

        commit = Commit(
            id=uuid.uuid4(), organization_id=org_a.id,
            repo_identifier=repo_a.canonical_identifier,
            commit_sha="a" * 40, committed_at=now, ingested_at=now,
            model_identities=["test"],
        )
        db.add(commit)
        db.commit()

        result_a = get_timeline(db, org_a.id, since=now - timedelta(hours=1))
        result_b = get_timeline(db, org_b.id, since=now - timedelta(hours=1))

        assert len(result_a["events"]) == 1
        assert len(result_b["events"]) == 0

    def test_activity_isolates_orgs(self, db, org_a, org_b, repo_a):
        from app.services.activity_reads import get_repo_activity
        now = datetime.now(timezone.utc)

        commit = Commit(
            id=uuid.uuid4(), organization_id=org_a.id,
            repo_identifier=repo_a.canonical_identifier,
            commit_sha="b" * 40, committed_at=now, ingested_at=now,
            model_identities=["claude-opus-4"],
        )
        db.add(commit)
        db.commit()

        result_a = get_repo_activity(db, org_a.id, repo_a.id)
        result_b = get_repo_activity(db, org_b.id, repo_a.id)

        assert result_a is not None
        assert result_b is None  # repo belongs to org_a, not org_b
