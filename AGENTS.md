# Codex uses Devarness rules and verifies its own checkout

> **2026-10-21** · Aster · `current`
>
> Read CLAUDE.md as the shared router and README.md for setup. Codex is
> an optional review and execution adapter in the Claude Code centred
> workspace. Keep credentials and model choices in local client settings.

## Each working turn starts from current evidence

Run `python3 tools/session.py --check --text`, read the current task
record and apply the compaction rule in CLAUDE.md. Load applicable
skills from `.agents/skills/`; optional upstream skills require setup.
Never resolve this checkout through global launcher links.

## Reviews follow reachable failures and independent verification

Trace changed callers, serialized data and lifecycle boundaries. Look
hardest at hook concurrency, Git conflict recovery, nested repositories,
portable paths, secrets, tests passing for the wrong reason and stale
documentation. Label source evidence, runtime evidence and uncertainty.
A same-model reviewer is a separate read, not model diversity.
