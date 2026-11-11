# CYN-X Architecture Decision Record

## Why CYN-X Uses the Llama 3 Architecture

**Project:** CYN-X
**Organization:** Barkly Labs
**Decision:** Use a Llama 3-family 8B model as the local foundation for CYN-X
**Status:** Accepted
**Decision type:** Model architecture / deployment architecture

---

## 1. Summary

CYN-X uses a Llama 3-family 8B model as its local language-model foundation.

This decision does **not** mean that Llama 3 is objectively the best language-model architecture available.

Other architectures and models may outperform Llama 3 in particular areas, including reasoning, coding, instruction following, context handling, tool use, or conversational quality.

We chose Llama 3 because it provides a practical combination of:

* local deployability
* manageable memory requirements
* acceptable model capability
* compatibility with the existing CYN-X stack
* ability to run without depending on a cloud inference service
* sufficient capability for personality, conversation, tools, coding assistance, and general interaction
* a model size that can realistically operate on Barkly Labs' available hardware

The architectural goal is not to choose the theoretically strongest model.

The goal is to build a **real, locally running AI companion that Barkly Labs can actually operate, modify, test, and understand.**

---

# 2. What CYN-X Is Optimizing For

CYN-X is not being designed as a benchmark-only language model.

Its purpose is to function as a local AI companion and engineering system with:

* persistent memory
* personality
* conversation history
* contextual reasoning
* optional tools
* web access when appropriate
* calculator capabilities
* project-specific knowledge
* technical assistance
* adult conversational capability
* a local user interface
* recoverable failures
* inspectable software architecture

The underlying model therefore needs to be **good enough across many dimensions**, rather than being maximally optimized for one benchmark.

The model is only one component of CYN-X.

The surrounding architecture provides:

```text
CYN-X
├── Language Model
├── Personality
├── Memory
├── Context Management
├── Tool Routing
├── Tool Execution
├── Conversation State
├── Error Recovery
├── Web Interface
└── Project-Specific Behavior
```

This means the model does not need to independently solve every problem.

The architecture can provide capabilities around the model.

---

# 3. Why Local Inference Matters

One of the most important requirements for CYN-X is that the system can run locally.

Local inference provides several important properties:

### Ownership

Barkly Labs controls the inference environment rather than depending entirely on an external API provider.

### Experimentation

The model can be tested, modified, benchmarked, and integrated with the surrounding system without depending on a remote service.

### Privacy

Conversation and project data can remain within the local environment when the user chooses a local-only configuration.

### Cost control

A local model does not require a per-request API bill for every conversation.

### Engineering transparency

The entire system surrounding the model can be inspected and debugged.

This is particularly important for Barkly Labs because the project is itself an experiment in building humane technology that **front-loads difficult work for humans**.

CYN-X should therefore be something Barkly Labs can actually operate rather than merely consume as a hosted service.

---

# 4. Why Not Simply Use the Largest Available Model?

A larger model can provide better capabilities.

That does not automatically make it a better architecture for CYN-X.

Larger models generally require more:

* RAM
* VRAM
* storage
* compute
* inference time
* power
* infrastructure

CYN-X is being developed on constrained hardware.

The available development environment includes a laptop with approximately 16 GB of system memory.

A model that consumes most of the available memory leaves less room for:

* the operating system
* the CYN-X application
* FastAPI
* the database
* context management
* tool execution
* development tools
* testing
* other applications

The practical question therefore becomes:

> Can the model run while leaving enough resources for the rest of CYN-X?

A theoretically stronger model that makes the entire system unusable is not necessarily the better architecture.

---

# 5. Why We Moved Away From Dolphin 3 8B

Dolphin 3 was experimentally evaluated as a possible foundation.

The problem was not that Dolphin was inherently a bad model.

The problem was resource consumption in the actual CYN-X environment.

The Dolphin 3 8B Q8 model used approximately 8.5 GB of model memory.

On a 16 GB development machine, that created substantial memory pressure.

When the model was loaded, the machine could be left with very little usable memory for the rest of CYN-X and the operating system.

This directly interfered with development and regression testing.

The model therefore became an infrastructure constraint.

The decision was consequently not:

> “Dolphin is bad.”

It was:

> “This model configuration consumes too much of the resources required by the complete CYN-X system.”

That distinction matters.

A model can be excellent in isolation while still being the wrong deployment choice for a particular system.

---

# 6. Why Llama 3 Was a Practical Compromise

The Llama 3-family 8B configuration provides a more manageable local deployment target.

The current CYN-X model is an 8B-class quantized model.

This allows CYN-X to retain substantial language capability while leaving more resources available for the surrounding software.

That makes it possible to run:

* the model
* the CYN-X server
* the web interface
* memory systems
* tool infrastructure
* development tools
* regression tests

within a realistic local environment.

The model therefore becomes a **component of the system instead of consuming the system's entire resource budget.**

---

# 7. Quantization Is Part of the Architecture

CYN-X does not require the model to run at maximum precision.

Quantization allows a capable model to occupy substantially less memory while remaining useful for local inference.

This creates a deliberate tradeoff:

```text
Higher precision
    ↓
Higher memory requirements
    ↓
Potentially higher fidelity
    ↓
Less room for the rest of CYN-X
```

versus:

```text
Quantized model
    ↓
Lower memory requirements
    ↓
Some capability/fidelity tradeoff
    ↓
More resources available to CYN-X
```

For CYN-X, the second tradeoff is currently more useful.

The objective is not maximum theoretical model quality.

The objective is **maximum useful system capability within the available hardware envelope.**

---

# 8. Why an 8B Model Is Interesting for CYN-X

An 8B model occupies an important middle ground.

It is small enough to make local deployment realistic while being large enough to provide meaningful:

* conversation
* reasoning
* coding assistance
* tool interaction
* instruction following
* personality expression
* contextual responses

This is particularly important because CYN-X is not intended to be a single-purpose chatbot.

The model needs to be capable enough to support many different interactions while remaining deployable on relatively modest hardware.

---

# 9. Model Limitations Are an Architectural Constraint, Not a Secret

Choosing Llama 3 also means accepting its limitations.

An 8B local model will not match the strongest current frontier models in every capability.

Possible weaknesses include:

* weaker complex reasoning
* more frequent hallucinations
* weaker long-context behavior
* imperfect tool selection
* occasional malformed tool calls
* less reliable instruction following
* less consistent personality
* weaker performance on difficult coding problems

CYN-X therefore needs surrounding engineering to compensate where appropriate.

Examples include:

* explicit tool contracts
* tool-result handling
* context management
* memory management
* regression tests
* PEG-native recovery
* tool safety checks
* current-turn precedence
* personality architecture
* model benchmarking

The architecture treats the model as a component with strengths and weaknesses rather than assuming the model will behave perfectly.

---

# 10. Why the Architecture Matters as Much as the Model

One of the central lessons from CYN-X development is that a model alone does not determine the experience.

For example, CYN-X has encountered:

* malformed tool-call output
* unnecessary tool selection
* context precedence problems
* memory contamination
* generic assistant behavior
* personality dilution
* resource constraints

These problems cannot all be solved by changing models.

They are **system architecture problems**.

This is why CYN-X deliberately separates concerns:

```text
Model
  ↓
Conversation / Context
  ↓
Personality
  ↓
Tool Selection
  ↓
Tool Execution
  ↓
Tool Results
  ↓
Final Response
```

Each layer can therefore be tested and improved independently.

---

# 11. Why We Are Not Locking CYN-X to Llama Forever

This decision is not permanent.

The architecture should make it possible to replace the underlying model later.

For example:

```text
CYN-X Architecture
        │
        ▼
   Model Adapter
        │
   ┌────┼────┐
   ▼    ▼    ▼
 Llama  Other  Future
  3     Model   Model
```

The personality, memory, context management, tools, UI, and surrounding infrastructure should not fundamentally depend on one specific model.

If a different architecture eventually provides substantially better results within an acceptable hardware envelope, CYN-X can be benchmarked against it.

The correct question will then be:

> Does the replacement improve the complete CYN-X system enough to justify the additional resource and engineering cost?

Not:

> Is this model theoretically better?

---

# 12. The Benchmarking Principle

Future model decisions should be based on **CYN-X-specific evaluation**, not simply model reputation.

A candidate model should be evaluated against the actual requirements of CYN-X.

Relevant dimensions include:

| Dimension                    | Why it matters                                |
| ---------------------------- | --------------------------------------------- |
| Conversation                 | CYN-X is a companion                          |
| Personality consistency      | CYN-X needs recognizable character            |
| Tool use                     | CYN-X has optional tools                      |
| Technical reasoning          | CYN-X helps build software                    |
| Context handling             | CYN-X maintains conversation                  |
| Memory interaction           | CYN-X has persistent memory                   |
| Adult informational handling | CYN-X supports ordinary adult conversation    |
| Latency                      | Local interaction should remain usable        |
| RAM/VRAM usage               | Hardware is constrained                       |
| Reliability                  | Failures must be recoverable                  |
| Quantization behavior        | Local deployment depends on it                |
| Long-session stability       | Companion use involves extended conversations |

A model that wins a benchmark but performs poorly in these dimensions may not be the better CYN-X foundation.

---

# 13. The Deeper Barkly Labs Reason

This decision also reflects Barkly Labs' broader philosophy.

The mission is:

> **Can we make computers front-load the hard stuff for humans?**

CYN-X applies that idea directly.

Instead of requiring Piper to constantly:

* manage cloud APIs
* pay per request
* manually assemble context
* rebuild personality behavior
* manually route every tool
* understand every infrastructure detail

CYN-X is being built to handle as much of that complexity as possible.

Using a locally manageable model is therefore part of the experiment.

The point is not to prove that local Llama 3 is universally superior.

The point is to demonstrate that a relatively accessible machine can host a meaningful AI system with:

* personality
* memory
* tools
* autonomy within defined boundaries
* useful technical capability
* persistent context
* human-centered interaction

That is a much more interesting engineering experiment for Barkly Labs than simply calling the strongest available API.

---

# 14. Decision

CYN-X will continue using the Llama 3-family 8B foundation for the current development architecture.

This decision is based on:

1. **Local deployability**
2. **Manageable memory requirements**
3. **Sufficient general capability**
4. **Compatibility with the current CYN-X stack**
5. **Ability to experiment without mandatory cloud inference**
6. **Ability to leave resources available for the surrounding system**
7. **A reasonable capability/resource tradeoff**
8. **The ability to replace the model later if benchmarks justify doing so**

This is a **pragmatic architecture decision**, not a claim that Llama 3 is the best model in existence.

---

# 15. Reconsideration Criteria

The architecture should be reconsidered when one or more of the following becomes true:

* substantially better local models become available
* available hardware changes significantly
* CYN-X's context requirements increase
* tool-use reliability becomes a major limitation
* personality consistency becomes a persistent model-level limitation
* a different model provides significantly better capability at similar resource cost
* a GPU becomes available that changes the deployment envelope
* CYN-X-specific benchmarks show a clear advantage for another architecture

When that happens, the replacement should be tested as a **whole-system candidate**, not merely compared by parameter count or benchmark score.

---

# 16. Final Principle

The model is not CYN-X.

**The model is the cognitive engine inside CYN-X.**

CYN-X is the system surrounding it:

> model + memory + personality + context + tools + interface + recovery + engineering.

Llama 3 was chosen because it currently gives Barkly Labs a useful balance between capability and the physical resources required to run the complete system.

Another architecture may eventually be better.

If that happens, CYN-X should be able to move.

The important architectural decision is therefore not:

> “Llama 3 is the best.”

It is:

> **“Choose the strongest model that Barkly Labs can realistically run, understand, test, and integrate into the complete CYN-X system.”**
