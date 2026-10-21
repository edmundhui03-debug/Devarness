#!/usr/bin/env bash
# PreToolUse on Bash and PowerShell: no `git commit --amend` in the middle of a rebase.
# The rule and its reason are in guard_git_amend.py. With no python3 it lets the call through:
# a guard that stops ordinary work gets switched off.
HOOKS="$(cd "$(dirname "$0")" && { pwd -W 2>/dev/null || pwd; })"
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 "$HOOKS/guard_git_amend.py"
