import logging
import json

import pytest

from interfaces.web.pipeline import PipelineEventStore
from ai.chat_engine import ChatEngine, ChatRequestCancelled
from ai.ollama_client import OllamaClient
from tools.base import ToolResult


class FakePromptBuilder:
    def build_prompt(self, **kwargs):
        return "system prompt"


class FakeModeManager:
    def allowed_tools_for(self, mode):
        return {"web_search", "calculator"}


class FakeToolRouter:
    def __init__(self):
        self.tools = {
            "web_search": object(),
            "calculator": object(),
        }

    def describe_tools(self):
        return [
            {"name": "web_search", "description": "Search the web."},
            {"name": "calculator", "description": "Calculate arithmetic."},
        ]

    def as_ollama_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "calculator",
                    "description": "Calculate arithmetic.",
                    "parameters": {
                        "type": "object",
                        "properties": {"expression": {"type": "string"}},
                        "required": ["expression"],
                    },
                },
            },
        ]

    def detect(self, text):
        return None

    def call_tool(self, name, args):
        return ToolResult(True, "Current result")


class FakeOllama:
    supports_streaming_observer = True

    def __init__(self, responses):
        self.responses = iter(responses)

    def chat(self, **kwargs):
        response = next(self.responses)
        content = (response.get("message") or {}).get("content")
        if content and kwargs.get("on_content"):
            kwargs["on_content"]()
        return response


def _engine(responses, router=None):
    return ChatEngine(
        FakeOllama(responses),
        FakePromptBuilder(),
        None,
        router or FakeToolRouter(),
        FakeModeManager(),
    )


def test_pipeline_store_keeps_request_events_isolated_and_ordered():
    store = PipelineEventStore()
    store.create("request-a")
    store.create("request-b")
    store.publish("request-a", "stage", stage="understanding", status="active")
    store.publish("request-a", "request_completed")
    store.publish("request-b", "request_failed", message="Request failed.")

    a = store.read("request-a")
    b = store.read("request-b")

    assert [event["id"] for event in a["events"]] == [1, 2, 3]
    assert a["done"] is True
    assert b["done"] is True
    assert [event["type"] for event in b["events"]] == ["stage", "request_failed"]


def test_pipeline_store_tracks_cooperative_cancellation():
    store = PipelineEventStore()
    store.create("request-cancel")

    assert store.request_cancel("request-cancel") is True
    assert store.is_cancelled("request-cancel") is True
    assert store.read("request-cancel")["done"] is False

    store.publish(
        "request-cancel",
        "request_cancelled",
        message="Request cancelled.",
    )
    assert store.read("request-cancel")["done"] is True
    assert store.request_cancel("request-cancel") is False


def test_chat_engine_emits_direct_answer_lifecycle_without_tool_details():
    engine = _engine([{"message": {"content": "Hello."}}])
    events = []

    response = engine.handle_user_message(
        user_id="test",
        text="hello",
        request_id="request-direct",
        pipeline_callback=events.append,
    )

    assert response == "Hello."
    assert ("understanding", "active") in [
        (event.get("stage"), event.get("status"))
        for event in events
        if event["type"] == "stage"
    ]
    assert any(
        event["type"] == "decision"
        and event["action"] == "answer_directly"
        and event["tools"] == []
        for event in events
    )
    assert any(
        event["type"] == "stage"
        and event["stage"] == "generating_response"
        and event["status"] == "completed"
        for event in events
    )


def test_chat_engine_stops_at_a_cooperative_cancellation_boundary():
    engine = _engine([{"message": {"content": "Unused."}}])

    with pytest.raises(ChatRequestCancelled):
        engine.handle_user_message(
            user_id="test",
            text="hello",
            cancellation_check=lambda: True,
        )


def test_chat_engine_marks_failed_tool_execution_without_exposing_arguments():
    class FailedRouter:
        def call_tool(self, name, args):
            return ToolResult(False, "private tool output")

    engine = object.__new__(ChatEngine)
    engine.logger = logging.getLogger("test.pipeline")
    engine.tool_router = FailedRouter()
    events = []

    result = engine._call_tool_with_pipeline(
        "web_search",
        {"query": "sensitive query"},
        events.append,
        invocation_id="call-failed",
    )

    assert result.success is False
    assert [event["status"] for event in events if event["type"] == "tool"] == [
        "started",
        "failed",
    ]
    assert all("sensitive query" not in str(event) for event in events)
    assert all("private tool output" not in str(event) for event in events)


def test_chat_engine_reports_selected_tool_execution_and_final_generation():
    router = FakeToolRouter()
    engine = _engine([
        {
            "message": {
                "content": "",
                "tool_calls": [{
                    "id": "call-search-1",
                    "function": {
                        "name": "web_search",
                        "arguments": {"query": "current weather"},
                    },
                }, {
                    "id": "call-calculator-1",
                    "function": {
                        "name": "calculator",
                        "arguments": {"expression": "2 + 2"},
                    },
                }],
            }
        },
        {"message": {"content": "Here is the result."}},
    ], router=router)
    events = []

    response = engine.handle_user_message(
        user_id="test",
        text="search the web for current weather and calculate 2 + 2",
        request_id="request-tool",
        pipeline_callback=events.append,
    )

    assert response == "Here is the result."
    assert any(
        event["type"] == "decision"
        and event["action"] == "use_tools"
        and event["tools"] == ["web_search", "calculator"]
        for event in events
    )
    assert [
        event["status"] for event in events
        if event["type"] == "tool"
    ] == ["started", "completed", "started", "completed"]
    tool_events = [event for event in events if event["type"] == "tool"]
    assert [event["name"] for event in tool_events] == [
        "web_search",
        "web_search",
        "calculator",
        "calculator",
    ]
    assert all("arguments" not in event for event in events)
    assert any(
        event["type"] == "stage"
        and event["stage"] == "generating_response"
        and event["status"] == "active"
        for event in events
    )


def test_ollama_stream_observer_reports_output_and_reassembles_tool_calls(monkeypatch):
    chunks = [
        {"message": {"content": "Answer"}},
        {"message": {"tool_calls": [{
            "index": 0,
            "id": "call-1",
            "function": {"name": "web_search", "arguments": "{\"query\":"},
        }]}},
        {"message": {"tool_calls": [{
            "index": 0,
            "function": {"arguments": "\"weather\"}"},
        }]}},
        {"done": True, "model": "cyn-x:latest", "prompt_eval_count": 17,
         "prompt_eval_duration": 2_000_000_000, "eval_count": 3,
         "eval_duration": 750_000_000, "total_duration": 3_000_000_000},
    ]

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def iter_lines(self):
            return (json.dumps(chunk).encode("utf-8") for chunk in chunks)

    monkeypatch.setattr(
        "ai.ollama_client.requests.post",
        lambda *args, **kwargs: Response(),
    )
    observed = []
    result = OllamaClient().chat(
        messages=[],
        tools=[{"type": "function"}],
        stream=True,
        on_content=lambda: observed.append("content"),
    )

    assert result["message"]["content"] == "Answer"
    assert observed == ["content"]
    call = result["message"]["tool_calls"][0]
    assert call["id"] == "call-1"
    assert call["function"]["name"] == "web_search"
    assert json.loads(call["function"]["arguments"]) == {"query": "weather"}
    assert result["prompt_eval_count"] == 17
    assert result["eval_count"] == 3
    assert result["eval_duration"] == 750_000_000
    assert result["prompt_eval_duration"] == 2_000_000_000
