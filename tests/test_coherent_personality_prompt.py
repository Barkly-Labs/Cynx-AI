from ai.personality import build_personality_prompt


def test_prompt_has_coherent_emotional_range_and_contextual_teeth():
    prompt = build_personality_prompt()
    for text in (
        "one coherent emotional range",
        "smug, sarcastic, blunt",
        "playfully mean",
        "Keep the teeth contextual",
        "stop escalating when the",
        "situation is genuinely serious",
    ):
        assert text in prompt


def test_flirting_remains_cyn_specific_and_not_generic():
    prompt = build_personality_prompt()
    for text in (
        "Flirting and affection should still sound like CYN-X",
        "generic flirty chatbot",
        "Reciprocate",
        "without making every affectionate turn sexual",
        "pet-name-heavy",
    ):
        assert text in prompt


def test_existing_cadence_affection_direction_and_restraint_survive():
    prompt = build_personality_prompt()
    assert "uncanny synthetic cadence" in prompt
    assert "Use these as seasoning, not a pattern" in prompt
    assert 'if Piper addresses CYN-X as "mommy"' in prompt
    assert "if Piper calls themself puppy/puppy-girl" in prompt
    assert "Don't default to infantilizing names." in prompt
    assert "Sparse weirdness only" in prompt
    assert "kiddo" not in prompt.lower()


def test_no_modes_canned_lines_or_mandatory_character_performance_added():
    prompt = build_personality_prompt()
    forbidden = (
        "flirty_mode",
        "mean_mode",
        "uncanny_mode",
        "If Piper says",
        "always flirt",
        "always insult",
        "always use ellipses",
        "always use fragments",
        "imitate CYN verbatim",
        "copy CYN's dialogue",
        "HAHAHAHA CHAOS GREMLIN",
    )
    for text in forbidden:
        assert text not in prompt
