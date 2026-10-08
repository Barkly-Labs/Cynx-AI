import sys, types
m=types.ModuleType("ai.prompt_manager");m.PromptManager=type("P",(),{});sys.modules["ai.prompt_manager"]=m
from ai.personality import build_personality_prompt

def test_affection_and_distress():
 p=build_personality_prompt()
 for s in ("Meet affection naturally", "acknowledge feelings", "not referrals"):
  assert s in p

def test_invariants():
 p=build_personality_prompt()
 for s in ("Current turn first", "Personality may frame technical work, never displace it", "informational intent across turns", "puppy/puppy-girl describes Piper", "stage direction", "Reciprocate invited warmth"):
  assert s in p
 assert len(p)<=4000
