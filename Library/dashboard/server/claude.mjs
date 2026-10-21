// claude.mjs: the Claude page's readings. Live sessions come from Claude's
// registry (claudeSessions), ended ones from transcripts that changed in the
// last 24 h, and a session's last steps from its transcript's tail. Files are
// opened only by these names: sessions/<digits>.json, projects/<dir>/<uuid>.jsonl,
// the session folder's custom-title.json, subagents/[workflows/wf_<id>/]agent-<id>.jsonl
// and .meta.json, and workflows/wf_<id>.json; never a *.key, credentials,
// history, session-env, shell-snapshots or tool-results file, and never a link,
// which could lead to one. Every string that leaves passes mask() first and is
// cut only after it, so a cut never leaves part of a key.
// Plan: Setup/superpowers/plans/2026-10-15-dashboard-wave-4.md.
import { closeSync, lstatSync, openSync, readdirSync, readFileSync, readSync } from 'node:fs';
import { basename, join } from 'node:path';
import { claudeSessions, pidAlive } from './agents.mjs';
import { MASK, mask as realMask } from './mask.mjs';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const AGENT = /^agent-[A-Za-z0-9]{1,64}$/;
const AGENT_FILE = /^agent-[A-Za-z0-9]{1,64}\.jsonl$/;
const RUN = /^wf_[A-Za-z0-9-]{1,64}$/;
const DAY_MS = 24 * 3600_000;
const LIVE_MS = 120_000; // an agent written this lately is working, as Pi's sessions are read
const TITLE_WINDOW = 64 * 1024;
const JSON_MAX = 1024 * 1024; // a run's file reaches 225 KB, a title's or an agent's 200 bytes
const TITLE = 200;
const SHOWN = { ended: 10, agents: 10, runs: 5, runAgents: 30 };
// A prompt and a reply keep their first characters, a tool line its first; a result keeps its last 1,500.
const KEEP = { prompt: 4000, reply: 4000, tool: 300, thinking: 0 };
const TOOL_KEYS = ['command', 'file_path', 'path', 'pattern', 'url', 'query', 'description'];

const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
const str = (v) => (typeof v === 'string' ? v : '');
const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
// null for a time Date cannot represent, and for anything but a string or a number.
const iso = (v) => {
  if (typeof v !== 'string' && typeof v !== 'number') return null;
  const date = new Date(v);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
};
const names = (dir) => { try { return readdirSync(dir); } catch { return []; } };
const withoutExt = (path) => path.replace(/\.jsonl?$/, '');

// { path, id, mtime } of a regular file; null when it is gone, a folder or a link.
function fileInfo(path) {
  try {
    const st = lstatSync(path);
    return st.isFile() ? { path, id: basename(withoutExt(path)), mtime: st.mtimeMs } : null;
  } catch { return null; }
}

function readJson(path) {
  try {
    const st = lstatSync(path);
    if (!st.isFile() || st.size > JSON_MAX) return null;
    const value = JSON.parse(readFileSync(path, 'utf8'));
    return isObj(value) ? value : null;
  } catch { return null; }
}

// The JSON objects among a transcript's last windowBytes, oldest first, sidechain
// lines left out unless `sidechain` (an agent's own file, every line of which is
// one); null when the file cannot be read. A cut first line, a last line still
// being written and any other unparsable line are skipped.
function tail(path, windowBytes, sidechain = false) {
  let text;
  try {
    const st = lstatSync(path);
    if (!st.isFile()) return null;
    // One byte more, before the window: the first line is whole only when that byte ends a line.
    const from = Math.max(0, st.size - windowBytes - 1);
    const buf = Buffer.alloc(st.size - from);
    const fd = openSync(path, 'r');
    let read;
    try { read = readSync(fd, buf, 0, buf.length, from); } finally { closeSync(fd); }
    text = buf.subarray(0, read).toString('utf8');
    if (from > 0) text = text.includes('\n') ? text.slice(text.indexOf('\n') + 1) : '';
  } catch { return null; }
  const entries = [];
  for (const line of text.split('\n')) {
    let entry;
    try { entry = JSON.parse(line); } catch { continue; }
    if (isObj(entry) && (sidechain || entry.isSidechain !== true)) entries.push(entry);
  }
  return entries;
}

// The last non-empty string the lines give for `key`, or null.
function last(entries, key) {
  for (let i = entries.length - 1; i >= 0; i--) if (str(entries[i][key])) return entries[i][key];
  return null;
}

// An input with none of the known keys is masked as an object before it becomes
// a string: the object rule hides everything under a secret's name, "auth" too.
// One nested too deep to mask or stringify shows masked whole.
function toolText(input, mask) {
  const key = isObj(input) ? TOOL_KEYS.find((k) => str(input[k])) : undefined;
  try { return key ? input[key] : JSON.stringify(mask(input) ?? null); } catch { return MASK; }
}

// The owner's own words in a user text block: Claude Code leads some with its own
// elements, which are dropped; a slash command shows as its name and arguments,
// then any words after it.
const ADDED = /^\s*<(system-reminder|task-notification|local-command-stdout|local-command-stderr)>[\s\S]*?<\/\1>/;
const COMMAND = /<(command-name|command-message|command-args)>[\s\S]*?<\/\1>/g;
function ownWords(text) {
  let rest = text;
  for (let m; (m = ADDED.exec(rest)); ) rest = rest.slice(m[0].length);
  if (/^\s*<command-(name|message)>/.test(rest)) {
    const part = (tag) => new RegExp(`<${tag}>([\\s\\S]*?)</${tag}>`).exec(rest)?.[1].trim() ?? '';
    return [part('command-name'), part('command-args'), rest.replace(COMMAND, '').trim()].filter(Boolean).join(' ');
  }
  return rest === text ? text : rest.trim();
}

function resultText(content) {
  if (typeof content === 'string') return content;
  if (!Array.isArray(content)) return '';
  return content.map((b) => (b?.type === 'text' && typeof b.text === 'string' ? b.text : b?.type === 'image' ? '[image]' : null))
    .filter((text) => text !== null).join('\n');
}

// Every step the lines hold, oldest first, not yet masked as text. One line gives a step per block it holds.
function rawSteps(entries, mask) {
  const toolOf = new Map(); // a tool_use id → its tool's name
  const steps = [];
  const add = (kind, text, tool, error, at) => steps.push({ kind, text, tool, error, at });
  for (const e of entries) {
    // An isMeta line is Claude Code's, not the owner's: a command's expansion, a caveat, a reminder.
    if ((e.type !== 'user' && e.type !== 'assistant') || !isObj(e.message) || e.isMeta === true) continue;
    const { content } = e.message;
    const blocks = typeof content === 'string' ? [{ type: 'text', text: content }] : Array.isArray(content) ? content : [];
    const at = iso(e.timestamp);
    for (const b of blocks) {
      if (!isObj(b)) continue;
      if (b.type === 'text' && typeof b.text === 'string') {
        const text = e.type === 'user' ? ownWords(b.text) : b.text;
        if (text) add(e.type === 'user' ? 'prompt' : 'reply', text, null, false, at);
      }
      else if (b.type === 'thinking') add('thinking', '', null, false, at); // a marker only: its text is never shown
      else if (b.type === 'tool_use') {
        const name = str(b.name) || null;
        if (typeof b.id === 'string') toolOf.set(b.id, name);
        add('tool', toolText(b.input, mask), name, false, at);
      } else if (b.type === 'tool_result') add('result', resultText(b.content), toolOf.get(b.tool_use_id) ?? null, b.is_error === true, at);
    }
  }
  return steps;
}

// Masked whole, then cut.
function shown(step, mask) {
  const text = mask(step.text);
  return { ...step, text: step.kind === 'result' ? text.slice(-1500) : text.slice(0, KEEP[step.kind]), tool: step.tool === null ? null : mask(step.tool) };
}

// `folder` is the cwd unmasked, for git to run in: a mask can hide a real folder's
// name. It never leaves the server.
export function readSteps(path, { limit = 20, windowBytes = 2 * 1024 * 1024, mask = realMask, sidechain = false } = {}) {
  const entries = tail(path, windowBytes, sidechain);
  if (!entries) return { readable: false, steps: [], branch: null, cwd: null, source: null, folder: null };
  const steps = rawSteps(entries, mask);
  const masked = (key) => { const v = last(entries, key); return v === null ? null : mask(v); };
  return {
    readable: true,
    steps: steps.slice(Math.max(0, steps.length - limit)).map((s) => shown(s, mask)),
    branch: masked('gitBranch'), cwd: masked('cwd'), source: masked('entrypoint'), folder: last(entries, 'cwd'),
  };
}

const projectsOf = (home) => join(home, '.claude', 'projects');
function projectDirs(home) {
  try { return readdirSync(projectsOf(home), { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name); } catch { return []; }
}
const newer = (best, info) => (info && !(best?.mtime > info.mtime) ? info : best);

// Every uuid-named transcript, by id; the newest when one session has files in two folders.
function transcripts(home) {
  const found = new Map();
  for (const dir of projectDirs(home)) {
    for (const name of names(join(projectsOf(home), dir))) {
      if (!name.endsWith('.jsonl') || !UUID.test(name.slice(0, -'.jsonl'.length))) continue;
      const info = fileInfo(join(projectsOf(home), dir, name));
      if (info) found.set(info.id, newer(found.get(info.id), info));
    }
  }
  return found;
}

export function findTranscript(home, id) {
  if (typeof id !== 'string' || !UUID.test(id)) return null;
  let best = null;
  for (const dir of projectDirs(home)) best = newer(best, fileInfo(join(projectsOf(home), dir, `${id}.jsonl`)));
  return best?.path ?? null;
}

// The custom title cut to 200, else the last prompt cut to 80, else the id; masked.
function fallbackTitle(path, entries, id, mask) {
  const custom = str(readJson(join(withoutExt(path), 'custom-title.json'))?.customTitle);
  if (custom) return mask(custom).slice(0, TITLE);
  const prompt = last(entries, 'lastPrompt');
  return prompt ? mask(prompt).slice(0, 80) : mask(id);
}

export function listClaude(home, { now = Date.now(), alive = pidAlive, mask = realMask } = {}) {
  const files = transcripts(home);
  const registry = claudeSessions(home, alive).sessions;
  const live = registry.map((s) => {
    const path = files.get(s.id)?.path;
    // claudeSessions shows the cwd for a session with no name: that is not a title here.
    const name = s.title !== s.cwd ? s.title : '';
    const title = name ? mask(name).slice(0, TITLE) : path ? fallbackTitle(path, tail(path, TITLE_WINDOW) ?? [], s.id, mask) : mask(s.id);
    return { ...s, id: mask(s.id), title, cwd: mask(s.cwd), source: mask(s.source) };
  });
  const liveIds = new Set(registry.map((s) => s.id));
  const ended = [...files.values()]
    .filter((f) => !liveIds.has(f.id) && now - f.mtime <= DAY_MS)
    .sort((a, b) => b.mtime - a.mtime)
    .slice(0, SHOWN.ended)
    .map((f) => {
      const entries = tail(f.path, TITLE_WINDOW) ?? [];
      return {
        id: mask(f.id), title: fallbackTitle(f.path, entries, f.id, mask), cwd: mask(last(entries, 'cwd') ?? ''),
        state: 'ended', source: mask(last(entries, 'entrypoint') ?? ''), updatedAt: new Date(f.mtime).toISOString(),
      };
    });
  return { sessions: [...live, ...ended] };
}

// The regular agent-<id>.jsonl files of one folder, newest first.
function agentFiles(dir) {
  return names(dir).filter((n) => AGENT_FILE.test(n)).map((n) => fileInfo(join(dir, n))).filter(Boolean)
    .sort((a, b) => b.mtime - a.mtime);
}

function row(file, run, now, mask) {
  const meta = readJson(`${withoutExt(file.path)}.meta.json`);
  const type = str(meta?.agentType);
  return {
    id: mask(file.id), title: mask(str(meta?.description) || type || file.id).slice(0, TITLE), type: type ? mask(type).slice(0, TITLE) : null,
    run: run === null ? null : mask(run), state: now - file.mtime < LIVE_MS ? 'working' : 'idle', updatedAt: new Date(file.mtime).toISOString(),
  };
}

// The row of one agent findAgent found; null when its file is gone since.
export function agentRow(path, run, { now = Date.now(), mask = realMask } = {}) {
  const file = fileInfo(path);
  return file ? row(file, run, now, mask) : null;
}

export function sessionParts(home, id, { now = Date.now(), mask = realMask } = {}) {
  const transcript = findTranscript(home, id);
  if (!transcript) return { agents: [], runs: [] };
  const subagents = join(withoutExt(transcript), 'subagents');
  const runFiles = join(withoutExt(transcript), 'workflows');
  const runAgents = join(subagents, 'workflows');
  // A run shows by its file, by its agents' folder, or both; it is as new as the newest of them.
  const ids = new Set([...names(runFiles).map((n) => n.replace(/\.json$/, '')), ...names(runAgents)].filter((r) => RUN.test(r)));
  const runs = [...ids].map((r) => {
    const file = fileInfo(join(runFiles, `${r}.json`));
    const files = agentFiles(join(runAgents, r));
    return { r, file, files, latest: Math.max(file?.mtime ?? 0, files[0]?.mtime ?? 0) };
  }).sort((a, b) => b.latest - a.latest).slice(0, SHOWN.runs).map(({ r, file, files }) => {
    // Its script, result and logs are never taken.
    const data = file && readJson(file.path);
    const fresh = files.some((f) => now - f.mtime < LIVE_MS);
    return {
      id: mask(r), name: mask(str(data?.workflowName) || r).slice(0, TITLE),
      status: typeof data?.status === 'string' ? mask(data.status) : !data && fresh ? 'running' : 'unknown',
      summary: mask(str(data?.summary)).slice(0, 300),
      agentCount: num(data?.agentCount), startedAt: iso(data?.startTime), durationMs: num(data?.durationMs),
      agents: files.slice(0, SHOWN.runAgents).map((f) => row(f, r, now, mask)),
    };
  });
  return { agents: agentFiles(subagents).slice(0, SHOWN.agents).map((f) => row(f, null, now, mask)), runs };
}

// An agent's file inside this session's own folder: a direct subagent, or one of its runs' agents.
export function findAgent(home, sessionId, agentId) {
  if (typeof agentId !== 'string' || !AGENT.test(agentId)) return null;
  const transcript = findTranscript(home, sessionId);
  if (!transcript) return null;
  const subagents = join(withoutExt(transcript), 'subagents');
  const direct = join(subagents, `${agentId}.jsonl`);
  if (fileInfo(direct)) return { path: direct, run: null };
  const runAgents = join(subagents, 'workflows');
  for (const run of names(runAgents).filter((r) => RUN.test(r))) {
    const path = join(runAgents, run, `${agentId}.jsonl`);
    if (fileInfo(path)) return { path, run };
  }
  return null;
}
