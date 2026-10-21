// Tests for the dashboard server's Codex side: the codex.exe lookup behind an
// npm shim, the masker, the turn markers, and the Codex and taskboard routes.
// Codex is always fixtures/fake-codex.mjs, so no test spends Codex quota.
// Usage: node --test test_dashboard_codex.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { generateKeyPairSync, randomBytes } from 'node:crypto';
import fs, { appendFileSync, mkdirSync, mkdtempSync, readFileSync, utimesSync, writeFileSync } from 'node:fs';
import http from 'node:http';
import { syncBuiltinESMExports } from 'node:module';
import { tmpdir } from 'node:os';
import { delimiter, dirname, join, resolve, win32 } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';
import { createCodex, findCodex } from '../dashboard/server/codex.mjs';
import { lastTurnOpen } from '../dashboard/server/markers.mjs';
import { MASK, mask } from '../dashboard/server/mask.mjs';

const FAKE = fileURLToPath(new URL('fixtures/fake-codex.mjs', import.meta.url));

// A Windows folder holding exactly `files`, seen through findCodex's `exists`.
const disk = (...files) => (path) => files.includes(path);
const NPM = 'C:\\npm';
const SHIM = win32.join(NPM, 'codex.cmd');
const CODEX_PKG = win32.join(NPM, 'node_modules', '@openai', 'codex');
const exe = (vendor, triple = 'x86_64-pc-windows-msvc') => win32.join(vendor, triple, 'bin', 'codex.exe');
const windows = (exists, { arch = 'x64', path = `C:\\Windows;${NPM}` } = {}) => findCodex({ env: { PATH: path }, platform: 'win32', arch, exists }).command;

test('findCodex finds the codex.exe behind an npm shim, where the shim\'s codex.js would', () => {
  const nested = exe(win32.join(CODEX_PKG, 'node_modules', '@openai', 'codex-win32-x64', 'vendor'));
  assert.deepEqual(windows(disk(SHIM, nested)), [nested]);
  const beside = exe(win32.join(NPM, 'node_modules', '@openai', 'codex-win32-x64', 'vendor'));
  assert.deepEqual(windows(disk(SHIM, beside)), [beside]);
  const own = exe(win32.join(CODEX_PKG, 'vendor'));
  assert.deepEqual(windows(disk(SHIM, own)), [own]);
  // The Windows variable is spelled Path; a plain object does not fold the case.
  assert.deepEqual(findCodex({ env: { Path: NPM }, platform: 'win32', arch: 'x64', exists: disk(SHIM, own) }).command, [own]);
});

test('the codex.exe behind an npm shim starts with the npm launcher\'s two variables; one Node finds itself gets none', async (t) => {
  const own = exe(win32.join(CODEX_PKG, 'vendor'));
  const file = join(mkdtempSync(join(tmpdir(), 'dash-env-')), 'env.json');
  // A small environment of its own, never this computer's: a failure prints it whole.
  const kept = { PATH: `C:\\Windows;${NPM}`, FAKE_CODEX_ENV_TO: file };
  const parent = { ...kept, CODEX_MANAGED_BY_BUN: '1', CODEX_MANAGED_BY_PNPM: '1', CODEX_MANAGED_BY_VITE_PLUS: '1' };
  const find = (exists, platform = 'win32') => findCodex({ env: parent, platform, arch: 'x64', exists });
  const found = find(disk(SHIM, own));
  assert.deepEqual(found, { command: [own], env: { ...kept, CODEX_MANAGED_PACKAGE_ROOT: CODEX_PKG, CODEX_MANAGED_BY_NPM: '1' } });
  assert.deepEqual(find(disk('C:\\Windows\\codex.exe', SHIM, own)), { command: ['C:\\Windows\\codex.exe'] });
  for (const exists of [disk(SHIM), disk()]) assert.deepEqual(find(exists), { command: ['codex'] });
  assert.deepEqual(find(disk(SHIM, own), 'linux'), { command: ['codex'] });
  // The app-server gets that environment: the fake stands in for the codex.exe, which no test may start.
  const codex = createCodex({ folder: mkdtempSync(join(tmpdir(), 'dash-codex-')), command: [process.execPath, FAKE], env: found.env });
  t.after(() => codex.end());
  assert.equal((await codex.health()).up, true);
  assert.deepEqual(JSON.parse(readFileSync(file, 'utf8')), { CODEX_MANAGED_PACKAGE_ROOT: CODEX_PKG, CODEX_MANAGED_BY_NPM: '1' });
});

test('findCodex names a codex.exe on PATH by its full path, skips a relative PATH entry, and falls back to codex', () => {
  const nested = exe(win32.join(CODEX_PKG, 'node_modules', '@openai', 'codex-win32-x64', 'vendor'));
  // A codex.exe in a folder before the shim, named whole: a bare name would be
  // looked for first in the folder the app-server starts in (Aster's review, #5).
  assert.deepEqual(windows(disk('C:\\Windows\\codex.exe', SHIM, nested)), ['C:\\Windows\\codex.exe']);
  assert.deepEqual(windows(disk('codex.exe', 'tools\\codex.exe'), { path: '.;tools' }), ['codex']);
  assert.deepEqual(windows(disk(SHIM)), ['codex']);
  assert.deepEqual(windows(disk()), ['codex']);
  assert.deepEqual(findCodex({ env: {}, platform: 'win32', arch: 'x64', exists: disk() }).command, ['codex']);
});

test('findCodex looks for the arm64 package on arm64, and not at all off Windows', () => {
  const arm = exe(win32.join(CODEX_PKG, 'node_modules', '@openai', 'codex-win32-arm64', 'vendor'), 'aarch64-pc-windows-msvc');
  assert.deepEqual(windows(disk(SHIM, arm), { arch: 'arm64' }), [arm]);
  const x64 = exe(win32.join(CODEX_PKG, 'node_modules', '@openai', 'codex-win32-x64', 'vendor'));
  assert.deepEqual(windows(disk(SHIM, x64), { arch: 'arm64' }), ['codex']);
  for (const platform of ['linux', 'darwin']) {
    const looked = [];
    assert.deepEqual(findCodex({ env: { PATH: '/usr/bin' }, platform, arch: 'x64', exists: (p) => looked.push(p) }).command, ['codex']);
    assert.deepEqual(looked, [], platform);
  }
});

// Each secret as Codex might print it, and what is left once it is masked.
const SECRETS = [
  [`sk-proj-${'abcdefghij'.repeat(4)}`, MASK],
  [`ghp_${'A1b2C3d4E5'.repeat(4)}`, MASK],
  [`gho_${'A1b2C3d4E5'.repeat(4)}`, MASK],
  [`github_pat_11ABCDEFG0_${'x9Y8z7W6v5'.repeat(3)}`, MASK],
  [['xoxb-123', '4567890-', '09876543', '21-AbCdE', 'fGhIjKl'].join(''), MASK],
  ['AK' + 'IAIOSFODNN7EXAMPLE', MASK],
  ['AIzaSy0_-abcdefghijklmnopqrstuvwxyz1234', MASK],
  ['Authorization: Bearer abc.def.ghi', `Authorization: Bearer ${MASK}`],
  ['Authorization: Basic dXNlcjpodW50ZXIy', `Authorization: Basic ${MASK}`],
  ['DATABASE_URL=postgres://admin:hunter2@db.example.com:5432/app', `DATABASE_URL=postgres://admin:${MASK}@db.example.com:5432/app`],
  ['"password": "hunter2"', `"password": ${MASK}`],
  ['password=hunter2', `password=${MASK}`],
  ['PASSWD: x', `PASSWD: ${MASK}`],
  // Go's and make's assignments.
  ['PASSWORD := hunter2', `PASSWORD := ${MASK}`],
  ['API_KEY ?= abc123', `API_KEY ?= ${MASK}`],
  // An environment variable's name carries the word inside it.
  ['DB_PASSWORD=hunter2', `DB_PASSWORD=${MASK}`],
  ['AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY', `AWS_SECRET_ACCESS_KEY=${MASK}`],
  [['GITHUB_T', 'OKEN=abc', '123def45', '6ghi789'].join(''), `GITHUB_TOKEN=${MASK}`],
  // Key-named variables, each value too short for the long-run rule, as `cat .env` prints them.
  [['PRIVATE_', 'KEY=0x4c', '0883a691', '02937d62', '31471b5d', 'bb6204fe', '51296170', '82792ae4', '68d01a3f', '362318'].join(''), `PRIVATE_KEY=${MASK}`],
  [['ENCRYPTI', 'ON_KEY=q', '5Jd9h3kR', '7vT2mW8x', 'Y1zA4bC6', 'eF0gH2jK', '3lM5nP7r', 'S9='].join(''), `ENCRYPTION_KEY=${MASK}`],
  ['APP_KEY=base64:q5Jd9h3kR7vT2mW8xY1zA4bC6eF0gH2jK3lM5nP7rS9=', `APP_KEY=${MASK}`],
  [['SIGNING_', 'KEY=whse', 'c_5WbX5k', 'EWLlfzsG', 'NjH64I8l', 'OOqUB6e8', 'FH'].join(''), `SIGNING_KEY=${MASK}`],
  [['MASTER_K', 'EY=7f3c9', 'a1e5b2d8', 'f4a6c0e9', 'b3d7a1f5', 'c2e'].join(''), `MASTER_KEY=${MASK}`],
  // JSON inside JSON: `aws secretsmanager get-secret-value` prints SecretString so.
  [String.raw`"SecretString": "{\"username\":\"admin\",\"password\":\"hunter2\"}"`, `"SecretString": ${MASK}`],
  [String.raw`{\"username\":\"admin\",\"password\":\"hunter2\"}`, String.raw`{\"username\":\"admin\",\"password\":${MASK}}`],
  [['eyJhbGci', 'OiJIUzI1', 'NiJ9.eyJ', 'zdWIiOiI', 'xMjM0NTY', '3ODkwIn0', '.dozjgNr', 'yP4J3jVm', 'NHl0w5N_', 'XgL0n3I9', 'PlFUP0TH', 'sR8U'].join(''), MASK],
  ['QUJD'.repeat(20) + '==', MASK],
  // `cat key.pem` and `cat ~/.ssh/id_ed25519`: wrapped at 64 and 70, each line too short alone.
  [generateKeyPairSync('rsa', { modulusLength: 2048 }).privateKey.export({ type: 'pkcs8', format: 'pem' }), `${MASK}\n`],
  [generateKeyPairSync('ed25519').privateKey.export({ type: 'pkcs8', format: 'pem' }), `${MASK}\n`],
  [`${'-----BEGIN ' + 'OPENSSH PRIVATE KEY-----'}\n${'b3BlbnNzaC1rZXktdjE'.padEnd(70, 'A')}\n${'Q'.repeat(30)}\n-----END OPENSSH PRIVATE KEY-----`, MASK],
  // `base64 secret.bin` wraps at 76; the short last line goes too, with or without a final newline.
  [randomBytes(600).toString('base64').match(/.{1,76}/g).join('\n') + '\n', `${MASK}\n`],
  [randomBytes(600).toString('base64').match(/.{1,76}/g).join('\r\n'), MASK],
];

test('mask replaces each secret in a string, an array and a nested object, and keeps the words around it', () => {
  for (const [secret, masked] of SECRETS) {
    const text = `before ${secret} after`;
    const kept = `before ${masked} after`;
    assert.equal(mask(text), kept, secret);
    assert.deepEqual(mask(['plain', text]), ['plain', kept], secret);
    assert.deepEqual(mask({ turn: { items: [{ output: text, exitCode: 0 }] } }), { turn: { items: [{ output: kept, exitCode: 0 }] } }, secret);
  }
});

test('mask leaves ordinary text, a git hash, a Windows path and numbers as they were, and copies', () => {
  const plain = ['Ran the tests: 48 passed.', 'e87b768dd362c0f7da70859cfd5b71d7e81a2b3c',
    'D:\\work\\dev\\Library\\dashboard\\server\\codex.mjs', 'a task-runner with sk-learn',
    'a basic implementation of https://example.com:8443/a@b', `${'e3b0c442'.repeat(8)}\nDone.`];
  for (const text of plain) assert.equal(mask(text), text);
  const value = { n: 42, ok: true, none: null, list: [1, 'two'] };
  const copy = mask(value);
  assert.deepEqual(copy, value);
  assert.notEqual(copy, value);
  assert.notEqual(copy.list, value.list);
  assert.equal(mask(7), 7);
});

test('mask hides a string held under a secret\'s name, and keeps a count', () => {
  // As an MCP tool call's arguments would carry it.
  assert.deepEqual(mask({ type: 'mcpToolCall', arguments: { password: ['hunter2'].join(''), api_key: ['abc123de', 'f456'].join(''), path: 'a.txt', tokens: 12 } }),
    { type: 'mcpToolCall', arguments: { password: MASK, api_key: MASK, path: 'a.txt', tokens: 12 } });
});

test('mask hides the whole of a value in JSON inside JSON, a quote inside it included', () => {
  const line = JSON.stringify({ log: JSON.stringify({ password: 'hun"ter2' }) });
  const out = mask(line);
  assert.ok(out.includes(MASK) && !out.includes('ter2'), out);
});

test('mask hides any value under a password or secret name, and every string under a token name; counts stay', () => {
  assert.deepEqual(mask({ password: ['hunter2'], secret: 424242, api_key: ['k1', { v: 'k2' }], tokens: 12, token_count: 3 }),
    { password: [MASK], secret: MASK, api_key: [MASK, { v: MASK }], tokens: 12, token_count: 3 });
});

test('mask hides an Authorization header of any case and length, and temporary AWS key ids', () => {
  for (const text of ['Authorization: basic dXNlcjpwYXNz', 'authorization: Bearer abc123', 'key AS' + 'IAABCDEFGHIJKLMNOP here']) {
    const out = mask(text);
    assert.ok(out.includes(MASK) && !/dXNlcjpwYXNz|abc123|ASIAABCD/.test(out), out);
  }
});

test('mask leaves nothing of a key longer than one run of a pattern', () => {
  assert.equal(mask(`sk-${'A1_'.repeat(3000)}`), MASK);
  assert.equal(mask(`ghp_${'a'.repeat(9000)} done`), `${MASK} done`);
});

test('mask hides service tokens, a password argument, curl -u, a Cookie header and Docker\'s auth (ECC review)', () => {
  const k = 'aB3'.repeat(14);
  const cases = [
    [[`stripe =`, ` Stripe(`, `'sk_live`, `_`, String(k), `')`].join(''), k], [[`login hf`, `_`, String(k)].join(''), k], [[`glpat-`, String(k)].join(''), k], [[`npm_`, String(k.slice(0, 36))].join(''), k.slice(0, 36)],
    [['mysql -u', ' root --', 'password', ' aB3aB3a', 'B3aB3 db'].join(''), ['aB3aB3aB', '3aB3'].join('')], [['curl -u ', 'admin:aB', '3aB3aB3a', 'B3 https', '://x'].join(''), ['aB3aB3aB', '3aB3'].join('')],
    [['Cookie: ', 'sessioni', 'd=aB3aB3', 'aB3aB3; ', 'theme=da', 'rk'].join(''), ['sessioni', 'd'].join('')], [['{"auths"', ':{"ghcr.', 'io":{"au', 'th":"b3d', 'uZXI6cGF', 'zcw=="}}', '}'].join(''), ['b3duZXI6'].join('')],
  ];
  for (const [text, secret] of cases) {
    const out = mask(text);
    assert.ok(out.includes(MASK) && !out.includes(secret), out);
  }
  assert.deepEqual(mask({ auths: { 'ghcr.io': { auth: ['b3duZXI6', 'cGFzcw=='].join('') } } }), { auths: { 'ghcr.io': { auth: MASK } } });
});

test('mask hides any Authorization scheme, and an auth or password value in any case, escaped or an object (Aster, wave 4)', () => {
  const cases = [
    [['Authoriz', 'ation: N', 'egotiate', ' c2VjcmV', '0aA=='].join(''), ['c2VjcmV0'].join('')], [['{"Author', 'ization"', ': "Negot', 'iate c2V', 'jcmV0aA=', '="}'].join(''), ['c2VjcmV0'].join('')],
    [['{"auth":', '{"pass":', '"hunter2', '"}}'].join(''), 'hunter2'], [['{"AUTH":', '"admin:h', 'unter2"}'].join(''), 'hunter2'], [['{\\"auth\\', '":\\"admi', 'n:hunter', '2\\"}'].join(''), 'hunter2'],
    [['{"passwo', 'rd": {"v', 'alue": "', 'hunter2"', '}}'].join(''), 'hunter2'],
    // curl's user:password after many headers, or as --user.
    [[`curl `, String('-H "X-Trace: 1" '.repeat(20)), `-u root:`, `hunter2 `, `https://`, `x`].join(''), 'hunter2'], [['curl --u', 'ser=root', ':hunter2', ' https:/', '/x'].join(''), 'hunter2'],
  ];
  for (const [text, secret] of cases) {
    const out = mask(text);
    assert.ok(out.includes(MASK) && !out.includes(secret), out);
  }
  // A git commit id is 40 hex, and "author" and "oauth" are not "auth".
  for (const text of ['commit 0123456789abcdef0123456789abcdef01234567', '{"author": "Jane", "oauth": "on"}']) assert.equal(mask(text), text);
});

test('mask takes one linear pass over a long run after a key', () => {
  const started = performance.now();
  assert.equal(mask(`sk-${'a'.repeat(20)}${'-'.repeat(8 << 20)}`), MASK);
  assert.ok(performance.now() - started < 1500, `took ${Math.round(performance.now() - started)} ms`);
});

test('mask returns on a run of megabytes and leaves none of it; a repeated name costs nothing', () => {
  // `base64 -w0 photo.jpg` prints one such run; an open-ended pattern overflowed V8's stack on it.
  const runs = ['QUJD'.repeat(2_500_000), ...['sk-', 'ghp_', 'github_pat_', 'xoxb-', 'Bearer ', 'eyJhbGciOiJIUzI1NiJ9.']
    .map((prefix) => prefix + 'a'.repeat(10_000_000))];
  for (const text of runs) assert.ok(!/[A-Za-z0-9+/]{80}/.test(mask(text)), text.slice(0, 12));
  // `base64 photo.jpg` prints it wrapped at 76.
  assert.ok(!/[A-Za-z0-9+/]{60}/.test(mask(('QUJD'.repeat(19) + '\n').repeat(100_000))));
  // An unbounded name around the word took 4 s on this 256 KB; it takes no time bounded.
  const start = Date.now();
  mask('password'.repeat(32_000));
  assert.ok(Date.now() - start < 1000, `${Date.now() - start} ms`);
  // A bound of 4,096 on curl's reach took 2.7 s on this 1 MB line; 1,024 takes under half a second.
  const curls = Date.now();
  mask('curl '.repeat(200_000));
  assert.ok(Date.now() - curls < 1500, `${Date.now() - curls} ms`);
});

// Session file lines as Codex writes them: one JSON object per line.
const lines = (...entries) => entries.map((e) => JSON.stringify(e)).join('\n') + '\n';
const marker = (type) => ({ timestamp: '2026-10-10T10:00:00Z', type: 'event_msg', payload: { type } });
const OTHER = lines({ timestamp: '2026-10-10T10:00:00Z', type: 'response_item', payload: { type: 'message', role: 'assistant', content: [] } });
const filler = (bytes) => OTHER.repeat(Math.ceil(bytes / OTHER.length));

test('lastTurnOpen says whether the last turn marker of a session file is a start', () => {
  const file = join(mkdtempSync(join(tmpdir(), 'dash-markers-')), 'session.jsonl');
  writeFileSync(file, lines({ type: 'session_meta', payload: { id: 's1' } }, marker('task_started')) + OTHER);
  assert.equal(lastTurnOpen(file), true);
  appendFileSync(file, lines(marker('task_complete')) + OTHER);
  assert.equal(lastTurnOpen(file), false);
  appendFileSync(file, lines(marker('task_started'), marker('turn_aborted')));
  assert.equal(lastTurnOpen(file), false);
  writeFileSync(file, lines({ type: 'task_started' }));
  assert.equal(lastTurnOpen(file), true, 'a marker at the top level counts too');
});

test('lastTurnOpen is null when the last 64 KB hold no marker, or the file cannot be read', () => {
  const dir = mkdtempSync(join(tmpdir(), 'dash-markers-'));
  const big = join(dir, 'big.jsonl');
  // The last marker, a start, sits in the first 200 KB of 1 MB: only the tail is read.
  writeFileSync(big, lines(marker('task_complete')) + filler(190_000) + lines(marker('task_started')) + filler(820_000));
  assert.equal(lastTurnOpen(big), null);
  writeFileSync(join(dir, 'empty.jsonl'), '');
  writeFileSync(join(dir, 'broken.jsonl'), '{broken\nnot json\n{"type":\n');
  for (const name of ['gone.jsonl', 'empty.jsonl', 'broken.jsonl', '.']) assert.equal(lastTurnOpen(join(dir, name)), null, name);
});

test('a thread\'s state follows its session file\'s markers for 30 minutes; without one, the two-minute guess', async (t) => {
  const sessions = mkdtempSync(join(tmpdir(), 'dash-sessions-'));
  const codex = createCodex({ folder: mkdtempSync(join(tmpdir(), 'dash-codex-')), command: [process.execPath, FAKE, '--sessions', sessions] });
  t.after(() => codex.end());
  const file = join(sessions, 't-dev.jsonl');
  const state = async (text, ageMs) => {
    writeFileSync(file, text);
    const when = (Date.now() - ageMs) / 1000;
    utimesSync(file, when, when);
    return (await codex.listThreads()).find((th) => th.id === 't-dev').state;
  };
  // Changed a second ago, but its turn is complete: the guess alone said working elsewhere.
  assert.equal(await state(lines(marker('task_started'), marker('task_complete')), 1000), 'idle');
  assert.equal(await state(lines(marker('task_complete'), marker('task_started')), 1000), 'active-elsewhere');
  // A window killed mid-turn leaves its last turn open for good.
  assert.equal(await state(lines(marker('task_started')), 24 * 3600_000), 'idle');
  assert.equal(await state(OTHER, 1000), 'active-elsewhere');
  assert.equal(await state(OTHER, 600_000), 'idle');
  assert.equal((await codex.listThreads()).find((th) => th.id === 't-error').state, 'error');
});

test('a session file that cannot be measured shows its thread idle, and the rest of the list still comes', async (t) => {
  const sessions = mkdtempSync(join(tmpdir(), 'dash-sessions-'));
  const codex = createCodex({ folder: mkdtempSync(join(tmpdir(), 'dash-codex-')), command: [process.execPath, FAKE, '--sessions', sessions] });
  t.after(() => codex.end());
  writeFileSync(join(sessions, 't-dev.jsonl'), OTHER);
  // A file another process holds, or one in a folder this user may not read; the error quotes its path.
  const real = fs.statSync;
  fs.statSync = (path, ...rest) => {
    if (String(path).endsWith('t-dev.jsonl')) throw Object.assign(new Error(`EPERM: operation not permitted, stat '${path}'`), { code: 'EPERM' });
    return real(path, ...rest);
  };
  syncBuiltinESMExports();
  let threads;
  try { threads = await codex.listThreads(); } finally { fs.statSync = real; syncBuiltinESMExports(); }
  assert.deepEqual(threads.map((th) => [th.id, th.state]), [['t-dev', 'idle'], ['t-other', 'idle'], ['t-error', 'error']]);
});

// --- the routes, on the real server with the fake Codex --------------------------

const SERVER = fileURLToPath(new URL('../dashboard/server/server.mjs', import.meta.url));
const DEVARNESS_ROOT = resolve(dirname(SERVER), '..', '..', '..');
const THREAD_FIELDS = ['id', 'name', 'preview', 'source', 'nickname', 'cwd', 'inDev', 'createdAt', 'updatedAt', 'state', 'turn'];
const KEEP_ENV = ['PATH', 'SYSTEMROOT', 'USERPROFILE', 'HOME', 'TEMP', 'TMP'];

function request(port, method, path, { headers = {}, body } = {}) {
  return new Promise((done, fail) => {
    const req = http.request({ host: '127.0.0.1', port, method, path, headers: { Host: `127.0.0.1:${port}`, ...headers } }, (res) => {
      let text = '';
      res.setEncoding('utf8');
      res.on('data', (c) => { text += c; });
      res.on('end', () => done({ status: res.statusCode, headers: res.headers, text, body: JSON.parse(text) }));
    });
    req.on('error', fail);
    if (body !== undefined) req.write(body);
    req.end();
  });
}

// The server on port 0 with `command` as Codex (the fake by default), the fake
// steered by `env`. get and post answer { status, headers, text, body }.
async function startServer(t, { command = [process.execPath, FAKE], env = {} } = {}) {
  const root = mkdtempSync(join(tmpdir(), 'dash-codex-srv-'));
  const questions = join(root, 'questions.json');
  writeFileSync(questions, JSON.stringify({ version: 1, questions: [] }));
  const child = spawn(process.execPath, [SERVER, '--port', '0', '--home', root, '--questions', questions, '--dist', join(root, 'dist')], {
    env: { ...Object.fromEntries(KEEP_ENV.filter((k) => process.env[k]).map((k) => [k, process.env[k]])),
      CODEX_CMD: JSON.stringify(command), ...env }, windowsHide: true,
  });
  t.after(() => child.kill());
  const port = await new Promise((done, fail) => {
    let out = '';
    child.stdout.on('data', (c) => { out += c; const m = /http:\/\/127\.0\.0\.1:(\d+)/.exec(out); if (m) done(Number(m[1])); });
    child.on('exit', (code) => fail(new Error(`server exited ${code}: ${out}`)));
  });
  const own = `http://127.0.0.1:${port}`;
  return {
    root, port, own,
    get: (path) => request(port, 'GET', path),
    post: (path, body, origin = own) => request(port, 'POST', path, {
      headers: { 'Content-Type': 'application/json', Origin: origin }, body: JSON.stringify(body) }),
  };
}

// Opens the event stream; events() lists what has come whole, as parsed data
// lines, and closed() says whether the server has ended it.
function openEvents(t, port) {
  return new Promise((done, fail) => {
    let text = '';
    let closed = false;
    const req = http.get({ host: '127.0.0.1', port, path: '/api/codex/events', headers: { Host: `127.0.0.1:${port}` } }, (res) => {
      res.setEncoding('utf8');
      res.on('data', (c) => { text += c; });
      res.on('close', () => { closed = true; });
      done({
        res, text: () => text, closed: () => closed,
        // The last piece is an event still arriving, or empty.
        events: () => text.split('\n\n').slice(0, -1).filter((b) => b.startsWith('data: ')).map((b) => JSON.parse(b.slice(6))),
      });
    });
    req.on('error', (err) => fail(err));
    t.after(() => req.destroy());
  });
}

async function until(stream, method, ms = 5000) {
  for (const end = Date.now() + ms; Date.now() < end; await sleep(20)) {
    if (stream.events().some((e) => e.method === method)) return stream.events();
  }
  assert.fail(`no ${method} event within ${ms} ms: ${stream.text()}`);
}

test('GET /api/codex: up, the version from the user agent, the sign-in and the quota, never the email', async (t) => {
  const { get } = await startServer(t);
  const res = await get('/api/codex');
  assert.equal(res.status, 200);
  assert.deepEqual(res.body, {
    up: true, version: '0.162.0', signedIn: true, type: 'chatgpt', plan: 'plus',
    rateLimits: { primary: { usedPercent: 25, windowDurationMins: 300, resetsAt: 1900000000 },
      secondary: { usedPercent: 10, windowDurationMins: 10080, resetsAt: 1900500000 } },
    code: 'ok',
  });
  assert.ok(!res.text.includes('owner@example.com'));
});

test('GET /api/codex: signed out says so, still with 200', async (t) => {
  const { get } = await startServer(t, { env: { FAKE_CODEX_SIGNED_OUT: '1' } });
  const res = await get('/api/codex');
  assert.equal(res.status, 200);
  assert.deepEqual([res.body.up, res.body.signedIn, res.body.code], [true, false, 'codex-signed-out']);
});

test('a missing Codex answers 200 not started, and neither the answer nor the event stream names its path', async (t) => {
  const missing = join(mkdtempSync(join(tmpdir(), 'dash-nocodex-')), 'no-codex.exe');
  const { port, get, post } = await startServer(t, { command: [missing] });
  const stream = await openEvents(t, port);
  const res = await get('/api/codex');
  assert.equal(res.status, 200);
  assert.deepEqual(res.body, { up: false, version: null, signedIn: false, type: null, plan: null, rateLimits: null, code: 'codex-not-started' });
  const run = await post('/api/codex/run', { prompt: 'hi', sandbox: 'read-only', thread: null });
  assert.deepEqual([run.status, run.body.code], [502, 'codex-not-started']);
  const list = await get('/api/codex/threads');
  assert.deepEqual([list.status, list.body.code], [502, 'codex-not-started']);
  const down = (await until(stream, 'bridge/appServer')).find((e) => e.method === 'bridge/appServer');
  assert.deepEqual(down.params, { up: false });
  // The Agents board shows why Aster is offline.
  const agents = await get('/api/agents');
  assert.equal(agents.body.agents[1].note, 'Codex did not start');
  for (const text of [res.text, run.text, list.text, stream.text(), agents.text]) {
    assert.ok(!text.includes('no-codex') && !text.includes('dash-nocodex'), text);
  }
});

test('a Codex that exits at once answers 200 not started', async (t) => {
  const { get } = await startServer(t, { env: { FAKE_CODEX_EXIT: '1' } });
  const res = await get('/api/codex');
  assert.deepEqual([res.status, res.body.up, res.body.code], [200, false, 'codex-not-started']);
});

test('GET /api/codex/threads: every thread with the contract\'s fields, where it works and its state, names and previews masked', async (t) => {
  const { get } = await startServer(t);
  const res = await get('/api/codex/threads');
  assert.equal(res.status, 200);
  const { threads } = res.body;
  assert.deepEqual(threads.map((th) => [th.id, th.inDev, th.state]), [['t-dev', true, 'idle'], ['t-other', false, 'idle'], ['t-error', true, 'error']]);
  for (const th of threads) assert.deepEqual(Object.keys(th).sort(), [...THREAD_FIELDS].sort());
  assert.deepEqual([threads[0].name, threads[0].createdAt, threads[0].updatedAt], [`Dev root work: rotate ${MASK}`, 1790000000, 1790000300]);
  assert.equal(threads[0].preview, `deploy with OPENAI_API_KEY=${MASK}`);
  // The Agents board shows Aster's threads by their names, or their previews.
  const agents = await get('/api/agents');
  assert.equal(agents.status, 200);
  assert.equal(agents.body.agents[1].sessions[0].title, `Dev root work: rotate ${MASK}`);
  for (const text of [res.text, agents.text]) assert.ok(!text.includes('sk-proj-'), text);
});

test('GET /api/codex/threads/<id>: the thread and its turns, masked before they are cut; an unknown id is not-found', async (t) => {
  const { get } = await startServer(t);
  const res = await get('/api/codex/threads/t-dev');
  assert.equal(res.status, 200);
  assert.deepEqual(Object.keys(res.body).sort(), [...THREAD_FIELDS, 'turns'].sort());
  assert.equal(res.body.name, `Dev root work: rotate ${MASK}`);
  assert.deepEqual(res.body.turns.map((turn) => turn.id), ['turn-1', 'turn-2']);
  const [env, long, straddle, answer] = [res.body.turns[0].items[1], ...res.body.turns[1].items];
  assert.equal(env.aggregatedOutput, `LANG=en_GB.UTF-8\nOPENAI_API_KEY=${MASK}\n`);
  // Command output keeps its end, where a test or build summary sits; other long text keeps its start.
  assert.equal(long.aggregatedOutput, `…${'a line of test output\n'.repeat(500).slice(-3999)}`);
  assert.ok(straddle.aggregatedOutput.startsWith(MASK), 'the key is masked whole before the text is cut');
  assert.equal(answer.text, `${'a long answer\n'.repeat(400).slice(0, 3999)}…`);
  assert.ok(!res.text.includes('sk-proj-') && !res.text.includes('abcdefghij'));
  const missing = await get('/api/codex/threads/nope');
  assert.deepEqual([missing.status, missing.body.code], [404, 'not-found']);
  assert.equal(typeof missing.body.error, 'string');
});

test('codex: a thread this server just started is read again once', async (t) => {
  const reads = join(mkdtempSync(join(tmpdir(), 'dash-reads-')), 'reads.txt');
  const s = await startServer(t, { env: { FAKE_CODEX_NEW_LAG: '1', FAKE_CODEX_READS_TO: reads } });
  const { thread } = JSON.parse((await s.post('/api/codex/run', { prompt: 'hello', sandbox: 'read-only', thread: null })).text);
  const res = await s.get(`/api/codex/threads/${encodeURIComponent(thread)}`);
  assert.equal(res.status, 200);
  assert.deepEqual(readFileSync(reads, 'utf8').trim().split('\n'), [thread, thread]);
});

test('codex: a thread this server did not start is not read again', async (t) => {
  const reads = join(mkdtempSync(join(tmpdir(), 'dash-reads-')), 'reads.txt');
  const s = await startServer(t, { env: { FAKE_CODEX_READS_TO: reads } });
  const res = await s.get('/api/codex/threads/t-unknown');
  assert.equal(res.status, 404);
  assert.equal(JSON.parse(res.text).code, 'not-found');
  assert.deepEqual(readFileSync(reads, 'utf8').trim().split('\n'), ['t-unknown']);
});

test('codex: a thread-read error other than "no such thread" is codex-error, not not-found', async (t) => {
  const s = await startServer(t, { env: { FAKE_CODEX_READ_ERROR: '1' } });
  const res = await s.get('/api/codex/threads/t-dev');
  assert.equal(res.status, 502);
  assert.deepEqual(JSON.parse(res.text), { error: 'Codex answered with an error', code: 'codex-error' });
});

test('codex: an id that cannot be a thread is not-found, in Codex\'s other words', async (t) => {
  const s = await startServer(t);
  const res = await s.get(`/api/codex/threads/${encodeURIComponent('not a thread')}`);
  assert.equal(res.status, 404);
  assert.equal(JSON.parse(res.text).code, 'not-found');
});

test('POST /api/codex/run starts a read-only thread, Stop ends its turn, and a foreign turn or a second prompt is refused', async (t) => {
  const { post } = await startServer(t, { env: { FAKE_CODEX_TURN_MS: '10000' } });
  const run = await post('/api/codex/run', { prompt: 'hello', sandbox: 'read-only', thread: null });
  assert.equal(run.status, 200);
  assert.deepEqual(Object.keys(run.body).sort(), ['thread', 'turn']);
  const again = await post('/api/codex/run', { prompt: 'again', sandbox: 'read-only', thread: run.body.thread });
  assert.deepEqual([again.status, again.body.code], [409, 'thread-busy']);
  const foreign = await post('/api/codex/stop', { thread: run.body.thread, turn: 'turn-made-up' });
  assert.deepEqual([foreign.status, foreign.body.code], [404, 'unknown-turn']);
  const stop = await post('/api/codex/stop', run.body);
  assert.deepEqual([stop.status, stop.body], [200, { ok: true }]);
});

test('a run\'s thread names its turn, in the list and the view, until Codex reports it complete; then null', async (t) => {
  const { port, get, post } = await startServer(t, { env: { FAKE_CODEX_TURN_MS: '1500' } });
  const stream = await openEvents(t, port);
  const run = await post('/api/codex/run', { prompt: 'hello', sandbox: 'read-only', thread: null });
  assert.equal(run.status, 200);
  const turnNow = async () => [
    (await get('/api/codex/threads')).body.threads.find((th) => th.id === run.body.thread).turn,
    (await get(`/api/codex/threads/${run.body.thread}`)).body.turn,
  ];
  assert.deepEqual(await turnNow(), [run.body.turn, run.body.turn]);
  await until(stream, 'turn/completed');
  assert.deepEqual(await turnNow(), [null, null]);
  assert.equal((await get('/api/codex/threads/t-dev')).body.turn, null);
});

test('a value nested too deep to mask blanks its event and fails only that thread\'s view, with a code', async (t) => {
  const { port, get, post } = await startServer(t, { env: { FAKE_CODEX_DEEP: '1' } });
  const stream = await openEvents(t, port);
  const view = await get('/api/codex/threads/t-dev');
  assert.deepEqual([view.status, view.body], [500, { error: 'internal error', code: 'internal' }]);
  const run = await post('/api/codex/run', { prompt: 'hello', sandbox: 'read-only', thread: null });
  assert.equal(run.status, 200);
  const events = await until(stream, 'turn/completed');
  assert.ok(events.some((e) => e.method === 'item/completed' && e.params === null), stream.text().slice(0, 2000));
  assert.equal((await get('/api/codex')).status, 200, 'the server still answers');
});

test('a Codex named by CODEX_CMD starts without the npm launcher\'s variables, even with an npm shim first on PATH', async (t) => {
  // The shim and codex.exe findCodex would pick; empty files, since nothing may start them.
  const npm = mkdtempSync(join(tmpdir(), 'dash-npm-'));
  writeFileSync(join(npm, 'codex.cmd'), '');
  for (const triple of ['x86_64-pc-windows-msvc', 'aarch64-pc-windows-msvc']) {
    const bin = join(npm, 'node_modules', '@openai', 'codex', 'vendor', triple, 'bin');
    mkdirSync(bin, { recursive: true });
    writeFileSync(join(bin, 'codex.exe'), '');
  }
  const file = join(npm, 'env.json');
  // Node passes the first of PATH and Path on Windows, so PATH wins; undefined drops a variable.
  const { get } = await startServer(t, { env: { PATH: `${npm}${delimiter}${process.env.PATH}`, FAKE_CODEX_ENV_TO: file,
    CODEX_MANAGED_PACKAGE_ROOT: undefined, CODEX_MANAGED_BY_NPM: undefined } });
  assert.equal((await get('/api/codex')).body.up, true);
  assert.deepEqual(JSON.parse(readFileSync(file, 'utf8')), {});
});

test('workspace-write runs only in the dev root: elsewhere 403 naming no folder; full access 400; a foreign Origin 403', async (t) => {
  const { post } = await startServer(t);
  const outside = await post('/api/codex/run', { prompt: 'edit', sandbox: 'workspace-write', thread: 't-other' });
  assert.deepEqual([outside.status, outside.body.code], [403, 'write-outside-dev']);
  assert.ok(!outside.body.error.includes(DEVARNESS_ROOT) && !outside.text.includes('elsewhere-project'), outside.text);
  const full = await post('/api/codex/run', { prompt: 'edit', sandbox: 'danger-full-access', thread: null });
  assert.deepEqual([full.status, full.body.code], [400, 'bad-request']);
  const evil = await post('/api/codex/run', { prompt: 'edit', sandbox: 'read-only', thread: null }, 'http://evil.example');
  assert.deepEqual([evil.status, evil.body.code], [403, 'forbidden']);
  const inDev = await post('/api/codex/run', { prompt: 'edit', sandbox: 'workspace-write', thread: 't-dev' });
  assert.equal(inDev.status, 200, inDev.text);
});

test('GET /api/codex/events streams a run\'s items before its end, every event masked', async (t) => {
  const { port, post } = await startServer(t);
  const stream = await openEvents(t, port);
  assert.deepEqual([stream.res.statusCode, stream.res.headers['content-type'], stream.res.headers['cache-control']],
    [200, 'text/event-stream; charset=utf-8', 'no-store']);
  const run = await post('/api/codex/run', { prompt: 'hello', sandbox: 'read-only', thread: null });
  assert.equal(run.status, 200);
  const methods = (await until(stream, 'turn/completed')).map((e) => e.method);
  assert.ok(methods.indexOf('item/completed') !== -1 && methods.indexOf('item/completed') < methods.indexOf('turn/completed'), methods.join());
  assert.ok(stream.text().includes(`Bearer ${MASK}`));
  assert.ok(!stream.text().includes('abcdefghijkl'));
});

// ECC review of wave 2, 2026-10-10: one event past the response's 16 KB buffer dropped a page that reads.
test('an event over 16 KB reaches a page that reads it, and the stream stays open', async (t) => {
  const { port, post } = await startServer(t, { env: { FAKE_CODEX_FILES: '8' } });
  const stream = await openEvents(t, port);
  assert.equal((await post('/api/codex/run', { prompt: 'edit', sandbox: 'read-only', thread: null })).status, 200);
  const events = await until(stream, 'turn/completed');
  const item = events.find((e) => e.params?.item?.type === 'fileChange')?.params.item;
  assert.equal(item?.changes.length, 8, stream.text().slice(0, 500));
  assert.ok(JSON.stringify(item).length > 30_000);
  assert.equal(stream.closed(), false);
});

test('a page that stops reading is dropped once a megabyte waits for it, and gets no later event', async (t) => {
  // Three turns, each with an event of about 2 MB. Windows takes the first two
  // writes whole however big; the third waits, and the next event drops the stream.
  const { port, post } = await startServer(t, { env: { FAKE_CODEX_FILES: '520' } });
  const stream = await openEvents(t, port);
  stream.res.pause();
  let run;
  for (let i = 0; i < 3; i++) {
    run = await post('/api/codex/run', { prompt: 'edit', sandbox: 'read-only', thread: null });
    assert.equal(run.status, 200);
  }
  await sleep(1000); // each turn completes after 200 ms
  stream.res.resume();
  for (const end = Date.now() + 10_000; !stream.closed() && Date.now() < end;) await sleep(20);
  assert.equal(stream.closed(), true);
  assert.ok(!stream.events().some((e) => e.method === 'turn/completed' && e.params.turn.id === run.body.turn));
});

test('the event stream never names a thread\'s session file', async (t) => {
  const sessions = mkdtempSync(join(tmpdir(), 'dash-sessions-'));
  const { port, post } = await startServer(t, { command: [process.execPath, FAKE, '--sessions', sessions] });
  const stream = await openEvents(t, port);
  assert.equal((await post('/api/codex/run', { prompt: 'hello', sandbox: 'read-only', thread: null })).status, 200);
  const events = await until(stream, 'turn/completed');
  assert.ok(events.some((e) => e.method === 'thread/started' && e.params?.thread?.id), stream.text());
  assert.ok(!stream.text().includes('"path"') && !stream.text().includes(sessions.split(/[\\/]/).pop()), stream.text());
});

test('POST /api/codex/login answers an https sign-in address only', async (t) => {
  const { post } = await startServer(t);
  const res = await post('/api/codex/login', {});
  assert.deepEqual([res.status, res.body], [200, { authUrl: 'https://auth.openai.com/oauth/authorize?fake=1' }]);
});

test('POST /api/codex/login refuses an http sign-in address with bad-sign-in', async (t) => {
  const { post } = await startServer(t, { env: { FAKE_CODEX_BAD_LOGIN: '1' } });
  const res = await post('/api/codex/login', {});
  assert.deepEqual([res.status, res.body.code], [502, 'bad-sign-in']);
  assert.ok(!res.text.includes('http://auth'));
});

test('GET /api/taskboard says whether anything answers on the taskboard\'s port', async (t) => {
  // A port that was free a moment ago, then the taskboard's stand-in on it.
  const board = http.createServer((req, res) => res.end('taskboard'));
  await new Promise((done) => board.listen(0, '127.0.0.1', done));
  const port = board.address().port;
  await new Promise((done) => board.close(done));
  const { get } = await startServer(t, { env: { DEVARNESS_TASKBOARD_PORT: String(port) } });
  const url = `http://127.0.0.1:${port}`;
  assert.deepEqual((await get('/api/taskboard')).body, { running: false, url });
  await new Promise((done) => board.listen(port, '127.0.0.1', done));
  t.after(() => board.close());
  assert.deepEqual((await get('/api/taskboard')).body, { running: true, url });
});

test('GET /api/taskboard names the taskboard\'s own port by default', async (t) => {
  const { get } = await startServer(t);
  const res = await get('/api/taskboard');
  assert.deepEqual([res.status, res.body.url, typeof res.body.running], [200, 'http://127.0.0.1:47823', 'boolean']);
});

// Aster's review of wave 2, 2026-10-10: findings 6, 7, 8 (Stop's fields) and 9.

test('a timeout before a turn is sent does not hold the thread', async (t) => {
  const { post } = await startServer(t, { env: { FAKE_CODEX_SILENT: 'thread/read', CODEX_BRIDGE_TIMEOUT_MS: '300' } });
  for (let i = 0; i < 2; i++) {
    const run = await post('/api/codex/run', { prompt: 'hi', sandbox: 'read-only', thread: 't-dev' });
    assert.deepEqual([run.status, run.body.code], [504, 'codex-timeout'], run.text); // never thread-busy
  }
});

test('an app-server that answers nothing is ended after two timeouts in a row, and the next call starts a new one', async (t) => {
  const starts = join(mkdtempSync(join(tmpdir(), 'dash-starts-')), 'starts.txt');
  const { get } = await startServer(t, { env: {
    FAKE_CODEX_SILENT: 'account/read,account/rateLimits/read', FAKE_CODEX_STARTS_TO: starts, CODEX_BRIDGE_TIMEOUT_MS: '300' } });
  assert.equal((await get('/api/codex')).body.code, 'codex-not-started');
  await sleep(500); // the ended app-server's close reaches the server
  await get('/api/codex');
  assert.equal(readFileSync(starts, 'utf8').split('\n').filter(Boolean).length, 2);
});

test('Stop with a missing or wrong field is a bad request, not an unknown turn', async (t) => {
  const { post } = await startServer(t);
  for (const body of [{}, { thread: 't-dev' }, { thread: 7, turn: 'x' }, { thread: 't-dev', turn: '' }]) {
    const res = await post('/api/codex/stop', body);
    assert.deepEqual([res.status, res.body.code], [400, 'bad-request'], res.text);
  }
});

test('the taskboard probe hangs up once the board answers, even when the board keeps sending', async (t) => {
  let closed = false;
  const board = http.createServer((req, res) => {
    res.writeHead(200);
    const tick = setInterval(() => res.write('x'), 50);
    res.on('close', () => { clearInterval(tick); closed = true; });
  });
  await new Promise((done) => board.listen(0, '127.0.0.1', done));
  t.after(() => { board.closeAllConnections(); board.close(); });
  const { get } = await startServer(t, { env: { DEVARNESS_TASKBOARD_PORT: String(board.address().port) } });
  assert.equal((await get('/api/taskboard')).body.running, true);
  await sleep(300);
  assert.equal(closed, true);
});
