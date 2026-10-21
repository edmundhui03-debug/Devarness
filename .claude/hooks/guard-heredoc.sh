#!/usr/bin/env bash
# PreToolUse on Bash: on Windows, no backslash inside a heredoc, because the
# tool rewrites the body before bash sees it. The rule and its reason are in
# guard_heredoc.py. With no python3 it lets the call through: a guard that
# stops ordinary work gets switched off.
HOOKS="$(cd "$(dirname "$0")" && { pwd -W 2>/dev/null || pwd; })"
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 "$HOOKS/guard_heredoc.py"
