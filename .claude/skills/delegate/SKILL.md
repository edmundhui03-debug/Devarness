---
name: delegate
description: Use before launching a subagent or background reasoning task, and when accepting its result.
license: MIT
---

# Delegation needs a bounded brief and verified evidence

Paths are relative to this Devarness checkout. Run commands as
`python3 Harness/bin/<tool>` from its root. Keep client credentials and
task records outside the shared release.

## Give independent reasoning to workers and deterministic work to scripts

Delegate research, source reading and independent review when they can
proceed without shared writes. Run acceptance checks, syncs and citation
validation as scripts. The parent owns integration, commits, pushes and
owner decisions. Give each worker an explicit output path or disjoint
source ownership; preserve other sessions' changes.

## State a budget before launch

State worker count, model and effort, token estimate, wall time, maximum
files or pages, and child-agent limit. Use the current client configuration
unless the owner authorized a different model. Resource estimates are
estimates; collect observed usage separately and record UNKNOWN when the
runtime exposes none. Never report a parent's counter as a worker's usage.
Choose concurrency from actual session limits and resources.

Record launches in an ignored local task ledger, for example
`Setup/AGENT_LEDGER.md`. Include time, task, budget, output, status and
verification. Do not publish another project's ledger or transcript.

## Make the brief sufficient to resume

```text
GOAL: <one concrete result and its reader>.
INPUTS: <absolute paths, revisions and first reads>.
OWNERSHIP: edit only <output or disjoint source paths>.
BOUNDARIES: <network, downloads, commands and excluded material>.
OUTPUT: <format and destination; write sections as completed>.
EVIDENCE: label verified, inferred and not checked; cite path:line
  with the cited line's text, taking numbers from the actual source.
KNOWN ERRORS: <relevant verified failures to avoid>.
BUDGET: <tokens estimate, minutes, files/pages, child limit>.
RETURN: output path, findings, failed checks, unfinished work, observed usage.
```

A missing answer is `not checked`. Preserve every required claim when
shortening an output. Monitor an authorized spend limit using actual
usage telemetry; pause dependent work if that limit is reached.

## Verify the result before integrating it

1. Compare observed usage with the budget; retain UNKNOWN if unavailable.
2. Run `python3 Harness/bin/md-format check <doc>` and
   `python3 .claude/skills/delegate/check_refs.py <doc>` unpiped.
3. Read the source behind at least three claims and every claim used for
   a release decision. A failed sample expands checking to that claim type.
4. Relabel unsupported findings and run affected tests for accepted edits.
5. Record status, result, usage and verification in the local ledger.
6. Commit only owned changes when authorized; shared-file rows require
   an isolated index if other sessions have staged or working edits.

Independent review is useful for release findings and disputed results.
Name the review's actual model and limitations; another same-model worker
does not supply model diversity. Verify the client's tools and writable
scope before launching it. Use a scratch directory for a read-only review
when the current checkout cannot be safely isolated.

## Partial output makes interrupted work recoverable

Keep the task objective, input revisions, output path and completed
sections in the local record. Resume from that checkpoint with the same
boundaries. Read transcript content only when necessary and authorized;
usage scripts should consume usage fields without copying private prompts.
