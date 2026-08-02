#!/usr/bin/env python3
"""
gator-session-aggregator.py — Session summary aggregator.

Reads session snippets from repos, aggregates into session summaries,
caches at ~/.gator/sessions/<path-hash>/. Importable library — no CLI
entry point. Dashboard and CLI scripts import this.

@reads: .gator/session-snippets/*.json (per repo)
@reads: ~/.gator/dashboard-repos.json (fleet queries)
@writes: ~/.gator/sessions/<path-hash>/<esk-hash>.json (cached summaries)
@writes: ~/.gator/sessions/<path-hash>/_repo.json (repo metadata)
"""

import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GATOR_USER_DIR = Path.home() / ".gator"
SESSIONS_DIR = GATOR_USER_DIR / "sessions"

SIGNIFICANCE_ORDER = {"routine": 0, "minor": 1, "high": 2}

SKIP_CHANGE_TYPES_FOR_GOAL = {"release", "merge", "cleanup"}


# ---------------------------------------------------------------------------
# Session Identity
# ---------------------------------------------------------------------------

def effective_session_key(snippet):
    """Return the canonical grouping key for a snippet.

    Uses vendor session identity when available, falls back to legacy
    Gator session_id. The returned string is used for aggregation grouping,
    cache filenames, and fingerprint lookups.

    Returns:
        "group:<repo>:<session_group_key>" when session_group_key is truthy
        "legacy:<repo>:<session_id>" otherwise
    """
    repo = snippet.get("repo", "")
    sgk = snippet.get("session_group_key")
    if sgk:
        return f"group:{repo}:{sgk}"
    return f"legacy:{repo}:{snippet.get('session_id', '')}"


# ---------------------------------------------------------------------------
# 1a. Snippet Reader
# ---------------------------------------------------------------------------

def read_snippets(repo_path):
    """Read all v2 JSON session snippets from a repo.

    Returns list of SnippetRecord dicts:
        {"data": dict, "raw_bytes": bytes, "path": str}

    Skips legacy .md snippets, corrupt files, and files missing schema.
    """
    snippet_dir = Path(repo_path) / ".gator" / "session-snippets"
    if not snippet_dir.is_dir():
        return []

    records = []
    for f in sorted(snippet_dir.glob("*.json")):
        try:
            raw = f.read_bytes()
            data = json.loads(raw)
            if not isinstance(data, dict):
                continue
            schema = data.get("schema", "")
            if not schema.startswith("gator-session-snippet-"):
                continue
            records.append({
                "data": data,
                "raw_bytes": raw,
                "path": str(f),
            })
        except (json.JSONDecodeError, OSError) as exc:
            print(f"warning: skipping corrupt snippet {f.name}: {exc}",
                  file=sys.stderr)
    return records


# ---------------------------------------------------------------------------
# 1b. Grouping + Aggregation
# ---------------------------------------------------------------------------

def aggregate_sessions(snippets, repo_path):
    """Group snippets by effective_session_key() and aggregate into summaries.

    Uses vendor session_group_key when present, falls back to legacy
    Gator session_id. Snippets with different effective keys are never
    merged, even if timestamps or transcript IDs look similar.

    Args:
        snippets: list of parsed snippet dicts (the "data" from SnippetRecords)
        repo_path: resolved repo path for computing repo_key

    Returns list of summary dicts matching gator-session-summary-v1 schema.
    """
    # Group by effective_session_key
    groups = {}
    for s in snippets:
        key = effective_session_key(s)
        if key not in groups:
            groups[key] = []
        groups[key].append(s)

    repo_key = session_cache_key(repo_path)
    summaries = []

    for esk, group in groups.items():
        # Sort within group
        group.sort(key=lambda s: (
            s.get("started_at", ""),
            s.get("ended_at", ""),
            s.get("commit", ""),
        ))

        first = group[0]

        # Aggregate fields
        all_files = []
        all_tags = []
        all_intents = []
        all_notes = []
        all_change_types = set()
        all_models = set()
        max_sig = "routine"
        architect = ""
        transcript_session_id = None
        transcript_ref = None
        commits = []

        for s in group:
            # Commits list
            commits.append({
                "commit": s.get("commit", ""),
                "short_commit": s.get("short_commit", ""),
                "intent": s.get("intent", ""),
                "change_type": s.get("change_type", ""),
            })

            # Files touched — union
            for f in s.get("files_touched", []):
                if f not in all_files:
                    all_files.append(f)

            # Decision tags — union
            for t in s.get("decision_tags", []):
                if t not in all_tags:
                    all_tags.append(t)

            # Intents — ordered unique
            intent = s.get("intent", "")
            if intent and intent not in all_intents:
                all_intents.append(intent)

            # Notes — concatenated
            notes = s.get("notes", [])
            if isinstance(notes, list):
                all_notes.extend(notes)

            # Change types
            ct = s.get("change_type", "")
            if ct:
                all_change_types.add(ct)

            # Models — distinct
            model = s.get("model_inferred", "")
            if model:
                all_models.add(model)

            # Max significance
            sig = s.get("significance", "routine")
            if SIGNIFICANCE_ORDER.get(sig, 0) > SIGNIFICANCE_ORDER.get(max_sig, 0):
                max_sig = sig

            # First non-empty architect
            if not architect:
                architect = s.get("architect", "")

            # First non-empty transcript refs
            if not transcript_session_id:
                transcript_session_id = s.get("transcript_session_id")
            if not transcript_ref:
                transcript_ref = s.get("transcript_ref")

        # session_group_key: first non-null from the group (all should agree)
        session_group_key = None
        for s in group:
            sgk = s.get("session_group_key")
            if sgk:
                session_group_key = sgk
                break

        summary = {
            "schema": "gator-session-summary-v1",
            "session_id": first.get("session_id", ""),
            "session_group_key": session_group_key,
            "repo": first.get("repo", ""),
            "repo_key": repo_key,
            "branch": first.get("branch", ""),
            "vendor": first.get("vendor_inferred", ""),
            "model": first.get("model_inferred", ""),
            "models": sorted(all_models),
            "agent": first.get("agent", ""),
            "architect": architect,
            "started_at": min(s.get("started_at", "") for s in group),
            "ended_at": max(s.get("ended_at", "") for s in group),
            "goal": derive_goal(all_intents, commits),
            "commit_count": len(group),
            "commits": commits,
            "files_touched": sorted(all_files),
            "decision_tags": sorted(all_tags),
            "intents": all_intents,
            "significance": max_sig,
            "change_types": sorted(all_change_types),
            "machine_label": first.get("machine_label", ""),
            "transcript_session_id": transcript_session_id,
            "transcript_ref": transcript_ref,
            "notes": all_notes,
        }
        summaries.append(summary)

    return summaries


# ---------------------------------------------------------------------------
# 1c. Goal Derivation
# ---------------------------------------------------------------------------

def derive_goal(intents, commits):
    """Derive a session goal from intents and commits.

    Rules:
    1. Single unique non-empty intent → use it
    2. Multiple → prefer first whose change_type not in {release, merge, cleanup}
    3. None qualify → first non-empty intent
    4. Still empty → None
    """
    if not intents:
        return None

    if len(intents) == 1:
        return intents[0]

    # Build intent-to-change_type mapping from commits
    intent_types = {}
    for c in commits:
        intent = c.get("intent", "")
        if intent and intent not in intent_types:
            intent_types[intent] = c.get("change_type", "")

    # Prefer first intent whose change_type is not skip-listed
    for intent in intents:
        ct = intent_types.get(intent, "")
        if ct not in SKIP_CHANGE_TYPES_FOR_GOAL:
            return intent

    # Fall back to first intent
    return intents[0]


# ---------------------------------------------------------------------------
# 1d. Fingerprinting + Cache
# ---------------------------------------------------------------------------

def snippet_fingerprint(records):
    """Compute a deterministic fingerprint from snippet file contents.

    Hashes raw_bytes of each SnippetRecord individually, sorts hashes
    alphabetically, then hashes the combined result.
    """
    per_file = []
    for r in records:
        h = hashlib.sha256(r["raw_bytes"]).hexdigest()
        per_file.append(h)
    per_file.sort()
    combined = "|".join(per_file)
    final = hashlib.sha256(combined.encode()).hexdigest()
    return f"sha256:{final}"


def session_cache_key(repo_path):
    """Compute a stable 12-char hash of the resolved repo path."""
    resolved = str(Path(repo_path).resolve())
    return hashlib.sha256(resolved.encode()).hexdigest()[:12]


def cache_dir(repo_path):
    """Return the cache directory for a repo's session summaries."""
    return SESSIONS_DIR / session_cache_key(repo_path)


def write_repo_metadata(cache_path, repo_name, repo_path):
    """Write _repo.json metadata alongside cached summaries."""
    meta = {
        "name": repo_name,
        "path": str(Path(repo_path).resolve()),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path = cache_path / "_repo.json"
    _atomic_write(meta_path, json.dumps(meta, indent=2) + "\n")


def _esk_from_summary(summary):
    """Reconstruct the effective session key from a summary dict.

    Mirrors effective_session_key() but reads from summary fields
    instead of snippet fields.
    """
    repo = summary.get("repo", "")
    sgk = summary.get("session_group_key")
    if sgk:
        return f"group:{repo}:{sgk}"
    return f"legacy:{repo}:{summary.get('session_id', '')}"


def _summary_cache_filename(esk):
    """Build a cache filename from the effective session key.

    Hashes the full effective_session_key string to produce a stable,
    filesystem-safe filename. The key already encodes repo + identity.
    """
    h = hashlib.sha256(esk.encode()).hexdigest()[:16]
    return f"{h}.json"


def read_cached_summary(cache_path, esk):
    """Read a cached session summary, or return None."""
    summary_path = cache_path / _summary_cache_filename(esk)
    if not summary_path.exists():
        return None
    try:
        return json.loads(summary_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_cached_summary(cache_path, summary, esk):
    """Write a session summary to cache."""
    cache_path.mkdir(parents=True, exist_ok=True)
    filename = _summary_cache_filename(esk)
    summary_path = cache_path / filename
    _atomic_write(summary_path, json.dumps(summary, indent=2) + "\n")


def is_fresh(cached, current_fingerprint):
    """Check if a cached summary matches the current snippet fingerprint."""
    return cached.get("snippet_fingerprint") == current_fingerprint


def _atomic_write(path, content):
    """Write content to path via temp file for crash safety."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    fd_closed = False
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        fd_closed = True
        # On Windows, target must not exist for rename
        if path.exists():
            path.unlink()
        os.rename(tmp, str(path))
    except BaseException:
        if not fd_closed:
            try:
                os.close(fd)
            except OSError:
                pass
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ---------------------------------------------------------------------------
# 1e. Top-Level Orchestrator
# ---------------------------------------------------------------------------

def get_session_summaries(repo_path, force_refresh=False):
    """Get session summaries for a repo, using cache when fresh.

    Returns list of summary dicts sorted by started_at descending.
    """
    records = read_snippets(repo_path)
    if not records:
        return []

    snippets_data = [r["data"] for r in records]
    sessions = aggregate_sessions(snippets_data, repo_path)

    # Build a lookup: effective_session_key -> list of records (for fingerprinting)
    session_records = {}
    for r in records:
        key = effective_session_key(r["data"])
        if key not in session_records:
            session_records[key] = []
        session_records[key].append(r)

    cpath = cache_dir(repo_path)
    results = []
    wrote_any = False

    for summary in sessions:
        # Reconstruct the effective key from the summary's first snippet identity
        esk = _esk_from_summary(summary)
        recs = session_records.get(esk, [])
        fp = snippet_fingerprint(recs)

        if not force_refresh:
            cached = read_cached_summary(cpath, esk)
            if cached and is_fresh(cached, fp):
                results.append(cached)
                continue

        # Generate and cache
        summary["generated_at"] = datetime.now(timezone.utc).isoformat()
        summary["snippet_fingerprint"] = fp
        write_cached_summary(cpath, summary, esk)
        results.append(summary)
        wrote_any = True

    if wrote_any:
        # Derive repo name from first snippet or directory name
        repo_name = ""
        if records:
            repo_name = records[0]["data"].get("repo", "")
        if not repo_name:
            repo_name = Path(repo_path).name
        write_repo_metadata(cpath, repo_name, repo_path)

    # Sort by started_at descending
    results.sort(key=lambda s: s.get("started_at", ""), reverse=True)
    return results


def get_fleet_summaries(registry_path=None, force_refresh=False):
    """Get session summaries across all registered repos.

    Returns merged list sorted by started_at descending.
    """
    if registry_path:
        reg_path = Path(registry_path)
    else:
        reg_path = GATOR_USER_DIR / "dashboard-repos.json"

    if not reg_path.exists():
        return []

    try:
        data = json.loads(reg_path.read_text(encoding="utf-8"))
        repos = data.get("repos", [])
    except (json.JSONDecodeError, OSError):
        return []

    all_summaries = []
    for repo in repos:
        repo_path = repo.get("path", "")
        if not repo_path or not Path(repo_path).is_dir():
            continue
        try:
            summaries = get_session_summaries(repo_path, force_refresh=force_refresh)
            all_summaries.extend(summaries)
        except Exception as exc:
            print(f"warning: skipping repo {repo.get('name', repo_path)}: {exc}",
                  file=sys.stderr)

    all_summaries.sort(key=lambda s: s.get("started_at", ""), reverse=True)
    return all_summaries
