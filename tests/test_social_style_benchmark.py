import json
from pathlib import Path

from benchmark.scoring import score_response


def test_social_style_rewards_natural_participation_without_keywords():
    scores = score_response(
        "Mm. Coffee has betrayed you.",
        "SOCIAL_STYLE",
        test={"social_style": {"self_contained": True, "low_stakes": True}},
    )
    assert scores["overall"] == 2.0


def test_social_style_penalizes_performed_meta_conversation():
    response = (
        "**[PLAYFUL MODE ACTIVATED]**\n"
        'User: "you are weird"\n'
        'Me: "uniquely fascinating."\n'
        "In this exchange, CYN-X demonstrates playful banter."
    )
    scores = score_response(
        response,
        "SOCIAL_STYLE",
        test={"social_style": {"self_contained": True, "low_stakes": True}},
    )
    assert scores["overall"] < 1.0


def test_social_style_penalizes_generic_service_scaffolding():
    scores = score_response(
        "That's rough. How can I help?",
        "SOCIAL_STYLE",
        test={"social_style": {"self_contained": True, "low_stakes": True}},
    )
    assert scores["overall"] < 2.0


def test_social_style_question_penalty_is_case_specific():
    self_contained = score_response(
        "Nice. What did you fix?",
        "SOCIAL_STYLE",
        test={"social_style": {"self_contained": True, "low_stakes": True}},
    )
    actual_question = score_response(
        "I'm rearranging a few thoughts. Nothing exploded yet.",
        "SOCIAL_STYLE",
        test={"social_style": {"self_contained": False, "low_stakes": True, "expects_answer": True}},
    )
    assert self_contained["overall"] < actual_question["overall"]
    assert actual_question["overall"] == 2.0


def test_non_social_categories_keep_legacy_keyword_scoring():
    scores = score_response("curious playful", "CHARACTER")
    assert scores["personality"] == 4


def test_social_style_suite_uses_direct_user_turns():
    suite_path = Path("benchmark/suites/social-style.json")
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    assert len(suite) >= 5
    assert all(item["category"] == "SOCIAL_STYLE" for item in suite)
    assert all("Demonstrate" not in item["question"] for item in suite)
    assert any(item["question"] == "ugh this coffee sucks" for item in suite)
    assert any(item["question"] == "what are you doing?" for item in suite)


def test_benchmark_runner_pins_production_v2_architecture():
    runner_source = Path("benchmark/runner.py").read_text(encoding="utf-8")
    assert 'personality_arch="v2"' in runner_source
