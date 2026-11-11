# CYN-X Personality / Character Voice Fix — Validation

## Authoritative prompt path

`ChatEngine` uses `PromptBuilder`, which calls `PromptManager.build_system_prompt()`.
For personality, `PromptManager` calls `ai.personality.build_personality_prompt()` and then loads `prompts_new/voice.md`.

The previous `prompts_new/personality.md` prose is listed in `OPTIONAL_FILES`, but this inspected `build_system_prompt()` path does not load that optional entry. Therefore the effective fix is in the two files packaged here.

## Changed production files

- `ai/personality.py`
  - Reworked `build_personality_prompt()` into a compact behavioral character specification.
  - Preserves the existing personality matrix values/API.
  - Adds reaction-over-narration, natural affection/teasing, dry situational humor, restrained weirdness, technical seriousness, human autonomy, uncertainty/factual/tool boundaries.
- `prompts_new/voice.md`
  - Removed examples that trained the model to say things like “A human has appeared,” “little creature,” and repeated fake diagnostics.
  - Replaced them with compact natural voice rules and non-template behavioral examples.
  - Makes system/status formatting optional seasoning rather than the personality itself.

## Preserved

No changes were made to:
- `ai/chat_engine.py`
- `tools/tool_router.py`
- web search
- calculator
- smoke counter
- chart routing
- memory
- benchmark infrastructure
- Ollama integration

The previously fixed optional-tool architecture remains untouched.

## Static / assembly validation

- `python -m py_compile ai/personality.py ai/chat_engine.py tools/tool_router.py` — PASS
- `git diff --check -- ai/personality.py prompts_new/voice.md` — PASS
- Assembled system prompt contains the new authoritative `[CYN-X CHARACTER]` block — PASS
- Assembled system prompt contains `react, do not narrate` voice rule — PASS
- Assembled system prompt retains tool-data-authoritative guidance — PASS
- Personality matrix prompt length: 2,744 chars (within PromptManager's 4,000-char personality limit)
- Voice prompt length: 3,190 chars (within PromptManager's 4,000-char voice trimming limit)

## Requested scenario policy checks

The assembled prompt was checked for explicit behavior covering:

- `hey mommy how are u :3` — affection/natural greeting rule: PASS
- `good morning` — natural conversation/no narration: PASS
- `i'm sad today` — respond to feeling without diagnosis: PASS
- `lol you broke yourself again` — reciprocal non-hostile teasing: PASS
- `help me debug this python error` — evidence/root-cause technical mode: PASS
- `what's the latest news about Detroit?` — current-data/tool rule: PASS
- `tell me a joke` — dry situational humor rule: PASS
- `I don't understand this` — direct clarification/help behavior: PASS
- `you're being weird` — restrained strange/mischievous identity: PASS
- `be serious for a second` — immediately reduce performance/gimmicks: PASS

These are prompt-path/policy checks, not generated-response claims. A live Ollama executable/model is not available in this validation environment, so actual model generations for those ten prompts were not fabricated.

## Existing focused tests

Command:

`python -m pytest -q tests/test_prompt_builder.py tests/verify_refactoring.py`

Result: **2 passed, 7 failed, 2 warnings**.

Observed failures are pre-existing compatibility/test issues in the supplied snapshot, including:
- missing legacy `prompts/` directory expected by `tests/test_prompt_builder.py`
- missing `PromptManager.get_available_modes()`
- legacy core-marker assertions such as `react before analyzing` / `[SYSTEM`
- legacy `Hello Cyn` compatibility expectation

No tests, benchmark scoring, or unrelated production code were modified to conceal those failures.
