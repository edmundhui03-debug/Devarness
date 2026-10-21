#!/usr/bin/env bash
# UserPromptSubmit: grill-first before, retro-last after, the library's picks between.
# The rule and its reason are in prompt-start.py. With no python3 it says nothing:
# a hook that breaks ordinary prompting gets switched off.
HOOKS="$(cd "$(dirname "$0")" && { pwd -W 2>/dev/null || pwd; })"
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 "$HOOKS/prompt-start.py"
