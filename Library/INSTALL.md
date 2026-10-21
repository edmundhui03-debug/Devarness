# Installation starts with portable checks and explicit optional choices

> **2026-10-22** · Devarness · `current`
>
> Use the maintained setup walkthrough for a fresh project. Bootstrap
> checks the checkout and fetches only explicitly selected public pins;
> local authentication and specialist runtimes need separate setup.

## Start from the current tool catalogue

Follow [the setup guide](../docs/GETTING_STARTED.md) for Windows, macOS and
Linux and [the tool catalogue](../docs/TOOLS.md) for specialist prerequisites.
From the root, `python3 tools/bootstrap.py --list` shows public pins;
`--fetch NAME` fetches source and `--link-skills` repairs local links.
Use `python` on Windows if that is your interpreter's command.

## Readiness requires a real local check

Run `python3 tools/session.py --check --text` and `python3 tools/check.py`.
No default bootstrap installs global launchers, changes client settings,
registers services or supplies credentials. Legacy installers are optional
source references: inspect their effects before invoking them. Neutral
setup cards do not reproduce any user's private installation records.
