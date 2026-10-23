dev on a new Windows PC, from this USB
======================================

This folder installs dev, the workspace with every tool, skill and the
library, on a new machine. Everything is here except your logins, the
statusline's two programs (section 3, step 5) and the Python and Node
packages, which download during the install. The full guide,
with the reasons for each step, is Setup/NEW_DEVICE.md inside dev once it is
installed.

Nothing on this USB is secret. Never copy a login, a key or the ntfy topic
onto it.


1. Install the prerequisites (once, with the network on)
--------------------------------------------------------

  a. Settings > System > For developers (on newer builds System > Advanced >
     For developers, or search "developer" in Settings): turn on Developer
     Mode. Without it Windows refuses the symlinks dev's skills are made of.
  b. Git for Windows, from https://git-scm.com/download/win, with Git Bash.
  c. Python 3.12 from https://www.python.org/downloads/windows/ , in four
     parts:
     c1. Install the newest 3.12.x that offers "Windows installer (64-bit)"
         (3.12.10 when this was written), not the newest version, which the
         install refuses. Tick "Add python.exe to PATH".
     c2. On the installer's last screen click "Disable path length limit"
         (it asks for administrator): the install builds about 3 GB of
         runtimes with deep paths. Missed it? In a PowerShell opened as
         administrator:
           Set-ItemProperty HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem LongPathsEnabled 1
     c3. Settings > Apps > Advanced app settings > App execution aliases:
         turn OFF python.exe and python3.exe.
     c4. Copy python.exe to python3.exe in the folder Python was installed
         to (%LOCALAPPDATA%\Programs\Python\Python312 by default): the
         installer makes no python3.exe, and the install looks for python3.
     Check, in a new Git Bash: python3 --version   prints Python 3.12.x
  d. uv, in PowerShell:
       powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
     It also puts %USERPROFILE%\.local\bin on your PATH, where dev's
     commands live.
  e. Node.js LTS, 22.12 or newer, from https://nodejs.org/ , then
     npm install -g pnpm
  f. The three agents' programs: Claude Code (Peter), Codex CLI (Aster) and
     Pi (May). Install them before dev, so the install can register the
     laya and rea tools with them:
       Claude Code, in PowerShell:   irm https://claude.ai/install.ps1 | iex
       Codex CLI:   npm install -g @openai/codex
       Pi:          npm install -g @earendil-works/pi-coding-agent
     Check each: claude --version, codex --version, pi --version (must
     print 1.x; the old @mariozechner package is deprecated at 0.73.1)

Keep your home folder (%USERPROFILE%) out of OneDrive.

After f, close every terminal and open a new Git Bash before checking
anything or running the install: each program above changes PATH, and a
window opened earlier still has the old one, so it reports installed
programs as missing.


2. Install dev
--------------

Open Git Bash normally, not as administrator, and run, with your USB's
drive letter and folder:

    bash /d/dev-usb/install.sh

To find them: ls /  lists the drive letters, and  ls /d  (or /e, ...) shows
the folder that holds install.sh. If install.sh is at the top of the drive,
the folder's contents were copied without it: run  bash /d/install.sh

If its output says the daily run or the daily check is not registered, or
laya is not installed, run the command that line prints.

It checks the prerequisites, checks every file on the USB against
SHA256SUMS, puts dev in ~/dev, restores every tool at its pinned version
(and the book PDFs, whose pins it writes to ~/.config/devarness/personal-repos.txt),
installs the reverse tools (REA, Ghidra, JADX, Apktool) from reverse/, links
the commands into ~/.local/bin and every skill into ~/.claude/skills and
~/.agents/skills, registers the laya and rea MCP servers for Claude Code and
Codex, installs the tools' Python and Node packages, registers the daily
update-tools and dev-check runs and the laya service, and ends with
new-device check. Reading "NEW DEVICE READY" means every layer the install
makes is in place; the steps in section 3 are still yours. It is safe to run
again.

The commands, skills and MCP servers then work in any folder, not only in
~/dev.

To install somewhere else:   bash /d/dev-usb/install.sh ~/somewhere


3. Log in and finish by hand
----------------------------

The install prints this list at the end too.

Always by hand: the logins, the hook trust, cship and starship, and the
ntfy topic. Steps 3, 6 and the markitdown line of step 5 are done by the
install; repeat one only if the install's output said it failed, or you
installed Claude Code or Codex afterwards.

  1. Open a new Git Bash.
  2. Log each agent in once: claude (then /login), codex login, and pi.
  3. Done by the install; repeat only if it failed. In ~/dev:
       claude plugin install superpowers@claude-plugins-official
       python3 Harness/codex-setup.py
  4. Trust dev's Codex hooks, which Codex skips until trusted. In ~/dev:
       python3 Harness/codex-hook-trust.py --trust          shows each command
       python3 Harness/codex-hook-trust.py --trust --yes    after reading them
       python3 Harness/codex-hook-trust.py --check          must exit 0
     Start Codex with codex-start, because trust is keyed to the folder.
  5. The PDF reader and the statusline. Only if the install failed it
     (without it md-pages and i18n cannot run):
       uv tool install "markitdown[all]==0.1.8"
     and always, by hand (without them only the statusline renders short),
     the Windows x64 release binaries of cship 1.8.3
     (https://github.com/stephenleo/cship/releases, the file
     cship-x86_64-pc-windows-msvc.exe, saved as cship.exe) and starship
     (https://github.com/starship/starship/releases, the file
     starship-x86_64-pc-windows-msvc.zip, unzipped to starship.exe), both
     into %USERPROFILE%\.local\bin. new-device check then shows
     statusline-tools ok.
  6. Done by the install; repeat only if it failed, or after a later
     install. The library's index. In ~/dev:
       library refresh
  7. Phone alerts: put the ntfy topic in ~/.config/devarness/ntfy-topic, then
     run notify test.
  8. A GitHub remote, only when you want one: winget install GitHub.cli,
     open a new Git Bash, then
       gh auth login --hostname github.com --git-protocol ssh --skip-ssh-key --web
     Show the key with cat ~/.ssh/id_ed25519_dev.pub and paste it at
     https://github.com/settings/keys as an account key, then run
     Harness/finish-github-setup.sh in ~/dev.

If you installed Claude Code or Codex after dev, run Harness/bootstrap.sh
in ~/dev again to register the laya and rea tools with it.


4. Check it
-----------

In ~/dev, in Git Bash:

    new-device check             must end with NEW DEVICE READY
    start-check --check --text   must say READY; DEGRADED names a step
                                 of section 3 still open
    dev-check --fast             about two minutes
    dev-check                    every gate; about 20 minutes
    rea doctor --provider ghidra --json    "healthy": true
    reverse jadx --version                 1.5.6
    claude mcp list                        shows laya and rea
    codex mcp list                         shows laya and rea

From rea doctor read only the top-level "healthy" and the ghidra
provider's "available": true. Ignore "environment_healthy": false and every
"Run rea setup" line: dev registers REA itself, and Claude Desktop, VS Code,
Hopper and IDA are deliberately not used.

Then start an agent with claude-start or codex-start in ~/dev. Pi has no
launcher: run start-check --check --text first, and start pi only when it
ends START COMPLETE.


5. If something fails
---------------------

  - "differs from SHA256SUMS": the copy is damaged. On the machine that made
    it, copy the folder to the USB again and check the copy with:
    bash Harness/usb/pack.sh verify <the folder on the USB>
  - "Windows refused a symlink": Developer Mode is off (step 1a).
  - "python3 is ..., not 3.12": step 1c, including the aliases.
  - "is not registered" (the daily run or check) or "laya is not
    installed": run the command printed on that line, in the same Git Bash.
  - A file that vanished, or a reverse tool that will not start: look in
    the antivirus quarantine before anything else.
  - Anything else: the line above it names the step; the install can simply
    be run again once it is fixed.
