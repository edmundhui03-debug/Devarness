// agents.mjs: Peter (Claude Code), Aster (Codex) and May (Pi), from what each
// keeps on this computer. Reads file names, registry fields and the last line
// of a session file; never a *.key, credentials or history file.
import { closeSync, openSync, readdirSync, readFileSync, readSync, statSync } from 'node:fs';
import { basename, join } from 'node:path';

const LIVE_MS = 120_000;
const SHOWN = 10;
const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
// null for a time Date cannot represent (new Date(1e20).toISOString() throws).
const iso = (v) => {
  const date = new Date(typeof v === 'number' ? (v < 1e12 ? v * 1000 : v) : Date.parse(v));
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
};
const newestFirst = (a, b) => String(b.updatedAt ?? '').localeCompare(String(a.updatedAt ?? ''));

// Node's kill(pid, 0) only asks whether the process lives; it never ends it.
export function pidAlive(pid) {
  try { process.kill(pid, 0); return true; } catch (err) { return err.code === 'EPERM'; }
}

export function claudeSessions(home, alive = pidAlive) {
  const dir = join(home, '.claude', 'sessions');
  let names;
  try { names = readdirSync(dir).filter((n) => /^\d+\.json$/.test(n)); } catch { return { ok: false, sessions: [] }; }
  const sessions = [];
  for (const name of names) {
    let s;
    try { s = JSON.parse(readFileSync(join(dir, name), 'utf8')); } catch { continue; }
    // pid 0 is not a process: process.kill(0, 0) signals the whole group and succeeds.
    if (!isObj(s) || !Number.isInteger(s.pid) || s.pid <= 0 || !alive(s.pid)) continue;
    sessions.push({
      id: String(s.sessionId ?? s.pid), title: String(s.name || s.cwd || ''), cwd: String(s.cwd ?? ''),
      state: s.status === 'busy' ? 'working' : 'idle', updatedAt: iso(s.statusUpdatedAt ?? s.updatedAt),
      source: String(s.entrypoint ?? s.kind ?? ''),
    });
  }
  return { ok: true, sessions: sessions.sort(newestFirst) };
}

// The last message line of a Pi session file, read from its final 64 KB; null
// when the file cannot be read (gone, locked, a directory) or has no message.
function lastMessage(path) {
  try {
    const size = statSync(path).size;
    const length = Math.min(size, 64 * 1024);
    const buf = Buffer.alloc(length);
    const fd = openSync(path, 'r');
    try { readSync(fd, buf, 0, length, size - length); } finally { closeSync(fd); }
    for (const line of buf.toString('utf8').split('\n').reverse()) {
      try { const e = JSON.parse(line); if (e.type === 'message' && isObj(e.message)) return e.message; } catch { /* a cut first line */ }
    }
  } catch { /* an unreadable file counts as idle */ }
  return null;
}

export function piStatus(home, now = Date.now()) {
  const agent = join(home, '.pi', 'agent');
  let version = null;
  try { version = readFileSync(join(agent, 'install', 'current-version'), 'utf8').trim() || null; } catch { /* Pi not installed */ }
  const root = join(agent, 'sessions');
  const files = [];
  let folders = [];
  try { folders = readdirSync(root, { withFileTypes: true }).filter((d) => d.isDirectory()); } catch { /* no sessions yet */ }
  for (const d of folders) {
    let names;
    try { names = readdirSync(join(root, d.name)); } catch { continue; }
    for (const f of names) {
      // history.jsonl is a history file, never a session: it is not even measured.
      if (!f.endsWith('.jsonl') || f.toLowerCase() === 'history.jsonl') continue;
      const path = join(root, d.name, f);
      try { files.push({ path, folder: d.name, mtime: statSync(path).mtimeMs }); } catch { /* gone since the listing */ }
    }
  }
  files.sort((a, b) => b.mtime - a.mtime);
  const sessions = files.slice(0, SHOWN).map(({ path, folder, mtime }) => {
    const last = now - mtime < LIVE_MS ? lastMessage(path) : null;
    const open = last && (last.role === 'user' || last.role === 'toolResult' || last.stopReason === 'toolUse');
    const where = folder.replace(/^--|--$/g, '');
    return { id: basename(path, '.jsonl'), title: where, cwd: where, state: open ? 'working' : 'idle', updatedAt: new Date(mtime).toISOString(), source: 'pi' };
  });
  return { ok: version !== null, version, sessions };
}

function codexSession(t) {
  const state = t.state === 'running' || t.state === 'active-elsewhere' ? 'working' : t.state === 'error' ? 'error' : 'idle';
  return { id: t.id, title: String(t.name || t.preview || t.id), cwd: String(t.cwd ?? ''), state, updatedAt: iso(t.updatedAt), source: String(t.source ?? '') };
}

function agent(name, client, online, sessions, openQuestions, note) {
  const working = sessions.some((s) => s.state === 'working');
  return {
    name, client, availability: online ? 'online' : 'offline',
    workload: working ? 'working' : openQuestions ? 'waiting' : 'idle',
    sessions, openQuestions, ...(note ? { note } : {}),
  };
}

const failed = (err) => ({ ok: false, sessions: [], note: String(err?.message ?? err) });

// One unreadable source takes only its own agent offline, with the reason.
function guarded(read) {
  try { return read(); } catch (err) { return failed(err); }
}

// Codex gets a deadline, so a hung app server cannot hold the whole answer.
async function asterSessions(codex, deadlineMs) {
  let timer;
  const late = new Promise((resolve) => {
    timer = setTimeout(() => resolve(failed(`Codex did not answer within ${deadlineMs / 1000} s`)), deadlineMs);
  });
  const read = (async () => {
    const health = await codex.health();
    if (!health.up) return failed('Codex did not start'); // its own error can quote the command's path
    if (!(await codex.signedIn())) return failed('Codex is not signed in');
    return { ok: true, sessions: (await codex.listThreads()).slice(0, SHOWN).map(codexSession) };
  })().catch(() => failed('Codex answered with an error')); // an error's own words can quote a local path
  try { return await Promise.race([read, late]); } finally { clearTimeout(timer); }
}

// Every poll from every tab shares one reading: while one is being built each
// caller gets the same promise, and a finished one is reused for reuseMs, so
// polls never pile up Codex calls behind each other. forget() drops the
// reading, so the next call reads afresh; one still being built then serves
// only the callers that already have it. Timed by performance.now(), which a
// wall-clock step cannot move.
export function sharedSnapshot(read, reuseMs = 2000) {
  let current = null;
  let finished = null; // when current settled; null while it is being built
  const get = () => {
    if (current && (finished === null || performance.now() - finished < reuseMs)) return current;
    const mine = current = read();
    finished = null;
    mine.finally(() => { if (current === mine) finished = performance.now(); }).catch(() => {});
    return mine;
  };
  get.forget = () => { current = null; };
  return get;
}

export async function agents({ home, codex, questions, now = Date.now(), codexDeadlineMs = 5000 }) {
  const open = (name) => questions.filter((q) => q.status === 'open' && q.asked_by === name).length;
  const claude = guarded(() => claudeSessions(home));
  const pi = guarded(() => piStatus(home, now));
  const aster = await asterSessions(codex, codexDeadlineMs);
  return [
    agent('Peter', 'Claude Code', claude.sessions.length > 0, claude.sessions, open('Peter'), claude.note),
    agent('Aster', 'Codex', aster.ok, aster.sessions, open('Aster'), aster.note),
    agent('May', 'Pi', pi.ok, pi.sessions, open('May'), pi.note),
  ];
}
