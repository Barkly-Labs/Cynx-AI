import json

import pytest
import requests

from ai.ollama_client import OllamaClient


PEG_ERROR = (
    '{"error":"llama-server chat error: map[code:500 message:'
    'The model produced output that does not match the expected peg-native format '
    'type:server_error]"}'
)


class FakeResponse:
    def __init__(self, status_code, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {})

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the internet for current information.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate an arithmetic expression safely.",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        },
    },
]


@pytest.mark.parametrize(
    "user_text",
    [
        "What is Python?",
        "Find me information about Barkly Labs.",
        "Find me unusual sex positions for me and my partner.",
        "I kinda want Daddy to do the Cowboy position.",
        "What is 123 * 456?",
    ],
)
def test_peg_native_tool_failure_retries_same_turn_without_tools(monkeypatch, user_text):
    calls = []
    responses = [
        FakeResponse(500, text=PEG_ERROR),
        FakeResponse(
            200,
            payload={
                "message": {
                    "role": "assistant",
                    "content": "Recovered normal assistant response.",
                    "tool_calls": [],
                }
            },
        ),
    ]

    def fake_post(url, json, stream, timeout):
        calls.append(json)
        return responses.pop(0)

    monkeypatch.setattr("ai.ollama_client.requests.post", fake_post)

    client = OllamaClient(model="cyn-x:latest")
    result = client.chat(
        messages=[{"role": "user", "content": user_text}],
        tools=TOOLS,
    )

    assert result["message"]["content"] == "Recovered normal assistant response."
    assert len(calls) == 2
    assert calls[0]["tools"] == TOOLS
    assert "tools" not in calls[1]
    assert calls[1]["messages"] == calls[0]["messages"]
    assert calls[1]["options"] == calls[0]["options"]


def test_non_peg_http_error_is_not_swallowed(monkeypatch):
    def fake_post(url, json, stream, timeout):
        return FakeResponse(500, text='{"error":"different server failure"}')

    monkeypatch.setattr("ai.ollama_client.requests.post", fake_post)
    client = OllamaClient(model="cyn-x:latest")

    with pytest.raises(requests.HTTPError):
        client.chat(messages=[{"role": "user", "content": "hello"}], tools=TOOLS)


def test_peg_error_without_tools_is_not_recursively_hidden(monkeypatch):
    calls = []

    def fake_post(url, json, stream, timeout):
        calls.append(json)
        return FakeResponse(500, text=PEG_ERROR)

    monkeypatch.setattr("ai.ollama_client.requests.post", fake_post)
    client = OllamaClient(model="cyn-x:latest")

    with pytest.raises(requests.HTTPError):
        client.chat(messages=[{"role": "user", "content": "hello"}], tools=None)

    assert len(calls) == 1


def test_peg_fallback_current_user_appears_exactly_once(monkeypatch):
    calls = []
    current = "hey mommy how are u today"
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "older turn"},
        {"role": "assistant", "content": "older response"},
        {"role": "user", "content": current},
    ]
    responses = [
        FakeResponse(500, text=PEG_ERROR),
        FakeResponse(
            200,
            payload={
                "message": {
                    "role": "assistant",
                    "content": "Recovered.",
                    "tool_calls": [],
                }
            },
        ),
    ]

    def fake_post(url, json, stream, timeout):
        calls.append(json)
        return responses.pop(0)

    monkeypatch.setattr("ai.ollama_client.requests.post", fake_post)
    result = OllamaClient(model="cyn-x:latest").chat(messages=messages, tools=TOOLS)

    assert result["message"]["content"] == "Recovered."
    assert len(calls) == 2
    assert calls[1]["messages"] == messages
    assert calls[1]["messages"] == calls[0]["messages"]
    assert sum(
        1 for message in calls[1]["messages"]
        if message.get("role") == "user" and message.get("content") == current
    ) == 1


def test_peg_fallback_does_not_inject_failure_as_assistant_message(monkeypatch):
    calls = []
    messages = [{"role": "user", "content": "hey mommy how are u today"}]
    responses = [
        FakeResponse(500, text=PEG_ERROR),
        FakeResponse(
            200,
            payload={
                "message": {
                    "role": "assistant",
                    "content": "Recovered.",
                    "tool_calls": [],
                }
            },
        ),
    ]

    def fake_post(url, json, stream, timeout):
        calls.append(json)
        return responses.pop(0)

    monkeypatch.setattr("ai.ollama_client.requests.post", fake_post)
    OllamaClient(model="cyn-x:latest").chat(messages=messages, tools=TOOLS)

    assert calls[1]["messages"] == messages
    assert all("peg-native" not in str(message) for message in calls[1]["messages"])
    assert all("server_error" not in str(message) for message in calls[1]["messages"])


def test_streaming_peg_error_does_not_use_nonstreaming_fallback(monkeypatch):
    calls = []

    def fake_post(url, json, stream, timeout):
        calls.append((json, stream))
        return FakeResponse(500, text=PEG_ERROR)

    monkeypatch.setattr("ai.ollama_client.requests.post", fake_post)
    client = OllamaClient(model="cyn-x:latest")

    with pytest.raises(requests.HTTPError):
        list(client.chat(
            messages=[{"role": "user", "content": "hello"}],
            tools=TOOLS,
            stream=True,
        ))

    assert len(calls) == 1
