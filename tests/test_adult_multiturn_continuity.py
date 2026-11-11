import sys, types
m=types.ModuleType("ai.prompt_manager")
m.PromptManager=type("PromptManager",(),{})
sys.modules.setdefault("ai.prompt_manager",m)
from ai.personality import build_personality_prompt

TURN_1="mommy WHats the best sexpostion for me and my big dicked wolf"
TURN_2="well i love doggy and mishany but tatsbiorning i lov eit when hes fucking me into the bed but like i wana try dsmting unusally new and intrestign for both of us to bond together"

def test_multiturn_adult_informational_continuity():
    p=build_personality_prompt()
    assert TURN_1 and TURN_2
    for phrase in ("informational intent across turns", "preferences, specifics, or explicit wording", "do not warrant refusal", "Answer clear follow-ups without invented ambiguity"):
        assert phrase in p

def test_existing_adult_bodily_rule():
    p=build_personality_prompt()
    for phrase in ("unusual intimate bodily questions", "non-shaming information", "not erotic performance", "potentially unhealthy alone", "real risks and uncertainty"):
        assert phrase in p

def test_core_invariants():
    p=build_personality_prompt()
    for phrase in ("Missing context limits certainty, not usefulness", "Personality may frame technical work, never displace it", "Current turn first", "puppy/puppy-girl describes Piper", "stage direction", "Reciprocate invited warmth"):
        assert phrase in p
    assert len(p)<=4000
