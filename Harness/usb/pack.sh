#!/usr/bin/env bash
# pack.sh — make the USB payload that installs dev on a new machine. Run it in
# Git Bash on a machine that has dev and its clones; nothing it reads is written.
#
#   bash Harness/usb/pack.sh SRC_DEV DEST [--books-text DIR] [--personal-repos FILE]
#                     [--personal-from DIR] [--no-books-clone] [--no-books-text]
#                     [--reverse-from DIR] [--no-reverse]
#   bash Harness/usb/pack.sh verify DEST
#
# DEST must be new or empty. It receives:
#   dev.bundle    every committed ref of SRC_DEV (uncommitted work stays behind)
#   clones/       each Harness/repos.txt clone at its pin, named by its path
#                 with / made __: a git bundle, or a tar of its .git when the
#                 clone is shallow or partial, which a bundle cannot carry; the
#                 tar's git config is rebuilt, so no credential travels in it
#   books/        Books-text.tar, and each personal clone (the book PDFs) the
#                 same way, its rows in personal-repos.txt beside install.sh
#   reverse/      the five archives Harness/setup/reverse-downloads.json names,
#                 found anywhere under --reverse-from and checked against it
#   install.sh, README.txt   from this folder
#   SHA256SUMS    every other file; written only when everything packed
# A file named like a credential anywhere in the payload stops the pack.
# verify re-hashes DEST against SHA256SUMS and fails on any unlisted file.
#
# The personal clones are the rows of --personal-repos, by default the
# owner's ~/.config/devarness/personal-repos.txt, never in git. Each is read from
# SRC_DEV at its path, or from --personal-from DIR by its folder name; Books/text
# from SRC_DEV, or --books-text. --no-books-clone leaves every personal clone
# (2.8 GB of PDFs) out, for a test. A missing personal list, Books/text or
# --reverse-from stops the pack unless its --no-* flag leaves that part out.
set -uo pipefail
# Read-only on every source: no opportunistic index refresh, and no lazy fetch
# of a missing object from a partial clone's remote (git 2.45 and later).
export GIT_OPTIONAL_LOCKS=0 GIT_NO_LAZY_FETCH=1
HERE="$(cd "$(dirname "$0")" && pwd)"
# Credential files, and folders that are built per machine or may hold keys.
SECRET='(^|/)(\.credentials\.json|auth\.json|ntfy-topic|id_(rsa|dsa|ecdsa|ed25519)[^/]*|settings\.local\.json|[^/]*\.pem|\.env)$|(^|/)(\.runtime|node_modules|__pycache__|\.ssh)(/|$)'

die() { echo "pack: $*" >&2; exit 1; }
say() { printf '   %s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }

verify() {  # <dest>
  [ -f "$1/SHA256SUMS" ] || die "no SHA256SUMS in $1: the payload is incomplete"
  (cd "$1" && sha256sum --quiet -c SHA256SUMS) || die "a file in $1 differs from SHA256SUMS"
  local extra
  extra="$(cd "$1" && comm -23 <(find . -type f ! -name SHA256SUMS | sort) \
                               <(sed 's/^[0-9a-f]\{64\} [ *]//' SHA256SUMS | sort))"
  [ -z "$extra" ] || die "files in $1 that SHA256SUMS does not list:"$'\n'"$extra"
  echo "pack: $(wc -l < "$1/SHA256SUMS") files in $1 match SHA256SUMS"
}

if [ "${1:-}" = verify ]; then
  [ -d "${2:-}" ] || die "usage: pack.sh verify DEST"
  verify "$2"
  exit 0
fi

[ $# -ge 2 ] || die "usage: pack.sh SRC_DEV DEST [--books-text DIR] [--personal-repos FILE] [--personal-from DIR] [--no-books-clone] [--no-books-text] [--reverse-from DIR] [--no-reverse]"
SRC="$1" DEST="$2"
shift 2
BOOKS_TEXT="$SRC/Books/text" PERSONAL_FROM="" NO_BOOKS_CLONE="" NO_BOOKS_TEXT="" REVERSE_FROM="" NO_REVERSE=""
PERSONAL="$HOME/.config/dev/personal-repos.txt"
while [ $# -gt 0 ]; do
  case "$1" in
    --books-text) BOOKS_TEXT="${2:?--books-text needs a folder}"; shift 2 ;;
    --personal-repos) PERSONAL="${2:?--personal-repos needs a file}"; shift 2 ;;
    --personal-from) PERSONAL_FROM="${2:?--personal-from needs a folder}"; shift 2 ;;
    --no-books-clone) NO_BOOKS_CLONE=1; shift ;;
    --no-books-text) NO_BOOKS_TEXT=1; shift ;;
    --no-reverse) NO_REVERSE=1; shift ;;
    --reverse-from) REVERSE_FROM="${2:?--reverse-from needs a folder}"; shift 2 ;;
    *) die "unknown option $1" ;;
  esac
done
[ -z "$REVERSE_FROM" ] || [ -d "$REVERSE_FROM" ] || die "--reverse-from: no folder $REVERSE_FROM"
[ "$(git -C "$SRC" rev-parse --show-toplevel 2>/dev/null)" ] || die "$SRC is not a git checkout"
# A bundle of a shallow repository reports a complete history, then cannot be cloned.
[ "$(git -C "$SRC" rev-parse --is-shallow-repository)" = false ] \
  || die "$SRC is shallow, and a bundle of it cannot be cloned: pack dev itself, or a full clone of it"
SRC="$(cd "$SRC" && pwd)"
mkdir -p "$DEST" && [ -z "$(ls -A "$DEST")" ] || die "$DEST is not empty; give a new or empty folder"
DEST="$(cd "$DEST" && pwd)"
mkdir -p "$DEST/clones" "$DEST/books"
failed=0

secret_names() {  # <what>: names on stdin; says and fails on any that looks like a credential
  local hits
  hits="$(grep -E "$SECRET")"
  [ -z "$hits" ] || { say "STOP: $1 holds names like credentials:"; printf '%s\n' "$hits" | sed 's/^/     /'; return 1; }
}

tar_git() {  # <clone> <url> <archive>
  local stage="$DEST/.stage" key value
  [ -d "$1/.git" ] || { say "$1/.git is not a folder"; return 1; }
  [ ! -f "$1/.git/objects/info/alternates" ] || { say "$1 borrows objects from another repository"; return 1; }
  rm -rf "$stage" && mkdir -p "$stage/.git"
  # Only what a restore needs: a credential helper, an extra header or a
  # token in a URL stays behind, and the origin is the manifest's URL.
  git config -f "$1/.git/config" --get-regexp \
      '^(core\.repositoryformatversion|extensions\..*|remote\.origin\.(fetch|promisor|partialclonefilter))$' |
    while read -r key value; do git config -f "$stage/.git/config" --add "$key" "$value"; done
  git config -f "$stage/.git/config" remote.origin.url "$2"
  # A clone copied locally from a blobless one keeps its .promisor packs but not
  # the setting that fetches a missing blob; the restored clone gets it back.
  if ls "$1"/.git/objects/pack/*.promisor >/dev/null 2>&1 &&
     [ -z "$(git config -f "$stage/.git/config" --get remote.origin.promisor)" ]; then
    git config -f "$stage/.git/config" remote.origin.promisor true
    git config -f "$stage/.git/config" remote.origin.partialclonefilter blob:none
  fi
  tar -cf "$3" -C "$1" --exclude=.git/config --exclude=.git/config.worktree --exclude=.git/FETCH_HEAD \
      --exclude=.git/hooks --exclude=.git/logs --exclude=.git/index --exclude=.git/remotes \
      --exclude=.git/branches --exclude='*.lock' .git &&
    tar -rf "$3" -C "$stage" .git/config
  local rc=$?
  rm -rf "$stage"
  return $rc
}

archive_clone() {  # <clone> <url> <pin> <archive path without extension>
  local head
  head="$(git -C "$1" rev-parse HEAD 2>/dev/null)" || { say "missing: $1"; return 1; }
  [ "$head" = "$3" ] || { say "not at its pin: $1 is at ${head:0:7}, the pin is ${3:0:7}"; return 1; }
  [ -z "$(git -C "$1" status --porcelain --untracked-files=no)" ] || { say "changed files in $1"; return 1; }
  # Shallow or partial (by its setting or by its .promisor packs): its history
  # is incomplete, and a bundle would need every object of it.
  if [ "$(git -C "$1" rev-parse --is-shallow-repository)" = true ] ||
     [ -n "$(git -C "$1" config --get remote.origin.promisor)$(git -C "$1" config --get extensions.partialclone)" ] ||
     ls "$1"/.git/objects/pack/*.promisor >/dev/null 2>&1; then
    tar_git "$1" "$2" "$4.git.tar" || return 1
    tar -tf "$4.git.tar" | secret_names "$4.git.tar" || return 1
    say "$(basename "$4").git.tar (shallow or partial)"
  else
    git -C "$1" bundle create -q "$4.bundle" --all || return 1
    [ "$(git -C "$1" bundle list-heads "$4.bundle" HEAD | cut -d' ' -f1)" = "$3" ] \
      || { say "$4.bundle does not carry the pin as HEAD"; return 1; }
    say "$(basename "$4").bundle"
  fi
}

step "dev"
git -C "$SRC" bundle create -q "$DEST/dev.bundle" --all || die "the dev bundle failed"
# Every path in every object the --all bundle carries: each commit of every ref,
# refs/stash and refs/remotes too, so a credential stashed or deleted is caught.
git -C "$SRC" rev-list --objects --all | cut -s -d' ' -f2- | sort -u | secret_names "dev.bundle" || failed=1
say "dev.bundle: $(git -C "$SRC" rev-parse --short HEAD) on $(git -C "$SRC" branch --show-current), $(git -C "$SRC" bundle list-heads "$DEST/dev.bundle" | wc -l) refs"
left="$(git -C "$SRC" status --porcelain | wc -l)"
[ "$left" = 0 ] || say "note: $left uncommitted changes in $SRC are not in the bundle"

pack_rows() {  # <folder under DEST>: manifest rows on stdin
  local path url sha name source
  while IFS="$(printf '\t')" read -r path url sha _; do
    sha="${sha%$'\r'}"  # a list saved with CRLF line endings
    case "${path:-}" in ''|\#*) continue ;; esac
    name="$(printf '%s' "$path" | sed 's#/#__#g')"
    source="$SRC/$path"
    [ "$1" != books ] || [ -z "$PERSONAL_FROM" ] || source="$PERSONAL_FROM/${path##*/}"
    archive_clone "$source" "$url" "$sha" "$DEST/$1/$name" || failed=1
  done
}

step "pinned clones"
pack_rows clones < <(git -C "$SRC" show HEAD:Harness/repos.txt)

step "personal clones"
if [ -n "$NO_BOOKS_CLONE" ]; then
  say "left out: every personal clone (--no-books-clone)"
elif [ -f "$PERSONAL" ]; then
  pack_rows books < "$PERSONAL"
  cp "$PERSONAL" "$DEST/personal-repos.txt" || failed=1
else
  say "no $PERSONAL: pass it with --personal-repos, or leave the personal clones out with --no-books-clone"; failed=1
fi

step "books text"
if [ -n "$NO_BOOKS_TEXT" ]; then
  say "left out: Books/text (--no-books-text); books build makes it on the new machine"
elif [ -d "$BOOKS_TEXT" ]; then
  # An older workspace named the state file .<its name>-books.json; books reads
  # .books.json, and without it would convert every book again.
  tar -cf "$DEST/books/Books-text.tar" -C "$BOOKS_TEXT" --exclude='*.partial' --exclude='*.partial.json' \
      --exclude='*.lock' --exclude='*.tmp' --transform='s,^\./\.[a-z]*-books\.json$,./.books.json,' . || failed=1
  tar -tf "$DEST/books/Books-text.tar" | secret_names "Books-text.tar" || failed=1
  say "Books-text.tar: $(tar -tf "$DEST/books/Books-text.tar" | grep -c '\.md$') Markdown files"
else
  say "no Books/text at $BOOKS_TEXT: pass it with --books-text, or leave it out with --no-books-text"; failed=1
fi

step "reverse tools"
# Flat, as setup-reverse.py --from reads them; the npm packages are not
# packed, because REA's lock reinstalls them on the new machine.
if [ -n "$NO_REVERSE" ]; then
  say "left out: the reverse archives (--no-reverse); the new machine installs them by hand"
elif [ -n "$REVERSE_FROM" ]; then
  mkdir -p "$DEST/reverse"
  sums="$(git -C "$SRC" show HEAD:Harness/setup/reverse-downloads.json | python3 -c '
import json, sys
for tool in json.load(sys.stdin)["tools"].values():
    print(tool["sha256"] + "  " + tool["file"])' | tr -d '\r')" \
    || { say "no Harness/setup/reverse-downloads.json in $SRC"; failed=1; }
  while read -r _ file; do
    [ -n "$file" ] || continue
    found="$(find "$REVERSE_FROM" -type f -name "$file" | head -1)"
    [ -n "$found" ] && cp "$found" "$DEST/reverse/$file" || { say "not in $REVERSE_FROM: $file"; failed=1; }
  done <<< "$sums"
  (cd "$DEST/reverse" && printf '%s\n' "$sums" | sha256sum --quiet -c -) \
    || { say "a reverse archive differs from Harness/setup/reverse-downloads.json"; failed=1; }
  say "reverse/: $(ls "$DEST/reverse" | wc -l) archives, $(du -sh "$DEST/reverse" | cut -f1)"
else
  say "no --reverse-from: pass the folder holding the reverse archives, or leave them out with --no-reverse"; failed=1
fi

step "install.sh and README.txt"
cp "$HERE/install.sh" "$HERE/README.txt" "$DEST/" || failed=1
(cd "$DEST" && find . -type f) | secret_names "$DEST" || failed=1

[ "$failed" = 0 ] || die "the payload in $DEST is incomplete; SHA256SUMS was not written, so install.sh refuses it"
(cd "$DEST" && find . -type f ! -name 'SHA256SUMS*' -print0 | sort -z | xargs -0 sha256sum -b) > "$DEST/SHA256SUMS.tmp" &&
  mv "$DEST/SHA256SUMS.tmp" "$DEST/SHA256SUMS" || die "SHA256SUMS could not be written"
step "done"
say "$(wc -l < "$DEST/SHA256SUMS") files, $(du -sh "$DEST" | cut -f1), in $DEST"
say "packed: $(ls "$DEST/reverse" 2>/dev/null | wc -l) reverse archives, books text $([ -f "$DEST/books/Books-text.tar" ] && echo yes || echo no), $(ls "$DEST/books" 2>/dev/null | grep -vc '^Books-text[.]tar$') personal clones"
say "copy the folder to the USB, then: bash Harness/usb/pack.sh verify <the copy>"
