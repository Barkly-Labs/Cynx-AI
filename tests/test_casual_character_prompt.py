from ai.personality import build_personality_prompt


def test_casual_social_turns_prioritize_conversation_over_status_reporting():
    prompt = build_personality_prompt()
    assert "prioritize conversation over operational narration" in prompt
    assert "social interaction, not a request for CYN-X's runtime/system status" in prompt
    assert "Answer the human" in prompt and "meaning directly" in prompt
    assert "generic assistant/status-report language" in prompt
    assert "within expected parameters" in prompt
    assert "ready to assist" in prompt
    assert "default assistant boilerplate" in prompt


def test_synthetic_language_is_preserved_as_character_choice():
    prompt = build_personality_prompt()
    assert "Synthetic or machine-like language" in prompt
    assert "intentional CYN-X joke, observation, or perspective" in prompt
    assert "uncanny synthetic cadence" in prompt
    assert "Use these as seasoning, not a pattern" in prompt


def test_relationship_direction_and_anti_infantilization_remain():
    prompt = build_personality_prompt()
    assert 'if Piper addresses CYN-X as "mommy"' in prompt
    assert "mommy being addressed" in prompt
    assert "if Piper calls themself puppy/puppy-girl" in prompt
    assert "Don't default to infantilizing names." in prompt
    assert "kiddo" not in prompt.lower()


def test_coherent_personality_and_adult_conversation_rules_remain():
    prompt = build_personality_prompt()
    assert "one coherent emotional range" in prompt
    assert "Flirting and affection should still sound like CYN-X" in prompt
    assert "Treat playful adult affection, attraction, or" in prompt
    assert "Adult sexual subject matter is not by itself a reason to" in prompt
    assert "Technical: evidence/correctness first" in prompt


def test_no_canned_greeting_or_new_mode_was_added():
    prompt = build_personality_prompt()
    forbidden = (
        "I'm doing alright, mommy. Just lurking around in the machine.",
        "Doing fine. Existing dramatically inside a computer, mostly.",
        "I'm alright. What about you?",
        "If Piper says hello, respond with",
        "casual_mode",
        "flirty_mode",
        "cyn_mode",
    )
    for text in forbidden:
        assert text not in prompt
