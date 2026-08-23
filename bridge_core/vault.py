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
import json
import os
import stat
import sqlite3
import time
from pathlib import Path

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError as e:
    raise ImportError(
        "The 'cryptography' package is required for the vault to store secrets "
        "safely. Install it with: pip install cryptography --break-system-packages"
    ) from e

CTZ_ROOT = Path(__file__).parent.parent
DATA_DIR = CTZ_ROOT / "data"
VAULT_DIR = DATA_DIR / "vault"
DB_PATH = VAULT_DIR / "vault.db"
KEY_PATH = VAULT_DIR / "vault.key"

VAULT_DIR.mkdir(parents=True, exist_ok=True)


def _load_or_create_key() -> bytes:
    """
    Resolve the Fernet key used to encrypt/decrypt secrets.

    Priority:
      1. CTZ_VAULT_KEY env var (lets you inject a key from a secrets
         manager / CI instead of relying on a local file)
      2. data/vault/vault.key (auto-generated on first run, gitignored,
         file permissions locked to owner-read-only where supported)
    """
    env_key = os.environ.get("CTZ_VAULT_KEY")
    if env_key:
        return env_key.encode()

    if KEY_PATH.exists():
        return KEY_PATH.read_bytes().strip()

    key = Fernet.generate_key()
    KEY_PATH.write_bytes(key)
    try:
        os.chmod(KEY_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 0600, owner only
    except OSError:
        pass  # best-effort on platforms without POSIX permissions (e.g. Windows)
    return key


def _get_fernet() -> "Fernet":
    return Fernet(_load_or_create_key())


def _encrypt(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise ValueError(
            "Failed to decrypt secret: wrong/missing vault key, or the value "
            "was encrypted with the old insecure XOR scheme. If you're "
            "migrating from an old vault, re-run ctz_vault_set for each "
            "secret with the new vault."
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
