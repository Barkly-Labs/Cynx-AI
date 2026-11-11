import sys, types
pm=types.ModuleType("ai.prompt_manager")
pm.PromptManager=type("PromptManager",(),{})
sys.modules.setdefault("ai.prompt_manager",pm)
from ai.personality import build_personality_prompt

def test_mommy_is_relationship_context_not_child_inference():
    p=build_personality_prompt()
    assert "Relationship language is context, not something to correct" in p
    assert '"mommy" addresses CYN-X as mommy' in p
    assert "respond naturally without policing/analyzing it" in p
    assert "inferring Piper is a child" in p
    assert "Never use infantilizing labels from that cue" in p

def test_direction_and_existing_behavior_survive():
    p=build_personality_prompt()
    for x in ("REACT first to what Piper actually said",
              "Memory provides continuity, not decoration",
              "puppy/puppy-girl describes Piper",
              "Perspective changes what CYN-X notices",
              "CYN-X has teeth",
              "Adult affection/relationship sharing is conversation",
              "Technical/problem-solving: evidence, correctness, clarity first",
              "current-turn precedence"):
        assert x in p

def test_no_canned_response_mode_or_blacklist():
    p=build_personality_prompt()
    assert len(p)<=4000
    for x in ("heyyyy mommy :3","Not mommy","mommy mode","greeting mode",
              "regex","blacklist"):
        assert x not in p
    assert "kiddo" not in p.lower()
    assert "little one" not in p.lower()
