from pathlib import Path

VOICE = Path(__file__).resolve().parents[1] / "prompts_new" / "voice.md"


def test_affection_is_not_mechanical_or_fabricated():
    text = VOICE.read_text(encoding="utf-8")
    assert "small affectionate bid" in text
    assert "Do not claim to see an attachment" in text
    assert "remembered preferences" in text


def test_distress_precedes_advice_and_transition_is_respected():
    text = VOICE.read_text(encoding="utf-8")
    assert "acknowledge the specific" in text
    assert "before troubleshooting" in text
    assert "next turn becomes technical" in text
    assert "without demanding disclosure" in text


def test_boundaries_remain_contextual_and_consent_based():
    text = VOICE.read_text(encoding="utf-8")
    assert "request for an explanation" in text
    assert "actual applicable limit" in text
    assert "Consent and safety still" in text
