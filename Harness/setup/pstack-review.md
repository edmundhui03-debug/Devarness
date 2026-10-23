# pstack contributes concrete review checks through the local adaptation

> **2026-10-22** · Devarness · `current`
>
> TieItUp includes compact pstack review guidance beside its own rules.
> The complete upstream remains optional and library-only; it does not
> take over Ponytail or the process gates.

## Start with the shipped review guidance

Read [the local adaptation](../../.claude/skills/tieitup/references/review.md)
before the final diff review. Trace callers and persisted contracts, keep
concrete reachable failures, and prove critical checks reject bad cases.
Label self-review and unverified evidence. The root router owns precedence;
the complete walkthrough is [the setup guide](../../docs/GETTING_STARTED.md).

## Fetch the full public source only when its other skills are needed

Run from the root, using `python` on Windows if needed:

```bash
python3 tools/bootstrap.py --fetch pstack
git -C Harness/pstack rev-parse HEAD
git -C Harness/pstack status --short
```

Match the public pin in `Harness/repos.txt` and keep the clone clean.
Read the selected upstream skill and its prerequisites before invoking it.
Fetching source does not install its plugin or activate all upstream skills.
Preserve attribution in `THIRD_PARTY.md` and the retained license notices.
