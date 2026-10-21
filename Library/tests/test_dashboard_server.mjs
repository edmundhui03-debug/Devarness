// Tests for Library/dashboard/server: the questions store, the agent
// readers and the HTTP server. Usage: node --test test_dashboard_server.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { chmodSync, existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { answerQuestion, readQuestions, validateQuestions } from '../dashboard/server/questions.mjs';

// A small environment of its own for each child, never a copy of the whole one (LESSONS.md:460).
const KEEP_ENV = ['PATH', 'SYSTEMROOT', 'USERPROFILE', 'HOME', 'TEMP', 'TMP'];
const smallEnv = (extra) => ({ ...Object.fromEntries(KEEP_ENV.filter((k) => process.env[k]).map((k) => [k, process.env[k]])), ...extra });

const question = (id, extra = {}) => ({
  id, project: 'Library', task: 'Wave 1', asked_by: 'May', asked_at: '2026-10-09T10:00:00+08:00',
  question: 'Which port?', status: 'open', answer: '', answered_at: '', used_by: '', used_at: '', used_note: '',
  ...extra,
});
function mailbox(questions) {
  const dir = mkdtempSync(join(tmpdir(), 'dash-q-'));
  const path = join(dir, 'questions.json');
  writeFileSync(path, JSON.stringify({ version: 1, questions }, null, 2) + '\n');
  return path;
}

test('validateQuestions names the first bad field, as the page does', () => {
  assert.equal(validateQuestions({ version: 1, questions: [question('q-1')] }), null);
  assert.equal(validateQuestions({ version: 2, questions: [] }), 'version');
  assert.equal(validateQuestions({ version: 1, questions: [question('q-1', { project: 'SAMPLE_FIRMWARE' })] }), 'questions[0].project');
  assert.equal(validateQuestions({ version: 1, questions: [question('q-1'), question('q-1')] }), 'questions[1].id');
});

test('an answer changes only status, answer and answered_at, and keeps an entry an agent just added', async () => {
  const path = mailbox([question('q-1')]);
  // An agent adds a question after the page loaded the file.
  const onDisk = JSON.parse(readFileSync(path, 'utf8'));
  onDisk.questions.push(question('q-2', { asked_by: 'Aster', question: 'New one?' }));
  writeFileSync(path, JSON.stringify(onDisk, null, 2) + '\n');
  const saved = await answerQuestion(path, 'q-1', '  Use 47900\n<b>now</b>  ', '2026-10-09T12:00:00.000Z');
  assert.equal(saved.answer, 'Use 47900\n<b>now</b>');
  const after = JSON.parse(readFileSync(path, 'utf8'));
  const expected = structuredClone(onDisk);
  Object.assign(expected.questions[0], { status: 'answered', answer: 'Use 47900\n<b>now</b>', answered_at: '2026-10-09T12:00:00.000Z' });
  assert.deepEqual(after, expected);
  assert.ok(readFileSync(path, 'utf8').endsWith('}\n'));
});

test('an empty answer, an unknown id, a used question and a broken file are refused without writing', async () => {
  const path = mailbox([question('q-1'), question('q-9', { status: 'used' })]);
  const before = readFileSync(path, 'utf8');
  await assert.rejects(answerQuestion(path, 'q-1', '   '), { status: 400 });
  await assert.rejects(answerQuestion(path, 'q-404', 'x'), { status: 404 });
  await assert.rejects(answerQuestion(path, 'q-9', 'x'), { status: 409 });
  assert.equal(readFileSync(path, 'utf8'), before);
  assert.ok(!existsSync(`${path}.lock`), 'a refusal still lets go of the lock');
  writeFileSync(path, '{"version": 1, "questions": [{"id": 3}]}');
  assert.throws(() => readQuestions(path), { status: 409 });
  await assert.rejects(answerQuestion(path, 'q-1', 'x'), { status: 409 });
});

test('a mailbox saved with a byte order mark is read and answered, and written back without one', async () => {
  // PowerShell 5.1 writes UTF-8 with a BOM.
  const bom = String.fromCodePoint(0xfeff);
  const path = mailbox([question('q-1')]);
  writeFileSync(path, bom + readFileSync(path, 'utf8'));
  assert.ok(readFileSync(path).subarray(0, 3).equals(Buffer.from([0xef, 0xbb, 0xbf])));
  assert.equal(readQuestions(path).questions[0].id, 'q-1');
  await answerQuestion(path, 'q-1', 'Yes');
  const text = readFileSync(path, 'utf8');
  assert.ok(!text.startsWith(bom));
  assert.equal(JSON.parse(text).questions[0].answer, 'Yes');
});

// The lock the server shares with `dashboard ask` and `dashboard used`.
test('an answer waits for the lock, so what another writer saves meanwhile is kept', async () => {
  const path = mailbox([question('q-1')]);
  // Another writer takes the lock and reads the file, as an agent's tools would.
  writeFileSync(`${path}.lock`, '999 2026-10-09T12:00:00+08:00');
  const theirs = JSON.parse(readFileSync(path, 'utf8'));
  const saving = answerQuestion(path, 'q-1', 'Yes', '2026-10-09T12:00:00.000Z');
  await sleep(200);
  // Seconds later it writes its question and lets go; only then may the answer land.
  theirs.questions.push(question('q-2', { asked_by: 'Aster' }));
  writeFileSync(path, JSON.stringify(theirs, null, 2) + '\n');
  rmSync(`${path}.lock`);
  assert.equal((await saving).status, 'answered');
  const after = JSON.parse(readFileSync(path, 'utf8'));
  assert.deepEqual(after.questions.map((q) => [q.id, q.status, q.answer]), [['q-1', 'answered', 'Yes'], ['q-2', 'open', '']]);
  assert.ok(!existsSync(`${path}.lock`));
});

test('a lock older than the stale age is broken, and one that never clears gives the busy error', async () => {
  const path = mailbox([question('q-1')]);
  const lock = `${path}.lock`;
  writeFileSync(lock, '999 left by a writer that stopped');
  utimesSync(lock, new Date(Date.now() - 60_000), new Date(Date.now() - 60_000));
  await answerQuestion(path, 'q-1', 'Yes');
  assert.equal(JSON.parse(readFileSync(path, 'utf8')).questions[0].answer, 'Yes');
  assert.ok(!existsSync(lock));
  writeFileSync(lock, '999 still at work');
  const before = readFileSync(path, 'utf8');
  const started = Date.now();
  await assert.rejects(answerQuestion(path, 'q-1', 'Again', undefined, { waitMs: 200 }),
    { status: 503, message: 'the mailbox is busy, try again' });
  assert.ok(Date.now() - started < 2000);
  assert.equal(readFileSync(path, 'utf8'), before);
  assert.equal(readFileSync(lock, 'utf8'), '999 still at work', 'another writer\'s lock is never removed');
});

const failure = (code, what) => Object.assign(new Error(`${code}: ${what}`), { code });

test('an answer holds its own lock from the read to the rename', async () => {
  const path = mailbox([question('q-1')]);
  const lock = `${path}.lock`;
  const holder = () => (existsSync(lock) ? fs.readFileSync(lock, 'utf8').split(' ')[0] : 'no lock');
  const seen = [];
  await stubbed('readFileSync', (real, file, ...rest) => {
    if (file === path) seen.push(['read', holder()]);
    return real(file, ...rest);
  }, () => stubbed('renameSync', (real, from, to) => {
    if (to === path) seen.push(['rename', holder()]);
    return real(from, to);
  }, () => answerQuestion(path, 'q-1', 'Yes')));
  assert.deepEqual(seen, [['read', String(process.pid)], ['rename', String(process.pid)]]);
});

test('a folder that refuses to create the lock is waited on to the bound, then busy, never spun', async () => {
  const path = mailbox([question('q-1')]);
  const before = readFileSync(path, 'utf8');
  let tries = 0;
  // Windows reports a folder that refuses file creation as EPERM, and no lock ever appears.
  const outcome = await stubbed('openSync', (real, file, ...rest) => {
    if (!String(file).endsWith('.lock')) return real(file, ...rest);
    // A guard, so a loop that never yields fails here instead of hanging the suite.
    if (++tries > 1000) throw failure('ESPUN', 'open without a pause');
    throw failure('EPERM', 'operation not permitted, open');
  }, () => answerQuestion(path, 'q-1', 'Yes', undefined, { waitMs: 200 }).then(() => 'saved', (err) => err.status ?? err.code));
  assert.equal(outcome, 503);
  assert.ok(tries < 50, `${tries} tries in 200 ms`);
  assert.equal(readFileSync(path, 'utf8'), before);
});

test('the wait for the lock ends at its bound when the wall clock steps back', async () => {
  const path = mailbox([question('q-1')]);
  writeFileSync(`${path}.lock`, '999 still at work');
  const realNow = Date.now;
  const saving = answerQuestion(path, 'q-1', 'Yes', undefined, { waitMs: 200 });
  Date.now = () => realNow() - 600_000; // an NTP step or a person sets the clock 10 minutes back
  let outcome;
  try {
    outcome = await Promise.race([saving.then(() => 'saved', (err) => err.status), sleep(3000).then(() => 'still waiting after 3 s')]);
  } finally {
    Date.now = realNow;
    rmSync(`${path}.lock`, { force: true });
    await saving.catch(() => {});
  }
  assert.equal(outcome, 503);
});

test('a rename a reader refuses is tried again under the lock, and the answer lands', async () => {
  const path = mailbox([question('q-1')]);
  let refused = 0;
  // On Windows a rename over a file another process has open, such as a `dashboard wait` poll, fails.
  await stubbed('renameSync', (real, from, to) => {
    if (to === path && refused < 3) { refused++; throw failure('EPERM', 'operation not permitted, rename'); }
    return real(from, to);
  }, () => answerQuestion(path, 'q-1', 'Yes'));
  assert.equal(refused, 3);
  assert.equal(JSON.parse(readFileSync(path, 'utf8')).questions[0].answer, 'Yes');
  assert.deepEqual(readdirSync(dirname(path)), ['questions.json']);
});

test('a rename refused through every retry answers busy, and leaves no scratch file or lock', async () => {
  const path = mailbox([question('q-1')]);
  const before = readFileSync(path, 'utf8');
  await stubbed('renameSync', (real, from, to) => {
    if (to === path) throw failure('EBUSY', 'resource busy or locked, rename');
    return real(from, to);
  }, () => assert.rejects(answerQuestion(path, 'q-1', 'Yes'), { status: 503, message: 'the mailbox is busy, try again' }));
  assert.equal(readFileSync(path, 'utf8'), before);
  assert.deepEqual(readdirSync(dirname(path)), ['questions.json']);
});

test('a writer whose lock another takes over never renames, so a save it reports is on disk', async () => {
  const path = mailbox([question('q-1')]);
  const before = readFileSync(path, 'utf8');
  const lock = `${path}.lock`;
  let refused = 0;
  // A reader refuses the first rename; meanwhile a wall-clock step makes another writer break the lock as stale and take it.
  const outcome = await stubbed('renameSync', (real, from, to) => {
    if (to === path && refused++ === 0) {
      writeFileSync(lock, '999 took it over');
      throw failure('EPERM', 'operation not permitted, rename');
    }
    return real(from, to);
  }, () => answerQuestion(path, 'q-1', 'Yes').then(() => 'saved', (err) => err.status ?? err.code));
  assert.equal(outcome, 503);
  assert.equal(readFileSync(path, 'utf8'), before);
  assert.equal(readFileSync(lock, 'utf8'), '999 took it over', 'the other writer\'s lock is left alone');
  assert.deepEqual(readdirSync(dirname(path)).sort(), ['questions.json', 'questions.json.lock']);
});

test('each answer writes its own scratch file, so two in one process never share one', async () => {
  const path = mailbox([question('q-1'), question('q-2')]);
  const names = [];
  await stubbed('writeFileSync', (real, target, ...rest) => {
    if (String(target).endsWith('.tmp')) names.push(String(target));
    return real(target, ...rest);
  }, async () => { await answerQuestion(path, 'q-1', 'A'); await answerQuestion(path, 'q-2', 'B'); });
  assert.equal(names.length, 2);
  assert.notEqual(names[0], names[1]);
});

test('a mailbox file marked read-only is refused at once, not answered busy', async () => {
  const path = mailbox([question('q-1')]);
  const before = readFileSync(path, 'utf8');
  let renames = 0;
  chmodSync(path, 0o444);
  try {
    // Windows refuses a rename over a read-only file for good; no reader is to blame.
    const outcome = await stubbed('renameSync', (real, from, to) => {
      if (to === path) { renames++; throw failure('EPERM', 'operation not permitted, rename'); }
      return real(from, to);
    }, () => answerQuestion(path, 'q-1', 'Yes').then(() => 'saved', (err) => err.status ?? err.code));
    assert.equal(outcome, 'EPERM');
    assert.equal(renames, 1, 'not retried');
  } finally { chmodSync(path, 0o644); }
  assert.equal(readFileSync(path, 'utf8'), before);
  assert.deepEqual(readdirSync(dirname(path)), ['questions.json']);
});

test('a process that ends while an answer waits on a rename leaves no lock or scratch file', () => {
  const path = mailbox([question('q-1')]);
  const child = join(mkdtempSync(join(tmpdir(), 'dash-ends-')), 'ends.mjs');
  // The server's own Ctrl+C handler calls process.exit, which may land while the rename is retried.
  writeFileSync(child, [
    "import fs from 'node:fs';",
    "import { syncBuiltinESMExports } from 'node:module';",
    'const [path, module] = process.argv.slice(2);',
    'const real = fs.renameSync;',
    "fs.renameSync = (from, to) => { if (to === path) throw Object.assign(new Error('EPERM'), { code: 'EPERM' }); return real(from, to); };",
    'syncBuiltinESMExports();',
    'const { answerQuestion } = await import(module);',
    "answerQuestion(path, 'q-1', 'Yes').catch(() => {});",
    'setTimeout(() => process.exit(0), 300);',
  ].join('\n'));
  try {
    const run = spawnSync(process.execPath, [child, path, new URL('../dashboard/server/questions.mjs', import.meta.url).href],
      { encoding: 'utf8', timeout: 10000, env: smallEnv(), windowsHide: true });
    assert.equal(run.status, 0, run.stderr);
  } finally { rmSync(child, { force: true }); }
  assert.deepEqual(readdirSync(dirname(path)), ['questions.json']);
});

test('a token write that fails lets go of the lock it just made', async () => {
  const path = mailbox([question('q-1')]);
  // The token goes to the new lock's descriptor; a full disk refuses it.
  await stubbed('writeFileSync', (real, target, ...rest) => {
    if (typeof target === 'number') throw failure('ENOSPC', 'no space left on device, write');
    return real(target, ...rest);
  }, () => assert.rejects(answerQuestion(path, 'q-1', 'Yes'), { code: 'ENOSPC' }));
  assert.ok(!existsSync(`${path}.lock`), 'the lock is let go');
  assert.equal((await answerQuestion(path, 'q-1', 'Yes', undefined, { waitMs: 300 })).status, 'answered');
});

test('a scratch write that fails part-way leaves no scratch file', async () => {
  const path = mailbox([question('q-1')]);
  const before = readFileSync(path, 'utf8');
  await stubbed('writeFileSync', (real, target, ...rest) => {
    if (!String(target).endsWith('.tmp')) return real(target, ...rest);
    real(target, '{"vers'); // made, then the disk fills
    throw failure('ENOSPC', 'no space left on device, write');
  }, () => assert.rejects(answerQuestion(path, 'q-1', 'Yes'), { code: 'ENOSPC' }));
  assert.equal(readFileSync(path, 'utf8'), before);
  assert.deepEqual(readdirSync(dirname(path)), ['questions.json']);
});

import fs, { mkdirSync, utimesSync } from 'node:fs';
import childProcess from 'node:child_process';
import { syncBuiltinESMExports } from 'node:module';
import { agents, claudeSessions, piStatus, sharedSnapshot } from '../dashboard/server/agents.mjs';
import { createCodex } from '../dashboard/server/codex.mjs';

// A fake home: one live Claude session (this test's own pid), one dead one,
// one broken file and a key file; Pi 1.0.4 with one session.
function fakeHome({ piFresh = true, piLast = { role: 'assistant', stopReason: 'toolUse' } } = {}) {
  const home = mkdtempSync(join(tmpdir(), 'dash-home-'));
  const sessions = join(home, '.claude', 'sessions');
  mkdirSync(sessions, { recursive: true });
  writeFileSync(join(sessions, `${process.pid}.json`), JSON.stringify({
    pid: process.pid, sessionId: 'claude-1', cwd: 'C:/dev', status: 'busy', name: 'dashboard work',
    statusUpdatedAt: Date.parse('2026-10-09T10:00:00Z'), entrypoint: 'cli' }));
  writeFileSync(join(sessions, '2147483646.json'), JSON.stringify({ pid: 2147483646, sessionId: 'gone', status: 'busy' }));
  writeFileSync(join(sessions, '77.json'), '{broken');
  // Valid registry JSON for a live pid, so only the file-name filter keeps it out.
  writeFileSync(join(sessions, `${process.pid}.abc.key`), JSON.stringify({
    pid: process.pid, sessionId: 'key-file-session', cwd: 'C:/key', status: 'busy' }));
  const pi = join(home, '.pi', 'agent');
  mkdirSync(join(pi, 'install'), { recursive: true });
  writeFileSync(join(pi, 'install', 'current-version'), '1.0.4\n');
  const folder = join(pi, 'sessions', '--C--dev--');
  mkdirSync(folder, { recursive: true });
  const file = join(folder, '2026-10-09T10-00-00_pi-1.jsonl');
  writeFileSync(file, [JSON.stringify({ type: 'session', version: 3 }), JSON.stringify({ type: 'message', message: piLast })].join('\n') + '\n');
  if (!piFresh) utimesSync(file, new Date('2026-10-01'), new Date('2026-10-01'));
  return home;
}

test('Claude sessions come from the live registry; dead, broken and key files are skipped', () => {
  const { ok, sessions } = claudeSessions(fakeHome());
  assert.equal(ok, true);
  assert.deepEqual(sessions.map((s) => [s.id, s.state, s.title]), [['claude-1', 'working', 'dashboard work']]);
  assert.ok(!JSON.stringify(sessions).includes('key-file-session'));
});

test('Pi is working only while its newest session changed lately and its turn is open', () => {
  assert.equal(piStatus(fakeHome()).sessions[0].state, 'working');
  assert.equal(piStatus(fakeHome({ piFresh: false })).sessions[0].state, 'idle');
  assert.equal(piStatus(fakeHome({ piLast: { role: 'assistant', stopReason: 'stop' } })).sessions[0].state, 'idle');
  assert.equal(piStatus(fakeHome()).version, '1.0.4');
  assert.equal(piStatus(mkdtempSync(join(tmpdir(), 'dash-empty-'))).ok, false);
});

test('agents: Aster from Codex, waiting when a question is open and nothing runs', async () => {
  const codex = { health: async () => ({ up: true }), signedIn: async () => true, listThreads: async () => [
    { id: 't1', name: null, preview: 'audit the library', source: 'exec', cwd: 'C:/dev', updatedAt: 1791000000, state: 'idle' }] };
  const questions = [question('q-1', { asked_by: 'Aster' }), question('q-2', { asked_by: 'May', status: 'answered' })];
  const [peter, aster, may] = await agents({ home: fakeHome(), codex, questions });
  assert.deepEqual([peter.name, peter.availability, peter.workload], ['Peter', 'online', 'working']);
  assert.deepEqual([aster.availability, aster.workload, aster.openQuestions], ['online', 'waiting', 1]);
  assert.equal(aster.sessions[0].title, 'audit the library');
  assert.equal(aster.sessions[0].updatedAt, new Date(1791000000 * 1000).toISOString());
  assert.deepEqual([may.client, may.workload, may.openQuestions], ['Pi', 'working', 0]);
});

test('agents: Codex down makes Aster offline without the error\'s path, and the others still show', async () => {
  const codex = { health: async () => ({ up: false, error: 'spawn C:\\tools\\codex.exe ENOENT' }), listThreads: async () => { throw new Error('never'); } };
  const list = await agents({ home: fakeHome(), codex, questions: [] });
  assert.deepEqual(list.map((a) => a.name), ['Peter', 'Aster', 'May']);
  assert.deepEqual([list[1].availability, list[1].note], ['offline', 'Codex did not start']);
});

// One bad source must never take down the other agents.
const okCodex = { health: async () => ({ up: true }), signedIn: async () => true, listThreads: async () => [] };
const claudeDir = (home) => join(home, '.claude', 'sessions');
const piFolder = (home) => join(home, '.pi', 'agent', 'sessions', '--C--dev--');

// Puts fake(real, ...args) in place of one fs function while `run` is going;
// the server modules see it through their named imports.
async function stubbed(fnName, fake, run) {
  const real = fs[fnName];
  fs[fnName] = (...args) => fake(real, ...args);
  syncBuiltinESMExports();
  try { return await run(); } finally { fs[fnName] = real; syncBuiltinESMExports(); }
}

// Makes one fs function fail for paths ending in `suffix` while `run` is going,
// the way a file deleted or locked between the directory scan and the read would.
function whileFailing(fnName, suffix, run) {
  return stubbed(fnName, (real, path, ...rest) => {
    if (String(path).endsWith(suffix)) throw Object.assign(new Error(`EBUSY: ${fnName} ${suffix}`), { code: 'EBUSY' });
    return real(path, ...rest);
  }, run);
}

test('a Pi session file that cannot be read leaves Peter and Aster showing and May answering', async () => {
  const home = fakeHome();
  const session = '2026-10-09T10-00-00_pi-1';
  // The read fails after the scan: that one session shows idle, nothing throws.
  const [peter, aster, may] = await whileFailing('openSync', `${session}.jsonl`,
    () => agents({ home, codex: okCodex, questions: [] }));
  assert.deepEqual([peter.availability, aster.availability, may.availability], ['online', 'online', 'online']);
  assert.deepEqual(may.sessions.map((s) => [s.id, s.state]), [[session, 'idle']]);
  // The file is gone before it is measured: only that entry drops, the other stays.
  writeFileSync(join(piFolder(home), 'gone.jsonl'), '{}\n');
  const { sessions } = await whileFailing('statSync', 'gone.jsonl', () => piStatus(home));
  assert.deepEqual(sessions.map((s) => [s.id, s.state]), [[session, 'working']]);
});

test('a registry file with a time Date cannot hold still lists the session, with no time', async () => {
  const home = fakeHome();
  writeFileSync(join(claudeDir(home), `${process.pid}.json`), JSON.stringify({
    pid: process.pid, sessionId: 'claude-1', cwd: 'C:/dev', status: 'busy', statusUpdatedAt: 1e20 }));
  const { sessions } = claudeSessions(home);
  assert.deepEqual(sessions.map((s) => [s.id, s.updatedAt]), [['claude-1', null]]);
  const [peter, aster, may] = await agents({ home, codex: okCodex, questions: [] });
  assert.deepEqual([peter.availability, aster.availability, may.availability], ['online', 'online', 'online']);
});

test('a reader that throws makes only its own agent offline, with the message as the note', async () => {
  // A BigInt clock makes piStatus throw while the other two readers are fine.
  const [peter, aster, may] = await agents({ home: fakeHome(), codex: okCodex, questions: [], now: 1n });
  assert.deepEqual([peter.availability, aster.availability, may.availability], ['online', 'online', 'offline']);
  assert.match(may.note, /BigInt/);
  // A home that is not a path makes both file readers throw; Codex still shows.
  const list = await agents({ home: null, codex: okCodex, questions: [] });
  assert.deepEqual(list.map((a) => a.availability), ['offline', 'online', 'offline']);
  assert.ok(list[0].note && list[2].note);
});

test('Codex failing makes Aster offline with a fixed sentence, never the error\'s own words, while Peter and May show', async () => {
  const healthFails = { health: async () => { throw new Error('health blew up'); }, listThreads: async () => [] };
  const listFails = { health: async () => ({ up: true }), signedIn: async () => true, listThreads: async () => { throw new Error('list blew up'); } };
  // An fs error quotes the file's path.
  const statFails = { health: async () => ({ up: true }), signedIn: async () => true,
    listThreads: async () => { throw new Error("EPERM: operation not permitted, stat 'D:\\profiles\\owner\\.codex\\sessions\\rollout-x.jsonl'"); } };
  for (const codex of [healthFails, listFails, statFails]) {
    const [peter, aster, may] = await agents({ home: fakeHome(), codex, questions: [] });
    assert.deepEqual([peter.availability, aster.availability, aster.note, may.availability], ['online', 'offline', 'Codex answered with an error', 'online']);
  }
});

test('a signed-out Codex makes Aster offline, and says so', async () => {
  const signedOut = { health: async () => ({ up: true }), signedIn: async () => false, listThreads: async () => [] };
  const [peter, aster, may] = await agents({ home: fakeHome(), codex: signedOut, questions: [] });
  assert.deepEqual([peter.availability, aster.availability, aster.note, may.availability], ['online', 'offline', 'Codex is not signed in', 'online']);
});

test('a Codex that never answers is cut off at the deadline', async () => {
  const hung = { health: () => new Promise(() => {}), listThreads: () => new Promise(() => {}) };
  // The deadline covers the sign-in check too, not only health.
  const hungSignIn = { health: async () => ({ up: true }), signedIn: () => new Promise(() => {}), listThreads: async () => [] };
  for (const codex of [hung, hungSignIn]) {
    const started = Date.now();
    const [peter, aster, may] = await agents({ home: fakeHome(), codex, questions: [], codexDeadlineMs: 30 });
    assert.ok(Date.now() - started < 2000);
    assert.deepEqual([peter.availability, aster.availability, may.availability], ['online', 'offline', 'online']);
    assert.match(aster.note, /^Codex did not answer within /);
  }
});

test('polls share one snapshot: two at once make one Codex call, and a finished one is reused briefly', async () => {
  let lists = 0;
  const codex = { health: async () => ({ up: true }), signedIn: async () => true, listThreads: async () => { lists++; return []; } };
  const home = fakeHome();
  const snapshot = sharedSnapshot(() => agents({ home, codex, questions: [] }), 100);
  const [first, second] = await Promise.all([snapshot(), snapshot()]);
  assert.equal(lists, 1);
  assert.equal(first, second);
  assert.equal(await snapshot(), first, 'reused while it is fresh');
  assert.equal(lists, 1);
  await sleep(150);
  await snapshot();
  assert.equal(lists, 2, 'read again once it is older than the reuse time');
});

test('a snapshot forgotten while it is being built is read afresh, and the late one never returns', async () => {
  const finish = [];
  // No reuse, so a finished time wrongly set by the late reading would start a third read.
  const snapshot = sharedSnapshot(() => new Promise((done) => finish.push(done)), 0);
  const first = snapshot();
  snapshot.forget(); // an answer is saved while the first reading is still being built
  const second = snapshot();
  assert.notEqual(second, first);
  assert.equal(finish.length, 2);
  finish[0]('first');
  await first;
  assert.equal(snapshot(), second, 'the late reading neither returns nor ends the newer one');
  assert.equal(finish.length, 2);
  finish[1]('second');
  assert.equal(await second, 'second');
});

test('a wall clock stepped back does not keep a finished snapshot past its reuse time', async () => {
  let reads = 0;
  const snapshot = sharedSnapshot(async () => ++reads, 50);
  await snapshot();
  const realNow = Date.now;
  Date.now = () => realNow() - 600_000; // an NTP step or a person sets the clock 10 minutes back
  try {
    await sleep(100);
    assert.equal(await snapshot(), 2);
  } finally { Date.now = realNow; }
});

// A fake `codex app-server` that logs each request's method and has an account
// only when started with `signed-in`.
const FAKE_CODEX = `
import { appendFileSync } from 'node:fs';
import { createInterface } from 'node:readline';
const account = process.argv.includes('signed-in') ? { type: 'chatgpt', planType: 'plus' } : null;
createInterface({ input: process.stdin }).on('line', (line) => {
  const msg = JSON.parse(line);
  if (msg.id === undefined) return;
  appendFileSync('calls.log', msg.method + '\\n');
  const result = msg.method === 'initialize' ? { userAgent: 'fake' } : msg.method === 'account/read' ? { account } : {};
  process.stdout.write(JSON.stringify({ id: msg.id, result }) + '\\n');
});
`;
function fakeCodex(...args) {
  const folder = mkdtempSync(join(tmpdir(), 'dash-codex-'));
  writeFileSync(join(folder, 'fake.mjs'), FAKE_CODEX);
  return { folder, codex: createCodex({ folder, command: [process.execPath, join(folder, 'fake.mjs'), ...args] }) };
}

test('signedIn asks Codex for the account only, never the quota', async () => {
  for (const [args, expected] of [[['signed-in'], true], [[], false]]) {
    const { folder, codex } = fakeCodex(...args);
    try {
      assert.equal(await codex.signedIn(), expected);
      assert.deepEqual(readFileSync(join(folder, 'calls.log'), 'utf8').trim().split('\n'), ['initialize', 'account/read']);
    } finally { codex.end(); }
  }
});

test('ending the app-server gives taskkill at most 5 s', { skip: process.platform !== 'win32' && 'taskkill runs on Windows only' }, async () => {
  const { codex } = fakeCodex();
  assert.equal((await codex.health()).up, true);
  const real = childProcess.spawnSync;
  let options;
  childProcess.spawnSync = (file, args, opts) => { options = opts; return real(file, args, opts); };
  syncBuiltinESMExports();
  try { codex.end(); } finally { childProcess.spawnSync = real; syncBuiltinESMExports(); }
  assert.deepEqual([options?.timeout, options?.windowsHide], [5000, true]);
});

test('a registry pid of 0 or below is skipped, and so is a history.jsonl in a Pi folder', () => {
  const home = fakeHome();
  writeFileSync(join(claudeDir(home), '0.json'), JSON.stringify({ pid: 0, sessionId: 'pid-zero', status: 'busy' }));
  writeFileSync(join(claudeDir(home), '5.json'), JSON.stringify({ pid: -1, sessionId: 'pid-negative', status: 'busy' }));
  assert.deepEqual(claudeSessions(home).sessions.map((s) => s.id), ['claude-1']);
  writeFileSync(join(piFolder(home), 'history.jsonl'), JSON.stringify({ type: 'message', message: { role: 'user' } }) + '\n');
  assert.deepEqual(piStatus(home).sessions.map((s) => s.id), ['2026-10-09T10-00-00_pi-1']);
});

import http from 'node:http';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { basename, dirname } from 'node:path';

const SERVER = fileURLToPath(new URL('../dashboard/server/server.mjs', import.meta.url));
const BESIDE_DIST = 'MARKER-BESIDE-DIST';

function request(port, method, path, { headers = {}, body } = {}) {
  return new Promise((done, fail) => {
    const req = http.request({ host: '127.0.0.1', port, method, path, headers: { Host: `127.0.0.1:${port}`, ...headers } }, (res) => {
      let text = '';
      res.setEncoding('utf8');
      res.on('data', (c) => { text += c; });
      res.on('end', () => done({ status: res.statusCode, headers: res.headers, text }));
    });
    req.on('error', fail);
    if (body !== undefined) req.write(body);
    req.end();
  });
}

async function startServer(t, { dist = true, args = [], home = fakeHome() } = {}) {
  const root = mkdtempSync(join(tmpdir(), 'dash-srv-'));
  const questions = mailbox([question('q-1')]);
  const distDir = join(root, 'dist');
  // A file beside the build, which no request may reach.
  writeFileSync(join(root, 'secret.txt'), BESIDE_DIST);
  if (dist) {
    mkdirSync(join(distDir, 'assets'), { recursive: true });
    writeFileSync(join(distDir, 'index.html'), '<!doctype html><title>dev</title>');
    writeFileSync(join(distDir, 'assets', 'app.js'), 'console.log(1)');
  }
  const child = spawn(process.execPath, [SERVER, '--port', '0', '--home', home, '--questions', questions, '--dist', distDir, ...args], {
    env: smallEnv({ CODEX_CMD: JSON.stringify([join(root, 'no-codex.exe')]) }), windowsHide: true,
  });
  t.after(() => child.kill());
  const port = await new Promise((done, fail) => {
    let out = '';
    child.stdout.on('data', (c) => { out += c; const m = /http:\/\/127\.0\.0\.1:(\d+)/.exec(out); if (m) done(Number(m[1])); });
    child.on('exit', (code) => fail(new Error(`server exited ${code}: ${out}`)));
  });
  return { root, port, questions, own: `http://127.0.0.1:${port}` };
}

// The .mjs suites only: the Python suites have their own guard, SmallEnvironmentTest in test_dashboard_tasks.py.
test('every child a dashboard .mjs test starts gets a small environment, never the whole one (LESSONS.md:460)', () => {
  const dir = dirname(fileURLToPath(import.meta.url));
  const found = [];
  for (const name of readdirSync(dir).filter((n) => /^test_dashboard.*\.mjs$/.test(n))) {
    const text = readFileSync(join(dir, name), 'utf8');
    const where = (at) => `${name}:${text.slice(0, at).split('\n').length}`;
    for (const m of text.matchAll(/\.\.\.process\.env(?![\w.[])/g)) found.push(`${where(m.index)} copies it`);
    // A call with no env option inherits everything; its text runs to the matching parenthesis.
    for (const m of text.matchAll(/\b(?:spawn|spawnSync|execFile|execFileSync)\(/g)) {
      let end = m.index + m[0].length;
      for (let depth = 1; depth > 0 && end < text.length; end++) {
        if (text[end] === '(') depth++;
        else if (text[end] === ')') depth--;
      }
      if (!/[{,]\s*env\s*[:,}]/.test(text.slice(m.index, end))) found.push(`${where(m.index)} gives no env`);
    }
  }
  assert.deepEqual(found, []);
});

test('server: only its own Host is answered', async (t) => {
  const { port, own } = await startServer(t);
  for (const host of [`localhost:${port}`, `attacker.example:${port}`, '127.0.0.1']) {
    const res = await request(port, 'GET', '/api/questions', { headers: { Host: host } });
    assert.equal(res.status, 403, host);
    assert.deepEqual(JSON.parse(res.text), { error: `wrong host: open ${own}`, code: 'forbidden' });
  }
  assert.equal((await request(port, 'GET', '/api/questions')).status, 200);
});

test('server: a write needs the page\'s own Origin, or one named by --allow-origin', async (t) => {
  const { port, questions, own } = await startServer(t, { args: ['--allow-origin', 'http://127.0.0.1:5173'] });
  const post = (origin) => request(port, 'POST', '/api/questions/q-1/answer', {
    headers: { 'Content-Type': 'application/json', ...(origin ? { Origin: origin } : {}) }, body: JSON.stringify({ answer: 'Yes' }) });
  const before = readFileSync(questions, 'utf8');
  for (const origin of ['http://evil.example', 'http://localhost:5173', null]) {
    const res = await post(origin);
    assert.deepEqual([res.status, JSON.parse(res.text).code], [403, 'forbidden'], String(origin));
  }
  assert.equal(readFileSync(questions, 'utf8'), before);
  const saved = await post(own);
  assert.equal(saved.status, 200);
  // The answered question comes back, so the page can show it at once.
  assert.deepEqual([JSON.parse(saved.text).question.status, JSON.parse(saved.text).question.answer], ['answered', 'Yes']);
  assert.equal(JSON.parse(readFileSync(questions, 'utf8')).questions[0].answer, 'Yes');
  assert.equal((await post('http://127.0.0.1:5173')).status, 200);
});

test('server: a mailbox another writer holds answers 503, busy, and is left as it was', { timeout: 20000 }, async (t) => {
  const { port, questions, own } = await startServer(t);
  writeFileSync(`${questions}.lock`, '999 still at work');
  const before = readFileSync(questions, 'utf8');
  const res = await request(port, 'POST', '/api/questions/q-1/answer', {
    headers: { 'Content-Type': 'application/json', Origin: own }, body: JSON.stringify({ answer: 'Yes' }) });
  assert.deepEqual([res.status, JSON.parse(res.text).error], [503, 'the mailbox is busy, try again']);
  assert.equal(readFileSync(questions, 'utf8'), before);
});

test('server: a link inside the build that leads outside it is not followed', async (t) => {
  const { root, port } = await startServer(t);
  // A junction needs no special right on Windows; elsewhere it is an ordinary directory link.
  try { symlinkSync(root, join(root, 'dist', 'outside'), 'junction'); } catch (err) {
    return t.skip(`this computer does not permit creating a link here (${err.code})`);
  }
  const res = await request(port, 'GET', '/outside/secret.txt');
  assert.equal(res.status, 404);
  assert.ok(!res.text.includes(BESIDE_DIST));
});

test('server: a link to the build that spells it in another case is followed', {
  skip: process.platform !== 'win32' && 'only Windows takes a folder spelled in another case as the same folder',
}, async (t) => {
  const { root, port } = await startServer(t);
  const dist = join(root, 'dist');
  symlinkSync(dist.toUpperCase(), join(dist, 'upper'), 'junction');
  assert.equal((await request(port, 'GET', '/upper/index.html')).status, 200);
});

test('server: a build file that stats but cannot be read gets a prompt 500, not a hang', {
  skip: process.platform !== 'win32' && 'holding a file readable by stat but not by read uses a Windows share mode',
}, async (t) => {
  const { root, port } = await startServer(t);
  const file = join(root, 'dist', 'assets', 'locked.js');
  writeFileSync(file, 'console.log(2)');
  // A hidden PowerShell opens it with share mode None until its stdin closes.
  const holder = spawn('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command',
    "$f = [IO.File]::Open($env:HOLD, 'Open', 'ReadWrite', 'None'); 'held'; [void][Console]::In.ReadLine(); $f.Close()"],
  { env: smallEnv({ HOLD: file }), windowsHide: true });
  t.after(() => holder.kill());
  await new Promise((done, fail) => {
    holder.stdout.on('data', (c) => { if (String(c).includes('held')) done(); });
    holder.on('exit', (code) => fail(new Error(`PowerShell exited ${code} before it held the file`)));
  });
  const res = await Promise.race([request(port, 'GET', '/assets/locked.js'), sleep(3000).then(() => ({ status: 'no answer within 3 s' }))]);
  assert.equal(res.status, 500);
  assert.deepEqual(JSON.parse(res.text), { error: 'internal error', code: 'internal' });
});

test('server: agents load with Codex missing, and no key file text is served', async (t) => {
  const { port } = await startServer(t);
  const res = await request(port, 'GET', '/api/agents');
  assert.equal(res.status, 200);
  const { agents: list } = JSON.parse(res.text);
  assert.deepEqual(list.map((a) => [a.name, a.availability]), [['Peter', 'online'], ['Aster', 'offline'], ['May', 'online']]);
  assert.ok(list[1].note);
  // fakeHome()'s key file holds a live registry entry with this session id.
  assert.ok(!res.text.includes('key-file-session'));
});

test('server: the agents poll after an answer counts it at once, not from a reused snapshot', async (t) => {
  // May's Pi session is idle, so her open question alone makes her waiting.
  const { port, own } = await startServer(t, { home: fakeHome({ piFresh: false }) });
  const may = async () => JSON.parse((await request(port, 'GET', '/api/agents')).text).agents.find((a) => a.name === 'May');
  const before = await may();
  assert.deepEqual([before.openQuestions, before.workload], [1, 'waiting']);
  const saved = await request(port, 'POST', '/api/questions/q-1/answer', {
    headers: { 'Content-Type': 'application/json', Origin: own }, body: JSON.stringify({ answer: 'Yes' }) });
  assert.equal(saved.status, 200);
  const after = await may();
  assert.deepEqual([after.openQuestions, after.workload], [0, 'idle']);
});

test('server: the built app is served with its security policy, and nothing outside it', async (t) => {
  const { port } = await startServer(t);
  const page = await request(port, 'GET', '/');
  assert.equal(page.status, 200);
  // frame-src lets the taskboard page frame the board; default-src alone would block it.
  assert.equal(page.headers['content-security-policy'], "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    + "connect-src 'self'; frame-src http://127.0.0.1:47823; frame-ancestors 'none'; base-uri 'none'; form-action 'none'");
  assert.equal(page.headers['cache-control'], 'no-cache');
  const asset = await request(port, 'GET', '/assets/app.js');
  assert.deepEqual([asset.status, asset.headers['cache-control']], [200, 'max-age=31536000, immutable']);
  // Each resolves to secret.txt beside dist once decoded; %5c is a separator on Windows.
  for (const path of ['/..%2fsecret.txt', '/..%5csecret.txt']) {
    const res = await request(port, 'GET', path);
    assert.deepEqual([res.status, JSON.parse(res.text).code], [404, 'not-found'], path);
    assert.ok(!res.text.includes(BESIDE_DIST), path);
  }
  const bad = await request(port, 'GET', '/%E0%A4%A');
  assert.deepEqual([bad.status, JSON.parse(bad.text).code], [400, 'bad-request']);
});

test('server: every refusal outside the Codex routes carries a code', async (t) => {
  const { port, own } = await startServer(t);
  const answer = (headers, body = '{"answer":"Yes"}') => request(port, 'POST', '/api/questions/q-1/answer', { headers: { Origin: own, ...headers }, body });
  for (const [what, res, status, code] of [
    ['an unknown API route', await request(port, 'GET', '/api/nope'), 404, 'not-found'],
    ['a request target that is no URL', await request(port, 'GET', '//['), 400, 'bad-request'],
    ['a body that is not JSON', await answer({ 'Content-Type': 'text/plain' }), 415, 'bad-request'],
    ['a write to a page', await request(port, 'POST', '/index.html', { headers: { Origin: own } }), 405, 'bad-request'],
  ]) {
    assert.deepEqual([res.status, JSON.parse(res.text).code], [status, code], what);
  }
});

test('server: without a build it says how to make one', async (t) => {
  const { port } = await startServer(t, { dist: false });
  const res = await request(port, 'GET', '/');
  assert.equal(res.status, 503);
  assert.match(res.text, /npm ci --ignore-scripts/);
});

test('server: a malformed question id is refused with 400, and nothing is written', async (t) => {
  const { port, questions, own } = await startServer(t);
  const before = readFileSync(questions, 'utf8');
  const res = await request(port, 'POST', '/api/questions/%E0/answer', {
    headers: { 'Content-Type': 'application/json', Origin: own }, body: JSON.stringify({ answer: 'Yes' }) });
  assert.equal(res.status, 400);
  assert.equal(readFileSync(questions, 'utf8'), before);
});

test('server: a cross-site request may not use the API', async (t) => {
  const { port } = await startServer(t);
  for (const path of ['/api/agents', '/api/questions']) {
    const res = await request(port, 'GET', path, { headers: { 'Sec-Fetch-Site': 'cross-site' } });
    assert.deepEqual([res.status, JSON.parse(res.text).code], [403, 'forbidden'], path);
  }
  assert.equal((await request(port, 'GET', '/api/questions', { headers: { 'Sec-Fetch-Site': 'same-origin' } })).status, 200);
});

test('server: a body over 64 KB is refused at the limit, without waiting for the rest', { timeout: 10000 }, async (t) => {
  const { port, questions, own } = await startServer(t);
  const before = readFileSync(questions, 'utf8');
  const answer = await new Promise((done, fail) => {
    const req = http.request({ host: '127.0.0.1', port, method: 'POST', path: '/api/questions/q-1/answer',
      headers: { Host: `127.0.0.1:${port}`, Origin: own, 'Content-Type': 'application/json' } }, (res) => {
      let text = '';
      res.setEncoding('utf8');
      res.on('data', (c) => { text += c; });
      res.on('end', () => { done([res.statusCode, JSON.parse(text).code]); req.destroy(); });
    });
    req.on('error', fail); // after the answer the server drops the connection; a settled promise ignores it
    req.write(`{"answer":"${'x'.repeat(65 * 1024)}`); // never ended: a server waiting for the end never answers
  });
  assert.deepEqual(answer, [413, 'bad-request']);
  assert.equal(readFileSync(questions, 'utf8'), before);
});

test('server: an unexpected error is not echoed, and no answer names a local path', async (t) => {
  const { root, port, questions } = await startServer(t);
  // A NUL in the path makes statSync throw an error that quotes the full path.
  const res = await request(port, 'GET', '/a%00.js');
  assert.equal(res.status, 500);
  assert.deepEqual(JSON.parse(res.text), { error: 'internal error', code: 'internal' });
  fs.rmSync(questions);
  const list = await request(port, 'GET', '/api/questions');
  assert.equal(list.status, 200);
  const { error } = JSON.parse(list.text);
  assert.match(error, /questions\.json/);
  for (const folder of [root, dirname(questions)]) assert.ok(!error.includes(basename(folder)), error);
});

test('server: another host or a bad --allow-origin is refused at start', () => {
  for (const args of [['--host', '0.0.0.0'], ['--allow-origin', 'http://evil.example'], ['--allow-origin', 'http://127.0.0.1:99999']]) {
    const run = spawnSync(process.execPath, [SERVER, '--port', '0', ...args], { encoding: 'utf8', timeout: 20000, env: smallEnv(), windowsHide: true });
    assert.equal(run.status, 2, args.join(' '));
  }
});
