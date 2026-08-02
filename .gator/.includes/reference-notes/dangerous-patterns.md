# Dangerous Patterns Reference

Patterns the agent must surface to the Architect before writing, running, or committing. This applies to all session activity — not just commits.

The pre-commit hook catches these mechanically at commit time. This reference note governs agent behavior *during* the session: writing scripts, running commands, debugging, executing code.

**Rule**: If the agent encounters any of these patterns in code it is about to write or execute, it stops and asks the Architect before proceeding. If the Architect approves, the agent logs the approval in `commit_draft.md`.

## Credentials in the Conversation (Highest Priority)

This is not a code pattern — it's a conversation-level security boundary.

**If the Architect pastes a password, API key, token, private key, or any secret directly into a chat message, the agent must immediately stop and warn:**

> **STOP — Credential Exposure**
> The credential you just pasted has been transmitted to [provider] via the API request. It should be considered compromised regardless of what happens next. Rotate this credential immediately. I will not use, store, or repeat it.

**Why this is the highest priority pattern**: Every other dangerous pattern in this catalog can be caught before damage occurs. A credential pasted into the conversation is compromised *the instant the message is sent* — before the agent even sees it. There is no undo. The credential is in the provider's request logs, potentially in training data pipelines, and must be treated as leaked.

The agent cannot prevent the exposure (it happens before the agent responds), but it can:
1. Warn immediately so the Architect rotates fast
2. Refuse to use the credential (don't embed it in code, don't pass it to scripts)
3. Not repeat the credential in its response (avoid amplifying the exposure)

**Common scenarios**: Architect debugging auth failures pastes the raw token. Architect setting up a new service pastes the API key. Architect shares a `.env` file contents. Architect copies a database connection string with embedded password. All of these are compromised on paste.

## Secrets & Credentials (in Code)

| Pattern | Why it's dangerous |
|---|---|
| Hardcoded passwords (`password = "..."`) | Credentials in source code leak via git history, logs, and clones |
| API keys/tokens in source (`api_key = "sk-..."`) | Same as passwords — once committed, consider them compromised |
| Private key material (`-----BEGIN PRIVATE KEY-----`) | Cryptographic keys in source are permanent compromise vectors |
| `.env` files in commits | Environment files contain secrets that should never enter version control |

## Destructive Data Operations

| Pattern | Why it's dangerous |
|---|---|
| `DROP TABLE` | Destroys table and all data. Irreversible without backup |
| `DELETE FROM` without `WHERE` | Deletes all rows in a table. Usually a mistake |
| `TRUNCATE TABLE` | Fast bulk deletion. Irreversible, not logged in transaction log on some DBs |
| `ALTER TABLE ... DROP COLUMN` | Destroys column data. May break dependent queries silently |
| `UPDATE` without `WHERE` | Overwrites all rows. Usually a mistake |

## Code Execution Risks

| Pattern | Why it's dangerous |
|---|---|
| `eval()` | Executes arbitrary code. If input is untrusted, this is remote code execution |
| `exec()` | Same as eval but for statements. Same risk |
| `subprocess` with `shell=True` | Shell injection — user input can escape into shell commands |
| `os.system()` | Same as shell=True subprocess but harder to parameterize safely |
| SQL string concatenation (`f"SELECT ... {user_input}"`) | SQL injection. Use parameterized queries |

## Destructive System Operations

| Pattern | Why it's dangerous |
|---|---|
| `rm -rf` / `shutil.rmtree()` | Recursive deletion. One wrong path = catastrophic data loss |
| `git reset --hard` | Discards all uncommitted changes. Cannot be undone |
| `git push --force` | Overwrites remote history. Can destroy other people's work |
| `git clean -f` | Deletes untracked files. May include work not yet staged |
| `chmod 777` / wide-open permissions | Security regression — makes files world-writable |
| Disk formatting / partition operations | Catastrophic and irreversible |

## Network & External Service Risks

| Pattern | Why it's dangerous |
|---|---|
| Sending emails/messages programmatically | Can't unsend. May go to wrong recipients |
| API calls that create/delete external resources | Cloud resources cost money and may be hard to recover |
| Webhook registrations | May expose internal systems to external triggers |
| DNS changes | Propagation delays make mistakes hard to reverse quickly |

## What the Agent Does

1. **Before writing**: If the agent is about to write code containing a dangerous pattern, it tells the Architect what it's about to write and why, and waits for confirmation.

2. **Before executing**: If the agent is about to run a script, command, or test that contains a dangerous pattern (even if the code already exists), it surfaces the pattern and waits. This is especially important during debugging — "let me just run the migration script to see what happens" is exactly when accidents occur.

3. **After Architect approval**: Log the approval in `commit_draft.md` with the pattern, the file, and the Architect's attribution. Example:
   ```
   - Architect approved DELETE FROM in tests/cleanup.py — test fixture teardown [#security] [#decision] — AG
   ```

4. **When in doubt**: Surface it. A false pause costs seconds. A missed destructive action costs hours, data, or reputation.

## What This Is Not

This is not a ban on dangerous patterns. Migrations need `DROP TABLE`. Tests need `eval()`. Deployment scripts need `rm -rf`. The rule is not "never use these" — it's "never use these without the Architect knowing and approving."
