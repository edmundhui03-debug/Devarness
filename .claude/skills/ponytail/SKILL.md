---
name: ponytail
description: "Ponytail full mode and a final simplification review for dev's coding tasks. The tieitup skill loads this first on every coding task; use it alone only when the start check says TieItUp is missing."
---

# Ponytail keeps dev's code necessary and maintainable

Paths are relative to this Devarness checkout. From its root, run
`python3 Library/bin/<tool>` to select this checkout explicitly.

Read `Library/ponytail/skills/ponytail/SKILL.md` before coding. Use full mode
unless the owner changes it. Read the touched code and callers, reuse existing
helpers, prefer standard libraries and native capabilities, then write the
smallest clear solution that satisfies the complete requirement.

Before completing a code change, read
`Library/ponytail/skills/ponytail-review/SKILL.md` and review the actual diff.
Apply justified improvements within the current task and run relevant tests.
Record broader opportunities in the task handoff; a clean review can conclude
that no simplification is justified. Identify author self-review as such.

## dev's correctness and process rules remain authoritative

The root router and superpowers own approval, testing and verification.
Preserve required behaviour, input validation, recovery, security,
accessibility and hardware calibration. Upstream examples are suggestions,
not evidence that a particular validation or retry is redundant. Clear code
wins over compressed one-liners. Honour requested documentation detail.

Ponytail review assesses complexity; correctness review and performance
measurement remain separate. Claim speed or memory gains only with relevant
before/after measurements. Never invent benchmark gains from line counts.

## Activation follows coding work throughout the session

dev's instruction-based activation applies to Peter and Aster, including after
resume. The start check checks the pin and adapters and reminds sessions to load
this skill. This is guidance for active agents, not an unattended code-changing
service. Upstream lifecycle hooks, global mode files and statusline changes are
not installed. New sessions discover the adapter; current sessions read it
directly. See `Library/PONYTAIL.md` for restoration and verification.
