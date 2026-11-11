import sys,types,json
from pathlib import Path
m=types.ModuleType("ai.prompt_manager"); m.PromptManager=type("PromptManager",(),{})
sys.modules.setdefault("ai.prompt_manager",m)
from ai.personality import build_personality_prompt
def P(): return build_personality_prompt()
def test_technical_priority_is_explicit():
 p=P()
 for x in ("State the mechanism","next useful diagnostic","essential concept",
           "Missing context limits certainty, not usefulness",
           "Personality may frame technical work, never displace it"): assert x in p
def test_expression_relationship_and_switching_preserved():
 p=P()
 for x in ("playful, affectionate, or flirty","brief, varied","stage direction",
           "Reciprocate invited warmth","flirtation","switch cleanly when the subject changes",
           '"mommy" addresses',"puppy/puppy-girl describes Piper"): assert x in p
def test_memory_adult_grounding_preserved():
 p=P()
 for x in ("Current turn first","Memory is continuity","omit sensitive/intimate",
           "Ordinary adult sexual information","Do not refuse","Barkly Labs"): assert x in p
def test_budget(): assert len(P())<=4000
