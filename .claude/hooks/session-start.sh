#!/usr/bin/env bash
# One foreground sequence: preflight, then a fast-forward-only pull, then the verdict.
set -uo pipefail
# pwd -W is Git Bash's C:/... form, which a Windows python3 reads even with
# MSYS_NO_PATHCONV=1 set; elsewhere it fails and plain pwd answers.
HOOKS="$(cd "$(dirname "$0")" && { pwd -W 2>/dev/null || pwd; })"
# Remember the PATH we were spawned with BEFORE widening it: preflight probes
# statusline against that, because it is the PATH Claude uses for the bar.
export DEVARNESS_ORIG_PATH="$PATH"
export PATH="$PATH:$HOME/.local/bin"
if ! command -v python3 >/dev/null 2>&1; then
  case " $* " in
    *' --text '*) printf 'START FAILED — python3 is not on PATH; the start check stopped.\n'; exit 1 ;;
    # Same shape as the gate's own failure output: continue/stopReason for a
    # client that honours them, and additionalContext so START FAILED reaches the
    # model on Claude, which ignores the other two. "startup stopped" is only
    # true for the launchers; say so.
    *) printf '%s\n' '{"continue":false,"stopReason":"The start check could not run: python3 missing","systemMessage":"START FAILED — python3 is not on PATH. Launchers stop here; a hook-started session continues in a degraded state and must not do work until python3 is fixed.","hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"START FAILED: python3 is not on PATH, so the readiness gate could not run. Tell the user; do not start work."}}'; exit 0 ;;
  esac
fi
exec python3 "$HOOKS/session_start.py" "$@"
