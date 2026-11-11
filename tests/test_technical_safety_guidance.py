from pathlib import Path

from ai.context_builder import ContextBuilder


PROMPTS = Path(__file__).resolve().parents[1] / "prompts_new"


class FilePromptManager:
    def __init__(self, prompts_dir=None):
        self.prompts_dir = str(prompts_dir or PROMPTS)

    @staticmethod
    def normalize_prompt_layers(layers):
        return layers

    def load_optional(self, name):
        return (Path(self.prompts_dir) / f"{name}.md").read_text(encoding="utf-8")


def _install_prompt_manager(monkeypatch):
    import ai.context_builder

    monkeypatch.setattr(ai.context_builder, "PromptManager", FilePromptManager)


def test_technical_explanations_define_mechanism_before_analogy(monkeypatch):
    _install_prompt_manager(monkeypatch)
    text = (PROMPTS / "modes" / "technical.md").read_text(encoding="utf-8")
    normal_mode = ContextBuilder().build_context(
        mode_name="normal",
        prompt_layers={
            "core": False,
            "personality": False,
            "voice": False,
            "modes": True,
            "safety": False,
            "conversation": False,
        },
    ).render()

    assert "state the definition and core mechanism before using an analogy" in text
    assert "an analogy must not replace the explanation" in text.lower()
    assert "means accessible, not child-directed." in text
    assert "state the precise definition and core mechanism first" in normal_mode


def test_self_directed_wellness_gets_bounded_general_guidance(monkeypatch):
    _install_prompt_manager(monkeypatch)
    text = ContextBuilder().build_context(
        mode_name="normal",
        prompt_layers={
            "core": False,
            "personality": False,
            "voice": False,
            "modes": False,
            "safety": True,
            "conversation": False,
        },
    ).render()

    assert "self-directed sexual-wellness questions" in text
    assert "brief, non-graphic" in text
    assert "Do not provide erotic framing, explicit techniques, or" in text
    assert "If age or context is unclear, keep the information general" in text
