# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |
| < 1.0   | No        |

## Reporting a Vulnerability

If you discover a security vulnerability in Gator, please report it responsibly.

**Do not open a public issue.**

Email: **security@cumberlandlaboratories.com**

Include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will acknowledge receipt within 48 hours and provide a timeline for resolution.

## Scope

Gator runs entirely locally. There are no network calls during governance operations. The security surface is:

- **Git hooks** — pre-commit, commit-msg, post-commit scripts that execute during `git commit`
- **CLI scripts** — Python scripts that read filesystem and git state
- **Session extraction** — reads from AI tool storage directories (`~/.claude/`, `~/.codex/`, `~/.gemini/`)

Gator does not transmit source code, session data, or governance metadata to any external service.
