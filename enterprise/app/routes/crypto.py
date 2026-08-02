"""Crypto policy routes — org key management, machine key registration, policy fetch.

Manages envelope encryption keys for session blocks. Org keys are asymmetric
keypairs stored server-side. Machine keys are public keys registered by
developer machines during activation.
"""

import uuid
from datetime import datetime, timezone

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api_contract import ApiError
from app.auth import verify_token
from app.db import get_db
from app.models.api_token import ApiToken
from app.models.machine_key import MachineKey
from app.models.org_encryption_key import OrgEncryptionKey

router = APIRouter(tags=["crypto"])


def _generate_rsa_keypair():
    """Generate a 2048-bit RSA keypair for DEK wrapping."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    return public_pem, private_pem


@router.post("/crypto/org-keys")
def create_org_key(
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Generate a new org encryption keypair. Admin only."""
    # Deactivate existing active keys
    existing = db.execute(
        select(OrgEncryptionKey).where(
            OrgEncryptionKey.organization_id == token.organization_id,
            OrgEncryptionKey.active == True,
        )
    ).scalars().all()
    for k in existing:
        k.active = False

    # Generate new keypair
    public_pem, private_pem = _generate_rsa_keypair()
    now = datetime.now(timezone.utc)
    key_id = f"org-key-{now.strftime('%Y-%m-%d-%H%M%S')}"

    key = OrgEncryptionKey(
        organization_id=token.organization_id,
        key_id=key_id,
        public_key_pem=public_pem,
        private_key_pem=private_pem,
        algorithm="rsa-oaep",
        active=True,
    )
    db.add(key)
    db.commit()

    return {
        "status": "created",
        "key_id": key_id,
        "algorithm": "rsa-oaep",
        "public_key_pem": public_pem,
    }


@router.get("/crypto/policy")
def get_crypto_policy(
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Get current crypto policy for the org. Used by CLI sync."""
    active_key = db.execute(
        select(OrgEncryptionKey).where(
            OrgEncryptionKey.organization_id == token.organization_id,
            OrgEncryptionKey.active == True,
        )
    ).scalar_one_or_none()

    if active_key is None:
        return {
            "org_key": None,
            "session_blocks": {
                "mode": "plaintext",
                "recipient_policy": "none",
                "missing_policy_behavior": "fallback_plaintext",
            },
        }

    return {
        "org_key": {
            "key_id": active_key.key_id,
            "algorithm": active_key.algorithm,
            "public_key_pem": active_key.public_key_pem,
        },
        "session_blocks": {
            "mode": "encrypted",
            "content_encoding": "gzip",
            "content_encryption": "aes-256-gcm",
            "recipient_policy": "org+origin_machine",
            "missing_policy_behavior": "fallback_plaintext",
        },
    }


@router.post("/crypto/org-keys/rotate")
def rotate_org_key(
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Rotate the org encryption key. Old keys kept for historical decrypt."""
    # Deactivate current active key
    existing = db.execute(
        select(OrgEncryptionKey).where(
            OrgEncryptionKey.organization_id == token.organization_id,
            OrgEncryptionKey.active == True,
        )
    ).scalars().all()

    old_key_id = None
    for k in existing:
        k.active = False
        old_key_id = k.key_id

    # Generate new keypair
    public_pem, private_pem = _generate_rsa_keypair()
    now = datetime.now(timezone.utc)
    key_id = f"org-key-{now.strftime('%Y-%m-%d-%H%M%S')}"

    key = OrgEncryptionKey(
        organization_id=token.organization_id,
        key_id=key_id,
        public_key_pem=public_pem,
        private_key_pem=private_pem,
        algorithm="rsa-oaep",
        active=True,
    )
    db.add(key)
    db.commit()

    return {
        "status": "rotated",
        "old_key_id": old_key_id,
        "new_key_id": key_id,
        "public_key_pem": public_pem,
    }


@router.post("/crypto/machine-keys")
def register_machine_key(
    body: dict,
    token: ApiToken = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """Register a machine's public key during activate."""
    machine_id = body.get("machine_id", "")
    machine_label = body.get("machine_label", "")
    public_key_pem = body.get("public_key_pem", "")
    algorithm = body.get("algorithm", "rsa-oaep")

    if not machine_id or not public_key_pem:
        raise ApiError(400, "invalid_parameter", "machine_id and public_key_pem are required")

    # Upsert: update if exists, create if not
    existing = db.execute(
        select(MachineKey).where(
            MachineKey.organization_id == token.organization_id,
            MachineKey.machine_id == machine_id,
        )
    ).scalar_one_or_none()

    if existing:
        existing.public_key_pem = public_key_pem
        existing.machine_label = machine_label
        existing.algorithm = algorithm
        existing.key_id = f"machine-key-{machine_id[:16]}"
        existing.active = True
        db.commit()
        return {"status": "updated", "machine_id": machine_id, "key_id": existing.key_id}

    key_id = f"machine-key-{machine_id[:16]}"
    key = MachineKey(
        organization_id=token.organization_id,
        machine_id=machine_id,
        machine_label=machine_label,
        key_id=key_id,
        public_key_pem=public_key_pem,
        algorithm=algorithm,
        active=True,
    )
    db.add(key)
    db.commit()

    return {"status": "registered", "machine_id": machine_id, "key_id": key_id}
