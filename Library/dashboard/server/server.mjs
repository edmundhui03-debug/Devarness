#!/usr/bin/env node
// server.mjs: the dev dashboard's one local server. It serves the built app
// from app/dist and a small JSON API: the agents' state, the questions
// mailbox and answers to it, Codex's threads, runs and live events, masked,
// whether the taskboard runs, the Tasks page's section index, running ledger
// rows and a document's last commits, and Claude's sessions with a session's
// or subagent's last steps, masked, read-only. It listens on 127.0.0.1 only,
// answers only its own Host (a site that rebinds its name to this computer is refused),
// takes writes only from its own page or one named by --allow-origin, and
// refuses the API to a request a browser marks as cross-site.
// Start it by hand with `dashboard serve`; nothing starts it at sign-in.
// Node built-ins only. Design: Setup/superpowers/specs/2026-10-09-dev-dashboard-design.md.
import { readFileSync, realpathSync, statSync } from 'node:fs';
import { createServer, get } from 'node:http';
import { homedir } from 'node:os';
import { dirname, extname, isAbsolute, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { agents, claudeSessions, sharedSnapshot } from './agents.mjs';
import { agentRow, findAgent, findTranscript, listClaude, readSteps, sessionParts } from './claude.mjs';
import { createCodex, findCodex, httpError, isObj } from './codex.mjs';
import { mask } from './mask.mjs';
import { answerQuestion, readQuestions } from './questions.mjs';
import { lastCommits, readTasks, run } from './tasks.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const HOST = '127.0.0.1';
const MAX_BODY = 64 * 1024;
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.json': 'application/json; charset=utf-8' };
const CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
  + "frame-src http://127.0.0.1:47823; frame-ancestors 'none'; base-uri 'none'; form-action 'none'";
// The tests move the taskboard's port; nothing else sets it.
const TASKBOARD = `http://${HOST}:${Number(process.env.DEVARNESS_TASKBOARD_PORT) || 47823}`;
// The page words a Codex route's error by its code. The module's own message can
// quote a folder (codex.mjs, startRun), so the answer says a fixed sentence instead.
const CODEX_ERRORS = {
  'bad-request': 'a field is missing or wrong',
  'write-outside-dev': 'Codex may write only in a thread whose folder is the dev root',
  'not-found': 'no such thread',
  'unknown-turn': 'this server did not start that turn',
  'thread-busy': 'the thread is running here or in another Codex window',
  'codex-not-started': 'Codex did not start',
  'codex-error': 'Codex answered with an error',
  'bad-sign-in': 'Codex gave a sign-in address that is not https',
  'codex-timeout': 'Codex did not answer in time',
};
const CODE_OF = { 400: 'bad-request', 403: 'write-outside-dev', 404: 'not-found', 409: 'thread-busy', 413: 'bad-request', 415: 'bad-request', 502: 'codex-error', 504: 'codex-timeout' };
// Every other error answer carries one of four codes, so the page can word it too.
const sharedCode = (status) => ({ 403: 'forbidden', 404: 'not-found' })[status] ?? (status < 500 ? 'bad-request' : 'internal');

function refuse(message) {
  console.error(message);
  process.exit(2);
}

let opts;
try {
  opts = parseArgs({ options: {
    port: { type: 'string', default: '47900' },
    host: { type: 'string', default: HOST },
    'allow-origin': { type: 'string', multiple: true, default: [] },
    home: { type: 'string', default: homedir() },
    questions: { type: 'string', default: resolve(HERE, '..', 'questions.json') },
    dist: { type: 'string', default: resolve(HERE, '..', 'app', 'dist') },
    root: { type: 'string', default: resolve(HERE, '..', '..', '..') }, // the dev root the Tasks page reads; tests name another
  } }).values;
} catch (err) { refuse(err.message); }
if (opts.host !== HOST) refuse(`The dashboard listens on ${HOST} only; --host ${opts.host} is refused.`);
const port = /^\d+$/.test(opts.port) ? Number(opts.port) : NaN;
if (!(port <= 65535)) refuse(`Not a port: ${opts.port}`);
for (const origin of opts['allow-origin']) {
  let url = null;
  try { url = new URL(origin); } catch { /* refused below */ }
  if (url?.protocol !== 'http:' || url.hostname !== HOST || !url.port || url.origin !== origin) refuse(`--allow-origin takes a page on this computer only; ${origin} is refused.`);
}
const allowed = new Set(opts['allow-origin']);
const dist = resolve(opts.dist);
const assets = resolve(dist, 'assets') + sep;
// Resolved once, so an fs error quotes exactly this string and plain() can cut it.
const questionsFile = resolve(opts.questions);
const plain = (message) => message.replaceAll(questionsFile, 'questions.json');
let { command, env } = findCodex();
if (process.env.CODEX_CMD) {
  env = undefined; // a command named by hand starts with this server's own environment
  try { command = JSON.parse(process.env.CODEX_CMD); } catch { command = null; }
  if (!Array.isArray(command) || !command.length || !command.every((p) => typeof p === 'string' && p)) refuse('CODEX_CMD must be a JSON array of strings.');
}
const streams = new Set(); // open /api/codex/events answers
// A page that stops reading (a frozen tab) would hold every later event in memory:
// once a megabyte waits for it, it is dropped, and its EventSource reconnects and reloads.
// write() returning false is no sign: one event past the 16 KB buffer does it to a page that reads.
const toStreams = (text) => { for (const res of streams) if (res.writableLength > 1 << 20) res.destroy(); else res.write(text); };
setInterval(() => toStreams(': ping\n\n'), 25_000).unref();
const codex = createCodex({
  folder: resolve(HERE, '..', '..', '..'), command, env, mask,
  // The app-server's own error can quote the command's path; the page needs only up or down.
  onEvent: (e) => toStreams(`data: ${JSON.stringify(e.method === 'bridge/appServer' ? { method: e.method, params: { up: e.params.up } } : e)}\n\n`),
});
// Every tab's poll shares one reading, so polls never queue Codex calls.
const agentsNow = sharedSnapshot(async () => ({
  agents: await agents({ home: opts.home, codex, questions: questionsOrNone() }), at: new Date().toISOString(),
}));
const root = resolve(opts.root);
// Every tab's poll shares one reading of the index and the ledger, as with the agents.
const tasksNow = sharedSnapshot(() => readTasks(root));
// And one listing of Claude's sessions; a session route answers only for an id it holds.
const claudeNow = sharedSnapshot(async () => ({ ...listClaude(opts.home), at: new Date().toISOString() }));

function send(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
  res.end(JSON.stringify(body));
}

function readJson(req, res) {
  if (!/^application\/json\s*(;|$)/i.test(req.headers['content-type'] ?? '')) throw httpError(415, 'send JSON');
  return new Promise((done, fail) => {
    const chunks = [];
    let size = 0;
    req.on('data', (c) => {
      if (size > MAX_BODY) return; // already refused
      size += c.length;
      if (size <= MAX_BODY) return chunks.push(c);
      // Refused at the limit, not after the rest arrives; the connection drops once the 413 is sent.
      res.setHeader('Connection', 'close');
      res.once('finish', () => req.destroy());
      fail(httpError(413, 'the body is over 64 KB'));
    });
    req.on('error', fail);
    req.on('end', () => {
      if (size > MAX_BODY) return;
      try {
        const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
        if (!isObj(body)) throw new Error();
        done(body);
      } catch { fail(httpError(400, 'the body must be a JSON object')); }
    });
  });
}

function questionsOrNone() {
  try { return readQuestions(questionsFile).questions; } catch { return []; }
}

// Never fails for a Codex reason: a Codex that is down, or cannot say who is
// signed in, is reported as not started.
async function codexStatus() {
  const health = await codex.health();
  const version = /\/(\d+\.\d+\.\d+)/.exec(health.userAgent ?? '')?.[1] ?? null;
  const down = { up: false, version, signedIn: false, type: null, plan: null, rateLimits: null, code: 'codex-not-started' };
  if (!health.up) return down;
  try {
    const account = await codex.account();
    return { up: true, version, ...account, code: account.signedIn ? 'ok' : 'codex-signed-out' };
  } catch { return down; }
}

function codexError(err) {
  if (!err.status) throw err; // unexpected: answered "internal error"
  const code = err.code ?? CODE_OF[err.status] ?? 'codex-error';
  throw Object.assign(httpError(err.status, CODEX_ERRORS[code]), { code });
}

function openStream(res) {
  res.writeHead(200, { 'Content-Type': 'text/event-stream; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
  res.flushHeaders();
  streams.add(res);
  res.on('close', () => streams.delete(res));
}

async function codexApi(req, res, url) {
  const route = `${req.method} ${url.pathname}`;
  if (route === 'GET /api/codex') return send(res, 200, await codexStatus());
  if (route === 'GET /api/codex/threads') return send(res, 200, { threads: await codex.listThreads() });
  if (route === 'GET /api/codex/events') return openStream(res);
  if (route === 'POST /api/codex/run') return send(res, 200, await codex.startRun(await readJson(req, res)));
  if (route === 'POST /api/codex/stop') {
    await codex.stopRun(await readJson(req, res));
    return send(res, 200, { ok: true });
  }
  if (route === 'POST /api/codex/login') {
    await readJson(req, res);
    const { authUrl } = await codex.login();
    // The page opens it in a new tab, so it must be a web address and nothing else.
    if (!(typeof authUrl === 'string' && authUrl.startsWith('https://'))) throw Object.assign(httpError(502, 'not https'), { code: 'bad-sign-in' });
    return send(res, 200, { authUrl });
  }
  const thread = /^\/api\/codex\/threads\/([^/]+)$/.exec(url.pathname);
  if (req.method === 'GET' && thread) {
    let id;
    try { id = decodeURIComponent(thread[1]); } catch { throw httpError(400, 'bad thread id'); }
    return send(res, 200, codex.threadView(await codex.readThread(id, true)));
  }
  throw httpError(404, 'not found');
}

function isDir(path) {
  try { return statSync(path).isDirectory(); } catch { return false; }
}

// The last 5 commits in a listed session's folder, masked; null when the folder
// is gone, is not a repository or git fails. git's words and the folder stay out of the log.
async function sessionCommits(cwd) {
  if (!isAbsolute(cwd) || !isDir(cwd)) return null;
  let result = null;
  try { result = await run('git', ['log', '-5', '--format=%h%x09%cI%x09%s'], cwd, 10_000); } catch { /* git cannot start */ }
  if (result?.code !== 0) {
    console.error(`claude: git log failed (exit ${result?.code})`);
    return null;
  }
  return mask(result.out.split(/\r?\n/).filter(Boolean).map((line) => {
    const [hash, at, ...subject] = line.split('\t');
    return { hash, at, subject: subject.join('\t') };
  }));
}

// A session the latest listing holds, or an agent inside that session's own
// folder: no request names a path that is read or a folder git runs in.
async function claudeView(rawId, rawAgent) {
  const notFound = () => httpError(404, 'no such session or agent');
  let id, agentId;
  try {
    id = decodeURIComponent(rawId);
    agentId = rawAgent === undefined ? null : decodeURIComponent(rawAgent);
  } catch { throw notFound(); }
  const session = (await claudeNow()).sessions.find((s) => s.id === id);
  if (!session) throw notFound();
  if (agentId !== null) {
    const found = findAgent(opts.home, id, agentId);
    const row = found && agentRow(found.path, found.run);
    if (!row) throw notFound();
    const { readable, steps } = readSteps(found.path, { sidechain: true });
    return { ...row, readable, steps };
  }
  const transcript = findTranscript(opts.home, id);
  const { readable, steps, branch, cwd, source, folder } = transcript ? readSteps(transcript) : { readable: false, steps: [], branch: null };
  // The listing's 64 KB tail can miss what this 2 MB one holds, when the last line alone is bigger.
  // git runs in the folder unmasked: the registry's for a live session, else the transcript's.
  const live = claudeSessions(opts.home).sessions.find((s) => s.id === id);
  return { ...session, cwd: session.cwd || cwd || '', source: session.source || source || '', branch,
    commits: await sessionCommits(live?.cwd || folder || ''), readable, steps, ...sessionParts(opts.home, id) };
}

// Any answer on the taskboard's port means it runs; the page frames it from there.
function taskboardRunning() {
  return new Promise((done) => {
    // Its first answer is enough; hanging up then means a board that keeps sending holds nothing open.
    const req = get(TASKBOARD, { agent: false, timeout: 1500 }, (res) => { res.destroy(); done(true); });
    req.on('timeout', () => req.destroy());
    req.on('error', () => done(false));
  });
}

async function api(req, res, url) {
  const route = `${req.method} ${url.pathname}`;
  if (route === 'GET /api/agents') return send(res, 200, await agentsNow());
  if (route === 'GET /api/questions') {
    try { return send(res, 200, readQuestions(questionsFile)); } catch (err) { return send(res, 200, { version: 1, questions: [], error: plain(err.message) }); }
  }
  const answer = /^\/api\/questions\/([^/]+)\/answer$/.exec(url.pathname);
  if (req.method === 'POST' && answer) {
    let id;
    try { id = decodeURIComponent(answer[1]); } catch { throw httpError(400, 'bad question id'); }
    const body = await readJson(req, res);
    const question = await answerQuestion(questionsFile, id, body.answer);
    agentsNow.forget(); // the refresh after Save counts the answered question at once
    return send(res, 200, { question });
  }
  if (route === 'GET /api/tasks') return send(res, 200, await tasksNow());
  if (route === 'GET /api/tasks/commits') {
    const file = url.searchParams.get('file') ?? '';
    // Only a document the index lists: no request names a path git is run on.
    if (!Object.hasOwn((await tasksNow()).titles, file)) throw Object.assign(httpError(404, 'not an indexed document'), { code: 'unknown-file' });
    return send(res, 200, { commits: await lastCommits(root, file) });
  }
  if (route === 'GET /api/claude') return send(res, 200, await claudeNow());
  const claude = /^\/api\/claude\/sessions\/([^/]+)(?:\/agents\/([^/]+))?$/.exec(url.pathname);
  if (req.method === 'GET' && claude) return send(res, 200, await claudeView(claude[1], claude[2]));
  if (route === 'GET /api/taskboard') return send(res, 200, { running: await taskboardRunning(), url: TASKBOARD });
  if (url.pathname === '/api/codex' || url.pathname.startsWith('/api/codex/')) return await codexApi(req, res, url).catch(codexError);
  throw httpError(404, 'not found');
}

function serveFile(res, pathname) {
  const index = resolve(dist, 'index.html');
  if (!statSync(index, { throwIfNoEntry: false })?.isFile()) {
    return send(res, 503, { error: 'The app is not built yet: in Library/dashboard/app run npm ci --ignore-scripts, then npm run build.', code: sharedCode(503) });
  }
  let rel;
  try { rel = pathname === '/' ? 'index.html' : decodeURIComponent(pathname).replace(/^\/+/, ''); } catch { throw httpError(400, 'bad path'); }
  const file = resolve(dist, rel);
  if (!file.startsWith(dist + sep) || !statSync(file, { throwIfNoEntry: false })?.isFile()) throw httpError(404, 'not found');
  // A link inside dist may lead anywhere: where it really leads must be inside dist too.
  // The native call gives the on-disk spelling, where the JS one keeps a link target's case (Windows).
  if (!realpathSync.native(file).startsWith(realpathSync.native(dist) + sep)) throw httpError(404, 'not found');
  // Read before the headers, so a file removed mid-rebuild still gets an answer.
  const body = readFileSync(file);
  res.writeHead(200, {
    'Content-Type': TYPES[extname(file)] ?? 'application/octet-stream', 'Content-Security-Policy': CSP,
    'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'Cache-Control': file.startsWith(assets) ? 'max-age=31536000, immutable' : 'no-cache',
  });
  res.end(body);
}

const server = createServer(async (req, res) => {
  const host = `${HOST}:${server.address().port}`;
  const own = `http://${host}`;
  // A site that rebinds its own name to 127.0.0.1 still sends its own Host.
  if (req.headers.host !== host) return send(res, 403, { error: `wrong host: open ${own}`, code: 'forbidden' });
  const writes = req.method !== 'GET' && req.method !== 'HEAD';
  if (writes && req.headers.origin !== own && !allowed.has(req.headers.origin)) return send(res, 403, { error: 'this origin may not change anything', code: 'forbidden' });
  let url;
  try { url = new URL(req.url, own); } catch { return send(res, 400, { error: 'bad request target', code: 'bad-request' }); }
  const isApi = url.pathname.startsWith('/api/');
  // Another site's page can still send a no-cors GET with this Host; the browser marks it.
  if (isApi && req.headers['sec-fetch-site'] === 'cross-site') return send(res, 403, { error: 'another site may not use the API', code: 'forbidden' });
  try {
    if (isApi) return await api(req, res, url);
    if (req.method !== 'GET') throw httpError(405, 'method not allowed');
    return serveFile(res, url.pathname);
  } catch (err) {
    if (res.headersSent) return void res.destroy(); // too late for an error answer; never leave it hanging
    if (err.status) return send(res, err.status, { error: plain(err.message), code: err.code ?? sharedCode(err.status) });
    console.error(err); // an unexpected error can quote a local path, so it stays here
    send(res, 500, { error: 'internal error', code: 'internal' });
  }
});

server.on('error', (err) => { console.error(`The dashboard could not listen on ${HOST}:${port}: ${err.message}`); process.exit(1); });
server.listen(port, HOST, () => {
  console.log(`Dashboard: http://${HOST}:${server.address().port}\nThis computer only. Close this window or press Ctrl+C to stop it.`);
});
for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(signal, () => process.exit(0));
process.on('exit', () => codex.end());
