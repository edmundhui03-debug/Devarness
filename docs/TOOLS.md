# The Library preserves reusable tools behind explicit setup

> **2026-10-21** · Aster · `current`
>
> The table lists the exported command surface. Python commands accept
> `python3 Library/bin/NAME`; shell commands run through Bash. Their source
> and regression tests are included, while optional runtimes and accounts
> require deliberate local installation.

## Core onboarding runs without provider credentials

Use tools/bootstrap.py, tools/session.py and tools/check.py first.
See [verification commands](VERIFICATION.md) for full acceptance and explicit
partial reruns after a failure.
The source manifest lists public URLs and exact commits. Fetching a
repository does not execute its code or register it with a client.

## The command table separates capabilities from readiness

| Command | Purpose |
| --- | --- |
| agent-memory | Find and check the current checkout's optional Claude Code memory folder. |
| archify | Pinned Archify: --install links this device; --check verifies; other args forward. |
| books | books — the book library as page-marked Markdown in Books/text/, never tracked or synced.  |
| browser | Pinned shared Playwright CLI. Use --agent peter/aster/may to isolate sessions. |
| claude-start | Checkout-local launcher; inspect source and --help. |
| codex-start | Checkout-local launcher; inspect source and --help. |
| dashboard | dashboard — write the snapshot the developer's dashboard reads.  |
| dev-check | dev-check — run every dev checker and both test trees, and print one table.  |
| diagram | dev diagram helpers using an isolated Python; source clone remains unchanged. |
| fds-setup | Install pinned NIST FDS + Smokeview in the ignored dev runtime, then prove it.  |
| i18n | i18n — give a dev HTML page an English <-> Cantonese toggle.  |
| laya-service | laya-service — dev's short decisions through laya: one local service, trusted above a threshold.  |
| learn-claude | Portable entry point; help and --check never launch a model. |
| library | library: search, pick and check the offline catalogue of every tool, skill, agent and guide. |
| md-format | md-format — the dev markdown house format: check, index and repair.  |
| md-pages | md-pages — convert a document to Markdown with page markers.  |
| new-device | new-device — which dev setup layers this device has, and the command that fixes each missing one.  |
| ngspice-setup | Install pinned ngspice in the ignored dev runtime, without a package manager.  |
| notify | notify — push a phone alert through ntfy when an agent finishes work.  |
| ocr | Local Docling OCR with page-marked Markdown. Does not replace md-pages. |
| rea | rea — run REA's CLI and stdio MCP server from the local runtime, nothing global, no console pop-up.  |
| reverse | reverse — run reverse-skill's local static tools (JADX, Apktool, the JDK's java) from the runtime.  |
| start-check | Checkout-local launcher; inspect source and --help. |
| statusline | Explicit configs keep the dev display consistent even in nested repositories. |
| task-recall | task-recall — name a task and get what is done, what is open, and the next step.  |
| taskboard | taskboard — start the Codex Taskboard in its safe shape, on demand.  |
| tieitup | tieitup: TieItUp's changed-line check, its whole-file jobs and its record.  |
| understand | Run the pinned local Understand-Anything helpers. No model or commit hooks. |
| update-tools | update-tools — keep every device on the pinned tools, and advance the pins.  |
| video-study | video-study — study a video from what is said and what is on screen.  |

## Optional integrations retain platform requirements

Python core checks target Windows, macOS and Linux. Shell launchers
require Bash; Windows uses Git Bash. The dashboard requires Node.js
and its own npm dependencies. OCR and document conversion use isolated
Python runtimes. PyroSim and its licensed simulator are Windows-only;
reverse tools, EDA applications, provider CLIs and MCP services require
their documented prerequisites and authorized targets. Native skill
symlinks on Windows require suitable permissions or Developer Mode.

Legacy device-completeness checks, USB migration and specialist tests
retain assumptions about a fully installed workspace. They are source
references and optional integration checks, not part of portable core
readiness. Do not run global installers or migration tools until their
effects match your intended local setup.

The bilingual checker is a Bash launcher. Run `bash Library/bin/i18n` with
a Python interpreter that has Beautiful Soup; select its executable with
`DEVARNESS_I18N_PYTHON` if `python3` on PATH is unsuitable. The bootstrap
does not install that dependency. Markdown checks use Python directly.

For example, from Git Bash on Windows, create an isolated HTML environment:

```bash
python -m venv .venv-html
.venv-html/Scripts/python.exe -m pip install beautifulsoup4
export DEVARNESS_I18N_PYTHON="$PWD/.venv-html/Scripts/python.exe"
bash Library/bin/i18n selftest
```

On macOS/Linux use `python3` for the first command and
`.venv-html/bin/python` for the interpreter paths. Installation downloads
the optional dependency; record its resolved version in your project's lock
file when reproducibility is required. No global launcher is needed.
