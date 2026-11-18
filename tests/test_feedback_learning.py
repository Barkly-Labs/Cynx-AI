import tempfile
import unittest
import uuid
from pathlib import Path

from ai.context_manager import ContextManager
from ai.feedback.service import FeedbackService
from ai.knowledge.store import KnowledgeStore
from memory.sqlite import connect


class EmptyMemory:
    def search(self, user_id, query, limit=5):
        return []


class FeedbackLearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "cyn.db"
        self.conn = connect(self.db_path)
        self.store = KnowledgeStore(self.conn)
        self.feedback = FeedbackService(self.db_path, self.store)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_legacy_table_migrates_and_irrelevant_search_does_not_match(self):
        self.conn.execute("INSERT INTO knowledge(category,title,content,importance) VALUES(?,?,?,?)",
                          ("legacy", "Existing", "Existing note about rabbits", 10))
        self.conn.commit()
        self.assertEqual(self.store.search("volcano astronomy", limit=3), [])
        row = self.store.list_records(limit=10)[0]
        self.assertEqual(row["knowledge_type"], "legacy")
        self.assertEqual(row["content"], "Existing note about rabbits")

    def test_feedback_creates_scoped_candidate_and_reviewed_context(self):
        message_id, conversation_id = str(uuid.uuid4()), str(uuid.uuid4())
        self.feedback.register_response(message_id=message_id, conversation_id=conversation_id,
            user_id="alice", user_input="I need help fixing my Minecraft storage sorter", assistant_response="Try this.",
            model="local-test", model_version="local-test", prompt_version="p1", configuration_version=2,
            personality_version=1)
        saved = self.feedback.submit(message_id=message_id, conversation_id=conversation_id, user_id="alice",
            rating="down", category="missed_context", explanation="Use the prior chest layout I described.")
        self.assertEqual(saved["processing_status"], "candidate_created")
        self.assertEqual(len(self.store.list_records(user_id="alice", status="unverified")), 1)
        self.assertEqual(self.store.search_records("Minecraft storage sorter", user_id="bob"), [])
        self.assertTrue(self.store.search_records("Minecraft storage sorter", user_id="alice"))
        self.assertTrue(self.feedback.can_rate(message_id, conversation_id, "alice"))
        self.assertNotIn("assistant_response", self.feedback.get(message_id, conversation_id, "alice")["feedback"])
        self.store.review(saved["related_knowledge_ids"][0], "correct", corrected_content="Use the previously agreed chest layout.")
        # Reopen the database and all stores to simulate an application restart.
        self.conn.close()
        self.conn = connect(self.db_path)
        self.store = KnowledgeStore(self.conn)
        self.feedback = FeedbackService(self.db_path, self.store)
        lessons = self.store.search("Minecraft storage sorter", user_id="alice")
        self.assertTrue(any("previously agreed chest layout" in item for item in lessons))
        self.assertEqual(self.store.search("Minecraft storage sorter", user_id="bob"), [])
        context = ContextManager(EmptyMemory(), self.store, self.feedback).build_context("alice", "Minecraft storage sorter")
        self.assertIn("previously agreed chest layout", context["knowledge"])

    def test_feedback_upsert_and_delete(self):
        message_id, conversation_id = str(uuid.uuid4()), str(uuid.uuid4())
        self.feedback.register_response(message_id=message_id, conversation_id=conversation_id,
            user_id="alice", user_input="Explain local Ollama setup", assistant_response="Here is a guide.",
            model="local", model_version="local", prompt_version="p1", configuration_version=1,
            personality_version=1)
        self.feedback.submit(message_id=message_id, conversation_id=conversation_id, user_id="alice", rating="up")
        changed = self.feedback.submit(message_id=message_id, conversation_id=conversation_id, user_id="alice",
            rating="down", category="generic_or_robotic", explanation="Please be specific.")
        self.assertEqual(changed["rating"], "down")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM knowledge WHERE source_feedback_id=?",
                         (changed["feedback_id"],)).fetchone()[0], 1)
        restarted = FeedbackService(self.db_path, KnowledgeStore(self.conn))
        self.assertEqual(restarted.get(message_id, conversation_id, "alice")["feedback"]["rating"], "down")
        self.assertTrue(restarted.delete(message_id, conversation_id, "alice"))
        self.assertIsNone(restarted.get(message_id, conversation_id, "alice")["feedback"])

    def test_context_includes_user_feedback_and_excludes_other_user(self):
        message_id, conversation_id = str(uuid.uuid4()), str(uuid.uuid4())
        self.feedback.register_response(message_id=message_id, conversation_id=conversation_id,
            user_id="alice", user_input="Minecraft chest sorter", assistant_response="Sort by item type.",
            model="local", model_version="local", prompt_version="p1", configuration_version=1,
            personality_version=1)
        self.feedback.submit(message_id=message_id, conversation_id=conversation_id, user_id="alice",
            rating="down", category="missed_context", explanation="Remember my earlier hopper layout.")
        context = ContextManager(EmptyMemory(), self.store, self.feedback).build_context("alice", "Minecraft chest sorter")
        self.assertIn("unverified", context["knowledge"].lower())
        other = ContextManager(EmptyMemory(), self.store, self.feedback).build_context("bob", "Minecraft chest sorter")
        self.assertNotIn("hopper layout", other["knowledge"].lower())

    def test_ratings_and_payload_fields_are_validated(self):
        with self.assertRaises(ValueError):
            self.feedback.submit(message_id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()),
                user_id="alice", rating="maybe")
        with self.assertRaises(ValueError):
            self.feedback.submit(message_id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()),
                user_id="alice", rating="down", explanation="x" * 1501)

    def test_comparison_assessment_rejects_unverified_evidence(self):
        assessed = self.feedback.validate_assessment({"dimensions": [
            {"name": "helpfulness", "score": 5, "confidence": 0.8, "evidence": "invented quote"},
            {"name": "tone", "score": 4, "confidence": 0.7, "evidence": "Thanks for sharing."}],
            "limitations": "Model-judged."}, "Thanks for sharing.")
        values = {item["name"]: item for item in assessed["dimensions"]}
        self.assertIsNone(values["helpfulness"]["score"])
        self.assertEqual(values["tone"]["score"], 4)
        self.assertEqual(len(values), 7)

    def test_shared_review_requires_generalization_and_removes_private_candidate_text(self):
        message_id, conversation_id = str(uuid.uuid4()), str(uuid.uuid4())
        self.feedback.register_response(message_id=message_id, conversation_id=conversation_id,
            user_id="alice", user_input="My private family situation", assistant_response="Old reply.",
            model="local", model_version="local", prompt_version="p1", configuration_version=1,
            personality_version=1)
        saved = self.feedback.submit(message_id=message_id, conversation_id=conversation_id, user_id="alice",
            rating="down", category="missed_context", explanation="Remember the private details I already shared.")
        candidate_id = saved["related_knowledge_ids"][0]
        with self.assertRaises(ValueError):
            self.store.review(candidate_id, "accept", knowledge_type="behavioral_lesson")
        shared = self.store.review(candidate_id, "accept", knowledge_type="behavioral_lesson",
                                   corrected_content="Use relevant established context when it changes the answer.")
        self.assertIsNone(shared["user_id"])
        self.assertEqual(shared["content"], "Use relevant established context when it changes the answer.")
        self.assertNotIn("private family situation", shared["learning_data_json"])

    def test_unrated_saved_response_can_be_registered_after_service_restart(self):
        message_id, conversation_id = str(uuid.uuid4()), str(uuid.uuid4())
        after_restart = FeedbackService(self.db_path, self.store)
        self.assertFalse(after_restart.can_rate(message_id, conversation_id, "alice"))
        after_restart.register_response(message_id=message_id, conversation_id=conversation_id,
            user_id="alice", user_input="Saved local user message", assistant_response="Saved local answer",
            model="local", model_version="local", prompt_version="p2", configuration_version=2,
            personality_version=1)
        result = after_restart.submit(message_id=message_id, conversation_id=conversation_id, user_id="alice",
            rating="down", explanation="The saved context should have been used.")
        self.assertEqual(result["processing_status"], "candidate_created")


if __name__ == "__main__":
    unittest.main()
