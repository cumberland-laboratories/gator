"""Model activity read-model service — heuristic commit-derived AI model activity.

IMPORTANT: This is NOT a session model. Enterprise has no durable session ID,
no session start/end events, and no session-snippet pipeline. This endpoint
derives model activity from commit metadata (model_identities JSONB) only.

The word "session" must not appear in endpoint paths, response keys, or docs
for this service. Use "activity" throughout.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, func, select, text
from sqlalchemy.orm import Session

from app.models.commit import Commit
from app.models.commit_observation import CommitObservation
from app.models.repository import Repository


def get_repo_activity(
    db: Session,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    model_filter: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 30,
    offset: int = 0,
) -> dict | None:
    """Model commit activity for a repo, grouped by day.

    Confidence level: heuristic. Derived from commit metadata only.
    """
    repo = db.execute(
        select(Repository).where(
            Repository.id == repo_id,
            Repository.organization_id == org_id,
        )
    ).scalar_one_or_none()

    if repo is None:
        return None

    # Base query — commits for this repo
    filters = [
        Commit.organization_id == org_id,
        Commit.repo_identifier == repo.canonical_identifier,
    ]

    if model_filter:
        # Filter to commits involving this model.
        # model_identities can contain either plain strings or dicts with "name" key:
        #   ["claude-opus-4", ...]  OR  [{"name": "claude-opus-4"}, ...]
        # Use OR with JSONB containment (@>) to match both forms.
        import json
        from sqlalchemy import or_
        from sqlalchemy.sql.expression import cast
        from sqlalchemy.dialects.postgresql import JSONB as JSONB_TYPE
        filters.append(
            or_(
                # Array of strings: ["claude-opus-4", ...]
                Commit.model_identities.op("@>")(
                    cast(json.dumps([model_filter]), JSONB_TYPE)
                ),
                # Array of dicts: [{"name": "claude-opus-4"}, ...]
                Commit.model_identities.op("@>")(
                    cast(json.dumps([{"name": model_filter}]), JSONB_TYPE)
                ),
            )
        )

    if since:
        filters.append(Commit.committed_at >= since)
    if until:
        filters.append(Commit.committed_at <= until)

    # Get commits ordered by date
    commits = db.execute(
        select(Commit)
        .where(*filters)
        .order_by(desc(Commit.committed_at))
    ).scalars().all()

    # Group by calendar day
    days: dict[str, list] = {}
    for c in commits:
        if c.committed_at is None:
            continue
        day_key = c.committed_at.strftime("%Y-%m-%d")
        if day_key not in days:
            days[day_key] = []
        days[day_key].append(c)

    # Build activity rows
    activity = []
    sorted_days = sorted(days.keys(), reverse=True)

    # Apply pagination to days
    total = len(sorted_days)
    page_days = sorted_days[offset:offset + limit]

    for day_key in page_days:
        day_commits = days[day_key]

        # Collect all distinct models from this day's commits
        all_models = set()
        for c in day_commits:
            if c.model_identities and isinstance(c.model_identities, list):
                for m in c.model_identities:
                    if isinstance(m, str):
                        all_models.add(m)
                    elif isinstance(m, dict) and "name" in m:
                        all_models.add(m["name"])

        # Governance depth
        commit_ids = [c.id for c in day_commits]
        observations = db.execute(
            select(CommitObservation).where(
                CommitObservation.commit_id.in_(commit_ids),
                CommitObservation.observation_status == "observed",
            )
        ).scalars().all()

        obs_by_commit = {o.commit_id: o for o in observations}
        commits_with_trailers = sum(
            1 for o in observations if o.trailers
        )
        commits_with_obs = len(observations)
        charter_counts = [o.charter_count for o in observations if o.charter_count is not None]
        avg_charter = sum(charter_counts) / len(charter_counts) if charter_counts else 0.0

        timestamps = [c.committed_at for c in day_commits if c.committed_at]
        activity.append({
            "date": day_key,
            "models": sorted(all_models),
            "commit_count": len(day_commits),
            "first_commit_at": min(timestamps).isoformat() if timestamps else None,
            "last_commit_at": max(timestamps).isoformat() if timestamps else None,
            "governance_depth": {
                "commits_with_trailers": commits_with_trailers,
                "commits_with_observations": commits_with_obs,
                "avg_charter_count": round(avg_charter, 1),
            },
        })

    # Model summary — across all matching commits (not just this page)
    model_counts: dict[str, int] = {}
    for c in commits:
        if c.model_identities and isinstance(c.model_identities, list):
            for m in c.model_identities:
                name = m if isinstance(m, str) else (m.get("name", "unknown") if isinstance(m, dict) else str(m))
                model_counts[name] = model_counts.get(name, 0) + 1

    model_summary = [
        {"model": name, "commits_involving": count}
        for name, count in sorted(model_counts.items(), key=lambda x: -x[1])
    ]

    return {
        "repo": {"id": str(repo.id), "name": repo.name},
        "activity": activity,
        "model_summary": model_summary,
        "pagination": {"offset": offset, "limit": limit, "total": total},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "_heuristic": "Activity derived from commit metadata. Not true sessions. See API docs.",
    }
