import pytest

from interfaces.web.conversation_test import (
    ConversationTestSessions,
    MAX_TEST_TEXT_BYTES,
    parse_test_text,
)


def test_parse_plain_text_one_nonempty_line_per_turn():
    assert parse_test_text("hello\nsecond turn\nthird") == [
        "hello", "second turn", "third"
    ]


def test_parse_ignores_blank_lines_and_comments():
    text = "\n# greeting\n heeeyyyyyyyy :3 \n\n# affection\ni missed you mommy\n"
    assert parse_test_text(text) == ["heeeyyyyyyyy :3", "i missed you mommy"]


def test_parse_rejects_oversized_input():
    with pytest.raises(ValueError, match="too large"):
        parse_test_text("x" * (MAX_TEST_TEXT_BYTES + 1))


def test_runner_preserves_turn_order_and_conversation_key():
    sessions = ConversationTestSessions()
    session = sessions.create()
    calls = []

    def production_turn(message, conversation_key):
        calls.append((message, conversation_key))
        return f"reply-{len(calls)}"

    first = sessions.run_turn(session.session_id, "one", production_turn)
    second = sessions.run_turn(session.session_id, "two", production_turn)

    assert calls == [
        ("one", session.conversation_key),
        ("two", session.conversation_key),
    ]
    assert first == {"user": "one", "assistant": "reply-1"}
    assert second == {"user": "two", "assistant": "reply-2"}
    assert session.results == [first, second]


def test_failed_turn_is_not_recorded_so_retry_is_safe():
    sessions = ConversationTestSessions()
    session = sessions.create()

    def failed_turn(message, conversation_key):
        raise RuntimeError("backend unavailable")

    with pytest.raises(RuntimeError, match="backend unavailable"):
        sessions.run_turn(session.session_id, "one", failed_turn)

    assert session.results == []


def test_finish_removes_session():
    sessions = ConversationTestSessions()
    session = sessions.create()
    assert sessions.finish(session.session_id) is session
    with pytest.raises(KeyError):
        sessions.get(session.session_id)
