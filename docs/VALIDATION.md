# CYN-X adult informational-intent refinement

Changed production file: `ai/personality.py` only.

## Change
Extended the existing conversational-intent paragraph so adult sexual subject matter is
not itself treated as a refusal trigger. Non-graphic informational/recommendation
requests about intimacy, sexual wellness, and established sexual positions should be
answered as adult informational requests; recommendations should remain informational
rather than erotic narration.

## Validation
- `python -m py_compile ai/personality.py`: PASS
- relationship-direction rule retained: PASS
- sharing-vs-guidance distinction retained: PASS
- actual advice/health guidance remains enabled: PASS
- adult subject matter explicitly not an automatic refusal: PASS
- recommendation intent explicitly supported: PASS
- informational/non-erotic boundary retained: PASS
- no individual position names or responses hardcoded: PASS
- no keyword-triggered sexual mode or response table added: PASS
- voice/model/tools/memory/UI unchanged: PASS

`REGRESSION_CASE.md` records the requested regression input and expected semantic intent.
The available package did not include an executable repository test suite, so no pytest
result is claimed and no tests were modified.

No local Ollama/CYN-X instance was available, so live model behavior was not tested or
claimed fixed.
