---
name: tieitup
description: "Apply automatically to every coding task in dev and its projects: design, implement, debug, refactor and review with Ponytail first, then the coding books' 18 rules, the language pack, tieitup check after each edit and in the final review. Ponytail is the base and the fallback."
---

# TieItUp: Ponytail first, then the books, checked by script

Paths are relative to this Devarness checkout. From its root, run
`python3 Library/bin/<tool>` to select this checkout explicitly.
The design and its evidence are `docs/ADAPTATION.md`.

## Load the layers in order

1. The router's safety rules and the superpowers gates (TDD, debugging,
   verification) come first; nothing here overrides them.
2. Ponytail: read `.claude/skills/ponytail/SKILL.md` and the two upstream skills
   it names, `Library/ponytail/skills/ponytail/SKILL.md` and
   `Library/ponytail/skills/ponytail-review/SKILL.md`. When Ponytail's rules
   are already in your context, as in a benchmark session, do not load them
   again. Its smallest complete change and its never-cut list win over every
   book rule below.
3. The 18 rules below, then the pack for each language you edit:
   `references/python.md` for Python, `references/c.md` for C and headers.
   Every other kept rule, each conflict and each refused rule is in
   `references/rules.md`.

If any of this skill's files is missing, the start check reports DEGRADED: use
`.claude/skills/ponytail/SKILL.md` alone, as before TieItUp.

## The 18 rules

A book rule applies only where it agrees with Ponytail or fills a gap. A
design pattern waits until a second real implementation exists.

| # | Rule | Source |
| --- | --- | --- |
| 1 | Never swallow a failure: name the exception types, wrap only the call that can fail, and re-raise what you do not handle. A handler that only passes carries a comment saying why that is safe | The Practice of Programming p.113 |
| 2 | Check every return value and exit status, and report the underlying reason | Code Complete p.66 |
| 3 | An error message names the operation that failed and how it failed | Clean Code p.117 |
| 4 | Signal failure the way the codebase already does: exceptions in new Python and JS, status codes in C and Bash. At a trust boundary, reject and report; substitute a value only where the domain defines a safe one, and log it | Clean Code p.60-61, p.114 |
| 5 | Never put work the program needs inside an assert: `python -O` and C's `NDEBUG` remove asserts | Code Complete p.62 |
| 6 | Write files inside a `with` block, naming `encoding='utf-8'` and the newline; replace a file that matters through a temp file and `os.replace` | Python Crash Course p.182; Beginning Python p.226 |
| 7 | Use only what every target machine provides: the Mac runs Python 3.9, so no `Path.write_text(newline=)` and no `match` | The Practice of Programming p.156-158 |
| 8 | Run subprocesses with an argument list; use `shell=True` only with `shlex.quote` on every part that comes from input | Python Cookbook p.576-577 |
| 9 | Name things for what they mean in the problem, with the specific word; no noise-word twins such as `customer` beside `customer_info` | Clean Code p.34 |
| 10 | One name per concept; a rename covers code, tests, documents and messages in the same change | Domain-Driven Design p.39-40 |
| 11 | A function does only what its name says; a query changes nothing | Clean Code p.58-59 |
| 12 | No boolean parameter that switches a function between two jobs; write two functions | Clean Code p.56 |
| 13 | Handle failures and edge cases first with an early return or `continue`; a new check adds no nesting level | The Art of Readable Code p.91-93 |
| 14 | Name a non-obvious number once and derive related numbers from it; measured calibration values stay as measured | The Practice of Programming p.15-16 |
| 15 | Fix or delete any comment your change makes false, in the same diff | Clean Code p.68, p.82 |
| 16 | Delete code instead of commenting it out, and do not sign it | Clean Code p.81-82 |
| 17 | Reuse a shared type only with its existing meanings; otherwise keep your own type | Domain-Driven Design p.255-256 |
| 18 | A stored or exchanged format uses an existing format and carries a version from the start | The Art of Unix Programming p.29 |

Where a book loses to Ponytail, Ponytail's way holds: split a function by job,
never by line count; no parameter ceiling; no one-line wrappers; remove only
what your own change made unused. The never-cut list stays whole: validation at
trust boundaries, error handling that prevents data loss, security,
accessibility, hardware calibration and anything the owner asked for.

## Check each edit and the whole change

`tieitup check` reads only changed lines and never blocks. In Claude Code the
post-edit hook runs it on each edited file and hands back its findings. Fix
each finding, or say in one line why it stands. A `shortcut:` marker that names
its limit and when to upgrade is a decision, not a finding.

The final review, before calling a coding task done:

1. Ponytail's review of the actual diff. Before giving a verdict, read
   `references/review.md` beside this skill and complete its review. Reuse it
   when already read in this context; memory of the rules is not a review.
2. `tieitup check` on the whole change (`--staged`, or `A..B` for commits). It
   ends with a balance line and lists the callers of each changed definition;
   read each caller the change could break.
3. Keep a finding only with a concrete case where the code goes wrong.
4. Record what you judged: `tieitup mark ID fp "why"` for a false alarm,
   `tieitup mark ID ok` for a right one, and `tieitup miss PATH:LINE "what"`
   for a problem the check should have found. These feed `tieitup learn`.
5. Run `tieitup learn` and apply what it teaches in this session, as the
   next section says.

Label the review self-review when you wrote the code.

## TieItUp improves itself in the session that teaches it

The owner made this automatic on 15 October; the design is in SPEC.html 06.

- **narrow** or **missed**, at the end of each final review: apply at most
  one. Write a failing test in `Library/tests/test_tieitup.py`, narrow the
  check or teach it the missed case, run the whole suite, `tieitup check`
  the change, and commit it by path apart from the task's own commit. A miss
  that needs a new check stays a proposal.
- **silent**, and anything that touches a never-cut check, adds or removes a
  check, or changes a rule's text, the levels or the wiring: leave it for
  the owner and name it in the hand-off.
- **drift**, or a start banner reading `tieitup stale` because Ponytail's
  skills changed: before the first coding task, read
  `git -C Library/ponytail diff <checked commit>..HEAD -- skills`, update the
  conflicts in `references/rules.md` and the counterpart table below where
  Ponytail moved, run the tests, then `tieitup rechecked` and commit by
  path; a rule whose own text must change goes to the owner. A Ponytail
  update that leaves its skills alone is never stale. The daily
  `update-tools` sends the owner one `needs-owner` alert per new skills tree.
- **harness**, when Claude Code or the model moved past the newest
  benchmark: run `python -B Library/tieitup-bench.py auto` in the background.
  It decides by itself: the pilot only, with a $5 stop line, at most once in
  seven days, and never when the model changed until `OPUS` in the runner
  names the new one. When it spends, add the row to `Setup/AGENT_LEDGER.md`
  and report the spend. For a new model, re-audit the lines `learn` lists
  with the `claude-api` skill's `prompt-audit`; do not rewrite them unasked.

## The other commands do Ponytail's other jobs

| Ponytail | Its job | TieItUp |
| --- | --- | --- |
| ponytail | The smallest complete change and the never-cut list | This skill loads it first, then adds the rules, the packs and the check |
| ponytail-review | Trace the real flow, grep the callers, keep only concrete findings | The final review above, with `tieitup check` and its callers list |
| ponytail-audit | A whole-tree review with concrete cases | `tieitup audit [PATH]`: every check over whole files, grouped by check |
| ponytail-debt | A ledger of `shortcut:` markers and their triggers | `tieitup debt [PATH]`: each marker with its age, then unmarked TODO notes |
| ponytail-gain | The benchmark's measured averages, never one repository's saving | `tieitup gain`: TieItUp's own measured result against Ponytail |
| ponytail-help | Levels, commands and how to stop | `tieitup help` |

`tieitup learn` lists proposals from the record and from what moved since
TieItUp was checked; the section above says which ones an agent applies.

## Levels

Full is the default, fixed by the router; only the owner's words change it or
stop TieItUp ("stop tieitup").

| Level | Adds to Ponytail's level |
| --- | --- |
| lite | The same rules and checks as full |
| full | The 18 rules, the language packs and the check after each edit and in the final review |
| ultra | The final review also reads `references/rules.md` for the languages touched |

No level turns off a rule, the check or the never-cut list.
