#!/usr/bin/env bash
# PostToolUse on Edit, Write and MultiEdit: run the house checker on the document just changed.
# The rule and its reason are in post_edit_check.py. With no python3 it says nothing:
# a hook that breaks ordinary editing gets switched off, and then it checks nothing.
HOOKS="$(cd "$(dirname "$0")" && { pwd -W 2>/dev/null || pwd; })"
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 "$HOOKS/post_edit_check.py"
