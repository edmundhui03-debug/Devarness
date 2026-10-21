# TieItUp's reference: every kept rule with its page, and every rule it refuses

> **2026-10-15** · Peter · `current`
>
> The study kept 117 rules from the coding books. The skill states 18 of them;
> this file holds the rest that apply to every language, the rules another skill
> owns, the conflicts with their resolutions, the wording that keeps Ponytail's
> never-cut list whole, and the rules TieItUp refuses, so a later pass does not
> add them back. Generated from the study's evidence file.

## Contents

- [The 18 core rules come from these books and fold in these rules](#the-18-core-rules-come-from-these-books-and-fold-in-these-rules)
- [Twenty-two more rules apply in every language, read at ultra](#twenty-two-more-rules-apply-in-every-language-read-at-ultra)
- [Thirty-five rules belong to another skill, so TieItUp only points to them](#thirty-five-rules-belong-to-another-skill-so-tieitup-only-points-to-them)
- [Ten pairs of book rules conflict, and each has one resolution](#ten-pairs-of-book-rules-conflict-and-each-has-one-resolution)
- [Eleven rules carry wording that keeps Ponytail's never-cut list whole](#eleven-rules-carry-wording-that-keeps-ponytails-never-cut-list-whole)
- [Eleven rules are refused, each with its reason](#eleven-rules-are-refused-each-with-its-reason)
- [The ranked checks the command does not run are review prompts](#the-ranked-checks-the-command-does-not-run-are-review-prompts)

## The 18 core rules come from these books and fold in these rules

The skill states each rule in full. The IDs are the study's, and `docs/ADAPTATION.md` holds each with its cite, its page
and its relation to Ponytail. A page number is the PDF's page index, not the
printed folio.

| # | Primary | Folded in | Checks |
| --- | --- | --- | --- |
| 1 | A-14 | D-14, D-17, D-16, A-12 | swallowed-error, bare-except |
| 2 | B-08 | - | unchecked-run |
| 3 | A-13 | - | - |
| 4 | A-11 | B-07 | - |
| 5 | B-04 | - | - |
| 6 | D-20 | D-22, D-M1 | open-file |
| 7 | None | - | py39 |
| 8 | D-23 | - | shell-true |
| 9 | A-01 | A-02, A-03, B-09 | vague-name |
| 10 | C-18 | - | - |
| 11 | A-04 | - | - |
| 12 | A-10 | - | - |
| 13 | A-08 | B-03 | nesting |
| 14 | A-24 | - | magic-number |
| 15 | A-22 | - | - |
| 16 | A-20 | - | commented-code |
| 17 | C-06 | - | - |
| 18 | C-05 | C-M3 | - |

## Twenty-two more rules apply in every language, read at ultra

| ID | Rule | Source |
| --- | --- | --- |
| A-09 | Give a new function three parameters at most; when several always travel together, bundle them into one named object. | Clean Code p.55, p.58, book text |
| A-16 | Wrap a third-party API in your own class that translates its many exception types into the one your callers catch. | Clean Code p.117-118, book text |
| A-26 | Break an expression a reader must decode into named parts (`username = line.split(':')[0].strip()`); but inline a temporary used once that clarifies nothing. | The Art of Readable Code p.97-99, p.106, book text |
| A-M1 | Default to if/else; use a conditional expression (`x if c else y`, `c ? a : b`) only to choose between two simple values. | The Art of Readable Code p.87-88, book text |
| B-10 | Fit a name's length to its reach: one-letter names only within a few nearby lines, such as a short loop; names read across a module are longer and specific. | Code Complete p.123, bibliographic reference above |
| B-14 | When the same switch or if-chain on one type code appears in two places, move it into one function or table both call; leave a lone switch as it is. | Refactoring: Improving the Design of Existing Code p.107, book text |
| B-16 | When the same three or four values travel together through several signatures or fields, give them one object; if dropping one leaves the rest meaningless, they belong together. | Refactoring: Improving the Design of Existing Code p.106, book text |
| B-21 | To get untested code under test, edit it as little as possible: substitute the troublesome dependency at a seam, such as an overridable forwarding method, instead of rewriting it. | Working Effectively with Legacy Code p.55, book text |
| B-23 | When a test swaps in stubs through the build, link path or classpath, make the difference between the test setup and production obvious. | Working Effectively with Legacy Code p.52, book text |
| B-28 | When characterizing shipped code exposes a likely bug, check whether users depend on that behavior before fixing it, and mark doubtful tests suspicious instead of dropping them. | Working Effectively with Legacy Code p.174, book text |
| B-M3 | Give a switch over known cases a final branch that flags any other value, loudly in development and recoverably, such as logged, in production. | Code Complete p.63, book text |
| C-01 | Before a new function's body, give it a meaningful name, write its contract (input and output types) and a one- or two-line statement of what it computes. | How to Design Programs p.22-23, bibliographic reference above |
| C-04 | Keep policy separate from mechanism, so a change of policy never has to edit, or risk breaking, the mechanism that applies it. | The Art of Unix Programming p.20, bibliographic reference above |
| C-10 | Pass a plain function, or a data row run by one shared function, instead of a one-method Command class; build Command objects only for queueing, logging or undo. | Design Patterns: Elements of Reusable Object-Oriented Software p.165-167, bibliographic reference above |
| C-11 | Keep a few states as one state value checked where it is used; move to per-state handlers only when many states scatter the same checks across several functions. | Design Patterns: Elements of Reusable Object-Oriented Software p.214, bibliographic reference above |
| C-17 | Follow the conventions similar tools use for options, input and output, and break one only after every conventional approach has visibly failed. | The Art of Unix Programming p.256, bibliographic reference above |
| C-19 | For code with modes or states, tabulate which actions are legal in which state, and make each action reject the reachable states where it is illegal. | Zen of Design Patterns p.348, bibliographic reference above |
| C-20 | When a run has nothing worth saying, print nothing; spend the user's attention on output only when it must. | The Art of Unix Programming p.17, p.25, bibliographic reference above |
| C-21 | Put a needed setting where its lifetime fits: a flag for per-run choices, a user dot file for rare personal ones, a system file for admin ones; local overrides global. | The Art of Unix Programming p.237-238, bibliographic reference above |
| C-22 | Write a data-transforming tool as a filter: read stdin or named files in order, write results to stdout, take control from options, and never prompt for input. | The Art of Unix Programming p.270, bibliographic reference above |
| C-M2 | Keep code that must run with elevated privilege (setuid, sudo, administrator) in a small separate program, so only that small part has to be trusted. | The Art of Unix Programming p.163-164, bibliographic reference above |
| C-M4 | Parse a format by its specification, adding no private tolerances other readers lack, and emit strictly correct output for the next program in the chain. | The Art of Unix Programming p.25, bibliographic reference above |

## Thirty-five rules belong to another skill, so TieItUp only points to them

TieItUp never restates these: the owner's skill governs, and the book is cited
as support.

| ID | Rule | Owner |
| --- | --- | --- |
| A-06 | Give each block one task: list what the code does (validate, parse, apply), then separate the tasks into their own functions or at least their own paragraphs. | Ponytail, `Library/ponytail/skills/ponytail-review/SKILL.md:53` |
| A-07 | Extract a function only for a distinct subproblem or real reuse; never add pass-through helpers that only forward a call, since each new function costs the reader a jump. | Ponytail, `Library/ponytail/skills/ponytail-review/SKILL.md:54` |
| A-19 | Delete any comment that only restates the line beside it (`i += 1  # increment i`); a comment must add what the code cannot say. | Ponytail, `Library/ponytail/skills/ponytail/SKILL.md:37` |
| A-21 | Write deferred work as `shortcut: <the limit>, <when to upgrade>`, never a bare TODO, and never as an excuse to leave bad code in place. | Ponytail, `Library/ponytail/skills/ponytail/SKILL.md:42` |
| A-27 | Write no code the need does not demand: skip features nobody needs, use the standard library first (`set(items)`, not a hand-written `unique()`), and delete what your change leaves unused. | Ponytail, `Library/ponytail/skills/ponytail/SKILL.md:15` |
| A-28 | Shrink the requirement to the case you have (30 Texas stores need no date-line math), never below what the user asked; mark the cut `shortcut: <limit>, <when to upgrade>`. | Ponytail, `Library/ponytail/skills/ponytail/SKILL.md:27` |
| A-30 | Leave code that already reads easily alone, even if it is not perfectly decomposed; ask whether it is easy to understand before restructuring it. | karpathy-guidelines, `Library/karpathy-skills/skills/karpathy-guidelines/SKILL.md:41` |
| A-M3 | Review a change in the whole function it lands in, not only as a diff, and insert new checks so they do not add a nesting level. | Ponytail, `Library/ponytail/skills/ponytail-review/SKILL.md:21` |
| B-01 | Never split or cap a function by line count alone; split by job, and give a function past 200 lines extra scrutiny, one past 500 the most. | Ponytail, `Library/ponytail/skills/ponytail-review/SKILL.md:54` |
| B-11 | Never mix restructuring and behavior change in one step: a refactor keeps observable behavior and adds no feature, and feature work adds code without restructuring. | superpowers' test-driven-development |
| B-12 | Treat a smell's size measure (lines, fields, parameters) as a prompt to look, never as a finding; report it only with the concrete harm it does here. | Ponytail, `Library/ponytail/skills/ponytail-review/SKILL.md:59` |
| B-13 | Never add a block that repeats code already in the repo or diff: call it, or extract it once; for near-copies, extract the shared part and keep what differs apart. | Ponytail, `Library/ponytail/skills/ponytail-review/SKILL.md:52` |
| B-15 | Put new code beside the data it uses most; flag a diff making the same small edit in many files for one reason: that knowledge belongs in one place. | Ponytail, `Library/ponytail/skills/ponytail/SKILL.md:38` |
| B-18 | Delete what was built for someday: unused parameters, hooks, idle abstract classes, and a function or class used only by tests, unless it helps them check real behavior. | Ponytail, `Library/ponytail/skills/ponytail-review/SKILL.md:47` |
| B-24 | Keep the code under test identical in test and production runs; choose substitute behavior at the seam's enabling point, never with test-only branches inside that code. | superpowers' test-driven-development |
| B-25 | Start a sensing fake as the simplest recorder of the calls it receives, such as a list of their arguments, and grow it only when a test needs more. | Ponytail, `Library/ponytail/skills/ponytail/SKILL.md:32` |
| B-27 | Before using any method of an untested legacy system, check whether a test covers it, and write one first if none does. | Ponytail, `Library/ponytail/skills/ponytail/SKILL.md:41` |
| B-29 | Before moving or extracting code, make sure a test runs each branch you will rewrite, with inputs whose result changes if a value is truncated or converted. | Ponytail, `Library/ponytail/skills/ponytail-review/SKILL.md:42` |
| B-M1 | Mark where outside data enters as a safe-zone boundary and validate everything crossing it, sanitizing at more than one layer when the data needs it. | Ponytail, `Library/ponytail/skills/ponytail/SKILL.md:44` |
| B-M4 | When shipped code meets a fatal error, let the user save their work before it stops; never ship a debug check that halts and loses their data. | Ponytail, `Library/ponytail/skills/ponytail/SKILL.md:44` |
| B-M5 | When two functions do the same job by different algorithms, keep the clearer one and replace the other's algorithm with it. | Ponytail, `Library/ponytail/skills/ponytail-review/SKILL.md:48` |
| C-02 | Make a failing test pass with the smallest change, even a hard-coded value, before working toward the real solution. | Ponytail, `Library/ponytail/skills/ponytail/SKILL.md:34` |
| C-03 | Give a component one entry point that performs the steps a client would otherwise have to know and call in the right order. | Ponytail, `Library/ponytail/skills/ponytail/SKILL.md:35` |
| C-09 | Add an adapter or wrapper only when an existing, working component's interface does not match what a current caller needs. | Ponytail, `Library/ponytail/skills/ponytail/SKILL.md:35` |
| C-14 | Store new config or data in a format that already exists—the project's own, or one the standard library parses such as JSON, INI or CSV—instead of inventing a syntax. | Ponytail, `Library/ponytail/skills/ponytail/SKILL.md:29` |
| C-15 | Before adopting a more complex IPC technique, prove with a prototype and a benchmark that every simpler technique fails. | Ponytail, `Library/ponytail/skills/ponytail/SKILL.md:25` |
| C-16 | Before adding an option, ask whether the feature can be dropped, the behaviour changed without an option, or made a separate program; each option multiplies the test matrix. | Ponytail, `Library/ponytail/skills/ponytail/SKILL.md:27` |
| C-23 | Write new code only when an automated test is failing: add a test, watch it fail, make a small change, run all tests, then refactor. | superpowers' test-driven-development |
| C-24 | Predict each test's expected value before the code exists; never read it off the program's own answer. | superpowers' test-driven-development |
| C-25 | Write the test against the interface you wish existed, then work backwards to make the implementation fit it. | superpowers' test-driven-development |
| C-26 | Before building on an unfamiliar library or API, write a small learning test that exercises only that API to confirm your understanding of it. | superpowers' test-driven-development |
| C-27 | When a stray idea arrives mid-task, add it to the to-do list and return to the current test instead of chasing it. | karpathy-guidelines, `Library/karpathy-skills/skills/karpathy-guidelines/SKILL.md:49` |
| C-M1 | Do not add concurrency or extra processes for speed before the design has minimized global complexity; that is premature optimization. | Ponytail, `Library/ponytail/skills/ponytail-review/SKILL.md:44` |
| D-28 | Write a small test first, run it and watch it fail, then write the code; never commit code with a known-failing test to a shared repository. | superpowers' test-driven-development |
| D-29 | When a test that checks a correct condition fails, fix the code that fails it; never edit or weaken the test to make it pass. | superpowers' test-driven-development |

## Ten pairs of book rules conflict, and each has one resolution

- A-14 vs D-17: A-14's check flags every pass-only handler (27 in dev's own
  Python tools); D-17 exempts a broad handler whose lines record why it
  swallows. Resolution: one check, D-17's. Flag a pass or ... handler with no
  comment, broad ones first; a comment stating why is a decision
  (ponytail-review/SKILL.md:63). In dev that leaves one hit:
  .claude/hooks/preflight_report.py:24.
- A-23 vs B-13 vs C-08: three duplicate-block checks with thresholds of 4, 5 and
  6 lines and different scopes. Resolution: keep B-13's scope (the diff plus the
  same file's unchanged lines) with C-08's 6-line threshold, ignoring lines that
  are only brackets, else, fi, done or esac. Cut A-23 and C-08.
- A-08 vs B-03: two nesting checks with different shapes (any statement more
  than three blocks deep, versus an if inside two ifs). Resolution: one rule
  (B-03's guard-clause remedy in A-08's text) and one check: depth 4 or more of
  if/for/while/try inside one function, not counting with.
- A-09 vs B-12 (and the A-05/B-01 resolutions): A-09 keeps a fixed 3-parameter
  ceiling, while B-12 says a size measure is a prompt, never a finding, which is
  why A-05's 20-line ceiling was rejected. 38 of dev's 585 Python functions take
  more than three parameters (e.g. Library/bin/dev-check:228). Resolution: drop
  the ceiling from the rule; a fourth parameter only prompts a look for an
  option nobody asked for or a mixed job.
- D-22 vs house lesson LESSONS.md:86-88 (not a pair of accepted ids): D-22's
  check flags write_text() without newline=, which steers agents to
  Path.write_text(newline=). That keyword needs Python 3.10, and this exact call
  broke the Mac's 3.9 (practice-of-programming.md:185-190). D-22 also omits the
  encoding LESSONS.md:227 requires. Resolution: fold it into D-20 using the
  house idiom open(path, 'w', encoding='utf-8', newline='\n')
  (Library/bin/i18n:387) or write_bytes.
- B-M3 vs D-01: D-01 carries checked errors in status enums, while B-M3's
  resolution demands a default branch for any value from another module. In
  SAMPLE_FIRMWARE, the detector firmware's sys_app.c:983 switches with no default on the
  ConfigApplyAction_e that ConfigStore_Apply returns, built with -Wall
  (detector/cmake/gcc-arm-none-eabi.cmake:29). Adding a default would silence
  the compiler's missing-enumerator warning (-Wswitch); GCC behaviour from
  documentation, not tested here. Resolution: a C switch over an enum lists
  every enumerator and omits default; raw integers from flash, radio or config
  are converted to the enum and rejected at the boundary; B-M3's default applies
  to switches on raw integers, strings and Python match.
- B-M6 vs B-21: B-21 adds a defaulted parameter as the test seam, and SAMPLE_FIRMWARE's
  pure modules take explicit parameters so they can be tested on the host
  (the-c-programming-language.md:105-111; alarm_status.h:14 per
  head-first-design-patterns.md:204-206). B-M6 says not to pass what the routine
  could fetch for itself, and it repeats B-16's Preserve Whole Object resolution
  (both cite Refactoring p.104). Resolution: cut B-M6.
- A-07 vs B-21: B-21's rule text recommends 'an overridable forwarding method',
  which A-07 bans. B-21's resolution already forbids a new forwarding layer but
  credits the ban to B-19, which is not in the accepted set. Resolution: reword
  B-21's rule text to match its resolution and point the reference at A-07.
- B-13 vs C-06: B-13 says to call existing code instead of repeating it; C-06
  says to keep your own type when meanings differ. Resolution: B-13 applies to
  copies that must change together (ponytail-review/SKILL.md:52); look-alike
  code serving two meanings that change for different reasons stays separate
  (C-06).
- C-22 vs C-03: C-22 forbids interactive prompts, while C-03's resolution
  protects review gates such as preview before apply. Resolution: a destructive
  tool replaces a prompt with an explicit flag (--apply or --yes) or a preview
  step, and never loses the gate.

## Eleven rules carry wording that keeps Ponytail's never-cut list whole

Ponytail never cuts validation at trust boundaries, error handling that prevents
data loss, security, accessibility, hardware calibration or anything the user
asked for (`Library/ponytail/skills/ponytail/SKILL.md:44`). Wherever TieItUp
states one of these rules, it carries this wording.

- A-15: 'return an empty list' can turn a failed read into an empty result that
  a caller then writes back, losing data. The rule must say: empty only for
  'found nothing'; a failure raises (A-14).
- A-28 (cite-only, but in the set): 'shrink the requirement to the case you
  have' can be read as permission to drop validation of outside input or
  time-zone handling, and ponytail-review's own sample bug is a time-zone error
  (Library/ponytail/skills/ponytail-review/SKILL.md:85-92). A shrink never goes
  below Ponytail SKILL.md:44 and is always marked shortcut:.
- B-M3 (together with karpathy-guidelines/SKILL.md:30, 'no error handling for
  impossible scenarios'): in firmware, a value read from flash, a LoRa downlink
  or a config key is outside input even when it is typed as an enum. Validate it
  at the boundary; Sys_ApplyConfig's own comment says a downlink must not
  silence a sounding siren (the detector firmware's sys_app.c:975-980).
- C-20: the Rule of Silence could be read as permission to drop warnings,
  degraded-state notices or error output. The router says an empty preflight is
  START FAILED, never silence, and a fallback that weakens security reports
  FAILED, never a warning. Silence covers routine success narration only.
- C-22: 'never prompt for input' could remove a confirmation gate on a
  destructive action. Keep the gate as an explicit flag (--apply or --yes) or a
  preview step; C-03's resolution protects preview before apply.
- B-18 (cite-only, but its check ships): 'delete unused parameters and hooks'
  can delete a calibration value or a validation hook that firmware reads
  through a registry or flash and that looks unused in the diff. Its resolution
  (report older code; delete only what your own change orphaned) must appear in
  any text the check prints.
- A-24: 'derive related numbers rather than retyping them' must never turn
  independently measured hardware calibration values into derived formulas
  (Ponytail SKILL.md:44, the calibration real hardware needs).
- A-07 and its check: a one-line forwarding method can be the only path to
  safety machinery, as with Example App's StudioService @tool methods, which hold
  the job and revision checks (head-first-design-patterns.md:172-193). Exempt
  decorated entry points; never remove a facade method as a pass-through.
- D-19: 'print a plain message instead of a raw traceback' must still exit
  non-zero and keep the underlying cause (Rule of Repair,
  Books/notes/linux/art-of-unix-programming.md:98-109). It must never become a
  broad catch that hides programming errors.
- B-07 (folded into A-11): 'substitute a safe value' can hide bad input at a
  trust boundary. At a boundary, reject and report; substitute only where the
  domain defines a safe value, and log the substitution.
- A-27 (cite-only): 'write no code the need does not demand' leaves out
  Ponytail's Never-cut list. Because it is cite-only, the spine's SKILL.md:44
  governs; never restate it without that caveat.

## Eleven rules are refused, each with its reason

| ID | Rule | Why it is refused |
| --- | --- | --- |
| A-05 | Keep functions to 20 lines at most, with each if, else or while body one line, ideally a function call. | Do not carry the ceiling. ponytail-review:54 splits by job, never by line count, and never into helpers that only shorten a function; The Art of Readable Code p.130 shows tiny helpers cost readability. Carry A-06 (one task at a time) and A-08 (shallow nesting) instead. |
| A-23 | Don't add the same logic twice in one change; when added blocks repeat, write the logic once and call it from each place. |  |
| A-M2 | Put the changing value being examined on the left of a comparison and the steadier one on the right (`length >= 10`); never Yoda order (`NULL == obj`). |  |
| B-02 | Extract any block that needs a comment into a function named for its purpose, even a single line, even when the call is longer than the body. | Keep Ponytail (no wrapper nobody asked for; ponytail-review/SKILL.md:54 split by job): extract only a block that is a separate job or repeats; for a single line, rename what it uses instead of adding a one-line function. |
| B-17 | Replace a bare value that carries meaning, such as money with its currency, a range, a phone number or a ZIP code, with a small object of its own. | Keep Ponytail: values stay in the form the platform gives; add a small type only when it deletes checks or conversions on that value already repeated in the code the change touches. |
| B-22 | Prefer a seam in the code's own interface, a parameter or an overridable method, over build, link or preprocessor substitution; save those for pervasive dependencies with no better option. | Follow B-21's resolution: use a seam the code already has, an interface one before a build, link or PATH one; add only a defaulted parameter, and only when no existing seam lets the required test run; make any link-type swap obvious (B-23). |
| B-26 | Before changing untested code, pin what it does now: assert a value you expect to be wrong, run it, set the expectation to the actual output, and repeat. | TDD outranks TieItUp: do not adopt this loop. Expected values stay derived without the code under test (writing-good-tests.md:76) and a failing test is fixed in the code (TDD:181); use only the narrow characterization test writing-good-tests.md:58-60 allows, and ask the owner before using the loop more widely on legacy code. |
| B-M2 | Never put a call with side effects inside an assert: run it first, keep its result in a variable, then assert on that variable. |  |
| B-M6 | Don't pass a routine a value it can get by asking an object it already has, either a field of its own or another parameter. |  |
| C-08 | Remove the duplication a change creates before calling it done: no two added blocks that must change together. |  |
| D-06 | Never put work the program needs, such as an assignment, increment or required call, inside a C assert(); defining NDEBUG removes the whole expression. |  |

## The ranked checks the command does not run are review prompts

The final review reads these as prompts. Each is a candidate for a later check,
only on the owner's word.

- 3. D-M6 (checker-proposed): a def default that is a list/dict/set literal, a
  comprehension, or a list()/dict()/set() call. FP: a default that is only ever
  read; dev tools have 0.
- 4. D-15: in one try, a handler whose builtin class subclasses an earlier
  handler's builtin class. FP: none when restricted to builtins; rare hits.
- 5. B-24 (report under writing-good-tests.md:124-127): PYTEST_CURRENT_TEST,
  'pytest' in sys.modules, JEST_WORKER_ID or BATS_TEST_ in a non-test file. FP:
  conftest.py and helpers under tests/ not named test_*; treat both as test
  files.
- 7. D-M4 (checker-proposed): an object-like #define whose body ends in *. FP: a
  macro meant as a multiplication fragment; near zero.
- 8. D-M3 (checker-proposed): a typedef with a comma outside parentheses or
  braces, or typedef after another type word. FP: function-pointer typedefs,
  which the parenthesis rule exempts.
- 9. D-M5 (checker-proposed): name = getchar() where the diff declares name as a
  char type. FP: none known; probably never fires, since the firmware reads its
  UART through the HAL (not checked).
- 10. D-03: a comparison of the form <= expr - 1. FP: a deliberately inclusive
  arithmetic bound that is not a range.
- 11. A-M1 (checker-proposed): an IfExp inside an IfExp, or a ? inside an
  operand of ?:. FP: a two-level choice some readers find clear; rare.
- 14. D-26: a class-body list/dict/set that a method mutates through
  self.<name>. FP: an intentionally shared class-level registry or cache.
- 15. D-05: a newly added X.c with no #include of X.h when X.h exists in the
  repo. FP: generated (STM32CubeMX) sources whose same-named header serves
  another job.
- 16. B-04 (absorbing D-06 and B-M2): C assert( containing ++, -- or a lone =;
  Python assert containing := or await. FP: low for these patterns; leave named
  method calls to review, because B-M2's side-effect name list matches pure
  methods.
- 17. A-13: raise Name or raise Name() with no arguments (exempt bare raise,
  StopIteration, NotImplementedError, SystemExit, KeyboardInterrupt), and JS
  throw new Error() with no argument. FP: custom sentinel exceptions used for
  control flow; dev's only 2 hits (Library/bin/dashboard:262 and :347, Busy) are
  exactly that.
- 18. B-10: a one-letter name bound at module level, or a one-letter def or
  class (exempt _, TypeVar names and loop variables). FP: maths or physics
  constants in a simulation script.
- 19. C-24 (report under writing-good-tests.md:27-39): an assert whose two sides
  call the same function, or whose expected side was assigned from that call.
  FP: idempotence or determinism tests that compare two runs.
- 20. C-02 (report under TDD SKILL.md:132): an added function that only returns
  a constant equal to an added assertion's expected value. FP: a genuinely
  constant function, though its test is then a change detector
  (writing-good-tests.md:41-45).
- 21. B-14: two if/elif chains or match/switch blocks, at least one added,
  testing the same name against the same three or more literals. FP: an encoder
  and decoder that must mirror each other.
- 26. A-26: a condition joining four or more boolean operands at one level, or
  an assignment inside a compound test. FP: a validation that lists independent
  flags.
- 27. A-M4 + D-M2 merged (checker-proposed): a function-like #define that uses a
  parameter twice, or leaves a parameter or an operator-bearing body
  unparenthesized (skip # and ## operands). FP: stringizing, attribute macros
  such as UTIL_PLACE_IN_SECTION(__x__), and do{}while(0) statement macros.
- 28. A-M6 (checker-proposed): a malloc/memcpy/memset/fgets size argument that
  is an integer literal above 1 with no sizeof. FP: protocol-defined lengths (an
  8-byte LoRaWAN EUI) that want a named constant (A-24), not sizeof.
- 30. C-22: input(, read -p or prompt( outside test files. FP: interactive setup
  scripts and confirmation gates on destructive actions (see never-cut risks).
- 33. A-19 (report under Ponytail SKILL.md:37): a comment of six words or fewer
  whose content words all appear in its code line. FP: section labels above a
  call in a long function.
- 34. A-07 (report under Ponytail SKILL.md:35): a def whose body passes its
  parameters unchanged to one call. FP: decorated entry points that are the only
  path to safety checks (StudioService @tool methods,
  head-first-design-patterns.md:172-193), interface implementations and
  compatibility aliases. Exempt decorated functions and overrides.
- 35. B-16: the same run of three or more parameter names, in order, in two
  signatures, one of them added. FP: a family of checkers that each take (path,
  text, lines).
- 36. B-18 (report under Ponytail SKILL.md:35): a parameter that a fully added
  function never reads, with its listed exemptions. FP: interface and
  CLI-handler signatures, only partly covered by those exemptions.
- 37. A-15: a def returning a collection on one path and None on another. FP:
  None that deliberately means 'absent or not computed', which is different from
  empty.
- 39. A-09: more than three parameters in Python (not counting self, cls, *args,
  **kwargs), four or more in JS or C. FP: 38 of dev's 585 functions (e.g.
  Library/bin/dev-check:228 run with 4, daily_task_xml with 7). Report only as a
  prompt under B-12, never as a finding.
- 40. B-M3 (checker-proposed): a match with no wildcard case, a switch with no
  default, or a Bash case with no *) arm. FP: C enum switches under -Wall, where
  a default disables -Wswitch (Core/Src/sys_app.c:983;
  detector/cmake/gcc-arm-none-eabi.cmake:29), and closed Python match sets.
- 41. A-M2 (checker-proposed; cut): Yoda-order comparisons. FP: ST-generated
  firmware (Core/Src/sysmem.c:63, usart_if.c:241) and plain style taste; do not
  ship.
