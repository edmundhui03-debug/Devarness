# Three audit passes check retained capabilities and useful instructions

> **2026-10-22** · Devarness · `current`
>
> The source and export retain the same 22 shared skill registrations and
> 30 command names. Karpathy and document style are included. Three bounded
> passes distinguish reusable omissions from optional or private material.

## The inventory retains the reusable command and skill surface

Pass 1 compared tracked path inventories and public manifest rows with the
source workspace. It found no missing shared skill name, Claude skill path,
command, root Library Markdown path or setup-card path. This establishes
path coverage; it does not establish identical content or active runtimes.

| Surface | Source | Devarness | Interpretation |
| --- | --- | --- | --- |
| Shared skill names | 22 | 22 | No missing registration |
| Claude skill names | 22 | 22 | Same reusable names |
| Library commands | 30 | 30 | No missing command name |
| Public source pins | 29 | 30 | Original 29 unchanged; Superpowers added |

Reproduce the target inventory with `git ls-files Library/bin`,
`tools/skill-links.json` and `python3 tools/bootstrap.py --list`. Exact public
commits live in `Library/repos.txt`. Upstream clones remain ignored and are
fetched explicitly; their code and licenses keep their original authorship.

## Karpathy and the document styles have instructions and executable checks

Pass 2 traced selected routing, link targets and helper references. It read
the relevant bodies rather than inferring useful content from filenames.

| Capability | Retained source or adapter | Activation or check |
| --- | --- | --- |
| Karpathy | `Library/karpathy-skills` public pin; Claude/Codex shared links | Fetch `karpathy-skills`, link skills, verify client loading |
| Markdown style | `.claude/skills/markdown-format/SKILL.md`; `Library/templates/markdown-doc.md` | `python3 Library/bin/md-format check FILE` |
| Bilingual HTML | `.claude/skills/bilingual-page/SKILL.md`; HTML template | `bash Library/bin/i18n check FILE` with Beautiful Soup |
| Technical diagrams | Archify adapter and public pin | Fetch `archify`; verify its runtime separately |
| Coding simplicity | Ponytail adapter and public pin | Read full coding and actual-diff review skills |
| TieItUp | 18 rules, Python/C packs, checker and tests | Changed-line check, whole diff and relevant tests |
| pstack review | Local compact adaptation plus upstream pin and notice | Read `references/review.md` beside TieItUp |
| Process gates | Superpowers public pin | Fetch source; plugin activation is separate |
| Harness improvement | Harness² pin and local harness-step runner/helpers | Freeze task/ref/model, probe within an agreed budget |

The root router's ownership table is authoritative. These are selected
core references; no claim is made that every optional upstream reference
or external application was exercised.

## The audit repairs content and portability gaps hidden by matching paths

The Ponytail restoration link previously led to a generic placeholder.
[Its guide](../Library/PONYTAIL.md) now gives local fetch, pin, clean-tree,
skill-loading and real-diff verification steps. The Library's Claude/Codex
entry notes and installation pointer now lead to the maintained procedure.
The Karpathy, pstack and Harness² setup cards now describe their actual
restore and usage paths instead of repeating the generic placeholder.

Markdown examples now invoke the checkout's Python command. Bilingual
examples invoke its Bash launcher, whose interpreter can be selected with
`DEVARNESS_I18N_PYTHON`; a previous installation is no longer required to
select Python. Beautiful Soup remains an explicit optional dependency.

TieItUp's inherited automatic USD 5 benchmark instruction was removed.
Its legacy runner still contains that allocation: launching it requires
the current owner's explicit authorization. Time/cost heuristics do not
grant permission. The controlled harness-step procedure in
[the setup guide](GETTING_STARTED.md) records task, model, budget and spend.

## Optional sources and private dependencies remain explicit exclusions

A fresh template has pins and adapters, not preinstalled third-party
checkouts or logins. In the audit machine, four of 30 upstreams were fetched.
An unresolved diagram-design link, or unfetched pstack/Harness² source, is
an optional fetch requirement rather than a lost exported helper.

`library check --json` reported 126 entries, no diagnostics and no problems
after refresh in that local configuration. Legacy `library coverage --json`
exited 1: it labels the 26 unfetched clones and two unresolved diagram skill
links as orphans. That result is recorded as an optional-source limitation,
not a successful full-catalogue check.

Two omitted simulation helper files were inspected separately. They combine
generic conversion with an excluded project scoring dependency, so they were
not copied. Extracting an independent converter would require a separate
scoped change and fixtures. Personal projects, books, credentials, API keys,
user settings and original history remain excluded.

Other specialist setup cards retain neutral capability pointers rather
than original private device records. Their presence is not a complete
runtime installation manual; inspect each selected tool and its upstream
instructions before installing it.

## The third pass verifies repairs and records remaining limits

`fixed` · independent recheck, affected tests and privacy checks completed

Pass 3 checked repaired instructions, link containment, document format and
known bad controls, followed by tracked-content/history privacy scans.
The first full run passed 18 commands. The repeat run passed 17 and reached
a suite deadline; all 80 TieItUp tests then passed separately. The suite
deadline now allows that measured run; no functional assertion was removed.
The full i18n suite also passed 16 cases with its dependency available.
Exact timings and limits are in
[the improvement report](TIEITUP_IMPROVEMENT.md).

The agents used bounded read-only passes for inventory and references;
the parent reviewed and repaired source. A separate read checks the repairs.
No additional paid experiment was launched for this audit. Runtime client
logins, all optional tools and model diversity remain unverified.
