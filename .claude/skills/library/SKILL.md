---
name: library
description: "Find the dev tool, skill, command, agent brief, MCP server or guide that fits a task. In dev the prompt hook already lists library pick's suggestions for each prompt; read only those entries, and search further with library search when they miss. Picks are suggestions: the router's ownership table and the safety rules win. Use library-intake instead to install an owner-supplied GitHub tool."
---

# Read the picked entries, not the catalogue

Paths are relative to this Devarness checkout. From its root, run
`python3 Library/bin/<tool>` to select this checkout explicitly.

## The picks arrive with the prompt in dev

In dev, the prompt hook runs `library pick` on every prompt of four words or
more and adds up to five lines between the grill-first and retro-last
reminders:

```text
1. dev:skill:bilingual-page - Build an HTML page in the dev workspace. ... - .claude/skills/bilingual-page/SKILL.md
```

Each line is an entry id, its one-line purpose and the file to read. Read
only the picked entries you will use, at the path given, and only the
references they need for this task. Name the entries you chose in your first
message. A prompt with no lines got no pick: the library found nothing it
could stand behind, which is normal for chit-chat and for tasks dev holds no
tool for.

Outside dev, or to ask again with other words, run it yourself; it works from
any folder and reads only the saved index:

```sh
library pick "the task in plain words" [--top 3] [--project Projects/NAME] [--json]
```

## The router defines selection and permissions

`CLAUDE.md` owns selection, permissions and activation. Its ownership table
and secrets/local-state rules govern reverse-engineering work too.
This skill supplies the commands and result format.

## Search further when the picks miss

External lookup: `library find "<the task>"`. Its shared policy is in
`CLAUDE.md`; default hooks use local discovery only. Installation, keyword
locations and current task status are in `Library/setup/vercel-find-skills.md`.

```sh
library search "the task in plain words" --project Projects/NAME --client claude
library show collection:kind:name --json
```

Search shows each result's owner, scope, mode and matched terms.
An entry scoped to a project, such as claude-scholar's skills under
`Projects/`, is eligible only from inside that project: pass `--project`.
No suitable match means use the existing owner or ask a necessary question.
For delegated work, load `delegate` before launching an agent; a library
agent file is a brief, not a live registered agent type.

## Refresh, check and coverage are deliberate

```sh
library refresh --json     # rebuild the index from the manifests (isolated parser)
library check --json       # well-formed, fresh and without diagnostics
library coverage --json    # every skill, command, agent, MCP server and clone has an entry
library eval-picks Library/tests/fixtures/library-picks.json   # frozen prompts, by their pass mark
```

Refresh reads allowlisted metadata offline; it downloads, installs and
launches nothing. A stale index still gives picks, with a warning to run
`library refresh`; a missing or corrupt one gives none. `coverage` and
`eval-picks` are gates in `dev-check`. Fix an orphan by adding a source to
`Library/library-sources.json`, never by hiding it; tune picks in the
library, never in a frozen prompt set, and never add a test prompt as a
trigger.
