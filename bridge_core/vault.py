#!/usr/bin/env python3
"""
CHAOS TYPE ZERO Vault — Secure Credential Management
Encrypt and manage API keys, tokens, secrets.

Features:
- AES-128 authenticated encryption (Fernet) with a per-install key
- Key is generated locally on first run and NEVER committed to git
  (lives in data/vault/vault.key, which is gitignored, or can be
  supplied out-of-band via the CTZ_VAULT_KEY env var)
- Access logging
- Secret categories
- Auto-redaction in logs

SECURITY NOTE (fixed 2026-08-23):
Earlier versions of this file used a hardcoded XOR key
(`_OBFUSC_KEY = b"CTZ_VAULT_2026_CHAOS_TYPE_ZERO"`) baked directly into
source that was pushed to a public GitHub repo. Because the "encryption"
key was public, any secret ever stored in the vault could be trivially
decrypted by anyone who saw the repo. If this vault was ever used to
store real credentials, treat those credentials as compromised, rotate
them, and delete data/vault/vault.db before reusing the vault.
"""

import base64
import hashlib
import hmac
import json
import os
import stat
import sqlite3
import time
from pathlib import Path

try:
    from cryptography.fernet import Fernet, InvalidToken
    HAS_CRYPTO = True
except ImportError:
    Fernet = None
    InvalidToken = Exception
    HAS_CRYPTO = False

CTZ_ROOT = Path(__file__).parent.parent
DATA_DIR = CTZ_ROOT / "data"
VAULT_DIR = DATA_DIR / "vault"
DB_PATH = VAULT_DIR / "vault.db"
KEY_PATH = VAULT_DIR / "vault.key"

VAULT_DIR.mkdir(parents=True, exist_ok=True)


def _load_or_create_key() -> bytes:
    """
    Resolve the key used to encrypt/decrypt secrets.
    Priority:
      1. CTZ_VAULT_KEY env var
      2. data/vault/vault.key
    """
    env_key = os.environ.get("CTZ_VAULT_KEY")
    if env_key:
        return env_key.encode()

    if KEY_PATH.exists():
        return KEY_PATH.read_bytes().strip()

    if HAS_CRYPTO and Fernet is not None:
        key = Fernet.generate_key()
    else:
        key = base64.urlsafe_b64encode(os.urandom(32))
    KEY_PATH.write_bytes(key)
    try:
        os.chmod(KEY_PATH, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return key


def _get_fernet() -> "Fernet":
    return Fernet(_load_or_create_key())


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    """Generate deterministic pseudorandom keystream using HMAC-SHA256 in counter mode."""
    blocks = []
    counter = 0
    while len(b"".join(blocks)) < length:
        block = hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        blocks.append(block)
        counter += 1
    return b"".join(blocks)[:length]


def _encrypt(plaintext: str) -> str:
    if HAS_CRYPTO and Fernet is not None:
        return _get_fernet().encrypt(plaintext.encode()).decode()
    raw = plaintext.encode("utf-8")
    key = _load_or_create_key()
    nonce = os.urandom(16)
    ks = _keystream(key, nonce, len(raw))
    ciphertext = bytes(a ^ b for a, b in zip(raw, ks))
    tag = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    payload = b"STD:" + nonce + tag + ciphertext
    return base64.urlsafe_b64encode(payload).decode("ascii")


def _decrypt(ciphertext: str) -> str:
    if HAS_CRYPTO and Fernet is not None:
        try:
            return _get_fernet().decrypt(ciphertext.encode()).decode()
        except Exception:
            pass
    try:
        data = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        if data.startswith(b"STD:"):
            nonce = data[4:20]
            tag = data[20:52]
            ct = data[52:]
            key = _load_or_create_key()
            expected_tag = hmac.new(key, nonce + ct, hashlib.sha256).digest()
            if not hmac.compare_digest(tag, expected_tag):
                raise ValueError("Vault authentication tag mismatch: data corrupted or tampered.")
            ks = _keystream(key, nonce, len(ct))
            raw = bytes(a ^ b for a, b in zip(ct, ks))
            return raw.decode("utf-8")
    except Exception as e:
        if isinstance(e, ValueError):
            raise
    raise ValueError(
        "Failed to decrypt secret: wrong/missing vault key or corrupted ciphertext."
    )


class Vault:
    def __init__(self, db_path=None):
        self.db_path = db_path or str(DB_PATH)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS secrets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            value_encrypted TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            description TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_accessed DATETIME,
            access_count INTEGER DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS access_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            secret_name TEXT,
            action TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.commit()
        conn.close()

    def set(self, name, value, category="general", description=""):
        encrypted = _encrypt(value)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO secrets (name, value_encrypted, category, description) VALUES (?, ?, ?, ?)",
                  (name, encrypted, category, description))
        c.execute("INSERT INTO access_log (secret_name, action) VALUES (?, 'set')", (name,))
        conn.commit()
        conn.close()
        return {"status": "stored", "name": name}

    def get(self, name):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT value_encrypted, category, description FROM secrets WHERE name = ?", (name,))
        row = c.fetchone()
        if row:
            c.execute("UPDATE secrets SET last_accessed = CURRENT_TIMESTAMP, access_count = access_count + 1 WHERE name = ?", (name,))
            c.execute("INSERT INTO access_log (secret_name, action) VALUES (?, 'get')", (name,))
            conn.commit()
            conn.close()
            return {"name": name, "value": _decrypt(row[0]), "category": row[1], "description": row[2]}
        conn.close()
        return None

    def delete(self, name):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("DELETE FROM secrets WHERE name = ?", (name,))
        c.execute("INSERT INTO access_log (secret_name, action) VALUES (?, 'delete')", (name,))
        conn.commit()
        conn.close()
        return {"status": "deleted", "name": name}

    def list_all(self, category=None):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        if category:
            c.execute("SELECT name, category, description, access_count FROM secrets WHERE category = ?", (category,))
        else:
            c.execute("SELECT name, category, description, access_count FROM secrets")
        rows = c.fetchall()
        conn.close()
        return [{"name": r[0], "category": r[1], "description": r[2], "access_count": r[3]} for r in rows]

    def stats(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM secrets")
        total = c.fetchone()[0]
        c.execute("SELECT category, COUNT(*) FROM secrets GROUP BY category")
        cats = {r[0]: r[1] for r in c.fetchall()}
        c.execute("SELECT COUNT(*) FROM access_log")
        logs = c.fetchone()[0]
        conn.close()
        return {"total_secrets": total, "categories": cats, "access_logs": logs}


_vault = None

def get_vault():
    global _vault
    if _vault is None:
        _vault = Vault()
    return _vault


if __name__ == "__main__":
    v = get_vault()
    v.set("test_key", "super_secret_123", category="api", description="Test key")
    print("Get:", v.get("test_key"))
    print("List:", v.list_all())
    print("Stats:", v.stats())
    v.delete("test_key")
