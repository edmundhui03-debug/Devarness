---
name: ponytail
description: "Ponytail full mode and a final simplification review for Devarness coding tasks. TieItUp loads this first; use this base directly when TieItUp is unavailable."
---

# Ponytail keeps Devarness code necessary and maintainable

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

## The router's correctness and process rules remain authoritative

The root router and superpowers own approval, testing and verification.
Preserve required behaviour, input validation, recovery, security,
accessibility and hardware calibration. Upstream examples are suggestions,
not evidence that a particular validation or retry is redundant. Clear code
wins over compressed one-liners. Honour requested documentation detail.

Ponytail review assesses complexity; correctness review and performance
measurement remain separate. Claim speed or memory gains only with relevant
before/after measurements. Never invent benchmark gains from line counts.

## Activation follows coding work throughout the session

Instruction-based activation applies to Claude Code, Codex and Pi, including
after resume. The portable core start check does not verify the upstream pin
or client loading; follow `Library/PONYTAIL.md` for those checks. This is
guidance for active agents, not an unattended code-changing service. Upstream
lifecycle hooks, global mode files and statusline changes are not installed.
New sessions discover the adapter; current sessions read it directly.
