"""Session block and snippet reader — uses bare clone cache to read repo files.

Reads .gator/session-blocks/ files from bare clones via git show.
Supports both v2 plaintext (.json.gz) and v3 encrypted (.block.json) formats.
Handles decompression, decryption, JSON parsing, and content_sha256 verification.
"""

import base64
import gzip
import hashlib
import json

from app.logging import get_logger
from app.services.repo_clone import RepoCloneCache

logger = get_logger("gator.enterprise.artifact_reader")


class ArtifactReader:
    """Reads session blocks and snippets from bare clone cache."""

    def __init__(self, clone_cache: RepoCloneCache):
        self.cache = clone_cache

    def get_session_block(self, repo, block_path: str, branch: str = "main",
                          org_private_key_pem: str | None = None) -> dict | None:
        """Fetch, decrypt/decompress, and validate a session block.

        Detects format automatically:
        - .json.gz → v2 plaintext (gzip decompress, verify hash)
        - .block.json → v3 encrypted (decrypt, decompress, verify hash)

        For v3 encrypted blocks, org_private_key_pem is required for decryption.
        """
        raw = self.cache.read_file(repo, block_path, branch=branch)
        if raw is None:
            return None

        # Detect format
        if block_path.endswith(".block.json"):
            return self._read_encrypted_block(raw, block_path, org_private_key_pem)
        else:
            return self._read_plaintext_block(raw, block_path)

    def get_session_block_metadata(self, repo, block_path: str, branch: str = "main") -> dict | None:
        """Read block metadata WITHOUT decryption. For indexing encrypted blocks.

        Returns the envelope JSON with cleartext fields (target_commit, vendor,
        turn_count, etc.) but no plaintext turns.
        """
        raw = self.cache.read_file(repo, block_path, branch=branch)
        if raw is None:
            return None

        if block_path.endswith(".block.json"):
            try:
                envelope = json.loads(raw)
                # Return metadata without decrypting ciphertext
                return {
                    "schema": envelope.get("schema"),
                    "target_commit": envelope.get("target_commit"),
                    "short_commit": envelope.get("short_commit"),
                    "snippet_id": envelope.get("snippet_id"),
                    "vendor": envelope.get("vendor"),
                    "capture_quality": envelope.get("capture_quality"),
                    "turn_count": envelope.get("turn_count"),
                    "content_sha256": envelope.get("content_sha256"),
                    "content_encryption": envelope.get("content_encryption"),
                    "recipients": envelope.get("recipients", []),
                    "source_metadata": envelope.get("source_metadata"),
                    "_encrypted": True,
                }
            except json.JSONDecodeError as e:
                logger.warning("artifact_reader.envelope_parse_failed",
                               path=block_path, error=str(e))
                return None
        else:
            # Plaintext — need to decompress to read metadata
            return self._read_plaintext_block(raw, block_path)

    def _read_plaintext_block(self, raw: bytes, block_path: str) -> dict | None:
        """Read a v2 plaintext gzip-compressed block."""
        try:
            decompressed = gzip.decompress(raw)
        except (gzip.BadGzipFile, OSError) as e:
            logger.warning("artifact_reader.decompress_failed",
                           path=block_path, error=str(e))
            return None

        try:
            block = json.loads(decompressed)
        except json.JSONDecodeError as e:
            logger.warning("artifact_reader.json_parse_failed",
                           path=block_path, error=str(e))
            return None

        if not self._verify_content_hash(block, block_path):
            return None

        block["_encrypted"] = False
        return block

    def _read_encrypted_block(self, raw: bytes, block_path: str,
                               org_private_key_pem: str | None) -> dict | None:
        """Read a v3 encrypted envelope, decrypt, decompress, verify."""
        try:
            envelope = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("artifact_reader.envelope_parse_failed",
                           path=block_path, error=str(e))
            return None

        if envelope.get("schema") != "gator-session-block-v3-encrypted":
            logger.warning("artifact_reader.unknown_encrypted_schema",
                           path=block_path, schema=envelope.get("schema"))
            return None

        if org_private_key_pem is None:
            logger.warning("artifact_reader.no_org_key_for_decrypt", path=block_path)
            return None

        try:
            # Find org recipient
            org_recipient = None
            for r in envelope.get("recipients", []):
                if r.get("kind") == "org":
                    org_recipient = r
                    break

            if org_recipient is None:
                logger.warning("artifact_reader.no_org_recipient", path=block_path)
                return None

            # Unwrap DEK
            from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
            from cryptography.hazmat.primitives import hashes, serialization

            private_key = serialization.load_pem_private_key(
                org_private_key_pem.encode("utf-8"), password=None
            )
            wrapped_dek = base64.b64decode(org_recipient["wrapped_key_b64"])
            dek = private_key.decrypt(
                wrapped_dek,
                asym_padding.OAEP(
                    mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )

            # Decrypt ciphertext
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            nonce = base64.b64decode(envelope["nonce_b64"])
            ciphertext = base64.b64decode(envelope["ciphertext_b64"])
            aesgcm = AESGCM(dek)
            compressed = aesgcm.decrypt(nonce, ciphertext, None)

            # Decompress
            plaintext_bytes = gzip.decompress(compressed)
            block = json.loads(plaintext_bytes)

        except Exception as e:
            logger.warning("artifact_reader.decrypt_failed",
                           path=block_path, error=str(e))
            return None

        # Verify content hash
        if not self._verify_content_hash(block, block_path):
            return None

        block["_encrypted"] = True
        return block

    def _verify_content_hash(self, block: dict, block_path: str) -> bool:
        """Verify content_sha256 using two-pass canonicalization."""
        expected_hash = block.get("content_sha256")
        if not expected_hash:
            return True  # No hash to verify

        verify_payload = dict(block)
        verify_payload.pop("_encrypted", None)
        verify_payload["content_sha256"] = ""
        canonical = json.dumps(
            verify_payload, sort_keys=True,
            separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        actual_hash = hashlib.sha256(canonical).hexdigest()
        if actual_hash != expected_hash:
            logger.warning("artifact_reader.hash_mismatch",
                           path=block_path,
                           expected=expected_hash[:12],
                           actual=actual_hash[:12])
            return False
        return True

    def get_snippet(self, repo, snippet_path: str, branch: str = "main") -> dict | None:
        """Read and parse a snippet JSON file from the bare clone."""
        raw = self.cache.read_file(repo, snippet_path, branch=branch)
        if raw is None:
            return None

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("artifact_reader.snippet_parse_failed",
                           path=snippet_path, error=str(e))
            return None

    def list_session_blocks(self, repo, branch: str = "main") -> list[str]:
        """List session block files in .gator/session-blocks/ at branch.

        Returns both v2 (.json.gz) and v3 (.block.json) files.
        """
        files = self.cache.list_directory(repo, ".gator/session-blocks", branch=branch)
        return [f for f in files if f.endswith(".json.gz") or f.endswith(".block.json")]

    def list_snippets(self, repo, branch: str = "main") -> list[str]:
        """List .json files in .gator/session-snippets/ at branch."""
        files = self.cache.list_directory(repo, ".gator/session-snippets", branch=branch)
        return [f for f in files if f.endswith(".json")]

    @staticmethod
    def snippet_stem_to_block_path(snippet_filename: str) -> str:
        """Deterministic path derivation: snippet → block.

        .gator/session-snippets/2026-07-12-repo-abc123.json
        → .gator/session-blocks/2026-07-12-repo-abc123.json.gz
        """
        return snippet_filename.replace(
            "session-snippets/", "session-blocks/"
        ) + ".gz"

    @staticmethod
    def block_stem_to_snippet_path(block_filename: str) -> str:
        """Reverse derivation: block → snippet.

        .gator/session-blocks/2026-07-12-repo-abc123.json.gz
        → .gator/session-snippets/2026-07-12-repo-abc123.json

        .gator/session-blocks/2026-07-12-repo-abc123.block.json
        → .gator/session-snippets/2026-07-12-repo-abc123.json
        """
        path = block_filename.replace("session-blocks/", "session-snippets/")
        if path.endswith(".block.json"):
            path = path.removesuffix(".block.json") + ".json"
        elif path.endswith(".json.gz"):
            path = path.removesuffix(".gz")
        return path
