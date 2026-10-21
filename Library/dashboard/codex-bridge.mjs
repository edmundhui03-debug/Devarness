#!/usr/bin/env node
// codex-bridge.mjs: the local bridge between the Zack dev. dashboard and Codex.
//
//   node codex-bridge.mjs --folder <project folder> [--port 47901] [--key-file <new file>]
//                         [--allow-origin http://127.0.0.1:<port>]...
//
// It listens on 127.0.0.1 only, makes a fresh key at every start and answers
// only requests that carry it. The key is printed once for a person at their
// own terminal; with --key-file it goes into that new file instead, for an
// agent whose output a transcript keeps. Behind it runs one `codex app-server`,
// Codex's own local protocol, started on first use and ended with the bridge:
// it lists every Codex thread on this computer (the app's, the terminal's and
// Aster's `codex exec` runs), shows what each is doing, signs in, reads the
// quota, and runs prompts in new threads in the folder or in threads it lists.
// Approvals are off: Codex is never asked to wait for one, and any request it
// sends anyway is declined and shown. Full access is never offered. Every
// prompt spends the Codex account's quota. Nothing is written to disk. The
// design is DESIGN.md beside this file; Node built-ins only.

import { createHash, randomBytes, timingSafeEqual } from 'node:crypto';
import { statSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { createCodex, findCodex, httpError, isObj } from './server/codex.mjs';

const HOST = '127.0.0.1';
const MAX_BODY = 64 * 1024;
const USAGE = 'Usage: node codex-bridge.mjs --folder <project folder> [--port 47901] [--key-file <new file>] [--allow-origin http://127.0.0.1:<port>]';

function refuse(message) {
  console.error(`${message}\n${USAGE}`);
  process.exit(2);
}

// --- what it was started with ------------------------------------------------

let opts;
try {
  opts = parseArgs({ options: {
    folder: { type: 'string' },
    port: { type: 'string', default: '47901' },
    host: { type: 'string', default: HOST },
    'key-file': { type: 'string' },
    'allow-origin': { type: 'string', multiple: true, default: [] },
    help: { type: 'boolean', short: 'h' },
  } }).values;
} catch (err) {
  refuse(err.message);
}
if (opts.help) {
  console.log(USAGE);
  process.exit(0);
}
if (opts.host !== HOST) refuse(`The bridge listens on ${HOST} only; --host ${opts.host} is refused.`);
if (!opts.folder) refuse('--folder is required: the project folder Codex works in.');
const folder = resolve(opts.folder);
if (!statSync(folder, { throwIfNoEntry: false })?.isDirectory()) refuse(`Not a folder: ${folder}`);
const port = /^\d+$/.test(opts.port) ? Number(opts.port) : NaN;
if (!(port <= 65535)) refuse(`Not a port: ${opts.port}`);
for (const origin of opts['allow-origin']) {
  // Compared as the browser spells it: the URL parser refuses a bad port and drops a default one.
  let url = null;
  try { url = new URL(origin); } catch { /* refused below */ }
  if (url?.protocol !== 'http:' || url.hostname !== HOST || !url.port || url.origin !== origin) {
    refuse(`--allow-origin takes a page on this computer only, such as http://127.0.0.1:5173; ${origin} is refused.`);
  }
}
const allowed = new Set(opts['allow-origin']);
const keyFile = opts['key-file'] === undefined ? null : resolve(opts['key-file']);
// CODEX_CMD starts as given; a codex.exe found behind an npm shim gets the npm launcher's environment.
const { command: codexCmd, env: codexEnv } = process.env.CODEX_CMD ? { command: parseCommand(process.env.CODEX_CMD) } : findCodex();

function parseCommand(text) {
  let cmd;
  try { cmd = JSON.parse(text); } catch { /* refused below */ }
  if (Array.isArray(cmd) && cmd.length && cmd.every((part) => typeof part === 'string' && part)) return cmd;
  refuse('CODEX_CMD must be a JSON array of strings, such as ["codex"].');
}

// --- the key -----------------------------------------------------------------

const KEY = randomBytes(24).toString('base64url');
const digest = (text) => createHash('sha256').update(text).digest();
const KEY_DIGEST = digest(KEY);
// Equal-length digests make the comparison constant-time whatever was sent.
const keyOk = (given) => typeof given === 'string' && timingSafeEqual(digest(given), KEY_DIGEST);

// --- Codex: server/codex.mjs runs the one app-server -----------------------------

const listeners = new Set(); // open /events streams
const sse = (event) => `data: ${JSON.stringify(event)}\n\n`;
const broadcast = (event) => { for (const res of listeners) res.write(sse(event)); };
const codex = createCodex({ folder, command: codexCmd, env: codexEnv, onEvent: broadcast });

// --- HTTP ----------------------------------------------------------------------

function send(res, status, body, headers) {
  const json = body === null ? {} : { 'Content-Type': 'application/json; charset=utf-8' };
  res.writeHead(status, { ...headers, ...json, 'Cache-Control': 'no-store' });
  res.end(body === null ? '' : JSON.stringify(body));
}

function readJson(req) {
  if (!/^application\/json\s*(;|$)/i.test(req.headers['content-type'] ?? '')) {
    throw httpError(415, 'send JSON, with Content-Type: application/json');
  }
  return new Promise((done, fail) => {
    const chunks = [];
    let size = 0;
    req.on('data', (chunk) => {
      size += chunk.length;
      if (size <= MAX_BODY) chunks.push(chunk);
    });
    req.on('error', fail);
    req.on('end', () => {
      if (size > MAX_BODY) return fail(httpError(413, 'the body is over 64 KB'));
      let body;
      try { body = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch {
        return fail(httpError(400, 'the body is not valid JSON'));
      }
      if (!isObj(body)) return fail(httpError(400, 'the body must be a JSON object'));
      done(body);
    });
  });
}

function openStream(res, cors) {
  res.writeHead(200, { ...cors, 'Content-Type': 'text/event-stream; charset=utf-8', 'Cache-Control': 'no-store' });
  res.flushHeaders();
  listeners.add(res);
  res.on('close', () => listeners.delete(res));
}

const server = createServer(async (req, res) => {
  const own = `http://${HOST}:${server.address().port}`;
  // A site that rebinds its own name to 127.0.0.1 still sends its own Host.
  if (req.headers.host !== `${HOST}:${server.address().port}`) return send(res, 403, { error: 'wrong host' }, {});
  const origin = req.headers.origin;
  // A page opened from disk sends Origin "null", but so do sandboxed iframes and
  // data: pages on any site, so this only narrows who may call: the key is the
  // only real barrier.
  if (origin !== undefined && origin !== 'null' && origin !== own && !allowed.has(origin)) {
    return send(res, 403, { error: 'this origin may not use the bridge' }, {});
  }
  const cors = origin === undefined ? {} : { 'Access-Control-Allow-Origin': origin, Vary: 'Origin' };
  if (req.method === 'OPTIONS') {
    return send(res, 204, null, {
      ...cors,
      'Access-Control-Allow-Methods': 'GET, POST',
      'Access-Control-Allow-Headers': 'X-Bridge-Key, Content-Type',
      'Access-Control-Max-Age': '600',
      ...(req.headers['access-control-request-private-network'] ? { 'Access-Control-Allow-Private-Network': 'true' } : {}),
    });
  }
  let url;
  try {
    url = new URL(req.url, own);
  } catch {
    // An unparsable target would otherwise reject this async handler and end the bridge.
    return send(res, 400, { error: 'bad request target' }, cors);
  }
  // The key travels in a header only, never in an address a log or history keeps.
  if (!keyOk(req.headers['x-bridge-key'])) return send(res, 401, { error: 'missing or wrong key' }, cors);
  try {
    switch (`${req.method} ${url.pathname}`) {
      case 'GET /health':
        return send(res, 200, { ok: true, folder, codex: codexCmd.join(' '), appServer: await codex.health() }, cors);
      case 'GET /account':
        return send(res, 200, await codex.account(), cors);
      case 'POST /login':
        await readJson(req);
        return send(res, 200, await codex.login(), cors);
      case 'GET /threads':
        return send(res, 200, { threads: await codex.listThreads() }, cors);
      case 'GET /thread': {
        const id = url.searchParams.get('id');
        if (!id) throw httpError(400, 'id is required');
        return send(res, 200, codex.threadView(await codex.readThread(id, true)), cors);
      }
      case 'POST /run':
        return send(res, 200, await codex.startRun(await readJson(req)), cors);
      case 'POST /stop':
        await codex.stopRun(await readJson(req));
        return send(res, 200, { ok: true }, cors);
      case 'GET /events':
        return openStream(res, cors);
      default:
        throw httpError(404, 'not found');
    }
  } catch (err) {
    if (!res.headersSent) send(res, err.status ?? 500, { error: err.message }, cors);
  }
});

server.on('error', (err) => {
  console.error(`The bridge could not listen on ${HOST}:${port}: ${err.message}`);
  process.exit(1);
});

server.listen(port, HOST, () => {
  const page = pathToFileURL(join(dirname(fileURLToPath(import.meta.url)), 'index.html')).href;
  let keyLines = ["Open the dashboard's Codex page and paste this key:", KEY];
  if (keyFile) {
    // 'wx': a new file only, so nothing already there is overwritten or reused.
    try {
      writeFileSync(keyFile, `${KEY}\n`, { flag: 'wx', mode: 0o600 });
    } catch (err) {
      refuse(`The key file was not written (${err.code ?? err.message}); name a file that does not exist yet: ${keyFile}`);
    }
    keyLines = [`key written to ${keyFile}`];
  }
  console.log([
    `Codex bridge for ${folder}`,
    `Listening on http://${HOST}:${server.address().port}, this computer only. Close this window or press Ctrl+C to stop it.`,
    `Dashboard: ${page}`,
    "Every prompt spends the Codex account's quota.",
    ...keyLines,
  ].join('\n'));
});

// Closing the window or Ctrl+C ends the app-server, and with it every turn, with the bridge.
for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP']) {
  process.on(signal, () => process.exit(0));
}
process.on('exit', () => codex.end());
