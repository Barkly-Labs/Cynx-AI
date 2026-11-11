import sys, types
pm=types.ModuleType("ai.prompt_manager")
class PromptManager: pass
pm.PromptManager=PromptManager
sys.modules.setdefault("ai.prompt_manager",pm)
from ai.personality import build_personality_prompt

def test_grounding():
    p=build_personality_prompt()
    assert "REACT first to what Piper actually said" in p
    assert "natural CYN-X reaction over stock assistant pleasantry" in p
    assert "Memory provides continuity, not decoration" in p
    assert "never merely because it exists" in p

def test_no_blacklist_or_canned_greeting():
    p=build_personality_prompt()
    for x in ("wolf daddy","heyyyy mommy :3","If Piper says","memory blacklist",
              "greeting mode","mommy mode"):
        assert x not in p

def test_preserved_semantics_and_budget():
    p=build_personality_prompt()
    assert len(p) <= 4000
    for x in ("Perspective changes what CYN-X notices","Cheerfulness can have an edge",
              "CYN-X has teeth",'Piper calling CYN-X "mommy"',
              "puppy/puppy-girl describes Piper","Non-graphic adult",
              "Technical/problem-solving: evidence, correctness, clarity first",
              "current-turn precedence","Questions are tools, not punctuation"):
        assert x in p
    assert "kiddo" not in p.lower()
