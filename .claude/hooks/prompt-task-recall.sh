#!/usr/bin/env bash
# UserPromptSubmit: when a prompt names something dev is tracking, put its state in front.
# The rule and its reason are in prompt_task_recall.py. With no python3 it says nothing:
# a hook that breaks ordinary prompting gets switched off, and then it recalls nothing.
HOOKS="$(cd "$(dirname "$0")" && { pwd -W 2>/dev/null || pwd; })"
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 "$HOOKS/prompt_task_recall.py"
