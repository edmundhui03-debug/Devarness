#!/usr/bin/env bash
# install.sh — put dev on this machine from the USB payload. Run it in Git Bash:
#
#   bash /d/dev-usb/install.sh [TARGET] [--no-system]
#
# TARGET defaults to ~/dev. It checks the prerequisites, verifies every file
# against SHA256SUMS, clones dev from dev.bundle with the four clone settings,
# unpacks Books/text, runs TARGET/Library/bootstrap.sh --offline with this
# folder (which also installs the reverse tools from reverse/ and links the
# skills for every folder), then new-device check. A personal-repos.txt on
# the USB becomes ~/.config/devarness/personal-repos.txt when there is none.
# --no-system goes to bootstrap: nothing is written outside the checkout,
# ~/.local/bin, ~/.config/devarness and the user's skill folders. README.txt beside
# this file is the owner's guide; Setup/NEW_DEVICE.md in dev is the full one.
#
#   bash /d/dev-usb/install.sh verify
#
# only re-checks every file against SHA256SUMS, and fails on a file it does
# not list; it installs nothing. (A folder named verify is ./verify.)
set -uo pipefail
USB="$(cd "$(dirname "$0")" && pwd)"
TARGET="$HOME/dev" NO_SYSTEM="" VERIFY=""
for arg in "$@"; do
  case "$arg" in
    --no-system) NO_SYSTEM=--no-system ;;
    verify) VERIFY=1 ;;
    -*) echo "usage: bash install.sh [TARGET] [--no-system] | bash install.sh verify" >&2; exit 2 ;;
    *) TARGET="$arg" ;;
  esac
done

step() { printf '\n== %s\n' "$*"; }
say()  { printf '   %s\n' "$*"; }
stop() { say "STOP: $*"; exit 1; }

check_payload() {
  [ -f "$USB/SHA256SUMS" ] || stop "no SHA256SUMS beside install.sh: the payload is incomplete"
  say "checking $(wc -l < "$USB/SHA256SUMS") files against SHA256SUMS"
  (cd "$USB" && sha256sum --quiet -c SHA256SUMS) || stop "a file on the USB differs from SHA256SUMS: copy the payload again"
  say "every file matches"
}

if [ -n "$VERIFY" ]; then
  step "the payload"
  check_payload
  extra="$(cd "$USB" && comm -23 <(find . -type f ! -name SHA256SUMS | sort) \
                                 <(sed 's/^[0-9a-f]\{64\} [ *]//' SHA256SUMS | sort))"
  [ -z "$extra" ] || stop "files that SHA256SUMS does not list:"$'\n'"$extra"
  say "nothing installed: verify only checks the USB"
  exit 0
fi

step "prerequisites"
command -v git >/dev/null 2>&1 || stop "git is missing: install Git for Windows, then run this in Git Bash"
say "$(git --version)"
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    # Git Bash's ln copies unless told otherwise; a refusal here means Windows
    # will not let git make the workspace's symlinks either.
    export MSYS=winsymlinks:nativestrict
    probe="$(mktemp -d)"
    touch "$probe/target"
    if ln -s "$probe/target" "$probe/link" 2>/dev/null && [ -L "$probe/link" ]; then
      rm -rf "$probe"; say "symlinks: native"
    else
      rm -rf "$probe"; stop "Windows refused a symlink: turn on Developer Mode (Settings > System > For developers)"
    fi ;;
esac
version="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
[ "$version" = 3.12 ] || stop "python3 is ${version:-missing}, not 3.12: install Python 3.12 from python.org and turn off the Store's python and python3 aliases"
say "python3 $version"
command -v uv >/dev/null 2>&1 || stop "uv is missing; the tools' Python environments need it (README.txt step 1d)"
say "$(uv --version)"
node="$(node -p 'process.versions.node' 2>/dev/null)"
IFS=. read -r major minor _ <<< "${node:-0.0.0}"
if [ "$major" -gt 22 ] || { [ "$major" -eq 22 ] && [ "$minor" -ge 12 ]; }; then
  say "node $node"
else
  stop "Node.js ${node:-is missing}; the reverse tools (REA) and the browser tools need 22.12 or newer (README.txt step 1e)"
fi
command -v pnpm >/dev/null 2>&1 && say "pnpm $(pnpm -v)" \
  || say "WARNING: pnpm is missing; the knowledge tools need it: npm install -g pnpm (README.txt step 1e)"

step "the payload"
check_payload

step "dev"
if git -C "$TARGET" rev-parse --git-dir >/dev/null 2>&1; then
  # Only dev's own checkout root is a rerun; a folder inside another repository is not.
  [ -z "$(git -C "$TARGET" rev-parse --show-prefix)" ] && [ -f "$TARGET/Library/bootstrap.sh" ] \
    || stop "$TARGET is inside a git repository that is not a dev checkout"
  say "a checkout is already at $TARGET; left alone"
else
  [ ! -e "$TARGET" ] || [ -z "$(ls -A "$TARGET")" ] || stop "$TARGET exists and is not empty"
  git clone -q -c core.autocrlf=false -c core.eol=lf -c core.symlinks=true -c core.longpaths=true \
    "$USB/dev.bundle" "$TARGET" || stop "the clone from dev.bundle failed"
  # The USB is not a remote: a GitHub one is added by hand (Library/finish-github-setup.sh).
  git -C "$TARGET" remote remove origin
  [ -z "$(git -C "$TARGET" status --porcelain)" ] || stop "the new checkout is not clean; delete $TARGET and run this again"
  plain="$(git -C "$TARGET" ls-files -s | awk -F'\t' '$1 ~ /^120000 / {print $2}' |
           while IFS= read -r p; do [ -L "$TARGET/$p" ] || echo "$p"; done)"
  [ -z "$plain" ] || stop "tracked symlinks came out as plain files (Developer Mode?): $plain"
  say "cloned $(git -C "$TARGET" rev-parse --short HEAD) into $TARGET"
fi
TARGET="$(cd "$TARGET" && pwd)"

step "books"
if [ ! -f "$USB/books/Books-text.tar" ]; then
  say "no Books/text on this USB; books build makes it, slowly, without a GPU"
elif [ -e "$TARGET/Books/text" ]; then
  say "Books/text is already there; left alone"
else
  # Unpacked beside it and renamed only when tar succeeds, so a failed run is retried.
  partial="$TARGET/Books/.text-unpacking"
  rm -rf "$partial"
  mkdir -p "$partial" && tar -xf "$USB/books/Books-text.tar" -C "$partial" \
    && mv "$partial" "$TARGET/Books/text" || stop "Books-text.tar did not unpack"
  say "Books/text: $(find "$TARGET/Books/text" -name '*.md' | wc -l) Markdown files"
fi

step "personal clones"
# The owner's own pins (the book PDFs), kept in ~/.config/devarness and never in git;
# bootstrap restores each row from books/ like the clones in repos.txt.
personal="$HOME/.config/dev/personal-repos.txt"
if [ ! -f "$USB/personal-repos.txt" ]; then
  say "none on this USB"
elif [ -f "$personal" ]; then
  say "~/.config/devarness/personal-repos.txt is already there; left alone"
else
  mkdir -p "$HOME/.config/dev" && cp "$USB/personal-repos.txt" "$personal" \
    || stop "~/.config/devarness/personal-repos.txt could not be written"
  say "~/.config/devarness/personal-repos.txt written from the USB"
fi

step "bootstrap"
bash "$TARGET/Library/bootstrap.sh" --offline "$USB" ${NO_SYSTEM:+"$NO_SYSTEM"}
booted=$?

step "new-device check"
python3 "$TARGET/Library/bin/new-device" check ${NO_SYSTEM:+"$NO_SYSTEM"}
ready=$?

step "left to do by hand"
# The same eight steps as README.txt section 3 and Setup/NEW_DEVICE.md.
say "1. Open a new Git Bash, so ~/.local/bin is on its PATH."
say "2. Log each agent in once: claude (then /login), codex login, and pi."
say "3. In $TARGET: claude plugin install superpowers@claude-plugins-official,"
say "   then python3 Library/codex-setup.py."
say "4. Trust dev's Codex hooks, which Codex skips until trusted. In $TARGET:"
say "   python3 Library/codex-hook-trust.py --trust (shows each command), then"
say "   --trust --yes after reading them; --check must exit 0. Start Codex with codex-start."
say "5. The PDF reader and the statusline: only if needed, uv tool install \"markitdown[all]==0.1.8\";"
say "   always the Windows x64 release binaries of cship 1.8.3 and starship into ~/.local/bin."
say "6. Build the library's index, after the installs above: library refresh in $TARGET."
say "7. Phone alerts: write the ntfy topic to ~/.config/devarness/ntfy-topic, then notify test."
say "8. A GitHub remote, when wanted: winget install GitHub.cli, gh auth login (README.txt),"
say "   add ~/.ssh/id_ed25519_dev.pub at github.com/settings/keys as an account key,"
say "   then Library/finish-github-setup.sh."
if [ -z "$NO_SYSTEM" ] && [ "$booted" = 0 ]; then
  say "Steps 3, 6 and step 5's markitdown were done by the install: repeat one only if"
  say "its output above said it failed, or you install Claude Code or Codex afterwards."
fi
say "Then, in $TARGET: start-check --check --text, then dev-check --fast, then dev-check."
say "If Claude Code or Codex was installed after this, run Library/bootstrap.sh again:"
say "it registers the laya and rea MCP servers it skipped."

echo
if [ "$booted" = 0 ] && [ "$ready" = 0 ]; then
  say "dev is installed at $TARGET"
  exit 0
fi
say "dev is at $TARGET, with the problems named above"
exit 1
