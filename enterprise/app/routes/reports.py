"""Reporting routes — observations, drift findings, report snapshots."""

from fastapi import APIRouter, Depends
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.api_contract import ApiError, parse_uuid
from app.auth import verify_token
from app.db import get_db
from app.models.api_token import ApiToken
from app.models.commit import Commit
from app.models.commit_observation import CommitObservation
from app.models.drift_finding import PolicyDriftFinding
from app.models.ingest_job import IngestJob
from app.models.policy import Policy
from app.models.report_run import ReportRun
from app.models.report_snapshot import ReportSnapshot
from app.models.repository import Repository

router = APIRouter(tags=["reports"])


@router.get("/repos/{repo_id}/observations")
def list_repo_observations(
    repo_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """List observations for a repository."""
    rid = parse_uuid(repo_id, "repo_id")
    observations = db.execute(
        select(CommitObservation, Commit)
        .join(Commit, CommitObservation.commit_id == Commit.id)
        .where(
            CommitObservation.repository_id == rid,
            CommitObservation.organization_id == token.organization_id,
        )
        .order_by(desc(Commit.committed_at))
        .limit(50)
    ).all()

    return [
        {
            "id": str(row.CommitObservation.id),
            "commit_sha": row.Commit.commit_sha,
            "committed_at": row.Commit.committed_at.isoformat() if row.Commit.committed_at else None,
            "status_json_present": row.CommitObservation.status_json_present,
            "charter_count": row.CommitObservation.charter_count,
            "constitution_present": row.CommitObservation.constitution_present,
            "trailers": row.CommitObservation.trailers,
            "observation_status": row.CommitObservation.observation_status,
        }
        for row in observations
    ]


@router.get("/commits/{commit_id}/observation")
def get_commit_observation(
    commit_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Get the observation for a specific commit."""
    cid = parse_uuid(commit_id, "commit_id")
    observation = db.execute(
        select(CommitObservation).where(
            CommitObservation.commit_id == cid,
            CommitObservation.organization_id == token.organization_id,
        )
    ).scalar_one_or_none()

    if observation is None:
        raise ApiError(404, "not_found", "Observation not found")

    return {
        "id": str(observation.id),
        "commit_id": str(observation.commit_id),
        "status_json_present": observation.status_json_present,
        "status_json_hash": observation.status_json_hash,
        "charter_count": observation.charter_count,
        "charter_names": observation.charter_names,
        "constitution_present": observation.constitution_present,
        "trailers": observation.trailers,
        "observation_status": observation.observation_status,
        "error": observation.error,
    }


@router.get("/repos/{repo_id}/drift")
def list_repo_drift(
    repo_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """List drift findings for a repository."""
    rid = parse_uuid(repo_id, "repo_id")
    findings = db.execute(
        select(PolicyDriftFinding).where(
            PolicyDriftFinding.repository_id == rid,
            PolicyDriftFinding.organization_id == token.organization_id,
        )
        .order_by(desc(PolicyDriftFinding.created_at))
        .limit(100)
    ).scalars().all()

    return [
        {
            "id": str(f.id),
            "policy_id": str(f.policy_id),
            "policy_version_id": str(f.policy_version_id),
            "commit_id": str(f.commit_id),
            "check_name": f.check_name,
            "severity": f.severity,
            "expected": f.expected,
            "observed": f.observed,
            "detail": f.detail,
        }
        for f in findings
    ]


@router.get("/policies/{policy_id}/drift")
def list_policy_drift(
    policy_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """List drift findings for a policy."""
    pid = parse_uuid(policy_id, "policy_id")
    findings = db.execute(
        select(PolicyDriftFinding).where(
            PolicyDriftFinding.policy_id == pid,
            PolicyDriftFinding.organization_id == token.organization_id,
        )
        .order_by(desc(PolicyDriftFinding.created_at))
        .limit(100)
    ).scalars().all()

    return [
        {
            "id": str(f.id),
            "repository_id": str(f.repository_id),
            "commit_id": str(f.commit_id),
            "check_name": f.check_name,
            "severity": f.severity,
            "detail": f.detail,
        }
        for f in findings
    ]


@router.post("/reports/repos/{repo_id}")
def trigger_repo_report(
    repo_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Trigger repo governance report generation via worker."""
    rid = parse_uuid(repo_id, "repo_id")
    repo = db.execute(
        select(Repository).where(
            Repository.id == rid,
            Repository.organization_id == token.organization_id,
        )
    ).scalar_one_or_none()
    if repo is None:
        raise ApiError(404, "not_found", "Repository not found")

    db.add(IngestJob(
        organization_id=token.organization_id,
        job_type="generate_report",
        payload={"report_type": "repo", "target_id": str(repo.id)},
        status="pending",
    ))
    db.commit()
    return {"status": "report_queued", "repo": repo.canonical_identifier}


@router.post("/reports/policies/{policy_id}")
def trigger_policy_report(
    policy_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Trigger policy compliance report generation via worker."""
    pid = parse_uuid(policy_id, "policy_id")
    policy = db.execute(
        select(Policy).where(
            Policy.id == pid,
            Policy.organization_id == token.organization_id,
        )
    ).scalar_one_or_none()
    if policy is None:
        raise ApiError(404, "not_found", "Policy not found")

    db.add(IngestJob(
        organization_id=token.organization_id,
        job_type="generate_report",
        payload={"report_type": "policy", "target_id": str(policy.id)},
        status="pending",
    ))
    db.commit()
    return {"status": "report_queued", "policy": policy.slug}


@router.get("/reports/runs")
def list_report_runs(
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """List recent report runs."""
    runs = db.execute(
        select(ReportRun).where(
            ReportRun.organization_id == token.organization_id,
        )
        .order_by(desc(ReportRun.started_at))
        .limit(20)
    ).scalars().all()

    return [
        {
            "id": str(r.id),
            "run_type": r.run_type,
            "scope": r.scope,
            "status": r.status,
            "started_at": r.started_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in runs
    ]


@router.get("/reports/snapshots/{snapshot_id}")
def get_report_snapshot(
    snapshot_id: str,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Fetch a report snapshot."""
    sid = parse_uuid(snapshot_id, "snapshot_id")
    snapshot = db.execute(
        select(ReportSnapshot).where(
            ReportSnapshot.id == sid,
            ReportSnapshot.organization_id == token.organization_id,
        )
    ).scalar_one_or_none()

    if snapshot is None:
        raise ApiError(404, "not_found", "Snapshot not found")

    return {
        "id": str(snapshot.id),
        "report_run_id": str(snapshot.report_run_id),
        "snapshot_type": snapshot.snapshot_type,
        "scope": snapshot.scope,
        "content": snapshot.content,
        "content_hash": snapshot.content_hash,
        "created_at": snapshot.created_at.isoformat(),
    }
