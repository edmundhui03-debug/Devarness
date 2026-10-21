# Zack dev. dashboard is a local page where agents ask and the developer answers

> **2026-10-09** · Peter · `current`
>
> A prototype home page for the new developer, Zack: questions from agents at
> the top, open work for PCB, DATASET, Research and the library below, and his
> own notes. It opens from the folder with no install, keeps its answers in a
> file every agent reads, and is built to be changed freely afterwards. The
> app replacing it is `Setup/superpowers/specs/2026-10-09-dev-dashboard-design.md`,
> and where that work stands is
> `Setup/superpowers/plans/2026-10-09-dashboard-wave-1-handoff.md`.

## Contents

- [The owner asked for a vibe-codeable starter, not a finished product](#the-owner-asked-for-a-vibe-codeable-starter-not-a-finished-product)
- [Seven files; index.html and the bridge are the code](#seven-files-indexhtml-and-the-bridge-are-the-code)
- [Questions sit at the top until they are answered and used](#questions-sit-at-the-top-until-they-are-answered-and-used)
- [The task pages read a snapshot written by hand with dashboard export](#the-task-pages-read-a-snapshot-written-by-hand-with-dashboard-export)
- [One click connects the folder; other browsers import and export](#one-click-connects-the-folder-other-browsers-import-and-export)
- [Black and white, two languages, any screen](#black-and-white-two-languages-any-screen)
- [The taskboard shows inside the dashboard while it runs](#the-taskboard-shows-inside-the-dashboard-while-it-runs)
- [The Codex page shows every Codex thread through a local bridge Zack starts](#the-codex-page-shows-every-codex-thread-through-a-local-bridge-zack-starts)
- [The workspace leaves this page free and points to it](#the-workspace-leaves-this-page-free-and-points-to-it)
- [Adding a page takes five steps](#adding-a-page-takes-five-steps)
- [The prototype is done when these checks pass](#the-prototype-is-done-when-these-checks-pass)
- [Later, after the migration](#later-after-the-migration)

## The owner asked for a vibe-codeable starter, not a finished product

`fixed` · the owner's answers of 2026-10-09

The owner's design reference is the SAMPLE_FIRMWARE CTO Workspace (a static site with
hash routes, a sidebar, snapshot data, browser-saved edits and backup
export). From it this keeps the idea and the layout, not the brand. The
owner's answers:

1. The name is **Zack dev. dashboard**: capital Z, the rest small.
2. It is for the new developer, Zack, and travels with his dev folder.
3. Pages: PCB, DATASET, Research and Library tasks, no device page, and
   questions from agents at the top that Zack answers. Answers are saved,
   and the next prompt or task an agent runs reads them and updates
   clearly. A prototype; the owner optimises it after the migration.
4. English with a Hong Kong Cantonese switch.
5. Black and white, with a "vibe" layout.
6. Workspace data refreshed for it automatically.
7. Every feature proposed here goes into the prototype for the owner to try.
8. An `AGENTS.md` for every agent.
9. Links to the device sync page and the tools page.
10. Built in steps with subagents.

Question file: **one** file in this folder, every project's agents write to
it (the owner chose "A").

## Seven files; index.html and the bridge are the code

`fixed` · built after the Library rename window

| File | Holds | Who changes it |
| --- | --- | --- |
| `index.html` | The display: layout, styles and code in one file; the name and the link list sit in one settings block at the top | Zack, freely |
| `DESIGN.md` | This design: what each part does and how to add a page | Zack or an agent, when the design changes |
| `BRAND.md` | The look: black-and-white tokens, type, spacing, the one accent | Zack |
| `AGENTS.md` | For every agent: how to ask, how to read answers, how to report | Peter keeps it right; any agent follows it |
| `questions.json` | Questions from agents and Zack's answers | Agents add questions; the page adds answers |
| `snapshot.json` | Open work per project and the library list, from the workspace; git-ignored | `dashboard export` only |
| `codex-bridge.mjs` | The local bridge the Codex panel talks to | Zack, freely |

Adding a page is one entry in the page list inside `index.html` and one
render function; `DESIGN.md` gives the five steps with an example.

## Questions sit at the top until they are answered and used

`fixed`

```json
{"version": 1, "questions": [{
  "id": "q-2026-10-09-pcb-001", "project": "PCB", "task": "CO detector v0.4",
  "asked_by": "Peter", "asked_at": "2026-10-09T10:00:00+08:00",
  "question": "Which battery holder footprint should v0.4 use?",
  "status": "open", "answer": "", "answered_at": "",
  "used_by": "", "used_at": "", "used_note": ""}]}
```

- **open** — shown at the top of the page with an answer box.
- **answered** — Zack saved an answer; still shown, marked "waiting for an
  agent".
- **used** — an agent read it on its next task, acted on it and wrote one
  line in `used_note` saying what changed. It moves to the history list.

An agent never edits an answer, never deletes a question and keeps IDs
unique (`q-<date>-<project>-<number>`). `AGENTS.md` carries these rules and
tells an agent to read the file at the start of every task in dev.

## The task pages read a snapshot written by hand with dashboard export

`fixed`

`dashboard export` (in `Library/bin`, test-first) writes `snapshot.json`:
for each of PCB, DATASET and Research the open items `md-format status`
already finds (title, state, file and line), and for Library the indexed
tools and skills with their one-line purpose. A project is every file under
its folders: `PCB Tools/` or `Projects/PCB`, `DATASET/` or `Projects/DATASET`,
`Research/` or `Projects/Research`; dev has none yet, so the lists start
empty. dev has no scheduled refresh, so nothing runs it on its own: run
`dashboard export` from the dev root whenever the page should catch up. It
reads the workspace's records and writes one git-ignored file; it never edits
a record. The snapshot holds no absolute path and no user name: paths are
relative to the dev root or start `~/`.

## One click connects the folder; other browsers import and export

`partial` · the folder connection is checked in the browser during the build

A page opened from disk cannot read files beside it, so the page asks once
to **connect this folder** (Chrome and Edge's folder access). After that it
reads `questions.json` and `snapshot.json` and writes answers straight into
`questions.json`; the folder handle is remembered, and Chrome asks for one
click again after a restart. That save takes no lock, unlike `dashboard serve`
and the `dashboard` command, so a write made at the same moment can be lost.
Where folder access does not exist, the page offers **import** for both files
and **download** for the answered `questions.json`, which Zack puts back in
the folder. Notes and to-dos stay in the browser with **backup export and
restore**; a malformed backup is refused before anything is replaced.

## Black and white, two languages, any screen

`fixed`

Black text on white or white on black, chosen by the system or a switch;
bold headings, thin rules, monospaced labels, generous space. The only
accent marks a question that needs an answer. System fonts only, so nothing
is downloaded. Every word sits in one text table with English and Hong Kong
Cantonese; a switch changes the language and remembers the choice. The
layout collapses the sidebar into a menu below tablet width and never
scrolls sideways on a phone.

## The taskboard shows inside the dashboard while it runs

`partial` · built and node-tested 2026-10-09; the browser check is item 10 of
the checks below

The owner asked for `chuspeeism/dashi-taskboard` (Codex Taskboard,
Apache-2.0, a local issue board, Node 22.5+, SQLite) to be installed and to
show inside the dashboard. Intake installed it with its warnings settled as
recommended (`Library/setup/dev-taskboard.md`). Zack starts it in a
terminal with `taskboard start`, which binds `127.0.0.1:47823`, so it
stays on this computer; Ctrl+C stops it. The dashboard never starts it.

The **Taskboard** page, between Codex and Links, asks the port on arrival and
on **Check again**: one `no-cors` request with a two-second timeout, whose
reply is never read. When the board answers, it fills the content area in a
frame at least 70% of the window high, with **Open in a new tab** beside it.
When it does not, a card in both languages says it is not running, gives the
start command and says it stays on this computer. The frame sits outside the
part of the page that re-renders, so switching language or page never
reloads the board. The sidebar's Codex Taskboard link opens this page; the
Links page keeps the new-tab link.

The page's security policy frames one origin, `http://127.0.0.1:47823`. To
move the board, change `taskboardPort` in `SETTINGS`, the policy's
`frame-src` and `DEVARNESS_TASKBOARD_PORT` for `taskboard` together: a port the
policy does not name is detected as running, then shown as a blocked frame.

## The Codex page shows every Codex thread through a local bridge Zack starts

`fixed` · the owner, 2026-10-09: "the prototype doesnt work for codex so I
want the fix in codex that can tell what is going on and running ... fix it
first"

The first bridge ran `codex exec --json` and saw only the prompts it started
itself, so the page could not show what Codex was doing anywhere else. The
bridge now runs one `codex app-server`, Codex's own local protocol (its
messages are printed by `codex app-server generate-json-schema`), started on
first use and ended with the bridge. A page cannot start programs, so Zack
runs `node codex-bridge.mjs --folder <project>`; it listens on `127.0.0.1`
only, refuses any request whose `Host` is not its own address (a site that
rebinds its name to this computer), prints a one-time key and answers only
requests that carry it in the `X-Bridge-Key` header, the event stream
included. The page keeps the key in the tab's storage and never shows it in
the key field again.

| Route | What it does |
| --- | --- |
| `GET /health` | The folder, the Codex command and whether the app-server is up |
| `GET /account` | Signed in or not, the plan and the quota windows; never the email |
| `POST /login` | Starts a ChatGPT sign-in and returns its page, which the Codex page opens in a new tab |
| `GET /threads` | The 50 most recent threads on this computer, `codex exec` runs included, running first |
| `GET /thread?id=` | One thread's last 20 turns, long output cut to 4,000 characters |
| `POST /run` | A prompt in a new thread in the folder, or in a listed thread |
| `POST /stop` | Interrupts a turn this bridge started |
| `GET /events` | Codex's notifications as a stream, without token-by-token deltas |

A thread counts as working elsewhere while its session file changed in the
last two minutes, later than this bridge's own last turn there; that is a
guess from recency, not a lock, and such a thread is not continued from here.
The page refreshes its list every 15 seconds and on each event. Approvals
are off: a request Codex sends anyway is declined and shown. The sandbox
defaults to read-only; Zack can switch one prompt to workspace-write, in the
bridge's own folder only, with the temporary folders and the network shut;
a thread from another folder continues read-only; full access is never
offered. Each prompt holds its thread until Codex reports the turn finished,
even when the start reply never comes, and the page frees Run when the turn
ends, Codex stops or the event stream closes.
`--allow-origin http://127.0.0.1:<port>` admits one more page on this
computer, such as the next dashboard's. The bridge runs only while its
window is open, never at sign-in, and each prompt spends the Codex
account's quota.

## The workspace leaves this page free and points to it

`fixed`

- `i18n` skips `Library/dashboard/`, test-first, because the page carries its
  own English and Hong Kong Cantonese text table and switch rather than
  generated `data-i18n` keys. The prototype itself still ships both
  languages. The Markdown files here still pass `md-format check`.
- The router's ownership table gets one line pointing here; this folder
  repeats none of the workspace's rules.
- The page links, relatively, to the workspace's `README.md` and
  `LESSONS.md`.

## Adding a page takes five steps

`fixed` · worked through for a SAMPLE_FIRMWARE task page; steps 1 and 2 are the page,
steps 3 and 4 connect its questions and its data

A page is a name, one entry in the page list and a render function. A task
page reuses the render function that PCB, DATASET and Research share, so it
needs no new code. Every `index.html` edit below is in its script block.

1. **Give the page its words in both languages.** Add one key to the English
   table and one to the Hong Kong Cantonese table (`TEXT`, `index.html:226`).
   A project name stays in English in both:

   ```js
   'nav.sample_firmware': 'SAMPLE_FIRMWARE',   // in TEXT.en
   'nav.sample_firmware': 'SAMPLE_FIRMWARE',   // in TEXT['zh-HK']
   ```

2. **Add the page to the list.** One line in `PAGES` (`index.html:213`). The
   sidebar link, the route `#sample_firmware` and the page title follow from it, in list
   order:

   ```js
   { id: 'sample_firmware', text: 'nav.sample_firmware', render: () => renderTasks('SAMPLE_FIRMWARE', 'nav.sample_firmware') },
   ```

   A page that is not a task list gives `render` its own function instead,
   one that returns DOM nodes built with `el(...)` and `t(...)`, never
   `innerHTML` filled from data.

3. **Let agents ask about it.** The project list has three copies; add the
   name to all of them, then to the project list in
   [`AGENTS.md`](AGENTS.md):

   - `PROJECTS` in the prototype (`index.html:668`);
   - `PROJECTS` in the server (`server/questions.mjs:8`);
   - `QUESTION_PROJECTS` in the `dashboard` command
     (`Library/bin/dashboard:208`), the list `dashboard ask --project`
     accepts.

   A copy without it refuses the whole file: the prototype or the server
   loads nothing from a `questions.json` holding `"project": "SAMPLE_FIRMWARE"`, and
   `dashboard ask --project SAMPLE_FIRMWARE` stops with exit 2:

   ```js
   const PROJECTS = ['PCB', 'DATASET', 'Research', 'SAMPLE_FIRMWARE', 'Library', 'General'];
   ```

4. **Teach the exporter the folder, test first.** In the exporter's test, add a
   SAMPLE_FIRMWARE section to the fixture and expect it where the Research one is
   expected (`test_each_project_lists_its_live_sections_and_nothing_else`),
   and add SAMPLE_FIRMWARE to the set of names pinned by
   `test_the_snapshot_has_the_agreed_shape`. Watch both fail, then add the
   prefixes to `PROJECTS` near the top of `Library/bin/dashboard` and run
   `dashboard export`:

   ```python
   PROJECTS = (("PCB", ("PCB Tools/", "Projects/PCB")), ...,
               ("SAMPLE_FIRMWARE", ("SAMPLE_FIRMWARE/", "Projects/SAMPLE_FIRMWARE")))
   ```

   `snapshot.json` then holds a `SAMPLE_FIRMWARE` list. A page whose name the snapshot
   lacks does not fail; it reads "No open items in the snapshot".

5. **Check it in the browser.** Run `node --check` on the script. Open the
   page, choose SAMPLE_FIRMWARE in the sidebar, switch to Cantonese, then narrow the
   window to 375 px: the page appears, every word changes and nothing scrolls
   sideways. Open the Questions page too, to confirm a question for the new
   project still loads.

Until a SAMPLE_FIRMWARE document carries a state line such as `open` (the format is
in the `markdown-format` skill), `md-format status` finds no marked section
for it, and the new page reads "No open items in the snapshot".

## The prototype is done when these checks pass

`partial`

1. `index.html` opens from disk with no network request and no console
   error.
2. With the folder connected: an open question shows at the top; saving an
   answer writes it into `questions.json`; reloading keeps it.
3. Without folder access: import, answer and download produce a valid
   `questions.json`.
4. A note survives a reload; backup export then restore returns it; a
   malformed backup is refused with a message.
5. The language switch changes every visible word and is remembered.
6. At 375 px wide nothing scrolls sideways and every page is reachable.
7. `dashboard export` passes its tests and writes a valid
   `snapshot.json` from the real workspace.
8. An agent following `AGENTS.md` reads an answer, marks it used with a
   note, and the page shows it in history.
9. With the bridge running, the Codex page shows the account, the quota and
   every Codex thread; a read-only prompt streams Codex's reply into the
   page; a request without the key is refused; Stop ends the turn; the
   bridge listens on `127.0.0.1` and nowhere else.
10. With `taskboard start` running, the Taskboard page shows the board in
    its frame; with it stopped, Check again shows the card with the start
    command, and after a restart Check again brings the board back.

## Later, after the migration

`open` · the owner optimises the prototype

Optional loopback server instead of folder access, a Library search box,
pulling the taskboard's issues into the task pages, and a phone view served
on the home network like the device sync page.
