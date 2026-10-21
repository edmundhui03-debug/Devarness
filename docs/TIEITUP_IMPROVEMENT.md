# TieItUp reuses traversal work and reports incomplete checks explicitly

> **2026-10-22** · Aster · `current`
>
> A local audit became faster with byte-identical findings. Checker faults
> now produce an unverified status while edits remain nonblocking. A bounded
> onboarding experiment supported clearer setup facts over extra review prose.

## Cache one file's traversal without changing rule coverage

The reference is commit `5abfc111faa95231ff90ecaa5431b97429f41d80`.
Profiling an audit of its `Library/bin/tieitup` found repeated AST traversal
in `Source.nodes`. The change retains the traversal per Source and returns
a fresh filtered list for each query. All existing checks remain enabled;
separate files and malformed Python retain their previous behavior.

One warmup and five alternating-order, in-process audit samples used the
same frozen source on Windows. Both versions emitted exactly the same 65
findings, including their IDs, ordering and messages.

| Version | Five audit times, seconds | Median |
| --- | --- | --- |
| Reference | 17.719, 14.856, 6.634, 4.734, 21.271 | 14.856 |
| Cached traversal | 8.053, 6.175, 10.747, 4.841, 7.069 | 7.069 |

This is a 52.4% lower observed median for one audit under variable host load.
It does not establish agent throughput or performance on other platforms.
The frozen source SHA-256 was
`243775261ee791d107cbb12a77ca9a82956fe7cf455979645ddaa34491f55237`.
The output hash was
`9b58f9e73b001732209fd75b599c849fe5f05a0910fcd6a667bb1b4d9c67ce1f`.

To repeat the comparison, save that commit's checker source, load each
checker version separately and audit the same saved file, alternating order.
Require identical output before interpreting timing. Run
`python3 Library/tests/test_tieitup.py SourceTraversal` for the regression:
the old code walks three times where the new code walks once. The test also
checks ordered results, caller list mutation, separate files and invalid syntax.

## A checker fault must not look like a clean edit

The code hook previously returned no feedback for both a clean file and a
checker error. It now emits `UNVERIFIED` on stderr, nonzero exit, timeout
or launch failure. Completed checker findings remain visible alongside
stderr errors. Diagnostic stderr stays out of injected context, and the
hook still exits zero. A timeout does not inject partial checker output.

Regression tests invoke the hook against failing and clean checker fixtures;
focused tests cover timeout, launch failure and mixed findings plus stderr.
The old hook fails the fault-feedback tests. The portable release runner now
includes the whole post-edit hook suite so this boundary is checked in CI.
This proves the tested consumer behavior, not every client session's loading.

## The onboarding experiment preferred verified facts to extra process

Three Claude Code probes used the same source-reading runbook task and
reference commit. The actual model was `claude-opus-5-5`, CLI 2.1.292.
Each had a USD 1 CLI cap and 300-second timeout, within the owner's USD 4
allocation. Reported total cost was **USD 1.2843402**; no fourth call ran.

The common executor restricted available tools to Read, Grep, Glob, Edit and
Write, loaded project settings only and disabled MCP servers. It retained
project hooks. This was a controlled comparison, not the stock runner's
default configuration. No application project or credential was in the task.

Ten compound criteria were frozen before the reference: private template
origin; tracked source and intent; core/source/runtime distinction; three
root-level launch commands; actual Claude/Codex integration; Pi trust and
Python prerequisite; Ponytail/TieItUp/pstack review; frozen ref/model and
budget; approval/shared-clone/acceptance limits; bounded honest delivery.

| Candidate | Criteria passed | Lines (limit 110) | Tool calls | Seconds | Reported USD |
| --- | --- | --- | --- | --- | --- |
| Reference | 3/10 | 114 | 16 | 98 | 0.389439 |
| INV: extra final-artifact review prose | 6/10 | 110 | 22 | 183 | 0.474302 |
| DOM: verified setup facts in README | 9/10 | 109 | 19 | 120 | 0.420599 |

The parent graded saved artifacts against source; grading was manual and
not blinded. One run per candidate, API caching and variable host load limit
causal claims. DOM still omitted the shared-clone warning in its generated
runbook. The maintained guide includes that warning.

- Kept: the verified README facts; they improved coverage in this task.
- Dropped: the extra review paragraph; DOM met the length bound without it
  and had better coverage with fewer calls. No global review rule was added.
- Composition: adopt DOM whole, so a different combined harness needed no
  fourth paid probe. The code cache and fault feedback have separate offline
  regression and timing evidence; this task did not measure coding quality.

Verdicts for the instruction changes are **confounded**; adoption is not
proof of general improvement. Raw trajectories and machine state stay ignored.
NO_ENTRY: this sample does not justify a new general lesson.

## Verification records what actually ran

`fixed` · affected regressions, independent review and privacy scans passed

The first full portable run passed all 18 commands, including 80 TieItUp
tests in 158 seconds. After the coverage repairs, 17 commands passed and
the repeat TieItUp run hit the runner's 600-second limit. A standalone
verbose rerun passed all 80 tests in 600.672 seconds, including the
five-second large-file assertion. The suite now gets 900 seconds; other
suite budgets, per-call limits and functional assertions are unchanged.
The cause of the runtime variation is not established. The narrow audit
timing above does not predict full-suite or end-to-end agent latency.

The full i18n suite passed 16 tests with no skips using an explicitly
selected existing Beautiful Soup runtime; its Python body is unchanged.
The default host run skips unavailable optional dependencies. Markdown's
selftest passed 63 controls; known bad traversal and checker-fault controls
reject the previous implementations. Probe helper tests passed 15 cases.

Independent source reviews found no actionable regression in their selected
scope. Tracked-content/history scans and Gitleaks reported no findings.
Current hosted platform results belong to the commit's GitHub checks;
optional client authentication and all specialist runtimes are unverified.
See [the setup guide](GETTING_STARTED.md) and [coverage audit](COVERAGE.md).
