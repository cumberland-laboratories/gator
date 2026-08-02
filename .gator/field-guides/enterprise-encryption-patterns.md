---
generated: 2026-07-14
generator: field-guide-gen-v1
type: agent-patterns
language: enterprise-encryption
source-charters: [enterprise-service, session-archaeology]
source-file-count: 7
pattern-count: 8
tutorial: enterprise-encryption-tutorial.md
---

# Enterprise Encryption Patterns

### Repo-First Evidence, Ciphertext in Git
Files: enterprise/enterprise-cli/gator_enterprise_cli/block_generate.py, enterprise/app/services/artifact_reader.py, enterprise/app/services/session_blocks.py
When session evidence is durable, write it into `.gator/session-blocks/` and let Enterprise reconstruct from cloned repos. The database stores index metadata, not the transcript payload.
! Breaking this turns E8 into a DB-centric audit log and loses the repo-native evidence model.

### Envelope Encryption per Block
Files: enterprise/enterprise-cli/gator_enterprise_cli/block_generate.py, enterprise/app/routes/crypto.py
When encrypting a session block, generate a fresh symmetric DEK for that block, encrypt the compressed payload with AES-GCM, then wrap the DEK for recipients using asymmetric org and machine keys.

### Cleartext Metadata, Deferred Decrypt
Files: enterprise/app/services/artifact_reader.py, enterprise/app/services/session_blocks.py
When indexing encrypted blocks, read only envelope metadata in cleartext (`target_commit`, `vendor`, `turn_count`, key ids). Decrypt only when transcript content is explicitly requested.
! Index-time decrypt defeats the point of the envelope and adds unnecessary key exposure to routine scans.

### Org Key for Central Decrypt, Machine Key for Local Access
Files: enterprise/app/routes/crypto.py, enterprise/app/models/org_encryption_key.py, enterprise/app/models/machine_key.py
When reasoning about trust boundaries, treat the org key as the Enterprise audit authority and the machine key as the local-origin access path. Both receive the same per-block DEK via wrapping, not separate payload encryptions.

### Rotation Means New Writes, Not Repo Rewrite
Files: enterprise/app/routes/crypto.py, enterprise/app/services/session_blocks.py, enterprise/app/models/evidence_block.py
When keys rotate, new blocks use the new org key id and old blocks keep their historical key ids. Enterprise decrypts old artifacts by looking up the stored key id rather than rewriting the repo.

### Hook Runtime Must Pin the CLI Interpreter
Files: enterprise/enterprise-cli/gator_enterprise_cli/commands/activate.py, enterprise/enterprise-cli/pyproject.toml
When post-commit needs `cryptography`, run through the pinned Enterprise CLI interpreter recorded at activation time. Do not assume the shell’s `python3` has the right environment.

### Fail Behavior Is Policy, Not an Accident
Files: enterprise/enterprise-cli/gator_enterprise_cli/block_generate.py, enterprise/app/routes/crypto.py
When crypto material is missing or encryption fails, use the synced policy mode (`fallback_plaintext`, `skip_block`, `block_commit`) rather than ad hoc behavior. This is an operator choice about evidence and leakage tradeoffs.

### Machine Identity Must Reuse the Shared Contract
Files: enterprise/enterprise-cli/gator_enterprise_cli/commands/activate.py, enterprise/enterprise-cli/gator_enterprise_cli/block_generate.py, enterprise/enterprise-cli/gator_enterprise_cli/bundled_scripts/precommit_session.py
When reading or creating `~/.gator/machine-id`, use the existing `key: value` contract (`id:`, `label:`, etc.). Encryption recipients, snippet attribution, and pending-evidence reporting all depend on the same machine identity.
