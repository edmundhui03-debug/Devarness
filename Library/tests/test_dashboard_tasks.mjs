import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { request as httpRequest } from 'node:http';
import { tmpdir } from 'node:os';
import { basename, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { lastCommits, launchedAt, parseLedger, readIndex, readRuns, readTasks } from '../dashboard/server/tasks.mjs';

const HERE = fileURLToPath(new URL('.', import.meta.url));
const FAKE_MD_FORMAT = join(HERE, 'fixtures', 'fake-md-format.cjs');
const NOW = Date.parse('2026-10-14T10:00:00Z'); // 18:00 in Hong Kong
const KEEP_ENV = ['PATH', 'SYSTEMROOT', 'USERPROFILE', 'HOME', 'TEMP', 'TMP'];
// A small environment of its own for each child, never the whole one (LESSONS.md:460).
const smallEnv = () => Object.fromEntries(KEEP_ENV.filter((k) => process.env[k]).map((k) => [k, process.env[k]]));

const LEDGER = [
  '| Launched | Session | Task | Agent, model | Budget | Output | Status | Spend | Checked |',
  '| --- | --- | --- | --- | --- | --- | --- | --- | --- |',
  '| 2026-10-14 13:00 | `aaaa` | Five hours old | one Opus agent | 0.4M | out | running | | |',
  '| 2026-10-14 11:00 | `bbbb` | Seven hours old | one Sonnet agent | 0.2M | out | running; awaiting seal | | |',
  '',
  '| 2026-10-14 09:00 | `cccc` | Finished | one Opus agent | 0.1M | out | done | 0.1M | yes |',
  '| 2026-10-14 08:00 UTC | `dddd` | A \\| B, escaped | one agent | 1M | out | running',
  '| 2026-10-14 08:00 | `eeee` | Too few cells | agent |',
  '| 2026-10-11 (launch clock not captured) | `ffff` | No time | agent | 1M | out | running | | |',
].join('\n');

test('tasks: a launch time is read in each form the ledger uses', () => {
  const cases = {
    '2026-10-13 11:06': '2026-10-13T03:06:00.000Z', // Hong Kong, the ledger's clock
    '2026-10-13 10:00:00 (pre-launch clock)': '2026-10-13T02:00:00.000Z',
    '2026-10-13 23:12:22 UTC+8 (pre-launch clock)': '2026-10-13T15:12:22.000Z',
    '2026-10-13 23:58:32 UTC (pre-launch clock)': '2026-10-13T23:58:32.000Z',
    '2026-10-13 10:00:00 (pre-launch UTC+9 clock)': '2026-10-13T01:00:00.000Z',
    '2026-10-13 10:00:00 HKT': '2026-10-13T02:00:00.000Z',
  };
  for (const [cell, iso] of Object.entries(cases)) assert.equal(launchedAt(cell), iso, cell);
  assert.equal(launchedAt('2026-10-11 (launch clock not captured)'), null);
  assert.equal(launchedAt('yesterday evening'), null);
});

test('tasks: only running rows are kept, each with its age', () => {
  const runs = parseLedger(LEDGER, NOW);
  assert.deepEqual(runs.map((r) => [r.session, r.task, r.stale]), [
    ['`aaaa`', 'Five hours old', false],
    ['`bbbb`', 'Seven hours old', true],
    ['`dddd`', 'A | B, escaped', false], // UTC, two hours old; the row has no closing pipe
    ['`ffff`', 'No time', false],        // no time: never called stale
  ]);
  assert.deepEqual(runs[0], {
    launched: '2026-10-14 13:00', at: '2026-10-14T05:00:00.000Z', session: '`aaaa`',
    task: 'Five hours old', agent: 'one Opus agent', budget: '0.4M', stale: false,
  });
  assert.equal(runs[3].at, null);
});

// A temporary dev root: the fake md-format, its mode, and a ledger unless null.
function fakeRoot(t, mode, ledger = LEDGER) {
  const root = mkdtempSync(join(tmpdir(), 'dash-tasks-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  mkdirSync(join(root, 'Library', 'bin'), { recursive: true });
  copyFileSync(FAKE_MD_FORMAT, join(root, 'Library', 'bin', 'md-format'));
  writeFileSync(join(root, 'fake-index.txt'), mode);
  if (ledger !== null) {
    mkdirSync(join(root, 'Setup'));
    writeFileSync(join(root, 'Setup', 'AGENT_LEDGER.md'), ledger);
  }
  return root;
}
const git = (cwd, ...args) => execFileSync('git', ['-c', 'user.name=t', '-c', 'user.email=t@example.invalid', ...args],
  { cwd, env: smallEnv(), windowsHide: true, stdio: 'ignore' });
function commit(repo, file, message) {
  mkdirSync(join(repo, file, '..'), { recursive: true });
  writeFileSync(join(repo, file), `# ${message}\n`);
  git(repo, 'add', file);
  git(repo, 'commit', '-q', '-m', message);
}

test('tasks: the index comes from md-format, its four fields only, bad entries dropped', async (t) => {
  const index = await readIndex(fakeRoot(t, 'junk'), process.execPath);
  assert.equal(index.code, 'ok');
  assert.deepEqual(index.sections, [
    { status: 'needs-owner', file: 'Setup/a.md', line: 7, heading: 'The owner picks a colour' },
    { status: 'open', file: 'Projects/demo/docs/b.md', line: 12, heading: 'The icon is open' },
    { status: 'fixed', file: 'README.md', line: 3, heading: 'Done' },
  ]);
  assert.deepEqual(index.titles, { 'Setup/a.md': 'A', 'Projects/demo/docs/b.md': 'B', 'README.md': 'dev' });
});

test('tasks: no Python, or one that is not there, is told apart from a failed index', async (t) => {
  const root = fakeRoot(t, 'ok');
  assert.deepEqual(await readIndex(root, null), { code: 'tasks-no-python' });
  assert.deepEqual(await readIndex(root, join(root, 'no-python.exe')), { code: 'tasks-no-python' });
});

test('tasks: a crash, garbage or a hang is a failed index', async (t) => {
  for (const mode of ['fail', 'garbage', 'hang']) {
    assert.deepEqual(await readIndex(fakeRoot(t, mode), process.execPath, 500), { code: 'tasks-index-failed' }, mode);
  }
});

test('tasks: without Python the runs are still read, and a missing ledger is no runs', async (t) => {
  const tasks = await readTasks(fakeRoot(t, 'ok'), null);
  assert.equal(tasks.code, 'tasks-no-python');
  assert.deepEqual([tasks.sections, tasks.titles], [[], {}]);
  assert.equal(tasks.runs.length, 4);
  assert.deepEqual(await readRuns(fakeRoot(t, 'ok', null)), []);
});

test('tasks: a document\'s last three commits come from the repository that holds it', async (t) => {
  const root = fakeRoot(t, 'ok');
  git(root, 'init', '-q');
  for (const n of [1, 2, 3, 4]) commit(root, 'Setup/a.md', `Edit A ${n}`);
  const commits = await lastCommits(root, 'Setup/a.md');
  assert.deepEqual(commits.map((c) => c.subject), ['Edit A 4', 'Edit A 3', 'Edit A 2']);
  assert.match(commits[0].hash, /^[0-9a-f]{7,}$/);
  assert.ok(!Number.isNaN(Date.parse(commits[0].at)));
  const project = join(root, 'Projects', 'demo');
  mkdirSync(project, { recursive: true });
  git(project, 'init', '-q');
  commit(project, 'docs/b.md', 'Add B');
  assert.deepEqual((await lastCommits(root, 'Projects/demo/docs/b.md')).map((c) => c.subject), ['Add B']);
});

test('tasks: a document name is a literal path, never a glob', async (t) => {
  const root = fakeRoot(t, 'ok');
  git(root, 'init', '-q');
  commit(root, 'Setup/a.md', 'Add a');
  commit(root, 'Setup/[a].md', 'Add [a]');
  assert.deepEqual((await lastCommits(root, 'Setup/[a].md')).map((c) => c.subject), ['Add [a]']);
});

test('tasks: git outside any repository is git-failed', async (t) => {
  await assert.rejects(lastCommits(fakeRoot(t, 'ok'), 'Setup/AGENT_LEDGER.md'), { status: 502, code: 'git-failed' });
});

const SERVER = join(HERE, '..', 'dashboard', 'server', 'server.mjs');

function request(port, method, path, headers = {}, body) {
  return new Promise((done, fail) => {
    const req = httpRequest({ host: '127.0.0.1', port, method, path, headers }, (res) => {
      let text = '';
      res.on('data', (c) => { text += c; });
      res.on('end', () => done({ status: res.statusCode, text }));
    });
    req.on('error', fail);
    if (body !== undefined) req.write(body);
    req.end();
  });
}

// The server on port 0 against `root`, with DEVARNESS_PYTHON set to node (the fake
// md-format is JavaScript) unless the test passes python: null.
async function startServer(t, root, { python = process.execPath } = {}) {
  const env = smallEnv();
  if (python) env.DEVARNESS_PYTHON = python;
  env.CODEX_CMD = JSON.stringify([join(root, 'no-codex.exe')]);
  const child = spawn(process.execPath, [SERVER, '--port', '0', '--root', root, '--home', root,
    '--questions', join(root, 'questions.json'), '--dist', join(root, 'dist')], { env, windowsHide: true });
  t.after(() => child.kill());
  return new Promise((done, fail) => {
    let out = '';
    child.stdout.on('data', (c) => { out += c; const m = /http:\/\/127\.0\.0\.1:(\d+)/.exec(out); if (m) done(Number(m[1])); });
    child.on('exit', (code) => fail(new Error(`server exited ${code}: ${out}`)));
  });
}

test('tasks route: the index, the titles and the running rows in one answer', async (t) => {
  const port = await startServer(t, fakeRoot(t, 'ok'));
  const res = await request(port, 'GET', '/api/tasks');
  assert.equal(res.status, 200);
  const body = JSON.parse(res.text);
  assert.equal(body.code, 'ok');
  assert.deepEqual(body.sections.map((s) => s.file), ['Setup/a.md', 'Projects/demo/docs/b.md', 'README.md']);
  assert.equal(body.titles['Setup/a.md'], 'A');
  assert.equal(body.runs.length, 4);
  assert.ok(!Number.isNaN(Date.parse(body.at)));
});

test('tasks route: without Python it still answers 200, with the runs and the code', async (t) => {
  const port = await startServer(t, fakeRoot(t, 'ok'), { python: null });
  const body = JSON.parse((await request(port, 'GET', '/api/tasks')).text);
  assert.deepEqual([body.code, body.sections, body.runs.length], ['tasks-no-python', [], 4]);
});

test('tasks route: a failed index answers its code and names no path', async (t) => {
  const root = fakeRoot(t, 'fail');
  const res = await request(await startServer(t, root), 'GET', '/api/tasks');
  assert.equal(JSON.parse(res.text).code, 'tasks-index-failed');
  // basename: JSON doubles a Windows path's backslashes, so the whole root would never match.
  assert.ok(!res.text.includes(basename(root)) && !res.text.includes('Traceback'));
});

test('tasks route: commits only for a document the index lists', async (t) => {
  const root = fakeRoot(t, 'ok');
  git(root, 'init', '-q');
  commit(root, 'Setup/a.md', 'Edit A 1');
  const port = await startServer(t, root);
  const ok = await request(port, 'GET', '/api/tasks/commits?file=Setup%2Fa.md');
  assert.equal(ok.status, 200);
  assert.deepEqual(JSON.parse(ok.text).commits.map((c) => c.subject), ['Edit A 1']);
  for (const file of ['../../secret.md', '-p', '--output=x', 'Setup/none.md', '']) {
    const res = await request(port, 'GET', `/api/tasks/commits?file=${encodeURIComponent(file)}`);
    assert.equal(res.status, 404, file);
    assert.equal(JSON.parse(res.text).code, 'unknown-file');
    assert.ok(!res.text.includes(basename(root)), file);
  }
});

test('tasks route: the Host rule and the cross-site refusal hold, and nothing is written', async (t) => {
  const port = await startServer(t, fakeRoot(t, 'ok'));
  assert.equal((await request(port, 'GET', '/api/tasks', { Host: `localhost:${port}` })).status, 403);
  assert.equal((await request(port, 'GET', '/api/tasks', { 'Sec-Fetch-Site': 'cross-site' })).status, 403);
  const post = await request(port, 'POST', '/api/tasks', { Origin: `http://127.0.0.1:${port}`, 'Content-Type': 'application/json' }, '{}');
  assert.equal(post.status, 404);
});
