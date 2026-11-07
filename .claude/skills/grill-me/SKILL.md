---
name: grill-me
description: Interview me about a design, one open-ended question at a time, until every decision is explicit. Use when I say "grill me".
---

# Grill me

Goal: reach a complete, shared understanding of the design before any code is written.

## Rules
- Don't use the AskUserQuestion tool. Plain text only.
- ONE open-ended question per message, numbered (Q1, Q2, ...).
- After each question, give a **Suggested answer** with a one-line reason.
- If I say "I don't know", don't push the suggestion: present 2–3 options with pros, cons and when each fits, then let me choose.
- If a concept may be new to me, explain it in 1–3 lines before asking.
- Dig deeper on vague answers; point out conflicts with earlier answers.
- When a topic is settled, write one line: "Decision: ... because ...".
- If I say "out of scope", record it under "Later" and move on.
- Use the current code only as context; don't assume its design is right.
- Order: goal & users → inputs/outputs → scope (what's NOT in v2.0) → knowledge sources & ingestion → retrieval → answer pipeline & graph design → failures & human review → evaluation & success metrics → cost/latency limits → API & frontend changes → testing & verification.
- Never write or change code during grilling.
- On "summary": list all decisions so far, open questions, and "Later" items.
- On "write the spec": create `docs/SPEC.md`, max ~2 pages: Goal, Scope (in/out), Decisions (one line each + reason), Graph design (a short diagram), Evaluation plan, Milestones (v2.0 first, small), Later.