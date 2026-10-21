// Tests for Library/dashboard/server/claude.mjs and the Claude routes (wave 4):
// sessions from a fake home's registry and transcripts, a transcript's tail as
// steps, masked, and no file opened outside the plan's allowed names. No test
// reads the real ~/.claude. Usage: node --test test_dashboard_claude.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs, { mkdirSync, mkdtempSync, rmSync, statSync, utimesSync, writeFileSync } from 'node:fs';
import http from 'node:http';
import { execFileSync, spawn } from 'node:child_process';
import { syncBuiltinESMExports } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { agentRow, findAgent, findTranscript, listClaude, readSteps, sessionParts } from '../dashboard/server/claude.mjs';

const MIN = 60_000;
const HOUR = 60 * MIN;
const DEAD_PID = 999_999;
const alive = (pid) => pid !== DEAD_PID;
const plain = (v) => v; // masking off: the known-bad case every masking test starts from
const uuid = (n) => `${String(n).padStart(8, '0')}-0000-4000-8000-${String(n).padStart(12, '0')}`;
const AT = '2026-10-15T08:00:00.000Z';

function fakeHome(t) {
  const home = mkdtempSync(join(tmpdir(), 'dash-claude-'));
  t.after(() => rmSync(home, { recursive: true, force: true }));
  mkdirSync(join(home, '.claude', 'sessions'), { recursive: true });
  mkdirSync(join(home, '.claude', 'projects', 'C--dev'), { recursive: true });
  return home;
}
const cl = (home, ...parts) => join(home, '.claude', ...parts);
// Writes a file, its folders first; ageMs sets its mtime that long ago.
function put(path, text, ageMs) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, text);
  if (ageMs !== undefined) {
    const when = new Date(Date.now() - ageMs);
    utimesSync(path, when, when);
  }
  return path;
}
const jsonl = (lines) => lines.map((l) => (typeof l === 'string' ? l : JSON.stringify(l))).join('\n') + '\n';
const transcript = (home, id, lines, ageMs, dir = 'C--dev') => put(cl(home, 'projects', dir, `${id}.jsonl`), jsonl(lines), ageMs);
const folder = (home, id, dir = 'C--dev') => cl(home, 'projects', dir, id);
const register = (home, pid, fields) => put(cl(home, 'sessions', `${pid}.json`), JSON.stringify({ pid, ...fields }));
const user = (content, extra = {}) => ({ type: 'user', message: { role: 'user', content }, timestamp: AT, ...extra });
const assistant = (content, extra = {}) => ({ type: 'assistant', message: { role: 'assistant', content }, timestamp: AT, ...extra });
// Every line of an agent's own file is marked isSidechain, as Claude writes them.
function agent(dir, id, ageMs, meta) {
  put(join(dir, `${id}.jsonl`), jsonl([user('task', { isSidechain: true })]), ageMs);
  if (meta) put(join(dir, `${id}.meta.json`), JSON.stringify(meta));
}
const mtimeIso = (path) => new Date(statSync(path).mtimeMs).toISOString();

test('claude: live sessions from the registry, then the 10 newest that ended in the last 24 h', (t) => {
  const home = fakeHome(t);
  register(home, 101, { sessionId: uuid(1), cwd: 'C:/dev', status: 'busy', name: 'busy work', entrypoint: 'claude-desktop', statusUpdatedAt: Date.now() - MIN });
  register(home, 102, { sessionId: uuid(2), cwd: 'C:/b', status: 'idle', kind: 'interactive', statusUpdatedAt: Date.now() - 2 * MIN });
  register(home, DEAD_PID, { sessionId: uuid(3), cwd: 'C:/dead', status: 'busy', name: 'dead' });
  // The live sessions' transcripts are fresh: they are still never listed again as ended.
  transcript(home, uuid(1), [user('hi')], 0);
  transcript(home, uuid(2), [user('hi')], MIN);
  const ended = [];
  for (let i = 0; i < 11; i++) ended.push(transcript(home, uuid(10 + i), [user('x', { cwd: `C:/e${i}`, entrypoint: 'cli' })], (i + 1) * HOUR));
  transcript(home, uuid(30), [user('old')], 25 * HOUR);
  const { sessions } = listClaude(home, { alive });
  assert.deepEqual(sessions.map((s) => [s.id, s.state]), [
    [uuid(1), 'working'], [uuid(2), 'idle'],
    ...Array.from({ length: 10 }, (_, i) => [uuid(10 + i), 'ended']),
  ]);
  assert.deepEqual(sessions[0], { id: uuid(1), title: 'busy work', cwd: 'C:/dev', state: 'working', source: 'claude-desktop',
    updatedAt: sessions[0].updatedAt });
  assert.equal(sessions[1].source, 'interactive');
  assert.deepEqual(sessions[2], { id: uuid(10), title: uuid(10), cwd: 'C:/e0', state: 'ended', source: 'cli', updatedAt: mtimeIso(ended[0]) });
});

test('claude: a title is the registry name, else the custom title, else the last prompt cut to 80, else the id', (t) => {
  const home = fakeHome(t);
  register(home, 101, { sessionId: uuid(1), cwd: 'C:/a', status: 'busy', name: 'named one' });
  // claudeSessions falls back to the cwd for a session with no name: that is never the title.
  register(home, 102, { sessionId: uuid(2), cwd: 'C:/b', status: 'idle' });
  transcript(home, uuid(2), [user('x')], 0);
  put(join(folder(home, uuid(2)), 'custom-title.json'), JSON.stringify({ customTitle: 'Custom title' }));
  const long = 'Fix the dashboard and then '.repeat(6);
  transcript(home, uuid(3), [{ type: 'last-prompt', lastPrompt: 'first prompt' }, user('x'), { type: 'last-prompt', lastPrompt: long }], MIN);
  transcript(home, uuid(4), [user('x')], 2 * MIN);
  const titles = listClaude(home, { alive }).sessions.map((s) => s.title);
  assert.deepEqual(titles, ['named one', 'Custom title', long.slice(0, 80), uuid(4)]);
});

test('claude: steps, oldest first: prompts, replies, thinking as a marker, tool lines and their results', (t) => {
  const home = fakeHome(t);
  const longCommand = `echo ${'y '.repeat(200)}`;
  const path = transcript(home, uuid(1), [
    user('hello', { timestamp: '2026-10-15T08:00:01.000Z' }),
    user([{ type: 'text', text: 'look at this' }]),
    assistant([
      { type: 'thinking', thinking: 'private thoughts' },
      { type: 'text', text: 'On it.' },
      { type: 'tool_use', id: 'tu1', name: 'Bash', input: { description: 'list', command: 'ls -la' } },
    ]),
    user([{ type: 'tool_result', tool_use_id: 'tu1', content: 'file1\nfile2' }]),
    assistant([{ type: 'tool_use', id: 'tu2', name: 'Read', input: { file_path: 'C:/x.txt' } }]),
    user([{ type: 'tool_result', tool_use_id: 'tu2', is_error: true, content: [{ type: 'text', text: 'no such file' }, { type: 'image', source: {} }] }]),
    assistant([{ type: 'tool_use', id: 'tu3', name: 'Mystery', input: { count: 1 } }]),
    assistant([{ type: 'tool_use', id: 'tu4', name: 'Bash', input: { command: longCommand } }]),
    user([{ type: 'tool_result', tool_use_id: 'not-in-tail', content: 'orphan' }]),
  ]);
  const view = readSteps(path);
  const step = (kind, text, tool = null, error = false, at = AT) => ({ kind, text, tool, error, at });
  assert.deepEqual(view.steps, [
    step('prompt', 'hello', null, false, '2026-10-15T08:00:01.000Z'),
    step('prompt', 'look at this'),
    step('thinking', ''),
    step('reply', 'On it.'),
    step('tool', 'ls -la', 'Bash'),
    step('result', 'file1\nfile2', 'Bash'),
    step('tool', 'C:/x.txt', 'Read'),
    step('result', 'no such file\n[image]', 'Read', true),
    step('tool', '{"count":1}', 'Mystery'),
    step('tool', longCommand.slice(0, 300), 'Bash'),
    step('result', 'orphan'),
  ]);
  assert.equal(view.readable, true);
});

test('claude: sidechain lines, other line types, unparsable lines and unknown blocks are skipped', (t) => {
  const home = fakeHome(t);
  const path = transcript(home, uuid(1), [
    'this line is not JSON',
    { type: 'attachment', attachment: { type: 'file' } },
    { type: 'file-history-snapshot', snapshot: {} },
    user('from a subagent', { isSidechain: true }),
    assistant([{ type: 'mystery', text: 'unknown block' }, { type: 'text', text: 'kept' }], { gitBranch: 'main', cwd: 'C:/dev', entrypoint: 'cli' }),
    { type: 'system', content: 'compacted' },
  ]);
  // A last line still being written: no newline, cut mid-object.
  fs.appendFileSync(path, '{"type":"user","message":{"role":"user","content":"par');
  const view = readSteps(path);
  assert.deepEqual(view.steps.map((s) => [s.kind, s.text]), [['reply', 'kept']]);
  assert.deepEqual([view.readable, view.branch, view.cwd, view.source], [true, 'main', 'C:/dev', 'cli']);
  // An agent's own file is all sidechain lines: read as one, they are kept.
  assert.deepEqual(readSteps(path, { sidechain: true }).steps.map((s) => s.text), ['from a subagent', 'kept']);
});

// Real transcripts, 2026-10-15: of 220 user text lines not marked isMeta, 114 began with
// a tag, 100 of them task notifications; 3 system reminders led the owner's own prompt.
test('claude: lines and tags Claude Code adds are never shown as the owner\'s prompt', (t) => {
  const home = fakeHome(t);
  const path = transcript(home, uuid(1), [
    user('<command-message>init</command-message>', { isMeta: true }),
    user([{ type: 'text', text: '<system-reminder>hook context</system-reminder>' }, { type: 'text', text: 'the real ask' }]),
    user('<system-reminder>\nreminder\n</system-reminder>\nfix the panel'),
    user('<task-notification>\n<task-id>b1</task-id>\n</task-notification>'),
    user('<local-command-stdout>Compacted</local-command-stdout>'),
    user('<command-name>/compact</command-name>\n<command-message>compact</command-message>\n<command-args>keep notes</command-args>'),
    user('<command-message>review</command-message>\n<command-name>/review</command-name>\n<command-args></command-args>'),
    user('<pasted_content id="p1">pasted text</pasted_content> what is this'),
    user('why does <system-reminder> show?'),
    // A command after a reminder, and the owner's words after a command (Aster, F9).
    user('<system-reminder>x</system-reminder><command-name>/review</command-name><command-args>diff</command-args>'),
    user('<command-name>/review</command-name><command-args></command-args>Also check tests.'),
  ]);
  assert.deepEqual(readSteps(path).steps.map((s) => [s.kind, s.text]), [
    ['prompt', 'the real ask'], ['prompt', 'fix the panel'], ['prompt', '/compact keep notes'], ['prompt', '/review'],
    ['prompt', '<pasted_content id="p1">pasted text</pasted_content> what is this'], ['prompt', 'why does <system-reminder> show?'],
    ['prompt', '/review diff'], ['prompt', '/review Also check tests.'],
  ]);
});

test('claude: a result keeps its last 1,500 characters once masked', (t) => {
  const home = fakeHome(t);
  const path = transcript(home, uuid(1), [user([{ type: 'tool_result', tool_use_id: 'tu1', content: `HEAD ${'y '.repeat(1500)}TAIL` }])]);
  const { text } = readSteps(path).steps[0];
  assert.deepEqual([text.length, text.endsWith('TAIL'), text.includes('HEAD')], [1500, true, false]);
});

test('claude: only the last 20 steps; a cut first line, a huge line, an empty file, a missing file and a folder', (t) => {
  const home = fakeHome(t);
  const many = transcript(home, uuid(1), Array.from({ length: 25 }, (_, i) => user(`p${i + 1}`)));
  assert.deepEqual(readSteps(many).steps.map((s) => s.text), Array.from({ length: 20 }, (_, i) => `p${i + 6}`));
  // The window starts inside line 3: that cut line is skipped, lines 4 and 5 are read.
  const lines = Array.from({ length: 5 }, (_, i) => JSON.stringify(user(`q${i + 1} ${'z'.repeat(60)}`)));
  const cut = put(cl(home, 'projects', 'C--dev', `${uuid(2)}.jsonl`), lines.join('\n') + '\n');
  const windowBytes = Buffer.byteLength(`${lines[3]}\n${lines[4]}\n`) + 10;
  assert.deepEqual(readSteps(cut, { windowBytes }).steps.map((s) => s.text.slice(0, 2)), ['q4', 'q5']);
  // The window starts one byte into a line whose rest parses: it is still a cut line (Aster, F10).
  const forged = JSON.stringify(user('FORGED'));
  const real = JSON.stringify(user('real'));
  const stray = put(cl(home, 'projects', 'C--dev', `${uuid(7)}.jsonl`), `X${forged}\n${real}\n`);
  assert.deepEqual(readSteps(stray, { windowBytes: Buffer.byteLength(`${forged}\n${real}\n`) }).steps.map((s) => s.text), ['real']);
  // A window that starts just after a newline keeps that whole line.
  assert.deepEqual(readSteps(stray, { windowBytes: Buffer.byteLength(`${real}\n`) }).steps.map((s) => s.text), ['real']);
  // One line bigger than the window: readable, no steps; with the whole line, the prompt keeps 4,000 characters.
  const huge = transcript(home, uuid(3), [user('x '.repeat(2500))]);
  assert.deepEqual(readSteps(huge, { windowBytes: 1024 }), { readable: true, steps: [], branch: null, cwd: null, source: null, folder: null });
  assert.equal(readSteps(huge).steps[0].text, 'x '.repeat(2000));
  const empty = put(cl(home, 'projects', 'C--dev', `${uuid(4)}.jsonl`), '');
  assert.deepEqual(readSteps(empty), { readable: true, steps: [], branch: null, cwd: null, source: null, folder: null });
  const unreadable = { readable: false, steps: [], branch: null, cwd: null, source: null, folder: null };
  assert.deepEqual(readSteps(cl(home, 'projects', 'C--dev', `${uuid(5)}.jsonl`)), unreadable);
  const dir = cl(home, 'projects', 'C--dev', `${uuid(6)}.jsonl`);
  mkdirSync(dir);
  assert.deepEqual(readSteps(dir), unreadable);
});

test('claude: a tool input nested too deep to mask shows masked, and the steps after it still read (Aster, F8)', (t) => {
  const home = fakeHome(t);
  let deep = '"x"';
  for (let i = 0; i < 20_000; i++) deep = `[${deep}]`;
  const path = transcript(home, uuid(1), [
    `{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t","name":"X","input":{"other":${deep}}}]}}`, user('after')]);
  assert.deepEqual(readSteps(path).steps.map((s) => [s.kind, s.text]), [['tool', '[masked]'], ['prompt', 'after']]);
});

// Planted secrets: each appears with masking off, so the masked case can fail.
const SK = 'sk' + '-PlantedOpenAiKey0123456789abcdef';
const GHP = 'gh' + 'p_PlantedGitHubToken0123456789abcdefgh';
const PASSWORD = 'hunter2-secret';
const API_KEY = 'p' + 'lantedApiKeyValue0123';
const AUTH_PASS = 'PlantedPass99';
const BODY = 'Straddle0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJ';
const SECRETS = [SK, GHP, PASSWORD, API_KEY, AUTH_PASS];
const bodyRuns = (text) => Array.from({ length: BODY.length - 11 }, (_, i) => BODY.slice(i, i + 12)).filter((run) => text.includes(run));
function secretTranscript(home, id, ageMs) {
  return transcript(home, id, [
    user(`deploy with ${SK} please`),
    assistant([{ type: 'text', text: `using ${GHP}` }, { type: 'tool_use', id: 'tu1', name: 'Bash', input: { command: `mysql --password ${PASSWORD} -u root` } },
      // A tool input with none of the known keys, a login object under "auth": only the object rule reaches it.
      { type: 'tool_use', id: 'tu2', name: 'Login', input: { auth: { user: 'admin', pass: AUTH_PASS } } }]),
    // Docker's "auth" as user:password in JSON inside a result, not its base64 form.
    user([{ type: 'tool_result', tool_use_id: 'tu1', content: `{"api_key": "${API_KEY}", "auth": "admin:${AUTH_PASS}"}` }]),
    // The key's start lies before the result's last 1,500 characters, its end inside them.
    user([{ type: 'tool_result', tool_use_id: 'tu1', content: [{ type: 'text', text: `x sk-${BODY}${' .'.repeat(735)}` }] }]),
  ], ageMs);
}

test('claude: a key in a prompt, a reply, a command, a result and one cut by the tail never leaves masked', (t) => {
  const home = fakeHome(t);
  const path = secretTranscript(home, uuid(1));
  const unmasked = JSON.stringify(readSteps(path, { mask: plain }));
  for (const secret of SECRETS) assert.ok(unmasked.includes(secret), `the known-bad case shows ${secret}`);
  assert.notDeepEqual(bodyRuns(unmasked), [], 'the known-bad case shows part of the cut key');
  const masked = JSON.stringify(readSteps(path));
  for (const secret of SECRETS) assert.ok(!masked.includes(secret), secret);
  assert.deepEqual(bodyRuns(masked), []);
});

test('claude: a key in a session title, a custom title, a folder and a workflow summary is masked too', (t) => {
  const home = fakeHome(t);
  register(home, 101, { sessionId: uuid(1), cwd: 'C:/dev', status: 'busy', name: `deploy ${SK}` });
  register(home, 102, { sessionId: uuid(4), cwd: `C:/keys/${GHP}`, status: 'idle' });
  transcript(home, uuid(1), [user('x')]);
  transcript(home, uuid(2), [{ type: 'last-prompt', lastPrompt: `push with ${GHP}` }], MIN);
  transcript(home, uuid(3), [user('x', { cwd: `C:/keys/${SK}` })], 2 * MIN);
  put(join(folder(home, uuid(3)), 'custom-title.json'), JSON.stringify({ customTitle: `title ${GHP}` }));
  put(join(folder(home, uuid(1)), 'workflows', 'wf_r1.json'), JSON.stringify({ workflowName: 'Build', status: 'completed', summary: `used ${GHP}` }));
  const unmasked = JSON.stringify([listClaude(home, { alive, mask: plain }), sessionParts(home, uuid(1), { mask: plain })]);
  for (const secret of [SK, GHP]) assert.ok(unmasked.includes(secret), `the known-bad case shows ${secret}`);
  const masked = JSON.stringify([listClaude(home, { alive }), sessionParts(home, uuid(1))]);
  for (const secret of [SK, GHP]) assert.ok(!masked.includes(secret), secret);
});

test('claude: sessionParts lists the 10 newest subagents and the 5 newest runs, each with at most 30 agents', (t) => {
  const home = fakeHome(t);
  const id = uuid(1);
  transcript(home, id, [user('x')]);
  const sub = join(folder(home, id), 'subagents');
  agent(sub, 'agent-d01', 0, { description: 'Explore code', agentType: 'Explore' });
  agent(sub, 'agent-d02', 2.5 * MIN, { agentType: 'general-purpose' });
  for (let i = 3; i <= 12; i++) agent(sub, `agent-d${String(i).padStart(2, '0')}`, i * MIN);
  put(join(sub, 'agent-d01.prefix.json'), '{}');
  const runFiles = join(folder(home, id), 'workflows');
  const runAgents = join(sub, 'workflows');
  agent(join(runAgents, 'wf_live'), 'agent-l1', 0); // no run file yet, an agent just wrote: running
  agent(join(runAgents, 'wf_stale'), 'agent-s1', 10 * MIN); // no run file, nothing lately: unknown
  put(join(runFiles, 'wf_a.json'), JSON.stringify({ workflowName: 'Build', status: 'completed', summary: 'built it', agentCount: 31,
    startTime: Date.parse(AT), durationMs: 1234, script: 'MARKER-SCRIPT', result: 'MARKER-RESULT', logs: ['MARKER-LOGS'] }), 20 * MIN);
  for (let i = 1; i <= 31; i++) agent(join(runAgents, 'wf_a'), `agent-a${String(i).padStart(2, '0')}`, 20 * MIN + i * 1000);
  put(join(runFiles, 'wf_b.json'), JSON.stringify({ workflowName: 'B', status: 'failed' }), HOUR);
  put(join(runFiles, 'wf_c.json'), JSON.stringify({ workflowName: 'C', status: 'completed' }), 2 * HOUR);
  put(join(runFiles, 'wf_d.json'), JSON.stringify({ workflowName: 'D', status: 'completed' }), 3 * HOUR);
  const { agents, runs } = sessionParts(home, id, { now: Date.now() });
  assert.deepEqual(agents.map((a) => a.id), Array.from({ length: 10 }, (_, i) => `agent-d${String(i + 1).padStart(2, '0')}`));
  assert.deepEqual(agents.slice(0, 3).map((a) => [a.title, a.type, a.run, a.state]), [
    ['Explore code', 'Explore', null, 'working'], ['general-purpose', 'general-purpose', null, 'idle'], ['agent-d03', null, null, 'idle']]);
  assert.equal(agents[1].updatedAt, mtimeIso(join(sub, 'agent-d02.jsonl')));
  assert.deepEqual(runs.map((r) => [r.id, r.name, r.status]), [
    ['wf_live', 'wf_live', 'running'], ['wf_stale', 'wf_stale', 'unknown'], ['wf_a', 'Build', 'completed'], ['wf_b', 'B', 'failed'], ['wf_c', 'C', 'completed']]);
  const build = runs[2];
  assert.deepEqual([build.summary, build.agentCount, build.startedAt, build.durationMs, build.agents.length], ['built it', 31, AT, 1234, 30]);
  assert.deepEqual(build.agents[0], { id: 'agent-a01', title: 'agent-a01', type: null, run: 'wf_a', state: 'idle',
    updatedAt: mtimeIso(join(runAgents, 'wf_a', 'agent-a01.jsonl')) });
  assert.deepEqual(runs[0].agents.map((a) => [a.id, a.run, a.state]), [['agent-l1', 'wf_live', 'working']]);
  assert.deepEqual([runs[0].summary, runs[0].agentCount, runs[0].startedAt, runs[0].durationMs], ['', null, null, null]);
  assert.ok(!JSON.stringify(runs).includes('MARKER-'), 'a run\'s script, result and logs never appear');
});

// The names the plan lets the reader open (Global constraints).
const ALLOWED = [
  /[\\/]\.claude[\\/]sessions[\\/]\d+\.json$/,
  /[\\/]projects[\\/][^\\/]+[\\/][0-9a-f-]{36}\.jsonl$/,
  /[\\/]projects[\\/][^\\/]+[\\/][0-9a-f-]{36}[\\/]custom-title\.json$/,
  /[\\/][0-9a-f-]{36}[\\/]subagents[\\/](?:workflows[\\/]wf_[A-Za-z0-9-]+[\\/])?agent-[A-Za-z0-9]+\.(?:jsonl|meta\.json)$/,
  /[\\/][0-9a-f-]{36}[\\/]workflows[\\/]wf_[A-Za-z0-9-]+\.json$/,
];

test('claude: Claude\'s secret files are never opened and never reach an answer', (t) => {
  const home = fakeHome(t);
  const id = uuid(1);
  register(home, 101, { sessionId: id, status: 'busy', cwd: 'C:/dev' });
  transcript(home, id, [user('x')], MIN);
  put(join(folder(home, id), 'custom-title.json'), JSON.stringify({ customTitle: 'mine' }));
  agent(join(folder(home, id), 'subagents'), 'agent-s1', MIN, { agentType: 'Explore' });
  put(join(folder(home, id), 'workflows', 'wf_r1.json'), JSON.stringify({ status: 'completed' }));
  agent(join(folder(home, id), 'subagents', 'workflows', 'wf_r1'), 'agent-w1', MIN);
  const secrets = {
    credentials: cl(home, '.credentials.json'),
    sessionKey: cl(home, 'sessions', '101.abc123.key'),
    daemonKey: cl(home, 'daemon', 'x.key'),
    sessionEnv: cl(home, 'session-env', id, 'env.sh'),
    snapshot: cl(home, 'shell-snapshots', 'snapshot.sh'),
    history: cl(home, 'history.jsonl'),
    projectHistory: cl(home, 'projects', 'C--dev', 'history.jsonl'),
    toolResults: join(folder(home, id), 'tool-results', 'x.txt'),
  };
  // Each holds a line any reader would show: a registry entry for a live pid and a prompt.
  for (const [name, path] of Object.entries(secrets)) {
    put(path, jsonl([{ pid: 101, sessionId: `MARKER-${name}`, status: 'busy', type: 'user', message: { role: 'user', content: `MARKER-${name}` } }]));
  }
  const opened = [];
  const real = { openSync: fs.openSync, readFileSync: fs.readFileSync };
  fs.openSync = (path, ...rest) => { opened.push(String(path)); return real.openSync(path, ...rest); };
  fs.readFileSync = (path, ...rest) => { opened.push(String(path)); return real.readFileSync(path, ...rest); };
  syncBuiltinESMExports();
  let answers;
  try {
    const path = findTranscript(home, id);
    const found = findAgent(home, id, 'agent-w1');
    answers = [listClaude(home, { alive }), path, readSteps(path), sessionParts(home, id), found, agentRow(found.path, found.run), readSteps(found.path, { sidechain: true })];
  } finally {
    Object.assign(fs, real);
    syncBuiltinESMExports();
  }
  assert.ok(!JSON.stringify(answers).includes('MARKER-'));
  const secretPaths = new Set(Object.values(secrets).map((p) => resolve(p)));
  assert.deepEqual(opened.filter((p) => secretPaths.has(resolve(p))), []);
  assert.deepEqual(opened.filter((p) => !ALLOWED.some((re) => re.test(p))), [], 'every file opened has an allowed name');
  assert.ok(opened.some((p) => p.endsWith('agent-w1.jsonl')), 'the watch saw the reads');
});

test('claude: a file with an allowed name that links elsewhere, or is over 1 MB, is never read (Aster, F1 and F6)', (t) => {
  const home = fakeHome(t);
  const id = uuid(1);
  transcript(home, id, [user('x')], MIN);
  const sub = join(folder(home, id), 'subagents');
  agent(sub, 'agent-real', MIN);
  mkdirSync(join(folder(home, id), 'workflows'));
  const history = put(cl(home, 'history.jsonl'), jsonl([user('MARKER-history'), { type: 'last-prompt', lastPrompt: 'MARKER-history' }]));
  const credentials = put(cl(home, '.credentials.json'),
    JSON.stringify(Object.fromEntries(['customTitle', 'description', 'agentType', 'workflowName', 'status'].map((k) => [k, 'MARKER-credentials']))));
  const linked = cl(home, 'projects', 'C--dev', `${uuid(2)}.jsonl`);
  try {
    fs.symlinkSync(history, linked);
    fs.symlinkSync(credentials, join(folder(home, id), 'custom-title.json'));
    fs.symlinkSync(history, join(sub, 'agent-linked.jsonl'));
    fs.symlinkSync(credentials, join(sub, 'agent-real.meta.json'));
    fs.symlinkSync(credentials, join(folder(home, id), 'workflows', 'wf_linked.json'));
  } catch (e) {
    if (e.code === 'EPERM') return t.skip('this machine cannot make links');
    throw e;
  }
  // A title file past 1 MB is never read; a long one in bounds is cut to 200 once masked.
  transcript(home, uuid(3), [user('x')], 2 * MIN);
  put(join(folder(home, uuid(3)), 'custom-title.json'), JSON.stringify({ customTitle: `MARKER-big ${' '.repeat(1 << 20)}` }));
  transcript(home, uuid(4), [user('x')], 3 * MIN);
  put(join(folder(home, uuid(4)), 'custom-title.json'), JSON.stringify({ customTitle: 'title '.repeat(100) }));
  const { sessions } = listClaude(home, { alive });
  assert.deepEqual(sessions.map((s) => s.id), [id, uuid(3), uuid(4)], 'the linked transcript is not listed');
  assert.deepEqual(sessions.map((s) => s.title.length), [id.length, uuid(3).length, 200]);
  const answers = JSON.stringify([sessions, findTranscript(home, uuid(2)), readSteps(linked), sessionParts(home, id), findAgent(home, id, 'agent-linked')]);
  assert.ok(!answers.includes('MARKER-'), 'nothing of history or credentials reaches an answer');
  assert.deepEqual([findTranscript(home, uuid(2)), readSteps(linked).readable, findAgent(home, id, 'agent-linked')], [null, false, null]);
});

test('claude: findTranscript takes only a uuid; findAgent only an agent id inside that session\'s folder', (t) => {
  const home = fakeHome(t);
  const id = 'abcdef01-2345-4678-9abc-def012345678'; // letters, so its uppercase spelling differs (and names the same file on Windows)
  const other = uuid(2);
  const path = transcript(home, id, [user('x')]);
  transcript(home, other, [user('y')]);
  put(cl(home, 'projects', 'x.jsonl'), jsonl([user('outside')])); // what '../x' would reach
  mkdirSync(cl(home, 'projects', 'C--dev', `${uuid(3)}.jsonl`)); // a folder where the file should be
  const mine = join(folder(home, id), 'subagents');
  agent(mine, 'agent-mine', 0);
  agent(join(mine, 'workflows', 'wf_r1'), 'agent-run1', 0);
  agent(join(folder(home, other), 'subagents'), 'agent-theirs', 0);
  assert.equal(findTranscript(home, id), path);
  for (const bad of ['../x', id.toUpperCase(), `${id}/..`, 'C--dev', uuid(3), '', undefined]) assert.equal(findTranscript(home, bad), null, String(bad));
  assert.deepEqual(findAgent(home, id, 'agent-mine'), { path: join(mine, 'agent-mine.jsonl'), run: null });
  assert.deepEqual(findAgent(home, id, 'agent-run1'), { path: join(mine, 'workflows', 'wf_r1', 'agent-run1.jsonl'), run: 'wf_r1' });
  for (const bad of ['agent-x/../agent-mine', 'agent-x\\..\\agent-mine', 'workflows/wf_r1/agent-run1', 'agent-theirs', 'agent-mine.jsonl', '../x']) {
    assert.equal(findAgent(home, id, bad), null, bad);
  }
  assert.equal(findAgent(home, '../x', 'agent-mine'), null);
});

// ---- The routes, on the real server with --home the fake home ----
const SERVER = fileURLToPath(new URL('../dashboard/server/server.mjs', import.meta.url));
// A small environment of its own for each child, never a copy of the whole one (LESSONS.md:460).
const KEEP_ENV = ['PATH', 'SYSTEMROOT', 'USERPROFILE', 'HOME', 'TEMP', 'TMP'];
const smallEnv = (extra) => ({ ...Object.fromEntries(KEEP_ENV.filter((k) => process.env[k]).map((k) => [k, process.env[k]])), ...extra });
const git = (cwd, ...args) => execFileSync('git', ['-c', 'user.name=t', '-c', 'user.email=t@example.invalid', '-c', 'commit.gpgsign=false', ...args],
  { cwd, env: smallEnv(), windowsHide: true, stdio: 'ignore' });
function tempDir(t, prefix) {
  const dir = mkdtempSync(join(tmpdir(), prefix));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  return dir;
}

function request(port, method, path, headers = {}) {
  return new Promise((done, fail) => {
    const req = http.request({ host: '127.0.0.1', port, method, path, headers: { Host: `127.0.0.1:${port}`, ...headers } }, (res) => {
      let text = '';
      res.setEncoding('utf8');
      res.on('data', (c) => { text += c; });
      res.on('end', () => done({ status: res.statusCode, text }));
    });
    req.on('error', fail);
    req.end();
  });
}

async function startServer(t, home, env = {}) {
  const root = tempDir(t, 'dash-claude-srv-');
  const child = spawn(process.execPath, [SERVER, '--port', '0', '--home', home, '--questions', join(root, 'questions.json'), '--dist', join(root, 'dist')], {
    env: smallEnv({ CODEX_CMD: JSON.stringify([join(root, 'no-codex.exe')]), ...env }), windowsHide: true,
  });
  t.after(() => child.kill());
  return new Promise((done, fail) => {
    let out = '';
    child.stdout.on('data', (c) => { out += c; const m = /http:\/\/127\.0\.0\.1:(\d+)/.exec(out); if (m) done(Number(m[1])); });
    child.on('exit', (code) => fail(new Error(`server exited ${code}: ${out}`)));
  });
}

const LIVE = uuid(1);
const IN_REPO = uuid(2);
const GONE = uuid(3);
const OTHER = uuid(4);
const OLD = uuid(5);
// A fake home for the routes: this test's own pid as the live session, with the
// planted secrets, a subagent and a run; ended sessions in a six-commit
// repository and in a folder that is gone; another session's agent; one 25 h old.
function routeHome(t) {
  const home = fakeHome(t);
  const noRepo = tempDir(t, 'dash-claude-norepo-');
  register(home, process.pid, { sessionId: LIVE, cwd: noRepo, status: 'busy', name: 'live work', entrypoint: 'cli' });
  secretTranscript(home, LIVE);
  fs.appendFileSync(cl(home, 'projects', 'C--dev', `${LIVE}.jsonl`), jsonl([assistant([{ type: 'text', text: 'done' }], { gitBranch: 'feature-x' })]));
  agent(join(folder(home, LIVE), 'subagents'), 'agent-s1', 0, { description: 'Explore code', agentType: 'Explore' });
  put(join(folder(home, LIVE), 'workflows', 'wf_r1.json'), JSON.stringify({ workflowName: 'Build', status: 'completed', summary: `used ${GHP}` }));
  agent(join(folder(home, LIVE), 'subagents', 'workflows', 'wf_r1'), 'agent-w1', 3 * MIN);
  const repo = tempDir(t, 'dash-claude-repo-');
  git(repo, 'init', '-q');
  for (const subject of ['c1', 'c2', 'c3', 'c4', 'c5', `c6 ${GHP}`]) git(repo, 'commit', '-q', '--allow-empty', '-m', subject);
  transcript(home, IN_REPO, [user('x', { cwd: repo, entrypoint: 'cli' })], MIN);
  transcript(home, GONE, [user('x', { cwd: join(noRepo, 'removed-worktree'), entrypoint: 'cli' })], 2 * MIN);
  transcript(home, OTHER, [user('x')], 3 * MIN);
  agent(join(folder(home, OTHER), 'subagents'), 'agent-theirs', 0);
  transcript(home, OLD, [user('x')], 25 * HOUR);
  return home;
}

test('claude route: GET /api/claude lists the live session, then the ended ones', async (t) => {
  const port = await startServer(t, routeHome(t));
  const res = await request(port, 'GET', '/api/claude');
  assert.equal(res.status, 200);
  const body = JSON.parse(res.text);
  assert.deepEqual(body.sessions.map((s) => [s.id, s.state, s.title]), [
    [LIVE, 'working', 'live work'], [IN_REPO, 'ended', IN_REPO], [GONE, 'ended', GONE], [OTHER, 'ended', OTHER]]);
  assert.ok(!Number.isNaN(Date.parse(body.at)));
});

test('claude route: a session\'s view holds its steps, branch, subagents and runs, and no planted secret', async (t) => {
  const port = await startServer(t, routeHome(t));
  const res = await request(port, 'GET', `/api/claude/sessions/${LIVE}`);
  assert.equal(res.status, 200);
  const view = JSON.parse(res.text);
  assert.deepEqual([view.id, view.title, view.state, view.source, view.branch, view.readable], [LIVE, 'live work', 'working', 'cli', 'feature-x', true]);
  assert.deepEqual(view.steps.map((s) => s.kind), ['prompt', 'reply', 'tool', 'tool', 'result', 'result', 'reply']);
  assert.deepEqual(view.agents.map((a) => [a.id, a.title, a.state]), [['agent-s1', 'Explore code', 'working']]);
  assert.deepEqual(view.runs.map((r) => [r.id, r.name, r.status, r.agents.map((a) => a.id)]), [['wf_r1', 'Build', 'completed', ['agent-w1']]]);
  for (const secret of [...SECRETS, GHP]) assert.ok(!res.text.includes(secret), secret);
  assert.deepEqual(bodyRuns(res.text), []);
  const sub = await request(port, 'GET', `/api/claude/sessions/${LIVE}/agents/agent-w1`);
  assert.equal(sub.status, 200);
  const agentView = JSON.parse(sub.text);
  assert.deepEqual([agentView.id, agentView.run, agentView.state, agentView.readable, agentView.steps.map((s) => s.text)], ['agent-w1', 'wf_r1', 'idle', true, ['task']]);
});

test('claude route: a live session whose transcript is not there yet answers unreadable, with no steps, agents or runs', async (t) => {
  const home = fakeHome(t);
  register(home, process.pid, { sessionId: LIVE, cwd: tempDir(t, 'dash-claude-norepo-'), status: 'idle', name: 'just started' });
  const port = await startServer(t, home);
  const res = await request(port, 'GET', `/api/claude/sessions/${LIVE}`);
  assert.equal(res.status, 200);
  const view = JSON.parse(res.text);
  assert.deepEqual([view.id, view.state, view.readable, view.steps, view.branch, view.agents, view.runs], [LIVE, 'idle', false, [], null, [], []]);
});

test('claude route: the last 5 commits in a repository; a folder that is no repository, or is gone, is null', async (t) => {
  const port = await startServer(t, routeHome(t));
  const inRepo = await request(port, 'GET', `/api/claude/sessions/${IN_REPO}`);
  assert.equal(inRepo.status, 200);
  const { commits } = JSON.parse(inRepo.text);
  assert.deepEqual(commits.map((c) => c.subject), ['c6 [masked]', 'c5', 'c4', 'c3', 'c2']);
  for (const c of commits) {
    assert.match(c.hash, /^[0-9a-f]{7,}$/);
    assert.ok(!Number.isNaN(Date.parse(c.at)), c.at);
  }
  assert.ok(!inRepo.text.includes(GHP));
  // OTHER's cwd is unknown (''): git never runs in the server's own folder instead.
  for (const id of [LIVE, GONE, OTHER]) {
    const res = await request(port, 'GET', `/api/claude/sessions/${id}`);
    assert.deepEqual([res.status, JSON.parse(res.text).commits], [200, null], id);
  }
});

test('claude route: with no git to start, a repository\'s commits are null, never an error answer', async (t) => {
  const home = fakeHome(t);
  const repo = tempDir(t, 'dash-claude-repo-');
  git(repo, 'init', '-q');
  git(repo, 'commit', '-q', '--allow-empty', '-m', 'c1');
  register(home, process.pid, { sessionId: LIVE, cwd: repo, status: 'busy', name: 'live work' });
  transcript(home, LIVE, [user('x')]);
  // The server's PATH holds no git, so git cannot start in a folder that is a repository.
  const port = await startServer(t, home, { PATH: tempDir(t, 'dash-claude-nogit-') });
  const res = await request(port, 'GET', `/api/claude/sessions/${LIVE}`);
  assert.deepEqual([res.status, JSON.parse(res.text).commits], [200, null]);
});

test('claude route: an ended session whose last line outgrows the listing\'s 64 KB tail still answers its folder, source and commits', async (t) => {
  const home = fakeHome(t);
  const repo = tempDir(t, 'dash-claude-repo-');
  git(repo, 'init', '-q');
  git(repo, 'commit', '-q', '--allow-empty', '-m', 'c1');
  // A Read result, its text kept twice as Claude keeps it: in the block and in toolUseResult.
  const big = 'z'.repeat(40_000);
  transcript(home, IN_REPO, [
    user('x', { cwd: repo, entrypoint: 'cli' }),
    user([{ type: 'tool_result', tool_use_id: 'tu1', content: big }], { cwd: repo, entrypoint: 'cli', toolUseResult: { file: { content: big } } }),
  ], MIN);
  const port = await startServer(t, home);
  const res = await request(port, 'GET', `/api/claude/sessions/${IN_REPO}`);
  assert.equal(res.status, 200);
  const view = JSON.parse(res.text);
  assert.deepEqual([view.cwd, view.source, view.commits?.map((c) => c.subject)], [repo, 'cli', ['c1']]);
});

test('claude route: a folder whose name the mask hides still gives its commits, and is shown masked (Aster, F11)', async (t) => {
  const home = fakeHome(t);
  const repo = join(tempDir(t, 'dash-claude-repo-'), 'a'.repeat(80));
  mkdirSync(repo);
  git(repo, 'init', '-q');
  git(repo, 'commit', '-q', '--allow-empty', '-m', 'c1');
  // A live session takes its folder from the registry, an ended one from its transcript.
  register(home, process.pid, { sessionId: LIVE, cwd: repo, status: 'busy', name: 'live work' });
  transcript(home, LIVE, [user('x')]);
  transcript(home, IN_REPO, [user('x', { cwd: repo, entrypoint: 'cli' })], MIN);
  const port = await startServer(t, home);
  for (const id of [LIVE, IN_REPO]) {
    const res = await request(port, 'GET', `/api/claude/sessions/${id}`);
    const view = JSON.parse(res.text);
    assert.deepEqual([res.status, view.cwd.includes('a'.repeat(80)), view.commits?.map((c) => c.subject)], [200, false, ['c1']], id);
  }
});

test('claude route: an id the listing does not hold, or an agent outside the session, is 404 not-found and names no path', async (t) => {
  const home = routeHome(t);
  const port = await startServer(t, home);
  const paths = [
    `/api/claude/sessions/${uuid(99)}`, `/api/claude/sessions/${OLD}`, '/api/claude/sessions/..%2F..%2F.credentials.json',
    '/api/claude/sessions/%2E%2E', '/api/claude/sessions/', '/api/claude/sessions/%E0%A4%A',
    `/api/claude/sessions/${LIVE}/agents/agent-nope`, `/api/claude/sessions/${LIVE}/agents/agent-theirs`,
    `/api/claude/sessions/${LIVE}/agents/..%2F..%2F${OTHER}%2Fsubagents%2Fagent-theirs`, `/api/claude/sessions/${LIVE}/agents/%E0%A4%A`,
    `/api/claude/sessions/${OTHER}/agents/agent-s1`,
  ];
  for (const path of paths) {
    const res = await request(port, 'GET', path);
    assert.deepEqual([res.status, JSON.parse(res.text).code], [404, 'not-found'], path);
    assert.ok(!res.text.includes(home) && !/[A-Za-z]:[\\/]|\.claude/.test(res.text), `${path} names a path: ${res.text}`);
  }
});

test('claude route: a foreign Host and a cross-site request are refused, and a POST is never a write', async (t) => {
  const port = await startServer(t, routeHome(t));
  for (const path of ['/api/claude', `/api/claude/sessions/${LIVE}`, `/api/claude/sessions/${LIVE}/agents/agent-s1`]) {
    const foreign = await request(port, 'GET', path, { Host: `attacker.example:${port}` });
    assert.deepEqual([foreign.status, JSON.parse(foreign.text).code], [403, 'forbidden'], path);
    const crossSite = await request(port, 'GET', path, { 'Sec-Fetch-Site': 'cross-site' });
    assert.deepEqual([crossSite.status, JSON.parse(crossSite.text).code], [403, 'forbidden'], path);
    const post = await request(port, 'POST', path, { Origin: `http://127.0.0.1:${port}`, 'Content-Type': 'application/json' });
    assert.deepEqual([post.status, JSON.parse(post.text).code], [404, 'not-found'], path);
  }
});
