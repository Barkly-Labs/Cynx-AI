# CYN-X Benchmark Baseline

## Why CYN-X Currently Uses Llama 3.1 8B

**Barkly Labs**
**Project:** CYN-X
**Document Type:** Technical Decision / Benchmarking Record
**Status:** Active
**Date:** October 2026

---

## 1. Summary

CYN-X previously experimented with Dolphin 3.0 Llama 3.1 8B as a local model.

Dolphin was useful and remains an important experimental reference. However, the specific Dolphin build used during development created enough memory pressure on the development machine that it interfered with another critical part of CYN-X development:

> **The ability to continuously run the benchmark suite and detect regressions.**

CYN-X therefore currently uses **Llama 3.1 8B as its benchmark baseline**.

This is not a declaration that Llama 3.1 is universally better than Dolphin.

It is an engineering decision intended to establish a **stable, repeatable, resource-efficient baseline** while CYN-X's benchmark and regression infrastructure is being developed.

---

# 2. The Problem We Encountered

The initial CYN-X development path used:

```text
Dolphin 3.0 Llama 3.1 8B Q8
```

The Ollama package currently identified as:

```text
dolphin3:8b-llama3.1-q8_0
```

is approximately **8.5 GB** and uses Q8_0 quantization.

That model is capable and useful, but the model's memory footprint became a practical problem on the development machine.

CYN-X development was simultaneously running other resource-intensive software:

```text
Windows
VS Code
Firefox
Discord
development tools
Ollama
CYN-X
benchmark runner
model
model context
```

The result was significant memory pressure.

---

# 3. Why This Became a Benchmarking Problem

At first glance, memory pressure appears to be a performance problem.

For CYN-X, it became something more important:

> **A testing problem.**

A benchmark system needs to be able to repeatedly execute tests under reasonably consistent conditions.

If the development machine is constantly running near its memory limits, several things become harder:

* benchmark execution;
* repeated model loading;
* running multiple tests;
* keeping development tools open;
* comparing results;
* reproducing failures;
* running regression tests after code changes;
* investigating failures while the benchmark is running.

That creates a dangerous development cycle:

```text
Change CYN-X
     ↓
Need to benchmark
     ↓
Memory pressure
     ↓
Close development tools
     ↓
Run benchmark
     ↓
Reopen tools
     ↓
Investigate result
     ↓
Repeat
```

This increases friction precisely where CYN-X needs **more testing**, not less.

---

# 4. Regression Detection Is More Important Than Model Prestige

The immediate objective is not to determine which publicly available model has the highest theoretical capability.

The immediate objective is to determine:

> **Does a change to CYN-X make the system better or worse?**

For example:

```text
CYN-X version A
    ↓
84% benchmark score

CYN-X version B
    ↓
88% benchmark score
```

That gives us useful evidence.

But:

```text
CYN-X version A
    ↓
84%

CYN-X version B
    ↓
?
```

is much less useful if the benchmark cannot be run reliably.

Therefore, a smaller and more manageable baseline is currently more valuable than a larger model that prevents frequent testing.

---

# 5. Why Llama 3.1 8B

CYN-X currently uses:

```text
llama3.1:8b
```

through Ollama.

The current Ollama package is approximately **4.9 GB** and uses Q4_K_M quantization. Ollama lists the model with a 128K context window.

This gives CYN-X a substantially smaller model footprint than the 8.5 GB Dolphin Q8 model used during experimentation.

The goal is not simply to save storage.

The goal is to leave enough system resources available for:

```text
Model
+
Ollama
+
CYN-X
+
Benchmark runner
+
Development environment
```

at the same time.

---

# 6. Llama 3.1 Is Also a Useful Baseline

Llama 3.1 is a particularly useful baseline because it is a known foundation model family with documented model specifications and publicly available evaluation information.

Meta released Llama 3.1 in 8B, 70B, and 405B sizes and expanded the model family to a 128K context length.

The 8B model is therefore a reasonable reference point for CYN-X while the project's own evaluation system is being built.

This gives us an important distinction:

```text
External model capability
          +
CYN-X-specific evaluation
          =
CYN-X evidence
```

We do not need to assume that the underlying model is perfect.

We need to measure what happens when CYN-X is built around it.

---

# 7. This Is a Benchmark Baseline, Not a Permanent Model Decision

The current decision should **not** be interpreted as:

> "CYN-X will always use Llama 3.1 8B."

Instead:

> "Llama 3.1 8B is the current controlled baseline for CYN-X regression testing."

That distinction is important.

Future benchmarks should be able to compare:

```text
Llama 3.1 8B
Dolphin 3.0 8B
Other Llama variants
Other model families
Future CYN-X models
```

without changing the benchmark methodology itself.

---

# 8. Dolphin Remains an Experimental Reference

Dolphin should not be erased from the project history.

It provided useful evidence about:

* local model behavior;
* system-prompt steerability;
* coding;
* general-purpose interaction;
* local inference;
* model customization.

The Dolphin model documentation explicitly describes Dolphin 3.0 Llama 3.1 8B as a general-purpose local model supporting coding, mathematics, agentic tasks, function calling, and general use.

Therefore the conclusion is not:

```text
Dolphin = bad
```

It is:

```text
Dolphin = useful experimental model

but

Dolphin Q8 = too resource-intensive
for the current development + regression-testing workflow
```

---

# 9. The Important Tradeoff

The current tradeoff can be represented as:

| Requirement                               | Dolphin Q8 | Llama 3.1 8B |
| ----------------------------------------- | ---------: | -----------: |
| Local inference                           |        Yes |          Yes |
| 8B-class model                            |        Yes |          Yes |
| CYN-X experimentation                     |        Yes |          Yes |
| Model footprint                           |    ~8.5 GB |      ~4.9 GB |
| Leaves more RAM for development           |         No |          Yes |
| Practical for frequent regression testing |     Poorer |       Better |
| Useful as comparison model                |        Yes |          Yes |
| Current baseline                          |         No |      **Yes** |

The important row is not "which model is smarter."

It is:

> **Which model allows us to continuously test CYN-X?**

At the current development stage, Llama 3.1 8B wins that requirement.

---

# 10. Why We Do Not Simply Stop Benchmarking

One possible response to resource pressure would be to benchmark less frequently.

That would be the wrong engineering decision.

CYN-X is intended to become a system that can evolve through measurable engineering work.

Therefore:

```text
More code changes
       ↓
More possible regressions
       ↓
More need for testing
       ↓
Lower-friction benchmark execution
```

The benchmark infrastructure should become **easier to run**, not harder.

---

# 11. What Counts as a Regression?

CYN-X should eventually track multiple dimensions.

A regression does not necessarily mean:

> "The answer became incorrect."

It can include:

### Capability regression

A previously successful task begins
