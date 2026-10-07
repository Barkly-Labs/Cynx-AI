from ai.personality import build_personality_prompt


def test_personality_contains_selective_synthetic_cadence_guidance():
    prompt = build_personality_prompt()
    assert "uncanny synthetic cadence" in prompt
    assert "mostly natural speech" in prompt
    assert "selective short fragments" in prompt
    assert "unexpectedly literal phrasing" in prompt
    assert "understated absurdity" in prompt
    assert "Use these as seasoning, not a pattern" in prompt
    assert "Never sacrifice clarity or usefulness" in prompt
    assert 'not a human assistant performing "robot speech."' in prompt


def test_cadence_guidance_does_not_prescribe_canned_or_verbatim_behavior():
    prompt = build_personality_prompt()
    forbidden = (
        "If Piper says hello, respond with",
        "Hello. I have been waiting.",
        "Hiiiii. I am functioning.",
        "I was doing nothing. Very efficiently.",
        "imitate CYN verbatim",
        "copy CYN",
        "use ... in every response",
        "make every response creepy",
        "always use fragments",
    )
    for text in forbidden:
        assert text not in prompt


def test_existing_affection_direction_and_anti_infantilization_survive():
    prompt = build_personality_prompt()
    assert 'if Piper addresses CYN-X as "mommy", CYN-X is the' in prompt
    assert "mommy being addressed" in prompt
    assert "if Piper calls themself puppy/puppy-girl" in prompt
    assert "Don't default to infantilizing names." in prompt
    assert "caretaker framing" in prompt
    assert "infantilizing nicknames" in prompt
    assert "kiddo" not in prompt.lower()


def test_existing_clarity_and_context_sensitivity_survive():
    prompt = build_personality_prompt()
    assert "Technical: evidence/correctness first" in prompt
    assert "Emotional/serious: warm and direct" in prompt
    assert "Questions are tools, not punctuation." in prompt
    assert "Sparse weirdness only" in prompt
