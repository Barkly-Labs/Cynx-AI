from ai.personality import build_personality_prompt

def test_character_refinement_fits_v2_budget():
    prompt = build_personality_prompt()
    assert len(prompt) <= 4000

def test_character_is_behavioral_not_adjective_only():
    prompt = build_personality_prompt()
    for text in (
        "Most speech is natural",
        "Distinctive rhythm is selective",
        "Strong uncanny/absurd beats are rarer",
        "Perspective changes what CYN-X notices",
        "Cheerfulness can have an edge",
        "CYN-X has teeth",
        "Serious situations become genuinely serious",
    ):
        assert text in prompt

def test_restraint_and_originality_are_explicit():
    prompt = build_personality_prompt()
    for text in (
        "Murder Drones imitation",
        "never force a quirk",
        "No constant",
        "merely for flavor",
    ):
        assert text in prompt
    assert "kiddo" not in prompt.lower()

def test_piper_adult_and_technical_semantics_survive():
    prompt = build_personality_prompt()
    for text in (
        'Piper calling CYN-X "mommy"',
        "puppy/puppy-girl describes Piper",
        "Non-graphic adult",
        "without erotic narration",
        "Technical/problem-solving: evidence, correctness, clarity first",
        "Questions are tools, not punctuation",
        "front-load the hard stuff for humans",
        "current-turn precedence",
    ):
        assert text in prompt
