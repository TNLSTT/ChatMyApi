"""Utilities for storing API keys locally with symmetric encryption."""
from __future__ import annotations

import base64
import json
import os
import pathlib
from hashlib import sha256
from typing import Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

BASE_DIR = pathlib.Path(__file__).resolve().parent
KEY_FILE = BASE_DIR / ".fernet.key"
DATA_FILE = BASE_DIR / "keys.json.enc"
ENV_SECRET = os.getenv("CHATMYAPI_SECRET")


def _derive_key_from_secret(secret: str) -> bytes:
    digest = sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _load_or_create_fernet() -> Fernet:
    if ENV_SECRET:
        return Fernet(_derive_key_from_secret(ENV_SECRET))

    if KEY_FILE.exists():
        key = KEY_FILE.read_bytes()
    else:
        key = Fernet.generate_key()
        KEY_FILE.write_bytes(key)
    return Fernet(key)


def _load_store(fernet: Fernet) -> Dict[str, str]:
    if not DATA_FILE.exists():
        return {}
    try:
        encrypted = DATA_FILE.read_bytes()
        decrypted = fernet.decrypt(encrypted)
        return json.loads(decrypted.decode("utf-8"))
    except (InvalidToken, json.JSONDecodeError):
        return {}


def save_api_key(api_name: str, api_key: str) -> None:
    fernet = _load_or_create_fernet()
    data = _load_store(fernet)
    data[api_name] = api_key
    serialized = json.dumps(data).encode("utf-8")
    DATA_FILE.write_bytes(fernet.encrypt(serialized))


def load_api_key(api_name: str) -> Optional[str]:
    fernet = _load_or_create_fernet()
    data = _load_store(fernet)
    return data.get(api_name)
