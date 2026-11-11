# CYN-X Model Architecture Decision

## Why CYN-X Could Not Follow the Standard Dolphin Path

**Barkly Labs**
**Project:** CYN-X
**Document Type:** Architecture Decision Record
**Status:** Accepted
**Date:** October 2026

---

## 1. Executive Summary

CYN-X initially explored the Dolphin model family as a practical foundation for a local, steerable AI system.

Dolphin was valuable because it demonstrated several properties that were important to CYN-X:

* local execution;
* strong system-prompt steerability;
* coding capability;
* conversational capability;
* reduced refusal behavior;
* compatibility with Ollama and other local inference runtimes;
* the ability to run without sending user conversations to a hosted AI provider.

However, CYN-X eventually encountered a fundamental architectural problem:

> **Using Dolphin as the model itself was not the same thing as owning the behavior, architecture, evaluation process, or long-term direction of CYN-X.**

Dolphin is a community fine-tune built on top of another foundation model. Dolphin 3.0 Llama 3.1 8B is based on Meta's Llama 3.1 8B and is trained using multiple instruction, coding, mathematics, and function-calling datasets.

That makes Dolphin an excellent *component to experiment with*, but it does not automatically provide the level of control that CYN-X ultimately requires.

CYN-X therefore moved toward a more controlled architecture in which the model is treated as one component of a larger human-centered AI system rather than being treated as the entire AI product.

---

# 2. What We Originally Wanted

The original goal was straightforward:

> Run a capable local model, give it a CYN-X system prompt, connect it to local tools, and build the rest of the system around it.

Dolphin appeared attractive because it was explicitly designed for local use and advertised as a general-purpose model capable of coding, mathematics, agentic tasks, function calling, and general conversation.

The normal architecture looked approximately like this:

```text
User
  ↓
CYN-X application
  ↓
Ollama
  ↓
Dolphin
  ↓
Response
```

This is extremely useful for a prototype.

It is also where the limitations begin to matter.

---

# 3. Dolphin Was Not the Problem

It is important to document this correctly.

**Dolphin was not a failure.**

It solved an important problem for CYN-X:

> It demonstrated that a locally running model could be significantly more steerable than the heavily constrained hosted assistants we were originally trying to reproduce.

Dolphin's model documentation explicitly describes its goal as a general-purpose local model and emphasizes system-prompt control.

The problem was not:

> "Dolphin doesn't work."

The problem was:

> "Dolphin works, but using it as the permanent foundation of CYN-X creates constraints that become increasingly important as CYN-X grows."

That distinction matters.

---

# 4. The First Limitation: CYN-X Does Not Own the Base Model

Dolphin 3.0 Llama 3.1 8B is a fine-tuned version of Llama 3.1 8B.

The resulting dependency chain is therefore approximately:

```text
Meta
  ↓
Llama 3.1
  ↓
Dolphin training
  ↓
Dolphin release
  ↓
Ollama packaging
  ↓
CYN-X
```

This creates multiple external dependencies.

CYN-X does not control:

* the original foundation model;
* the original tokenizer;
* the original pretraining;
* Dolphin's training data;
* Dolphin's fine-tuning process;
* Dolphin's release schedule;
* future Dolphin variants;
* future upstream changes.

For an experiment, this is acceptable.

For infrastructure intended to become a long-lived open project, it becomes a strategic limitation.

---

# 5. System Prompts Are Not the Same as Model Behavior

One of the most important discoveries was that a system prompt provides **behavioral steering**, not complete behavioral ownership.

Dolphin explicitly supports system-prompt customization. Its model documentation even demonstrates changing the system prompt to define the model's role.

That is useful, but CYN-X requires more than:

```text
You are CYN-X.
You should behave like X.
```

A system prompt does not give us complete control over:

* learned associations;
* latent behavior;
* instruction-following tendencies;
* refusal tendencies;
* hallucination patterns;
* coding habits;
* reasoning tendencies;
* biases inherited from training;
* representation of concepts;
* failure modes.

The system prompt is an interface.

It is not ownership of the underlying model.

---

# 6. "Uncensored" Does Not Mean "Uncontrolled"

Dolphin is commonly described as an uncensored model. The Ollama model listing describes Dolphin Llama 3 as uncensored and notes that its dataset was filtered to remove alignment and bias, making it more compliant.

That property was useful during experimentation.

However:

> **Removing refusals is not equivalent to creating a human-centered AI architecture.**

CYN-X does not want "no rules."

CYN-X wants:

* user autonomy;
* transparent behavior;
* explicit safety boundaries;
* privacy;
* predictable tool behavior;
* human override;
* inspectable systems;
* evidence-based decisions;
* non-manipulative interaction.

Those requirements cannot be reduced to whether a model refuses or complies with a prompt.

This became one of the central architectural lessons of the project.

---

# 7. The "Normal Dolphin Path" Encourages the Wrong Abstraction

The conventional approach is:

```text
Pick model
    ↓
Write system prompt
    ↓
Connect tools
    ↓
Build application
```

CYN-X needs something closer to:

```text
Human requirements
       ↓
Behavior specification
       ↓
Safety + autonomy constraints
       ↓
Evaluation
       ↓
Model
       ↓
Runtime
       ↓
Tools
       ↓
Evidence
       ↓
Human-visible result
```

The model is therefore **not the whole system**.

It is one component.

This is much closer to what Barkly Labs means by:

> **"Can we make computers front-load the hard stuff for humans?"**

The engineering effort should happen around the model, rather than assuming that selecting

## Lama 3 works 
1. shipped this model because it still  till worked  because of ram usage
