"""Persistent, isolated configuration and evidence storage for DX Personality Studio."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TRAITS = (
    "warmth", "playfulness", "affection", "mischievousness", "intelligence",
    "curiosity", "sarcasm", "flirtiness", "assertiveness", "seriousness",
)
TRAIT_INFO = {
    "warmth": "Shows care and approachability while respecting the user's tone.",
    "playfulness": "Adds light energy when it fits the conversation.",
    "affection": "Responds warmly to closeness without assuming it is always wanted.",
    "mischievousness": "Uses impish surprise sparingly and contextually.",
    "intelligence": "Explains clearly, reasons carefully, and stays useful.",
    "curiosity": "Asks relevant questions instead of interrogating or prolonging turns.",
    "sarcasm": "Uses dry humor only when it remains kind and appropriate.",
    "flirtiness": "Uses consensual flirtation only when invited and appropriate.",
    "assertiveness": "Offers clear recommendations while preserving user choice.",
    "seriousness": "Takes serious, technical, and emotional topics seriously.",
}
STARTER_TRAITS = {
    "warmth": 90, "playfulness": 90, "affection": 95, "mischievousness": 75,
    "intelligence": 90, "curiosity": 80, "sarcasm": 65, "flirtiness": 77,
    "assertiveness": 75, "seriousness": 45,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_traits(value: Any) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != set(TRAITS):
        raise ValueError("A personality configuration must include exactly the ten supported traits.")
    result = {}
    for trait in TRAITS:
        item = value[trait]
        if isinstance(item, bool) or not isinstance(item, (int, float)) or int(item) != item or not 0 <= item <= 100:
            raise ValueError(f"{trait} must be a whole percentage from 0 to 100.")
        result[trait] = int(item)
    return result


class PersonalityStudioStore:
    """SQLite-backed active versions, presets, and evaluation records.

    A legacy installation is represented faithfully: existing matrix dimensions
    are reported, while newly introduced dimensions remain null until the owner
    explicitly activates a complete Studio configuration.
    """

    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self):
        conn = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def _initialize(self):
        with self._lock, self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS personality_configs (
                config_id TEXT PRIMARY KEY, version INTEGER NOT NULL, traits_json TEXT NOT NULL,
                created_at TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', source TEXT NOT NULL,
                activated INTEGER NOT NULL DEFAULT 0)""")
            db.execute("""CREATE TABLE IF NOT EXISTS personality_active (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1), config_id TEXT NOT NULL,
                version INTEGER NOT NULL, updated_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS personality_presets (
                preset_id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, traits_json TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, description TEXT NOT NULL DEFAULT '')""")
            db.execute("""CREATE TABLE IF NOT EXISTS personality_evaluations (
                evaluation_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, traits_json TEXT NOT NULL,
                config_id TEXT, config_version INTEGER, model TEXT NOT NULL, prompt TEXT NOT NULL,
                response TEXT NOT NULL, evaluator_model TEXT, evaluation_json TEXT NOT NULL)""")
            row = db.execute("SELECT config_id FROM personality_active WHERE singleton=1").fetchone()
            if not row:
                from .personality import get_personality_matrix
                legacy = get_personality_matrix()
                values = {
                    "warmth": legacy.get("warmth"), "playfulness": legacy.get("playfulness"),
                    "affection": legacy.get("affection"), "mischievousness": None,
                    "intelligence": None, "curiosity": legacy.get("curiosity"),
                    "sarcasm": None, "flirtiness": legacy.get("flirtiness"),
                    "assertiveness": None, "seriousness": legacy.get("seriousness"),
                }
                config_id = str(uuid.uuid4())
                now = _now()
                db.execute("INSERT INTO personality_configs VALUES(?,?,?,?,?,?,0)",
                           (config_id, 1, json.dumps(values), now, "Existing CYN-X personality", "legacy"))
                db.execute("INSERT INTO personality_active VALUES(1,?,?,?)", (config_id, 1, now))
            if not db.execute("SELECT 1 FROM personality_presets LIMIT 1").fetchone():
                now = _now()
                preset_id = str(uuid.uuid4())
                db.execute("INSERT INTO personality_presets VALUES(?,?,?,?,?,?)", (
                    preset_id, "Owner's companion example", json.dumps(STARTER_TRAITS), now, now,
                    "Suggested starting draft from the Personality Studio brief. Loading this preset never activates it."))

    def active(self) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("""SELECT c.*, a.updated_at FROM personality_active a
                JOIN personality_configs c ON c.config_id=a.config_id WHERE a.singleton=1""").fetchone()
            return {"config_id": row["config_id"], "version": row["version"],
                    "traits": json.loads(row["traits_json"]), "created_at": row["created_at"],
                    "activated_at": row["updated_at"], "description": row["description"],
                    "source": row["source"], "activated": bool(row["activated"])}

    def history(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM personality_configs ORDER BY version DESC, created_at DESC").fetchall()
        return [{"config_id": r["config_id"], "version": r["version"], "traits": json.loads(r["traits_json"]),
                 "created_at": r["created_at"], "description": r["description"], "source": r["source"],
                 "activated": bool(r["activated"])} for r in rows]

    def activate(self, traits: dict[str, int], expected_version: int, description: str = "") -> dict[str, Any]:
        traits = validate_traits(traits)
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute("SELECT config_id,version FROM personality_active WHERE singleton=1").fetchone()
            if int(active["version"]) != int(expected_version):
                db.rollback()
                raise RuntimeError("The active personality changed in another session. Reload before applying your draft.")
            next_version = int(active["version"]) + 1
            config_id, now = str(uuid.uuid4()), _now()
            db.execute("INSERT INTO personality_configs VALUES(?,?,?,?,?,?,1)",
                       (config_id, next_version, json.dumps(traits), now, description[:300], "studio"))
            db.execute("UPDATE personality_active SET config_id=?,version=?,updated_at=? WHERE singleton=1",
                       (config_id, next_version, now))
            db.commit()
        return self.active()

    def restore(self, config_id: str, expected_version: int) -> dict[str, Any]:
        """Restore a saved version as a new version, including legacy source semantics."""
        with self._lock, self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute("SELECT config_id,version FROM personality_active WHERE singleton=1").fetchone()
            target = db.execute("SELECT * FROM personality_configs WHERE config_id=?", (config_id,)).fetchone()
            if not target:
                db.rollback()
                raise KeyError("Saved personality version not found.")
            if int(active["version"]) != int(expected_version):
                db.rollback()
                raise RuntimeError("The active personality changed in another session. Reload before restoring.")
            now, version, new_id = _now(), int(active["version"]) + 1, str(uuid.uuid4())
            activated = int(target["activated"])
            db.execute("INSERT INTO personality_configs VALUES(?,?,?,?,?,?,?)",
                       (new_id, version, target["traits_json"], now,
                        f"Restored copy of v{target['version']}: {target['description']}",
                        "studio" if activated else "legacy", activated))
            db.execute("UPDATE personality_active SET config_id=?,version=?,updated_at=? WHERE singleton=1",
                       (new_id, version, now))
            db.commit()
        return self.active()

    def presets(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM personality_presets ORDER BY name COLLATE NOCASE").fetchall()
        return [{"preset_id": r["preset_id"], "name": r["name"], "traits": json.loads(r["traits_json"]),
                 "created_at": r["created_at"], "updated_at": r["updated_at"], "description": r["description"]}
                for r in rows]

    def save_preset(self, name: str, traits: dict[str, int], description: str = "", preset_id: str | None = None):
        name = " ".join(str(name).split())
        if not name or len(name) > 80:
            raise ValueError("Preset names must be between 1 and 80 characters.")
        traits = validate_traits(traits)
        now = _now()
        preset_id = preset_id or str(uuid.uuid4())
        with self._connect() as db:
            db.execute("""INSERT INTO personality_presets VALUES(?,?,?,?,?,?)
                ON CONFLICT(preset_id) DO UPDATE SET name=excluded.name, traits_json=excluded.traits_json,
                updated_at=excluded.updated_at, description=excluded.description""",
                (preset_id, name, json.dumps(traits), now, now, str(description)[:300]))
        return next(item for item in self.presets() if item["preset_id"] == preset_id)

    def delete_preset(self, preset_id: str):
        with self._connect() as db:
            db.execute("DELETE FROM personality_presets WHERE preset_id=?", (preset_id,))

    def record_evaluation(self, *, traits, prompt, response, model, evaluation, config=None, evaluator_model=None):
        evaluation_id, created_at = str(uuid.uuid4()), _now()
        with self._connect() as db:
            db.execute("INSERT INTO personality_evaluations VALUES(?,?,?,?,?,?,?,?,?,?)", (
                evaluation_id, created_at, json.dumps(validate_traits(traits)),
                config.get("config_id") if config else None, config.get("version") if config else None,
                str(model), prompt, response, evaluator_model, json.dumps(evaluation, ensure_ascii=False)))
        return {"evaluation_id": evaluation_id, "created_at": created_at, "traits": traits,
                "config_id": config.get("config_id") if config else None,
                "config_version": config.get("version") if config else None, "model": model,
                "prompt": prompt, "response": response, "evaluator_model": evaluator_model,
                "evaluation": evaluation}

    def evaluations(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM personality_evaluations ORDER BY created_at DESC LIMIT ?", (min(max(limit, 1), 500),)).fetchall()
        return [{"evaluation_id": r["evaluation_id"], "created_at": r["created_at"],
                 "traits": json.loads(r["traits_json"]), "config_id": r["config_id"],
                 "config_version": r["config_version"], "model": r["model"], "prompt": r["prompt"],
                 "response": r["response"], "evaluator_model": r["evaluator_model"],
                 "evaluation": json.loads(r["evaluation_json"])} for r in rows]
