# Devarness starts with a small core and tracks verified changes

> **2026-10-29** · Aster · `current`
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
- [A fresh public clone must finish the documented setup](#a-fresh-public-clone-must-finish-the-documented-setup)
- [Native client checks verify the Devarness environment first](#native-client-checks-verify-the-devarness-environment-first)
- [Default release checks retain the Codex setup regressions](#default-release-checks-retain-the-codex-setup-regressions)
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

## A fresh public clone must finish the documented setup

`fixed` · fresh public setup and all 20 checks verified at source commit 3306810

Test an anonymous public clone in a path with spaces, with a new Python
environment and disposable home. Preserve the core-first boundary: no
client login, paid model call, service or global configuration is needed.
The owner authorizes fixes for reproduced setup failures and a normal
public update; earlier Git history remains intact.

A synthetic Git clone stopped at `--no-checkout` reproduces misleading
fetch success at the exact pin with `SKILL.md` absent. The baseline
existing-source path checks HEAD alone (`tools/bootstrap.py:75`). INV checks
tracked changes before reporting success; candidate DOM only documents
the interrupted state. INV's five-state regression rejects missing and
modified tracked files while accepting clean or untracked-only sources
and retaining the off-pin refusal. Both bad states fail before the repair
and pass afterward; local file contents stay unchanged. Keep the small
script guard and its guide note. No reset, recovery framework or new
dependency is added; no model-quality or speed improvement is claimed.

Actual optional setup finds two metadata faults. With Windows text link
placeholders and diagram-design unfetched, catalogue refresh exits 1.
Pointing that source directly into its pinned Harness directory lets the
existing optional-source resolver handle it; its control fails before
the correction and passes afterward. No new link resolver is needed.
Repeated fetch also rejects superpowers because its recorded object is an
annotated tag. The manifest now names the tag's existing commit bb92a777;
the checked-out source version stays the same. All five fetched pins are
verified as commit objects. Repeated fetch passes; catalogue refresh returns
122 entries and zero diagnostics. Search, catalogue check, session and prompt
hook JSON pass. Both skill-link runs succeed, with 29 of 31 links readable;
the two remaining links require the unfetched optional diagram source.

The untouched public clone passes bootstrap and the three-command core
acceptance in 227.62 seconds before parser installation: 36 core tests and
the retained-history scan pass. Its fresh virtual environment initially has
only pip. The repaired clone passes all 20 portable commands, including
38 core tests, 10 portable onboarding tests, 140 updater tests in 485.278
seconds and 80 TieItUp tests in 116.994 seconds. Current-tree and retained
history scans have zero findings; the inventory matches all 328 tracked
files. Existing optional/platform-specific skips remain explicit in the
runner output. No client login or optional runtime readiness is claimed.

A second anonymous public clone verifies published source commit 3306810
using the documented Windows clone flags, a path with spaces and another
empty home and virtual environment. Its 38 core tests pass before parser
installation. Both source-fetch runs, both link runs, locked parser install,
refresh, search, catalogue check, session checks, legacy core check and
prompt-hook JSON pass. Every fetched HEAD equals its manifest commit;
the final Git tree is clean. All six hosted jobs pass the default 20 commands
at that exact source commit: Linux, macOS and Windows on both public branches
([main acceptance](https://github.com/edmundhui03-debug/Devarness/actions/runs/40048976892),
[verification acceptance](https://github.com/edmundhui03-debug/Devarness/actions/runs/40048976370)).
This result-record follow-up changes documentation only; the runtime source
remains identical to the tested commit. Continue with one small project task;
additional client integrations still need their own explicit setup and checks.

- [x] Run the documented core bootstrap, acceptance and session commands
  before installing optional parser dependencies or source capabilities.
- [x] Fetch the five documented coding sources at their public pins;
  link skills twice, install the locked parser, refresh and search discovery.
- [x] Reproduce any failure, keep the smallest supported repair, and verify
  its regression controls and actual setup command against the same task.
- [x] Complete the default portable checks; review the diff, privacy and
  inventory; prepare only reusable source and this result record.
- [x] Verify the published commit through another fresh clone and hosted
  Linux, macOS and Windows checks; report optional runtime limits explicitly.

## Native client checks verify the Devarness environment first

`fixed` · native client checks and final portable acceptance pass

The reference is public commit 683a5bb. A new public clone in a path with
spaces uses disposable client configuration, no copied credentials and no
model turns.
Claude Code 2.1.292 loads the real SessionStart hook and validates its READY
context. Codex CLI 0.163.0 starts its app-server with strict configuration,
loads the project compaction limit of 300000, lists skills without errors,
and starts an ephemeral thread. Its empty hook list is intentional.
Pi 1.3.0 answers offline RPC state and command requests. Its native resource
loader loads the project extension, APPEND_SYSTEM and AGENTS.md, and its
event dispatcher accepts the shared hidden discovery guidance. These
checks verify startup and resource loading, not provider authentication or
paid inference (`tools/session.py:48`, `.codex/hooks.json:1`,
`.pi/extensions/dev-discovery.ts:5`).

Codex also lists global user and system skills on this Windows device. The
16 repository-scoped skill paths were verified against the new clone;
complete OS-account isolation is untested. Optional plugin installations
and authenticated model behavior are outside these checks.

The Python-only Windows control starts the core with Python 3.12 but fails
Claude's actual hook with command-not-found; Claude itself still exits 0.
The getting-started guide now checks the literal python3 prerequisite for
both hook clients and repairs skill links before checking loaded resources.
No automatic installation or client configuration rewrite is introduced.

Frozen failure controls compare the reference with the smallest script
repairs. A documentation-only candidate cannot correct lost checker status,
destructive marketplace recovery or an uncaught process-launch failure.
The retained changes report document-checker failures as UNVERIFIED without
copying raw stderr, preserve an existing marketplace on any add failure,
and return the hook helper's documented error status when its server cannot
launch. Genuine marketplace source conflicts now require explicit resolution;
setup does not remove registrations automatically. No model-quality or speed
claim is made. Raw client logs and review reports remain ignored.

A help invocation exposed another setup boundary: the optional Codex setup
helper ignored arguments and entered installation. It now parses arguments
before reading the plugin registry; isolated controls verify help exits 0,
unknown options exit 2 and neither changes the disposable home. Touched
helper comments also replace inherited account anecdotes with generic
rationale. Public/legal attribution is retained.

Independent review found that the HTML test could accept an UNVERIFIED
checker result as a document finding. It now requires the actual missing
toggle diagnostic and rejects UNVERIFIED. A synthetic checker failure
passes the old assertion and fails the strengthened one. All 21 post-edit
tests pass with Bash and Beautiful Soup available, without skips. The
Codex specialist suites run 25 tests with one absent optional-source skip;
the three legacy settings assertions and the Pi event-adapter check pass.

The first full portable run exposed a 0.5-second test deadline that could
expire before Python printed its startup marker. The real timeout test now
uses its existing five-second helper allowance; production deadlines stay
unchanged. A delayed-start control reproduces the missing marker at 0.5
seconds and preserves it at five seconds, while both runs still report
TIMEOUT. All 38 core tests pass on the rerun (`tests/test_check_process.py:20`).

The final frozen candidate passes all 20 commands in `python tools/check.py`,
including the current-tree and retained-history scans, 140 updater tests in
565.391 seconds and 80 TieItUp tests in 165.888 seconds. Existing optional
source skips remain explicit; no production timeout was extended. Both
public branches run the same portable Linux, macOS and Windows matrix;
their hosted results are retained in the
[portable workflow](https://github.com/edmundhui03-debug/Devarness/actions/workflows/portable.yml).
Keep the core small and add further integration changes only for a reproduced
failure or a concrete project need.

A second fresh public clone verifies published source commit 8f7a10b with
the documented Windows clone flags and skill-link repair. Claude startup,
Codex project configuration and resources, Pi offline RPC and native event
dispatch all pass again; the clone's tracked tree remains clean. All six
hosted jobs pass the default 20 commands at that source commit:
[main acceptance](https://github.com/edmundhui03-debug/Devarness/actions/runs/40278463538)
and [verification acceptance](https://github.com/edmundhui03-debug/Devarness/actions/runs/40278463497).
This follow-up records the results only; its runtime source matches 8f7a10b.

## Default release checks retain the Codex setup regressions

`fixed` · both Codex suites now run in the passing 22-command acceptance

The release command omitted the two existing Codex specialist suites after
the client setup repairs. A synthetic failure in either suite still allowed
the reference runner to report success because it never invoked that suite.
The standard list now includes both suites, using disposable homes and a
fake app-server; client installation, login and model calls are unnecessary
(`tools/check.py:20`, `Harness/tests/test_codex_setup.py:31`,
`Harness/tests/test_codex_hook_trust.py:5`).

The frozen task is to reject either Codex regression through the default
release command and continue the remaining checks. A documentation-only
candidate leaves that failure undetected; adding the existing suites makes
both failing controls return nonzero. The runner's 11 selection and failure
tests pass after failing against the reference. This keeps the existing
runner, timeouts and optional-source skip instead of adding a framework
(`tests/test_check.py:77`). No model-quality or performance claim is made.

The actual release CLI also runs against an isolated synthetic repository.
For each failing Codex suite, the reference exits 0 after 20 commands;
the candidate exits 1 after all 22 commands and names the failing suite.
These controls verify invocation and failure propagation, while the real
specialist suites verify the client helpers separately.

Full local acceptance passes all 22 commands on Python 3.12.10, including
39 core tests, the 25 Codex tests with one absent optional-source skip,
140 updater tests in 575.442 seconds and 80 TieItUp tests in 139.139 seconds.
Core-only and named reruns remain explicitly partial. Existing source and
platform skips stay visible; deterministic checks do not certify native
client authentication or model behavior. Source review, Markdown and
changed-line checks pass (`tools/check.py:99`, `tests/test_check.py:72`).

The current-tree and retained-history scans report no findings. Public
repository metadata has no actionable personal value; the 328 tracked paths
are unchanged. History is retained. Both public branches use the same
[portable workflow](https://github.com/edmundhui03-debug/Devarness/actions/workflows/portable.yml)
for hosted acceptance after publication. Further changes still need a
concrete failure or task; this run adds no new helper, service or dependency.

## Further expansion waits for a concrete task and evidence

`open` · next action: start one small project task with the core commands

Use Harness/ for reusable tools and retain optional integrations. Add no new
service, dashboard, installer, automatic model call or directory migration
after this rename. Future harness changes should name one task, compare the
reference and candidate on it, and record an outcome or KEEP_BASE.

Historical export evidence remains in docs/ADAPTATION.md; later verification
records supplement it without treating earlier counts as the current suite.
