---
name: retro-last
description: "ALWAYS-ON in dev for Claude, Codex and Pi: before each working turn review relevant lessons; after work run one bounded retrospective and identify evidence-backed improvements. No extra agents, model calls or recursive hooks."
---

# Retrospectives improve the next turn without expanding the current task

## Before work, apply only lessons relevant to this task

After the current turn's start check and required project instructions, review
relevant existing reminders, task checkpoints and corrections in this session.
In dev the lessons file is `LESSONS.md` at the root; elsewhere, the project's
own reminders file.
Use that evidence to avoid repeating a mistake. Reuse material already read;
search the named project only when something relevant is missing. Finish when
you can name the applicable lesson, or conclude none applies. Conversational
turns with no project work need no filesystem exploration or retrofit.

## After work, run one bounded retrospective before the final reply

Review this turn's actual actions, tests, owner corrections and tool failures.
Assess navigation, automated checks, review standards, steering-file load,
tool economy and information access. This adapts Matt Pocock's categories in
`Harness/skills/skills/engineering/retro/SKILL.md`, relative to dev's root
(use this checkout's local commands); read that file as reference when a deeper
session retrospective is warranted. Its explicit-only
invocation setting stays unchanged; this adapter supplies automatic timing.

Keep at most three actionable findings, ordered by severity. A finding names
the observed problem, evidence, smallest prevention and verification method.
A check already installed but unwired is preferable to a duplicate checker.
Mechanical mistakes should become deterministic checks when they fit the
approved scope; judgement calls belong in the owning review guidance. Never
invent a lesson to fill a quota: "no improvement needed" is a valid result.
Finish after one pass; a retrospective does not retrospect on itself.

## Improvements stay within the owner's approved task

Automatically apply only small, reversible improvements within the current
approved task and run the relevant checks. Existing process, approval,
read-only-input and hardware gates still apply. Ask the owner before changing
shared rules, hooks, security settings, unrelated tools or project scope.
Present those findings as recommendations, not edits. This skill does not
authorize extra model calls, subagents, background jobs or a new review gate.

A finding about the harness itself (a rule, hook, skill, memory or brief) is
`unprobed` until re-run evidence supports it: Harness² measured that editing a
harness from reflection alone lowered scores (`harness-step`). Name the
cheapest part that could hold the fix, and offer it as a harness step.

Record a durable, verified lesson in the existing owning skill or project
reminder only when permitted, linking its evidence. Use one authoritative
record; avoid per-turn files, duplicate rules and copies of secrets or logs.
If verification cannot finish, report the limitation instead of claiming a
fix. Existing mandatory incident-recording rules remain authoritative.

## Report only actionable findings and preserve user focus

Keep the final reply about the requested work. Include a short retro note
only when an actionable finding, verified improvement or owner decision is
worth reporting. An empty result needs no visible "retro complete" message.
Automatic activation is instruction-based, not an executable hook guarantee.
Fresh sessions discover the shared skill; Pi can refresh skills with `/reload`.
