import json
import sqlite3
from types import SimpleNamespace

import pytest

from ai.chat_engine import ChatEngine, IncompleteModelResponse
from ai.memory_system.manager import MemoryManager
from ai.ollama_client import OllamaClient
from tools.base import BaseTool, ToolResult
from tools.tool_router import ToolRouter
from tools.web_search import OutputMode, ResultRanker, build_intent, build_search_query


class SearchTool(BaseTool):
    name = "web_search"
    description = "Search current public web information."

    def __init__(self, success=True):
        self.calls = []
        self.success = success

    def call(self, args):
        self.calls.append(args)
        if self.success:
            return ToolResult(True, "Listing: Model A; price $40; 4.7 stars", {
                "success": True,
                "results": [{"name": "Model A", "price": "$40", "rating": 4.7,
                             "url": "https://example.test/product-a"}],
            })
        return ToolResult(False, "Search provider unavailable", {"success": False, "results": []})


class Prompt:
    def build_prompt(self, **kwargs):
        self.last = kwargs
        return "CYN-X test system prompt\n" + kwargs.get("tools_spec", "")


class SearchSummaryModel:
    model = "fixture-model"

    def __init__(self):
        self.calls = []

    def chat(self, messages, tools=None, **kwargs):
        self.calls.append({"messages": messages, "tools": tools})
        tool_message = next((m for m in messages if m.get("role") == "tool"), None)
        payload = json.loads(tool_message["content"])
        if payload["result"].get("success"):
            return {"message": {"role": "assistant", "content": "Model A is the only listing I could verify: $40 and 4.7 stars. Here is the source: https://example.test/product-a"}}
        return {"message": {"role": "assistant", "content": "I couldn't verify any products because the search service is unavailable."}}


class NoContext:
    def build_context(self, _user, _text):
        return {"memory": "", "knowledge": ""}


class NoMode:
    def allowed_tools_for(self, _mode):
        return set()


def make_search_engine(tool=None, model=None):
    router = ToolRouter()
    search = tool or SearchTool()
    router.register_tool(search)
    prompt = Prompt()
    model = model or SearchSummaryModel()
    engine = ChatEngine(model, prompt, None, router, NoMode(), context_manager=NoContext())
    return engine, router, search, prompt, model


def test_explicit_adult_retail_request_routes_through_actual_search_tool(monkeypatch):
    monkeypatch.setenv("CYNX_PERSONALITY_ARCH", "v2")
    engine, _, search, _, model = make_search_engine()

    answer = engine.handle_user_message(
        "user-1", "mommy find me the best dildos on amazon im an adult"
    )

    assert search.calls == [{"query": "best dildos on amazon"}]
    assert "Model A" in answer
    assert len(model.calls) == 1  # Search happened in Python before the model's summary.
    assert model.calls[0]["tools"] is None
    assert "commerce/product research" in next(
        m["content"] for m in model.calls[0]["messages"] if m.get("role") == "tool"
    )
    assert engine.conversation_history["user-1"][-1]["content"] == answer


def test_web_search_classifies_adult_product_commerce_and_ranks_product_evidence():
    intent = build_intent("best dildos on amazon")
    query = build_search_query(intent)
    assert intent.is_adult_search is True
    assert intent.output_type == OutputMode.LIST
    assert "site:amazon.com" in query
    assert "adult product reviews" in query
    ranker = ResultRanker(intent)
    assert ranker.rank("Amazon adult product listing: silicone dildo reviews", "", "https://amazon.com/item") > 0


@pytest.mark.parametrize("query", [
    "Find me the best ergonomic keyboard on Amazon",
    "Find me a wireless keyboard",
    "Recommend a well-reviewed desk lamp from Walmart",
    "Search the web for the latest Python release notes",
])
def test_product_and_explicit_research_intents_are_detected(query):
    router = ToolRouter()
    detected = router.detect(query)
    assert detected["tool"] == "web_search"
    assert detected["query"]


@pytest.mark.parametrize("query", [
    "Find an adult sex toy for a 15-year-old on Amazon",
    "Search for a dildo to use without consent",
])
def test_restricted_adult_product_search_is_not_routed(query):
    router = ToolRouter()
    assert router.is_restricted_adult_product_search(query)
    assert router.detect(query) is None


def test_ordinary_adult_product_education_does_not_trigger_retail_search():
    router = ToolRouter()
    query = "What general safety features should an adult look for in a sex toy?"
    assert router.detect(query) is None
    assert not router.is_restricted_adult_product_search(query)


def test_restricted_product_request_reaches_model_without_search_execution(monkeypatch):
    monkeypatch.setenv("CYNX_PERSONALITY_ARCH", "v2")

    class BoundaryModel:
        model = "fixture-model"

        def __init__(self):
            self.tools = []

        def chat(self, messages, tools=None, **kwargs):
            self.tools.append(tools)
            return {"message": {"role": "assistant", "content": "I can't help find sexual products for a minor."}}

    model = BoundaryModel()
    engine, _, search, _, _ = make_search_engine(model=model)
    response = engine.handle_user_message(
        "user-1", "Find an adult sex toy for a 15-year-old on Amazon"
    )
    assert response.startswith("I can't help")
    assert search.calls == []
    assert model.tools == [None]


def test_failed_search_does_not_create_product_recommendations(monkeypatch):
    monkeypatch.setenv("CYNX_PERSONALITY_ARCH", "v2")
    engine, _, search, _, _ = make_search_engine(tool=SearchTool(success=False))

    answer = engine.handle_user_message("user-1", "Find me the best adult toy online")

    assert search.calls
    assert "couldn't verify" in answer
    assert engine.conversation_history["user-1"][-1]["content"] == answer


def test_sensitive_memories_without_real_term_overlap_are_not_retrieved():
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE memories (
        id INTEGER PRIMARY KEY, user_id TEXT, kind TEXT, content TEXT,
        importance INTEGER, tags TEXT, metadata TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    manager = MemoryManager(conn)
    manager.remember("user-1", "Sensitive relationship and health details", importance=10)
    manager.remember("user-1", "Python parser bug in parse_config", importance=3)

    assert manager.search("user-1", "mommy find me the best dildos on amazon im an adult") == []
    assert manager.search("user-1", "Help debug the Python parser")


def test_standalone_retail_search_omits_sensitive_memory_and_old_chat(monkeypatch):
    monkeypatch.setenv("CYNX_PERSONALITY_ARCH", "v2")

    class SensitiveContext:
        def build_context(self, _user, _text):
            return {
                "memory": "Sensitive intimate relationship and medical history",
                "knowledge": "Unrelated private background document",
            }

    engine, _, _, prompt, model = make_search_engine()
    engine.context_manager = SensitiveContext()
    engine.conversation_history["user-1"] = [
        {"role": "user", "content": "Earlier sensitive personal details"},
        {"role": "assistant", "content": "A private support conversation"},
    ]
    engine.handle_user_message("user-1", "mommy find me the best dildos on amazon im an adult")

    assert prompt.last["memory_summary"] == ""
    assert prompt.last["knowledge_context"] == ""
    request_messages = model.calls[0]["messages"]
    assert not any("private" in message.get("content", "").lower() for message in request_messages)


def test_incomplete_nonstream_response_is_not_persisted_and_retry_is_clean(monkeypatch):
    monkeypatch.setenv("CYNX_PERSONALITY_ARCH", "v2")

    class SequencedModel:
        model = "fixture-model"

        def __init__(self):
            self.calls = []
            self.responses = [
                {"message": {"role": "assistant", "content": "I"}, "done_reason": "stop"},
                {"message": {"role": "assistant", "content": "Here is a complete answer."}, "done_reason": "stop"},
            ]

        def chat(self, messages, tools=None, **kwargs):
            self.calls.append(messages)
            return self.responses.pop(0)

    model = SequencedModel()
    engine = ChatEngine(model, Prompt(), None, ToolRouter(), NoMode(), context_manager=NoContext())
    with pytest.raises(IncompleteModelResponse):
        engine.handle_user_message("user-1", "Explain this clearly")

    assert engine.conversation_history["user-1"] == []
    result = engine.handle_user_message("user-1", "Explain this clearly")
    assert result == "Here is a complete answer."
    assert not any(
        message.get("role") == "assistant" and message.get("content") == "I"
        for message in model.calls[1]
    )
    assert model.calls[1][-1] == {"role": "user", "content": "Explain this clearly"}


class StreamingResponse:
    status_code = 200
    text = ""

    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    def iter_lines(self):
        return iter(self.chunks)

    def raise_for_status(self):
        return None

    def close(self):
        self.closed = True


@pytest.mark.parametrize("chunks", [
    [b'{"message":{"content":"I"},"done":false}'],
    [b'{"message":{"content":"still incomplete"},"done":true,"done_reason":"length"}'],
    [b'{"message":{"content":""},"done":true,"done_reason":"stop"}'],
])
def test_ollama_stream_rejects_missing_terminal_or_incomplete_output(monkeypatch, chunks):
    response = StreamingResponse(chunks)
    monkeypatch.setattr("ai.ollama_client.requests.post", lambda *args, **kwargs: response)
    with pytest.raises(RuntimeError, match="stream|incomplete|no completed"):
        OllamaClient().chat([{"role": "user", "content": "hello"}], stream=True)
    assert response.closed
