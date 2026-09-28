import os
import json
import hashlib
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from src.config import DATA_DIR

KEY_FILE = DATA_DIR / "ed25519_private.pem"
PUB_FILE = DATA_DIR / "ed25519_public.pem"

def get_or_create_keys():
    """Loads or generates persistent Ed25519 keypair."""
    if KEY_FILE.exists() and PUB_FILE.exists():
        with open(KEY_FILE, "rb") as f:
            priv_key = serialization.load_pem_private_key(f.read(), password=None)
        with open(PUB_FILE, "rb") as f:
            pub_key = serialization.load_pem_public_key(f.read())
        return priv_key, pub_key

    # Generate new
    priv_key = ed25519.Ed25519PrivateKey.generate()
    pub_key = priv_key.public_key()

    priv_pem = priv_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    pub_pem = pub_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    with open(KEY_FILE, "wb") as f:
        f.write(priv_pem)
    with open(PUB_FILE, "wb") as f:
        f.write(pub_pem)

    return priv_key, pub_key

def canonicalize_json(data: dict) -> bytes:
    """Produces deterministically sorted canonical JSON bytes."""
    return json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')

def sign_bundle(payload_dict: dict) -> tuple[str, str, str]:
    """Signs payload with Ed25519, returns (canonical_json, signature_hex, public_key_hex)."""
    priv_key, pub_key = get_or_create_keys()
    canonical_bytes = canonicalize_json(payload_dict)
    
    signature = priv_key.sign(canonical_bytes)
    
    pub_bytes = pub_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    
    return canonical_bytes.decode('utf-8'), signature.hex(), pub_bytes.hex()

def verify_signature(canonical_json_str: str, signature_hex: str, public_key_hex: str) -> bool:
    """Verifies Ed25519 signature."""
    try:
        pub_bytes = bytes.fromhex(public_key_hex)
        sig_bytes = bytes.fromhex(signature_hex)
        pub_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
        pub_key.verify(sig_bytes, canonical_json_str.encode('utf-8'))
        return True
    except Exception:
        return False
