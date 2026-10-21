# Review the intent, connected contracts and evidence before giving a verdict

> **2026-10-21** · Aster · `current`
>
> This is TieItUp's compact adaptation of pstack's review strengths. Apply it
> in every final coding review for Peter, Aster and May. Ponytail's simplicity
> rules, the router and superpowers remain authoritative.

## Establish what must work and what the change can reach

State the intended outcome and review the actual diff against it. Apply the
relevant lenses: correctness, security, failure recovery, concurrency,
verification, structural fit and justified complexity. Judge an error or
retry path by the contract it protects; remove it only with evidence.

Trace callers and the contracts symbol searches miss: serialized fields,
stored data, command output, configuration, cross-language consumers,
feature flags, dependency versions and lifecycle timing. Identify the one
or two facts that make the change safe. Where practical, run the real code
through that boundary and retain the command and result. Show that the
check rejects the corresponding bad case. A fixture or cached status alone
does not establish that the running integration works.

## Verify each finding and separate proof from uncertainty

For each candidate, trace a reachable input through the actual consumer to
the concrete failure. Check upstream validation and constraints that might
rule it out. Keep actionable findings with path:line, consequence and the
smallest complete correction. An empty review is valid.

Separate confirmed findings, cleared concerns and unverified risks. Label
evidence as source-verified, runtime-verified or unverified; say exactly
where proof stopped. A checker error is unverified, not a pass. Label a
review of your own work self-review. Keep correctness and security ahead
of simplification; a file's size or a preferred style alone is no finding.

## Add independent reviewers when the change justifies the cost

For a substantial change, use the existing `delegate` budget and reviewer
limits: public or persisted contracts, trust boundaries, shared mutable
state, concurrency, or a wide change with unresolved risk. Give bounded
reviewers the same intent, diff, relevant context and this rubric. Keep
reviews read-only; review findings before applying a correction.

Use only models exposed and authorized in the current harness. Preserve
the configured model and effort unless the owner or applicable routing
already authorizes a change. Report the models actually used. Same-model
reviewers provide separate reads, not model diversity. Never invent an
alternative model or silently open a PR to repair a model name.

Merge duplicate findings, record disagreements, and verify every retained
claim yourself. Agreement helps prioritize investigation; a lone security
or correctness finding still deserves a full check. Agreement is not proof.
If extra review cannot run, report the gap and complete the checks you can.

## The upstream source stays separate from the house adaptation

The pin is in `Library/repos.txt`; the intake and rollback record is
`Library/setup/pstack-review.md`. Source evidence:

- `Library/pstack/skills/interrogate/SKILL.md:23`, intent before review.
- `Library/pstack/skills/interrogate/references/rubric.md:3`, relevant lenses.
- `Library/pstack/skills/interrogate/references/lead-judgment.md:19`, reject
  preferences without a concrete problem.
- `Library/pstack/skills/blast-radius/SKILL.md:35`, indirect contracts.

Attribution: pstack, copyright 2026 Lauren Tan, MIT. The retained notice is
`Library/PSTACK-LICENSE.txt`. Raw pstack skills remain library-only; this
reference installs no upstream model rules, tooling, hooks or services.
