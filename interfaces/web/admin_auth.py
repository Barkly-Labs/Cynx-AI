"""Single local administrator authentication for the CYN-X research console."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class AdminAuthStore:
    """SQLite-backed one-owner account and expiring browser sessions."""

    SESSION_SECONDS = 12 * 60 * 60
    IDLE_SECONDS = 30 * 60

    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS dx_admin (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                password_salt BLOB NOT NULL, password_hash BLOB NOT NULL,
                created_at REAL NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS dx_admin_sessions (
                token_hash TEXT PRIMARY KEY, csrf_token TEXT NOT NULL,
                created_at REAL NOT NULL, last_seen REAL NOT NULL,
                expires_at REAL NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS dx_admin_audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at REAL NOT NULL,
                action TEXT NOT NULL, result_code INTEGER NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS dx_admin_login_limits (
                bucket TEXT PRIMARY KEY, window_started REAL NOT NULL, failures INTEGER NOT NULL)""")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        return db

    def is_configured(self) -> bool:
        with self._connect() as db:
            return db.execute("SELECT 1 FROM dx_admin WHERE singleton=1").fetchone() is not None

    @staticmethod
    def _hash_password(password: str, salt: bytes) -> bytes:
        return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=64)

    @staticmethod
    def validate_password(password: Any) -> str:
        if not isinstance(password, str) or len(password) < 12 or len(password) > 256:
            raise ValueError("Use a password between 12 and 256 characters.")
        if not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
            raise ValueError("Include at least one letter and one number.")
        return password

    def setup(self, password: str) -> None:
        password = self.validate_password(password)
        salt = secrets.token_bytes(16)
        password_hash = self._hash_password(password, salt)
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM dx_admin WHERE singleton=1").fetchone():
                db.rollback()
                raise RuntimeError("The administrator account is already configured.")
            db.execute("INSERT INTO dx_admin VALUES(1,?,?,?)", (salt, password_hash, time.time()))
            db.commit()

    def login(self, password: str) -> tuple[str, str] | None:
        with self._connect() as db:
            row = db.execute("SELECT password_salt,password_hash FROM dx_admin WHERE singleton=1").fetchone()
        if not row or not isinstance(password, str) or len(password) > 256:
            # Do comparable work when no account exists to reduce timing clues.
            self._hash_password(password[:256] if isinstance(password, str) else "", b"cynx-dx-salt-000")
            return None
        candidate = self._hash_password(password, row["password_salt"])
        if not hmac.compare_digest(candidate, row["password_hash"]):
            return None
        token, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
        now = time.time()
        with self._connect() as db:
            db.execute("INSERT INTO dx_admin_sessions VALUES(?,?,?,?,?)",
                       (self.token_hash(token), csrf, now, now, now + self.SESSION_SECONDS))
        return token, csrf

    @staticmethod
    def token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def session(self, token: str | None, *, touch: bool = True) -> dict[str, Any] | None:
        if not token or len(token) > 256:
            return None
        key, now = self.token_hash(token), time.time()
        with self._connect() as db:
            row = db.execute("SELECT csrf_token,created_at,last_seen,expires_at FROM dx_admin_sessions WHERE token_hash=?", (key,)).fetchone()
            if not row:
                return None
            if now >= row["expires_at"] or now - row["last_seen"] >= self.IDLE_SECONDS:
                db.execute("DELETE FROM dx_admin_sessions WHERE token_hash=?", (key,))
                return None
            if touch:
                db.execute("UPDATE dx_admin_sessions SET last_seen=? WHERE token_hash=?", (now, key))
            return {"csrf_token": row["csrf_token"], "created_at": row["created_at"], "expires_at": row["expires_at"]}

    def logout(self, token: str | None) -> None:
        if token:
            with self._connect() as db:
                db.execute("DELETE FROM dx_admin_sessions WHERE token_hash=?", (self.token_hash(token),))

    def login_allowed(self, client_key: str) -> bool:
        bucket = hashlib.sha256(client_key.encode("utf-8")).hexdigest()
        now = time.time()
        with self._connect() as db:
            row = db.execute("SELECT window_started,failures FROM dx_admin_login_limits WHERE bucket=?", (bucket,)).fetchone()
            if not row or now - row["window_started"] >= 15 * 60:
                db.execute("DELETE FROM dx_admin_login_limits WHERE window_started<?", (now - 24 * 60 * 60,))
                return True
            return row["failures"] < 5

    def record_login_failure(self, client_key: str) -> None:
        bucket, now = hashlib.sha256(client_key.encode("utf-8")).hexdigest(), time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT window_started,failures FROM dx_admin_login_limits WHERE bucket=?", (bucket,)).fetchone()
            if not row or now - row["window_started"] >= 15 * 60:
                db.execute("INSERT INTO dx_admin_login_limits VALUES(?,?,1) ON CONFLICT(bucket) DO UPDATE SET window_started=excluded.window_started,failures=1", (bucket, now))
            else:
                db.execute("UPDATE dx_admin_login_limits SET failures=failures+1 WHERE bucket=?", (bucket,))
            db.commit()

    def clear_login_failures(self, client_key: str) -> None:
        bucket = hashlib.sha256(client_key.encode("utf-8")).hexdigest()
        with self._connect() as db:
            db.execute("DELETE FROM dx_admin_login_limits WHERE bucket=?", (bucket,))

    def audit(self, action: str, result_code: int) -> None:
        with self._connect() as db:
            db.execute("INSERT INTO dx_admin_audit(occurred_at,action,result_code) VALUES(?,?,?)",
                       (time.time(), action[:200], int(result_code)))

    def audit_history(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT occurred_at,action,result_code FROM dx_admin_audit ORDER BY audit_id DESC LIMIT ?",
                              (min(max(int(limit), 1), 500),)).fetchall()
        return [{"occurred_at": row["occurred_at"], "action": row["action"], "result_code": row["result_code"]} for row in rows]

