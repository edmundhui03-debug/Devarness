# The Library follows the root router and preserves upstream sources

> **2026-10-22** · Devarness · `current`
>
> Read the root router before changing tools or skills here. Public pins,
> local adapters and runtime activation are separate; no earlier device's
> setup record establishes readiness on your machine.

## Reuse existing tools and leave fetched clones unchanged

Follow [the shared router](../CLAUDE.md), [the tool catalogue](../docs/TOOLS.md)
and [the setup guide](../docs/GETTING_STARTED.md). Search the local catalogue
before adding a duplicate capability. Use checkout-local commands, for
example `python3 Library/bin/library search "task"`; shell launchers need
Bash. On Windows use Git Bash for shell tools and an available Python.

`repos.txt` pins public upstreams. Keep fetched clones clean and unmodified;
put integration changes in local adapters and preserve third-party notices.
Review a pin update and its affected instructions before adopting it.

## Readiness requires a real local check

Use `python3 tools/check.py` from the root for the portable release gate.
Specialist applications, MCP servers, plugins and provider logins need their
own explicit setup and checks. Never infer activation from a source path.
Keep authentication and local evidence outside tracked files. See
[the coverage audit](../docs/COVERAGE.md) for what was retained and tested.
