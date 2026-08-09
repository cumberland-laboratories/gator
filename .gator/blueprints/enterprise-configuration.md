# Enterprise Configuration

> **HISTORICAL — pre-transcripts-first (2026-08-08).** This blueprint maps the Enterprise configuration model as it existed on the `enterprise-mvp` line and was carried into the monorepo. The current transcripts-first MVP does NOT follow this model:
> - session-block generation and per-commit envelope encryption are RETIRED as the evidence path (see [`../vault/artifacts/2026-08-08-enterprise-transcripts-first-mvp-implementation-plan.md`](../vault/artifacts/2026-08-08-enterprise-transcripts-first-mvp-implementation-plan.md) §2 D2 OBSOLETE list)
> - `.gator/session-blocks/` stays gitignored; evidence lives in Enterprise-managed storage (DB + blob)
> - `_fix_gitignore()` in `repo_init.py` (retiring per stabilization plan Phase 4 P1.2) is the last active vestige of the "commit session-blocks to Git" design
>
> Retained here as reference for the pre-transcripts-first architecture — useful for tracing legacy code paths and understanding why the current code base still contains block-related surfaces. Do NOT use this document as guidance for new work. For the current design, read the MVP plan + ADR at [`../vault/artifacts/2026-08-08-enterprise-transcripts-first-adr.md`](../vault/artifacts/2026-08-08-enterprise-transcripts-first-adr.md).

## What This Page Is

This page maps the Enterprise configuration model that was set up on the old `enterprise-mvp` line and then carried into the monorepo.

It is not a marketing overview. It is a flow map for:

- how a machine becomes Enterprise-active
- what local machine state gets created
- how repo provisioning was designed to work
- how policy and crypto state sync down from the Enterprise server
- what files are repo-scoped versus machine-scoped

This is the right page to read when the question is:

> What exactly was the Enterprise setup/configuration model supposed to be?

## Core Position

The Enterprise setup model was designed around three distinct scopes:

1. **Server scope**
   The Enterprise control plane owns provider integration, policy, evidence indexing, reporting, org-scoped key material, and machine-key registry.

2. **Machine scope**
   A developer machine is activated once. That creates `~/.gator/enterprise/` state, installs global git hooks, caches policy, and stores credentials and crypto material.

3. **Repo scope**
   A repo is provisioned separately. That creates a minimal `.gator/` footprint in the repo so machine-level hooks and Enterprise sync can identify and govern it.

This is a deliberate configuration split. Enterprise was not designed as "put everything in the repo." It was designed as:

- machine-local activation
- repo-local markers and scripts
- server-side control plane

## The Three-Step Configuration Model

The intended setup sequence was:

1. `gator-enterprise activate`
2. `gator-enterprise sync`
3. `gator-enterprise repo init <path>`

In practice, `activate` already calls `sync`, and `repo init` tries to register hook policy and sync again. But conceptually those are still the three configuration phases.

## Step 1: Machine Activation

### What it does

`gator-enterprise activate`

This is the one-time machine setup step.

Its job is to make the local machine Enterprise-capable before any repo is provisioned.

### Flow

1. **CLI activate command** → `enterprise/enterprise-cli/gator_enterprise_cli/commands/activate.py::_do_activate()`
   Creates the machine-local directory structure under `~/.gator/`.
   → [Enterprise CLI](../charters/scripts-enterprise.md)

2. **Global hook install**
   Writes machine-global git hooks under `~/.gator/hooks/`:
   - `pre-commit`
   - `commit-msg`
   - `post-commit`

   These wrappers:
   - no-op outside governed repos
   - read `.gator/repo-id`
   - read `~/.gator/enterprise/hook-policy.json`
   - set `GATOR_HOOK_MODE`
   - invoke repo-local `.gator/scripts/gator-pre-commit.py`

3. **Git global hook path**
   `activate` sets `git config --global core.hooksPath <home>/.gator/hooks`
   so the machine uses Enterprise-managed wrappers for every repo.

4. **Enterprise config file**
   Writes `~/.gator/enterprise/config.json`
   containing the Enterprise server URL and activation timestamp.

5. **Hook-policy cache bootstrap**
   Initializes `~/.gator/enterprise/hook-policy.json`
   so hook wrappers have a machine-local policy cache to consult.

6. **Machine identity and crypto bootstrap**
   Reads or creates `~/.gator/machine-id`.
   Generates machine key material under:
   - `~/.gator/enterprise/keys/machine-private-key.pem`
   - `~/.gator/enterprise/keys/machine-public-key.pem`

   Then attempts machine-key registration with the Enterprise API.

7. **CLI interpreter pin**
   Writes `~/.gator/enterprise/cli-python-path`
   so post-commit block generation can use the same interpreter that has the Enterprise CLI environment and crypto dependencies installed.

8. **Policy sync**
   Calls `_do_sync()` at the end of activation.

## Step 2: Machine Sync

### What it does

`gator-enterprise sync`

This refreshes machine-local Enterprise policy/cache state from the server.

### Flow

1. **Hook policy fetch** → `GET /api/v1/hook-policy`
   Writes `~/.gator/enterprise/hook-policy.json`

2. **Org policy fetch** → `GET /api/v1/org-policies`
   Writes markdown policy files to:
   - `~/.gator/enterprise/policies/<slug>.md`

3. **Crypto policy fetch** → `GET /api/v1/crypto/policy`
   Writes:
   - `~/.gator/enterprise/crypto-policy.json`
   - `~/.gator/enterprise/org-keys/org-public-key.pem` when present

### Why this matters

The machine-global hook wrappers do not reach back to the server on every commit.

They rely on:

- local hook-policy cache
- local org policy cache
- local crypto policy cache

That is an important design point: Enterprise setup was meant to make commit-time behavior mostly local and deterministic.

## Step 3: Repo Provisioning

### What it does

`gator-enterprise repo init <path>`

This provisions a specific git repo for Enterprise governance.

### Flow

1. **Repo verification** → `enterprise/enterprise-cli/gator_enterprise_cli/commands/repo_init.py::_do_repo_init()`
   Confirms the target has a `.git/` directory.

2. **Canonical repo identifier**
   Derives a canonical repo ID from `git remote origin` when not explicitly supplied.
   SSH/HTTPS forms are normalized.

3. **Repo-local `.gator/` footprint**
   Creates:
   - `.gator/repo-id`
   - `.gator/org-policy.md`
   - `.gator/session-snippets/`
   - `.gator/session-blocks/`
   - `.gator/scripts/`

4. **Bundled script install**
   Copies repo-local hook/runtime scripts into `.gator/scripts/`
   from the Enterprise CLI bundled scripts package unless an explicit script source is provided.

5. **Agent entry files**
   Creates or preserves:
   - `CLAUDE.md`
   - `AGENTS.md`

   These are lightweight Enterprise instructions pointing the agent toward org policy and the repo-local policy pointer.

6. **Gitignore correction**
   Removes stale `.gator/session-blocks/` ignore rules if present.
   This reflects the repo-first evidence design: session blocks were meant to be committed, not ignored.

7. **Auto-stage**
   Stages the newly provisioned files with `git add`.

8. **Optional policy registration**
   Attempts to register the repo's hook mode with the Enterprise server.
   Then triggers a sync so the local machine cache sees the resulting policy.

## The Resulting Configuration Surfaces

## Machine-local Enterprise state

Expected machine-local state:

```text
~/.gator/
  machine-id
  hooks/
    pre-commit
    commit-msg
    post-commit
  enterprise/
    config.json
    hook-policy.json
    crypto-policy.json
    cli-python-path
    credentials.json
    policies/
      *.md
    org-keys/
      org-public-key.pem
    keys/
      machine-private-key.pem
      machine-public-key.pem
```

### Why this is machine-local

These files are:

- environment-specific
- secret-bearing or trust-bearing
- unsuitable for Git
- intended to support many repos on one machine

This scope includes:

- credentials
- hook-policy cache
- org-policy cache
- crypto policy
- machine private key
- global hook wrappers

## Repo-local Enterprise state

Expected repo-local state after `repo init`:

```text
.gator/
  repo-id
  org-policy.md
  scripts/
    gator-pre-commit.py
    gator-session-block.py
    ...
  session-snippets/
  session-blocks/
CLAUDE.md
AGENTS.md
```

### Why this is repo-local

These files define how a specific repo participates in Enterprise governance.

They provide:

- repo identity
- repo-local hook/runtime scripts
- evidence landing zones
- repo-visible guidance for agents

The repo does **not** own:

- credentials
- org private keys
- machine private keys
- hook-policy authority

Those remain machine-local or server-side.

## Server-side configuration/state

The Enterprise control plane owns:

- API token auth
- provider integrations
- repo inventory and reconcile
- hook-policy authority
- org policy documents
- machine-key registry
- org encryption keys
- evidence indexing
- drift evaluation
- reporting and fleet views

The old repo's Enterprise charter and E8 artifacts show this clearly:

- `enterprise/app/routes/hook_policy.py`
- `enterprise/app/routes/policies.py`
- `enterprise/app/routes/crypto.py`
- `enterprise/app/routes/views.py`
- `enterprise/app/services/sync.py`
- `enterprise/app/services/session_blocks.py`

## Commit-Time Behavior After Configuration

Once machine activation and repo provisioning are both in place, commit-time behavior was intended to work like this:

1. Global hook wrapper runs because `core.hooksPath` points at `~/.gator/hooks/`
2. Wrapper checks whether the current repo has `.gator/scripts/gator-pre-commit.py`
3. Wrapper reads `.gator/repo-id`
4. Wrapper reads `~/.gator/enterprise/hook-policy.json`
5. Wrapper sets `GATOR_HOOK_MODE`
6. Wrapper invokes repo-local `gator-pre-commit.py`
7. Post-commit path also invokes session-block generation
8. Session blocks are staged for the next commit

For encrypted-block-capable setups, the post-commit wrapper prefers the CLI interpreter pinned in `~/.gator/enterprise/cli-python-path` so the Enterprise block generator can use crypto dependencies reliably.

## Credentials Model

There are two distinct Enterprise participation facts:

1. **Repo participates**
   Recorded by repo-local Enterprise markers/config.

2. **Machine is authorized**
   Recorded by machine-local credentials and sync state.

The credentials store lives at:

- `~/.gator/enterprise/credentials.json`

Owned by:

- `enterprise/enterprise-cli/gator_enterprise_cli/credentials.py`

This is deliberately machine-scoped. A repo should not carry API bearer credentials in Git.

## Hook Model

The Enterprise setup model intentionally used two hook layers:

1. **Machine-global git hooks**
   Installed once by `activate`
   Stored under `~/.gator/hooks/`
   Enabled via global `core.hooksPath`

2. **Repo-local session-start hooks**
   Installed into vendor configs
   Intended to call repo-local `.gator/scripts/gator-session-open.py` and `gator-session-start.py`

This split is important:

- git hooks are machine-global and fire on every commit
- vendor SessionStart hooks are vendor-tool-specific and fire at session start

Both were meant to cooperate through repo-local `.gator/scripts/` plus machine-local Enterprise cache/config.

## Encryption / E8 Configuration Extension

The E8 design artifacts extended the setup model further.

After E8, the Enterprise configuration story included:

- machine keypair generated during `activate`
- machine public key registered with Enterprise
- org public key synced down during `sync`
- machine-local crypto policy cache
- encrypted session blocks with:
  - org recipient
  - origin-machine recipient

That means the Enterprise configuration model was not just "connect to server."

It was also:

- establish machine identity
- establish machine trust material
- establish local decrypt capability
- establish Enterprise-side decrypt capability

## Key Charters And Artifacts

Primary charter:

- [Enterprise CLI](../charters/scripts-enterprise.md)

Related blueprints:

- [Session-Block Capture](session-block-capture.md)
- [Hook Pipeline](hook-pipeline.md)
- [Commit Pipeline](commit-pipeline.md)

Primary older source materials used for this synthesis:

- old `enterprise-service.md` charter from `code2/gator-command`
- old E8 sketch and implementation plan from `code2/gator-command/gator-command/artifacts/`

## Invariants

- Machine credentials are machine-local, never repo-local.
- Machine private keys are machine-local, never committed.
- Repo-local `.gator/` state is a participation/configuration surface, not an authority surface.
- Machine-global git hooks must degrade cleanly on ungoverned repos.
- Repo-local `.gator/repo-id` is the bridge between the current repo and machine-local hook-policy cache.
- Policy and crypto behavior at commit time should depend on machine-local synced cache, not on live server availability.
- Session-block evidence was designed to be repo-first, not gitignored.

## Bottom Line

The Enterprise configuration model that existed on the old `enterprise-mvp` line was a three-scope system:

- **server authority**
- **machine activation and cache**
- **repo provisioning**

That is the right mental model for the latent Enterprise code today. The work ahead is not inventing configuration from nothing. It is hardening and clarifying a configuration architecture that was already substantially defined.
