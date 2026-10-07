import sys,types
m=types.ModuleType("ai.prompt_manager"); m.PromptManager=type("PromptManager",(),{})
sys.modules.setdefault("ai.prompt_manager",m)
from ai.personality import build_personality_prompt
def P(): return build_personality_prompt()
def test_expression_is_contextual_not_banned_or_forced():
 p=P()
 for x in ("playful, affectionate, or flirty",
 "brief, varied","stage direction","technical/serious turns",
 "Never require a stage direction","pet name","Natural does not mean generic"): assert x in p
def test_conversational_switching():
 p=P()
 for x in ("current conversational direction","change turn by turn",
 "Reciprocate invited warmth","flirtation","switch cleanly when the subject changes"): assert x in p
def test_relationship_direction_and_memory_preserved():
 p=P()
 for x in ('"mommy" addresses','never infer Piper is a child',
 "puppy/puppy-girl describes Piper","Memory is continuity, not a personality",
 "omit sensitive/intimate","Current turn first"): assert x in p
def test_technical_and_adult_improvements_preserved():
 p=P()
 for x in ("answer what can be answered now","Missing context limits certainty, not usefulness",
 "Precision is mandatory","Ordinary adult sexual information","Do not refuse",
 "merely because the topic is sexual"): assert x in p
def test_no_legacy_mandates_or_modes_recovered():
 p=P().lower()
 for x in ("frequent pet names","scan complete","solver cyn mode","gremlin cyn mode",
 "helper cyn mode","focuses on emotional understanding rather than factual authority"):
  assert x not in p
def test_budget():
 assert len(P())<=4000
