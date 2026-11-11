"""Small helpers for the web conversation regression runner.

This module deliberately does not know how CYN-X generates a response. The web
route supplies the existing production chat-turn function so regression runs
exercise the same ChatEngine path as normal chat.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, List
from uuid import uuid4

MAX_TEST_TEXT_BYTES = 64 * 1024
MAX_TEST_TURNS = 200


def parse_test_text(text: str) -> List[str]:
    """Parse one non-empty, non-comment line as one user turn."""
    if not isinstance(text, str):
        raise ValueError("Test conversation must be text.")
    if len(text.encode("utf-8")) > MAX_TEST_TEXT_BYTES:
        raise ValueError("Test conversation is too large (64 KiB maximum).")

    turns = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not turns:
        raise ValueError("Test conversation contains no user turns.")
    if len(turns) > MAX_TEST_TURNS:
        raise ValueError(f"Test conversation has too many turns ({MAX_TEST_TURNS} maximum).")
    return turns


@dataclass
class ConversationTestSession:
    session_id: str
    conversation_key: str
    results: List[Dict[str, str]] = field(default_factory=list)


class ConversationTestSessions:
    """In-memory test-session metadata; ChatEngine owns the actual history."""

    def __init__(self):
        self._sessions: Dict[str, ConversationTestSession] = {}

    def create(self) -> ConversationTestSession:
        session_id = uuid4().hex
        session = ConversationTestSession(
            session_id=session_id,
            conversation_key=f"conversation_test:{session_id}",
        )
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> ConversationTestSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError("Unknown or expired conversation test session.") from exc

    def finish(self, session_id: str) -> ConversationTestSession | None:
        return self._sessions.pop(session_id, None)

    def run_turn(
        self,
        session_id: str,
        message: str,
        turn_processor: Callable[[str, str], str],
    ) -> Dict[str, str]:
        session = self.get(session_id)
        response = turn_processor(message, session.conversation_key)
        result = {"user": message, "assistant": response}
        session.results.append(result)
        return result
