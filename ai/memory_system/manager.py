"""
MemoryManager

Handles:
- remembering memories
- searching memories
- recalling memories
- retrieving recent memories
- retrieving all memories
- deleting memories
- updating memories

Uses the existing SQLite memories table.
"""

import json
import re


class MemoryManager:

    def __init__(self, conn):

        self.conn = conn

        print("===== MEMORY MANAGER DATABASE CHECK =====")

        cur = self.conn.cursor()

        cur.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            """)

        print(cur.fetchall())

        print("=========================================")

    # ---------------------------------
    # Remember
    # ---------------------------------

    def remember(self, user_id, content, category="general", importance=5):

        if not content:

            return None

        cur = self.conn.cursor()

        try:

            print("[MEMORY SAVE]")
            print("USER ID:", user_id)
            print("CONTENT:", content)
            print("CATEGORY:", category)

            cur.execute(
                """
                INSERT INTO memories
                (
                    user_id,
                    kind,
                    content,
                    importance,
                    tags,
                    metadata
                )

                VALUES (?, ?, ?, ?, ?, ?)

                """,
                (
                    user_id,
                    category,
                    content,
                    importance,
                    json.dumps([category]),
                    json.dumps({"source": "memory_manager"}),
                ),
            )

            print("[MEMORY INSERTED]")

            print("ROW ID:", cur.lastrowid)

            self.conn.commit()

            print("[MEMORY COMMITTED]")

            return cur.lastrowid

        except Exception as e:

            self.conn.rollback()

            print("[MEMORY ERROR]", e)

            return None

    # ---------------------------------
    # Recall Memories
    # ---------------------------------

    def recall(self, user_id, limit=5, min_importance=1, categories=None):

        cur = self.conn.cursor()

        try:

            if categories:

                placeholders = ",".join("?" for _ in categories)

                cur.execute(
                    f"""
                    SELECT
                        id,
                        user_id,
                        kind,
                        content,
                        importance,
                        created_at

                    FROM memories

                    WHERE user_id=?
                    AND importance>=?
                    AND kind IN ({placeholders})

                    ORDER BY importance DESC,
                             created_at DESC

                    LIMIT ?

                    """,
                    (user_id, min_importance, *categories, limit),
                )

            else:

                cur.execute(
                    """
                    SELECT
                        id,
                        user_id,
                        kind,
                        content,
                        importance,
                        created_at

                    FROM memories

                    WHERE user_id=?
                    AND importance>=?

                    ORDER BY importance DESC,
                             created_at DESC

                    LIMIT ?

                    """,
                    (user_id, min_importance, limit),
                )

            return cur.fetchall()

        except Exception as e:

            print("[MEMORY RECALL ERROR]", e)

            return []

    # ---------------------------------
    # Search Memories
    # ---------------------------------

    def search(self, user_id, query, limit=5):

        # Score distinct, meaningful terms instead of raw substrings. The old
        # implementation gave every positive-importance memory a score even
        # with zero query overlap, and tiny words such as "me" could match
        # inside unrelated sensitive memories.
        stop_words = {
            "a", "about", "after", "again", "all", "also", "am", "an", "and",
            "any", "are", "as", "at", "be", "because", "been", "before", "best",
            "but", "by", "can", "could", "did", "do", "does", "find", "for", "from",
            "get", "give", "had", "has", "have", "hey", "how", "i", "im", "in", "is",
            "it", "its", "me", "my", "of", "on", "or", "please", "search", "some",
            "tell", "that", "the", "their", "them", "there", "this", "to", "up", "was",
            "what", "when", "where", "which", "who", "why", "with", "would", "you",
            "your", "amazon", "online", "product", "products", "shop", "shopping",
            "adult", "adults", "recommend", "recommendation", "recommendations",
        }

        words = {
            word for word in re.findall(r"[a-z0-9]{3,}", str(query or "").lower())
            if word not in stop_words
        }
        if not words:
            return []

        cur = self.conn.cursor()

        try:

            cur.execute(
                """
                SELECT
                    id,
                    kind,
                    content,
                    importance,
                    tags

                FROM memories

                WHERE user_id=?

                """,
                (user_id,),
            )

            results = []

            for row in cur.fetchall():

                content_words = set(re.findall(r"[a-z0-9]{3,}", str(row[2] or "").lower()))
                overlap = words.intersection(content_words)

                # Importance ranks relevant memories; it never makes an
                # unrelated record eligible for injection by itself.
                if overlap:
                    score = len(overlap) + (row[3] or 0) * 0.01

                    results.append(
                        {
                            "id": row[0],
                            "kind": row[1],
                            "content": row[2],
                            "importance": row[3],
                            "score": score,
                            "matched_terms": sorted(overlap),
                        }
                    )

            results.sort(key=lambda x: x["score"], reverse=True)

            return [memory["content"] for memory in results[:limit]]

        except Exception as e:

            print("[MEMORY SEARCH ERROR]", e)

            return []

    # ---------------------------------
    # Get All Memories
    # ---------------------------------

    def get_all_memories(self, user_id):

        cur = self.conn.cursor()

        try:

            cur.execute(
                """
                SELECT
                    id,
                    user_id,
                    kind,
                    content,
                    importance,
                    tags,
                    metadata,
                    created_at

                FROM memories

                WHERE user_id=?

                ORDER BY created_at DESC

                """,
                (user_id,),
            )

            return cur.fetchall()

        except Exception as e:

            print("[MEMORY ERROR]", e)

            return []

    # ---------------------------------
    # Recent Memories
    # ---------------------------------

    def recent(self, limit=10):

        cur = self.conn.cursor()

        try:

            cur.execute(
                """
                SELECT *

                FROM memories

                ORDER BY created_at DESC

                LIMIT ?

                """,
                (limit,),
            )

            return cur.fetchall()

        except Exception as e:

            print("[MEMORY ERROR]", e)

            return []

    # ---------------------------------
    # Delete Memory
    # ---------------------------------

    def delete_memory(self, memory_id):

        cur = self.conn.cursor()

        try:

            cur.execute(
                """
                DELETE FROM memories

                WHERE id=?

                """,
                (memory_id,),
            )

            self.conn.commit()

            return True

        except Exception as e:

            self.conn.rollback()

            print("[MEMORY ERROR]", e)

            return False

    # ---------------------------------
    # Update Memory
    # ---------------------------------

    def update_memory(self, memory_id, importance=None, content=None):

        cur = self.conn.cursor()

        try:

            if importance is not None:

                cur.execute(
                    """
                    UPDATE memories

                    SET importance=?

                    WHERE id=?

                    """,
                    (importance, memory_id),
                )

            if content is not None:

                cur.execute(
                    """
                    UPDATE memories

                    SET content=?

                    WHERE id=?

                    """,
                    (content, memory_id),
                )

            self.conn.commit()

            return True

        except Exception as e:

            self.conn.rollback()

            print("[MEMORY ERROR]", e)

            return False

    # ---------------------------------
    # Format Memories For Prompt
    # ---------------------------------

    def format_for_prompt(self, memories):

        if not memories:

            return ""

        formatted = []

        for memory in memories:

            if isinstance(memory, str):

                formatted.append(memory)

                continue

            if isinstance(memory, dict):

                content = memory.get("content", "")

                if content:

                    formatted.append(content)

                continue

            # SQLite tuple

            try:

                content = memory[3]

                if content:

                    formatted.append(content)

            except Exception:

                formatted.append(str(memory))

        return "\n".join(formatted)
