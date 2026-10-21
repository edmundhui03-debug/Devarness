#!/usr/bin/env bash
#
# scholar-sync.sh — install the curated claude-scholar subset into one project.
#
#   bash Library/scholar-sync.sh PROJECT_FOLDER
#
# dev indexes the same 14 skills library-only from the clone; this installs
# them into a research project's own .claude/. See Library/SCHOLAR.md.
#
# Contract:
#   - Reads only from the vendored clone; never modifies it.
#   - Idempotent: running twice leaves the tree byte-identical.
#   - Fails loudly if upstream renamed or removed an allowlisted path.
#   - Installs no hooks. Touches nothing outside "PROJECT_FOLDER/.claude/".
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/claude-scholar"
[ $# -eq 1 ] && [ -d "$1" ] || { echo "usage: scholar-sync.sh PROJECT_FOLDER (an existing folder)" >&2; exit 2; }
DEST="$(cd "$1" && pwd)/.claude"
MANIFEST="$DEST/hooks/scholar-manifest.txt"
STAMP="$DEST/hooks/scholar-source.txt"

# ---------------------------------------------------------------- allowlist --
# The curation. Everything not named here is deliberately absent; §3 of the
# design records the reason for each refusal. Edit this list, not the clone.

SKILLS=(
  research-ideation
  citation-verification
  ml-paper-writing
  paper-self-review
  writing-anti-ai
  nature-polishing
  results-analysis
  results-report
  publication-chart-skill
  review-response
  post-acceptance
  latex-conference-template-organizer
  daily-paper-generator
  expression-skill
)

AGENTS=(
  paper-miner
  rebuttal-writer
)

# Deliberately NOT installed, though the design originally listed it:
#
#   literature-reviewer — four of its six workflow steps are marked
#   "Zotero-Integrated"; its documented fallback chain never leaves Zotero
#   (every branch ends in another zotero_* call); its frontmatter declares
#   fourteen mcp__zotero__* tools that do not exist in this workspace; and it
#   instructs the reader to set ssl.CERT_NONE to bypass TLS certificate
#   verification. Re-add it here if a Zotero MCP server is ever configured,
#   but strip the SSL advice first.

# Files to delete after copying: dead references inside skills that are
# otherwise wanted. Each entry needs a reason.
PRUNE=(
  # Zotero MCP is not configured in this workspace; the guide is unusable and
  # would invite tool calls that cannot resolve.
  "skills/research-ideation/references/zotero-integration-guide.md"
)

COMMANDS=(
  analyze-results
  mine-writing-patterns
  rebuttal
  presentation
  poster
)

# Paths that must never appear under DEST. Guard against an upstream
# reorganisation quietly reintroducing refused content through a kept skill.
FORBIDDEN_PATTERNS=(obsidian zotero kaggle defuddle)

# ------------------------------------------------------------------- output --
info() { printf '\033[1;34m[sync]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }

# ------------------------------------------------------------------- guards --
[ -d "$SRC" ] || die "vendored clone missing: $SRC
  Fix with: git -C \"$SCRIPT_DIR\" clone https://github.com/Galaxy-Dawn/claude-scholar.git"
[ -f "$SRC/.claude-plugin/plugin.json" ] || die "$SRC does not look like claude-scholar"

missing=()
for s in "${SKILLS[@]}";   do [ -d "$SRC/skills/$s" ]      || missing+=("skills/$s"); done
for a in "${AGENTS[@]}";   do [ -f "$SRC/agents/$a.md" ]   || missing+=("agents/$a.md"); done
for c in "${COMMANDS[@]}"; do [ -f "$SRC/commands/$c.md" ] || missing+=("commands/$c.md"); done

if [ ${#missing[@]} -gt 0 ]; then
  printf '\033[1;31m[fail]\033[0m upstream no longer provides:\n' >&2
  printf '  %s\n' "${missing[@]}" >&2
  die "the allowlist and upstream have diverged — reconcile before syncing"
fi

# ----------------------------------------------------------------- teardown --
# Remove exactly what a previous run installed, so a name dropped from the
# allowlist actually disappears instead of lingering.
if [ -f "$MANIFEST" ]; then
  removed=0
  while IFS= read -r rel; do
    [ -z "$rel" ] && continue
    target="$DEST/$rel"
    case "$rel" in
      skills/*|agents/*|commands/*) ;;
      *) warn "manifest entry outside managed tree, skipping: $rel"; continue ;;
    esac
    if [ -e "$target" ]; then rm -rf "$target"; removed=$((removed + 1)); fi
  done < "$MANIFEST"
  [ "$removed" -gt 0 ] && info "removed $removed previously synced path(s)"
fi

mkdir -p "$DEST/skills" "$DEST/agents" "$DEST/commands" "$DEST/hooks"

# ------------------------------------------------------------------- install --
: > "$MANIFEST.tmp"

for s in "${SKILLS[@]}"; do
  cp -R "$SRC/skills/$s" "$DEST/skills/$s"
  echo "skills/$s" >> "$MANIFEST.tmp"
done
info "installed ${#SKILLS[@]} skills"

for a in "${AGENTS[@]}"; do
  cp -p "$SRC/agents/$a.md" "$DEST/agents/$a.md"
  echo "agents/$a.md" >> "$MANIFEST.tmp"
done
info "installed ${#AGENTS[@]} agents"

for c in "${COMMANDS[@]}"; do
  cp -p "$SRC/commands/$c.md" "$DEST/commands/$c.md"
  echo "commands/$c.md" >> "$MANIFEST.tmp"
done
info "installed ${#COMMANDS[@]} commands"

# -------------------------------------------------------------- path rewrite --
# Upstream assumes a user-global install and hardcodes "~/.claude/skills/...".
# This install is project-scoped, so those paths would dangle. Rewrite them to
# be relative to the project folder.
#
# This is the ONLY content transformation applied to upstream files. It is
# recorded here and in the manual so the copies are never mistaken for
# pristine upstream text.
rewritten=0
while IFS= read -r f; do
  if grep -q '~/\.claude/skills/' "$f" 2>/dev/null; then
    perl -pi -e 's{~/\.claude/skills/}{.claude/skills/}g' "$f"
    rewritten=$((rewritten + 1))
  fi
done < <(find "$DEST/skills" "$DEST/agents" "$DEST/commands" -type f -name '*.md' 2>/dev/null)
info "rewrote global skill paths in $rewritten file(s)"

# ------------------------------------------------------------------- prune --
pruned=0
for rel in "${PRUNE[@]}"; do
  target="$DEST/$rel"
  if [ -e "$target" ]; then
    rm -rf "$target"
    pruned=$((pruned + 1))
  else
    warn "prune entry no longer present upstream, drop it from PRUNE: $rel"
  fi
done
info "pruned $pruned dead reference file(s)"

# --------------------------------------------------------------- assertions --
# Never install advice to disable TLS certificate verification. Upstream ships
# this in at least one agent; catch it if it spreads to a kept path.
if grep -rn 'CERT_NONE\|verify=False\|--no-check-certificate\|rejectUnauthorized' \
     "$DEST/skills" "$DEST/agents" "$DEST/commands" 2>/dev/null; then
  die "kept content contains TLS-verification-bypass advice (listed above)"
fi

# Agents declaring MCP tools this workspace does not provide will fail at use
# time rather than at load time, which is the worst way to find out.
if grep -rno 'mcp__[a-z0-9_]*__' "$DEST/agents" "$DEST/skills" 2>/dev/null | grep -v 'mcp__n8n-mcp__'; then
  die "kept content declares MCP tools that are not configured here (listed above)"
fi

for pat in "${FORBIDDEN_PATTERNS[@]}"; do
  if find "$DEST/skills" "$DEST/agents" "$DEST/commands" -iname "*$pat*" -print -quit 2>/dev/null | grep -q .; then
    die "refused content leaked into the install: matched '$pat' — check the allowlist"
  fi
done

if grep -rq '~/\.claude/skills/' "$DEST/skills" "$DEST/agents" "$DEST/commands" 2>/dev/null; then
  die "global skill paths survived the rewrite"
fi

bad_frontmatter=()
for s in "${SKILLS[@]}"; do
  f="$DEST/skills/$s/SKILL.md"
  [ -f "$f" ] || { bad_frontmatter+=("$s (no SKILL.md)"); continue; }
  grep -q '^name:' "$f" && grep -q '^description:' "$f" || bad_frontmatter+=("$s (frontmatter)")
done
if [ ${#bad_frontmatter[@]} -gt 0 ]; then
  printf '\033[1;31m[fail]\033[0m malformed skills:\n' >&2
  printf '  %s\n' "${bad_frontmatter[@]}" >&2
  exit 1
fi

# ------------------------------------------------------------------- record --
mv "$MANIFEST.tmp" "$MANIFEST"

{
  echo "upstream:  https://github.com/Galaxy-Dawn/claude-scholar"
  echo "clone:     $SRC"
  echo "revision:  $(git -C "$SRC" rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "committed: $(git -C "$SRC" log -1 --format=%ad --date=short 2>/dev/null || echo unknown)"
  echo "synced:    $(date +%Y-%m-%d)"
  echo "curation:  $SCRIPT_DIR/scholar-sync.sh"
} > "$STAMP"

info "manifest: $MANIFEST"
info "done — ${#SKILLS[@]} skills, ${#AGENTS[@]} agents, ${#COMMANDS[@]} commands, 0 hooks"
