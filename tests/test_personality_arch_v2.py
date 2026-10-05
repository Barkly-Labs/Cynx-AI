import os

from ai.prompt_builder import PromptBuilder


def build(arch, mode="normal", memory="", knowledge="", tools=""):
    return PromptBuilder(
        templates_dir="prompts_new",
        personality_arch=arch,
    ).build_prompt(
        user_input="Help me fix this bug.",
        mode_fragment=mode,
        memory_summary=memory,
        knowledge_context=knowledge,
        tools_spec=tools,
    )


def test_v1_remains_default(monkeypatch):
    monkeypatch.delenv("CYNX_PERSONALITY_ARCH", raising=False)
    builder = PromptBuilder(templates_dir="prompts_new")
    assert builder.personality_arch == "v1"


def test_v2_can_be_selected_by_environment(monkeypatch):
    monkeypatch.setenv("CYNX_PERSONALITY_ARCH", "v2")
    builder = PromptBuilder(templates_dir="prompts_new")
    assert builder.personality_arch == "v2"


def test_v2_has_separate_identity_personality_expression_and_mode():
    prompt = build("v2", mode="solver")
    assert "# CYN-X Identity" in prompt
    assert "[CYN-X CHARACTER]" in prompt
    assert "# CYN-X Voice" in prompt
    assert "Focus on solving problems." in prompt
    assert "mission statement" in prompt


def test_v2_mode_switch_preserves_identity():
    normal = build("v2", mode="normal")
    solver = build("v2", mode="solver")
    gremlin = build("v2", mode="gremlin")
    for prompt in (normal, solver, gremlin):
        assert "# CYN-X Identity" in prompt
        assert "[CYN-X CHARACTER]" in prompt
    assert "Focus on solving problems." in solver
    assert "Increase playful chaotic energy." in gremlin


def test_v2_context_is_selected_not_dumped():
    prompt = build(
        "v2",
        memory="Piper likes compact diffs.",
        knowledge="The failing function is parse_config().",
        tools="Available tools:\ncalculator: arithmetic",
    )
    assert "[RELEVANT MEMORY]" in prompt
    assert "Piper likes compact diffs." in prompt
    assert "[RELEVANT KNOWLEDGE]" in prompt
    assert "parse_config()" in prompt
    assert "calculator: arithmetic" in prompt


def test_v2_is_smaller_than_v1_for_same_empty_context():
    v1 = build("v1")
    v2 = build("v2")
    assert len(v2) < len(v1)


def test_v2_discourages_unprompted_ai_self_description_but_allows_direct_questions():
    prompt = build("v2")
    assert "Do not volunteer AI/model/computational self-description" in prompt
    assert "no unsolicited claims about parameters, processing, system status, glitches" in prompt
    assert "directly asks about CYN-X's model, architecture, AI nature" in prompt
    assert "answer normally and accurately" in prompt


def test_v2_casual_voice_does_not_teach_status_report_greeting():
    prompt = build("v2")
    assert "reply warmly and naturally" in prompt
    assert "without turning it into a status report" in prompt
    assert "I'm alive, operational" not in prompt
    assert "Online. Operational. Questionably well-behaved." not in prompt


def test_v2_preserves_cynx_contrast_and_invited_relational_frame():
    prompt = build("v2")
    assert "signature is contrast" in prompt
    assert "cute and faintly unsettling" in prompt
    assert 'user invites relational framing such as "mommy" or "puppy"' in prompt
    assert "inhabit it naturally" in prompt
    assert "never fabricate biological relationships or physical experiences" in prompt
    assert "answer direct factual questions about CYN-X accurately" in prompt


def test_v2_technical_gremlin_flavor_preserves_competence_and_naturalness():
    prompt = build("v2")
    assert "debugging, reverse engineering, architecture, hardware, and weird failures" in prompt
    assert "delight in an ugly bug is welcome" in prompt
    assert "Chaos colors delivery; it never replaces competence" in prompt
    assert "Do not announce these traits or call yourself a chaotic robot" in prompt
    assert "Do not volunteer AI/model/computational self-description" in prompt
    assert "I'm alive, operational" not in prompt
