import json
import time

from fastapi.testclient import TestClient

from interfaces.web import app as web_app


def test_dx_shell_and_real_benchmark_catalog_are_served():
    client = TestClient(web_app.app)

    page = client.get("/dx")
    suites = client.get("/api/dx/benchmark/suites")
    questions = client.get("/api/dx/benchmark/suites/questions.json")

    assert page.status_code == 200
    assert "Benchmark Lab" in page.text
    assert suites.status_code == 200
    assert len(suites.json()["suites"]) >= 1
    assert questions.status_code == 200
    assert len(questions.json()["cases"]) == 27


def test_main_chat_redesign_serves_existing_controls_and_shared_assets():
    client = TestClient(web_app.app)
    page = client.get("/")
    theme = client.get("/static/cynx-theme.css")
    shell = client.get("/static/chat-shell.css")
    script = client.get("/static/chat-shell.js")
    chat_script = client.get("/static/chat.js")

    assert page.status_code == theme.status_code == shell.status_code == script.status_code == chat_script.status_code == 200
    assert 'id="message"' in page.text and "<textarea" in page.text
    assert 'id="sendButton"' in page.text and 'id="stop-generation"' in page.text
    assert 'id="prompt-preset"' in page.text and 'id="prompt-layers-panel"' in page.text
    assert 'id="thinking"' in page.text and 'id="pipeline-cancel"' in page.text
    assert "conversation_id" in chat_script.text
    assert "--cynx-pink" in theme.text


def test_personality_trace_view_is_shipped_with_dx_assets():
    client = TestClient(web_app.app)
    page = client.get("/dx")
    script = client.get("/static/dx.js")
    styles = client.get("/static/dx.css")

    assert page.status_code == script.status_code == styles.status_code == 200
    assert "Personality Trace" in script.text
    assert "copy-personality-trace" in script.text
    assert ".bench-tabs" in styles.text


def test_dx_tool_explorer_uses_registered_router():
    client = TestClient(web_app.app)
    response = client.get("/api/dx/tools")

    assert response.status_code == 200
    tools = response.json()["tools"]
    assert {tool["name"] for tool in tools} == set(web_app.tool_router.list_tools())
    assert all("schema" in tool for tool in tools)


def test_dx_benchmark_saves_existing_scorer_output(tmp_path, monkeypatch):
    monkeypatch.setattr(web_app, "DX_BENCHMARK_RUNS", tmp_path)
    monkeypatch.setattr(web_app.benchmark_runs, "results_dir", tmp_path)
    client = TestClient(web_app.app)

    response = client.post("/api/dx/benchmark/runs", json={
        "suite": "social-style.json",
        "mode": "manual",
        "results": [{
            "test_id": "SOCIAL_TEST",
            "category": "SOCIAL_STYLE",
            "question": "ugh this coffee sucks",
            "response": "Yeah, burnt coffee can ruin the whole morning.",
            "response_time": 0.25,
            "tools": [{"name": "web_search", "status": "failed"}],
            "test": {"social_style": {"self_contained": True, "low_stakes": True}},
        }],
    })

    assert response.status_code == 200
    result = response.json()
    assert result["attempted"] == 1
    assert result["successful"] == 1
    assert result["tool_failures"] == 1
    assert result["partial_tool_failures"] == 1
    assert result["results"][0]["scores"]["overall"] == 2.0
    saved = json.loads((tmp_path / f"{result['run_id']}.json").read_text())
    assert saved["results"][0]["response"] == "Yeah, burnt coffee can ruin the whole morning."

    history = client.get("/api/dx/benchmark/runs")
    assert history.status_code == 200
    assert history.json()["runs"][0]["run_id"] == result["run_id"]


def test_dx_suite_route_rejects_path_traversal():
    client = TestClient(web_app.app)
    response = client.get("/api/dx/benchmark/suites/%2e%2e%2fconfig.py")

    assert response.status_code == 404


def test_dx_benchmark_watchdog_reads_persisted_runs_without_running_benchmark(tmp_path, monkeypatch):
    old = {
        "run_id": "watch-old", "suite": "watch.json", "created_at": "2026-01-01", "status": "completed",
        "questions": [{"question_id": "old-q", "test_id": "WATCH_1", "category": "SOCIAL_STYLE",
                       "question": "Say hello.", "status": "completed", "quality_status": "passed",
                       "response": "Hello!", "score": {"overall": 2.0}, "tools": [], "metrics": {}}],
    }
    new = {
        "run_id": "watch-new", "suite": "watch.json", "created_at": "2026-01-02", "status": "completed_with_failures",
        "questions": [{"question_id": "new-q", "test_id": "WATCH_1", "category": "SOCIAL_STYLE",
                       "question": "Say hello.", "test": {"expected_behavior": "Greet"}, "status": "completed",
                       "quality_status": "failed", "response": "I cannot help with that.",
                       "score": {"overall": 0.0}, "tools": [], "metrics": {}}],
    }
    tmp_path.joinpath("watch-old.json").write_text(json.dumps(old))
    tmp_path.joinpath("watch-new.json").write_text(json.dumps(new))
    monkeypatch.setattr(web_app.benchmark_runs, "results_dir", tmp_path)

    response = TestClient(web_app.app).get("/api/dx/benchmark/watchdog?run_id=watch-new")

    assert response.status_code == 200
    report = response.json()
    assert report["baseline_run_id"] == "watch-old"
    assert report["regression_feed"][0]["regression"] is True
    assert report["questions"][0]["failure"]["signals"][0]["kind"] == "possible_unexpected_refusal"


def test_dx_watchdog_tab_is_inside_existing_benchmark_workspace():
    client = TestClient(web_app.app)
    page = client.get("/dx")
    script = client.get("/static/dx.js")
    styles = client.get("/static/dx.css")

    assert page.status_code == script.status_code == styles.status_code == 200
    assert 'data-bench-tab="watchdog"' in script.text
    assert 'id="benchmark-watchdog-panel"' in script.text
    assert ".watchdog-inspector" in styles.text


def test_versioned_personality_scenarios_are_added_to_existing_benchmark_catalog():
    client = TestClient(web_app.app)
    catalog = client.get("/api/dx/benchmark/suites")
    suite = client.get("/api/dx/benchmark/suites/personality-diagnostics-v1.json")

    assert catalog.status_code == suite.status_code == 200
    item = next(entry for entry in catalog.json()["suites"] if entry["id"] == "personality-diagnostics-v1.json")
    assert item["count"] >= 10
    assert item["personality_contract_version"] == "1.0.0"
    assert all(case.get("turns") and case.get("target_dimensions") for case in suite.json()["cases"])


def test_personality_diagnostics_endpoints_read_and_persist_run_scoped_records(tmp_path, monkeypatch):
    run_id = "85db1028-6819-42aa-b860-6711403053e2"
    run = {
        "schema": "cynx-dx-benchmark-run-v1", "run_id": run_id,
        "suite": "personality-diagnostics-v1.json", "status": "completed", "created_at": "2026-11-12T12:00:00+00:00",
        "personality_contract_version": "1.0.0", "scenario_library_version": "1.0.0",
        "questions": [{
            "question_id": "question-1", "scenario_id": "serious-support-01", "test_id": "SUPPORT_01",
            "scenario_category": "emotional_sensitivity", "target_dimensions": ["warmth"],
            "expected_behavior": "Respond calmly and acknowledge the stated feeling.",
            "question": "I feel lonely.", "status": "completed", "quality_status": "scored",
            "response": "I hear that this has been lonely.", "request_id": "request-1", "request_ids": ["request-1"],
            "conversation_turns": [{"turn_index": 1, "user_message": "I feel lonely.", "response": "I hear that this has been lonely.", "request_id": "request-1"}],
            "request_events": [], "tools": [], "metrics": {},
        }],
    }
    (tmp_path / f"{run_id}.json").write_text(json.dumps(run), encoding="utf-8")

    class Judge:
        model = "local-test-judge"

        def chat(self, messages, tools=None, **kwargs):
            assert tools is None
            return {"message": {"content": json.dumps({"evaluations": [{
                "dimension": "warmth", "score": 3.2, "confidence": 0.8,
                "observed_behavior": "Acknowledged loneliness.", "expected_behavior": "Acknowledge the feeling.",
                "explanation": "The answer uses a measured acknowledgment.", "potential_contributing_factors": [],
                "recommendations": [], "evidence": [{"turn_index": 1, "quote": "I hear that this has been lonely."}],
            }]})}}

    service = web_app.personality_diagnostics
    monkeypatch.setattr(service, "runs_dir", tmp_path)
    monkeypatch.setattr(service, "records_dir", tmp_path / "personality_diagnostics")
    monkeypatch.setattr(service, "ollama", Judge())
    client = TestClient(web_app.app)

    evaluated = client.post(f"/api/dx/benchmark/personality/{run_id}/evaluate?refresh=true", json={})
    historical = client.get(f"/api/dx/benchmark/personality/history?run_id={run_id}")

    assert evaluated.status_code == historical.status_code == 200
    assert evaluated.json()["diagnostics"][0]["dimension"] == "warmth"
    assert historical.json()["trend"][0]["dimensions"]["warmth"] == 3.2


def test_backend_benchmark_runs_after_start_response_and_uses_chat_dispatcher(tmp_path, monkeypatch):
    suites = tmp_path / "suites"
    runs = tmp_path / "runs"
    suites.mkdir()
    (suites / "one.json").write_text(json.dumps([
        {"test_id": "ONE", "category": "SOCIAL_STYLE", "question": "The actual suite question."}
    ]), encoding="utf-8")
    monkeypatch.setattr(web_app.benchmark_runs, "suites_dir", suites)
    monkeypatch.setattr(web_app.benchmark_runs, "results_dir", runs)
    seen = []

    async def fake_chat_dispatch(data):
        seen.append(data)
        web_app.pipeline_events.create(data["request_id"])
        web_app.pipeline_events.publish(data["request_id"], "stage", stage="generating_response", status="active")
        web_app.pipeline_events.publish(data["request_id"], "request_completed")
        return {"request_id": data["request_id"], "response": "Actual generated benchmark answer.", "response_time": 0.41}

    monkeypatch.setattr(web_app, "_dispatch_chat", fake_chat_dispatch)
    client = TestClient(web_app.app)
    start = client.post("/api/dx/benchmark/start", json={
        "suite": "one.json", "mode": "automatic", "idempotency_key": "api-start-key-0001"
    })
    assert start.status_code == 200
    run_id = start.json()["run_id"]

    deadline = time.monotonic() + 2
    state = start.json()
    while time.monotonic() < deadline and state["status"] not in {"completed", "completed_with_failures", "failed"}:
        time.sleep(0.01)
        state = client.get(f"/api/dx/benchmark/runs/{run_id}").json()

    assert state["status"] == "completed"
    assert state["questions"][0]["response"] == "Actual generated benchmark answer."
    assert state["questions"][0]["metrics"]["response_time_seconds"] == 0.41
    assert seen == [{"message": "The actual suite question.", "request_id": state["questions"][0]["request_id"]}]
    assert json.loads((runs / f"{run_id}.json").read_text())["questions"][0]["response"] == "Actual generated benchmark answer."
    latest = client.get("/api/dx/benchmark/latest").json()["run"]
    assert latest["run_id"] == run_id
    assert latest["questions"][0]["response"] == "Actual generated benchmark answer."
    delta = client.get(f"/api/dx/benchmark/runs/{run_id}/updates?after_event=1").json()
    assert any(question["status"] == "completed" for question in delta["questions"])


def test_benchmark_dispatch_persists_chat_engine_trace_events(tmp_path, monkeypatch):
    suites = tmp_path / "suites"
    runs = tmp_path / "runs"
    suites.mkdir()
    (suites / "trace.json").write_text(json.dumps([
        {"test_id": "TRACE", "category": "SOCIAL_STYLE", "question": "Trace this real request."}
    ]), encoding="utf-8")
    monkeypatch.setattr(web_app.benchmark_runs, "suites_dir", suites)
    monkeypatch.setattr(web_app.benchmark_runs, "results_dir", runs)

    def fake_engine(**kwargs):
        kwargs["trace_callback"]({"stage": "instructions_assembled", "status": "completed", "system_prompt": "captured"})
        kwargs["pipeline_callback"]({"type": "decision", "action": "answer_directly", "tools": []})
        return "Traceable answer."

    monkeypatch.setattr(web_app.chat_engine, "handle_user_message", fake_engine)
    client = TestClient(web_app.app)
    started = client.post("/api/dx/benchmark/start", json={
        "suite": "trace.json", "mode": "automatic", "idempotency_key": "trace-api-key-00001"
    })
    assert started.status_code == 200
    run_id = started.json()["run_id"]

    deadline = time.monotonic() + 2
    run = started.json()
    while time.monotonic() < deadline and run["status"] not in {"completed", "completed_with_failures", "failed"}:
        time.sleep(0.01)
        run = client.get(f"/api/dx/benchmark/runs/{run_id}").json()

    question = run["questions"][0]
    assert question["response"] == "Traceable answer."
    assert question["personality_trace"]["available"] is True
    assert {event["stage"] for event in question["personality_trace"]["events"]} >= {
        "configuration_loaded", "instructions_assembled", "routing_decision", "response_returned"
    }


def test_personality_scenario_turns_share_chat_conversation_but_use_distinct_request_ids(monkeypatch):
    import asyncio

    conversation_ids = []
    request_ids = []
    registrations = []

    class Events:
        def read(self, request_id):
            return {"events": []}

    async def fake_chat(data):
        conversation_ids.append(data["conversation_id"])
        request_ids.append(data["request_id"])
        return {"response": f"Answer {len(request_ids)}", "response_time": 0.1}

    class RunManager:
        def register_question_request(self, run_id, question_id, request_id):
            registrations.append((run_id, question_id, request_id))

    monkeypatch.setattr(web_app, "_dispatch_chat", fake_chat)
    monkeypatch.setattr(web_app, "benchmark_runs", RunManager())
    monkeypatch.setattr(web_app, "pipeline_events", Events())
    data = {
        "request_id": "first-request", "conversation_id": "scenario-conversation",
        "_benchmark_run_id": "run-1", "_benchmark_question_id": "question-1",
        "turns": ["First user turn", "Second user turn"],
        "turn_expectations": [{"expected_tools": []}, {"expected_tools": []}],
    }

    result = asyncio.run(web_app._dispatch_benchmark_scenario(data))

    assert conversation_ids == ["scenario-conversation", "scenario-conversation"]
    assert request_ids[0] == "first-request" and request_ids[0] != request_ids[1]
    assert registrations == [("run-1", "question-1", request_ids[1])]
    assert [turn["response"] for turn in result["conversation_turns"]] == ["Answer 1", "Answer 2"]


def test_chat_route_uses_validated_conversation_id_for_short_term_context(monkeypatch):
    seen = {}

    def fake_engine(**kwargs):
        seen.update(kwargs)
        return "Conversation response."

    monkeypatch.setattr(web_app.chat_engine, "handle_user_message", fake_engine)
    conversation_id = "f7a4d609-6ec2-4dc6-9d42-1b8cd2b1664a"
    response = TestClient(web_app.app).post("/chat", json={
        "message": "Isolate this conversation.", "conversation_id": conversation_id
    })

    assert response.status_code == 200
    assert seen["conversation_key"] == f"web_user:{conversation_id}"
    assert seen["user_id"] == "web_user"
