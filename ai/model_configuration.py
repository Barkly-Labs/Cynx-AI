"""Versioned, optimistic-concurrency-safe active Ollama configuration."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OPTIONS = {"num_ctx": 8192, "temperature": 0.7}


def validate_model_configuration(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Configuration must be an object.")
    model = value.get("model")
    if not isinstance(model, str) or not model.strip() or len(model) > 200 or any(c in model for c in "\r\n\\"):
        raise ValueError("Choose a valid installed model.")
    raw = value.get("options", {})
    if not isinstance(raw, dict):
        raise ValueError("Generation settings must be an object.")
    if set(raw) - {"num_ctx", "temperature", "top_p", "repeat_penalty"}:
        raise ValueError("One or more generation settings are unsupported.")
    options = dict(DEFAULT_OPTIONS)
    for key, limits in {"num_ctx": (256, 131072), "temperature": (0, 2), "top_p": (0.01, 1), "repeat_penalty": (0.5, 2)}.items():
        if key not in raw:
            continue
        number = raw[key]
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ValueError(f"{key} must be numeric.")
        lo, hi = limits
        if not lo <= number <= hi or (key == "num_ctx" and int(number) != number):
            raise ValueError(f"{key} must be between {lo} and {hi}{' whole tokens' if key == 'num_ctx' else ''}.")
        options[key] = int(number) if key == "num_ctx" else float(number)
    return {"model": model.strip(), "options": options}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ModelConfigurationStore:
    def __init__(self, db_path: str | Path, initial_model: str):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS dx_model_configs (
                config_id TEXT PRIMARY KEY, version INTEGER NOT NULL,
                configuration_json TEXT NOT NULL, created_at TEXT NOT NULL,
                description TEXT NOT NULL, activated INTEGER NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS dx_model_active (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                config_id TEXT NOT NULL, version INTEGER NOT NULL, updated_at TEXT NOT NULL)""")
            active = db.execute("SELECT 1 FROM dx_model_active WHERE singleton=1").fetchone()
            if not active:
                config_id, now = str(uuid.uuid4()), _now()
                configuration = validate_model_configuration({"model": initial_model, "options": DEFAULT_OPTIONS})
                db.execute("INSERT INTO dx_model_configs VALUES(?,?,?,?,?,1)",
                           (config_id, 1, json.dumps(configuration), now, "Initial application configuration"))
                db.execute("INSERT INTO dx_model_active VALUES(1,?,?,?)", (config_id, 1, now))

    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        return db

    @staticmethod
    def _record(row):
        return {"config_id": row["config_id"], "version": row["version"],
                **json.loads(row["configuration_json"]), "created_at": row["created_at"],
                "description": row["description"], "activated": bool(row["activated"])}

    def active(self):
        with self._connect() as db:
            row = db.execute("SELECT c.* FROM dx_model_active a JOIN dx_model_configs c ON c.config_id=a.config_id WHERE a.singleton=1").fetchone()
        return self._record(row)

    def history(self, limit: int = 50):
        with self._connect() as db:
            rows = db.execute("SELECT * FROM dx_model_configs ORDER BY version DESC LIMIT ?", (min(max(limit, 1), 200),)).fetchall()
        return [self._record(row) for row in rows]

    def activate(self, configuration: dict[str, Any], expected_version: int, description: str = ""):
        configuration = validate_model_configuration(configuration)
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute("SELECT config_id,version FROM dx_model_active WHERE singleton=1").fetchone()
            if int(active["version"]) != int(expected_version):
                db.rollback()
                raise RuntimeError("The active model configuration changed. Reload before applying this draft.")
            version, config_id, now = int(active["version"]) + 1, str(uuid.uuid4()), _now()
            db.execute("INSERT INTO dx_model_configs VALUES(?,?,?,?,?,1)",
                       (config_id, version, json.dumps(configuration, sort_keys=True), now, str(description or "Model Lab configuration")[:300]))
            db.execute("UPDATE dx_model_active SET config_id=?,version=?,updated_at=? WHERE singleton=1", (config_id, version, now))
            db.commit()
        return self.active()

    def restore(self, config_id: str, expected_version: int):
        with self._connect() as db:
            row = db.execute("SELECT configuration_json,description FROM dx_model_configs WHERE config_id=?", (config_id,)).fetchone()
        if not row:
            raise KeyError("Saved model configuration not found.")
        return self.activate(json.loads(row["configuration_json"]), expected_version, f"Rollback: {row['description']}")

