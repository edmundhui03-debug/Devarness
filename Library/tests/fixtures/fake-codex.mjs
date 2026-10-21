// fake-codex.mjs: a fake `codex app-server` for the dashboard's tests, so no
// test starts the real Codex or spends its quota. One JSON-RPC message per line
// on stdin and stdout, as Codex's own. It writes no file but those its
// FAKE_CODEX_*_TO variables name: the dashboard server starts it in the dev root.
// Steered by the environment:
//   FAKE_CODEX_SIGNED_OUT=1  no account
//   FAKE_CODEX_BAD_LOGIN=1   a sign-in address that is http://, not https://
//   FAKE_CODEX_EXIT=1        it exits at once
//   FAKE_CODEX_TURN_MS       how long a turn runs before it completes, default 200
//   FAKE_CODEX_DEEP=1        a turn's item and an item/completed event nested 100,000 deep
//   FAKE_CODEX_ENV_TO=<file> it writes the CODEX_MANAGED_* variables it was given there
//   FAKE_CODEX_SILENT=a,b    it never answers these methods, as a wedged Codex would
//   FAKE_CODEX_STARTS_TO=<file> it adds a line there each time it starts
//   FAKE_CODEX_FILES=<n>     a turn's first item changes n files, each diff 3,893 characters
//   FAKE_CODEX_NEW_LAG=1     the first thread/read of a thread it has just started answers "no such thread"
//   FAKE_CODEX_READ_ERROR=1  every thread/read answers an error that is not "no such thread"
//   FAKE_CODEX_READS_TO=<file> it adds the thread id there on each thread/read
// and by `--sessions <folder>`: each thread's session file is <folder>/<id>.jsonl.
import { appendFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { createInterface } from 'node:readline';

if (process.env.FAKE_CODEX_EXIT === '1') process.exit(1);
if (process.env.FAKE_CODEX_ENV_TO) {
  writeFileSync(process.env.FAKE_CODEX_ENV_TO, JSON.stringify(Object.fromEntries(
    Object.entries(process.env).filter(([name]) => name.startsWith('CODEX_MANAGED_')))));
}
if (process.env.FAKE_CODEX_STARTS_TO) appendFileSync(process.env.FAKE_CODEX_STARTS_TO, 'start\n');
const SILENT = new Set(String(process.env.FAKE_CODEX_SILENT ?? '').split(',').filter(Boolean));
const at = process.argv.indexOf('--sessions');
const sessions = at === -1 ? null : process.argv[at + 1];
const TURN_MS = Number(process.env.FAKE_CODEX_TURN_MS) || 200;
const FILES = Number(process.env.FAKE_CODEX_FILES) || 0;
// A 40-letter key, as an `env` command would print it.
const KEY = `sk-proj-${'abcdefghij'.repeat(4)}`;
// JSON.parse reads this; a walk that calls itself per level cannot. Written in place of "<deep>".
const DEEP = process.env.FAKE_CODEX_DEEP === '1' ? '{"a":'.repeat(100_000) + '1' + '}'.repeat(100_000) : null;

const send = (msg) => process.stdout.write((DEEP ? JSON.stringify(msg).replace('"<deep>"', DEEP) : JSON.stringify(msg)) + '\n');
const note = (method, params) => send({ method, params });
const thread = (id, extra) => ({
  id, name: null, preview: `first prompt of ${id}`, source: 'cli', cwd: process.cwd(),
  createdAt: 1790000000, updatedAt: 1790000000, status: { type: 'notLoaded' },
  path: sessions && join(sessions, `${id}.jsonl`), turns: [], ...extra,
});
// One thread in the dev root, one in another folder, one Codex marks broken.
const threads = new Map([
  ['t-dev', thread('t-dev', { name: `Dev root work: rotate ${KEY}`, preview: `deploy with OPENAI_API_KEY=${KEY}`, updatedAt: 1790000300 })],
  ['t-other', thread('t-other', { cwd: resolve(process.cwd(), '..', 'elsewhere-project'), updatedAt: 1790000200 })],
  ['t-error', thread('t-error', { status: { type: 'systemError' }, updatedAt: 1790000100 })],
]);
const turns = [
  { id: 'turn-1', status: 'completed', items: [
    { type: 'userMessage', id: 'u1', content: [{ type: 'text', text: 'print the environment' }] },
    { type: 'commandExecution', id: 'c1', command: 'env', status: 'completed', exitCode: 0, aggregatedOutput: `LANG=en_GB.UTF-8\nOPENAI_API_KEY=${KEY}\n` },
    { type: 'agentMessage', id: 'a1', text: 'The key is set.' },
  ] },
  { id: 'turn-2', status: 'completed', items: [
    { type: 'commandExecution', id: 'c2', command: 'npm test', status: 'completed', exitCode: 0, aggregatedOutput: 'a line of test output\n'.repeat(500) },
    // The key straddles the 4,000-character cut, which takes command output from its start:
    // masked first, nothing of it is left.
    { type: 'commandExecution', id: 'c3', command: 'cat .env', status: 'completed', exitCode: 0, aggregatedOutput: `${KEY} ${'.'.repeat(3980)}` },
    { type: 'agentMessage', id: 'a2', text: 'a long answer\n'.repeat(400) },
  ] },
  ...(DEEP ? [{ id: 'turn-deep', status: 'completed', items: ['<deep>'] }] : []),
];

let n = 0;
const running = new Map(); // turn id -> the timer that completes it
const LATER = Symbol('later'); // a handler that replies by itself
const finish = (threadId, turnId, status) => {
  clearTimeout(running.get(turnId));
  running.delete(turnId);
  note('turn/completed', { threadId, turn: { id: turnId, status, items: [] } });
};
// Codex's words for a thread it does not have, and for an id that cannot be one (plan P2).
const NO_THREAD = (threadId) => ({ code: -32602, message: `thread not loaded: ${threadId}` });
const lagging = new Set(); // threads started here whose first read has not come yet
const known = (threadId) => {
  if (!/^[\w-]+$/.test(threadId)) throw { code: -32602, message: 'invalid thread id: invalid character' };
  if (!threads.has(threadId)) throw NO_THREAD(threadId);
  return threads.get(threadId);
};
const handlers = {
  initialize: () => ({ userAgent: 'codex_cli_rs/0.162.0 (Windows 11; x86_64) dev-dashboard-bridge' }),
  'account/read': () => ({ account: process.env.FAKE_CODEX_SIGNED_OUT === '1' ? null : { type: 'chatgpt', email: 'owner@example.com', planType: 'plus' } }),
  'account/rateLimits/read': () => ({ rateLimits: {
    primary: { usedPercent: 25, windowDurationMins: 300, resetsAt: 1900000000 },
    secondary: { usedPercent: 10, windowDurationMins: 10080, resetsAt: 1900500000 },
  } }),
  'account/login/start': () => ({ type: 'chatgpt', loginId: 'login-1',
    authUrl: `${process.env.FAKE_CODEX_BAD_LOGIN === '1' ? 'http' : 'https'}://auth.openai.com/oauth/authorize?fake=1` }),
  'thread/list': () => ({ data: [...threads.values()].map(({ turns: _, ...t }) => t) }),
  'thread/read': ({ threadId, includeTurns }) => {
    if (process.env.FAKE_CODEX_READS_TO) appendFileSync(process.env.FAKE_CODEX_READS_TO, `${threadId}\n`);
    if (process.env.FAKE_CODEX_READ_ERROR === '1') throw { code: -32603, message: 'internal error: the rollout cannot be read' };
    if (lagging.delete(threadId)) throw NO_THREAD(threadId);
    return { thread: { ...known(threadId), turns: includeTurns ? turns : [] } };
  },
  'thread/start': ({ cwd }) => {
    const t = thread(`t-new-${++n}`, { cwd, status: { type: 'idle' } });
    threads.set(t.id, t);
    if (process.env.FAKE_CODEX_NEW_LAG === '1') lagging.add(t.id);
    note('thread/started', { thread: t });
    return { thread: t };
  },
  'thread/resume': ({ threadId }) => ({ thread: known(threadId) }),
  'turn/start': ({ threadId }, id) => {
    const turnId = `turn-${++n}`;
    send({ id, result: { turn: { id: turnId, status: 'inProgress', items: [] } } });
    note('turn/started', { threadId, turn: { id: turnId, status: 'inProgress', items: [] } });
    if (FILES) {
      note('item/completed', { threadId, turnId, item: { type: 'fileChange', id: `f${n}`, status: 'completed',
        changes: Array.from({ length: FILES }, (_, i) => ({ path: `src/file${i}.mjs`, kind: 'update', diff: '+ a changed line\n'.repeat(229) })) } });
    }
    note('item/completed', { threadId, turnId, item: { type: 'agentMessage', id: `m${n}`, text: 'Called the API with Authorization: Bearer abcdefghijkl' } });
    if (DEEP) note('item/completed', { threadId, turnId, item: '<deep>' });
    running.set(turnId, setTimeout(() => finish(threadId, turnId, 'completed'), TURN_MS));
    return LATER;
  },
  'turn/interrupt': ({ threadId, turnId }) => {
    if (running.has(turnId)) setTimeout(() => finish(threadId, turnId, 'interrupted'), 20);
    return {};
  },
};

createInterface({ input: process.stdin }).on('line', (line) => {
  const msg = JSON.parse(line);
  if (msg.method === undefined || msg.id === undefined) return; // a reply or a notification
  if (SILENT.has(msg.method)) return;
  try {
    const handler = handlers[msg.method];
    if (!handler) throw { code: -32601, message: `unknown method ${msg.method}` };
    const result = handler(msg.params ?? {}, msg.id);
    if (result !== LATER) send({ id: msg.id, result });
  } catch (err) {
    send({ id: msg.id, error: { code: err.code ?? -32603, message: err.message ?? String(err) } });
  }
});
