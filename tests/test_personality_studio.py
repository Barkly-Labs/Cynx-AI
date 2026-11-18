import json

import pytest
from fastapi.testclient import TestClient

from ai.personality_studio import PersonalityStudioStore, STARTER_TRAITS, TRAITS, validate_traits


def test_legacy_config_is_reported_without_overwriting_new_traits(tmp_path):
    store = PersonalityStudioStore(tmp_path / "studio.db")
    active = store.active()
    assert not active["activated"]
    assert active["traits"]["warmth"] == 80
    assert active["traits"]["playfulness"] == 90
    assert active["traits"]["mischievousness"] is None
    assert store.presets()[0]["traits"] == STARTER_TRAITS


def test_activation_is_atomic_versioned_and_rejects_stale_sessions(tmp_path):
    store = PersonalityStudioStore(tmp_path / "studio.db")
    before = store.active()
    applied = store.activate(STARTER_TRAITS, before["version"], "owner example")
    assert applied["activated"] is True
    assert applied["version"] == before["version"] + 1
    assert applied["traits"] == STARTER_TRAITS
    with pytest.raises(RuntimeError, match="changed in another session"):
        store.activate({**STARTER_TRAITS, "warmth": 12}, before["version"], "stale")
    assert store.active()["config_id"] == applied["config_id"]
    assert store.history()[0]["config_id"] == applied["config_id"]


def test_rollback_can_restore_the_unmodified_legacy_personality(tmp_path):
    store = PersonalityStudioStore(tmp_path / "studio.db")
    legacy = store.active()
    store.activate(STARTER_TRAITS, legacy["version"], "new personality")
    restored = store.restore(legacy["config_id"], store.active()["version"])
    assert restored["activated"] is False
    assert restored["source"] == "legacy"
    assert restored["traits"] == legacy["traits"]
    assert restored["version"] == 3


@pytest.mark.parametrize("architecture", ["v1", "v2"])
def test_activated_configuration_reaches_both_production_prompt_builders(monkeypatch, tmp_path, architecture):
    from ai import personality
    from ai.prompt_builder import PromptBuilder

    store = PersonalityStudioStore(tmp_path / f"{architecture}.db")
    monkeypatch.setattr(personality, "_studio_store", store)
    store.activate(STARTER_TRAITS, store.active()["version"], "verified")
    prompt = PromptBuilder(personality_arch=architecture).build_prompt("Hello")
    assert "Warmth: 90% tendency" in prompt
    assert "Affection: 95% tendency" in prompt
    assert "These settings never override safety" in prompt


def test_import_validation_rejects_security_or_unrelated_settings():
    with pytest.raises(ValueError):
        validate_traits({**STARTER_TRAITS, "tool_permissions": ["filesystem"]})
    with pytest.raises(ValueError):
        validate_traits({**STARTER_TRAITS, "warmth": 101})


def test_preset_saves_and_deletes_without_changing_active(tmp_path):
    store = PersonalityStudioStore(tmp_path / "studio.db")
    active = store.active()
    saved = store.save_preset("Test draft", STARTER_TRAITS)
    assert saved["traits"] == STARTER_TRAITS
    assert store.active() == active
    store.delete_preset(saved["preset_id"])
    assert all(item["preset_id"] != saved["preset_id"] for item in store.presets())


def test_http_activation_requires_version_and_reports_concurrent_conflict(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from interfaces.web import app as web

    store = PersonalityStudioStore(tmp_path / "studio.db")
    monkeypatch.setattr(web, "personality_studio", store)
    client = TestClient(web.app)
    version = store.active()["version"]
    applied = client.post("/api/dx/personality/activate", json={"traits": STARTER_TRAITS, "expected_version": version})
    assert applied.status_code == 200
    stale = client.post("/api/dx/personality/activate", json={"traits": STARTER_TRAITS, "expected_version": version})
    assert stale.status_code == 409
    assert store.active()["version"] == version + 1


def test_personality_preview_isolated_from_active_and_real_conversation(monkeypatch, tmp_path):
    from interfaces.web import app as web
    from ai import personality

    store = PersonalityStudioStore(tmp_path / "studio.db")
    monkeypatch.setattr(web, "personality_studio", store)
    monkeypatch.setattr(personality, "_studio_store", store)
    captured = {}

    def fake_chat(**kwargs):
        captured.update(kwargs)
        return {"model": "fixture:latest", "message": {"content": "That sounds rough. Want company or a distraction?"},
                "prompt_eval_count": 25, "eval_count": 12, "done": True}

    monkeypatch.setattr(web.ollama_client, "chat", fake_chat)
    client = TestClient(web.app)
    before = store.active()
    original_history = dict(web.chat_engine.conversation_history)
    response = client.post("/api/dx/personality/preview", json={"prompt": "I had a difficult day.", "traits": STARTER_TRAITS})
    assert response.status_code == 200, response.text
    assert response.json()["experimental"] is True
    assert response.json()["active_configuration_unchanged"] is True
    assert "Warmth: 90%" in captured["messages"][0]["content"]
    assert store.active() == before
    assert web.chat_engine.conversation_history == original_history


def test_evaluation_records_actual_response_and_rejects_unverified_quotes(monkeypatch, tmp_path):
    from interfaces.web import app as web
    from ai import personality

    store = PersonalityStudioStore(tmp_path / "studio.db")
    monkeypatch.setattr(web, "personality_studio", store)
    monkeypatch.setattr(personality, "_studio_store", store)
    calls = iter([
        {"model": "fixture:latest", "message": {"content": "Hey, that sounds rough. I can keep you company."}, "done": True},
        {"model": "fixture:judge", "message": {"content": json.dumps({
            "dimensions": [
                {"trait": "warmth", "score": 4, "confidence": 0.8, "evidence": "that sounds rough", "explanation": "Acknowledges the stated difficulty."},
                {"trait": "sarcasm", "score": 3, "confidence": 0.9, "evidence": "invented quote", "explanation": "Unverified."},
            ], "overall_consistency": {"score": 4}, "limitations": []
        })}, "done": True},
    ])
    monkeypatch.setattr(web.ollama_client, "chat", lambda **kwargs: next(calls))
    response = TestClient(web.app).post("/api/dx/personality/evaluate", json={"prompt": "I've had a hard day.", "traits": STARTER_TRAITS})
    assert response.status_code == 200, response.text
    record = response.json()
    assert record["response"] == "Hey, that sounds rough. I can keep you company."
    dimensions = {item["trait"]: item for item in record["evaluation"]["dimensions"]}
    assert dimensions["warmth"]["observed_score"] == 4
    assert dimensions["warmth"]["predicted_score"] == 3.6
    assert dimensions["sarcasm"]["observed_score"] is None
    assert dimensions["sarcasm"]["status"] == "insufficient_evidence"
    history = store.evaluations()
    assert history[0]["evaluation_id"] == record["evaluation_id"]
    assert history[0]["response"] == record["response"]


def test_studio_is_linked_inside_existing_dx_page():
    from fastapi.testclient import TestClient
    from interfaces.web import app as web

    page = TestClient(web.app).get("/dx")
    assert page.status_code == 200
    assert 'data-view="personality-studio"' in page.text


def test_multi_turn_evaluation_uses_prior_preview_turns_and_stores_transcript(monkeypatch, tmp_path):
    from interfaces.web import app as web
    from ai import personality

    store = PersonalityStudioStore(tmp_path / "studio.db")
    monkeypatch.setattr(web, "personality_studio", store)
    monkeypatch.setattr(personality, "_studio_store", store)
    seen = []

    def fake_chat(**kwargs):
        seen.append([dict(message) for message in kwargs["messages"]])
        if len(seen) == 1:
            return {"model": "fixture:latest", "message": {"content": "I can stay and keep you company."}, "done": True}
        if len(seen) == 2:
            return {"model": "fixture:latest", "message": {"content": "Bug fights are rude. What failed?"}, "done": True}
        return {"model": "fixture:judge", "message": {"content": json.dumps({
            "dimensions": [{"trait": "warmth", "score": 4, "confidence": 0.7,
                            "evidence": "I can stay and keep you company", "explanation": "Offers direct companionship."}],
            "overall_consistency": {"score": 3, "confidence": 0.6, "explanation": "Recognizable through two turns."},
            "limitations": []
        })}, "done": True}

    monkeypatch.setattr(web.ollama_client, "chat", fake_chat)
    response = TestClient(web.app).post("/api/dx/personality/conversation", json={
        "turns": ["I've had a hard day.", "I spent all day fighting a bug."], "traits": STARTER_TRAITS})
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["evaluation"]["conversation_turns"]) == 2
    assert result["evaluation"]["overall_consistency"]["score"] == 3
    assert [message["role"] for message in seen[1][-3:]] == ["user", "assistant", "user"]
    assert "Turn 2 CYN-X" in store.evaluations()[0]["response"]
    assert result["active_configuration_unchanged"] is True


def test_personality_output_redacts_hidden_reasoning_and_credentials():
    from interfaces.web.app import _studio_safe_text

    safe = _studio_safe_text("visible <think>private reasoning</think> api_key=sk-abcdefghijklmnop1234")
    assert "private reasoning" not in safe
    assert "sk-abcdefghijklmnop1234" not in safe
    assert "visible" in safe

