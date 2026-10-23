# Devarness combines one Claude Code harness with shared client capabilities

> **2026-10-21** · Aster · `current`
>
> Claude Code is the primary execution harness. Harness² supplies the
> measured improvement method, while Codex and Pi contribute review,
> discovery and design adapters. This integration is Devarness; upstream
> components retain their own authorship and licenses.

## The owner controls scope and agents verify outcomes

Read README.md, this router, LESSONS.md and the current project note.
Run `python3 tools/session.py --check --text` at the start of a working
turn. An unavailable optional tool is not ready. Use library discovery
once, read only the skills that apply, and never treat source presence
as proof of a configured or working integration.

Start with the core harness and the smallest task that proves a need.
Add a library capability only for that need, check it, and record the
result and next step in the current task record before adding another.

Claude Code leads execution; Codex provides an optional outside review;
Pi provides optional design and exploration. Those roles do not grant
permission to message another person, spend money or expose data. Models,
accounts, credentials and effort are chosen by each user.

## Existing process owners keep their responsibilities

| Domain | Owner |
| --- | --- |
| Process gates: brainstorming, TDD, debugging, verification, finishing a branch | Pinned `superpowers` skills, with `grill-first` as the interview inside brainstorming; plugin activation is optional |
| How code is written: think first, simplicity, surgical changes, goal-driven execution | `karpathy-guidelines`, always on; `grill-first`, `tieitup` and superpowers enforce each part |
| Simplicity and the coding books' rules in every coding task, and the final diff review | `tieitup`, full mode, which loads `ponytail` first and falls back to it; correctness and process keep their owners |
| Supplementary engineering skills and adversarial review references | `pstack`, library-only; TieItUp integrates selected review guidance under Ponytail and superpowers |
| Grilling a plan; a retrospective on request | Pocock's `grilling`, `grill-me`, `retro` from the pinned `Harness/skills`, and `writing-for-agents`, the style guide `retro` loads first; superpowers' `writing-skills` keeps the process of making a skill; his other skills are library-only |
| Finding a specialist tool, skill, agent brief or guide | `library` skill and command; `library pick` suggests entries for each prompt |
| External skill discovery using approved generic keywords | Vercel `find-skills`, through `library find`; local routing stays with `library`, installs with `library-intake` |
| An owner-pasted skills or tools link; installing an entry | `library-intake` |
| Specialist agents, security scanning, build repair, memory | ECC, library-only |
| Delegating to a subagent, a workflow or another agent | `delegate`: brief, budget, ledger row, `check_refs.py` |
| Review or a second opinion from a non-Claude model | Optional Codex client or plugin; verify its exposure before use |
| Building any HTML page | `bilingual-page` with the `archify` adapter; `i18n` for the toggle |
| Writing or editing any Markdown file | `markdown-format`; `md-format check` before calling it done |
| Technical diagrams: architecture, workflow, sequence, data flow, lifecycle | Archify through `archify`; `bilingual-page` owns the bilingual shell |
| Other editorial diagrams and diagram imports | `diagram-design` with the house profile `Harness/profiles/house.md`, already chosen: never re-onboard it or edit the upstream style guide; a project's own profile still wins |
| Optional static artwork and palette/font references | Anthropic `canvas-design` and `theme-factory`, library-only supplements; existing presentation, diagram, HTML and process owners remain authoritative |
| Reading PDF, Office, spreadsheet, EPub or ZIP documents | `markitdown`; `md-pages` first when a page will be cited |
| OCR for scans, images and difficult PDF tables | Scanned PDF: `md-pages` first; when a page comes back near-empty, `ocr` (`browser-docs`, local Docling, also page-marked) |
| Browser interaction and page testing | `browser-docs` through `browser --agent <name>` |
| Writing or fixing a prompt aimed at another AI tool | `prompt-master` |
| Reverse-engineering a target the owner names | REA `reverse-engineer-anything` through `rea`; `reverse-skill-router` through `reverse` (JADX, Apktool) for APKs; task-triggered, see Safety |
| Codebase or knowledge graphs, guided tours | Understand-Anything, library-only, one named project at a time; `understand`, `diagram`; a graph is navigation, not proof |
| Literature, paper writing, results analysis, rebuttal | claude-scholar, library-only, inside a research project only, with no hooks (`bash Harness/scholar-sync.sh PROJECT`) |
| An optional local book collection | `books`; add your own licensed material outside the shared repository; no book collection ships |
| PCB circuit simulation | kicad-happy `spice` with ngspice (`ngspice-setup`), library-only in `Harness/pcb/` |
| KiCad schematic, board and PCB agent sources | `kicad-happy` analyzers for review evidence; Konnect on a copy, live editing and global `konnect init` off; KiCAD-MCP-Server, pcb-designer-ai-agent, HeyPCB; all library-only in `Harness/pcb/` |
| Fire simulation: PyroSim, FDS, Smokeview | `pyrosim`, guide in `Harness/guides/pyrosim/`; FDS 6.10.1 as PyroSim bundles it (`fds-setup`); PyroSim is Windows-only |
| Agent harness lessons and experiments | learn-claude-code (`learn-claude`), library-only, isolated, owns no process gate; needs a POSIX device |
| Improving the agent harness itself: rules, hooks, skills, memory, briefs | `harness-step`, one Propose–Probe–Compose step after Harness² (`Harness/harness2`, library-only); records in `Setup/harness-steps/`; retro-last findings that need a shared change enter here |
| Studying a video from its audio and its screen | `video-study`; output goes outside dev |
| Building on the Claude API or Managed Agents | `claude-api` skill; `Harness/guides/managed-agents.md` |
| Evals, model or effort choice, API cost | `claude-api` guides `build-eval`, `hillclimb`, `cost-optimize`; real spend needs the owner |
| A short closed decision over a text that must not be invented | `laya` MCP tools through `laya-service`, served from `127.0.0.1:47631`; an answer counts only when trusted at 0.8 or more; never for routing |
| Concise task output and resuming work | `task-support`, when asked for |
| What happened to a project, and what is next | `task-recall <words>`; `--prompt` gives the next step |
| Telling the owner's phone an agent finished or is stuck | `notify` through ntfy |
| The statusline | cship through `statusline`; Codex keeps its own `tui.status_line`; a preview's sample cost is never reported as live |
| The start check | `start-check`; terminal sessions through `claude-start` and `codex-start` |
| Bringing up the portable workspace | `python3 tools/bootstrap.py --check`; `new-device check` shares its core readiness check |
| Checking optional client memory files | `agent-memory check`, read-only, when asked |
| Checking a reusable release | `python3 tools/check.py`; legacy `dev-check` assumes the full optional installation |
| Keeping clones and installed plugins at their latest | `update-tools`, policy in `Harness/updates.txt` |

## Work moves from explicit intent to verified completion

Grill-first asks every open decision together, with a recommendation.
An instruction to just do it ends the interview. Superpowers owns the
process gates; Karpathy owns simple, surgical and goal-driven coding.
TieItUp loads Ponytail before its additional rules, and the final review
traces actual callers, checks errors and keeps concrete findings.

Use a current project record for intent, scope, accepted decisions,
verification and the next step. Put project review documents under
`PRDs and Specs/`; projects may live outside this harness. Do not copy
private project content into the reusable template. Use bounded workers
only for independent reasoning; state a budget, record the launch and
verify returned citations. Keep deterministic checks in scripts.

Fetch the public `superpowers` pin before using its process skills.
Read the relevant instructions under `Harness/superpowers/skills/`;
install its client plugin separately if automatic plugin invocation is
desired. A source checkout alone does not activate that plugin.

Every working turn ends with one bounded retro-last pass. Harness
changes use harness-step: freeze a task, run a reference, propose two
scoped candidates, probe the same task, compose supported changes and
record evidence. Reflection alone is not proof of improvement.

## Secrets and local state stay outside the shared repository

Never print a key, credential or private topic, or put one in a URL,
argument, log, commit or agent memory. Use environment variables or a
local ignored configuration file. No authentication material ships.
Optional state uses `~/.config/devarness`, never another harness
installation. Personal clone discovery is off unless explicitly enabled.

No bootstrap changes global client settings, SSH, Git identity,
scheduled tasks, MCP servers or user skills. Optional installers and
services are explicit choices. No notification or external prompt
discovery runs in the default hooks. Never weaken a security gate as a
fallback. Reverse tools run only on a named, authorized target.

## Portable source and fresh evidence make sharing reviewable

Derive paths from the current checkout. Run Windows background tools
without visible windows. Keep upstream clones pinned and unmodified;
never commit them as gitlinks. Commit only task-owned paths and preserve
other sessions' changes. Stop and report a Git conflict. No automatic
commit, push, sync or paid evaluation runs at a session boundary.

Markdown follows markdown-format. House HTML follows bilingual-page
and archify, including English and Hong Kong Cantonese. Convert binary
documents before extracting evidence and use page markers for citations.
Run `python3 tools/check.py` before releasing harness changes; additional
affected specialist checks are required for those integrations. Report
failed, skipped and unverified checks explicitly.

## Sessions compact at 300K active context tokens

Keep automatic compaction enabled at 300,000 active context tokens or
the client's earlier safe native limit. Never enlarge a model window to
reach this ceiling. This is active context, not billed usage. Retain
the objective, permissions, decisions, completed work, exact paths and
commits, verification, blockers, next actions and live job identifiers.
Update the current task record before compaction, re-read it afterward,
run a fresh start check and resume. A client without a supported counter
or control must report that limitation.
