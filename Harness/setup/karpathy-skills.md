# Karpathy guidance is pinned and shared across the three clients

> **2026-10-22** · Devarness · `current`
>
> The router retains Karpathy's four coding principles. Fetch the public
> source and verify local skill discovery; no previous user's plugin or
> global configuration is required or inherited.

## Restore the source and checkout-local skill links

From the repository root, run the following. Use `python` on Windows if
that is your interpreter's command.

```bash
python3 tools/bootstrap.py --fetch karpathy-skills
python3 tools/bootstrap.py --link-skills
git -C Harness/karpathy-skills rev-parse HEAD
git -C Harness/karpathy-skills status --short
```

Compare HEAD with `Harness/repos.txt`; preserve any off-pin local work.
Read `Harness/karpathy-skills/skills/karpathy-guidelines/SKILL.md`.
`tools/skill-links.json` maps the Claude and shared `.agents` entries to
that source. Windows needs working native directory links for discovery.

## Apply the principles inside the existing process

Think before coding; choose simplicity; make surgical changes; work toward
verifiable goals. These guide implementation alongside the router's existing
process owners. Ponytail and TieItUp do not replace testing, debugging or
correctness review. Read [the root router](../../CLAUDE.md) for precedence.

Claude Code uses the project skill; Codex and Pi share `.agents/skills/`.
Check each client's loaded resources or read the instructions explicitly.
A fetched clone and valid links alone do not prove client activation.
See [the setup walkthrough](../../docs/GETTING_STARTED.md) for all clients.
