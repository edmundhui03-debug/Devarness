// codex.mjs: Codex's app-server, shared by codex-bridge.mjs and the dashboard
// server. One `codex app-server` per factory, started on first use and ended
// by end(). Node built-ins only. Design: Library/dashboard/DESIGN.md.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, statSync } from 'node:fs';
import { join, resolve, win32 } from 'node:path';
import { createInterface } from 'node:readline';
import { lastTurnOpen } from './markers.mjs';

const SANDBOXES = ['read-only', 'workspace-write'];
// Codex leaves `codex exec` runs out of its thread list unless asked for every kind.
const SOURCE_KINDS = ['cli', 'vscode', 'exec', 'appServer', 'subAgent', 'subAgentReview',
  'subAgentCompact', 'subAgentThreadSpawn', 'subAgentOther', 'unknown'];
// ponytail: a thread run by another program counts as active while its session
// file changed in the last two minutes; Codex says nothing about other processes.
const ACTIVE_MS = 120_000;
// ponytail: an open turn marker counts only while its file changed in the last
// 30 minutes, since a window killed mid-turn leaves it open for good; a turn
// silent for longer shows idle.
const OPEN_MS = 30 * 60_000;
const TURNS_SHOWN = 20;
const LONG_TEXT = 4000;
const PREVIEW = 200;
// The tests shorten it; nothing else sets it.
const CALL_TIMEOUT_MS = Number(process.env.CODEX_BRIDGE_TIMEOUT_MS) || 30_000;
// Codex's words for a thread it does not have, or an id that cannot be one,
// as read on the real Codex on 2026-10-14 (plan P2).
const NO_THREAD = /^Codex: (thread not loaded|invalid thread id): /;
const FRESH_MS = 30_000; // a thread this server started so recently may not be readable yet
const RETRY_MS = 750;

export const isObj = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
export const httpError = (status, message) => Object.assign(new Error(message), { status });

// A thread's session-file path stays on this computer: no field of the page needs it.
function withoutPath(params) {
  if (!isObj(params) || !isObj(params.thread)) return params;
  const { path, ...thread } = params.thread;
  return { ...params, thread };
}

const WINDOWS_TARGETS = {
  x64: ['@openai/codex-win32-x64', 'x86_64-pc-windows-msvc'],
  arm64: ['@openai/codex-win32-arm64', 'aarch64-pc-windows-msvc'],
};

// npm puts a codex.cmd shim on PATH, which Node cannot spawn without a shell;
// this finds the codex.exe the shim's codex.js would start, the same way, and
// the environment it would start it with. { command, env }; env undefined inherits.
export function findCodex({ env = process.env, platform = process.platform, arch = process.arch, exists = existsSync } = {}) {
  const target = platform === 'win32' ? WINDOWS_TARGETS[arch] : null;
  if (!target) return { command: ['codex'] };
  const [pkg, triple] = target;
  // A relative entry would be looked up from the app-server's own folder, so it is skipped,
  // and an .exe found is named whole: a bare name is looked for in that folder first.
  for (const dir of String(env.PATH ?? env.Path ?? '').split(';').filter((d) => win32.isAbsolute(d))) {
    if (exists(win32.join(dir, 'codex.exe'))) return { command: [win32.join(dir, 'codex.exe')] };
    if (!exists(win32.join(dir, 'codex.cmd'))) continue;
    const codexPkg = win32.join(dir, 'node_modules', '@openai', 'codex');
    for (const vendor of [win32.join(codexPkg, 'node_modules', pkg, 'vendor'), win32.join(dir, 'node_modules', pkg, 'vendor'), win32.join(codexPkg, 'vendor')]) {
      const exe = win32.join(vendor, triple, 'bin', 'codex.exe');
      if (!exists(exe)) continue;
      // As the npm package's bin/codex.js sets them for an npm install (its lines 231-239).
      const launched = { ...env, CODEX_MANAGED_PACKAGE_ROOT: codexPkg, CODEX_MANAGED_BY_NPM: '1' };
      for (const name of ['CODEX_MANAGED_BY_BUN', 'CODEX_MANAGED_BY_PNPM', 'CODEX_MANAGED_BY_VITE_PLUS']) delete launched[name];
      return { command: [exe], env: launched };
    }
    return { command: ['codex'] };
  }
  return { command: ['codex'] };
}

// `mask` is applied to what Codex says before long text is cut, so a cut never
// leaves part of a secret: the server masks; the prototype bridge shows it as it is.
export function createCodex({ folder, command = ['codex'], env, onEvent = () => {}, mask = (value) => value }) {
  // --- the app-server: one JSON-RPC message per line on its stdin and stdout ---------

  let app = null;      // { child, pending, ready, userAgent }: the one running app-server
  let nextId = 1;
  const loadedHere = new Set(); // threads this app-server has started or resumed
  // thread id -> { turn }: one record per prompt this factory started, its turn id
  // null until Codex names it. Each prompt has its own record, so a late reply
  // for an older prompt never touches a newer one.
  const runs = new Map();
  const lastHere = new Map();   // thread id -> when this factory last saw its own turn there

  function appServer() {
    if (app) return app.ready;
    const conn = { child: null, pending: new Map(), userAgent: null };
    app = conn;
    conn.ready = new Promise((ready, fail) => {
      const lost = (err) => {
        const error = Object.assign(httpError(502, `Codex app-server: ${err.message}`), { code: 'codex-not-started' });
        for (const waiter of conn.pending.values()) waiter.fail(error);
        conn.pending.clear();
        if (app !== conn) return;
        app = null;
        loadedHere.clear();
        runs.clear();
        onEvent({ method: 'bridge/appServer', params: { up: false, error: error.message } });
        fail(error);
      };
      try {
        conn.child = spawn(command[0], [...command.slice(1), 'app-server'], {
          cwd: folder, env, windowsHide: true, shell: false, detached: process.platform !== 'win32',
        });
      } catch (err) {
        return lost(err);
      }
      conn.child.on('error', lost);
      conn.child.on('close', (code) => lost(new Error(`ended with code ${code}`)));
      conn.child.stdin.on('error', () => {}); // a closing app-server may refuse a last write
      createInterface({ input: conn.child.stdout, crlfDelay: Infinity }).on('line', (line) => onMessage(conn, line));
      conn.child.stderr.resume(); // drained, or a chatty app-server would block
      call(conn, 'initialize', { clientInfo: { name: 'dev-dashboard-bridge', title: 'Zack dev. dashboard', version: '2.0.0' } })
        .then((init) => {
          write(conn, { method: 'initialized' });
          conn.userAgent = isObj(init) ? init.userAgent ?? null : null;
          onEvent({ method: 'bridge/appServer', params: { up: true } });
          ready(conn);
        }, lost);
    });
    conn.ready.catch(() => endApp(conn));
    return conn.ready;
  }

  function write(conn, message) {
    conn.child.stdin.write(JSON.stringify(message) + '\n');
  }

  function call(conn, method, params) {
    return new Promise((done, fail) => {
      const id = nextId++;
      const timer = setTimeout(() => {
        conn.pending.delete(id);
        fail(httpError(504, `Codex did not answer ${method} within ${CALL_TIMEOUT_MS / 1000} s`));
        // Two calls in a row with no answer: the app-server is wedged. Ending it
        // fails what waits and frees its runs; the next call starts a new one.
        conn.silent = (conn.silent ?? 0) + 1;
        if (conn.silent === 2) endApp(conn);
      }, CALL_TIMEOUT_MS);
      conn.pending.set(id, {
        done: (result) => { clearTimeout(timer); done(result); },
        fail: (err) => { clearTimeout(timer); fail(err); },
      });
      write(conn, params === undefined ? { id, method } : { id, method, params });
    });
  }

  const rpc = (method, params) => appServer().then((conn) => call(conn, method, params));

  function onMessage(conn, line) {
    let msg;
    try { msg = JSON.parse(line); } catch { return; }
    if (!isObj(msg)) return;
    if (msg.method !== undefined && msg.id !== undefined) {
      // Codex asks something (an approval, user input): with approvals off the
      // bridge has no one to ask, so it declines rather than leave Codex waiting.
      write(conn, { id: msg.id, error: { code: -32601, message: 'The dev dashboard bridge answers no requests; approvals are off.' } });
      onEvent({ method: 'bridge/declined', params: { request: msg.method, threadId: msg.params?.threadId ?? null } });
      return;
    }
    if (msg.method !== undefined) {
      const params = isObj(msg.params) ? msg.params : {};
      const run = runs.get(params.threadId);
      const turnId = isObj(params.turn) ? params.turn.id : undefined;
      // A started turn names the prompt still waiting for its reply; a finished
      // one frees its thread, even when its reply has not come yet.
      if (run && msg.method === 'turn/started' && run.turn === null) run.turn = turnId;
      if (run && msg.method === 'turn/completed' && (run.turn === null || run.turn === turnId)) {
        runs.delete(params.threadId);
        lastHere.set(params.threadId, Date.now());
        console.log(`turn ${turnId ?? '?'}: ended, ${params.turn?.status ?? '?'}`);
      }
      // Token-by-token deltas stay here: the page shows each item once it completes.
      if ((/^(thread|turn|item|account)\//.test(msg.method) || msg.method === 'error') && !/delta$/i.test(msg.method)) {
        let shown = null; // a value nested too deep to walk throws here; its event goes out blank
        try { shown = clip(mask(withoutPath(msg.params ?? null))); } catch { /* blank */ }
        onEvent({ method: msg.method, params: shown });
      }
      return;
    }
    const waiter = conn.pending.get(msg.id);
    if (!waiter) return;
    conn.pending.delete(msg.id);
    conn.silent = 0; // it answers
    if (msg.error !== undefined) {
      const message = isObj(msg.error) && typeof msg.error.message === 'string' ? msg.error.message : 'error';
      waiter.fail(Object.assign(httpError(502, `Codex: ${message}`), { rpc: true }));
    } else {
      waiter.done(msg.result);
    }
  }

  // Ends the app-server and its tree on a normal exit or a signal. A process that
  // is killed outright runs no handler: on Windows its children still die with it
  // (libuv's kill-on-close job, so they are never detached there); elsewhere they
  // are left to the process group.
  function endApp(conn = app) {
    const child = conn?.child;
    if (!child?.pid || child.exitCode !== null || child.signalCode !== null) return;
    if (process.platform === 'win32') {
      const taskkill = join(process.env.SystemRoot ?? 'C:\\Windows', 'System32', 'taskkill.exe');
      // A taskkill that hangs would hold this exit; past 5 s it is cut off and the child is ended directly.
      const done = spawnSync(taskkill, ['/T', '/F', '/PID', String(child.pid)], { windowsHide: true, stdio: 'ignore', timeout: 5000 });
      if (done.status !== 0) {
        console.error(`taskkill could not end the Codex app-server (pid ${child.pid}); ending it directly.`);
        child.kill();
      }
    } else {
      try { process.kill(-child.pid, 'SIGKILL'); } catch { /* the group is gone */ }
    }
  }

  async function health() {
    try {
      const conn = await appServer();
      return { up: true, userAgent: conn.userAgent };
    } catch (err) {
      return { up: false, error: err.message };
    }
  }

  // --- what the page sees of a thread ---------------------------------------------

  function cut(text, size) {
    return text.length > size ? text.slice(0, size - 1) + '…' : text;
  }

  // Long command output and file text are cut, so a thread reads at a glance.
  function clip(value, key) {
    if (typeof value === 'string') {
      // Command output keeps its end, where a test or build summary sits (contract A3).
      if (key === 'aggregatedOutput' && value.length > LONG_TEXT) return '…' + value.slice(-(LONG_TEXT - 1));
      return cut(value, LONG_TEXT);
    }
    if (Array.isArray(value)) return value.map((v) => clip(v));
    if (!isObj(value)) return value;
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, clip(v, k)]));
  }

  // This app-server sees only its own turns. A session file whose last turn is
  // open, and that changed lately and after this factory's own last turn there,
  // means another Codex window is at work on it. A file with no marker falls back
  // to a guess from recency; neither is a lock.
  function stateOf(thread) {
    const status = isObj(thread.status) ? thread.status.type : null;
    if (status === 'active') return 'running';
    if (status === 'systemError') return 'error';
    if (typeof thread.path === 'string') {
      let changed = 0; // a file that cannot be measured counts as unchanged, so one cannot fail the list
      try { changed = statSync(thread.path, { throwIfNoEntry: false })?.mtimeMs ?? 0; } catch { /* unchanged */ }
      const mine = lastHere.get(thread.id) ?? 0;
      const age = Date.now() - changed;
      if (changed > mine + 1000 && age < OPEN_MS && (lastTurnOpen(thread.path) ?? age < ACTIVE_MS)) return 'active-elsewhere';
    }
    return 'idle';
  }

  function summary(thread) {
    return {
      id: thread.id,
      name: mask(thread.name ?? null),
      preview: cut(mask(String(thread.preview ?? '')), PREVIEW),
      // A sub-agent's source is an object naming its parent; its kind is enough here.
      source: isObj(thread.source) ? Object.keys(thread.source)[0] ?? null : thread.source ?? null,
      nickname: thread.agentNickname ?? null,
      cwd: thread.cwd ?? null,
      inDev: sameFolder(thread.cwd, folder),
      createdAt: thread.createdAt ?? null,
      updatedAt: thread.updatedAt ?? null,
      state: stateOf(thread),
      // The turn this factory started there and has not seen complete, so Stop survives a reload.
      turn: runs.get(thread.id)?.turn ?? null,
    };
  }

  // The page's view of one thread from readThread: its summary and its last
  // turns, long text cut.
  function threadView(thread) {
    const turnsShown = Array.isArray(thread.turns) ? thread.turns.slice(-TURNS_SHOWN) : [];
    return { ...summary(thread), turns: clip(mask(turnsShown)) };
  }

  // ponytail: the 50 most recently updated threads; a running one is always among them.
  async function listThreads() {
    const reply = await rpc('thread/list', { limit: 50, sortKey: 'updated_at', sortDirection: 'desc', sourceKinds: SOURCE_KINDS });
    const busy = (t) => (t.state === 'running' || t.state === 'active-elsewhere' ? 0 : 1);
    return (Array.isArray(reply?.data) ? reply.data : []).filter(isObj).map(summary)
      .sort((a, b) => busy(a) - busy(b) || (b.updatedAt ?? 0) - (a.updatedAt ?? 0));
  }

  async function readThread(id, includeTurns) {
    const read = async () => {
      const reply = await rpc('thread/read', { threadId: id, includeTurns });
      if (!isObj(reply?.thread)) throw httpError(502, 'Codex sent no thread');
      return reply.thread;
    };
    try {
      try {
        return await read();
      } catch (err) {
        // Codex cannot serve a thread for a moment after starting it (wave 2, check 7): one more try.
        if (!err.rpc || Date.now() - (lastHere.get(id) ?? 0) > FRESH_MS) throw err;
        await new Promise((done) => setTimeout(done, RETRY_MS));
        return await read();
      }
    } catch (err) {
      // Only Codex's "no such thread" is a 404; any other error it answers stays a 502 (Aster's #8).
      throw err.rpc && NO_THREAD.test(err.message) ? httpError(404, err.message) : err;
    }
  }

  const sameFolder = (a, b) => {
    const norm = (p) => (process.platform === 'win32' ? resolve(p).toLowerCase() : resolve(p));
    return typeof a === 'string' && norm(a) === norm(b);
  };

  // --- runs -----------------------------------------------------------------------

  async function startRun({ prompt, sandbox, thread = null }) {
    if (typeof prompt !== 'string' || !prompt.trim()) throw httpError(400, 'prompt must be a non-empty string');
    if (!SANDBOXES.includes(sandbox)) throw httpError(400, `sandbox must be ${SANDBOXES.join(' or ')}`);
    if (thread !== null && (typeof thread !== 'string' || !thread)) throw httpError(400, 'thread must be a thread id or null');
    if (thread !== null && runs.has(thread)) throw httpError(409, 'this thread is already running a prompt');
    let threadId = thread;
    let sent = false; // turn/start went to Codex
    const run = { turn: null };
    if (thread !== null) runs.set(thread, run); // held from here, so two prompts cannot race
    try {
      if (thread === null) {
        const reply = await rpc('thread/start', { cwd: folder, sandbox, approvalPolicy: 'never' });
        threadId = reply?.thread?.id;
        if (typeof threadId !== 'string') throw httpError(502, 'Codex started no thread');
        runs.set(threadId, run);
        loadedHere.add(threadId);
      } else {
        const existing = await readThread(thread, false);
        const state = stateOf(existing);
        if (state === 'running' || state === 'active-elsewhere') throw httpError(409, 'this thread is running in another Codex window');
        // Writing is offered in the bridge's own folder only, as it always was.
        if (sandbox !== 'read-only' && !sameFolder(existing.cwd, folder)) {
          throw httpError(403, `this thread works in ${existing.cwd}; the bridge lets Codex write only in ${folder}`);
        }
        if (!loadedHere.has(thread)) {
          await rpc('thread/resume', { threadId: thread, sandbox, approvalPolicy: 'never' });
          loadedHere.add(thread);
        }
      }
      lastHere.set(threadId, Date.now());
      sent = true;
      const reply = await rpc('turn/start', {
        threadId,
        input: [{ type: 'text', text: prompt }],
        approvalPolicy: 'never',
        // Codex's defaults would also let the turn write to the temporary folders and the network.
        sandboxPolicy: sandbox === 'read-only' ? { type: 'readOnly' }
          : { type: 'workspaceWrite', writableRoots: [], networkAccess: false, excludeSlashTmp: true, excludeTmpdirEnvVar: true },
      });
      const turnId = reply?.turn?.id;
      if (typeof turnId !== 'string') throw httpError(502, 'Codex started no turn');
      if (run.turn === null) run.turn = turnId;
      console.log(`turn ${turnId}: started in thread ${threadId}, ${sandbox}`);
      return { thread: threadId, turn: turnId };
    } catch (err) {
      // Without an answer to turn/start the turn may be running: the thread stays
      // held until Codex reports it, and Stop can end it by the id it reports.
      // A timeout before turn/start was sent started nothing, so it frees the thread.
      if (runs.get(threadId) === run && !(sent && err.status === 504)) runs.delete(threadId);
      throw err;
    }
  }

  async function stopRun(body) {
    const { thread, turn } = body;
    if (typeof thread !== 'string' || !thread || typeof turn !== 'string' || !turn) throw httpError(400, 'thread and turn must be ids');
    if (runs.get(thread)?.turn !== turn) {
      throw Object.assign(httpError(404, 'unknown turn: the bridge stops only turns it started'), { code: 'unknown-turn' });
    }
    await rpc('turn/interrupt', { threadId: thread, turnId: turn });
  }

  async function account() {
    const [read, limits] = await Promise.all([
      rpc('account/read', {}),
      rpc('account/rateLimits/read', undefined).catch(() => null),
    ]);
    const acct = isObj(read?.account) ? read.account : null;
    const windows = isObj(limits?.rateLimits) ? limits.rateLimits : null;
    // The email stays in Codex: the page needs only whether, how and how much.
    return {
      signedIn: acct !== null,
      type: acct?.type ?? null,
      plan: acct?.planType ?? null,
      rateLimits: windows ? { primary: windows.primary ?? null, secondary: windows.secondary ?? null } : null,
    };
  }

  // One account/read and nothing else, so a slow quota read cannot make Codex look offline.
  async function signedIn() {
    const read = await rpc('account/read', {});
    return isObj(read?.account);
  }

  async function login() {
    const reply = await rpc('account/login/start', { type: 'chatgpt' });
    return { authUrl: reply?.authUrl ?? null, loginId: reply?.loginId ?? null };
  }

  return { health, account, signedIn, login, listThreads, readThread, threadView, startRun, stopRun, end: () => endApp() };
}
