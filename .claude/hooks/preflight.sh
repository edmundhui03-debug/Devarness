#!/bin/bash
# start preflight. Runs from session-start.sh on SessionStart (startup|resume).
# Contract: no network calls, always exits 0, no process spawn slower than ~40 ms.
# Emits JSON: systemMessage (shown to the user), additionalContext (given to the model).
set -uo pipefail

# Root is derived from this script's own location, never $PWD or a literal:
# the workspace is cloned to a different path on each device.
# pwd -W: Git Bash's C:/... form, which python3 reads even with MSYS_NO_PATHCONV=1.
ROOT="$(cd "$(dirname "$0")/../.." && { pwd -W 2>/dev/null || pwd; })"
# The hook's stdin must still be drained, or the writer can block. It is
# discarded rather than saved: the earlier debug lines here wrote the whole
# environment (including CLAUDE_CODE_MESSAGING_TOKEN) to a world-readable
# /tmp file on every session start. Do not reinstate them.
#
# Running this by hand: redirect stdin, `preflight.sh < /dev/null`. Without it
# this line waits for an EOF that an interactive shell never sends, and the
# script appears to hang when it is in fact doing exactly what a hook needs.
cat > /dev/null
# fnm's default alias lives in a different place per platform; check both.
FNM_DEFAULT="$HOME/Harness/Application Support/fnm/aliases/default"
[ -d "$FNM_DEFAULT" ] || FNM_DEFAULT="${XDG_DATA_HOME:-$HOME/.local/share}/fnm/aliases/default"

# Socket presence, never `docker info` -- that blocks for seconds when the
# daemon is down and this hook must never stall a session start.
DOCKER="absent"
if command -v docker >/dev/null 2>&1 || [ -x "$HOME/.orbstack/bin/docker" ]; then
  DOCKER="installed"
  for s in "$HOME/.orbstack/run/docker.sock" /var/run/docker.sock; do
    [ -S "$s" ] && DOCKER="running" && break
  done
fi

# The statusLine command is the bare name `statusline`, tracked in
# settings.json, resolved through ~/.local/bin on Claude's hook PATH. A device
# where bootstrap has not linked it gets a silently empty bar, so say so here.
# Probe with the PATH Claude spawned us with, not the widened one: the wrapper
# appends ~/.local/bin for its own children, but the statusLine runner uses the
# app's PATH, and on a fresh macOS that lacks ~/.local/bin. Probing the widened
# PATH said "ready" while the bar was blank.
ORIG_PATH="${DEVARNESS_ORIG_PATH:-$PATH}"
# On Windows the variable comes back through Python as a Windows path list,
# which bash cannot search; convert it back when that is what arrived.
case "$ORIG_PATH" in *\;*) command -v cygpath >/dev/null 2>&1 && ORIG_PATH="$(cygpath -u -p "$ORIG_PATH")" ;; esac
STATUSLINE="missing"; PATH="$ORIG_PATH" command -v statusline >/dev/null 2>&1 && STATUSLINE="on PATH"

# Document conversion. `command -v` is a shell builtin, so this costs nothing;
# never run `markitdown --version`, which loads Python and takes about a second.
MARKITDOWN="absent"
if command -v markitdown >/dev/null 2>&1; then
  # md-pages is the page-marking wrapper the review convention depends on.
  # Report the pair, since either one alone is a half-working setup.
  MARKITDOWN="ready"
  command -v md-pages >/dev/null 2>&1 || MARKITDOWN="no md-pages"
fi

# Skills installed from a clone rather than a plugin are checked by file
# presence, which is one stat call.
PROMPT_MASTER="absent"
[ -f "$ROOT/.claude/skills/prompt-master/SKILL.md" ] && PROMPT_MASTER="ready"

# Bilingual pages are a house rule, so the toolchain that makes them is part of
# readiness: the tool, the template, and the skill that tells an agent to use them.
PAGE_SKILL="absent"
if command -v i18n >/dev/null 2>&1; then
  PAGE_SKILL="ready"
  [ -f "$ROOT/Harness/templates/bilingual-page.html" ] || PAGE_SKILL="no template"
  [ -f "$ROOT/.claude/skills/bilingual-page/SKILL.md" ] || PAGE_SKILL="no skill"
fi

# The markdown house format is a rule in the same sense: report the tool, its
# template and the skill separately, because a missing template silently turns
# "follow the format" back into "guess the format".
MD_SKILL="absent"
if command -v md-format >/dev/null 2>&1; then
  MD_SKILL="ready"
  [ -f "$ROOT/Harness/templates/markdown-doc.md" ] || MD_SKILL="no template"
  [ -f "$ROOT/.claude/skills/markdown-format/SKILL.md" ] || MD_SKILL="no skill"
fi

# cship statusline. Three parts, and any one missing changes what appears at the
# bottom of the screen, so report the weakest link rather than a bare yes/no:
# the binary, the dev config it walks up to find, and starship, whose absence
# silently drops the whole top row instead of erroring.
CSHIP="absent"
if command -v cship >/dev/null 2>&1 || [ -x "$HOME/.local/bin/cship" ]; then
  CSHIP="ready"
  [ -f "$ROOT/cship.toml" ] || CSHIP="no config"
  command -v starship >/dev/null 2>&1 || CSHIP="no starship"
fi

# Codex bridge. The plugin's own commands are checked by Claude Code, so what
# is worth a line here is the half a hook cannot fix: `codex login` is
# interactive, and finding out at the first /codex:review is finding out late.
CODEX="absent"
if command -v codex >/dev/null 2>&1; then
  CODEX="no login"
  [ -f "${CODEX_HOME:-$HOME/.codex}/auth.json" ] && CODEX="ready"
fi

# Node version that a NEW login shell resolves, which is what Claude Code will
# hand to spawned MCP servers. Read the fnm alias symlink rather than executing
# node: same answer, ~140 ms cheaper. Several MCP servers (chrome-devtools-mcp)
# refuse to start below Node 20.19.
NODE_V=""
if [ -L "$FNM_DEFAULT" ]; then
  NODE_V="$(basename "$(dirname "$(readlink "$FNM_DEFAULT")")" 2>/dev/null | tr -d 'v')"
fi
[ -z "$NODE_V" ] && NODE_V="$(node --version 2>/dev/null | tr -d 'v')"

# The report program is a file, not a here-document: bash 3.2 writes
# here-documents to a temporary file, which a read-only sandbox refuses.
python3 "$ROOT/.claude/hooks/preflight_report.py" "$DOCKER" "$ROOT" "$NODE_V" "$MARKITDOWN" "$PROMPT_MASTER" "$PAGE_SKILL" "$CSHIP" "$CODEX" "$STATUSLINE" "$MD_SKILL"
exit 0
