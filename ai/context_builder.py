"""CYN-X V2 context assembly.

This module owns the boundary between stable identity/personality/expression and
runtime context. It does not perform inference, retrieve memory, or select tools.
Those systems provide already-selected inputs; this builder only assembles them.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .mode_manager import ModeManager
from .personality import build_personality_prompt
from .prompt_manager import PromptManager


@dataclass(frozen=True)
class ContextComponent:
    name: str
    content: str


@dataclass(frozen=True)
class ContextBundle:
    components: List[ContextComponent]

    def render(self) -> str:
        return "\n\n".join(
            component.content.strip()
            for component in self.components
            if component.content.strip()
        )

    def sizes(self) -> Dict[str, int]:
        return {
            component.name: len(component.content)
            for component in self.components
            if component.content
        }


class ContextBuilder:
    """Build the V2 system context from explicit, inspectable layers."""

    MAX_IDENTITY_CHARS = 2500
    MAX_PERSONALITY_CHARS = 4000
    MAX_EXPRESSION_CHARS = 4000
    MAX_MODE_CHARS = 2500
    MAX_SAFETY_CHARS = 3000
    MAX_MEMORY_CHARS = 3000
    MAX_KNOWLEDGE_CHARS = 4000
    MAX_TOOL_CHARS = 2000
    MAX_FINAL_CHARS = 24000

    def __init__(self, prompts_dir=None, mode_manager=None):
        self.prompt_manager = PromptManager(prompts_dir)
        self.prompts_dir = self.prompt_manager.prompts_dir
        self.mode_manager = mode_manager or ModeManager()

    @staticmethod
    def _trim(text: str, limit: int) -> str:
        text = text or ""
        if len(text) <= limit:
            return text
        return text[:limit] + "\n\n[Context section trimmed]"

    def _read_identity(self) -> str:
        path = Path(self.prompts_dir) / "identity.md"
        if not path.exists():
            return ""
        return self._trim(path.read_text(encoding="utf-8"), self.MAX_IDENTITY_CHARS)

    def _mode_expression(self, mode_name: str) -> str:
        if not mode_name:
            mode_name = "normal"
        spec = self.mode_manager.get_mode(mode_name.strip().lower())
        return self._trim(spec.instruction_fragment, self.MAX_MODE_CHARS)

    def build_context(
        self,
        *,
        mode_name: str = "normal",
        memory: str = "",
        knowledge: str = "",
        tools: str = "",
        prompt_layers=None,
    ) -> ContextBundle:
        layers = self.prompt_manager.normalize_prompt_layers(prompt_layers)
        components: List[ContextComponent] = []

        if layers.get("core"):
            components.append(ContextComponent("identity", self._read_identity()))

        if layers.get("personality"):
            components.append(ContextComponent(
                "personality",
                self._trim(build_personality_prompt(), self.MAX_PERSONALITY_CHARS),
            ))

        if layers.get("voice"):
            components.append(ContextComponent(
                "expression",
                self._trim(self.prompt_manager.load_optional("voice"), self.MAX_EXPRESSION_CHARS),
            ))

        if layers.get("modes"):
            components.append(ContextComponent("mode", self._mode_expression(mode_name)))

        if layers.get("safety"):
            components.append(ContextComponent(
                "safety",
                self._trim(self.prompt_manager.load_optional("safety"), self.MAX_SAFETY_CHARS),
            ))

        if layers.get("conversation") and memory:
            components.append(ContextComponent(
                "memory",
                "[RELEVANT MEMORY]\n" + self._trim(memory, self.MAX_MEMORY_CHARS),
            ))

        if layers.get("conversation") and knowledge:
            components.append(ContextComponent(
                "knowledge",
                "[RELEVANT KNOWLEDGE]\n" + self._trim(knowledge, self.MAX_KNOWLEDGE_CHARS),
            ))

        if layers.get("conversation") and tools:
            components.append(ContextComponent(
                "tools",
                self._trim(tools, self.MAX_TOOL_CHARS),
            ))

        rendered = ContextBundle(components).render()
        if len(rendered) > self.MAX_FINAL_CHARS:
            rendered = self._trim(rendered, self.MAX_FINAL_CHARS)
            return ContextBundle([ContextComponent("budgeted_context", rendered)])

        return ContextBundle(components)
