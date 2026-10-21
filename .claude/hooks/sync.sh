#!/usr/bin/env bash
# sync.sh — the start check's pull, and the guards a commit is checked against.
#
# It never commits and never pushes: agents commit by path and push their own
# work. --pull fast-forwards this checkout from origin, or says why it did not.
#
# Exit codes:  0 up to date, or no remote · 1 offline or not fast-forwarded ·
#              2 refused · 4 locked
#
# bash 3.2 compatible (Apple's): no associative arrays, no mapfile, no ${var^^}.
# No `timeout` binary everywhere, so network calls are bounded by hand: 20 s
# each, retried once after a timeout, none started past 80 s.
set -uo pipefail

# The root is derived from this script's own path, never $PWD: a terminal does
# not guarantee a working directory or a login shell for the processes it starts.
ROOT="$(cd "$(dirname "$0")/../.." && { pwd -W 2>/dev/null || pwd; })"
NAME="dev"
HOOKS="$ROOT/.claude/hooks"
LOCK="$HOOKS/.sync.lock"
STATE="$HOOKS/sync.state"
OFF="$HOOKS/sync.off"
MAX_FILE_BYTES=52428800     # 50 MB: GitHub warns here and blocks at 100

log() { printf '%s\n' "$*" >&2; }

# Network bounds in seconds; net_call says why. The DEVARNESS_SYNC_* overrides are
# for tests, and take whole seconds only.
START_TIMEOUT="${DEVARNESS_SYNC_START_TIMEOUT:-20}"     # each call
START_DEADLINE="${DEVARNESS_SYNC_START_DEADLINE:-80}"   # all of one run's calls, from launch
# An override that is not whole seconds would break every comparison in
# run_bounded, which then never times out; fall back to the default and say so.
whole_seconds() {   # <variable name> <value> <default> -> the value to use
  case "$2" in
    ""|*[!0-9]*) log "sync: $1=$2 is not whole seconds; using $3"; printf '%s' "$3" ;;
    *) printf '%s' "$((10#$2))" ;;   # 10#: a leading zero is not octal
  esac
}
START_TIMEOUT="$(whole_seconds DEVARNESS_SYNC_START_TIMEOUT "$START_TIMEOUT" 20)"
START_DEADLINE="$(whole_seconds DEVARNESS_SYNC_START_DEADLINE "$START_DEADLINE" 80)"
# The deadline counts from launch, as session_start.py's bound does.
LAUNCHED_AT="$(date +%s)"

# Guards set this so the caller can record WHY the pull was refused. Without it
# a refusal exited 2 silently and --status still showed the checkout as clean.
REFUSE_REASON=""
refuse() { REFUSE_REASON="$1"; log "sync: $1"; return 2; }

# ── state ────────────────────────────────────────────────────────────────
state_set() {   # repo key value
  local repo="$1" key="$2" val="$3" tmp
  # NOT `: > "$STATE"` — that truncates the file on every call and loses every
  # previously recorded key.
  mkdir -p "$HOOKS"; [ -f "$STATE" ] || : > "$STATE"
  tmp="$STATE.tmp.$$"
  grep -v "^$repo	$key	" "$STATE" 2>/dev/null > "$tmp" || true
  printf '%s\t%s\t%s\n' "$repo" "$key" "$val" >> "$tmp"
  mv "$tmp" "$STATE"
}
state_get() {   # repo key -> stdout
  [ -f "$STATE" ] || return 1
  awk -F'\t' -v r="$1" -v k="$2" '$1==r && $2==k {print $3; f=1} END{exit !f}' "$STATE"
}

# ── lock: atomic mkdir, ownership recorded, LIVENESS checked ─────────────
# Age is not death. A sleeping laptop can hold a live lock for hours.
# Advisory, like every lock file: it orders sync and update-tools runs against
# each other, and a git command typed by hand, or a deleted lock, is not stopped by it.
acquire_lock() {
  local tries=0 owner age now since
  while ! mkdir "$LOCK" 2>/dev/null; do
    owner="$(cat "$LOCK/pid" 2>/dev/null | tr -d '[:space:]')"
    case "$owner" in
      ''|*[!0-9]*)
        # No pid, an empty file from a partially-written lock, or garbage: a
        # lock with no usable owner and older than 10 minutes is dead.
        # GNU stat first, as guard_size does: its `-f` prints a file-system block.
        since="$(stat -c %Y "$LOCK" 2>/dev/null || stat -f %m "$LOCK" 2>/dev/null || echo 0)"
        case $since in ''|*[!0-9]*) since=0 ;; esac
        now="$(date +%s)"; age=$((now - since))
        if [ "$age" -gt 600 ]; then
          log "sync: breaking lock with no usable owner (${age}s old)"
          rm -rf "$LOCK"; continue
        fi
        ;;
      *)
        if ! kill -0 "$owner" 2>/dev/null; then
          log "sync: breaking lock left by dead pid $owner"
          rm -rf "$LOCK"; continue
        fi
        ;;
    esac
    tries=$((tries+1))
    [ "$tries" -ge 3 ] && return 1
    sleep 1
  done
  # Write the pid atomically: a reader that catches a half-written file sees an
  # empty pid, which is the state that used to deadlock.
  printf '%s\n' "$$" > "$LOCK/pid.tmp" && mv "$LOCK/pid.tmp" "$LOCK/pid"
  date -u +%Y-%m-%dT%H:%M:%SZ > "$LOCK/since"
  trap release_lock EXIT INT TERM
  return 0
}
release_lock() {
  [ -d "$LOCK" ] || return 0
  [ "$(cat "$LOCK/pid" 2>/dev/null)" = "$$" ] && rm -rf "$LOCK"
  return 0
}

# ── bounded network call: no `timeout` binary here ───────────────────────
run_bounded() {
  local secs="$1"; shift
  "$@" & local pid=$! n=0
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$n" -ge "$secs" ]; then
      kill -TERM "$pid" 2>/dev/null; sleep 1; kill -KILL "$pid" 2>/dev/null
      return 124
    fi
    sleep 1; n=$((n+1))
  done
  wait "$pid"
}

# --pull runs at session start under session_start.py's 100 s bound, and an
# overrun turns the start banner FAILED rather than DEGRADED. Fetches measured
# 5.0, 5.8 and 85.9 s: an 8 s bound read a reachable GitHub as offline. So each
# call gets START_TIMEOUT and one retry after a timeout, every bound is clipped
# to the time left, and no call starts once START_DEADLINE has passed. A call
# the deadline stops counts as offline, exactly as a timeout does.
net_call() {   # <label> <command...> -> its status; 124 if it timed out or never started
  local label="$1" left secs rc
  shift
  left=$((LAUNCHED_AT + START_DEADLINE - $(date +%s)))
  if [ "$left" -le 0 ]; then
    log "sync: $label not started: the ${START_DEADLINE}s session-start deadline has passed"
    return 124
  fi
  secs=$START_TIMEOUT; [ "$secs" -le "$left" ] || secs=$left
  run_bounded "$secs" "$@"; rc=$?
  [ "$rc" -eq 124 ] || return "$rc"
  left=$((LAUNCHED_AT + START_DEADLINE - $(date +%s)))
  if [ "$left" -le 0 ]; then
    log "sync: $label timed out after ${secs}s, and the ${START_DEADLINE}s session-start deadline has passed"
    return 124
  fi
  log "sync: $label timed out after ${secs}s; retrying once"
  secs=$START_TIMEOUT; [ "$secs" -le "$left" ] || secs=$left
  run_bounded "$secs" "$@"
}

# ── guards: what a commit is checked against before it is made ───────────
guard_git_state() {   # refuse the WHOLE transaction, not merely the commit
  local r="$1" g
  g="$(git -C "$r" rev-parse --git-dir 2>/dev/null)" || { log "sync: $r is not a git repo"; return 2; }
  case "$g" in /*) : ;; *) g="$r/$g" ;; esac
  [ -e "$g/index.lock" ]        && { refuse "$r has index.lock"; return 2; }
  [ -d "$g/rebase-merge" ]      && { refuse "$r is mid-rebase"; return 2; }
  [ -d "$g/rebase-apply" ]      && { refuse "$r is mid-rebase"; return 2; }
  [ -e "$g/MERGE_HEAD" ]        && { refuse "$r is mid-merge"; return 2; }
  [ -e "$g/CHERRY_PICK_HEAD" ]  && { refuse "$r is mid-cherry-pick"; return 2; }
  [ -e "$g/BISECT_LOG" ]        && { refuse "$r is mid-bisect"; return 2; }
  if git -C "$r" diff --name-only --diff-filter=U 2>/dev/null | grep -q .; then
    refuse "$r has unmerged paths"; return 2
  fi
  return 0
}

# Every file git tracks plus every untracked one it would add, one per line: the
# whole tree, not `git status`, so a file once committed is still checked.
# (Status also collapsed a new untracked folder to one "dir/" entry unless told
# otherwise: 117 files were invisible that way on 2026-09-09.)
changed_paths() { git -C "$1" -c core.quotePath=false ls-files --cached --others --exclude-standard 2>/dev/null | sed 's/^"//;s/"$//'; }

guard_secrets() {
  local r="$1" bad=0 f
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    case "$f" in
      *.env.example|*.env.sample|*.env.template|*.env.dist) continue ;;
    esac
    case "$f" in
      .env|*/.env|*.env|*.pem|*.key|*id_rsa*|*id_ed25519*|*auth.json|*credentials.json)
        log "sync: REFUSING to commit secret-shaped file: $f"; bad=1 ;;
    esac
  done <<EOF
$(changed_paths "$r")
EOF
  [ "$bad" = 1 ] && { REFUSE_REASON="secret-shaped file"; return 2; }
  return 0
}

guard_size() {
  local r="$1" bad=0 f sz
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    [ -f "$r/$f" ] || continue
    # GNU stat (Linux, Git Bash) reads `-f` as file-system status and prints a
    # block of text, so ask for `-c %s` first; BSD stat rejects `-c` and falls through.
    sz=$(stat -c %s "$r/$f" 2>/dev/null || stat -f %z "$r/$f" 2>/dev/null || echo 0)
    if [ "$sz" -gt "$MAX_FILE_BYTES" ]; then
      log "sync: REFUSING $f — $((sz/1048576)) MB, over the 50 MB limit"; bad=1
    fi
  done <<EOF
$(changed_paths "$r")
EOF
  [ "$bad" = 1 ] && { REFUSE_REASON="file over 50 MB"; return 2; }
  return 0
}

# Documents quote absolute paths as evidence and must be exempt; executables
# and configs must not contain them at all.
check_portability() {
  local r="$1" bad=0 f candidates
  # Exemptions first, in the shell, then one grep over what is left: a grep per
  # file took 48 s over dev's whole tree on Windows (2026-10-09).
  candidates="$(while IFS= read -r f; do
    [ -n "$f" ] || continue
    case "$f" in
      # Match by STRUCTURE, never by folder name. This list was keyed to `docs/`,
      # silently stopped matching when that folder became `Setup/`, and turned
      # every spec into a violation. It anchors on `superpowers/specs|plans`
      # wherever they sit.
      */superpowers/specs/*|*/superpowers/plans/*|superpowers/specs/*|superpowers/plans/*) continue ;;
      *INSTALL.md|*/_review/*|*_review/*|*.bak-*) continue ;;
      # A project's evidence/ is finished receipts, like _review/ (owner, 2026-10-16).
      "PRDs and Specs/"*/evidence/*) continue ;;
      # Research corpora are converted upstream documentation — an Altium or
      # KiCad handbook quoting C:\Users\<name> or /Applications/KiCad is
      # describing THEIR install, not ours. Reference material under a
      # research/ folder is exempt; executables and configs beside it are not.
      docs/research/*|*/docs/research/*|research/handbooks/*|*/research/handbooks/*) continue ;;
      # Vendored skill trees are upstream content we do not author; copied
      # skills are exempt for the same reason the upstream clones are gitignored.
      .agents/skills/*|.claude/skills/*|*/.agents/skills/*|*/.claude/skills/*) continue ;;
      # Orientation documents describe the rules, and describing this rule means
      # quoting the very patterns it looks for — so CLAUDE.md and AGENTS.md
      # would refuse every edit to themselves. They are read, never executed.
      # Operational documents that carry copy-paste command blocks are
      # deliberately NOT exempt.
      CLAUDE.md|*/CLAUDE.md|AGENTS.md|*/AGENTS.md) continue ;;
      # The checkers that look for machine paths spell out what they look for.
      Library/publish-check.py|Library/tests/test_publish_check.py) continue ;;
      .claude/hooks/guard_vendor_code.py|.claude/hooks/test_guard_vendor_code.py) continue ;;
    esac
    [ -f "$r/$f" ] || continue
    case "$f" in
      *.png|*.jpg|*.jpeg|*.pdf|*.step|*.gbr|*.drl|*.xlsx|*.zip|*.tar) continue ;;
      # CAD files are data the CAD tool writes, never anything we execute, and
      # KiCad stamps absolute paths into them by design. A supplied board is a
      # read-only design input, so a path the original designer's machine left
      # there is one we are forbidden to fix.
      *.kicad_pcb|*.kicad_sch|*.kicad_pro|*.kicad_prl|*.kicad_sym|*.kicad_mod) continue ;;
      *.net|*.dsn|*.ses|*.cmp|*netlist.xml) continue ;;
    esac
    printf '%s\n' "$f"
  done <<EOF
$(changed_paths "$r")
EOF
)"
  [ -n "$candidates" ] || return 0
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    # `/home/node` is a container's own user, identical on every machine, so
    # naming it is documentation, not a portability defect. A `/home/` hit
    # therefore counts only when it is not that.
    if grep -qE '/Users/[a-zA-Z]|C:\\Users\\|/Applications/|/private/tmp/' "$r/$f" 2>/dev/null \
       || grep -E '/home/[a-z]' "$r/$f" 2>/dev/null | grep -qv '/home/node'; then
      # A macOS path behind a runtime lookup is portable; a bare one is not.
      if ! grep -qE 'command -v|XDG_DATA_HOME|dirname "\$0"' "$r/$f" 2>/dev/null; then
        log "sync: $f names a machine-specific path with no runtime fallback"; bad=1
      fi
    fi
  done <<EOF
$(cd "$r" && printf '%s\n' "$candidates" | tr '\n' '\0' |
    xargs -0 grep -lE '/Users/[a-zA-Z]|C:\\Users\\|/Applications/|/private/tmp/|/home/[a-z]' 2>/dev/null)
EOF
  [ "$bad" = 1 ] && { REFUSE_REASON="machine-specific path"; return 2; }
  return 0
}

# ── status: local reads only, never the network ──────────────────────────
# Uncommitted and unpushed work is named, because nothing pushes it but the agent.
cmd_status() {
  if [ -f "$OFF" ]; then
    printf 'sync              PAUSED     remove .claude/hooks/sync.off to resume pulling\n'; return 0
  fi
  local out br pending ahead fetched err
  if ! git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    printf 'sync              %s absent\n' "$NAME"; return 0
  fi
  pending="$(git -C "$ROOT" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
  out="$NAME $pending uncommitted"
  br="$(git -C "$ROOT" branch --show-current 2>/dev/null)"
  if ! git -C "$ROOT" remote get-url origin >/dev/null 2>&1; then
    out="$out · no remote (a note: commits stay on this device)"
  else
    if [ -n "$br" ] && git -C "$ROOT" rev-parse --verify --quiet "origin/$br" >/dev/null 2>&1; then
      ahead="$(git -C "$ROOT" rev-list --count "origin/$br..HEAD" 2>/dev/null || echo '?')"
      out="$out, $ahead unpushed"
    fi
    fetched="$(state_get "$NAME" last_fetch 2>/dev/null || echo never)"
    out="$out · fetched ${fetched:-never}"
  fi
  err="$(state_get "$NAME" last_error 2>/dev/null || echo '')"
  [ -n "$err" ] && out="$out · $err"
  printf 'sync              %s\n' "$out"
}

# ── pull: fast-forward only; never a commit, a sweep, a rebase or a push ──
cmd_pull() {   # -> 0 up to date or no remote · 1 offline or not fast-forwarded · 2 refused · 4 locked
  local r="$ROOT" br up behind rc
  [ -f "$OFF" ] && { log "sync: paused (sync.off); not pulled"; return 0; }
  acquire_lock || { log "sync: another sync holds the lock — skipping"; return 4; }
  REFUSE_REASON=""
  guard_git_state "$r" || { state_set "$NAME" last_error "REFUSED ${REFUSE_REASON:-git state} $(date -u +%H:%M)"; return 2; }
  # A checkout with no remote is not a fault: dev starts life with none.
  if ! git -C "$r" remote get-url origin >/dev/null 2>&1; then
    log "sync: $NAME has no remote — nothing to pull; commits stay on this device"
    state_set "$NAME" last_error ""
    return 0
  fi
  br="$(git -C "$r" branch --show-current 2>/dev/null)"
  if [ -z "$br" ]; then
    log "sync: $NAME is on a detached HEAD — not pulled; check out a branch to pull"
    state_set "$NAME" last_error "not pulled: detached HEAD $(date -u +%H:%M)"
    return 0
  fi
  # Fetch with NO refspec: `fetch origin <branch>` fails against an EMPTY remote,
  # which a freshly created GitHub repository is, and reads as being offline.
  if ! net_call "$NAME fetch" git -C "$r" fetch --quiet origin; then
    state_set "$NAME" last_error "offline $(date -u +%H:%M)"
    log "sync: $NAME — offline, working locally"
    return 1
  fi
  state_set "$NAME" last_fetch "$(date -u +%H:%M)"
  up="origin/$br"
  if ! git -C "$r" rev-parse --verify --quiet "$up" >/dev/null 2>&1; then
    log "sync: $NAME — nothing upstream for '$br' yet; nothing to pull"
    state_set "$NAME" last_error ""
    return 0
  fi
  behind="$(git -C "$r" rev-list --count "HEAD..$up" 2>/dev/null || echo 0)"
  if [ "$behind" = 0 ]; then
    log "sync: $NAME up to date with $up"
    state_set "$NAME" last_error ""
    return 0
  fi
  # Fast-forward only. git refuses rather than overwrite a local edit, and a
  # diverged branch is left exactly as it is, for a person to rebase by hand.
  if ! git -C "$r" merge-base --is-ancestor HEAD "$up" 2>/dev/null; then
    log "sync: $NAME has diverged from $up — not pulled; nothing was changed. Rebase by hand: git pull --rebase"
    state_set "$NAME" last_error "diverged from $up $(date -u +%H:%M)"
    return 1
  fi
  git -C "$r" merge --ff-only --quiet "$up" >/dev/null 2>&1; rc=$?
  if [ "$rc" -ne 0 ]; then
    log "sync: $NAME is $behind behind $up, but local edits are in the way — not pulled; nothing was changed. Commit or set them aside, then git pull --ff-only"
    state_set "$NAME" last_error "not pulled: local edits in the way $(date -u +%H:%M)"
    return 1
  fi
  log "sync: $NAME fast-forwarded $behind commit(s) from $up"
  state_set "$NAME" last_error ""
  return 0
}

case "${1:---status}" in
  --status)             cmd_status ;;
  --pull)               cmd_pull ;;
  --guard-secrets)      guard_secrets "${2:-$ROOT}" ;;
  --guard-size)         guard_size "${2:-$ROOT}" ;;
  --guard-state)        guard_git_state "${2:-$ROOT}" ;;
  --check-portability)  check_portability "${2:-$ROOT}" ;;
  --help|-h)            sed -n '2,12p' "$0" ;;
  *) log "sync: unknown mode: $1 (dev has no sweep: commit by path and push)"; exit 2 ;;
esac
exit $?
