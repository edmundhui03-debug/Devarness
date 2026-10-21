// The Tasks page's readings: the house section index (md-format status --json,
// run by the Python `dashboard serve` passes as DEVARNESS_PYTHON), the agent ledger's
// running rows, and the last commits of one indexed document.
import { spawn } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { basename, dirname, join } from 'node:path';
import { httpError } from './codex.mjs';

export const STALE_MS = 6 * 3600_000; // a running row this old may have been left behind (R3-4)
const STATES = new Set(['open', 'partial', 'blocked', 'needs-owner', 'fixed']);
const KEEP = ['PATH', 'SYSTEMROOT', 'USERPROFILE', 'HOME', 'TEMP', 'TMP'];

// A small environment of its own, never the server's whole one (LESSONS.md:460).
function smallEnv() {
  const env = { PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' };
  for (const key of KEEP) if (process.env[key]) env[key] = process.env[key];
  return env;
}

// Runs a program hidden, with a deadline. Resolves { code, out, err }, code null
// when it was killed; rejects when the program cannot start at all.
export function run(command, args, cwd, timeoutMs) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, env: smallEnv(), windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    const out = [];
    let err = '';
    child.stdout.on('data', (chunk) => out.push(chunk));
    child.stderr.on('data', (chunk) => { err = (err + chunk).slice(-2000); });
    const timer = setTimeout(() => child.kill(), timeoutMs);
    child.on('error', (e) => { clearTimeout(timer); reject(e); });
    child.on('close', (code) => { clearTimeout(timer); resolve({ code, out: Buffer.concat(out).toString('utf8'), err }); });
  });
}

const isSection = (s) => STATES.has(s?.status) && typeof s.file === 'string'
  && Number.isInteger(s.line) && typeof s.heading === 'string';

export async function readIndex(root, python = process.env.DEVARNESS_PYTHON, timeoutMs = 45_000) {
  if (!python) return { code: 'tasks-no-python' };
  let result;
  try {
    result = await run(python, [join(root, 'Library', 'bin', 'md-format'), 'status', '--json'], root, timeoutMs);
  } catch {
    return { code: 'tasks-no-python' }; // the program named is not there, or cannot start
  }
  try {
    if (result.code !== 0) throw new Error(`exit ${result.code}`);
    const { sections, titles } = JSON.parse(result.out);
    return {
      code: 'ok',
      sections: (Array.isArray(sections) ? sections : []).filter(isSection)
        .map(({ status, file, line, heading }) => ({ status, file, line, heading })),
      titles: titles && typeof titles === 'object' && !Array.isArray(titles) ? titles : {},
    };
  } catch (err) {
    console.error(`tasks: md-format status failed (${err.message}) ${result.err}`); // the server's terminal only
    return { code: 'tasks-index-failed' };
  }
}

const ROW = /^\|\s*\d{4}-\d{2}-\d{2}/;
const WHEN = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/;
const ZONE = /\bUTC([+-]\d{1,2})?|\bHKT\b/;

// A ledger time in any form its rows use: Hong Kong time unless the cell says
// UTC, UTC+N or HKT (Setup/AGENT_LEDGER.md:17). Null when the cell holds no time.
export function launchedAt(cell) {
  const m = WHEN.exec(cell);
  if (!m) return null;
  const zone = ZONE.exec(cell);
  const offset = !zone || zone[0] === 'HKT' ? 8 : Number(zone[1] ?? 0);
  const [y, mo, d, h, mi, s = '0'] = m.slice(1);
  return new Date(Date.UTC(+y, +mo - 1, +d, +h - offset, +mi, +s)).toISOString();
}

// One table row's cells; `\|` is a pipe inside a cell, and a row may lack its closing pipe.
function cells(line) {
  const parts = line.split(/(?<!\\)\|/).map((c) => c.trim().replaceAll('\\|', '|'));
  parts.shift();
  if (parts.at(-1) === '') parts.pop();
  return parts;
}

// The running rows of Launched | Session | Task | Agent, model | Budget | Output | Status | ...
export function parseLedger(text, now = Date.now()) {
  const runs = [];
  for (const line of text.split(/\r?\n/)) {
    if (!ROW.test(line)) continue;
    const c = cells(line);
    if (c.length < 7 || !/^running\b/i.test(c[6])) continue;
    const at = launchedAt(c[0]);
    runs.push({ launched: c[0], at, session: c[1], task: c[2], agent: c[3], budget: c[4],
      stale: at !== null && now - Date.parse(at) > STALE_MS });
  }
  return runs;
}

export async function readRuns(root, now = Date.now()) {
  try {
    return parseLedger(await readFile(join(root, 'Setup', 'AGENT_LEDGER.md'), 'utf8'), now);
  } catch (err) {
    if (err.code === 'ENOENT') return [];
    throw err;
  }
}

export async function readTasks(root, python = process.env.DEVARNESS_PYTHON) {
  const [index, runs] = await Promise.all([readIndex(root, python), readRuns(root)]);
  return { code: index.code, sections: index.sections ?? [], titles: index.titles ?? {}, runs, at: new Date().toISOString() };
}

// The last three commits that touched one indexed document, asked of the
// repository that holds it: dev, or a nested house repository under Projects/.
// The name is a literal path, never a glob.
export async function lastCommits(root, file) {
  const full = join(root, file);
  let result = null;
  try {
    result = await run('git', ['--literal-pathspecs', 'log', '-3', '--format=%h%x09%cI%x09%s', '--', basename(full)],
      dirname(full), 10_000);
  } catch { /* git cannot start, or the folder is gone */ }
  if (result?.code !== 0) {
    console.error(`tasks: git log failed (exit ${result?.code}) ${result?.err ?? ''}`); // the server's terminal only
    throw Object.assign(httpError(502, 'git log failed'), { code: 'git-failed' });
  }
  return result.out.split(/\r?\n/).filter(Boolean).map((line) => {
    const [hash, at, ...subject] = line.split('\t');
    return { hash, at, subject: subject.join('\t') };
  });
}
