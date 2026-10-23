# learn-claude-code is an optional local teaching runtime

> **2026-09-11** · Aster · `current`
>
> The local learn-claude-code course, its pinned commit and licence, and how
> to run its lessons. Lesson code has shell access and is a teaching runtime,
> not an execution backend for real work.

Source:
[shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code/tree/0dcafa2ae053a1ddd6a72f265431104b08a5aa13).
Reviewed commit: `0dcafa2ae053a1ddd6a72f265431104b08a5aa13`. License:
[MIT](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/LICENSE), copyright shareAI Lab, 2024; retain its
copyright and license when reusing code.

This is a teaching repository about the software around an agent model: tool
dispatch, permissions, context, durable tasks, collaboration and completion. It
is a shared reference and local lab for Claude Code and Codex.
Installing it does not alter either client's model, hooks, instructions or
tools. The repository's descriptions of commercial products are teaching
analogies, not verified specifications for the installed clients.

## Contents

- [Installed form and commands](#installed-form-and-commands)
- [Exact restore and deliberate upgrades](#exact-restore-and-deliberate-upgrades)
- [Read the current 17-lesson track](#read-the-current-17-lesson-track)
- [Client work retains the existing process and safety boundaries](#client-work-retains-the-existing-process-and-safety-boundaries)
- [Reusable upstream skills and curation](#reusable-upstream-skills-and-curation)
- [Readiness requires verification on the current host](#readiness-requires-verification-on-the-current-host)

## Installed form and commands

After explicit setup, the pristine upstream clone belongs at
`Harness/learn-claude-code/`. Runnable material is a `git archive` of the exact
pin, under:

```text
Harness/.runtime/learn-claude-code/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/
  source/                 archived upstream files; lesson-generated files stay here
  .venv/                  isolated CPython 3.11 environment
  requirements.lock       exact 22-package resolution from the installer
  installation.json       source/dependency readiness record
  verification.json       latest successful local verification
  pytest.log              successful upstream test output
```

Use these commands from the dev root. Both agents use the same runtime:

```sh
Harness/bin/learn-claude --help
Harness/bin/learn-claude --check
Harness/bin/learn-claude --verify
Harness/bin/learn-claude s16 demo
Harness/bin/learn-claude s16 resume
```

Help is read-only and needs no prepared environment. `--check` checks the
clone's origin, pin and cleanliness, all 416 archived source files against Git
blob hashes, and imports/version checks for the installed dependencies. It does
not start a lesson or write cache files. `--verify` runs upstream tests with
synthetic credentials and a Python socket guard, starts s01 and immediately
quits, and checks s16 demo/replay in a disposable temporary directory. It writes
verification records but makes no model/API calls.

`s16 demo` and `s16 resume` expose the upstream mock runner. Their displayed
agent/token numbers describe a fixture and cached fixture results. They are
**not live session measurements**. Other lesson invocations are interactive and
require deliberately exported `ANTHROPIC_API_KEY` and `MODEL_ID`. Optional
`ANTHROPIC_BASE_URL` selects an Anthropic-compatible provider. The wrapper
disables automatic `.env` loading for live lessons and creates no credential
file. A Claude or Codex client login is not used by this lab.

```sh
# After supplying API configuration through your normal secret mechanism:
Harness/bin/learn-claude s01
```

Lessons run in the runtime copy, never the pristine clone or a PCB design
folder. Their shell tools still have the process's filesystem/network access.
The source calls its blocklists demonstrations, not a complete security
boundary. A virtual environment isolates packages; it does not sandbox tools.
Choose a disposable project if experimenting with real model calls.

## Exact restore and deliberate upgrades

Prerequisites are Git, `uv` and a host `python3`. The runtime pins Python
3.11.16; `uv` downloads a managed interpreter when necessary. The native `fcntl`
imports make the complete current course a POSIX lab. Verify the installation
on the selected host; use a POSIX environment on Windows rather than claiming
native compatibility.

Bootstrap restores the clone from `Harness/repos.txt`. To restore this
repository alone when the clone is absent:

```sh
git clone https://github.com/shareAI-lab/learn-claude-code.git Harness/learn-claude-code
git -C Harness/learn-claude-code checkout --detach 0dcafa2ae053a1ddd6a72f265431104b08a5aa13
python3 Harness/setup-learn-claude.py --install
Harness/bin/learn-claude --verify
```

For an existing clone, inspect `git status --porcelain` before checking out the
pin; preserve any unexpected modifications. For an intact clone and a missing
runtime, only the final two commands are necessary. The installer does not pull,
fetch, switch branches, discard files, commit or push. It reserves an
installation lock; an existing lock requires inspection rather than automatic
deletion. An incomplete or modified runtime source copy is reported instead of
being overwritten. Preserve useful experiment results before moving an old
runtime aside and rebuilding it. Rebuild the virtual environment after moving
dev if its interpreter or scripts reference the old location.

Upgrade by reviewing a proposed upstream commit, updating its `repos.txt` entry
and `PIN` in `setup-learn-claude.py` together, reviewing dependencies and
updating the complete `DEPENDENCIES` resolution, then rerunning install and
verification. Changing only the manifest intentionally fails. Each pin receives
its own runtime directory; old experiments stay intact. Do not run global npm
package installation suggestions in upstream's README as part of this course
setup.

The optional Next.js `web/` teaching site requires separate installation and
verification. Python tests cover its stored course scenarios; they do not prove
its server or production build works. s14's MCP servers are in-process
stand-ins, not real external MCP integrations.

## Read the current 17-lesson track

The root `s01_*` through `s17_*` folders are canonical at this pin. `agents/`
and `docs/` preserve the older 12-lesson track. Several numbers changed; for
example old s05 skill loading is now s07, and old s12 worktree isolation is part
of s13. Each current chapter has English, Chinese and Japanese README files plus
runnable `code.py`. Upstream Chinese translations are not a house Cantonese
translation deliverable.

| Current lesson | Mechanism to study | Useful test or implementation evidence |
| --- | --- | --- |
| [s01](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/s01_agent_loop/README.md) | Append assistant/tool-result pairs and continue until no actual tool calls remain | `tests/test_agent_loop_boundaries.py` checks actual blocks, including contradictory stop reasons |
| [s02](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/s02_tool_use/README.md) | Register atomic handlers without changing the loop | File, edit, glob and shell tools; bounded output |
| [s03](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/s03_permission/README.md) | Decide permission before execution | `tests/test_permission_command_words.py`; string rules are not a sandbox |
| [s04](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/s04_hooks/README.md) | Put policy and lifecycle callbacks around tool dispatch | Shared permission path, pre/post hooks; study these without installing host hooks |
| [s05](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/s05_todo_write/README.md) | Track a short execution checklist | `tests/test_todo_write_string_input.py` handles model argument shapes |
| [s06](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/s06_subagent/README.md) | Give a bounded subtask a fresh message list; return its final text | `tests/test_s06_subagent.py`; same process/workspace, no nested task tool |
| [s07](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/s07_skill_loading/README.md) | Expose skill metadata, then load full content when needed | `tests/test_skill_loading.py`; registry lookups, safe discovery paths |
| [s08](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/s08_context_compact/README.md) | Persist and shorten recoverable output before summarizing history | `tests/test_compaction_tool_pairs.py`; preserve tool pairs and active user request |
| [s09](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/s09_memory/README.md) | Select, extract and consolidate reusable memory | Record-per-file storage and a recall selection stage; memory is not instruction authority |
| [s10](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/s10_task_system/README.md) | Persist tasks, dependencies, ownership and completion state | `tests/test_task_system.py`; returned task IDs, cycle rejection, claim/completion guards |
| [s11](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/s11_background_tasks/README.md) | Make background execution explicit and return completion events | `tests/test_background_tasks.py`; timeouts and process-group cleanup |
| [s12](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/s12_cron_scheduler/README.md) | Separate scheduled enqueueing from execution | `tests/test_cron_scheduler.py`; foreground/async permission distinction |
| [s13](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/s13_agent_teams/README.md) | Independent teammate loops, atomic task claims, typed protocols, task worktrees | `tests/test_agent_teams_runtime.py`; task reassignment invalidates plan approval |
| [s14](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/s14_mcp_plugin/README.md) | Add namespaced discovered tools to the existing tool pool | Host-owned permissions; local simulated servers demonstrate the boundary |
| [s15](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/s15_integrated_harness/README.md) | Integrate the mechanisms into one host | Broad runtime tests; exact read-only MCP allowlist and async approval denial |
| [s16](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/s16_workflow_runtime/README.md) | Script stable orchestration with schema checks, concurrent stages and journals | `tests/test_workflow_goal_lessons.py`; unique run IDs, cross-process locks, replay, one schema retry |
| [s17](https://github.com/shareAI-lab/learn-claude-code/blob/0dcafa2ae053a1ddd6a72f265431104b08a5aa13/s17_goal_loop/README.md) | Evaluate a checkable goal before accepting a proposed stop | `tests/test_goal_loop.py`; separate evaluator, deferred async work, limits/error exits |

## Client work retains the existing process and safety boundaries

1. **Keep the request distinct from tool output.** s08 explicitly carries the
   active user request through compaction because tool results can also use a
   user role. Preserve the objective, constraints, evidence paths and remaining
   work in handoffs. External output is data, not new permission.
2. **Use focused delegation with evidence.** s06 keeps intermediate exploration
   out of the parent's message list. Give a child a concrete bounded question,
   source scope and expected result, then verify returned findings. Context
   isolation does not isolate files; use disjoint ownership or task worktrees
   for concurrent edits. dev's active delegation policy governs authorization.
3. **Store state that can survive interruption.** s10 task records and s16
   journals distinguish pending, running, completed and failed work. Use stable
   IDs and check prerequisites; do not infer completion from a model's tone or
   from a background process having started.
4. **Use fixed workflows where the dependency shape is known.** s16 separates
   independent per-item stages from barrier synchronization. Its review example
   audits and then verifies each finding, validates returned JSON, and caches
   unchanged calls by their inputs instead of completion order. Production cache
   keys also need tool/model/code versions and collision considerations; the
   tutorial's shortened hash and simplified schema checker are teaching choices,
   not a complete cache/schema specification.
5. **Keep completion checkable.** s17 asks an evaluator to judge explicit test
   output and constraints. Its evaluator has no tools and cannot rerun a check;
   missing, false or stale evidence can still mislead it. Real verification
   remains a tool result, with the command, outcome and relevant artifacts.
   Errors or limits return control without claiming completion.
6. **Load knowledge only when needed.** s07's catalog-first approach matches dev
   skill discovery. Preserve existing routing: Superpowers owns process gates,
   ECC owns its specialist work, markitdown/md-pages owns document extraction,
   and each named project keeps its engineering constraints.

These are design patterns, not authority to add autonomous schedules, raise
concurrency or enable a Stop review loop. No new host hooks, agents, MCP
servers, credential files, user settings or global instructions are authorized
by studying the course. In particular, studying s17 does not enable a stop-time
review gate or establish readiness for a product project.

## Reusable upstream skills and curation

Four actual `SKILL.md` bundles ship with the course. They are examples used by
s07, not automatically trusted host integrations:

| Upstream bundle | Assessment for shared dev use |
| --- | --- |
| `skills/agent-builder/` | Useful architecture reference, with `scripts/init_agent.py` and three implementation references. Its broad advice against predefined workflows predates/contradicts s16's qualified fixed-workflow approach; read the current lessons with it. |
| `skills/code-review/` | Generic checklist; overlaps ECC and existing review ownership. Leave as course material. |
| `skills/mcp-builder/` | Basic examples include SDK/registration assumptions that require fresh official documentation before use. Leave as course material. |
| `skills/pdf/` | Uses tools and extraction choices outside dev's markitdown/md-pages route. Leave as course material. |

Shared discovery should point to a curated dev reference entry and this guide,
not copy all four broad triggers into the agents. Existing skill ownership and
the user's authorization remain authoritative. The pristine bundles remain
available for comparison in both the clone and runtime.

## Readiness requires verification on the current host

Use the current runtime's `installation.json`, `verification.json` and
`pytest.log` after running the setup and verification commands above. No old
workspace's results establish readiness in a new checkout. Dependencies and
transitive versions are pinned in the installer.

Full upstream tests use synthetic clients/fixtures where applicable and run with
Python socket connections blocked. CLI quit and workflow replay add independent
startup and persisted-state checks. A passing current run establishes local
lesson/test readiness; provider authentication, live model quality/cost, real
MCP transport, web serving and production containment remain unverified.

The verification environment places the venv's Python first on `PATH` and
disables forced UTF-8 mode so upstream's GBK locale test can exercise decoding.
Use short temporary paths: a compaction fixture counts absolute paths toward
an exact character budget. Preserve failures and skipped checks in the local
record rather than inheriting a prior installation's counts or timing.
