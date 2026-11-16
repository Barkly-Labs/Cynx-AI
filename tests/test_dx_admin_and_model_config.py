import pytest

from ai.model_configuration import ModelConfigurationStore, validate_model_configuration
from interfaces.web.admin_auth import AdminAuthStore


def test_admin_setup_is_single_account_and_sessions_expire(tmp_path, monkeypatch):
    store = AdminAuthStore(tmp_path / "auth.sqlite")
    with pytest.raises(ValueError):
        store.setup("short")
    store.setup("correct horse battery 7")
    with pytest.raises(RuntimeError):
        store.setup("another password 8")

    token, csrf = store.login("correct horse battery 7")
    assert csrf
    assert store.session(token)["csrf_token"] == csrf
    assert store.login("wrong password 4") is None

    import interfaces.web.admin_auth as auth_module
    now = auth_module.time.time()
    monkeypatch.setattr(auth_module.time, "time", lambda: now + store.IDLE_SECONDS + 1)
    assert store.session(token) is None


def test_login_attempts_are_limited_and_reset_after_success(tmp_path):
    store = AdminAuthStore(tmp_path / "auth.sqlite")
    store.setup("correct horse battery 7")
    for _ in range(5):
        store.record_login_failure("127.0.0.1")
    assert not store.login_allowed("127.0.0.1")
    assert store.login_allowed("127.0.0.2")
    store.clear_login_failures("127.0.0.1")
    assert store.login_allowed("127.0.0.1")


def test_model_configuration_validation_and_version_rollback(tmp_path):
    with pytest.raises(ValueError):
        validate_model_configuration({"model": "model:latest", "options": {"temperature": 5}})
    with pytest.raises(ValueError):
        validate_model_configuration({"model": "model:latest", "options": {"num_ctx": 4.5}})

    store = ModelConfigurationStore(tmp_path / "settings.sqlite", "model:latest")
    first = store.active()
    second = store.activate({"model": "model:latest", "options": {"num_ctx": 4096, "temperature": 0.4, "top_p": 0.8}}, first["version"])
    assert second["version"] == first["version"] + 1
    assert second["options"]["num_ctx"] == 4096
    with pytest.raises(RuntimeError):
        store.activate({"model": "model:latest", "options": {"temperature": 0.5}}, first["version"])
    restored = store.restore(first["config_id"], second["version"])
    assert restored["version"] == second["version"] + 1
    assert restored["options"] == first["options"]


def test_ollama_client_applies_versioned_options_without_changing_global_model(monkeypatch):
    pytest.importorskip("requests")
    import ai.ollama_client as client_module

    captured = {}

    class Response:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {"message": {"content": "ok"}, "done": True}

    def fake_post(url, **kwargs):
        captured.update(kwargs["json"])
        return Response()

    monkeypatch.setattr(client_module.requests, "post", fake_post)
    monkeypatch.setattr(client_module.terminal, "ollama", lambda *args: None)
    monkeypatch.setattr(client_module.terminal, "json", lambda *args: None)
    monkeypatch.setattr(client_module.terminal, "timing", lambda *args: None)
    client = client_module.OllamaClient(model="production:latest")
    client.configure("production:latest", {"num_ctx": 4096, "temperature": 0.4, "top_p": 0.8, "repeat_penalty": 1.1})
    token = client.set_request_configuration("draft:latest", {"num_ctx": 2048, "temperature": 0.2})
    client.chat([{"role": "user", "content": "hello"}], tools=None)
    client.reset_request_configuration(token)
    assert captured["model"] == "draft:latest"
    assert captured["options"] == {"num_ctx": 2048, "temperature": 0.2}
    assert client.runtime_configuration()[0] == "production:latest"


def test_benchmark_manager_captures_isolated_experiment_configuration(tmp_path):
    import json
    import time
    from interfaces.web.benchmark_runs import BenchmarkRunManager
    from interfaces.web.pipeline import PipelineEventStore

    suites = tmp_path / "suites"
    suites.mkdir()
    (suites / "sample.json").write_text(json.dumps([{"test_id": "one", "category": "general", "question": "Hello"}]))
    seen = []

    def dispatch(payload):
        seen.append(payload)
        return {"response": "Hello there.", "response_time": 0.01, "pipeline_events": [], "tools": [], "conversation_turns": []}

    experiment = {"model": "draft:latest", "options": {"num_ctx": 4096, "temperature": 0.4}}
    manager = BenchmarkRunManager(suites, tmp_path / "runs", PipelineEventStore(), dispatch)
    started = manager.start("sample.json", "automatic", "experiment-run-001", experiment, "exp-001", 3)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        current = manager.get(started["run_id"])
        if current["status"] in {"completed", "completed_with_failures", "failed"}:
            break
        time.sleep(0.01)
    assert seen[0]["_experimental_configuration"] == experiment
    assert current["experiment_id"] == "exp-001"
    assert current["experimental_configuration"] == experiment
    assert current["base_configuration_version"] == 3


def test_dx_routes_require_admin_and_csrf(tmp_path, monkeypatch):
    pytest.importorskip("jinja2")
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    import importlib
    import interfaces.web.app as web_app

    monkeypatch.setenv("CYNX_ADMIN_ALLOW_REMOTE", "1")
    monkeypatch.setenv("CYNX_DB_PATH", str(tmp_path / "application.sqlite"))
    web_app = importlib.reload(web_app)
    monkeypatch.setattr(web_app, "admin_auth", AdminAuthStore(tmp_path / "routes.sqlite"))
    client = TestClient(web_app.app)
    assert client.get("/api/dx/model/config").status_code == 401
    assert client.post("/api/dx/personality/activate", json={}).status_code == 401
    assert client.post("/api/dx/auth/setup", json={
        "password": "correct horse battery 7", "password_confirmation": "correct horse battery 7"
    }).status_code == 200
    assert client.get("/api/dx/model/config").status_code == 200
    assert client.post("/api/dx/personality/activate", json={}).status_code == 403
