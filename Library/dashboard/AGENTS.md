# Every agent reads questions.json before a task and writes down what it used

> **2026-10-09** · Peter · `current`
>
> The rules for any agent working in dev while the Zack dev. dashboard is in
> use: read `questions.json` first, ask one plain question at a time, never
> touch Zack's answer, and say in one line what an answer changed.

## Contents

- [The file is read at the start of every task](#the-file-is-read-at-the-start-of-every-task)
- [A question has one shape and a unique id](#a-question-has-one-shape-and-a-unique-id)
- [An agent waits for its answer in the background](#an-agent-waits-for-its-answer-in-the-background)
- [An answer is never edited and a question is never deleted](#an-answer-is-never-edited-and-a-question-is-never-deleted)
- [An answer is marked used once you have acted on it](#an-answer-is-marked-used-once-you-have-acted-on-it)
- [The workspace's own records stay the source of truth](#the-workspaces-own-records-stay-the-source-of-truth)
- [snapshot.json is generated and never edited by hand](#snapshotjson-is-generated-and-never-edited-by-hand)
- [The bridge and the taskboard start only on request, and the key stays hidden](#the-bridge-and-the-taskboard-start-only-on-request-and-the-key-stays-hidden)
- [The app has one lockfile and the server stays loopback-only](#the-app-has-one-lockfile-and-the-server-stays-loopback-only)

## The file is read at the start of every task

`fixed`

Before any task in dev, open `Library/dashboard/questions.json` (it sits
beside this file). For each entry:

- `answered` and about your task: use it, then mark it used as shown below.
- `open` and asked by you: still waiting; do not act on it or ask it again.
- `used`: history. Ignore it.

If the file is missing or not valid JSON, say so in your report and carry on.

## A question has one shape and a unique id

`fixed`

Add a question only with `dashboard ask`, and mark one used only with
`dashboard used`; never edit `questions.json` yourself. Both take the lock the
app's server (`dashboard serve`) takes while it saves Zack's answer, so
neither write loses the other; an edit by hand skips the lock and can wipe out
his answer. The prototype page (`Library/dashboard/index.html`) saves without
the lock until wave 6 retires it, so while agents may be asking, Zack answers
in the app.

```sh
dashboard ask --project PCB --task "v0.4 order" --asked-by Peter "Which holder?"
```

It prints the new id. It writes twelve fields, in this order: `id`,
`project`, `task`, `asked_by`, `asked_at`, `question`, `status`, `answer`,
`answered_at`, `used_by`, `used_at`, `used_note`.
[`DESIGN.md`](DESIGN.md) shows a whole entry.

- `id` is `q-YYYY-MM-DD-<project>-NNN`: today's date, the project in lower
  case, and the next free three-digit number for that day and project, for
  example `q-2026-10-09-pcb-002`. Ids are unique within one checkout; a merge
  that keeps two entries with one id must renumber one, or the server and the
  command refuse the file.
- `project` is one of `PCB`, `DATASET`, `Research`, `Library` or `General`.
  Library is the tool and skill library; General is everything else. The
  command, the server and the page refuse any other value, so a new project
  needs a page change first (the five steps in `DESIGN.md`).
- One question per entry, in plain words, about one decision. Offer the
  options when there are options. Do not ask what dev's records already say.
- `task` names the task the answer blocks, for example "CO detector v0.4
  order". `asked_by` is your name: Peter, Aster or May. `asked_at` is now,
  with its offset, such as `2026-10-09T10:00:00+08:00`.
- `status` is `open`; the other five fields (`answer`, `answered_at`,
  `used_by`, `used_at`, `used_note`) are empty strings.

The command keeps every other entry as it was and saves the whole file as JSON
with two-space indent and a final newline, by temporary file and rename. It
changes nothing in a file that is not valid and says where, because the page
refuses an invalid file whole and one broken entry hides every question.

## An agent waits for its answer in the background

`fixed`

An agent that cannot go on without the answer starts `dashboard wait <id>`
in the background with a timeout, for example `dashboard wait <id> --timeout
3600`, so Claude Code wakes the session when it ends, with the answer in its
output. The command exits with one of these codes:

| Code | Means |
| --- | --- |
| 0 | Answered: the answer is printed |
| 1 | `ask` or `used` could not read or write the file, or it is not valid |
| 2 | No such question, or `ask` or `used` refused the request and said why |
| 3 | `wait` timed out; the question is still open |
| 4 | `ask` or `used` found the mailbox busy (another writer's lock for 5 s, or a reader holding the file); run it again |
| 130 | Interrupted |

## An answer is never edited and a question is never deleted

`fixed`

- `answer` and `answered_at` are Zack's. Never change, shorten or tidy them,
  and never write them yourself. If an answer is unclear, ask a new question
  that names the old id.
- Never delete a question or change its text, even your own. If it was wrong,
  ask a new one that says it replaces the old id, and tell Zack in your report.

## An answer is marked used once you have acted on it

`fixed`

When you act on an answered question, run `dashboard used <id> --by <your
name> --note "<one line>"`. It sets `status` to `used`, `used_by` to your
name, `used_at` to now and `used_note` to your line saying what changed, such
as "Video tools moved to search-only in the index.", and changes nothing else;
it refuses an open or already used question. The page then moves it to
history and locks it, so mark it after the work, not before. If you could not
use an answer, leave it `answered` for the next agent. Name the ids you used
in your task report.

## The workspace's own records stay the source of truth

`fixed`

`questions.json` is a mailbox, not a record. An answer that changes a decision,
a requirement or a status is also written where the workspace records that
decision (the task file, spec or review that raised it), citing the question
id, in the same task. If an answer conflicts with a workspace record, do not
pick one silently: tell the owner. The router `CLAUDE.md` at the dev root
outranks this file.

## snapshot.json is generated and never edited by hand

`fixed`

`dashboard export`, run from the dev root, writes `snapshot.json` from the
workspace's records: the open items for PCB, DATASET and Research, and the
library list. Nothing runs it on a schedule; run it by hand when the page
should catch up. The file is git-ignored. To fix an entry in it, fix the record
it came from, then export again.

## The bridge and the taskboard start only on request, and the key stays hidden

`fixed`

Zack starts the bridge in a terminal from this folder:
`node codex-bridge.mjs --folder <project folder>` (`--port` changes 47901).
It listens on `127.0.0.1` only, refuses any request without its one-time key
and talks to Codex through one `codex app-server` it starts and ends: it lists
every Codex thread on the computer and runs each prompt read-only unless Zack
allows `workspace-write` for one prompt in that folder; full access is never
offered and approvals are off. It runs only while its window is open, every
prompt spends Codex quota, and Codex run through it keeps these rules. The
routes are in [`DESIGN.md`](DESIGN.md).

An agent starts it only when asked, and adds `--key-file <new file>` in its
own scratch folder: the key goes into that file and only the path is printed.
The agent never prints, quotes or stores the key; it reads the file into the
`X-Bridge-Key` header, then stops the bridge and deletes the file. The
taskboard starts only with `taskboard start`, never from its own server.

## The app has one lockfile and the server stays loopback-only

`fixed` · the owner, 2026-10-09: Vite, React and TypeScript with lockfile
installs, in place in this folder

`app/` holds the React app: its packages are pinned in
`app/package-lock.json`, each on the licence list that `npm run licences`
checks, installed with `npm ci` (its `.npmrc` keeps install scripts off) and
built with `npm run build` once per device; `node_modules/` and `dist/` are
never committed. `server/` holds the one server, Node built-ins only,
listening on `127.0.0.1` and calling nothing but `127.0.0.1`; `dashboard
serve` starts it by hand, and nothing starts it at sign-in. Follow
[`BRAND.md`](BRAND.md), and give every new visible word in both
`app/src/i18n/en.json` and `zh-HK.json`. The workspace's bilingual check
(`i18n`) skips this folder, so check your own work: `npm test` and `npm run
typecheck` in `app/`, and `node --test
Library/tests/test_dashboard_server.mjs`.

The prototype keeps its own rules until wave 6 retires it: Zack changes
`index.html` and `codex-bridge.mjs` freely, an agent only when asked; they
take no package and no network call except to `http://127.0.0.1`; check them
with `node --check` and `node --test
Library/tests/test_dashboard_page.mjs`.
