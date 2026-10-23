---
name: grill-first
description: "ALWAYS-ON in dev, for Peter, Aster and May. Before designing, implementing or changing anything non-trivial, interview the owner in grilling's frontier rounds — every open question at once, numbered, each with a recommended answer — until nothing is silently assumed. Runs as the clarifying-questions step inside superpowers' brainstorming gate; it does not replace that gate. Skip only for trivial mechanical edits, direct factual questions, and work the owner has already grilled this session."
license: MIT
---

# Grill first — the interview is not optional here

**Grilling operates automatically, all the time, in dev.** Not on a trigger
phrase. Not when asked. Before any non-trivial work, for every agent.

This adapts Matt Pocock's `grilling` skill (MIT,
`Harness/skills/skills/productivity/grilling`) into a house rule. The technique
is his, unchanged; the *when* is ours.

## What to do

1. When superpowers' `brainstorming` reaches its clarifying-questions step, **do
   not ask one question at a time.** Load the `grilling` skill and run its
frontier rounds instead: map the design tree, ask every question whose
prerequisites are settled, number each, give your recommended answer under `➡️`,
then wait.
2. Facts are your job. Anything you can look up — a file, a version, a tool's
flags — you look up before asking. Only *decisions* go to the owner.
3. Recompute the frontier after each round. Stop when it is empty and the owner
confirms shared understanding. **Do not act until then.**
4. **End on a done-rubric.** When the frontier is empty, the last round
   proposes how the work will be judged finished: five to ten criteria, each
   checkable on its own by a command, a file or a named reviewer. The owner's
   confirmation covers the rubric, and verification grades every criterion —
   passed, failed, blocked or not applicable — before anything is called done.
   A criterion counts only if it is shown to fail on a known-bad case, a check
   that errors is counted as an error rather than a pass or a fail, a check is
   frozen while the work it grades is tuned, and a model that grades quality is
   not the model that produced the work, or the grade says that it is.
5. Then hand back to brainstorming for the path decision, the design, and
approval. Grilling sharpens the questions; superpowers still owns the gate.

## When not to grill

- A trivial mechanical edit: rename, typo, one-line config change.
- A direct factual question with an answer in the repository.
- Work the owner has already grilled in this session — do not re-interview.
- The owner says "just do it" or "no questions" — that ends grilling for that
  task.

## Why

The owner is a hardware engineer driving several agents from a prompt. One
question at a time costs a round trip each; the whole frontier at once, with the
recommended answer visible, costs one. And the failures that hurt most in this
workspace — the Altium that was never scriptable, the sync that ate staged work,
the tool that was installed and never usable — were all things nobody asked
about early. Grilling is how they get asked.
