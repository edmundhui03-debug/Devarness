# Devarness is a harness development workspace

> **2026-10-21** · Aster · `current`
>
> A Claude Code centred workspace that combines Harness²'s measured
> improvement cycle with reusable Codex and Pi capabilities. Bring the
> same rules, skill discovery, guards and tools to any project. Original
> integration code is MIT; upstream tools retain their own licenses.

## Start with a checkout that carries no account configuration

Follow [the new-project guide](docs/GETTING_STARTED.md) for Windows,
macOS and Linux setup with Claude Code, Codex and Pi.

Requires Python 3.9+ and Git. Windows shell tools need Git Bash;
macOS and Linux can use Bash. Node.js is optional for JS tools. No API key,
client login or paid model is required to run the core checks.

```sh
python3 tools/bootstrap.py --check
python3 tools/check.py --core-only
python3 tools/session.py --check --text
```

On Windows use `python` if `python3` is unavailable. Set the Python
command used by your client hooks accordingly. Nothing in the default
bootstrap changes your home profile, Git identity, SSH, client trust,
MCP registration, services or scheduled jobs.

## Fetch only the upstream capabilities you want

Start with the core commands above and one small project task. Keep its
objective, acceptance checks, result and next action in `docs/PROJECT.md`
in your own private template copy. Add one library capability when that
task needs it; verify the result before expanding the harness.

```sh
python3 tools/bootstrap.py --list
python3 tools/bootstrap.py --fetch ponytail skills karpathy-skills superpowers harness2
python3 tools/bootstrap.py --link-skills
python3 -m venv .venv
# Activate .venv, then install the locked parser:
python3 -m pip install --require-hashes -r Harness/library-requirements.txt
python3 Harness/bin/library refresh
python3 Harness/bin/library search "the task"
```

Fetch installs pinned source checkouts, without executing their code.
It never fetches a home-folder personal manifest. Skill links remain
inside this checkout. Windows may require Developer Mode for symlinks;
the link command reports missing link permissions without changing user
settings. Specialist runtime installers
under Harness/ are opt-in; read their guide before invoking them.

## Claude Code leads while Codex and Pi share the same rules

| Component | Role |
| --- | --- |
| CLAUDE.md and .claude/ | Primary rules, startup, guards and skills |
| Harness² and harness-step | Reference, propose, probe, compose, retain evidence |
| AGENTS.md, .agents/, .codex/ | Optional Codex review and shared skills |
| .pi/ | Optional Pi design and local discovery adapter |
| Harness/bin/ | Reusable tools, checkers and optional integrations |
| Harness/repos.txt | Public pinned upstream sources |
| tools/ | Neutral onboarding, session entry and release checks |

Authenticate each client using its own user settings. Models and
provider configuration are yours to choose. Codex hooks ship inactive;
use the local session command until you configure and trust hooks in
that client. Notifications, MCP services, reverse tools and external
skill search are optional and never run in the default hooks.

## Keep projects and secrets outside the reusable template

For a versioned product, create a **private repository using this template**
and clone that new repository, with its own remote. Put tracked source in
`app/` or `src/` and project intent in `docs/PROJECT.md`; `Projects/` and
`PRDs and Specs/` are ignored here. The public template receives only generic
harness changes. A template copy does not automatically receive later updates.

Pi project resources require trust, and its discovery extension specifically
runs `python3`, including on Windows. Fetching a plugin's source does not
activate that client plugin. Check the client's loaded resources separately.

Harness probes execute through Claude Code. Freeze the task, committed ref
and actual model for each comparison; uncommitted candidates need `--patch`.
The runner's `--tools` argument configures automatic approval through Claude's
`--allowedTools`; it is not a sandbox or an available-tool restriction.
Linked upstream clones and runtime remain shared with the main checkout.
Budget each run explicitly, including a composed rerun: four runs capped at
USD 1 each give a USD 4 planned maximum. Check reported spend after every run.
`delivered` records CLI completion; inspect the artifact for task acceptance.

Use this as a GitHub template or clone it beside your projects. Local project
folders, book collections, task records, review boxes, runtime state and
credential files are ignored. `tools/release_check.py` checks current index
blobs and modified working files for credentials, personal home paths and email
addresses, and checks reachable history for credentials. It also rejects local
recall caches and updater locks/logs, even if force-staged. It reads no personal
configuration. Review project examples and provenance before publication too;
generic patterns cannot recognize every private fact.

See docs/ARCHITECTURE.md for integration boundaries, docs/TOOLS.md for
the tool catalogue, docs/ADAPTATION.md for scope and verification, and
THIRD_PARTY.md for attribution. The legacy new-device checker still expects
the earlier full-install shell bootstrap; use the portable core checks above.
Its compatibility work is tracked in docs/PLAN.md.

The public harness's current work and verification are tracked in
[docs/PLAN.md](docs/PLAN.md). Personal dashboards and their local state
are excluded from this repository.

The [TieItUp improvement report](docs/TIEITUP_IMPROVEMENT.md) records local
timing, regression controls and the bounded onboarding experiment.
The [three-pass coverage audit](docs/COVERAGE.md) records retained skills,
tools, document styles, repairs and optional-source limitations.
