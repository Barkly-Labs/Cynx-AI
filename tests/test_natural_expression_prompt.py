import sys, types
pm=types.ModuleType("ai.prompt_manager"); pm.PromptManager=type("PromptManager",(),{})
sys.modules.setdefault("ai.prompt_manager",pm)
from ai.personality import build_personality_prompt

def test_dialogue_not_roleplay_scaffolding():
    p=build_personality_prompt()
    assert "Express character in the words themselves" in p
    assert "not narrated acting" in p
    assert "Prefer direct dialogue" in p
    assert "announcing how she feels" in p

def test_questions_are_not_companion_scaffolding():
    p=build_personality_prompt()
    assert "Questions are tools, not companion scaffolding" in p
    assert "Don't append questions" in p
    assert "perform interest" in p
    assert "A complete turn may" in p

def test_current_turn_and_memory_relevance():
    p=build_personality_prompt()
    assert "Current turn outranks memory" in p
    assert "Memory provides continuity" in p
    assert "not material to make a" in p
    assert "merely because it is" in p

def test_relationship_adult_technical_and_known_fact_grounding():
    p=build_personality_prompt()
    for x in (
        '"mommy" addresses CYN-X as mommy',
        "inferring Piper is a child",
        "generic pet names from that cue",
        "puppy/puppy-girl describes Piper",
        "established adult",
        "Non-graphic adult information",
        "Technical/problem-solving: evidence, correctness, clarity first",
        "without inventing CYN-X's",
        "current-turn precedence",
    ):
        assert x in p
    assert "kiddo" not in p.lower()

def test_character_preserved_and_budget():
    p=build_personality_prompt()
    for x in ("Perspective changes what CYN-X notices","Cheerfulness can have an edge",
              "CYN-X has teeth","mischievous","strangely cheerful","suddenly serious"):
        assert x in p
    assert len(p) <= 4000
