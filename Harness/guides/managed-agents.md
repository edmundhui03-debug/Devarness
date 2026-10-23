# Managed Agents run the loop in the cloud and the tools on your machine

> **2026-09-17** · Peter · `current`
>
> Anthropic's "Ship your first Managed Agent" workshop was studied from its
> audio, its screen and its pinned source, then checked against today's
> reference and two SDK releases. Its model still holds: an agent, an
> environment and a session, a loop that runs server-side and speaks in
> events, and custom tools answered from your own process. What changed since
> May makes a fresh install fail before any request; the offline lab proves it.
>
> **2026-10-03:** the offline lab, its installer and `managed-agents` were
> removed on the owner's word. What it taught stays here; its commands no
> longer run.

## Contents

- [The study used every track, and each caught what the others missed](#the-study-used-every-track-and-each-caught-what-the-others-missed)
- [Three resources and a server-side loop are the whole model](#three-resources-and-a-server-side-loop-are-the-whole-model)
- [Seven functions build the incident agent, one call each](#seven-functions-build-the-incident-agent-one-call-each)
- [Sessions speak in events, and the client answers custom tools inline](#sessions-speak-in-events-and-the-client-answers-custom-tools-inline)
- [A client must stop on more than a finished turn](#a-client-must-stop-on-more-than-a-finished-turn)
- [The live demo shows what the slides leave out](#the-live-demo-shows-what-the-slides-leave-out)
- [Beyond the basics has grown since May](#beyond-the-basics-has-grown-since-may)
- [Screen, audio and source disagree in five places](#screen-audio-and-source-disagree-in-five-places)
- [Today's SDK breaks the workshop before any request](#todays-sdk-breaks-the-workshop-before-any-request)
- [The lab proves the wire and is opt-in on each device](#the-lab-proves-the-wire-and-is-opt-in-on-each-device)
- [Peter and Aster carry four rules and four design habits into dev](#peter-and-aster-carry-four-rules-and-four-design-habits-into-dev)
- [Open after this study](#open-after-this-study)
- [What this could not establish](#what-this-could-not-establish)

## The study used every track, and each caught what the others missed

The talk is [Ship your first Managed
Agent](https://www.youtube.com/watch?v=19HDQ9HppOA), presented by Isabella He of
Anthropic's Applied AI team at Code with Claude London and uploaded on
2026-05-26 (37:09). It builds an incident-investigation agent live and then
explains what happened underneath.

| Track | How it was read | Evidence |
| --- | --- | --- |
| Audio | YouTube's auto-captions, deduplicated into timestamped paragraphs | timestamps below; the transcript itself is not committed |
| Screen | The 1080p stream: a contact-sheet tile every 5 s, the slides at full resolution, and a 97-frame delegated log of 09:15–28:25 | screen log, archived in `_archive/2026-10-08/peter-evidence/` |
| Source | [anthropics/cwc-workshops](https://github.com/anthropics/cwc-workshops), Apache-2.0: `7304cf0` is the code on screen, `068b84b` is pinned at `Harness/cwc-workshops` | `path:line` below, at `068b84b` unless marked |
| Reference | Claude Code's bundled `claude-api` skill, 2.1.274 | cited by path inside that skill; a delegated drift audit, archived in `_archive/2026-10-08/peter-evidence/` |
| SDK | `anthropic` 1.0.0 and 1.6.0, introspected and run by the lab's probe | `Harness/verification/managed-agents-verification.json` |

No single track was enough. The audio never gives the repository address or
shows the code. The screen shows a clone command that fails. The source and
the reference disagree about paths the demo proved worked in May.

`video-study`, added from this study, now repeats the audio-and-screen part of
the method for any video.

## Three resources and a server-side loop are the whole model

The talk places Managed Agents as the third way to build (02:10–04:30). With
the raw Messages API you write the loop, context handling and recovery
yourself. The Agent SDK packages Claude Code's harness as a library, but you
still host and scale it. Managed Agents runs the loop, the sandbox, session
state and scaling for you, leaving the task, the agent's configuration and your
custom tools.

Everything rests on three resources (05:55):

| Resource | What it holds | What to remember |
| --- | --- | --- |
| `/v1/agents` | Model, system prompt, tools, MCP servers, skills | Versioned; create once and reuse the ID |
| `/v1/environments` | Container type, networking, allowed hosts | Reusable template for where tools run |
| `/v1/sessions` | One agent plus one environment, with mounted files | Streams events; persists server-side |

The architectural point (07:20–09:15) is that the loop no longer shares a box
with tool execution. The loop is a shared Anthropic service; the sandbox is
provisioned only when a tool needs it. The talk draws two consequences:
credentials can stay out of the sandbox, and time to first token falls because
no container starts per session. The speaker put the cut above 90% at p95; that
figure appears nowhere in the reference and stays a talk claim.

The talk also argues that harness workarounds age with the model (04:30–05:55).
Its example: mitigations for a model that wrapped tasks up early became dead
weight once the next model stopped doing it. dev now records the model behind
any such rule — see the root `CLAUDE.md`.

## Seven functions build the incident agent, one call each

The workshop's scenario is a fictional checkout outage with a dashboard whose
chat panel stays offline until each function is filled in. The log the agent
searches is generated by the seeded `data/generate_log.py`; the lab's copy has
69,740 lines and 14,875,565 bytes, the figures the presenter's sandbox reported
on screen at 20:13.

| # | Function | SDK call | Source | What it teaches |
| --- | --- | --- | --- | --- |
| 1 | `setup_agent` | `beta.skills.create`, `beta.agents.create` | `Harness/cwc-workshops/ship-your-first-managed-agent/agent_complete.py:19` | Define the agent once. HEAD uploads a runbook Skill first; the video's version had no Skill and used `claude-opus-4-7` (`git show 7304cf0:ship-your-first-managed-agent/agent_complete.py`) |
| 2 | `setup_environment` | `beta.environments.create` | `agent_complete.py:39` | A cloud container with unrestricted networking; a random suffix keeps names unique |
| 3 | `upload_log` | `beta.files.upload` | `agent_complete.py:49` | Give the agent the data a human on call would open |
| 4 | `start_session` | `beta.sessions.create` | `agent_complete.py:55` | Bind agent and environment and mount the log |
| 5 | `stream_reply` | `beta.sessions.events.stream`, `.send` | `agent_complete.py:65` | Open the stream before sending; answer custom tools from inside the loop |
| 6 | `handle_tool` | none — local | `agent_complete.py:93` | Tools run in your process; the same wire protocol serves a JSON file or a monitoring API |
| 7 | `delete_session` | `beta.sessions.delete` | `agent_complete.py:107` | Sessions are real stored resources; deleting one removes its history |

The agenda slide at 01:05 promised six functions; the code, its docstring and
the README (`README.md:50`) all have seven, `delete_session` being the one the
talk treats as an extra.

## Sessions speak in events, and the client answers custom tools inline

A session is not request and response (28:25). The client posts `user.*`
events — a message, a custom tool's result, a permission confirmation, an
interrupt — and reads `agent.*` and `session.*` events from a stream: messages,
built-in, custom and MCP tool calls, the idle signal with its stop reason, and
errors.

A custom tool (29:25) is a round trip over that stream. The cloud agent emits
`agent.custom_tool_use`; the script that holds the stream open runs the
function and posts `user.custom_tool_result` with the same event id. Nothing
calls into the laptop, so no inbound port is needed.

The lab's probe confirmed the order on both SDKs: the `GET` of
`/v1/sessions/{id}/events/stream` goes out before the message is posted, and
the tool result names the tool-use id it answers. The slide's shorter `/stream`
path is not the real one; the reference gives `/events/stream`
(`shared/managed-agents-api-reference.md:81`).

## A client must stop on more than a finished turn

The talk's state diagram (31:05) has four statuses: `idle` waiting for input,
`running`, `rescheduling` while a transient error is retried, and `terminated`
after an unrecoverable one. Webhooks can wake a session from outside.

Today's reference widens two of them. `terminated` also covers a session that
finished normally (`shared/managed-agents-core.md:44`). An idle event's stop
reason can also be `retries_exhausted` or `budget_reached`, and a client should
leave its read loop on any idle stop reason except `requires_action`, or on
`session.status_terminated` (`shared/managed-agents-client-patterns.md:112-131`).
The workshop's panel leaves only on `end_turn`
(`ship-your-first-managed-agent/provided.py:217`), so a failed or budget-capped
session would leave it waiting.

## The live demo shows what the slides leave out

The first run (19:45) called the sandbox and all three local tools, but its
answer never appeared: by 21:14 every tool chip was complete and the chat was
empty, and at 22:36 the presenter opened a second session with the same
prompt. The talk does not mention the stall. The delegated screen log reports
that the first session's replay after the refresh showed a finished answer;
Peter did not re-read that frame. Either way it is the case the reference warns
about: a server-sent stream has no replay, so a client that loses or stalls on
it must reconnect and list events to catch up
(`shared/managed-agents-events.md:160`). The workshop has no reconnect.

The second run named the cause: commit `a3f9c21`, a refactor of the checkout
summary builder that turned one batched query into a query per order and
exhausted the database pool. That matches the pinned data
(`ship-your-first-managed-agent/data/diff.txt:1-2`). It also ruled out three
other deploys and proposed a rollback, a check that the pool recovered, and a
query-count regression test.

A hard refresh (26:07) reopened the newest session with its history replayed
from the server; the panel's caption says the session lives in the cloud, not
the browser. The session list, though, read `idle` throughout every run: the
panel caches it for twenty seconds (`provided.py:55`) and draws it before the
stream starts. Liveness comes from the event stream, not a cached list.

## Beyond the basics has grown since May

The closing slide (32:35) listed nine features as beta. Each row below was read
at source in the `claude-api` skill.

| Feature | As shown in May | As documented now |
| --- | --- | --- |
| Subagents | A field called `callable_agents` | No such field anywhere; delegation is `multiagent` with a `coordinator` roster that can include the agent itself (`shared/managed-agents-multiagent.md:22`) |
| Memory | Persistent memory mounted into the container | Memory stores attached as a `memory_store` session resource (`shared/managed-agents-memory.md:57`) |
| Outcomes | A structured record of what the agent produced | A `user.define_outcome` event with a rubric, graded by a separate evaluator; the default kickoff for deliverables (`shared/managed-agents-outcomes.md:7`) |
| Vaults | Per-user credentials referenced by id | Also `environment_variable` credentials the sandbox sees only as a placeholder, substituted at egress (`shared/managed-agents-tools.md:318`) |
| Webhooks | Console, Settings | Console, Manage, Webhooks (`shared/managed-agents-webhooks.md:11`) |
| Permission policies | `always_ask` pauses for confirmation | Also `auto`, where the server decides per call (`shared/managed-agents-tools.md:102`) |
| Not on the slide | — | Scheduled deployments (`shared/managed-agents-scheduled-deployments.md:39`) and hard per-session budgets (`shared/managed-agents-core.md:141`) |

Two things the talk named are missing from the `claude-api` skill but ship in
both installed SDKs: memory "dreaming" as `client.beta.dreams` (beta
`dreaming-2026-04-21`) and private MCP tunnels as `client.beta.tunnels` (beta
`mcp-tunnels-2026-06-22`). Both were read from SDK source in the lab's runtime
(`anthropic/resources/beta/dreams.py`, `anthropic/resources/beta/tunnels/`),
not exercised.

## Screen, audio and source disagree in five places

| What | One track says | Another says | Evidence |
| --- | --- | --- | --- |
| Function count | Agenda slide: six (01:05) | Code and README: seven | `README.md:50` |
| Clone URL | Setup slide: `anthropics/cwc-workshops` (09:37), which resolves | README: `anthropic-experimental/cwc-workshops`, which asks for a login | `README.md:31` |
| `handle_tool` | Slide reads JSON files by a `sha` argument (29:30) | Code looks up preloaded data by `commit` | `agent_complete.py:93` |
| Latency | Banner and audio: p99 at ten times baseline (10:55, 21:11) | The same dashboard's tile and data: about fifty-eight times | `data/metrics.json`, first sample 62.4 ms against 3,638 ms |
| Networking | Audio: an allow-list (14:41) | Code: `unrestricted` | `agent_complete.py:39` |

The screen log lists smaller slips. The rule the study produced is in
`Claude/REMINDERS.md`: check anything a slide shows against the commit it came
from.

## Today's SDK breaks the workshop before any request

The workshop asks for `anthropic>=0.97.0` with no upper bound. A fresh install
on 2026-09-17 resolves 1.6.0. The lab ran all seven functions offline on the
SDK its commit resolved, 1.0.0, and on 1.6.0:

| Function | SDK 1.0.0 | SDK 1.6.0 |
| --- | --- | --- |
| `setup_agent` | passes | `TypeError`: `Skills.create()` no longer takes `display_title` |
| The other six | pass | pass |

So `setup_agent()` and `e2e.py` stop at the Skill upload on a new install, with
no request sent. The record's `drift` shows the change three ways
(`Harness/verification/managed-agents-verification.json`): the outcome above;
the requests, where 1.0.0 sent the old Files beta header and 1.6.0 sends none on
the upload; and the recorded parameter names, where `display_title` became
`display_name` and every tracked call gained `workspace_id`. The same names show
`agent_id` on `sessions.list` in both releases, although the reference does not
document the filter.

The fix belongs upstream — rename the keyword or bound the SDK version — and
the pinned clone stays untouched.

## The lab proves the wire and is opt-in on each device

```sh
python3 Harness/setup-managed-agents.py --install   # clone must be at the pin
Harness/bin/managed-agents --check                # read-only
Harness/bin/managed-agents --verify               # offline probe, both SDKs
```

The runtime lives under `Harness/.runtime/cwc-workshops/<pin>/`: an archive of
the workshop folder only, the generated log, a CPython 3.12.14 environment
locked to the workshop's requirements as of its commit, and a second environment
with today's SDK alone. The probe imports the reference implementation with a
stub Streamlit and a mocked HTTP transport, calls each function, and checks
paths, beta headers, bodies, ordering and the custom-tool round trip. It also
records the parameter names of every SDK call the guide relies on, so each
`--verify` re-checks those claims at the pin. Sockets are blocked, the key is
synthetic, and no credential file is written.

It proves what the SDK sends. It cannot prove what Anthropic's server accepts:
whether today's API still takes the relative mount path, or how a session ends.
Bootstrap links the launcher but does not build the lab, so a device that never
installs it stays `READY`. The record is
`Harness/verification/managed-agents-verification.json`.

## Peter and Aster carry four rules and four design habits into dev

| Lesson | From the talk | Where it landed |
| --- | --- | --- |
| Study a video from both what is said and what is shown | the method of this study | `video-study`; router and `Claude/TOOLS.md` |
| Define done as criteria a separate check can grade | Outcomes, 34:28 | `grill-first` step 4, the done-rubric |
| A harness workaround is tied to the model that needed it | 04:30–05:55 | Root `CLAUDE.md`, the model-era rule |
| Teaching material simplifies | this study | `LESSONS.md`, from the old reminder "A slide is not the source" |

The design habits need no new file, only attention when building agents here:

1. **Keep secrets out of the agent's context.** The loop and the sandbox never
   hold credentials; a vault or a host-side tool does. dev's rule against
   provider secrets in tracked notes is the same idea.
2. **Keep an append-only record of what happened.** Sessions resume because
   events are appended, not overwritten. dev's agent ledger and change log work
   the same way.
3. **Name states and stop reasons.** A client that knows only "finished" hangs
   on "failed" and "paused". The start check's `READY`, `DEGRADED` and `FAILED`
   follow that; keep new states explicit.
4. **Give an agent the runbook a human would use.** HEAD's Skill is an order of
   operations, a list of past causes and a fixed one-line conclusion
   (`incident-triage-runbook/SKILL.md`). `LESSONS.md` is dev's list of past
   causes.

## Open after this study

| Item | State | What settles it |
| --- | --- | --- |
| A live run of the workshop on the owner's account | `needs-owner` | The owner exporting `ANTHROPIC_API_KEY` in their own shell and running `Harness/bin/managed-agents --live`. The guarded runner (`Harness/managed-agents-live.py`) follows `e2e.py` under a US$3 session budget it confirms before asking anything, stops at 10 minutes, tears down what it made and writes `Harness/verification/managed-agents-live.json`. It has run only against a fake client |
| Aster's adversarial review of this work | `open` | Aster's quota, recorded as returning 2026-09-19 22:28 |
| `agents-that-remember`, `production-ready-agent` and six more workshops in the same clone | `fixed` | Studied at `068b84b` on 2026-09-17: five study records, removed 2026-10-02, and what the old workspace took from them are in its history and archive |
| Neutralising spreadsheet formulas in Example App's CSV exports, such as BOMs | `open` | Example App's own session. Research Desk prefixes a cell starting with `=`, `+`, `-`, `@`, tab or carriage return with an apostrophe (`research-desk/src/lib/scorecard.ts:127-130`, tested at `research-desk/tests/scorecard.test.ts:54-57`, both at `068b84b`) |
| Memory consolidation for agent memory, the talk's "dreaming" | `open` | Its own grilling round and design |

## What this could not establish

Server behaviour today is documented, not observed: the relative mount path,
the `agent_id` filter and the newer stop reasons were not exercised against the
API. The talk's performance figures appear nowhere in the reference. Whether
the first live run finished rests on the delegated screen log, not a frame
Peter read. The presenter's slides and audio were paraphrased from a
caption-derived transcript and screen frames; where they disagreed with the
source, the source was taken as authoritative.
