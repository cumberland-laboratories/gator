"""policies commands — list, get, pull, drift.

Runtime-split Phase 5b (2026-08-21): `pull` is the ~/.gator/ policy
channel's client half — fetch active org policies, land them machine-side
(~/.gator/enterprise/org-policies.json), report applied state to the
control plane, and (inside a governed repo) commit-record the applied
versions in .gator/policy-pin.json (schema gator-policy-pin-v1) so
"what policy governed this commit" stays provable from git history.
`drift` is the fleet query: who is on what, where is the drift.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from gator_enterprise_cli.output import print_json, print_kv, print_table

_MACHINE_ID_FILE = Path(os.path.expanduser("~/.gator/machine-id"))


def _find_repo_root(start=None):
    """Walk up from `start` (default cwd) to the governed repo root.

    Whiteboard 2026-08-22 Finding 1: a bare `Path.cwd() / ".gator"` check
    silently dropped the pin + repo-scoped report from any subdirectory.
    Local walk-up (this package cannot import gator_core) — same pattern
    as gator-approve.py's find_gator_dir. Returns the repo root Path or
    None.
    """
    d = Path(start or Path.cwd()).resolve()
    # Uncapped walk to the filesystem root — whiteboard 2026-08-22 r2:
    # the r1 fix kept a 10-hop cap (inherited from gator-approve's
    # pattern) while the canonical gator_core.find_gator_root walks all
    # parents; a deeply nested working dir would re-trigger the exact
    # silent-skip this fix was meant to eliminate.
    if (d / ".gator").is_dir():
        return d
    for parent in d.parents:
        if (parent / ".gator").is_dir():
            return parent
    return None


def _read_machine_id():
    """Best-effort `id:` field from ~/.gator/machine-id, else None."""
    try:
        for line in _MACHINE_ID_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("id:"):
                return line.split(":", 1)[1].strip() or None
    except OSError:
        pass
    return None


def _write_org_policies(enterprise_dir, items):
    """Land the pulled policies machine-side. Returns the file path."""
    enterprise_dir = Path(enterprise_dir)
    enterprise_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "pulled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "policies": items,
    }
    dest = enterprise_dir / "org-policies.json"
    dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return dest


def _write_policy_pin(gator_dir, items, machine_id):
    """Commit-side record of the applied policy versions (Phase 5b).

    Mirrors the runtime pin: schema-tagged, hash-carrying, committed —
    the Git proof surface for "what policy governed this commit". Content
    itself is NOT embedded (policies can be large; the hash is the proof;
    the control plane and org-policies.json hold the content).
    """
    pin = {
        "schema": "gator-policy-pin-v1",
        "pulled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pulled_by_machine": machine_id,
        "policies": [
            {"slug": i["slug"], "version_number": i["version_number"],
             "content_hash": i["content_hash"]}
            for i in items
        ],
    }
    dest = Path(gator_dir) / "policy-pin.json"
    dest.write_text(json.dumps(pin, indent=2) + "\n", encoding="utf-8")
    return dest


def register(subparsers):
    """Register policies subcommands."""
    pol_parser = subparsers.add_parser("policies", help="Policy management")
    pol_sub = pol_parser.add_subparsers(dest="policies_command")

    pol_sub.add_parser("list", help="List all policies")

    get = pol_sub.add_parser("get", help="Get policy detail")
    get.add_argument("policy_id", help="Policy UUID")

    pull = pol_sub.add_parser(
        "pull",
        help="Pull active org policies to this machine + report applied state",
    )
    pull.add_argument(
        "--repo-id", default=None,
        help="Repo canonical id for the repo-scoped state report "
             "(default when run inside a governed repo: local/<dirname>)",
    )

    drift = pol_sub.add_parser(
        "drift", help="Fleet policy drift: who is on what, who is behind")
    drift.add_argument("--machine-id", default=None)
    drift.add_argument("--policy", default=None, help="Filter by policy slug")


def handle(args, client):
    """Handle policies commands."""
    if args.policies_command == "list":
        data = client.get("/api/v1/policies")
        if args.json:
            print_json(data)
        else:
            rows = [
                [
                    p["id"][:8],
                    p["name"],
                    p["slug"],
                    p["status"],
                    str(p.get("version_count", 0)),
                ]
                for p in data
            ]
            print_table(["ID", "Name", "Slug", "Status", "Versions"], rows)

    elif args.policies_command == "pull":
        _handle_pull(args, client)

    elif args.policies_command == "drift":
        _handle_drift(args, client)

    elif args.policies_command == "get":
        data = client.get(f"/api/v1/policies/{args.policy_id}")
        if args.json:
            print_json(data)
        else:
            av = data.get("active_version")
            print_kv([
                ("ID", data["id"]),
                ("Name", data["name"]),
                ("Slug", data["slug"]),
                ("Status", data["status"]),
                ("Versions", str(data.get("version_count", 0))),
                ("Active version", f"v{av['version_number']} ({av['content_hash'][:12]})" if av else "none"),
                ("Created", data.get("created_at", "—")),
            ])


def _handle_pull(args, client):
    machine_id = _read_machine_id()
    data = client.get("/api/v1/policies/active")
    items = data.get("items", [])
    noun = "policy" if len(items) == 1 else "policies"
    print(f"Pulled {len(items)} active {noun}")

    enterprise_dir = Path(os.path.expanduser("~/.gator/enterprise"))
    dest = _write_org_policies(enterprise_dir, items)
    print(f"  landed -> {dest}")

    # Machine-level entries; the machine scope is ALWAYS fully reported
    # (replace semantics) so retired policies clear (Finding 2).
    entries = [{"policy_slug": i["slug"], "content_hash": i["content_hash"],
                "repo_identifier": ""} for i in items]
    replace_scopes = [""]

    # Repo-scoped: inside a governed repo (root resolved by walk-up —
    # Finding 1: subdirectory pulls must behave identically), pin +
    # report per-repo. The pin is written even when items is empty —
    # the empty pin is the honest record that NO org policy is in force.
    repo_root = _find_repo_root()
    repo_identifier = args.repo_id
    if repo_root is not None:
        if not repo_identifier:
            repo_identifier = f"local/{repo_root.name}"
        pin_path = _write_policy_pin(repo_root / ".gator", items, machine_id)
        print(f"  policy pin -> {pin_path} (commit this — it is the Git-side "
              f"proof of the policy in force)")
        entries += [{"policy_slug": i["slug"],
                     "content_hash": i["content_hash"],
                     "repo_identifier": repo_identifier} for i in items]
        replace_scopes.append(repo_identifier)

    if not machine_id:
        print("  state report skipped: no ~/.gator/machine-id (run `gator "
              "init` in a governed repo first)")
        return

    report = client.post("/api/v1/policy-state/report",
                         json={"machine_id": machine_id, "entries": entries,
                               "replace_scopes": replace_scopes})
    results = report.get("results", [])
    drifted = [r for r in results
               if r.get("status") != "error" and not r.get("in_sync")]
    errors = [r for r in results if r.get("status") == "error"]
    cleared = report.get("cleared", 0)
    noun = "entry" if len(results) == 1 else "entries"
    print(f"  state reported: {len(results)} {noun} "
          f"({len(drifted)} drifted, {len(errors)} errors, "
          f"{cleared} retired cleared)")


def _handle_drift(args, client):
    params = []
    if args.machine_id:
        params.append(f"machine_id={args.machine_id}")
    if args.policy:
        params.append(f"policy={args.policy}")
    qs = ("?" + "&".join(params)) if params else ""
    data = client.get(f"/api/v1/policy-state/drift{qs}")
    if getattr(args, "json", False):
        print_json(data)
        return
    items = data.get("items", [])
    if not items:
        print(f"No drift. ({data.get('reported_total', 0)} reported "
              f"state(s) all in sync)")
        return
    rows = [[i["machine_id"][:12], i["repo_identifier"] or "(machine)",
             i["policy_slug"],
             f"v{i['applied_version_number']}",
             f"v{i['active_version_number']}" if i["active_version_number"] else "retired",
             i["reported_at"][:19]]
            for i in items]
    print_table(["Machine", "Scope", "Policy", "Applied", "Active", "Reported"],
                rows)
    print(f"\n({data['total']} drifted of {data['reported_total']} reported)")
