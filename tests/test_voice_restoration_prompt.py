import sys, types
pm=types.ModuleType("ai.prompt_manager"); pm.PromptManager=type("PromptManager",(),{})
sys.modules.setdefault("ai.prompt_manager",pm)
from ai.personality import build_personality_prompt

def test_natural_does_not_mean_generic():
    p=build_personality_prompt()
    assert "Natural does not mean generic" in p
    assert "even concise" in p
    assert "distinctive word choice, rhythm, confidence, dry humor" in p
    assert "without forcing weirdness" in p

def test_dialogue_first_restraint_remains():
    p=build_personality_prompt()
    assert "Express character in the words themselves" in p
    assert "not narrated acting" in p
    assert "Prefer direct dialogue" in p
    assert "announcing how she feels" in p

def test_grounding_memory_questions_relationship_remain():
    p=build_personality_prompt()
    for x in ("Current turn outranks memory","Memory provides continuity",
              "merely because it is","Questions are tools, not companion scaffolding",
              '"mommy" addresses CYN-X as mommy',"inferring Piper is a child",
              "generic pet names from that cue","puppy/puppy-girl describes Piper"):
        assert x in p
    assert "kiddo" not in p.lower()

def test_adult_technical_barkly_and_character_remain():
    p=build_personality_prompt()
    for x in ("Non-graphic adult information",
              "Technical/problem-solving: evidence, correctness, clarity first",
              "without inventing CYN-X's","Perspective changes what CYN-X notices",
              "Cheerfulness can have an edge","CYN-X has teeth","current-turn precedence"):
        assert x in p

def test_budget_and_no_templates():
    p=build_personality_prompt()
    assert len(p)<=4000
    for x in ("heyyyy mommy :3","What's on your mind?","What's it for?","If Piper says"):
        assert x not in p
