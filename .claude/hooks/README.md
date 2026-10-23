# The start check runs a preflight and a fast-forward pull, and never sweeps

> **2026-10-08** · Peter · `current`
>
> The entry points of dev's start check and what each script here does. The
> check must finish before any work; it pulls this checkout forward when a
> remote exists, and it never commits, sweeps or pushes. Agents commit by path
> and push their own work. The root CLAUDE.md carries the rule.

The start check must complete before an agent starts work in dev. The root
CLAUDE.md carries that rule, AGENTS.md and `.pi/APPEND_SYSTEM.md` point to it,
and each carries the fallback for a client without active hooks.

## Every entry point finishes the same check first

| Entry | What finishes before work |
| --- | --- |
| `codex-start` / `claude-start` | Preflight, a fast-forward-only pull, the verdict, then the client |
| Claude SessionStart | The same sequence, via `session-start.sh`; 120-second hook budget |
| Codex SessionStart | `start-check --check`: preflight and saved pull status; no fetch, no Git writes |
| Pi, or a client without hooks | The agent runs `start-check --check --text` before exploring or editing |
| Manual check | `start-check --check --text` |
| Manual pull and check | `start-check --text`. After a launcher gate ended READY, the hook reports status only for five minutes instead of pulling again |

The installed launchers resolve symlinks before deriving the dev root.
Launching them from outside dev enters the root; launching inside it keeps the
current subfolder. They forward client arguments unchanged.

Codex hooks live in `.codex/hooks.json` and must pass Codex's `/hooks` trust
review before they run; `Harness/codex-hook-trust.py --check` reports one
that has not. Codex runs hook commands through Windows PowerShell, so each
starts from `python3`.

## The verdict is COMPLETE, DEGRADED or FAILED, and FAILED is loud

`session_start.py` runs `preflight.sh` first (10-second limit), then
`sync.sh --pull` (100-second limit), in the foreground.

- `START COMPLETE — READY`: checks finished; the checkout is up to date with
  origin, or has no remote yet, which is a note and not a fault.
- `START COMPLETE — DEGRADED`: checks finished, with unavailable tools shown,
  or the pull did not happen: offline, a diverged branch, a local edit in the
  way, a paused pull (`sync.off`) or a busy lock. Local work is permitted.
- `START FAILED`: empty or malformed preflight, missing python3, a timeout, or
  a refused pull (a stopped rebase or merge, an `index.lock`). Launchers return
  nonzero and do not start the client. **Claude Code ignores `continue` from
  SessionStart**, so for Claude the hook path is advisory: the banner and the
  injected context both say `START FAILED` and why, and the agent stops and
  reports. A preflight that prints nothing is named in capitals; never
  simplify that away, because silence looks exactly like a healthy start.

The pull is `git merge --ff-only`: a diverged branch or an edit in the way is
left exactly as it was, and named. Nothing here rebases, archives or resolves.

## sync.sh keeps the pull and the guards, and nothing that writes history

| Mode | What it does |
| --- | --- |
| `--pull` | Fetch origin, then fast-forward only; a missing remote is a note |
| `--status` | Uncommitted and unpushed counts, last fetch, last problem; local reads only |
| `--guard-secrets`, `--guard-size`, `--guard-state` | Refuse secret-shaped files, files over 50 MB, a stopped Git operation |
| `--check-portability` | Refuse a machine-specific path in an executable or config |

The old workspace's `--reconcile`, `--push` and the SessionEnd `--hook-end`
swept every dirty file into a commit; they are gone, and a test proves no such
mode is left.

## The other hooks guard, check and recall

| File | What it does |
| --- | --- |
| `guard_git_amend.py` | PreToolUse: no `git commit --amend` while a rebase is stopped |
| `guard_heredoc.py` | PreToolUse: on Windows, no backslash inside a heredoc |
| `guard_vendor_code.py` | PreToolUse: no unpacking a vendor application's shipped code |
| `post_edit_check.py` | PostToolUse: `md-format check` or `i18n check` on the file just edited |
| `prompt_task_recall.py` | UserPromptSubmit: what `task-recall` tracks about a subject the prompt names |
| `prompt-start.py` | UserPromptSubmit: a `grill-first` line, `library pick`'s entries and a `retro-last` line for every prompt |
| `notify-stop.sh` | Stop: a phone alert through `notify` after a turn of 10 minutes or more |

Plugin rows in the banner describe Claude configuration, not tools loaded into
Codex. The start check confirms readiness; it does not read every document.

## The statusline is statusline, resolved through ~/.local/bin

Claude's tracked `statusLine` command is `statusline`. Its symlink-safe
wrapper sets `STARSHIP_CONFIG` to `starship.toml` here and passes the root
`cship.toml`. Machine-local settings must not carry a `statusLine` of their
own, because that would override the tracked one. `statusline --preview`
renders labelled synthetic data and never presents it as live usage. Codex
uses its own `tui.status_line` in `.codex/config.toml`.

## Verification runs on temporary workspaces

```bash
start-check --check --text
statusline --preview
python3 -m unittest discover -s .claude/hooks -p 'test_*.py' -v
```

The tests use temporary workspaces, stub clients and throwaway origins, so the
order, the pull and every failure are checked without touching this checkout.
