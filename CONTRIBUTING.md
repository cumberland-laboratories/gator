# Contributing to Gator

Thank you for your interest in Gator. We welcome bug reports, feature requests, and documentation improvements.

## Licensing

Gator is licensed under the **Apache License 2.0** (see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE)).

**By submitting any contribution**, you agree that:

1. You have the right to submit it under the Apache License 2.0.
2. Your contribution is licensed to the project and its users under the same Apache License 2.0.
3. You certify the contribution's provenance per the [Developer Certificate of Origin](https://developercertificate.org/) (DCO) — sign your commits with `git commit -s`. The `Signed-off-by:` line records the DCO attestation. Contributions without a DCO sign-off cannot be merged.

We do not require a separate CLA.

## Questions and Feedback

For install help, usage questions, product feedback, and open-ended discussion, use [Discussions](https://github.com/cumberland-laboratories/gator/discussions).

## Bug Reports

For something that's broken, open an [issue](https://github.com/cumberland-laboratories/gator/issues).

Please include:

- **What you were trying to do** (install, gatorize, commit, run a command)
- **What happened** (error message, unexpected behavior)
- **Your environment** (OS, Python version, Git version, AI coding tool)
- **Steps to reproduce** if possible

## Feature Requests

Open an issue with the `enhancement` label, or start a Discussion if the idea is still forming. Describe the problem you're trying to solve, not just the solution you want. Context helps us evaluate fit.

## Pull Requests

We're not accepting external PRs at this time. Gator is in early release and the architecture is still moving quickly. If you have a fix or improvement, open an issue first — we'll discuss approach before code.

This will change as the project stabilizes. When it does, PRs will need:
- DCO sign-off on every commit (`git commit -s`)
- Passing CI (Workflow A source CI runs pytest across supported OS × Python matrix)
- Governance discipline: charter updates alongside code changes (Gator's pre-commit hook enforces this locally; PRs to a governed branch will inherit the same expectation)

## Branching

- **`main`** is the release-anchor branch. Every commit on `main` MUST have a green `source-ci` run. Release tags (`vX.Y.Z-rcN`, `vX.Y.Z`) are cut from `main` only.
- **`dev`** is the working branch. Feature work, refactors, and bug fixes happen here. Push freely; `source-ci` runs on every push to `dev` too.
- When `dev` is green, fast-forward `main` to `dev`:

  ```bash
  git checkout main
  git merge --ff-only dev
  git push origin main
  ```

  If the fast-forward fails, someone else moved `main` — rebase `dev` onto `main` first (`git checkout dev && git rebase main`), then retry the merge.

- **Trivial edits** (typo fixes, single-line docs tweaks) may commit directly to `main` — pragmatism over ceremony. Anything non-trivial goes through `dev`.
- **Feature branches** off `dev` are fine when useful (`feat/xyz`), especially for larger changes or when you want to keep several small stacks in flight. Merge back to `dev` (either fast-forward or `--no-ff` for a merge commit), then dev → main as above.
- The `--migrate-layout` and other one-shot operations that mutate `.gator/` should always be run on `dev`, not `main`.

Solo maintainer note: this is a lightweight discipline, not full PR overhead. The point is that `main` stays green so anyone browsing the repo — external contributors, prospective users, `git bisect` — lands on validated commits.

## Source Header Policy

Gator does not require a full Apache 2.0 header on every source file. New source files SHOULD include an SPDX identifier line where practical:

```
# SPDX-License-Identifier: Apache-2.0
```

The root `LICENSE` and `NOTICE` are the canonical license grant. Do not remove or modify them.

## Security

See [SECURITY.md](SECURITY.md) for reporting security vulnerabilities.

## Code of Conduct

Be constructive. We're building governance tooling — the bar for professionalism is high.
