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
