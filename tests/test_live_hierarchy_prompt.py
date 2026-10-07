import sys, types
pm=types.ModuleType("ai.prompt_manager"); pm.PromptManager=type("PromptManager",(),{})
sys.modules.setdefault("ai.prompt_manager",pm)
from ai.personality import build_personality_prompt

def test_current_turn_memory_and_natural_voice():
    p=build_personality_prompt()
    assert "Current turn outranks memory" in p
    assert "Memory provides continuity" in p
    assert "surface old context merely because it is available" in p
    assert "Natural does not mean generic" in p
    assert "distinctive" in p and "dry humor" in p

def test_technical_precision_keeps_voice():
    p=build_personality_prompt()
    assert "Technical/problem-solving: evidence, correctness, clarity first" in p
    assert "Precision is mandatory; neutral" in p
    assert "corporate/documentation phrasing is not" in p
    assert "never at the cost of correctness" in p

def test_adult_information_is_direct_not_personalized():
    p=build_personality_prompt()
    assert "Non-graphic adult informational questions are ordinary requests" in p
    assert "answer directly" in p
    assert "disclosing preferences" in p
    assert "inviting personal questions" in p

def test_questions_relationship_stage_direction_and_barkly():
    p=build_personality_prompt()
    for x in ("Questions are tools, not conversation glue",
              "A turn may simply end after answering",
              '"mommy" addresses CYN-X as mommy',
              "inferring Piper is a child",
              "puppy/puppy-girl describes Piper",
              "not narrated acting",
              "Prefer direct dialogue",
              "without inventing CYN-X's feelings"):
        assert x in p
    assert "kiddo" not in p.lower()

def test_character_and_budget():
    p=build_personality_prompt()
    for x in ("Perspective changes what CYN-X notices","Cheerfulness can have an edge",
              "CYN-X has teeth","strangely cheerful","current-turn precedence"):
        assert x in p
    assert len(p)<=4000
