# Devarness starts with a small core and tracks verified changes

> **2026-10-23** · Aster · `current`
>
> Start with the portable core, add library capabilities for a demonstrated
> task, and record the checks before expanding. The current update removes
> the personal dashboard, moves reusable tools into Harness/, and adds a
> release boundary against the dashboard's return. Earlier history is retained.

## One task record carries the objective, checks and next action

Use one task record in each private project copy, `docs/PROJECT.md`, for
its objective, owner, state, acceptance checks, decisions, last verified
result and next action. Raw prompts, private evidence and credentials stay
outside public commits. The public harness's current work is tracked here.

## The current update removes the complete personal dashboard feature

`fixed` · Dashboard removal published; Windows upgrade repair verified locally

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

## Further expansion waits for a concrete task and evidence

`open` · next action: start one small project task with the core commands

Use Harness/ for reusable tools and retain optional integrations. Add no new
service, dashboard, installer, automatic model call or directory migration
after this rename. Future harness changes should name one task, compare the
reference and candidate on it, and record an outcome or KEEP_BASE.

Historical export evidence remains in docs/ADAPTATION.md; later verification
records supplement it without treating earlier counts as the current suite.
