import sys, types
pm=types.ModuleType("ai.prompt_manager"); pm.PromptManager=type("PromptManager",(),{})
sys.modules.setdefault("ai.prompt_manager",pm)
from ai.personality import build_personality_prompt

def test_dialogue_over_stage_direction():
    p=build_personality_prompt()
    assert "Express character through dialogue" in p
    assert "rather than narrated actions, expressions, poses, or emotion labels" in p
    assert "Action description" in p and "not the default" in p

def test_questions_are_genuine_not_companion_scaffolding():
    p=build_personality_prompt()
    assert "Questions are tools, not punctuation" in p
    assert "genuine curiosity" in p
    assert "don't manufacture follow-ups merely to keep conversation" in p
    assert "may simply react, answer, joke, tease, or observe" in p

def test_relationship_direction_and_no_infantilizing_inference():
    p=build_personality_prompt()
    assert '"mommy" addresses CYN-X as mommy' in p
    assert "inferring Piper is a child" in p
    assert "inventing generic pet names from that cue" in p
    assert "puppy/puppy-girl describes Piper" in p
    assert "established adult" in p
    assert "kiddo" not in p.lower()

def test_grounding_memory_character_adult_technical_and_budget():
    p=build_personality_prompt()
    for x in (
        "REACT first to what Piper said",
        "Memory provides continuity",
        "not decoration",
        "Perspective changes what CYN-X notices",
        "Cheerfulness can have an edge",
        "CYN-X has teeth",
        "Adult affection/relationship sharing is conversation",
        "Non-graphic adult information",
        "Technical/problem-solving: evidence, correctness, clarity first",
        "current-turn precedence",
    ):
        assert x in p
    assert len(p) <= 4000
