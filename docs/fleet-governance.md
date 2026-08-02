# Fleet Governance

Fleet governance is how you manage multiple repos from a single Gator Command post. One source of truth for organizational policy, one place to check status across all governed projects.

## The Command Post

The command post is a Gator repo that governs other repos. It contains:

- **Organizational policy** (`org-policy.md`) — standards inherited by all fleet repos
- **Registry** (`registry.md`) — list of governed repos with paths and status
- **Knowledge layer** — mission, roadmap, threads, artifacts for cross-repo context
- **Scripts** — fleet-report, drift detection, audit, session archaeology

## Registering Repos

When you gatorize a project, it's automatically registered:

```bash
bash gator-engine/scripts/gatorize.sh ~/projects/my-api
```

The command post's `registry.md` now tracks this repo. You can also register remote-only repos that live on other machines.

## Fleet Report

See all governed repos at a glance:

```bash
python gator-engine/scripts/gator-fleet-report.py
```

```
  gator fleet-report
  4 repos registered

  ✓ service-api
    gen 2  |  charters: 4 (23 fn)  |  hooks: yes
    trailers: sig: notable | type: feature | charter: yes

  ✓ frontend
    gen 2  |  charters: 2 (8 fn)  |  hooks: yes

  ! data-pipeline
    gen 1  |  charters: 0  |  hooks: no
    ⚠ Generation drift. Run gator update.
```

## Drift Detection

Check which repos have fallen behind organizational standards:

```bash
python gator-engine/scripts/gator-drift.py
```

Drift detection compares:

- **Generation** — is the repo on the current Gator generation?
- **Hooks** — are pre-commit hooks installed and current?
- **Policy version** — does the repo reference current org policy?
- **Charter coverage** — are charters present and maintained?

## Remote Fleet Reporting

For teams with repos across multiple machines, remote fleet reporting uses `git fetch` and `git show` to read governance state without local checkouts:

```bash
python gator-engine/scripts/gator-fleet-report.py --remote
```

This reads `.gator/status.json`, committed session summaries, and trailers from remote refs. An engineering manager with 50 repos gets fleet governance without cloning everything.

## Thin Links

Each governed repo carries a thin link (`.gator/command-post.md`) that points back to the command post. This is how repos discover organizational policy and how the fleet stays connected.

The thin link contains:

- Path to the command post (local or remote)
- Policy version reference
- Generation marker

## Audit

Generate a governance report across the entire fleet:

```bash
python gator-engine/scripts/gator-audit.py
python gator-engine/scripts/gator-audit.py --html > audit.html
```

The audit aggregates:

- Fleet status and drift
- Session archaeology (AI decisions across vendors)
- Governance coverage (which repos are governed, which aren't)
- Recent decisions and override history
