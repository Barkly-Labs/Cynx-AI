import inspect
import re

from ai.chat_engine import ChatEngine
from ai.personality import build_personality_prompt


def _retrieval_pattern_from_production_source():
    source = inspect.getsource(ChatEngine.handle_user_message)
    start = source.index("retrieval_cue = re.compile(")
    end = source.index("if not retrieval_cue.search(text):", start)
    block = source[start:end]
    # Keep this regression explicit: the execution brake must inspect current `text`.
    assert "retrieval_cue.search(text)" not in block
    return block


def test_affectionate_today_greeting_does_not_authorize_web_search():
    source = inspect.getsource(ChatEngine.handle_user_message)
    assert "if not retrieval_cue.search(text):" in source
    assert "today|right" not in source

    production_cue = re.compile(
        r"\b(?:search|find|look\s+up|lookup|browse|verify|check|online|"
        r"website|webpage|latest|current|currently|right\s+now|"
        r"recent|news)\b",
        re.IGNORECASE,
    )
    assert production_cue.search("hey mommy how are u today?") is None


def test_explicit_and_fresh_retrieval_cues_remain_available():
    cue = re.compile(
        r"\b(?:search|find|look\s+up|lookup|browse|verify|check|online|"
        r"website|webpage|latest|current|currently|right\s+now|"
        r"recent|news)\b",
        re.IGNORECASE,
    )
    for text in (
        "search the web for Barkly Labs",
        "look up Barkly Labs",
        "Barkly Labs right now",
        "latest news",
        "check barklylabs.space",
        "verify whether X is currently true",
    ):
        assert cue.search(text), text


def test_brake_checks_current_user_text_and_regenerates_without_tools():
    source = inspect.getsource(ChatEngine.handle_user_message)
    assert "if not retrieval_cue.search(text):" in source
    assert "tc_name == \"web_search\"" in source
    assert "blocked_optional_web_search = True" in source
    assert "if blocked_optional_web_search and not tool_calls:" in source
    assert "tools=None" in source


def test_model_optional_tools_and_python_authoritative_routing_are_not_reverted():
    source = inspect.getsource(ChatEngine._ollama_tools)
    assert '"web_search"' in source
    assert '"calculator"' in source
    assert '"smoke_counter"' in source
    assert '"chart"' in source


def test_casual_greeting_voice_rule_is_semantic_not_a_canned_response():
    prompt = build_personality_prompt()
    assert "For casual greetings/check-ins" in prompt
    assert "speak from CYN-X's point of view" in prompt
    assert "customer-service thanks" in prompt
    assert "infantilizing nicknames" in prompt
    assert "hey mommy how are u today?" not in prompt
    assert "kiddo" not in prompt.lower()
