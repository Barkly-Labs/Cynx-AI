"""Persistent response feedback, tied to and learned through the legacy store."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai.knowledge.store import KnowledgeStore, _terms


FEEDBACK_CATEGORIES = {
    "misunderstood_intent", "unnecessary_refusal", "generic_or_robotic",
    "incorrect_information", "missed_context", "forgot_previous_information",
    "inappropriate_tone", "other",
}
EVALUATION_DIMENSIONS = ("intent_recognition", "context_awareness", "helpfulness", "tone",
                         "safety", "personalization", "memory_use")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FeedbackService:
    """Store feedback only after a user rates a specific generated response."""

    CACHE_SECONDS = 4 * 60 * 60
    CACHE_LIMIT = 500

    def __init__(self, db_path: str | Path, knowledge_store: KnowledgeStore):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.knowledge_store = knowledge_store
        self._lock = threading.RLock()
        self._responses: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._initialize()

    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        return db

    def _initialize(self):
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS response_feedback (
                feedback_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                user_input TEXT NOT NULL,
                assistant_response TEXT NOT NULL,
                rating TEXT NOT NULL CHECK(rating IN ('up','down')),
                explanation TEXT NOT NULL DEFAULT '',
                category TEXT,
                model TEXT,
                model_version TEXT,
                prompt_version TEXT,
                configuration_version INTEGER,
                personality_version INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                processing_status TEXT NOT NULL DEFAULT 'received',
                related_knowledge_ids TEXT NOT NULL DEFAULT '[]'
            )""")
            db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_response_feedback_identity
                ON response_feedback(user_id,conversation_id,message_id)""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_response_feedback_scope ON response_feedback(user_id,created_at)")
            db.execute("""CREATE TABLE IF NOT EXISTS response_evaluations (
                evaluation_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                reference_feedback_ids TEXT NOT NULL,
                model TEXT,
                evaluation_json TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                error_code TEXT,
                UNIQUE(user_id,conversation_id,message_id)
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_response_evaluations_scope ON response_evaluations(user_id,status,created_at)")

    @staticmethod
    def validate_rating(rating: Any, explanation: Any = "", category: Any = None) -> tuple[str, str, str | None]:
        if rating not in {"up", "down"}:
            raise ValueError("Rating must be 'up' or 'down'.")
        if not isinstance(explanation, str) or len(explanation) > 1500:
            raise ValueError("Explanation must be text of up to 1,500 characters.")
        if category is not None and category not in FEEDBACK_CATEGORIES:
            raise ValueError("Choose one of the available feedback reasons.")
        if rating == "up":
            category = None
        return rating, explanation.strip(), category

    @staticmethod
    def _uuid(value: Any, label: str) -> str:
        try:
            return str(uuid.UUID(str(value)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError(f"{label} must be a valid identifier.") from exc

    def register_response(self, *, message_id: str, conversation_id: str, user_id: str,
                          user_input: str, assistant_response: str, model: str | None,
                          model_version: str | None, prompt_version: str | None,
                          configuration_version: int | None, personality_version: int | None) -> None:
        message_id = self._uuid(message_id, "Message ID")
        conversation_id = self._uuid(conversation_id, "Conversation ID")
        if not isinstance(user_input, str) or not isinstance(assistant_response, str):
            return
        if not assistant_response.strip() or len(user_input) > 12000 or len(assistant_response) > 30000:
            return
        record = {"message_id": message_id, "conversation_id": conversation_id, "user_id": str(user_id),
                  "user_input": user_input, "assistant_response": assistant_response,
                  "model": (model or "")[:200], "model_version": (model_version or model or "")[:200],
                  "prompt_version": (prompt_version or "")[:200],
                  "configuration_version": configuration_version, "personality_version": personality_version}
        now = time.monotonic()
        with self._lock:
            self._prune_cache(now)
            self._responses[message_id] = (now, record)
            self._responses.move_to_end(message_id)
            while len(self._responses) > self.CACHE_LIMIT:
                self._responses.popitem(last=False)

    def _prune_cache(self, now=None):
        now = now or time.monotonic()
        expired = [key for key, (created, _) in self._responses.items() if now - created > self.CACHE_SECONDS]
        for key in expired:
            self._responses.pop(key, None)

    def can_rate(self, message_id: str, conversation_id: str, user_id: str) -> bool:
        try:
            message_id = self._uuid(message_id, "Message ID")
            conversation_id = self._uuid(conversation_id, "Conversation ID")
        except ValueError:
            return False
        with self._lock:
            self._prune_cache()
            cached = self._responses.get(message_id)
            if cached and cached[1]["conversation_id"] == conversation_id and cached[1]["user_id"] == user_id:
                return True
        with self._connect() as db:
            return db.execute("""SELECT 1 FROM response_feedback
                WHERE message_id=? AND conversation_id=? AND user_id=?""",
                (message_id, conversation_id, user_id)).fetchone() is not None

    def submit(self, *, message_id: str, conversation_id: str, user_id: str,
               rating: str, explanation: str = "", category: str | None = None) -> dict[str, Any]:
        message_id = self._uuid(message_id, "Message ID")
        conversation_id = self._uuid(conversation_id, "Conversation ID")
        rating, explanation, category = self.validate_rating(rating, explanation, category)
        now = _now()
        with self._lock:
            self._prune_cache()
            cached_entry = self._responses.get(message_id)
            cached = cached_entry[1] if cached_entry else None
            if cached and (cached["conversation_id"] != conversation_id or cached["user_id"] != user_id):
                cached = None
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                old = db.execute("""SELECT * FROM response_feedback
                    WHERE user_id=? AND conversation_id=? AND message_id=?""",
                    (user_id, conversation_id, message_id)).fetchone()
                if not old and not cached:
                    db.rollback()
                    raise KeyError("This response is no longer available for feedback.")
                feedback_id = old["feedback_id"] if old else str(uuid.uuid4())
                if old:
                    values = (rating, explanation, category, now, old["feedback_id"])
                    db.execute("""UPDATE response_feedback SET rating=?,explanation=?,category=?,
                        updated_at=?,processing_status='candidate_pending' WHERE feedback_id=?""", values)
                    row = dict(old)
                    row.update({"rating": rating, "explanation": explanation, "category": category, "updated_at": now,
                                "processing_status": "candidate_pending"})
                else:
                    row = {**cached, "feedback_id": feedback_id, "rating": rating,
                           "explanation": explanation, "category": category,
                           "created_at": now, "updated_at": now,
                           "processing_status": "candidate_pending", "related_knowledge_ids": "[]"}
                    db.execute("""INSERT INTO response_feedback
                        (feedback_id,conversation_id,message_id,user_id,user_input,assistant_response,
                         rating,explanation,category,model,model_version,prompt_version,
                         configuration_version,personality_version,created_at,updated_at,processing_status)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (feedback_id, conversation_id, message_id, user_id, cached["user_input"],
                         cached["assistant_response"], rating, explanation, category, cached["model"],
                         cached["model_version"], cached["prompt_version"], cached["configuration_version"],
                         cached["personality_version"], now, now, "candidate_pending"))
                # A bare positive rating is useful as a historical example,
                # but not enough to infer a learning rule on its own.
                if rating == "down" or explanation:
                    knowledge_id = self.knowledge_store.save_candidate(row, connection=db)
                    related_ids = [knowledge_id]
                    processing_status = "candidate_created"
                else:
                    db.execute("DELETE FROM knowledge WHERE source_feedback_id=? AND status='unverified'",
                               (feedback_id,))
                    related_ids = []
                    processing_status = "recorded"
                db.execute("UPDATE response_feedback SET processing_status=?,related_knowledge_ids=? WHERE feedback_id=?",
                           (processing_status, json.dumps(related_ids), feedback_id))
                db.commit()
                row["related_knowledge_ids"] = json.dumps(related_ids)
                row["processing_status"] = processing_status
                return self.public_feedback(row)

    @staticmethod
    def public_feedback(row: dict | sqlite3.Row | None):
        if not row:
            return None
        result = dict(row)
        related = result.get("related_knowledge_ids", "[]")
        try:
            result["related_knowledge_ids"] = json.loads(related) if isinstance(related, str) else related
        except ValueError:
            result["related_knowledge_ids"] = []
        # The client does not need stored conversation text echoed back.
        result.pop("user_input", None)
        result.pop("assistant_response", None)
        return result

    def get(self, message_id: str, conversation_id: str, user_id: str):
        message_id = self._uuid(message_id, "Message ID")
        conversation_id = self._uuid(conversation_id, "Conversation ID")
        with self._connect() as db:
            row = db.execute("""SELECT * FROM response_feedback WHERE user_id=? AND conversation_id=? AND message_id=?""",
                             (user_id, conversation_id, message_id)).fetchone()
            evaluation = db.execute("""SELECT * FROM response_evaluations
                WHERE user_id=? AND conversation_id=? AND message_id=?""",
                                    (user_id, conversation_id, message_id)).fetchone()
        return {"feedback": self.public_feedback(row), "comparison": self.public_evaluation(evaluation)}

    def delete(self, message_id: str, conversation_id: str, user_id: str):
        message_id = self._uuid(message_id, "Message ID")
        conversation_id = self._uuid(conversation_id, "Conversation ID")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT feedback_id FROM response_feedback
                WHERE user_id=? AND conversation_id=? AND message_id=?""", (user_id, conversation_id, message_id)).fetchone()
            if not row:
                db.rollback()
                return False
            db.execute("DELETE FROM knowledge WHERE source_feedback_id=? AND user_id=?", (row["feedback_id"], user_id))
            db.execute("DELETE FROM response_feedback WHERE feedback_id=?", (row["feedback_id"],))
            db.execute("DELETE FROM response_evaluations WHERE user_id=? AND conversation_id=? AND message_id=?",
                       (user_id, conversation_id, message_id))
            db.commit()
        return True

    def search_examples(self, user_id: str, query: str, limit: int = 3) -> list[dict[str, Any]]:
        terms = _terms(query)
        if not terms:
            return []
        with self._connect() as db:
            rows = db.execute("""SELECT feedback_id,message_id,rating,category,explanation,user_input,
                assistant_response,model,created_at FROM response_feedback WHERE user_id=?
                ORDER BY updated_at DESC LIMIT 500""", (user_id,)).fetchall()
        results = []
        for row in rows:
            record = dict(row)
            matched = terms.intersection(_terms(" ".join(str(record.get(key) or "")
                                                   for key in ("user_input", "category", "explanation"))))
            if not matched:
                continue
            score = len(matched) / len(terms)
            if score < 0.2:
                continue
            record["relevance"] = round(score, 3)
            results.append(record)
        results.sort(key=lambda item: item["created_at"], reverse=True)
        results.sort(key=lambda item: -item["relevance"])
        return results[:min(max(int(limit), 0), 10)]

    def evaluation_history(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("""SELECT * FROM response_evaluations WHERE user_id=?
                ORDER BY created_at DESC LIMIT ?""", (user_id, min(max(int(limit), 1), 500))).fetchall()
        return [self.public_evaluation(row) for row in rows]

    def queue_evaluation(self, *, message_id: str, conversation_id: str, user_id: str,
                         reference_feedback_ids: list[str], model: str | None):
        now, evaluation_id = _now(), str(uuid.uuid4())
        with self._connect() as db:
            db.execute("""INSERT INTO response_evaluations
                (evaluation_id,conversation_id,message_id,user_id,reference_feedback_ids,model,
                 evaluation_json,status,created_at,updated_at,error_code)
                VALUES (?,?,?,?,?,?,NULL,'queued',?,?,NULL)
                ON CONFLICT(user_id,conversation_id,message_id) DO UPDATE SET
                 reference_feedback_ids=excluded.reference_feedback_ids,model=excluded.model,
                 evaluation_json=NULL,status='queued',updated_at=excluded.updated_at,error_code=NULL""",
                (evaluation_id, conversation_id, message_id, user_id,
                 json.dumps(reference_feedback_ids), model, now, now))
            row = db.execute("SELECT evaluation_id FROM response_evaluations WHERE user_id=? AND conversation_id=? AND message_id=?",
                             (user_id, conversation_id, message_id)).fetchone()
        return row[0]

    def finish_evaluation(self, evaluation_id: str, assessment: dict | None, error_code: str | None = None):
        now = _now()
        status = "completed" if assessment is not None else "failed"
        with self._connect() as db:
            db.execute("UPDATE response_evaluations SET evaluation_json=?,status=?,updated_at=?,error_code=? WHERE evaluation_id=?",
                       (json.dumps(assessment, ensure_ascii=False) if assessment else None, status, now,
                        error_code, evaluation_id))

    @staticmethod
    def public_evaluation(row):
        if not row:
            return None
        result = dict(row)
        for key in ("reference_feedback_ids", "evaluation_json"):
            try:
                result[key] = json.loads(result[key]) if result.get(key) else None
            except (TypeError, ValueError):
                result[key] = None
        result.pop("user_id", None)
        return result

    @staticmethod
    def validate_assessment(data: Any, response_text: str) -> dict[str, Any]:
        """Keep only bounded scores with evidence found in the actual reply."""
        if not isinstance(data, dict) or not isinstance(data.get("dimensions"), list):
            raise ValueError("Evaluator result must contain dimensions.")
        by_name = {item.get("name"): item for item in data["dimensions"] if isinstance(item, dict)}
        dimensions = []
        for name in EVALUATION_DIMENSIONS:
            item = by_name.get(name, {})
            score, confidence, evidence = item.get("score"), item.get("confidence"), item.get("evidence")
            if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
                score = None
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                confidence = None
            if not isinstance(evidence, str) or len(evidence) > 240 or evidence not in response_text:
                evidence = ""
                score, confidence = None, None
            dimensions.append({"name": name, "score": score, "confidence": confidence, "evidence": evidence})
        limitations = data.get("limitations")
        if not isinstance(limitations, str):
            limitations = "Evaluator interpretation; not objective evidence."
        return {"dimensions": dimensions, "limitations": limitations[:500]}
