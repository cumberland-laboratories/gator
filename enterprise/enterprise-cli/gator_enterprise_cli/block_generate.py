"""Block generation module — invoked by the post-commit hook via the CLI interpreter.

This module has access to the `cryptography` library (via the CLI pip environment)
and can emit both v2 plaintext and v3 encrypted session blocks depending on the
crypto policy synced from Enterprise.

Invoked as: python -m gator_enterprise_cli.block_generate --commit <sha> --repo-root <path>
"""

import argparse
import base64
import gzip
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def _read_machine_id() -> str:
    """Read machine ID from ~/.gator/machine-id (key: value format)."""
    machine_id_path = Path.home() / ".gator" / "machine-id"
    if machine_id_path.exists():
        for line in machine_id_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("id:"):
                return line.partition(":")[2].strip()
    return "unknown"


def main():
    parser = argparse.ArgumentParser(description="Generate session block for a commit")
    parser.add_argument("--commit", required=True, help="Full commit SHA")
    parser.add_argument("--repo-root", required=True, help="Path to repo root")
    args = parser.parse_args()

    repo_root = Path(args.repo_root)
    gator_dir = repo_root / ".gator"
    if not gator_dir.exists():
        sys.exit(0)

    # Session block generation only — snippet emission is handled by
    # record_commit_and_emit_snippet() in precommit_session.py during
    # post-commit (phase_cleanup), staged for the next commit.
    # This module handles session blocks; snippets are a separate pipeline.

    # Try to generate session block using the repo-local script
    block_script = gator_dir / "scripts" / "gator-session-block.py"
    if not block_script.exists():
        sys.exit(0)

    # Read crypto policy
    enterprise_dir = Path.home() / ".gator" / "enterprise"
    crypto_policy = _load_crypto_policy(enterprise_dir)
    mode = crypto_policy.get("session_blocks", {}).get("mode", "plaintext")

    if mode == "plaintext":
        # Delegate to repo-local script (v2 plaintext)
        result = subprocess.run(
            [sys.executable, str(block_script), "generate", "--commit", args.commit],
            cwd=str(repo_root),
            capture_output=True, text=True,
        )
        sys.exit(result.returncode)

    # Encrypted mode — generate v2 block via repo script, then encrypt it
    if mode == "encrypted":
        _generate_encrypted_block(args.commit, repo_root, gator_dir, enterprise_dir, crypto_policy)
    else:
        # Unknown mode — fall back to plaintext
        result = subprocess.run(
            [sys.executable, str(block_script), "generate", "--commit", args.commit],
            cwd=str(repo_root),
            capture_output=True, text=True,
        )
        sys.exit(result.returncode)


def _load_crypto_policy(enterprise_dir: Path) -> dict:
    """Load crypto policy from synced cache."""
    policy_path = enterprise_dir / "crypto-policy.json"
    if not policy_path.exists():
        return {"session_blocks": {"mode": "plaintext"}}
    try:
        return json.loads(policy_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"session_blocks": {"mode": "plaintext"}}


def _generate_encrypted_block(commit_sha, repo_root, gator_dir, enterprise_dir, crypto_policy):
    """Generate an encrypted v3 session block envelope.

    1. Run the repo-local script to generate v2 plaintext block
    2. Read the generated .json.gz
    3. Decompress to get plaintext
    4. Encrypt with envelope encryption
    5. Write v3 .block.json
    6. Remove the plaintext .json.gz
    """
    block_script = gator_dir / "scripts" / "gator-session-block.py"

    # Step 1: Generate v2 plaintext block using repo-local script
    result = subprocess.run(
        [sys.executable, str(block_script), "generate", "--commit", commit_sha],
        cwd=str(repo_root),
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        # Fall back based on policy
        missing_behavior = crypto_policy.get("session_blocks", {}).get(
            "missing_policy_behavior", "fallback_plaintext"
        )
        if missing_behavior == "skip_block":
            sys.exit(0)
        sys.exit(result.returncode)

    # Step 2: Find the generated .json.gz
    blocks_dir = gator_dir / "session-blocks"
    gz_files = sorted(blocks_dir.glob(f"*{commit_sha[:13]}*.json.gz"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not gz_files:
        sys.exit(0)  # No block generated (e.g., no transcript available)

    gz_path = gz_files[0]

    # Step 3: Read and decompress plaintext
    compressed = gz_path.read_bytes()
    try:
        plaintext_bytes = gzip.decompress(compressed)
        block = json.loads(plaintext_bytes)
    except Exception:
        sys.exit(0)  # Corrupt block, skip

    # Step 4: Encrypt
    try:
        envelope = _encrypt_block(block, plaintext_bytes, enterprise_dir, crypto_policy)
    except Exception as e:
        # Handle based on missing_policy_behavior
        missing_behavior = crypto_policy.get("session_blocks", {}).get(
            "missing_policy_behavior", "fallback_plaintext"
        )
        if missing_behavior == "fallback_plaintext":
            # Keep the plaintext .json.gz
            sys.exit(0)
        elif missing_behavior == "skip_block":
            gz_path.unlink(missing_ok=True)
            sys.exit(0)
        else:
            print(f"Error: encryption failed: {e}", file=sys.stderr)
            print("Run 'gator-enterprise sync' to refresh crypto policy.", file=sys.stderr)
            gz_path.unlink(missing_ok=True)
            sys.exit(0)

    # Step 5: Write encrypted envelope
    stem = gz_path.stem.removesuffix(".json")  # remove .json from .json.gz
    encrypted_path = blocks_dir / f"{stem}.block.json"
    encrypted_path.write_text(
        json.dumps(envelope, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Step 6: Remove plaintext .json.gz
    gz_path.unlink(missing_ok=True)


def _encrypt_block(block: dict, plaintext_bytes: bytes, enterprise_dir: Path, crypto_policy: dict) -> dict:
    """Create a v3 encrypted envelope from a plaintext block.

    Returns the envelope dict ready to write as JSON.
    """
    from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    # Load org public key
    org_key_path = enterprise_dir / "org-keys" / "org-public-key.pem"
    if not org_key_path.exists():
        raise RuntimeError("Org public key not found. Run 'gator-enterprise sync'.")
    org_public_key = serialization.load_pem_public_key(
        org_key_path.read_bytes()
    )

    # Load machine keys
    machine_public_key_path = enterprise_dir / "keys" / "machine-public-key.pem"
    machine_public_key = None
    if machine_public_key_path.exists():
        machine_public_key = serialization.load_pem_public_key(
            machine_public_key_path.read_bytes()
        )

    # Get key IDs from crypto policy
    org_key_id = crypto_policy.get("org_key", {}).get("key_id", "unknown")
    machine_id = _read_machine_id()
    machine_key_id = f"machine-key-{machine_id[:16]}"

    # Compress plaintext
    compressed = gzip.compress(plaintext_bytes, compresslevel=6)

    # Generate random DEK
    dek = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)

    # Encrypt with AES-256-GCM
    aesgcm = AESGCM(dek)
    ciphertext = aesgcm.encrypt(nonce, compressed, None)

    # Wrap DEK for org recipient
    org_wrapped = org_public_key.encrypt(
        dek,
        asym_padding.OAEP(
            mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )

    recipients = [
        {
            "kind": "org",
            "key_id": org_key_id,
            "wrapped_key_b64": base64.b64encode(org_wrapped).decode("ascii"),
        },
    ]

    # Wrap DEK for machine recipient
    if machine_public_key:
        machine_wrapped = machine_public_key.encrypt(
            dek,
            asym_padding.OAEP(
                mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        recipients.append({
            "kind": "machine",
            "machine_id": machine_id,
            "key_id": machine_key_id,
            "wrapped_key_b64": base64.b64encode(machine_wrapped).decode("ascii"),
        })

    # Build envelope
    envelope = {
        "schema": "gator-session-block-v3-encrypted",
        "type": "session_block",
        "content_encoding": "gzip",
        "content_encryption": "aes-256-gcm",
        "target_commit": block.get("target_commit", ""),
        "short_commit": block.get("short_commit", ""),
        "snippet_id": block.get("snippet_id", ""),
        "repo_relpath": block.get("repo_relpath", ""),
        "vendor": block.get("vendor", "unknown"),
        "capture_mode": block.get("capture_mode", "exact"),
        "capture_quality": block.get("capture_quality", "exact"),
        "captured_at": block.get("captured_at", ""),
        "turn_count": block.get("turn_count", 0),
        "content_sha256": block.get("content_sha256", ""),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        "recipients": recipients,
        "source_metadata": block.get("source_metadata", {}),
    }

    return envelope


if __name__ == "__main__":
    main()
