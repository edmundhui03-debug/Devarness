# Verification retains failures and supports explicit partial reruns

> **2026-10-22** · Aster · `current`
>
> Full acceptance uses the default command below. Bounded checker faults
> remain failures while later checks continue, and each command reports its
> elapsed time. Focused reruns reduce iteration work and remain partial.

## Full acceptance runs every portable command

From the repository root:

```sh
python tools/check.py
```

The default runs bootstrap, core controls, the release/history scanner and
all 15 deterministic suites. Original deadlines remain 600 seconds, with
900 seconds for TieItUp. A nonzero exit, timeout or launch error makes the
final command fail. Remaining suites still run after these bounded faults.
Syntax errors in tracked Python stop before command execution.

Per-command output retains the last 8,000 characters of each output stream;
timeouts retain available partial output. Redirect output to a local ignored
log when a lasting receipt is needed. Optional runtime integrations and real
model quality remain separate verification tasks.

## Focused reruns repeat affected checks without full acceptance

```sh
python tools/check.py --only test_post_edit_check test_tieitup
python tools/check.py --only core release
python tools/check.py --core-only
```

`--only` uses the names listed by `--help`: `bootstrap`, `core`, `release`,
or a deterministic suite's filename without `.py`. Unknown names and mixing
`--only` with `--core-only` are usage errors. Duplicate names run once.
Focused and core runs print `PARTIAL` in their final summary, including on
failure. Run the default full command before release.

This avoids unrelated checks during iteration; it does not make the full
test tree faster or establish coverage of omitted checks. No passing result
is cached, no test is run concurrently, and no deadline is shortened.

## Boundary controls distinguish failures from runner errors

`tests/test_check.py` fixes the original default command list and deadlines,
then exercises continuation and selection through the CLI entry function.
`tests/test_check_process.py` runs real child processes for timeout, nonzero
exit and missing-executable controls. The timeout child emits a marker before
sleeping, so preserving partial output is checked at the subprocess boundary.
