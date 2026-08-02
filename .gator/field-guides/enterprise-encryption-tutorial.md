---
generated: 2026-07-14
generator: field-guide-gen-v1
type: architect-tutorial
language: enterprise-encryption
source-charters: [enterprise-service, session-archaeology]
patterns: enterprise-encryption-patterns.md
---

# Enterprise Encryption Tutorial

Companion to [enterprise-encryption-patterns.md](enterprise-encryption-patterns.md). This is a topical field guide rather than a language guide: it explains how Gator Enterprise handles encrypted session evidence, what the trust boundaries are, and what questions to be ready for.

### Repo-First Evidence, Ciphertext in Git

**Charter connection**: Enterprise Service — session block index model; Session Archaeology — session-block durability

From `enterprise/app/services/session_blocks.py`:
```python
block = reader.get_session_block_metadata(repo, block_path, branch=branch)
...
evidence = CommitEvidenceBlock(
    commit_id=commit.id,
    block_type="session_block",
    artifact_path=block_path,
    indexed_from_ref=branch,
```

**Why it matters**: The durable object is the repo artifact, not a blob hidden in the Enterprise database. That is the core product distinction. The DB holds metadata for fast lookup, but the transcript evidence remains attached to the code lifecycle through Git. That makes the system resilient to vendor changes and avoids turning Enterprise into just another log warehouse.

**What to watch for**: Any design that starts storing transcript payloads as the primary durable copy in the database instead of treating Git as the evidence plane.

### Envelope Encryption per Block

**Charter connection**: Enterprise Service — E8 encryption section; E8 sketch artifacts

From `enterprise/enterprise-cli/gator_enterprise_cli/block_generate.py`:
```python
dek = AESGCM.generate_key(bit_length=256)
nonce = os.urandom(12)
aesgcm = AESGCM(dek)
ciphertext = aesgcm.encrypt(nonce, compressed, None)
```

And later in the same file:
```python
org_wrapped = org_public_key.encrypt(
    dek,
    asym_padding.OAEP(
        mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
```

**Why it matters**: This is classic envelope encryption. The payload is encrypted once with a random symmetric key, and that symmetric key is wrapped for recipients. It is operationally sane because you can rotate recipient keys without re-encrypting the payload format itself, and it avoids doing expensive asymmetric encryption over large transcript bodies.

**What to watch for**: Confusing “payload encryption” and “key wrapping” in discussion. The DEK is what gets wrapped for recipients; the transcript is encrypted symmetrically.

### Cleartext Metadata, Deferred Decrypt

**Charter connection**: Enterprise Service — metadata indexing, transcript reconstruction

From `enterprise/app/services/artifact_reader.py`:
```python
return {
    "target_commit": envelope.get("target_commit"),
    "vendor": envelope.get("vendor"),
    "turn_count": envelope.get("turn_count"),
    "recipients": envelope.get("recipients", []),
    "_encrypted": True,
}
```

**Why it matters**: Enterprise can answer “which commit has AI evidence?” and “which machine produced it?” without decrypting the transcript. That reduces routine key exposure and lets the fleet-scale indexing path stay cheap. Decrypt is reserved for the higher-trust path where an operator actually requests transcript reconstruction.

**What to watch for**: Proposals to decrypt in the reconciliation worker “for convenience.” That collapses the boundary between indexing and content access.

### Org Key for Central Decrypt, Machine Key for Local Access

**Charter connection**: Enterprise Service — machine identity + session blocks

From `enterprise/enterprise-cli/gator_enterprise_cli/block_generate.py`:
```python
recipients = [
    {
        "kind": "org",
        "key_id": org_key_id,
        "wrapped_key_b64": base64.b64encode(org_wrapped).decode("ascii"),
    },
]
```

And:
```python
recipients.append({
    "kind": "machine",
    "machine_id": machine_id,
    "key_id": machine_key_id,
```

**Why it matters**: This is the trust-boundary story you tell investors or customers. Enterprise can decrypt centrally because the org recipient exists. The local machine can also decrypt because it has its own wrapped copy of the same DEK. That is cleaner than inventing separate payload copies or a special server-only path.

**What to watch for**: Any drift where the machine identity used for recipients differs from the machine identity used in snippets and pending-evidence reporting.

### Rotation Means New Writes, Not Repo Rewrite

**Charter connection**: Enterprise Service — evidence metadata and decryption lookup

From `enterprise/app/services/session_blocks.py`:
```python
if evidence.encryption_mode and evidence.encryption_mode != "plaintext":
    org_private_key_pem = _get_org_private_key(
        db, commit.organization_id, evidence.org_key_id
    )
```

**Why it matters**: Historical decrypt works because each artifact records which org key wrapped its DEK. Rotation changes what future blocks use; it does not require churn across every old repo artifact. That is the answer when someone asks, “How do you still read old encrypted session blocks after rotation?”

**What to watch for**: Any proposal to discard old private keys without being explicit that historical evidence will become undecryptable.

### Hook Runtime Must Pin the CLI Interpreter

**Charter connection**: Enterprise Service — CLI/runtime model for E8

From `enterprise/enterprise-cli/gator_enterprise_cli/commands/activate.py`:
```sh
CLI_PYTHON=$(cat "$CLI_PYTHON_FILE")
if [ -x "$CLI_PYTHON" ]; then
    "$CLI_PYTHON" -m gator_enterprise_cli.block_generate \
        --commit "$COMMIT_SHA" --repo-root "$(pwd)"
fi
```

**Why it matters**: This is one of those details that sounds small but is structurally important. The repo-local scripts are executed by hooks, but encryption depends on the CLI environment having `cryptography` installed. Pinning the activating interpreter is what makes the hook reliable across `pipx`, venv, or other install modes.

**What to watch for**: Any attempt to revert to plain `python3` in hook wrappers.

### Fail Behavior Is Policy, Not an Accident

**Charter connection**: E8 design discussion captured in artifacts and crypto policy route

From `enterprise/enterprise-cli/gator_enterprise_cli/block_generate.py`:
```python
missing_behavior = crypto_policy.get("session_blocks", {}).get(
    "missing_policy_behavior", "fallback_plaintext"
)
```

**Why it matters**: Crypto failure is not just a technical error; it is a product policy decision. Some customers will accept plaintext fallback during rollout. Others will prefer missing evidence to plaintext leakage. Others will want an operationally loud failure. Making that explicit in policy is much stronger than hardcoding one answer.

**What to watch for**: Silent fallback behaviors that operators cannot reason about.

### Machine Identity Must Reuse the Shared Contract

**Charter connection**: Session Archaeology — machine-id format

From `enterprise/enterprise-cli/gator_enterprise_cli/commands/activate.py`:
```python
for line in machine_id_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line.startswith("id:"):
        return line.partition(":")[2].strip()
```

**Why it matters**: `~/.gator/machine-id` is not an incidental file. It is the shared identity primitive for snippets, session blocks, pending evidence, and now crypto recipients. If E8 invents a second interpretation of that file, the whole chain becomes inconsistent. This is a good example of why Gator’s repo and machine contracts need to be treated as first-class architecture, not just implementation detail.

**What to watch for**: Any code that treats `machine-id` as a bare token instead of the existing `key: value` file.

## How To Explain It

If you need the concise investor explanation:

“Gator Enterprise encrypts AI session evidence at the artifact level, not by hiding everything in a backend. The durable evidence stays repo-first in Git, but only as encrypted envelopes. Enterprise indexes cleartext metadata for fleet visibility, and decrypts on demand using org-controlled keys. That gives us provenance tied to code, confidentiality for sensitive transcripts, and key rotation without rewriting history.”

If you need the customer-control explanation:

“Each session block gets its own symmetric key. That key is wrapped to the org and the originating machine. So the customer can control decryption authority at the org boundary, rotate keys over time, and still retain historical decrypt because each artifact records which key wrapped it.”
