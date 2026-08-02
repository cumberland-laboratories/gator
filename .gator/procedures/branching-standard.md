# Branching Standard

**Scope**: All repos governed by Gator Command.

## The Rule

**Fleet project repos**: `dev` is the default working branch. All agent work, feature development, and day-to-day commits happen on `dev`. `main` is the stable branch - merges to `main` are human-authorized only.

**Gator product source repo (`code2/gator-command`)**: use a split model.

- `main` remains the stable `Gator Individual` line and the base for public-facing deploy/build work
- substantial `Gator Enterprise` work happens on a dedicated long-lived feature branch
- the current Enterprise branch is: `enterprise-mvp`

This repo is no longer treated as a simple "stay on main" exception. The product has now split enough that `main` should stay relatively clean for Individual while Enterprise MVP development proceeds in parallel.

## Why

- **`main` stays clean** in fleet repos. It represents reviewed, intentional state.
- **`dev` is the workspace** in fleet repos. Agents and humans commit freely. When the Architect is satisfied, they merge to `main`.
- **`main` should also stay cleaner in the Gator product repo.** `Gator Individual` is now stable enough that Enterprise buildout should not flood the main history with unfinished service work.
- **A dedicated Enterprise branch keeps the product boundary legible.** It allows Fly deployments, service scaffolding, migrations, and Enterprise-only planning to move quickly without immediately muddying the stable Individual line.

## For Agents

### In fleet project repos

- Default branch for commits: `dev`
- Never push directly to `main` unless the Architect explicitly authorizes it
- If the repo has no `dev` branch yet, create it from `main` before starting work
- Pull requests, if used, target `main` from `dev`

### In the Gator product source repo

- Default stable branch: `main`
- Default Enterprise development branch: `enterprise-mvp`
- `main` is for stable Individual work, documentation, and selected shared changes
- Substantial Enterprise features, scaffolding, deployment work, and service-layer changes should go to `enterprise-mvp`
- If an Individual bug fix is made on `main` and Enterprise needs it, merge or rebase that change into `enterprise-mvp`
- Do not create many long-lived Enterprise sub-branches unless the work becomes too large for one branch

## For the Architect

- In fleet repos: merge `dev` -> `main` when you're ready to checkpoint
- In the Gator product repo: keep `main` as the stable Individual line and use `enterprise-mvp` as the active Enterprise build branch until the Enterprise surface is mature enough to merge deliberately
