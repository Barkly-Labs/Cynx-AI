# CYN-X Tool Selection: Letting CYN Choose When to Use Tools

## What We Discovered

During testing of CYN-X's tool system, we discovered an important architectural distinction:

> **Giving CYN access to a tool is not the same thing as telling CYN to use that tool.**

The original implementation accidentally made Python decide whether CYN was allowed to see tools at all.

### The old behavior

`ChatEngine._ollama_tools()` first called the Python `ToolRouter`:

```python
detected = self.tool_router.detect(user_text)

if not detected:
    return []
```

If the Python keyword detector did not recognize the request, Ollama received:

```text
Tools=0
```

and:

```json
"tools": null
```

CYN therefore had **no opportunity to decide to use a tool herself**.

For example:

> "do it and show me the website for it"

wasn't recognized by the Python detector as a search request.

So CYN couldn't search, even though searching could have been useful.

---

# The Architectural Problem

The old flow was:

```text
User
  ↓
Python keyword detector
  ↓
Does Python think a tool is needed?
  ↓
Yes → give Ollama the tool
No  → give Ollama no tools
```

This made Python the decision-maker.

That is brittle for natural language because users don't always explicitly say:

- "search the internet"
- "look this up"
- "use web search"

They might simply say:

> "What's happening with this?"

or:

> "Do it and show me the website."

A language model is better positioned to understand the intent and context of those requests.

---

# The New Architecture

The new flow is:

```text
User
  ↓
CYN-X / Ollama
  ↓
CYN decides whether a tool is actually necessary
  ↓
┌───────────────────────┐
│                       │
│ No tool needed        │ Tool needed
│                       │
▼                       ▼
Answer directly         Call appropriate tool
```

Optional tools are available to CYN without being mandatory.

For normal requests, Ollama can see:

```text
web_search
calculator
```

But CYN is responsible for deciding whether to actually call them.

---

# Tool Availability ≠ Tool Usage

This is the key discovery.

If the log says:

```text
Tools=2
```

that does **not** mean:

> "CYN must use two tools."

It means:

> "CYN has two tools available if she decides they are necessary."

### Simple question

> "What is Python?"

CYN can simply answer.

```text
Tool calls: 0
```

### Current-information question

> "What's the latest CYN-X news?"

CYN can decide:

```text
Tool calls:
- web_search
```

### Calculation

> "What is 847 × 392?"

CYN can decide:

```text
Tool calls:
- calculator
```

---

# Why We Do Not Want Automatic Searching

Web search is comparatively expensive and time-consuming.

We therefore **do not want CYN searching every time the tool is available**.

The desired behavior is:

> **Use a tool only when it materially improves the answer.**

CYN should prefer answering directly when:

- the answer is already known;
- the conversation provides enough information;
- the user is asking for an opinion;
- the user is brainstorming;
- the user wants an explanation;
- the user is having ordinary conversation;
- current external information isn't necessary.

CYN should use `web_search` when:

- the user explicitly asks to search or look something up;
- the answer depends on current information;
- the user asks about something that may have changed;
- external verification is important;
- CYN doesn't have enough reliable information to answer;
- searching would materially improve the answer.

---

# Python Should Still Control Deterministic Tools

Not every tool should be handed over to model judgment.

Some tools have application-specific behavior and should remain Python-authoritative.

Currently:

```text
Python-authoritative:
    smoke_counter
    chart
```

while:

```text
Model-optional:
    web_search
    calculator
```

This gives us a hybrid architecture:

```text
                    CYN-X
                      │
             ┌────────┴────────┐
             │                 │
      Deterministic       Optional tools
         tools                │
             │                 │
        Python decides     CYN decides
             │                 │
       ┌─────┴─────┐      ┌───┴────────┐
       │           │      │            │
 smoke_counter   chart  web_search  calculator
```

This is intentional.

---

# The New Principle

The tool system should follow this rule:

> **Python determines tool availability and execution safety. CYN determines whether optional tools are actually necessary.**

This preserves application control without forcing a brittle keyword-based decision system onto natural language.

---

# Recommended Tool-Use Policy

CYN should be given a concise instruction along these lines:

```text
## TOOL USE

Tools are capabilities, not requirements.

Use a tool only when it materially improves the answer.

Prefer answering directly from the conversation, available context,
and your existing knowledge when that is sufficient.

Use web_search when current, external, specifically requested, or
otherwise unverifiable information is necessary.

Use calculator when exact arithmetic is better handled by calculation
than mental estimation.

Do not call tools merely because they are available.

Do not search for ordinary conversation, explanations, opinions,
brainstorming, or information you can reliably answer without external
retrieval.

When a tool is genuinely necessary, use the appropriate tool.
```

The exact wording can evolve, but the behavioral principle should remain stable.

---

# What We Fixed

### Before

```text
Python detector
      ↓
No keyword match
      ↓
Tools = 0
      ↓
CYN cannot search
```

### After

```text
Python
  ↓
Provides optional tools
  ↓
Ollama
  ↓
CYN evaluates the request
  ↓
 ┌───────────────┐
 │ Is a tool     │
 │ actually      │
 │ necessary?    │
 └───────┬───────┘
      No │ Yes
         │
    ↓    │    ↓
 Answer  │  Call tool
 directly│
```

---

# Why This Is Better for CYN-X

This makes CYN-X less like:

> "A program that reacts to keywords."

and more like:

> **"An AI that has capabilities and can decide when those capabilities are worth using."**

We don't want CYN to become a search engine with a personality.

We want her to be able to think:

> *I already know this. Why would I bother searching?*

and also:

> *I don't actually know what's happening right now. Better check.*

That gives her **tool judgment rather than tool compulsion**.

---

# Current Validation

| Request | Tools exposed | Intended decision |
|---|---|---|
| `"tell me about Barkly Labs"` | `web_search`, `calculator` | CYN decides |
| `"do it and show me the website for it"` | `web_search`, `calculator` | CYN can search |
| `"what is 123 * 456?"` | `web_search`, `calculator` | CYN can use calculator |
| `"show my smoke counter"` | `smoke_counter` | Python-authoritative |
| `"make a chart of this data"` | `chart` | Python-authoritative |

The important change is that **ordinary requests no longer get `Tools=0` simply because Python failed to recognize a keyword.**

---

# Final Design Goal

The goal is **not**:

> "Make CYN use tools more."

The goal is:

> **"Make CYN capable of using tools intelligently, while avoiding them when they aren't necessary."**

That should be the guiding principle for future CYN-X tool architecture.
