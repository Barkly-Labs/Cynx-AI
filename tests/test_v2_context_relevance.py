from ai.chat_engine import ChatEngine


class RecordingPromptBuilder:
    def __init__(self):
        self.calls = []

    def build_prompt(self, **kwargs):
        self.calls.append(kwargs)
        return "test system prompt"


class DirtyContextManager:
    def __init__(self):
        self.calls = []

    def build_context(self, user_id, user_message):
        self.calls.append((user_id, user_message))
        return {
            "memory": "old dad jokes; diaper talk; wolf daddies; unrelated project",
            "knowledge": "unrelated retrieved document",
        }


class NoToolRouter:
    tools = {}

    def as_ollama_tools(self):
        return []

    def describe_tools(self):
        return []

    def detect(self, text):
        return None


class CleanOllama:
    def __init__(self):
        self.calls = []

    def chat(self, messages, tools=None, **kwargs):
        self.calls.append({"messages": messages, "tools": tools})
        return {"message": {"role": "assistant", "content": "Heeey :3 *poke*"}}


def make_engine():
    prompt = RecordingPromptBuilder()
    context = DirtyContextManager()
    ollama = CleanOllama()
    engine = ChatEngine(
        ollama_client=ollama,
        prompt_builder=prompt,
        memory_store=None,
        tool_router=NoToolRouter(),
        mode_manager=None,
        memory_manager=None,
        memory_extractor=None,
        context_manager=context,
    )
    return engine, prompt, context, ollama


def seed_unrelated_history(engine):
    engine.conversation_history["piper"] = [
        {"role": "user", "content": "tell me another dad joke"},
        {"role": "assistant", "content": "old unrelated joke"},
        {"role": "user", "content": "let's discuss an unrelated project"},
        {"role": "assistant", "content": "old unrelated project details"},
    ]


def test_v2_simple_greeting_omits_unrelated_retrieved_context_and_history(monkeypatch):
    monkeypatch.setenv("CYNX_PERSONALITY_ARCH", "v2")
    engine, prompt, context, ollama = make_engine()
    seed_unrelated_history(engine)

    result = engine.handle_user_message("piper", "Heey :3")

    assert result == "Heeey :3 *poke*"
    assert context.calls == [("piper", "Heey :3")]
    assert prompt.calls[0]["memory_summary"] == ""
    assert prompt.calls[0]["knowledge_context"] == ""
    sent = ollama.calls[0]["messages"]
    assert [m["role"] for m in sent] == ["system", "user"]
    assert "dad joke" not in str(sent).lower()
    assert "unrelated project" not in str(sent).lower()


def test_v2_affectionate_greeting_uses_same_relevance_gate(monkeypatch):
    monkeypatch.setenv("CYNX_PERSONALITY_ARCH", "v2")
    engine, prompt, _, ollama = make_engine()
    seed_unrelated_history(engine)

    engine.handle_user_message("piper", "Hey mommy :3")

    assert prompt.calls[0]["memory_summary"] == ""
    assert [m["role"] for m in ollama.calls[0]["messages"]] == ["system", "user"]


def test_v2_explicit_memory_recall_keeps_retrieved_context_and_history(monkeypatch):
    monkeypatch.setenv("CYNX_PERSONALITY_ARCH", "v2")
    for text in (
        "Remember that Python bug we were fixing?",
        "What were we working on yesterday?",
    ):
        engine, prompt, _, ollama = make_engine()
        engine.conversation_history["piper"] = [
            {"role": "user", "content": "the parser bug is in parse_config"},
            {"role": "assistant", "content": "we traced parse_config"},
        ]
        engine.handle_user_message("piper", text)
        assert "old dad jokes" in prompt.calls[0]["memory_summary"]
        assert "unrelated retrieved document" in prompt.calls[0]["knowledge_context"]
        assert len(ollama.calls[0]["messages"]) == 4


def test_v2_technical_turn_keeps_context_available(monkeypatch):
    monkeypatch.setenv("CYNX_PERSONALITY_ARCH", "v2")
    engine, prompt, _, ollama = make_engine()
    engine.conversation_history["piper"] = [
        {"role": "user", "content": "def parse_config(): ..."},
        {"role": "assistant", "content": "the function falls through"},
    ]

    engine.handle_user_message("piper", "Help me debug this function")

    assert prompt.calls[0]["memory_summary"]
    assert prompt.calls[0]["knowledge_context"]
    assert any("parse_config" in m.get("content", "") for m in ollama.calls[0]["messages"])


def test_v1_context_behavior_is_unchanged(monkeypatch):
    monkeypatch.setenv("CYNX_PERSONALITY_ARCH", "v1")
    engine, prompt, _, ollama = make_engine()
    seed_unrelated_history(engine)

    engine.handle_user_message("piper", "Heey :3")

    assert "old dad jokes" in prompt.calls[0]["memory_summary"]
    assert len(ollama.calls[0]["messages"]) > 2
