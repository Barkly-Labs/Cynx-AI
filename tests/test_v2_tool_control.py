import os
from types import SimpleNamespace

from ai.chat_engine import ChatEngine


class FakeRouter:
    def __init__(self):
        self.tools = {"web_search": object(), "calculator": object()}
        self.calls = []

    def as_ollama_tools(self):
        return [
            {"type": "function", "function": {"name": "web_search", "description": "Search current web information.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
            {"type": "function", "function": {"name": "calculator", "description": "Calculate arithmetic.", "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}}},
        ]

    def describe_tools(self):
        return [
            {"name": "web_search", "description": "Search current web information."},
            {"name": "calculator", "description": "Calculate arithmetic."},
        ]

    def detect(self, text):
        lower = text.lower()
        if "search the web" in lower or "latest python 3.14 release notes" in lower:
            return {"tool": "web_search", "query": text}
        return None

    def call_tool(self, name, args):
        self.calls.append((name, args))
        return SimpleNamespace(
            success=True, output="Python 3.14 release notes result", metadata=None
        )


class FakePromptBuilder:
    def build_prompt(self, **kwargs):
        return "CYN-X test prompt\n" + kwargs.get("tools_spec", "")


class HallucinatingOllama:
    def __init__(self):
        self.calls = []

    def chat(self, messages, tools=None, **kwargs):
        self.calls.append({"messages": messages, "tools": tools})
        if len(self.calls) == 1:
            return {"message": {"role": "assistant", "content": "The user asked... I should have responded directly.", "tool_calls": [{"function": {"name": "web_search", "arguments": {"query": "CYN-X"}}}]}}
        return {"message": {"role": "assistant", "content": "hey sweetie :3 what's up?"}}


class SearchOllama:
    def __init__(self):
        self.calls = []

    def chat(self, messages, tools=None, **kwargs):
        self.calls.append({"messages": messages, "tools": tools})
        if len(self.calls) == 1:
            return {"message": {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "web_search", "arguments": {"query": "latest Python 3.14 release notes"}}}]}}
        return {"message": {"role": "assistant", "content": "Here are the current Python 3.14 release notes."}}


def make_engine(router=None, ollama=None):
    return ChatEngine(
        ollama_client=ollama or HallucinatingOllama(),
        prompt_builder=FakePromptBuilder(),
        memory_store=None,
        tool_router=router or FakeRouter(),
        mode_manager=None,
        memory_manager=None,
        memory_extractor=None,
        context_manager=None,
    )


def names(specs):
    return [(s.get("function") or {}).get("name") for s in (specs or [])]


def test_v2_ordinary_conversation_exposes_zero_tools(monkeypatch):
    monkeypatch.setenv("CYNX_PERSONALITY_ARCH", "v2")
    engine = make_engine()
    for text in ("hey mommy :3", "how are you mommy?", "what is a Python dictionary?", "why does this Python function return None?"):
        assert engine._ollama_tools(text) == []


def test_v2_explicit_search_exposes_only_web_search(monkeypatch):
    monkeypatch.setenv("CYNX_PERSONALITY_ARCH", "v2")
    engine = make_engine()
    assert names(engine._ollama_tools("search the web for the latest Python 3.14 release notes")) == ["web_search"]


def test_v2_search_followup_does_not_reoffer_search(monkeypatch):
    monkeypatch.setenv("CYNX_PERSONALITY_ARCH", "v2")
    engine = make_engine()
    assert engine._ollama_tools("okay, explain that") == []


def test_unoffered_or_nonexistent_tool_is_rejected():
    calls = [{"function": {"name": "web_search", "arguments": {"query": "CYN-X"}}}, {"function": {"name": "does_not_exist", "arguments": {}}}]
    valid, rejected = ChatEngine._validate_tool_calls(calls, [])
    assert valid == []
    assert {name for name, _ in rejected} == {"web_search", "does_not_exist"}


def test_invalid_arguments_are_rejected():
    specs = FakeRouter().as_ollama_tools()[:1]
    calls = [{"function": {"name": "web_search", "arguments": "{not-json"}}, {"function": {"name": "web_search", "arguments": {}}}]
    valid, rejected = ChatEngine._validate_tool_calls(calls, specs)
    assert valid == []
    assert len(rejected) == 2


def test_ordinary_text_mentioning_search_is_not_a_tool_call():
    specs = []
    valid, rejected = ChatEngine._validate_tool_calls([], specs)
    assert valid == []
    assert rejected == []


def test_rejected_hallucinated_tool_regenerates_clean_response(monkeypatch):
    monkeypatch.setenv("CYNX_PERSONALITY_ARCH", "v2")
    router = FakeRouter()
    ollama = HallucinatingOllama()
    engine = make_engine(router, ollama)
    result = engine.handle_user_message("piper", "hey mommy :3")
    assert result == "hey sweetie :3 what's up?"
    assert router.calls == []
    assert len(ollama.calls) == 2
    assert ollama.calls[0]["tools"] is None
    assert ollama.calls[1]["tools"] is None
    assert "The user asked" not in result
    assert "I should have" not in result


def test_explicit_search_executes_exactly_one_authorized_search(monkeypatch):
    monkeypatch.setenv("CYNX_PERSONALITY_ARCH", "v2")
    router = FakeRouter()
    ollama = SearchOllama()
    engine = make_engine(router, ollama)
    result = engine.handle_user_message(
        "piper", "search the web for the latest Python 3.14 release notes"
    )
    assert result == "Here are the current Python 3.14 release notes."
    assert router.calls == [(
        "web_search", {"query": "latest Python 3.14 release notes"}
    )]
    assert names(ollama.calls[0]["tools"]) == ["web_search"]
    assert ollama.calls[1]["tools"] is None


def test_v1_tool_exposure_is_preserved(monkeypatch):
    monkeypatch.setenv("CYNX_PERSONALITY_ARCH", "v1")
    engine = make_engine()
    assert set(names(engine._ollama_tools("hey mommy :3"))) == {"web_search", "calculator"}

def test_v2_explicit_calculation_preserves_calculator(monkeypatch):
    monkeypatch.setenv("CYNX_PERSONALITY_ARCH", "v2")
    engine = make_engine()
    assert names(engine._ollama_tools("calculate 144 / 12")) == ["calculator"]
