#!/usr/bin/env bash
# Stop: push a phone alert through ntfy when a turn ran 10 minutes or more.
# The rule is in Library/bin/notify. With no python3 it says nothing and never blocks.
ROOT="$(cd "$(dirname "$0")/../.." && { pwd -W 2>/dev/null || pwd; })"
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 "$ROOT/Library/bin/notify" hook claude
