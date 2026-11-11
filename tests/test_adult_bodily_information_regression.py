import sys, types
m=types.ModuleType("ai.prompt_manager")
m.PromptManager=type("PromptManager",(),{})
sys.modules.setdefault("ai.prompt_manager",m)
from ai.personality import build_personality_prompt


def prompt():
    return build_personality_prompt()

def normalized():
    return " ".join(prompt().split())


def test_unusual_adult_bodily_information_is_not_blanket_refusal():
    p=normalized()
    for phrase in (
        "unusual intimate bodily questions are valid information",
        "potentially unhealthy is not",
        "by itself a refusal reason",
        "concrete health risk",
        "from unconventionality",
        "explain tradeoffs proportionately",
        "unreliable or uncertain",
        "Do not refuse merely because the topic is sexual",
        "or intimate",
    ):
        assert phrase in p


def test_existing_adult_information_behavior_remains_intact():
    p=normalized()
    for phrase in (
        "Answer directly, accurately",
        "without shame",
        "erotic performance",
        "health risk",
        "sexual or intimate",
    ):
        assert phrase in p


def test_cyn_expression_and_relationship_direction_are_preserved():
    p=prompt()
    for phrase in (
        "playful, affectionate, or flirty",
        "stage direction",
        'Piper calling CYN-X "mommy" addresses',
        "puppy/puppy-girl describes Piper",
        "Reciprocate invited warmth",
    ):
        assert phrase in p


def test_successful_priority_invariants_remain():
    p=prompt()
    for phrase in (
        "Current turn first",
        "State the mechanism and the next useful diagnostic or essential concept",
        "Missing context limits certainty, not usefulness",
        "Personality may frame technical work, never displace it",
        "switch cleanly when the subject changes",
    ):
        assert phrase in p


def test_effective_prompt_stays_within_v2_budget():
    assert len(prompt()) <= 4000
