"""Search and manage the existing SQLite knowledge table."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any


_STOP_WORDS = {
    "about", "after", "again", "also", "and", "are", "because", "been", "before",
    "being", "but", "can", "could", "did", "does", "for", "from", "get", "give",
    "had", "has", "have", "how", "into", "its", "just", "like", "might", "more",
    "most", "not", "our", "out", "please", "should", "some", "such", "than", "that",
    "the", "their", "them", "then", "there", "these", "they", "this", "those", "through",
    "under", "very", "what", "when", "where", "which", "while", "who", "will", "with",
    "would", "you", "your",
}

_LESSON_BY_CATEGORY = {
    "misunderstood_intent": "Check what the user actually asked for. Distinguish personal disclosure and general discussion from requests for actionable assistance.",
    "unnecessary_refusal": "Identify the specific action requested before refusing. Do not infer a harmful request from a topic mention alone.",
    "generic_or_robotic": "Address the details and emotional register of the current situation instead of defaulting to a generic response.",
    "incorrect_information": "Verify claims, state uncertainty, and avoid repeating unsupported information.",
    "missed_context": "Check relevant established context and use it when it materially changes the response.",
    "forgot_previous_information": "Use relevant prior context when the user refers to it; ask briefly when the reference is unclear.",
    "inappropriate_tone": "Match the user's current tone and stated preferences without overdoing a persona.",
    "other": "Use the user's explanation as a signal about this situation; clarify intent when it remains ambiguous.",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _terms(value: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z0-9]{3,}", str(value or "").lower())
        if word not in _STOP_WORDS
    }


class KnowledgeStore:
    """Compatibility-preserving access to CYN-X's legacy ``knowledge`` table."""

    def __init__(self, conn):
        self.conn = conn

    def add(self, content, title="", category="general", importance=5, tags=None,
            *, knowledge_type="legacy", user_id=None, status="active", confidence=None,
            source_feedback_id=None, learning_data=None):
        """Add a note to the existing table; legacy call signatures still work."""
        cur = self.conn.execute(
            """INSERT INTO knowledge
                (category,title,content,importance,tags,knowledge_type,user_id,
                 source_feedback_id,status,confidence,updated_at,learning_data_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (category, title, content, importance, json.dumps(tags or [], ensure_ascii=False),
             knowledge_type, user_id, source_feedback_id, status, confidence, _now(),
             json.dumps(learning_data, ensure_ascii=False) if learning_data is not None else None),
        )
        self.conn.commit()
        return cur.lastrowid

    def search_records(self, query: str, limit: int = 5, user_id: str | None = None,
                       include_unverified: bool = True) -> list[dict[str, Any]]:
        terms = _terms(query)
        if not terms:
            return []
        limit = min(max(int(limit), 0), 50)
        if not limit:
            return []
        # Scope personal notes and pending candidates to their owner. Legacy
        # records remain visible as shared legacy knowledge for compatibility.
        allowed_types = ["legacy", "behavioral_lesson"]
        params: list[Any] = []
        scope = "(user_id IS NULL AND knowledge_type IN (?,?))"
        params.extend(allowed_types)
        if user_id:
            scope += " OR (user_id=? AND knowledge_type='user_context' AND status='active')"
            params.append(user_id)
            if include_unverified:
                scope += " OR (user_id=? AND knowledge_type='unverified_candidate' AND status='unverified')"
                params.append(user_id)
        rows = self.conn.execute(
            f"""SELECT id,category,title,content,importance,tags,created_at,
                       knowledge_type,user_id,source_feedback_id,status,confidence,
                       last_reviewed_at,superseded_by,updated_at,learning_data_json
                FROM knowledge WHERE ({scope}) AND status IN ('active','unverified')""",
            params,
        ).fetchall()
        results = []
        for row in rows:
            record = dict(row) if isinstance(row, dict) else {
                key: row[index] for index, key in enumerate((
                    "id", "category", "title", "content", "importance", "tags", "created_at",
                    "knowledge_type", "user_id", "source_feedback_id", "status", "confidence",
                    "last_reviewed_at", "superseded_by", "updated_at", "learning_data_json",
                ))
            }
            haystack = " ".join(str(record.get(key) or "") for key in ("title", "content", "tags", "learning_data_json"))
            matched = terms.intersection(_terms(haystack))
            if not matched:
                continue
            score = len(matched) / max(1, len(terms)) + max(0, int(record.get("importance") or 0)) * 0.01
            record["score"] = round(score, 4)
            record["matched_terms"] = sorted(matched)
            results.append(record)
        results.sort(key=lambda item: (-item["score"], -int(item.get("importance") or 0), item["id"]))
        return results[:limit]

    def search(self, query, limit=5, user_id=None, include_unverified=True):
        """Return relevant content strings, preserving the legacy API shape."""
        return [record["content"] for record in self.search_records(
            query, limit=limit, user_id=user_id, include_unverified=include_unverified
        )]

    @staticmethod
    def candidate_from_feedback(feedback: dict[str, Any]) -> dict[str, Any]:
        category = feedback.get("category") or "other"
        user_input = str(feedback.get("user_input") or "")[:1500]
        explanation = str(feedback.get("explanation") or "")[:1500]
        behavior = _LESSON_BY_CATEGORY.get(category, _LESSON_BY_CATEGORY["other"])
        confidence = 0.55 if explanation else 0.25
        structured = {
            "schema": "cynx-learning-candidate-v1",
            "knowledge_type": "unverified_candidate",
            "user_intent_or_context": user_input,
            "relevant_conversational_context": user_input,
            "previous_assistant_response": str(feedback.get("assistant_response") or "")[:1200],
            "observed_feedback": {
                "rating": feedback["rating"], "category": category, "explanation": explanation,
                "response_reference": feedback["feedback_id"],
            },
            "behavior_to_consider": behavior,
            "situations": sorted(_terms(user_input))[:20],
            "confidence": confidence,
            "source_feedback_id": feedback["feedback_id"],
            "created_at": feedback.get("created_at") or _now(),
            "last_reviewed_at": None,
            "warning": "User feedback is a signal, not proof. This candidate is unverified and must not be generalized to other users.",
        }
        parts = [f"User feedback signal ({feedback['rating']}; {category})."]
        if user_input:
            parts.append(f"Current user context: {user_input}")
        previous_response = str(feedback.get("assistant_response") or "")[:1200]
        if previous_response:
            parts.append(f"Previous assistant response: {previous_response}")
        if explanation:
            parts.append(f"User explanation: {explanation}")
        parts.append(f"Behavior to consider: {behavior}")
        parts.append("Unverified, user-scoped signal; do not treat as a universal rule.")
        return {"title": f"Unverified response feedback: {category}",
                "content": "\n".join(parts), "category": "response_evaluation",
                "importance": 5, "knowledge_type": "unverified_candidate",
                "user_id": feedback.get("user_id"), "status": "unverified",
                "confidence": confidence, "source_feedback_id": feedback["feedback_id"],
                "learning_data": structured}

    def save_candidate(self, feedback: dict[str, Any], connection=None) -> int:
        db = connection or self.conn
        candidate = self.candidate_from_feedback(feedback)
        now = _now()
        existing = db.execute("SELECT id FROM knowledge WHERE source_feedback_id=?",
                              (feedback["feedback_id"],)).fetchone()
        learning_json = json.dumps(candidate["learning_data"], ensure_ascii=False)
        tags = json.dumps([candidate["category"], feedback.get("rating"), "unverified"], ensure_ascii=False)
        values = (candidate["category"], candidate["title"], candidate["content"], candidate["importance"],
                  tags, candidate["knowledge_type"], candidate["user_id"], candidate["status"],
                  candidate["confidence"], now, learning_json, feedback["feedback_id"])
        if existing:
            knowledge_id = existing[0]
            db.execute("""UPDATE knowledge SET category=?,title=?,content=?,importance=?,tags=?,
                knowledge_type=?,user_id=?,status=?,confidence=?,updated_at=?,learning_data_json=?
                WHERE source_feedback_id=?""", values)
        else:
            cur = db.execute("""INSERT INTO knowledge
                (category,title,content,importance,tags,knowledge_type,user_id,status,confidence,
                 updated_at,learning_data_json,source_feedback_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", values)
            knowledge_id = cur.lastrowid
        if connection is None:
            db.commit()
        return int(knowledge_id)

    def get(self, knowledge_id: int) -> dict[str, Any] | None:
        cursor = self.conn.execute("SELECT * FROM knowledge WHERE id=?", (knowledge_id,))
        row = cursor.fetchone()
        return dict(zip((column[0] for column in cursor.description), row)) if row is not None else None

    def list_records(self, user_id=None, status=None, limit=200):
        clauses, params = [], []
        if user_id is not None:
            clauses.append("user_id=?")
            params.append(user_id)
        if status:
            clauses.append("status=?")
            params.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        cursor = self.conn.execute(
            f"SELECT * FROM knowledge{where} ORDER BY updated_at DESC,created_at DESC LIMIT ?",
            (*params, min(max(int(limit), 1), 500)),
        )
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]

    def review(self, knowledge_id: int, action: str, *, knowledge_type=None,
               corrected_content=None, superseded_by=None):
        allowed = {"user_context", "behavioral_lesson", "response_evaluation"}
        now = _now()
        row = self.conn.execute("SELECT id,user_id,knowledge_type FROM knowledge WHERE id=?", (knowledge_id,)).fetchone()
        if not row:
            raise KeyError("Knowledge record not found.")
        if action == "accept":
            target_type = knowledge_type or "user_context"
            if target_type not in allowed:
                raise ValueError("Choose a supported knowledge type.")
            if target_type == "behavioral_lesson":
                if not isinstance(corrected_content, str) or not corrected_content.strip() or len(corrected_content) > 3000:
                    raise ValueError("Provide a generalized shared lesson up to 3,000 characters.")
                self.conn.execute("""UPDATE knowledge SET content=?,knowledge_type=?,user_id=NULL,status='active',
                    learning_data_json=?,last_reviewed_at=?,updated_at=? WHERE id=?""",
                    (corrected_content.strip(), target_type,
                     json.dumps({"schema": "cynx-learning-candidate-v1", "reviewed_as": target_type,
                                 "source_feedback_id": self.conn.execute("SELECT source_feedback_id FROM knowledge WHERE id=?", (knowledge_id,)).fetchone()[0]}, ensure_ascii=False),
                     now, now, knowledge_id))
                self.conn.commit()
                return self.get(knowledge_id)
            user_id = None if target_type == "behavioral_lesson" else row[1]
            self.conn.execute("""UPDATE knowledge SET knowledge_type=?,user_id=?,status='active',
                last_reviewed_at=?,updated_at=? WHERE id=?""", (target_type, user_id, now, now, knowledge_id))
        elif action == "discard":
            self.conn.execute("UPDATE knowledge SET status='discarded',last_reviewed_at=?,updated_at=? WHERE id=?",
                              (now, now, knowledge_id))
        elif action == "correct":
            if not isinstance(corrected_content, str) or not corrected_content.strip() or len(corrected_content) > 3000:
                raise ValueError("Provide corrected lesson text up to 3,000 characters.")
            current = self.get(knowledge_id)
            if current["knowledge_type"] == "behavioral_lesson":
                if not current.get("user_id"):
                    self.conn.execute("UPDATE knowledge SET content=?,learning_data_json=?,status='active',last_reviewed_at=?,updated_at=? WHERE id=?",
                        (corrected_content.strip(), json.dumps({"schema": "cynx-learning-candidate-v1",
                         "reviewed_as": "behavioral_lesson", "source_feedback_id": current.get("source_feedback_id")}),
                         now, now, knowledge_id))
                else:
                    raise ValueError("Shared behavioral lessons must remain generalized.")
            else:
                self.conn.execute("UPDATE knowledge SET content=?,knowledge_type='user_context',status='active',last_reviewed_at=?,updated_at=? WHERE id=?",
                                  (corrected_content.strip(), now, now, knowledge_id))
        elif action == "supersede":
            if not superseded_by or not self.conn.execute("SELECT 1 FROM knowledge WHERE id=?", (superseded_by,)).fetchone():
                raise ValueError("Choose an existing replacement knowledge record.")
            self.conn.execute("UPDATE knowledge SET status='superseded',superseded_by=?,last_reviewed_at=?,updated_at=? WHERE id=?",
                              (superseded_by, now, now, knowledge_id))
        else:
            raise ValueError("Unsupported review action.")
        self.conn.commit()
        return self.get(knowledge_id)

    def recent(self, limit=10):
        return self.conn.execute("SELECT * FROM knowledge ORDER BY created_at DESC LIMIT ?",
                                 (min(max(int(limit), 1), 500),)).fetchall()
