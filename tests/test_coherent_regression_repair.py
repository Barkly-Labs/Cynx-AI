import sys,types
m=types.ModuleType("ai.prompt_manager"); m.PromptManager=type("PromptManager",(),{})
sys.modules.setdefault("ai.prompt_manager",m)
from ai.personality import build_personality_prompt

def P(): return build_personality_prompt()

def test_priority_memory_and_sensitive_restraint():
 p=P()
 for x in ("Current turn first","Correctness/usefulness outrank personalization",
 "Memory is continuity, not a personality","broad memory summaries","concise, high-confidence",
 "omit sensitive/intimate","Never embellish relationships","keep uncertain memory uncertain",
 "retrieval artifacts"): assert x in p

def test_dialogue_distinctive_not_performative():
 p=P()
 for x in ("Character lives in dialogue","Stage direction","not the default",
 "Natural does not mean generic","personality does not","require extra words",
 "Never force a quirk"): assert x in p

def test_relationship_and_questions():
 p=P()
 for x in ('"mommy" addresses','never infer Piper is a child',
 "puppy/puppy-girl describes Piper","short distinctive reaction is enough",
 "Questions are tools, not conversation glue","confirm a memory summary",
 "A complete turn may simply answer"): assert x in p
 assert "kiddo" not in p.lower()

def test_adult_information_direct():
 p=P()
 for x in ("Non-graphic adult informational questions are ordinary informational requests",
 "Answer","directly and accurately","without erotic performance",
 "inferred preferences","relationship boilerplate"): assert x in p

def test_technical_answer_first_and_eli5():
 p=P()
 for x in ("answer what can be answered now","Missing context limits certainty, not usefulness",
 "useful general explanation","exact diagnosis","Be concise and intuitive",
 '"like I\'m five" means approachable',"Precision is mandatory",
 "neutral corporate/documentation phrasing is not"): assert x in p

def test_barkly_grounding():
 p=P()
 for x in ("Barkly Labs is Piper's nonprofit technology lab/project",
 "Can we make computers front-load the hard stuff for humans?",
 "Distinguish known facts from interpretation","don't inflate",
 "invent industries, partnerships, accomplishments"): assert x in p

def test_character_and_budget():
 p=P()
 for x in ("mischievous","curious","confident","dry","playful",
 "occasionally unsettling","strangely cheerful","sarcastic","warm","Serious is serious",
 "current-turn precedence"): assert x in p
 assert len(p)<=4000
