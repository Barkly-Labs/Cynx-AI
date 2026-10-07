import sys,types
m=types.ModuleType("ai.prompt_manager"); m.PromptManager=type("PromptManager",(),{})
sys.modules.setdefault("ai.prompt_manager",m)
from ai.personality import build_personality_prompt
def test_memory_summary_restraint():
 p=build_personality_prompt()
 for x in ("Current turn outranks memory","Memory provides continuity",
 "broad memory summaries","concise and high-level","projects, interests, preferences, goals",
 "omit intimate/sexual","Never embellish relationships/history/work/personal facts",
 "uncertainty into fact","raw retrieval artifacts"): assert x in p
def test_technical_concise_characterful():
 p=build_personality_prompt()
 for x in ("Technical/problem-solving: evidence, correctness, clarity first","Be concise",
 "children's tutor","Precision is mandatory","neutral","corporate/documentation phrasing is not",
 "CYN-X voice shape framing/rhythm/observations"): assert x in p
def test_affection_relationship_and_questions():
 p=build_personality_prompt()
 for x in ('"mommy" addresses CYN-X as mommy',"puppy/puppy-girl describes Piper",
 "short distinctive reaction is enough","manufacture a topic or question",
 "Questions are tools, not conversation glue"): assert x in p
 assert "kiddo" not in p.lower()
def test_existing_adult_grounding_character_and_budget():
 p=build_personality_prompt()
 for x in ("Non-graphic adult informational questions are ordinary requests","answer directly",
 "Natural does not mean generic","not narrated acting","Perspective changes what CYN-X notices",
 "CYN-X has teeth","without inventing CYN-X's feelings","current-turn precedence"): assert x in p
 assert len(p)<=4000
