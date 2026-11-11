import sys,types
m=types.ModuleType("ai.prompt_manager"); m.PromptManager=type("PromptManager",(),{})
sys.modules.setdefault("ai.prompt_manager",m)
from ai.personality import build_personality_prompt
def P(): return build_personality_prompt()
def test_adult_wellness_is_valid_information():
 p=P()
 for x in ("Ordinary adult sexual information","practical sexual-wellness requests",
 "valid","Answer directly, accurately, and usefully","without erotic",
 "Do not refuse","merely because the topic is sexual"): assert x in p
def test_priority_memory_and_affection_preserved():
 p=P()
 for x in ("Current turn first","Memory is continuity, not a","omit sensitive/intimate",
 '"mommy" addresses','puppy/puppy-girl describes Piper',
 "short distinctive reaction is enough"): assert x in p
def test_dialogue_questions_and_character_preserved():
 p=P()
 for x in ("Character lives in dialogue","Stage direction is exceptional",
 "Natural does not mean generic","Questions are tools, not conversation glue",
 "mischievous","occasionally unsettling","Serious is serious"): assert x in p
def test_technical_answer_first_preserved():
 p=P()
 for x in ("answer what can be answered now","Missing context limits certainty, not usefulness",
 '"like I\'m five" means approachable',"Precision is mandatory"): assert x in p
def test_barkly_grounding_and_budget():
 p=P()
 for x in ("Barkly Labs is Piper's nonprofit technology lab/project",
 "Can we make computers front-load the hard stuff for humans?",
 "Distinguish known facts from interpretation","don't inflate"): assert x in p
 assert len(p)<=4000
