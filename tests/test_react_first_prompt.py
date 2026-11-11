from ai.personality import build_personality_prompt

def test_react_first_precedes_generic_pleasantry():
    prompt = build_personality_prompt()
    assert "REACT first" in prompt
    assert "stock assistant pleasantry" in prompt
    assert "lead with CYN-X's reaction" in prompt
    assert "personality be present from the first beat" in prompt

def test_behavioral_preference_not_canned_greeting():
    prompt = build_personality_prompt()
    assert "hey mommy how are u today" not in prompt
    assert "I'm doing well, thanks for asking" not in prompt
    assert "How can I help you today" not in prompt
    assert "If Piper says" not in prompt

def test_existing_character_constraints_survive_and_fit_budget():
    prompt = build_personality_prompt()
    assert len(prompt) <= 4000
    for text in (
        "Perspective changes what CYN-X notices",
        "Stronger uncanny/absurd beats are rarer",
        "Cheerfulness can have an edge",
        "CYN-X has teeth",
        'Piper calling CYN-X "mommy"',
        "puppy/puppy-girl describes Piper",
        "Non-graphic adult",
        "Technical/problem-solving: evidence, correctness, clarity first",
        "current-turn precedence",
    ):
        assert text in prompt
    assert "kiddo" not in prompt.lower()
