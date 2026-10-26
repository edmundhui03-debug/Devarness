# Start a private project with shared rules and measured improvements

> **2026-10-26** · Aster · `current`
>
> Create your own repository from Devarness, then run Claude Code, Codex
> and Pi from its root with shared project intent. Measure harness changes.

## Contents

- [Create your own repository and keep application files tracked](#create-your-own-repository-and-keep-application-files-tracked)
- [Check the core before adding optional source capabilities](#check-the-core-before-adding-optional-source-capabilities)
- [Launch each client from the same project root](#launch-each-client-from-the-same-project-root)
- [Use TieItUp and Ponytail to keep changes small and review complete](#use-tieitup-and-ponytail-to-keep-changes-small-and-review-complete)
- [Improve the harness by comparing one frozen task across candidates](#improve-the-harness-by-comparing-one-frozen-task-across-candidates)

## Create your own repository and keep application files tracked

Install Python 3.9+, Git and, on Windows, Git Bash. Install
[Claude Code](https://code.claude.com/docs/en/setup),
[Codex](https://learn.chatgpt.com/docs/codex/cli) and
[Pi](https://pi.dev/docs/latest/quickstart) using official instructions.
Pi's npm installation requires Node.js 22.19+. Authenticate through the native
client flow and choose your own supported model and effort.

On GitHub choose **Use this template**, create a **private** repository
under your account, then clone it. Replace the example below; origin is yours.

```powershell
git -c core.autocrlf=false -c core.symlinks=true -c core.longpaths=true clone https://github.com/YOURACCOUNT/MyProject.git
cd MyProject
git remote -v
```

Put application code in root `app/` or `src/`. Keep durable scope, acceptance
checks, decisions and next actions in tracked `docs/PROJECT.md`; link it
from the client instructions. `Projects/`, `PRDs and Specs/`, `Setup/` and
`.state/` are ignored (`.gitignore:13`). Keep secrets outside tracked files.

## Check the core before adding optional source capabilities

Start with one small task in `docs/PROJECT.md`. Record its objective,
acceptance check, current result and next action. The library supplies
optional capabilities to the harness: select one only when this task
needs it, and record the command and result before adding the next.

These commands are PowerShell examples. On macOS/Linux use `python3`
in place of `python`; run every command from the repository root.

```powershell
python tools/bootstrap.py --check
python tools/check.py --core-only
python tools/session.py --check --text
```

The core is enough to begin. When a task needs the shared skill library,
fetch the relevant sources explicitly. This example enables the existing
coding and harness improvement skills; select only those you will use.
Fetch refuses an existing source that is off-pin, modified or incompletely
checked out. Inspect that source before retrying; setup never resets it.

```powershell
python tools/bootstrap.py --fetch ponytail skills karpathy-skills superpowers harness2
python tools/bootstrap.py --link-skills
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r Harness/library-requirements.txt
.\.venv\Scripts\python.exe Harness/bin/library refresh
.\.venv\Scripts\python.exe Harness/bin/library search "my project task"
```

On macOS/Linux the last three commands use `.venv/bin/python`; no virtual
environment activation is needed. Fetching optional sources is explicit
network work. Source checkouts and `.agents/skills/` links do not activate
plugins or prove runtime readiness (`README.md:44`). Windows skill links
may require Developer Mode; resolve link failures before claiming skills
are loaded (`README.md:46`). Install the superpowers client plugin
separately if desired; its source checkout is not plugin activation.

## Launch each client from the same project root

Run `claude`, `codex` or `pi` from this root in separate terminals.
Read `docs/PROJECT.md`; keep credentials in each client's user configuration.

Claude hooks and Pi discovery both launch `python3`. Before starting either,
run `python3 --version` in the terminal you will use; on Windows also check
it in Git Bash. A successful core check with `python` does not verify this
separate command. Make Python 3.9+ available as `python3`, or deliberately
adjust the local client commands before proceeding (`.claude/settings.json:10`,
`.pi/extensions/dev-discovery.ts:10`). Claude can exit successfully even
when a startup hook fails; inspect its hook diagnostics for READY.

Run `python tools/bootstrap.py --link-skills` to repair the checkout's skill
links before checking loaded skills. This also works without fetching optional
sources; unavailable source skills remain absent (`tools/bootstrap.py:100`).

- **Claude Code:** trust this project only after reviewing its instructions
  and hooks. Read `CLAUDE.md` and verify the local startup check succeeds.
- **Codex:** read `AGENTS.md`, use the checkout's `.agents/skills/` links,
  and run `python tools/session.py --check --text` each working turn.
  Hooks ship inactive (`.codex/hooks.json:1`); configuring and trusting
  hooks in Codex is a separate step (`README.md:64`).
- **Pi:** review and trust the project extension and read
  `.pi/APPEND_SYSTEM.md`. Pi discovers project
  `.agents/skills/`; use `/skill:name` and `/reload` after edits. Verify startup
  diagnostics ([Pi skills](https://pi.dev/docs/latest/skills)).

Use Pi to clarify intent and explore design, Claude Code to implement, and
Codex for an independent review. Assign one writer per file; parallel
implementation needs separate worktrees and explicit ownership. A reviewer
using the same model supplies another read, not model diversity
(`.claude/skills/tieitup/references/review.md:47`).

## Use TieItUp and Ponytail to keep changes small and review complete

Load `.claude/skills/tieitup/SKILL.md`: Ponytail first, then the existing
18 rules and each touched language pack. Reuse instructions already loaded
in the current context (`.claude/skills/tieitup/SKILL.md:19`). Preserve
validation, recovery, security and the complete requested behavior.
Run the checkout-local checker after edits and on the final diff:

```powershell
python Harness/bin/tieitup check
```

For final review, use the compact pstack adaptation at
`.claude/skills/tieitup/references/review.md:11`: review the actual diff,
trace callers and persisted contracts, and demonstrate a reachable failure
before retaining a finding. Prove key checks reject the bad case. A checker
error is unverified, not a pass (line 33). Label your own review self-review.
Measure performance before claiming gains; fewer lines do not prove speed
(`.claude/skills/ponytail/SKILL.md:30`).

## Improve the harness by comparing one frozen task across candidates

Read `.claude/skills/harness-step/SKILL.md` before changing rules, hooks or
skills. Freeze a small, already clarified task with meaningful acceptance
checks. Target the TieItUp/Ponytail/pstack review path; compare correctness,
missed or false findings, instruction-loading work, time, tokens and cost.

Use one committed reference and one explicit Claude model for all runs.
Plan at most four paid runs: base, INV, DOM and composed, each with a USD 1
CLI cap and 300-second timeout; planned cycle allocation is USD 4. The
runner uses Claude Code only; Codex and Pi can propose and review.

Create `.state/harness-steps/first/task.md` and record the agreed budget:

```powershell
$probe = '.claude/skills/harness-step/scripts/probe.py'
$ref = git rev-parse HEAD
$out = '.state/harness-steps/first'
$model = 'YOUR_CLAUDE_MODEL'
python $probe run --task "$out/task.md" --ref $ref --model $model --max-usd 1 --timeout 300 --label base --out $out
```

For Bash, use `probe='...'`, `ref=$(git rev-parse HEAD)`, `out='...'` and
`model='...'`, with the same values; replace `python` with `python3`.
Read base evidence, then save two scoped patches against that same ref:
`inv.diff` for process and `dom.diff` for relevant domain guidance. Tie each
edit to a trajectory moment. Apply patches only in the probe worktrees.

```powershell
python $probe run --task "$out/task.md" --ref $ref --model $model --max-usd 1 --timeout 300 --patch "$out/inv.diff" --label inv --out $out
python $probe run --task "$out/task.md" --ref $ref --model $model --max-usd 1 --timeout 300 --patch "$out/dom.diff" --label dom --out $out
python $probe summary $out
```

Compose supported edits or `KEEP_BASE`. If composition differs from both
probed candidates, use the same run command with `--patch` pointing to
`composed.diff` and `--label composed`. Check task acceptance separately:
`delivered` means CLI completion, not acceptance.
The runner's `--tools` sets automatic approvals through `--allowedTools`,
not Claude's built-in executable tool restriction. Clones and runtime remain
shared with main; do not write there. Uncommitted edits need explicit patches.
See `.claude/skills/harness-step/scripts/probe.py:118`, line 184 and line 204.

Record helped, hurt, no observed effect or confounded, including actual
spend and errors. One run per candidate is weak evidence; retain only
supported changes and obtain approval for shared harness adoption. Raw
trajectories stay ignored and unpublished. This guide establishes setup
steps, not proof that your clients or proposed improvement have passed.
