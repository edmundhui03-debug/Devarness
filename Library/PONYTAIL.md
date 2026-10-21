# Ponytail restoration starts from the pinned source and local adapters

> **2026-10-22** · Devarness · `current`
>
> TieItUp loads Ponytail's full-mode coding guidance and diff review first.
> Restore those instructions from the public pin, then verify discovery in
> the client you use. No global plugin or lifecycle hook is installed here.

## Fetch source without changing a client installation

From the repository root, use `python3` below, or `python` on Windows:

```bash
python3 tools/bootstrap.py --fetch ponytail
python3 tools/bootstrap.py --link-skills
python3 tools/session.py --check --text
git -C Library/ponytail rev-parse HEAD
git -C Library/ponytail status --short
```

Match HEAD to `Library/repos.txt` and require a clean upstream tree.
Bootstrap refuses an existing off-pin checkout; inspect it and preserve any
local work before repairing it. Do not overwrite or reset it blindly.
An absent unrelated optional source does not make Ponytail missing.

## Read both upstream skills before reviewing a real diff

Read `.claude/skills/ponytail/SKILL.md`, then the coding and review skills
under `Library/ponytail/skills/ponytail/` and `ponytail-review/`.
TieItUp's adapter adds its rules, language pack and pstack review guidance
after this base (`.claude/skills/tieitup/SKILL.md:16`).

Claude uses the project adapter; Codex and Pi share the checkout's
`.agents/skills/` links. Verify each client's loaded resources or read the
adapter explicitly in an existing session. Links and a successful core
start check alone do not prove that the upstream instructions were loaded.

Review the actual diff, trace callers and preserve the never-cut behavior.
Run `python3 Library/bin/tieitup check --staged` on a staged change and the
relevant project tests. Label author review self-review. A zero exit with
checker diagnostics is unverified; a review needs concrete failure cases.
The full operating walkthrough is in [the setup guide](../docs/GETTING_STARTED.md).
