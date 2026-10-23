# Harness² informs a bounded local Propose–Probe–Compose step

> **2026-10-22** · Devarness · `current`
>
> The public Harness² source is pinned and optional. Devarness's local
> harness-step adapter applies its improvement method without installing
> an upstream runtime or inheriting anyone's provider credentials.

## Use the local procedure before changing the harness

Read [harness-step](../../.claude/skills/harness-step/SKILL.md) and
[the operating walkthrough](../../docs/GETTING_STARTED.md). Freeze one task,
acceptance checks, committed reference and model. Run a reference and two
scoped candidates; compose only supported edits or keep the reference.
Record confounded evidence and actual spend. A different composition needs
its own probe within the agreed budget.

The local runner uses Claude Code. Codex and Pi can propose and review;
their presence does not turn one provider's run into a cross-model test.
Paid experiments require the current owner's explicit authorization.
Keep raw traces, local task records and credentials out of the shared repo.

## Fetch upstream source for study without claiming runtime activation

From the root, use `python` on Windows if needed:

```bash
python3 tools/bootstrap.py --fetch harness2
git -C Harness/harness2 rev-parse HEAD
git -C Harness/harness2 status --short
```

Match `Harness/repos.txt` and preserve a clean upstream. Read its own setup
and dependency instructions before running anything. Fetching is not runtime
installation, provider authentication or a successful benchmark.
