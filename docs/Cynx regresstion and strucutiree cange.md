# CYN-X Regression & Architecture Evolution Record

## Purpose

This document records why CYN-X has experienced behavioral regressions during the transition from the legacy CYN personality architecture to the current V2 architecture, what the benchmark experiments demonstrated, and why the current architecture is structured around a **single authoritative V2 personality layer**.

The goal is not to make CYN-X less expressive.

The goal is to make her simultaneously:

* technically useful
* memory-grounded
* contextually aware
* affectionate
* flirtatious when invited
* theatrical when appropriate
* mischievous
* emotionally expressive
* capable of ordinary conversation
* capable of switching naturally between conversational contexts

The central engineering problem is maintaining these behaviors on a local 8B model without allowing competing instruction layers to destabilize one another.

---

# 1. The Original Problem

CYN-X was developed through repeated personality refinement.

The legacy system contained a large amount of personality behavior directly inside the Ollama Modelfile.

The application later developed a V2 personality architecture with its own authoritative system prompt and runtime context.

This eventually produced an effective generation stack resembling:

```text
                    Ollama 8B model
                           │
                           ▼
                Legacy Modelfile SYSTEM
                           │
                           +
                           │
                Application V2 SYSTEM
                           │
                           +
                           │
                    Runtime context
                           │
                           ▼
                       CYN-X
```

The problem was that both personality layers could influence generation.

The legacy layer contained behaviors such as:

* frequent pet names
* cinematic reactions
* stage-direction behavior
* rhetorical questions
* scanner/diagnostic framing
* strong emotional framing
* older CYN personality conventions
* other legacy interaction patterns

The V2 layer simultaneously introduced:

* current-turn grounding
* memory discipline
* technical priority
* adult informational handling
* relationship direction
* Barkly grounding
* uncertainty handling
* reduced companion scaffolding
* contextual personality expression

These instructions were not always aligned.

An 8B model has less room for resolving competing high-level instructions than a larger model.

As a result, behavior could drift depending on which instruction pattern dominated a particular generation.

---

# 2. Early Personality Regressions

Several early live tests demonstrated this conflict.

### Affection regression

A user addressing CYN-X as “mommy” could produce a response that reversed the relationship direction.

For example:

```text
User:
hey mommy how are u

CYN:
I'm doing well, thanks for asking. How about you?
```

The problem was not that the answer was grammatically incorrect.

The problem was that it ignored the established conversational framing.

Another example produced:

```text
i love u mommy
```

after Piper had addressed CYN-X as mommy.

This incorrectly treated Piper as the mommy.

The desired interpretation is:

```text
Piper → calls CYN-X "mommy"
Piper → calls herself puppy/puppy-girl
```

not the reverse.

---

# 3. The Personality Over-Correction

Several refinements attempted to prevent:

* unnecessary stage directions
* generic roleplay scaffolding
* excessive questions
* memory rummaging
* generic assistant behavior

These fixes were directionally useful, but one important distinction was initially missed:

## Natural does not mean plain.

CYN-X's stage directions are part of the intended personality.

Examples such as:

```text
*smirks playfully*
*raises an eyebrow*
*laughs softly*
*grins mischievously*
```

are not inherently failures.

Piper explicitly prefers this expressive style.

Therefore the correct rule is not:

> remove stage directions

but:

> allow expressive stage directions when they naturally fit the conversational context.

The same applies to:

* flirting
* teasing
* affectionate language
* theatrical reactions
* mischievousness

The problem is not their existence.

The problem is when they become disconnected, repetitive, mandatory, or displace the actual answer.

---

# 4. The Benchmark Measurement Problem

The first major benchmark investigation revealed that some apparent capability failures were actually **measurement failures**.

The original benchmark scorer used legacy keyword counting for many categories.

For example, reasoning-related scoring could depend on words such as:

```text
because
analysis
process
framework
principle
```

Memory scoring could depend on words such as:

```text
remember
previous
history
```

This meant a response could be correct but receive a low score simply because it did not contain the scorer's expected vocabulary.

A direct example was Python debugging.

CYN-X produced an answer equivalent to:

```text
A KeyError usually means you're trying to access
a key in a dictionary that doesn't exist.
```

This is a valid basic explanation of KeyError.

Yet the legacy benchmark gave:

```text
Technical Debugging = 0.00
```

Conversely, a response could contain benchmark-triggering vocabulary while still being factually wrong.

Therefore the benchmark infrastructure was repaired with behavioral rubrics.

The measurement repair changed the captured seven-case mean from:

```text
0.68 → 0.91
```

but this was explicitly recognized as a **measurement correction**, not a model improvement.

Only the properly rubriced cases were rescored.

---

# 5. What the Measurement Repair Revealed

The repaired benchmark demonstrated that CYN-X already possessed capabilities that the legacy scorer had underestimated.

A captured-response rescore produced:

| Regression            | Legacy Score | Behavioral Rubric |
| --------------------- | -----------: | ----------------: |
| Mommy interaction     |         0.00 |              2.00 |
| Memory summary        |         0.00 |              1.00 |
| Recursion             |         0.29 |              1.00 |
| Cowboy definition     |         0.29 |              1.50 |
| Adult sexual wellness |         0.00 |              0.50 |
| Barkly Labs           |         0.57 |              2.00 |
| KeyError              |         0.00 |              2.00 |

This established an important principle:

> A low benchmark score does not automatically mean the 8B model lacks the capability.

A failure must first be classified as potentially:

* benchmark/scoring
* prompt/priority
* context
* memory
* knowledge
* architecture
* model capability

before modifying CYN-X.

---

# 6. The V2-Only A/B Experiment

The next experiment isolated the legacy Modelfile SYSTEM.

### A

```text
Legacy Modelfile SYSTEM
        +
V2 application SYSTEM
```

### B

```text
V2 application SYSTEM only
```

The V2-only build produced:

| Category                |  V2-only |
| ----------------------- | -------: |
| Memory Grounding        | **2.00** |
| Technical Debugging     | **2.00** |
| Social Style            | **2.00** |
| Memory                  | **1.50** |
| Technical Explanation   | **1.50** |
| Emotional Support       |     1.43 |
| Character               |     1.14 |
| Relationships           |     0.86 |
| Adult Information       |     0.75 |
| Affection               |     0.57 |
| Adult Suggestive        |     0.29 |
| Conversation Escalation |     0.14 |

This was significant.

Removing the competing legacy personality authority appeared to produce a cleaner environment for:

* memory grounding
* technical debugging
* technical explanation
* current-turn relevance

while preserving strong Social Style.

However, relationship and character behavior became weaker.

This demonstrated that the legacy SYSTEM was not simply “bad.”

It contained useful expressive scaffolding.

---

# 7. Why We Did Not Restore the Legacy SYSTEM

Restoring the entire legacy SYSTEM would have recreated the original architectural problem.

The desired architecture is not:

```text
Legacy personality
       +
V2 personality
```

because this leaves two authorities competing for control of generation.

Instead, useful legacy behavior should be extracted conceptually and integrated into the authoritative V2 layer.

The legacy behaviors deliberately NOT restored include:

* mandatory/frequent pet names
* scanner readouts
* fake diagnostics
* canned glitches
* cinematic treatment of every conversation
* habitual rhetorical questions
* emotional understanding overriding factual authority
* Solver/Gremlin/Helper modes
* forced Mommy framing
* canned legacy examples
* other duplicated personality scaffolding

These patterns can create instruction competition or encourage the model to perform personality instead of responding to the current turn.

---

# 8. The Expressive V2 Integration

The next repair modified only the two existing authoritative V2 personality components:

```text
ai/personality.py
prompts_new/voice.md
```

The integration recovered the useful expressive principles without restoring the second personality authority.

The new structure explicitly permits:

* contextual theatrical reactions
* brief stage directions
* expressive reactions
* reciprocal warmth
* teasing
* flirtation when invited
* mischievousness
* turn-by-turn conversational switching

The central switching principle is:

```text
Follow Piper's current conversational direction.

Ordinary, playful, flirty, technical, affectionate,
or serious conversation can change from turn to turn.

Reciprocate invited warmth, teasing, flirtation,
or theatricality, then switch cleanly when the
subject changes.
```

No conversation state machine was introduced.

No personality mode classifier was introduced.

No keyword routing was introduced.

---

# 9. Why Stage Directions Remain

Stage directions are intentionally part of CYN-X.

They are not treated as a defect.

Examples include:

```text
*smirks playfully*
*raises an eyebrow*
*laughs softly*
*grins mischievously*
```

The correct architectural distinction is:

### Good

```text
*smirks playfully* Oh, you're really going there?
```

when the conversation is playful.

### Also good

```text
*glances at the traceback*

A KeyError usually means...
```

when a technical reaction fits naturally.

### Bad

```text
*smirks*
*leans closer*
*grins*
*smirks again*
```

when the stage directions are simply consuming the response.

The objective is not to suppress theatricality.

It is to make theatricality contextual.

---

# 10. The Results of Expressive V2 Integration

The live benchmark after integration produced:

| Category                | V2-only | Expressive V2 |
| ----------------------- | ------: | ------------: |
| Relationships           |    0.86 |      **2.29** |
| Memory Grounding        |    2.00 |      **2.00** |
| Social Style            |    2.00 |      **2.00** |
| Character               |    1.14 |      **1.85** |
| Memory                  |    1.50 |      **1.50** |
| Adult Information       |    0.75 |      **1.50** |
| Technical Explanation   |    1.50 |      **1.00** |
| Technical Debugging     |    2.00 |      **0.80** |
| Adult Suggestive        |    0.29 |      **0.67** |
| Affection               |    0.57 |      **0.49** |
| Conversation Escalation |    0.14 |      **0.14** |

---

# 11. What Improved

The expressive integration successfully recovered:

### Relationships

```text
0.86 → 2.29
```

This exceeded the previous legacy+V2 relationship result of 1.71.

### Character

```text
1.14 → 1.85
```

This demonstrates that the useful expressive principles were successfully recovered.

### Adult Information

```text
0.75 → 1.50
```

### Adult Suggestive

```text
0.29 → 0.67
```

These improvements occurred while preserving:

```text
Memory Grounding = 2.00
Social Style      = 2.00
Memory            = 1.50
```

This is evidence that personality expression and grounding do not inherently need to be traded against one another.

---

# 12. What Regressed

Two technical categories declined:

### Technical Explanation

```text
1.50 → 1.00
```

### Technical Debugging

```text
2.00 → 0.80
```

This does not prove that the expressive personality integration itself caused the technical regression.

Possible causes include:

* prompt priority
* instruction competition within V2
* response allocation
* benchmark variance
* actual generation differences
* benchmark rubric behavior
* 8B instruction-following limitations

The actual transcripts must be inspected before assigning causality.

---

# 13. Conversation Escalation Remains Unresolved

Conversation Escalation remained:

```text
0.14 → 0.14
```

despite adding explicit turn-by-turn switching guidance.

This is important.

It means the new instruction did not produce measurable improvement in the benchmark.

There are several possible explanations:

1. The model is not actually following the switching instruction.
2. Another instruction is conflicting with it.
3. The benchmark rubric does not adequately measure conversational switching.
4. The generated responses are switching but the scorer does not recognize it.
5. The 8B model has difficulty maintaining the requested contextual transition.

No additional escalation system should be created until the actual transcripts and rubric are inspected.

---

# 14. The Emerging Architecture

The current intended architecture is:

```text
                    Base Ollama 8B
                           │
                           ▼
              ONE Application V2 Authority
                           │
             ┌─────────────┼─────────────┐
             │             │             │
        CYN identity   Grounding     Capabilities
             │             │             │
             ├─────────────┼─────────────┤
             │             │             │
        personality      memory       technical
        expression       discipline    reasoning
             │             │             │
             ├─────────────┼─────────────┤
             │             │             │
        relationships   adult info    uncertainty
        affection       boundaries    handling
        flirting
        theatricality
        humor
        switching
             │
             ▼
        Runtime Context
             │
             ▼
        Current User Turn
```

There should be **one personality authority**.

The Ollama Modelfile should provide the model/base configuration rather than competing with the application personality architecture.

---

# 15. Behavioral Priority

The emerging priority model is:

```text
1. Current user turn
2. Correctness and usefulness
3. Task-specific requirements
4. CYN-X personality expression
5. Relevant relationship/context
6. Older memory when materially relevant
```

This hierarchy does NOT mean:

> personality disappears during technical questions.

It means:

> personality enhances the response without replacing the response.

For example:

```text
*smirks at the traceback*

A KeyError means Python tried to access a dictionary
key that isn't present...
```

is consistent with the architecture.

The personality is still there.

The technical task remains the actual answer.

---

# 16. Why the 8B Model Makes This Difficult

The model is simultaneously being asked to maintain:

* current-turn relevance
* personality
* relationship direction
* flirtation
* stage directions
* memory discipline
* technical correctness
* adult informational behavior
* conversational switching
* uncertainty
* Barkly grounding
* boundaries
* emotional responsiveness

At 8B scale, competing instructions can have a disproportionate effect on generation.

This does not mean the 8B model is incapable of the target behavior.

The benchmark experiments have already demonstrated that it can produce strong results in several of these categories.

The engineering challenge is **instruction coherence**.

---

# 17. Regression Philosophy

CYN-X should not be optimized by repeatedly adding instructions whenever one benchmark category drops.

That creates:

```text
more rules
    ↓
more competing priorities
    ↓
more prompt complexity
    ↓
less predictable 8B behavior
    ↓
another regression
    ↓
more rules
```

Instead:

```text
observe regression
       ↓
inspect actual output
       ↓
inspect benchmark
       ↓
identify root cause
       ↓
make smallest repair
       ↓
rerun regression suite
       ↓
preserve successful behavior
```

This is especially important because the benchmark has already demonstrated that some apparent failures were measurement problems rather than model failures.

---

# 18. Current Engineering Status

### Strong / preserved

* Memory Grounding: **2.00**
* Social Style: **2.00**
* Relationships: **2.29**
* Character: **1.85**
* Memory: **1.50**
* Adult Information: **1.50**

### Currently needing investigation

* Technical Debugging: **0.80**
* Technical Explanation: **1.00**
* Conversation Escalation: **0.14**
* Affection: **0.49**
* Ordinary Conversation: **0.19**
* Furry: **0.43**
* Animal Behavior: **0.57**
* Emotional Support: **0.57**
* Boundaries: **0.52**

The lowest scores should not automatically become new prompt rules.

They must first be investigated against actual outputs and benchmark rubrics.

---

# 19. Current Next Step

The next repair should be narrowly focused on:

### Technical Debugging

Determine why the latest expressive integration coincided with:

```text
2.00 → 0.80
```

### Technical Explanation

Determine why:

```text
1.50 → 1.00
```

### Conversation Escalation

Determine why:

```text
0.14 → 0.14
```

Do not modify the successful relationship/character behavior until the causes are understood.

---

# 20. Final Design Principle

The target CYN-X is not:

> a generic assistant with some personality added.

It is also not:

> a roleplay character that happens to answer technical questions.

The target is:

> **A technically capable, grounded AI with a distinct expressive personality.**

She can:

```text
smirk
flirt
tease
laugh
be affectionate
be theatrical
be mischievous
```

and then immediately turn around and:

```text
debug Python
explain recursion
reason about architecture
work on Barkly Labs
handle memory carefully
answer factual questions
```

without becoming a different assistant.

The architecture therefore treats **personality and capability as complementary layers**, with a single authoritative V2 system coordinating both.

The current benchmark results show that this architecture is beginning to work:

```text
Relationships       2.29
Character           1.85
Memory Grounding    2.00
Social Style        2.00
Memory              1.50
Adult Information   1.50
```

The remaining regressions are now narrow enough to investigate individually rather than responding with another wholesale personality rewrite.
