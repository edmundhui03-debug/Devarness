# Devarness starts with a small core and tracks verified changes

> **2026-10-23** · Aster · `current`
>
> Start with the portable core, add library capabilities for a demonstrated
> task, and record the checks before expanding. The public source now omits
> the personal dashboard and inherited private project/device records. Reusable
> tools live in Harness/. Release controls protect the current tree; earlier
> history is retained by owner decision.

## Contents

- [One task record carries the objective, checks and next action](#one-task-record-carries-the-objective-checks-and-next-action)
- [The dashboard and directory update establishes the public core](#the-dashboard-and-directory-update-establishes-the-public-core)
- [Verification distinguishes the core from optional capabilities](#verification-distinguishes-the-core-from-optional-capabilities)
- [The privacy follow-up removes inherited project and device records](#the-privacy-follow-up-removes-inherited-project-and-device-records)
- [Legacy onboarding shares the core and updater cleanup stays bounded](#legacy-onboarding-shares-the-core-and-updater-cleanup-stays-bounded)
- [Further expansion waits for a concrete task and evidence](#further-expansion-waits-for-a-concrete-task-and-evidence)

## One task record carries the objective, checks and next action

Use one task record in each private project copy, `docs/PROJECT.md`, for
its objective, owner, state, acceptance checks, decisions, last verified
result and next action. Raw prompts, private evidence and credentials stay
outside public commits. The public harness's current work is tracked here.

## The dashboard and directory update establishes the public core

`fixed` · Dashboard removal and Windows upgrade repair published

| Work | State | Evidence or next action |
| --- | --- | --- |
| Remove dashboard, bridge, taskboard, tests and discovery entries | verified | 87 personal feature files removed; independent dependency review found no remaining feature |
| Reject a reintroduced dashboard in the release tree | verified | Regression tests reject tracked dashboard files under both Library/ and Harness/ |
| Start with core, then add a needed library capability | documented | README.md and docs/GETTING_STARTED.md |
| Keep one task record with results and next steps | documented | This record and the private-project guide |
| Move Library/ to Harness/ | verified | 330 tracked files, 31 skill links; source, manifests, launchers, guides and fixtures agree |
| Run full portable verification | passed | 9d30b3e: default tools/check.py, all 18 commands pass; 291 tests, 6 environment-dependent skips |
| Repair Windows skill links after an existing checkout upgrades | verified | Native regression fails before the repair, passes after; all 29 core tests pass |
| Check the minimal discovery catalogue | verified with optional limits | Index has no diagnostics; the full optional pick benchmark is below its mark with sources absent |
| Publish and verify hosted checks | verified | 9d30b3e published on both existing branches; Linux, macOS and Windows pass in [GitHub Actions](https://github.com/edmundhui03-debug/Devarness/actions/runs/39902543391) |
| Retain public history | owner-decided | Remove the current feature only; no history rewrite or force push |

The release guard checks the staged tree, including existing tracked files;
ignore rules protect future untracked copies. Historical secret scanning
remains enabled. An ordinary source removal does not certify that the old
dashboard is absent from history, caches or existing clones.

## Verification distinguishes the core from optional capabilities

The full portable run on 9d30b3e used the default list and existing timeouts.
The harness-step helper and probe-control suites also pass, 15 tests each,
without model calls. Eight core documents pass the Markdown check. The
broader Markdown check reports 207 findings in six files, matching the
unchanged baseline's count. Renamed library.py also triggers inherited
TieItUp findings because the checker treats the moved file as new code;
review confirmed path updates and removal of its dashboard coverage entry.

Minimal discovery refresh and index checks pass with no diagnostics.
The optional catalogue benchmark scores 18/23 against a mark of 20, with
reverse-engineering, KiCad, Laya and scholar sources absent. Optional
coverage is incomplete on this minimal checkout. These results do not
claim readiness for optional services, tools or model integrations.

Upgrading the existing Windows checkout exposed Git-created file links to
skill directories. Bootstrap now inspects their native link attributes
before following them, then recreates them as directory links. The native
regression verifies repair, repeat setup and unchanged target contents.
The updated local checkout reports READY with 4/29 optional sources and
29 readable skill links. Independent source review found no remaining
finding in the repair. Follow-up pushes run the same portable matrix;
the [workflow page](https://github.com/edmundhui03-debug/Devarness/actions/workflows/portable.yml)
records their current result.

## The privacy follow-up removes inherited project and device records

`fixed` · current-source cleanup and portable acceptance verified

Two independent source reviews covered 256 tracked documentation, configuration,
script and fixture blobs at 8efe7c9. A repository-wide lexical screen covered
all 330 tracked blobs, including skill-link metadata; no optional clone target,
private project, personal profile or transcript was used as public source.
Public attribution, upstream links and clearly synthetic test values remain.

| Work | Result |
| --- | --- |
| Generalize private product examples and study-note citations | Programming rules and validation requirements retained without product symbols or source locations |
| Remove account/device chronology and personal fixture provenance | Quota timestamp, named project workflow, machine anecdotes removed; fixture session metadata made explicitly synthetic |
| Remove a private simulation-scoring dependency | The standalone exporter writes raw sensor frames and keeps sampling, unit and non-finite checks |
| Repair the public guide build | Missing private chart inputs get an explicit note; orphan tests for an omitted helper removed; English/Cantonese sources rebuilt together |
| Remove remaining private workflow consumers | Personal course exemptions and project anecdotes removed; orphan browser checks for omitted private pages removed |
| Isolate optional page-check configuration | Personal clone discovery requires explicit opt-in and uses the Devarness namespace |
| Add current-tree privacy controls | Existing publish-check matcher reused for personal home paths and email addresses in index blobs, link metadata and modified working files |
| Bound working-file reads to the checkout | Outward directory links are rejected before content is read |
| Keep runtime caches and updater state private | Recall memo, updater lock and log directory ignored and rejected even if force-staged |
| Inspect hosted metadata | Both branches share the audited source; no issues, pull requests or releases; wiki, Pages and discussions disabled |

The staged personal-path/email control fails on the reference scanner even
when its working file is clean, then passes with the new gate. Placeholder
paths and example/noreply addresses pass without reading personal settings.
A separate outward-directory-link control fails before containment, then
passes without reading the excluded target. Retained-history controls keep
credential scanning active without applying the new current-only policy to
past personal content. Review found no remaining actionable scanner finding.

Core controls pass, 35 tests. The affected memory suite passes, 27 tests;
a stale renamed slug fixture was repaired at its synthetic input/expectation.
The guide passes 37 tests. Its final page has 1,231 tagged and translated
elements, no missing translations and a working toggle; browser checks verify
the final heading in both languages, UTF-8 and no horizontal overflow.
All 18 portable commands pass, including the final 17-test page suite;
the last runtime-state guard also passes its affected core checks. Recall
integration checks pass against the public task record, with empty test memory,
rather than depending on omitted private documents. Six affected documents pass
format checks, and the final index contains 328 paths and 31 skill links.
The portable [workflow](https://github.com/edmundhui03-debug/Devarness/actions/workflows/portable.yml)
records hosted acceptance for each published branch.

The page check's personal-config control fails before the repair: an unrelated
workspace's clone list hides an authored page without opt-in. It passes after
the repair, verifies explicit Devarness opt-in, and rejects the unrelated
namespace even when opted in. Ordinary authored pages still require a toggle;
saved vendor datasheets remain exempt under the existing general rule.
The discovery control exercises the shipped enumeration function directly
without the optional HTML parser, so minimal CI still verifies these boundaries.

Runtime-state controls reject forced staging of the memo, updater lock and
updater logs; each failed before its corresponding repair. The existing
updater ignore regression now passes. The optional course guide links directly
to its verified public pin, so its references work without installing a clone.

These controls establish deterministic behavior, not a measured improvement
in model reasoning. Generic patterns cannot identify every confidential
project fact; source review remains part of publication. Git history, old
clones and past hosted artifacts remain outside current-source removal.

## Legacy onboarding shares the core and updater cleanup stays bounded

`fixed` · local acceptance and the legacy-console regression are verified

The reference at 9069c7e reproduces 33 failures and one skip in 38 legacy
new-device tests. The checker parses launcher and MCP loops removed from the
portable bootstrap. The replacement delegates to the shipped core readiness
helper, validates the selected Git root, and never imports selected-root code
or inspects personal settings (`Harness/bin/new-device:16`). Compatibility
flags and exit statuses remain; JSON schema 1 retires the old layer report.
Ten portable controls pass, including two that fail on the old checker.
Mutations that import selected-root code or accept a nested root are rejected.

The canonical updater reference completes 138 tests in 454.2 seconds, with
one failure and two errors: two tests omit the now-required personal-repository
opt-in, and one expects automatic global setup from the old bootstrap.
Those fixtures now match the portable boundary and use disposable homes.
The hung-CLI control passes on the reference; the earlier 600-second cutoff
during concurrent extra checks does not establish a production hang.

Two new controls expose a separate timeout risk: Windows taskkill has no
deadline, and a cleanup failure can escape the timeout result. Each cleanup
wait is now bounded at five seconds; failed cleanup returns timeout status
124 with a diagnostic (`Harness/bin/update-tools:171`). The direct process
kill is still attempted when tree cleanup fails. Nine focused checks pass,
including the existing hung-CLI, slow-installer and rollback controls.
The complete repaired updater suite passes all 140 tests in 463.6 seconds
on Windows, within the existing 600-second acceptance deadline. These runs
establish correctness controls; they do not establish a speed improvement.

Kept: shared readiness and bounded cleanup, supported by failing controls.
Kept unchanged: command budgets, personal opt-in and explicit optional setup.
Both deterministic suites join the existing sequential portable acceptance
list (`tools/check.py:21`), without a larger deadline or new runner.
Source reviews supply an independent same-model read, not model diversity.
No paid model experiment or model-quality improvement is claimed. Full
optional-install readiness remains outside the core report. This maintenance
adds no service, dashboard, dependency or global setup; history is retained.

Local acceptance at 55f059b passes all 20 default commands: 35 core controls,
10 portable onboarding controls, 140 updater tests and the remaining
deterministic tools. TieItUp passes 80 tests with one optional skip. The
staged privacy check is clean; inventory matches 328 files and 31 skill
links. Changed Markdown and staged TieItUp checks pass. The existing
[workflow](https://github.com/edmundhui03-debug/Devarness/actions/workflows/portable.yml)
records Linux, macOS and Windows acceptance for the published commit.

Hosted Windows acceptance at 55f059b exposed a parent-console encoding bug:
captured UTF-8 output could not be printed through CP1252. A strict legacy
console control reproduces the exception, then passes after the runner
configures its output streams as UTF-8 (`tools/check.py:59`). All 36 core
tests pass. Existing failure statuses, command deadlines and the 20-command
list remain covered; hosted acceptance reruns on the corrected commit.

The next Windows run exposes two fixture decoding failures: Git subjects
and updater banners are UTF-8, while test capture defaults to CP1252.
All seven text captures in the updater tests now name UTF-8 explicitly.
The two affected tests force the legacy default around their real reads;
both fail before the fixture repair and pass afterward, retaining exact
Unicode assertions, deadlines and disposable homes. The patch permits an
absent private encoding helper on Python 3.9; that runtime was not executed.
Production updater behavior is unchanged by this fixture-only follow-up.
Final acceptance remains the default 20-command hosted workflow.

## Further expansion waits for a concrete task and evidence

`open` · next action: start one small project task with the core commands

Use Harness/ for reusable tools and retain optional integrations. Add no new
service, dashboard, installer, automatic model call or directory migration
after this rename. Future harness changes should name one task, compare the
reference and candidate on it, and record an outcome or KEEP_BASE.

Historical export evidence remains in docs/ADAPTATION.md; later verification
records supplement it without treating earlier counts as the current suite.
