from ai.personality import build_personality_prompt


def test_prompt_adds_selective_synthetic_perspective():
    prompt = build_personality_prompt()
    for text in (
        "synthetic perspective occasionally shape what she notices",
        "ordinary phrase unusually literally",
        "mechanical, biological, spatial, or behavioral detail",
        "mundane as oddly fascinating",
        "inappropriate",
        "calm or cheerfulness",
        "Sometimes the most CYN-X response is completely normal.",
    ):
        assert text in prompt


def test_perspective_is_grounded_and_not_random_creepiness():
    prompt = build_personality_prompt()
    assert "follow from the actual situation" in prompt
    assert "not random creepiness, nonsense" in prompt
    assert "not random creepiness, nonsense, or a requirement to" in prompt.replace("\n", " ") or ("not random creepiness, nonsense" in prompt and "mention machinery/AI" in prompt)
    assert "Sparse weirdness only" in prompt
    assert "Use these as seasoning, not a pattern" in prompt


def test_recent_personality_refinements_remain_present():
    prompt = build_personality_prompt()
    assert "prioritize conversation over operational narration" in prompt
    assert "uncanny synthetic cadence" in prompt
    assert "one coherent emotional range" in prompt
    assert "Flirting and affection should still sound like CYN-X" in prompt
    assert 'if Piper addresses CYN-X as "mommy"' in prompt
    assert "if Piper calls themself puppy/puppy-girl" in prompt
    assert "Don't default to infantilizing names." in prompt
    assert "Technical: evidence/correctness first" in prompt
    assert "kiddo" not in prompt.lower()


def test_no_source_imitation_canned_lines_or_new_modes():
    prompt = build_personality_prompt()
    forbidden = (
        "imitate CYN verbatim",
        "copy dialogue from Murder Drones",
        "imitate CYN",
        "copy CYN",
        "If Piper says",
        "synthetic_mode",
        "uncanny_mode",
        "casual_mode",
        "always be creepy",
        "always mention being an AI",
    )
    for text in forbidden:
        assert text not in prompt
