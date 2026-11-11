from ai.chat_engine import ChatEngine


class _PromptBuilder:
    personality_arch = "v2"
    last_prompt_components = [{"source": "safety", "text": "Use the active safety guidance."}]

    def get_prompt_layers(self):
        return {"core": True, "personality": True, "safety": True}

    def build_prompt(self, **kwargs):
        return "Captured system instruction"


class _Context:
    def build_context(self, user_id, text):
        return {"memory": "one relevant memory", "knowledge": "one relevant fact"}


class _Tools:
    tools = {}

    def describe_tools(self):
        return []

    def detect(self, text):
        return None

    def as_ollama_tools(self):
        return []


class _Ollama:
    model = "local-test-model"
    supports_streaming_observer = False

    def chat(self, messages, tools=None, **kwargs):
        return {"message": {"role": "assistant", "content": "Actual captured answer."}, "eval_count": 5}


def test_chat_engine_trace_captures_actual_context_routing_and_final_response():
    events = []
    engine = ChatEngine(
        ollama_client=_Ollama(), prompt_builder=_PromptBuilder(), memory_store=None,
        tool_router=_Tools(), mode_manager=None, context_manager=_Context(),
    )

    result = engine.handle_user_message("dx-test-user", "A real benchmark question", trace_callback=events.append)

    assert result == "Actual captured answer."
    stages = [event["stage"] for event in events]
    assert "context_retrieved" in stages
    assert "instructions_assembled" in stages
    assert "model_request_constructed" in stages
    assert "routing_decision" in stages
    assert "response_transformation" in stages
    request = next(event for event in events if event["stage"] == "model_request_constructed")
    assert request["messages"][-1] == {"role": "user", "content": "A real benchmark question"}
    final = next(event for event in events if event["stage"] == "response_transformation")
    assert final["original_model_output"] == final["final_user_facing_response"] == result


def test_chat_engine_keeps_browser_conversation_histories_separate():
    engine = ChatEngine(
        ollama_client=_Ollama(), prompt_builder=_PromptBuilder(), memory_store=None,
        tool_router=_Tools(), mode_manager=None, context_manager=None,
    )
    first_key = "web_user:conversation-one"
    second_key = "web_user:conversation-two"

    engine.handle_user_message("web_user", "First session message", conversation_key=first_key)
    second_messages = []
    engine.ollama.chat = lambda messages, tools=None, **kwargs: (
        second_messages.extend(messages) or {"message": {"content": "Second session answer"}}
    )
    engine.handle_user_message("web_user", "Separate session message", conversation_key=second_key)

    assert all("First session message" not in message.get("content", "") for message in second_messages)
    assert any("First session message" in message.get("content", "") for message in engine.conversation_history[first_key])
