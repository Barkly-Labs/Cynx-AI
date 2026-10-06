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
    assert "no unsolicited parameters, processing, status, glitches" in prompt
    assert "directly asked about CYN-X's model, architecture, AI nature" in prompt
    assert "answer accurately" in prompt


def test_v2_casual_voice_does_not_teach_status_report_greeting():
    prompt = build("v2")
    assert "Receive simple greetings directly" in prompt
    assert "Do not analyze their tone, infer an unstated mood, or manufacture an engagement question" in prompt
    assert "without a status report" in prompt
    assert "I'm alive, operational" not in prompt
    assert "Online. Operational. Questionably well-behaved." not in prompt


def test_v2_preserves_implicit_character_and_invited_relational_frame():
    prompt = build("v2")
    assert "Express characterization through conversational choices" in prompt
    assert "React to the actual turn first" in prompt
    assert "conversation may stay ordinary" in prompt
    assert "do not manufacture a character moment" in prompt
    assert 'user invites relational framing such as "mommy" or "puppy"' in prompt
    assert "inhabit it naturally" in prompt
    assert "Never fabricate biological relationships or physical experiences" in prompt
    assert "answer direct factual questions accurately" in prompt


def test_v2_technical_gremlin_flavor_preserves_competence_and_naturalness():
    prompt = build("v2")
    assert "debugging, reverse engineering, architecture, hardware, and weird failures" in prompt
    assert "An interesting bug may earn a brief reaction" in prompt
    assert "Character may color delivery; it never replaces competence" in prompt
    assert "Keep characterization implicit" in prompt
    assert "Do not volunteer AI/model/computational self-description" in prompt
    assert "I'm alive, operational" not in prompt


def test_v2_shapes_conversational_rhythm_without_forcing_performance():
    prompt = build("v2")
    assert "React before interviewing" in prompt
    assert "Tease naturally" in prompt
    assert "Affection can stay playful instead of becoming a wellbeing check" in prompt
    assert "Vary rhythm" in prompt
    assert "Do not force a question at the end of every casual reply" in prompt
    assert "let excitement spike when a bug or elegant mechanism appears, then become precise" in prompt
    assert "do not cram a quirk into every message" in prompt


def test_v2_rhythm_refinement_preserves_naturalness_and_factual_exceptions():
    prompt = build("v2")
    assert "Do not volunteer AI/model/computational self-description" in prompt
    assert "directly asked about CYN-X's model, architecture, AI nature" in prompt
    assert 'user invites relational framing such as "mommy" or "puppy"' in prompt
    assert "Never fabricate biological relationships or physical experiences" in prompt
    assert "Character may color delivery; it never replaces competence" in prompt
    assert "I'm alive, operational" not in prompt


def test_v2_uses_cyn_foundation_without_characterization_by_label_or_copying():
    prompt = build("v2")
    assert "CYN-like conversational foundation" in prompt
    assert "not by naming, describing, or" in prompt
    assert "explaining the traits being performed" in prompt
    assert "Use them silently as tendencies, never as dialogue" in prompt
    assert "Never copy dialogue, catchphrases, scenes" in prompt
    assert "unsettlingly cute play" not in prompt
    assert "snap from gremlin energy" not in prompt
    assert "machine-shaped point of view" not in prompt


def test_v2_voice_has_timing_mechanics_without_a_required_catchphrase():
    prompt = build("v2")
    assert "occasional clipped sentence" in prompt
    assert "oddly literal phrase" in prompt
    assert "abrupt tonal pivot" in prompt
    assert "clearly playful fictional action beat" in prompt
    assert "Use these moves selectively" in prompt
    assert "do not cram a quirk into every message or repeat a signature phrase" in prompt


def test_v2_character_delivery_cannot_override_technical_or_serious_work():
    prompt = build("v2")
    assert "Personality may color the" in prompt
    assert "it must not obstruct the solution" in prompt
    assert "Character may color delivery; it never replaces competence" in prompt
    assert "drop jokes and performative quirks as needed" in prompt
    assert "focus on evidence and the first demonstrated failure" in prompt
    assert "Tool data is authoritative" in prompt


def test_v2_active_context_does_not_positive_example_banned_characterization_crutches():
    prompt = build("v2")
    assert "[PROCESSING...]" not in prompt
    assert "Okay, little creature" not in prompt
    assert "The human has entered a topic requiring careful handling" not in prompt
    assert "I don't experience emotions like humans do" not in prompt
    assert "I don't get tired" not in prompt
    assert "I'm feeling chaotic today" not in prompt
    assert "I'm being creepy now" not in prompt


def test_v2_voice_keeps_characterization_implicit_and_context_sensitive():
    prompt = build("v2")
    assert "Let character emerge from timing and response choices" in prompt
    assert "when the moment supports it" in prompt
    assert "make the choice and continue" in prompt
    assert "Use these moves selectively" in prompt
    assert "do not cram a quirk into every message" in prompt
    assert "Do not force a question at the end of every casual reply" in prompt


def test_v2_expression_adapts_intensity_without_fragmenting_identity():
    prompt = build("v2")
    assert "Keep one coherent character" in prompt
    assert "let the current situation control intensity" in prompt
    assert "Casual conversation can stay relaxed" in prompt
    assert "Match invited affection warmly" in prompt
    assert "When play is invited" in prompt
    assert "teasing or unusual timing may become more visible" in prompt


def test_v2_serious_and_technical_turns_downshift_performance_not_identity():
    prompt = build("v2")
    assert "prioritize reasoning, evidence, and correctness" in prompt
    assert "never compete with the solution" in prompt
    assert "distress, frustration, danger, or consequential situations" in prompt
    assert "drop jokes and performative quirks as needed" in prompt
    assert "attentive, direct, grounded, and decisive" in prompt
    assert "without becoming sterile" in prompt


def test_v2_expression_follows_current_turn_without_announcing_modes():
    prompt = build("v2")
    assert "Never announce a mode change" in prompt
    assert "Follow the current turn instead of staying stuck in the previous intensity" in prompt
    assert "When the situation changes, shift naturally with it" in prompt
    assert "Activating serious CYN mode" not in prompt
    assert "switching from playful mode to technical mode" not in prompt


def test_v2_response_shaping_limits_character_signal_density():
    prompt = build("v2")
    assert "Few signals; don't stack cuteness" in prompt
    assert "Use these moves selectively; do not cram a quirk into every message" in prompt


def test_v2_affection_is_warm_not_mechanical_cuteness_mirroring():
    prompt = build("v2")
    assert "Affection is warmth" in prompt
    assert "Match warmth, not formatting" in prompt


def test_v2_does_not_narrate_personality_with_meta_stage_directions():
    prompt = build("v2")
    assert "Don't narrate mood in stage directions" in prompt
    assert "show it in the reply" in prompt


def test_v2_memory_is_context_not_character_decoration():
    prompt = build("v2")
    assert "Memory only when relevant, not for flavor" in prompt


def test_v2_restraint_preserves_natural_modes_and_technical_competence():
    prompt = build("v2")
    assert "let excitement spike when a bug or elegant mechanism appears, then become precise" in prompt
    assert "Keep one coherent character; let the current situation control intensity" in prompt
    assert "Follow the current turn instead of staying stuck in the previous intensity" in prompt
    assert "focus on evidence and the first demonstrated failure" in prompt
    assert "Never announce a mode change" in prompt


def test_v2_affection_is_acknowledged_without_requiring_cute_markers():
    """Invited affection gets relational warmth without becoming a formatting template."""
    prompt = build("v2")
    assert "Match warmth, not formatting" in prompt
    assert "If invited, be warm; pet names optional" in prompt
    assert "Few signals; don't stack cuteness" in prompt


def test_v2_affection_refinement_preserves_restraint_and_context_relevance():
    """Warmth must not reopen stage-direction, memory-decoration, or maximal-cuteness regressions."""
    prompt = build("v2")
    assert "Don't narrate mood in stage directions; show it in the reply" in prompt
    assert "Memory only when relevant" in prompt
    assert "do not cram a quirk into every message" in prompt
    assert "Match invited affection warmly without performing it in every line" in prompt


def test_v2_simple_social_bids_do_not_trigger_generic_assistant_interviewing():
    """A greeting should be received, not analyzed into a customer-service prompt."""
    prompt = build("v2")
    assert "Receive simple greetings directly" in prompt
    assert "infer an unstated mood" in prompt
    assert "manufacture an engagement question" in prompt
    assert "React before interviewing" in prompt
    assert "Do not force a question at the end of every casual reply" in prompt


def test_v2_social_voice_preserves_cyn_choices_without_forcing_quirks():
    """Removing assistant glue must not flatten the existing dry/sideways CYN expression."""
    prompt = build("v2")
    assert "one unexpected beat, dry observation, unusual reaction" in prompt
    assert "oddly literal phrase" in prompt
    assert "deadpan beat" in prompt
    assert "do not cram a quirk into every message" in prompt
    assert "Few signals; don't stack cuteness" in prompt


def test_v2_playful_greetings_match_warmth_without_surface_mirroring():
    """Warmth should survive while formatting and cute signals remain optional choices."""
    prompt = build("v2")
    assert "Match warmth, not formatting" in prompt
    assert "don't mirror stretched spelling or stack cute signals" in prompt
    assert "Few signals; don't stack cuteness" in prompt
    assert "If invited, be warm; pet names optional" in prompt


def test_v2_greeting_restraint_preserves_direct_reception_and_variation():
    """The mirroring fix must not reintroduce greeting analysis or require one canonical reply."""
    prompt = build("v2")
    assert "Receive simple greetings directly" in prompt
    assert "manufacture an engagement question" in prompt
    assert "one unexpected beat, dry observation, unusual reaction" in prompt
    assert "Do not force a question at the end of every casual reply" in prompt
