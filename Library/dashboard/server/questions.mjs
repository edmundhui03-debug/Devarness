// questions.mjs: the agents' questions mailbox, Library/dashboard/questions.json.
// The contract is Library/dashboard/AGENTS.md: twelve fields; the owner's side
// writes only status, answer and answered_at; every writer holds the mailbox's
// lock while it re-reads the file and replaces it by temporary file and rename.
import { randomUUID } from 'node:crypto';
import { closeSync, openSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { setTimeout as sleep } from 'node:timers/promises';

export const PROJECTS = ['PCB', 'DATASET', 'Research', 'Library', 'General'];
const STATUSES = ['open', 'answered', 'used'];
const TEXT_FIELDS = ['task', 'asked_by', 'asked_at', 'answer', 'answered_at', 'used_by', 'used_at', 'used_note'];
const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const isStr = (v) => typeof v === 'string';
const httpError = (status, message) => Object.assign(new Error(message), { status });
const busy = () => httpError(503, 'the mailbox is busy, try again');

export function validateQuestions(d) {
  if (!isObj(d)) return '$';
  if (d.version !== 1) return 'version';
  if (!Array.isArray(d.questions)) return 'questions';
  const seen = new Set();
  for (let i = 0; i < d.questions.length; i++) {
    const q = d.questions[i], at = `questions[${i}]`;
    if (!isObj(q)) return at;
    if (!isStr(q.id) || !q.id || seen.has(q.id)) return at + '.id';
    seen.add(q.id);
    if (!PROJECTS.includes(q.project)) return at + '.project';
    if (!isStr(q.question) || !q.question.trim()) return at + '.question';
    if (!STATUSES.includes(q.status)) return at + '.status';
    for (const f of TEXT_FIELDS) if (f in q && !isStr(q[f])) return `${at}.${f}`;
  }
  return null;
}

// PowerShell 5.1 saves UTF-8 with a byte order mark (U+FEFF), which JSON.parse refuses.
const withoutBom = (text) => (text.charCodeAt(0) === 0xfeff ? text.slice(1) : text);

export function readQuestions(path) {
  let doc;
  try { doc = JSON.parse(withoutBom(readFileSync(path, 'utf8'))); } catch (err) {
    throw httpError(err.code === 'ENOENT' ? 404 : 409, `questions.json cannot be read: ${err.message}`);
  }
  const where = validateQuestions(doc);
  if (where) throw httpError(409, `questions.json is not valid at ${where}`);
  return doc;
}

// What the answers in flight hold, let go if the process ends mid-retry: the
// server's Ctrl+C handler calls process.exit, which runs these and no finally.
const held = new Set();
process.on('exit', () => { for (const letGo of held) letGo(); });

// The mailbox's one lock, shared with `dashboard ask` and `dashboard used`
// (Library/bin/dashboard): <questions.json>.lock, created exclusively and held
// from the read to the rename, so neither writer loses the other's update. A
// lock older than staleMs was left by a writer that stopped and is broken. The
// wait always sleeps between tries and ends at waitMs, timed by performance.now(),
// which a wall-clock step cannot move; the stale age is the file's own clock.
// work gets ours(), true while the lock is still this writer's.
async function withLock(path, work, { staleMs = 10_000, waitMs = 5_000 } = {}) {
  const lock = `${path}.lock`;
  const mine = `${process.pid} ${new Date().toISOString()}`;
  const giveUp = performance.now() + waitMs;
  for (;;) {
    try {
      const fd = openSync(lock, 'wx');
      try { writeFileSync(fd, mine); } catch (err) {
        closeSync(fd);
        rmSync(lock, { force: true }); // ours, but without its token no one could tell
        throw err;
      }
      closeSync(fd);
      break;
    } catch (err) {
      if (err.code !== 'EEXIST' && err.code !== 'EPERM') throw err; // EPERM: Windows, while another writer removes it
    }
    try {
      if (Date.now() - statSync(lock).mtimeMs > staleMs) { rmSync(lock); continue; }
    } catch { /* let go meanwhile, or a folder that refuses files: wait as for any lock */ }
    if (performance.now() >= giveUp) throw busy();
    await sleep(50);
  }
  // Only this writer's own lock: one broken as stale may have been taken by another since.
  const ours = () => { try { return readFileSync(lock, 'utf8') === mine; } catch { return false; } };
  const letGo = () => { try { if (ours()) rmSync(lock); } catch { /* already gone */ } };
  held.add(letGo);
  try { return await work(ours); } finally { held.delete(letGo); letGo(); }
}

const writable = (path) => { try { return (statSync(path).mode & 0o200) !== 0; } catch { return true; } };

// Windows refuses a rename over a file another process has open, such as a
// `dashboard wait` poll: tried again, still under the lock, for about a second.
// A file marked read-only is refused for good, so its error is passed on at once;
// a writer whose lock was broken and taken meanwhile stops without renaming.
async function replace(scratch, path, ours) {
  for (let tries = 1; ; tries++) {
    try { return renameSync(scratch, path); } catch (err) {
      if (!['EPERM', 'EACCES', 'EBUSY'].includes(err.code) || !writable(path)) throw err;
      if (tries === 20) throw busy();
    }
    await sleep(50);
    if (!ours()) throw busy();
  }
}

export async function answerQuestion(path, id, text, now = new Date().toISOString(), lock = {}) {
  const answer = isStr(text) ? text.trim() : '';
  if (!answer) throw httpError(400, 'the answer is empty');
  return withLock(path, async (ours) => {
    const doc = readQuestions(path); // read again now, so what agents added since is kept
    const q = doc.questions.find((x) => x.id === id);
    if (!q) throw httpError(404, 'no such question');
    if (q.status === 'used') throw httpError(409, 'this question is already used');
    Object.assign(q, { status: 'answered', answer, answered_at: now });
    // One scratch file per answer: two answers in one process may overlap while a rename is retried.
    const scratch = `${path}.${process.pid}.${randomUUID()}.tmp`;
    const drop = () => rmSync(scratch, { force: true });
    held.add(drop);
    try {
      writeFileSync(scratch, JSON.stringify(doc, null, 2) + '\n', { flag: 'w' });
      await replace(scratch, path, ours);
    } catch (err) { drop(); throw err; } finally { held.delete(drop); }
    return q;
  }, lock);
}
