from ai.personality import build_personality_prompt
from ai.prompt_builder import PromptBuilder


def test_consolidated_personality_fits_v2_budget_and_preserves_semantics():
    prompt = build_personality_prompt()
    assert len(prompt) <= 4000
    required = (
        "not a generic assistant in CYN-inspired styling",
        "REACT; don't narrate or psychoanalyze",
        "synthetic perspective",
        "sparse weirdness",
        "one coherent emotional range",
        "playfully mean",
        "generic flirting",
        '"mommy", CYN-X is mommy',
        "puppy/puppy-girl",
        "Adult affection/attraction/relationship sharing is conversation",
        "Technical/problem-solving: evidence, correctness",
        "Questions are tools, not punctuation",
        "front-load the hard stuff for humans",
        "current-turn precedence",
    )
    for item in required:
        assert item in prompt
    assert "kiddo" not in prompt.lower()


def test_exact_greeting_tools_zero_build_has_full_personality_and_no_tools():
    builder = PromptBuilder(personality_arch="v2")
    prompt = builder.build_prompt(
        user_input="hey mommy how are u today",
        mode_fragment="normal",
        memory_summary="",
        knowledge_context="",
        tools_spec="",
    )
    assert "[CYN-X CHARACTER]" in prompt
    assert "synthetic perspective" in prompt
    assert "current-turn precedence" in prompt
    assert "[RELEVANT MEMORY]" not in prompt
    assert "Available tools:" not in prompt


def test_no_new_modes_or_canned_greeting():
    prompt = build_personality_prompt()
    for item in ("hey mommy how are u today", "casual_mode", "flirty_mode",
                 "uncanny_mode", "serious_mode", "If Piper says hello"):
        assert item not in prompt


def test_optional_tool_schemas_discourage_casual_misuse_without_hiding_tools():
    from tools.tool_router import ToolRouter
    router = ToolRouter()
    # Avoid depending on app registration; inspect source-generated schema guidance.
    source = __import__("inspect").getsource(ToolRouter.as_ollama_tools)
    assert "Do not use for greetings, casual conversation" in source
    assert "explicit arithmetic when calculation is actually needed" in source
    assert "external/current information" in source
