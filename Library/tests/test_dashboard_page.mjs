// Tests for Library/dashboard/index.html: static rules, pure functions, and a
// smoke run of the page code against a small fake DOM (no browser, no deps).
// Usage: node --test test_dashboard_page.mjs   (INDEX env var overrides the path)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

// The page sits beside this folder, under Library/dashboard.
const INDEX = process.env.INDEX ||
  fileURLToPath(new URL('../dashboard/index.html', import.meta.url));
// The old library folder's name, built so a rename by rule cannot rewrite the check.
const OLD_FOLDER = ['R', 'B', 'R'].join('');
const html = fs.readFileSync(INDEX, 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
const code = scripts[0] || '';

// ---------- fake DOM ----------
class FakeEl {
  constructor(tag, doc) {
    this.tagName = String(tag).toUpperCase(); this.ownerDocument = doc;
    this.children = []; this.attrs = {}; this.listeners = {}; this.dataset = {}; this.style = {};
    this._text = ''; this.value = ''; this.checked = false; this.disabled = false; this.hidden = false;
    this.className = ''; this.files = []; this.scrollTop = 0; this.scrollHeight = 0;
    const set = new Set(); this._cls = set;
    this.classList = {
      add: (...c) => c.forEach((x) => set.add(x)), remove: (...c) => c.forEach((x) => set.delete(x)),
      toggle: (c, on) => { const v = on === undefined ? !set.has(c) : !!on; v ? set.add(c) : set.delete(c); return v; },
      contains: (c) => set.has(c),
    };
  }
  append(...nodes) { for (const n of nodes) this.children.push(typeof n === 'string' ? new FakeText(n) : n); }
  appendChild(n) { this.children.push(n); return n; }
  prepend(...nodes) { this.children.unshift(...nodes.map((n) => (typeof n === 'string' ? new FakeText(n) : n))); }
  replaceChildren(...nodes) { this.children = []; this._text = ''; this.append(...nodes); }
  remove() {}
  set textContent(v) { this.children = []; this._text = String(v); }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(''); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; }
  toggleAttribute(k, on) { if (on) this.attrs[k] = ''; else delete this.attrs[k]; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  dispatch(type, extra = {}) {
    const ev = { type, target: this, currentTarget: this, preventDefault() {}, key: '', ...extra };
    return Promise.all((this.listeners[type] || []).map((fn) => fn(ev)));
  }
  click() { return this.dispatch('click'); }
  focus() {} blur() {} scrollIntoView() {} select() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
  closest() { return null; }
}
class FakeText { constructor(t) { this.textContent = String(t); this.children = []; } }

function walk(node, out = []) {
  out.push(node);
  for (const c of node.children || []) walk(c, out);
  return out;
}
const findAll = (root, pred) => walk(root).filter((n) => n instanceof FakeEl && pred(n));
const buttonByText = (root, text) => findAll(root, (n) => n.tagName === 'BUTTON' && n.textContent === text)[0];

function memStore() {
  const m = new Map();
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k), _m: m,
  };
}

function makePage({ withDom = true, fetchImpl, confirmAnswer = true } = {}) {
  const ids = new Map();
  const doc = {
    title: '', visibilityState: 'visible', listeners: {},
    documentElement: null, body: null,
    createElement: (t) => new FakeEl(t, doc), createTextNode: (t) => new FakeText(t),
    getElementById: (id) => {
      for (const root of ids.values()) { const hit = findAll(root, (n) => n.id === id)[0]; if (hit) return hit; }
      const e = new FakeEl('div', doc); e.id = id; ids.set(id, e); return e;
    },
    querySelector: () => null, querySelectorAll: () => [],
    addEventListener: (t, fn) => { (doc.listeners[t] ||= []).push(fn); },
  };
  doc.documentElement = new FakeEl('html', doc); doc.body = new FakeEl('body', doc);
  const sources = []; const downloads = []; const fetches = [];
  class FakeES {
    constructor(url) { this.url = url; this.readyState = 1; this.closed = false; sources.push(this); }
    close() { this.closed = true; this.readyState = 2; }
  }
  const ctx = {
    console, structuredClone, setTimeout, clearTimeout, setInterval, clearInterval, Blob, File, JSON, Date, TextDecoder,
    URL: Object.assign(function (...a) { return new URL(...a); }, {
      createObjectURL: (b) => { downloads.push(b); return 'blob:fake'; }, revokeObjectURL: () => {},
    }),
    URLSearchParams, encodeURIComponent, AbortController, AbortSignal, Promise,
    localStorage: memStore(), sessionStorage: memStore(),
    location: { hash: '' }, navigator: { language: 'en' },
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    confirm: () => confirmAnswer, alert: () => {},
    fetch: fetchImpl || (async () => { throw new Error('no network in tests'); }),
    EventSource: FakeES,
    listeners: {},
    addEventListener(t, fn) { (ctx.listeners[t] ||= []).push(fn); },
  };
  if (withDom) ctx.document = doc;
  ctx.window = ctx; ctx.globalThis = ctx;
  vm.createContext(ctx);
  // A file loaded with a tag rewrite: wrap fetch calls for inspection.
  const realFetch = ctx.fetch;
  ctx.fetch = (url, opts) => { fetches.push({ url, opts }); return realFetch(url, opts); };
  vm.runInContext(code, ctx, { filename: 'index.html.js' });
  const run = (expr) => vm.runInContext(expr, ctx);
  return { ctx, doc, run, sources, downloads, fetches, el: (id) => doc.getElementById(id) };
}
const plain = (x) => JSON.parse(JSON.stringify(x));
const tick = async (n = 5) => { for (let i = 0; i < n; i++) await new Promise((r) => setTimeout(r, 0)); };
async function go(p, hash) {
  p.ctx.location.hash = '#' + hash;
  await Promise.all((p.ctx.listeners.hashchange || []).map((fn) => fn({})));
  await tick();
}

// ---------- static rules ----------
test('one inline script, no external scripts or styles', () => {
  assert.equal(scripts.length, 1, 'exactly one inline <script>');
  assert.ok(!/<script[^>]+src=/i.test(html), 'no script src');
  assert.ok(!/<link[^>]+rel=["']?stylesheet/i.test(html), 'no stylesheet links');
  assert.ok(!/@import|url\(\s*["']?https?:/i.test(html), 'no CSS imports or remote urls');
});

test('Content-Security-Policy meta tag is exact', () => {
  const m = html.match(/<meta http-equiv="Content-Security-Policy" content="([^"]+)">/);
  assert.ok(m, 'CSP meta present');
  assert.equal(m[1], "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src http://127.0.0.1:*; frame-src http://127.0.0.1:47823");
});

test('the only frame the policy allows is the taskboard, on the port SETTINGS names', () => {
  const csp = html.match(/<meta http-equiv="Content-Security-Policy" content="([^"]+)">/)[1];
  const frames = csp.split(';').map((d) => d.trim()).filter((d) => d.startsWith('frame-src'));
  assert.deepEqual(frames, ['frame-src http://127.0.0.1:' + makePage({ withDom: false }).run('SETTINGS.taskboardPort')]);
  assert.equal((html.match(/<iframe\b/g) || []).length, 1, 'one iframe: the taskboard');
  assert.match(html, /\.board \{[^}]*min-height: 70vh/, 'the frame is at least 70vh tall');
});

test('no HTML injection sinks and no eval', () => {
  for (const bad of ['innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write', 'eval(', 'new Function']) {
    assert.ok(!html.includes(bad), `must not contain ${bad}`);
  }
});

test('only loopback http URLs appear', () => {
  const urls = html.match(/https?:\/\/[^\s"'`)<]+/g) || [];
  for (const u of urls) assert.match(u, /^http:\/\/127\.0\.0\.1[:/]/, `unexpected URL ${u}`);
});

test('file hygiene: LF only, under 1600 lines, no old folder name, favicon is data', () => {
  assert.ok(!html.includes('\r'), 'LF endings only');
  assert.ok(html.split('\n').length <= 1600, `lines: ${html.split('\n').length}`);
  assert.ok(!html.includes(OLD_FOLDER), 'never spells the old library folder name');
  assert.match(html, /<link rel="icon" href="data:,">/);
  assert.match(html, /^<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">/);
});

// ---------- pure functions ----------
const P = makePage({ withDom: false });
const { run } = P;
const TASK_STATES = ['open', 'partial', 'needs-owner', 'blocked', 'fixed'];
const LIB_KINDS = ['skill', 'command', 'guide', 'agent', 'tool'];

test('settings carry the name, the links and the bridge port', () => {
  assert.equal(run('SETTINGS.name'), 'Zack dev. dashboard');
  const hrefs = run('SETTINGS.links.map(l => l.href)');
  for (const h of ['../../README.md', '../../LESSONS.md', 'http://127.0.0.1:47823']) {
    assert.ok(hrefs.includes(h), `link ${h}`);
  }
  assert.equal(run('SETTINGS.bridgePort'), 47901);
  assert.equal(run('SETTINGS.taskboardPort'), 47823);
  assert.equal(run('taskboardUrl()'), 'http://127.0.0.1:47823/');
});

test('text table: both languages have the same non-empty keys, every used key exists', () => {
  const en = run('TEXT.en'); const zh = run("TEXT['zh-HK']");
  assert.deepEqual(Object.keys(zh).sort(), Object.keys(en).sort());
  for (const [k, v] of Object.entries(zh)) {
    assert.ok(typeof v === 'string' && v.trim(), `zh-HK ${k} empty`);
    assert.ok(typeof en[k] === 'string' && en[k].trim(), `en ${k} empty`);
  }
  const used = new Set();
  for (const m of code.matchAll(/\bt\(\s*'([^']+)'\s*[,)]/g)) used.add(m[1]);
  assert.ok(used.size > 100, `found ${used.size} literal keys`);
  for (const m of html.matchAll(/data-t(?:-placeholder|-aria)?="([^"]+)"/g)) used.add(m[1]);
  for (const k of run('PAGES.map(p => p.text)')) used.add(k);
  for (const l of run('SETTINGS.links')) { used.add(l.text); if (l.note) used.add(l.note); }
  for (const k of ['done', 'error', 'command', 'message', 'reasoning', 'file', 'tool', 'search', 'todo', 'exit', 'event', 'you']) used.add('kind.' + k);
  for (const k of ['running', 'active-elsewhere', 'idle', 'error']) used.add('cstate.' + k);
  for (const k of ['exec', 'cli', 'vscode', 'appServer', 'subAgent', 'other']) used.add('src.' + k);
  for (const k of ['open', 'answered', 'used']) used.add('status.' + k);
  for (const k of ['system', 'light', 'dark']) used.add('theme.' + k);
  for (const k of TASK_STATES) used.add('state.' + k);
  for (const k of LIB_KINDS) used.add('libkind.' + k);
  for (const k of run('PROJECTS')) used.add('project.' + k);
  for (const k of used) assert.ok(k in en, `missing text key ${k}`);
  // Chinese strings are really Chinese, not English copies (allowing English-only terms)
  const same = Object.keys(en).filter((k) => en[k] === zh[k] && /[a-z]{4,}/.test(en[k]) && !/^[A-Za-z .:/-]*(PCB|DATASET|Research|Library|Codex|JSON|json)/.test(en[k]));
  assert.deepEqual(same, [], 'untranslated strings');
});

test('the Taskboard note says taskboard start, on this computer only, and never npm', () => {
  // The board's own start listens on every address with no login; the taskboard launcher binds 127.0.0.1.
  for (const lng of ['en', 'zh-HK']) {
    const note = run(`TEXT['${lng}']['link.taskboardNote']`);
    assert.match(note, /taskboard start/, lng);
    assert.doesNotMatch(note, /npm/i, lng);
  }
  assert.match(run("TEXT.en['link.taskboardNote']"), /this computer only/);
  assert.match(run("TEXT['zh-HK']['link.taskboardNote']"), /這部電腦/);
  assert.ok(!/npm/i.test(html), 'the page never mentions npm');
});

const ROUTES = ['questions', 'pcb', 'dataset', 'research', 'library', 'notes', 'codex', 'taskboard', 'links'];
test('pages: the nine routes in order, the taskboard between Codex and Links', () => {
  assert.deepEqual(plain(run('PAGES.map(p => p.id)')), ROUTES);
  assert.equal(run("TEXT.en['nav.taskboard']"), 'Taskboard');
  assert.equal(run("TEXT['zh-HK']['nav.taskboard']"), '工作看板');
});

const goodQ = () => ({ version: 1, questions: [
  { id: 'q-2026-10-09-pcb-001', project: 'PCB', task: 'CO detector v0.4', asked_by: 'Peter',
    asked_at: '2026-10-09T10:00:00+08:00', question: 'Which battery holder?', status: 'open',
    answer: '', answered_at: '', used_by: '', used_at: '', used_note: '', priority: 'high' },
  { id: 'q-2026-10-09-dataset-001', project: 'DATASET', task: 'fire01', asked_by: 'Aster',
    asked_at: '2026-10-09T11:00:00+08:00', question: 'Rerun?', status: 'answered',
    answer: 'Yes', answered_at: '2026-10-09T12:00:00+08:00', used_by: '', used_at: '', used_note: '' },
  { id: 'q-2026-10-08-research-001', project: 'Research', task: 'P46', asked_by: 'Peter',
    asked_at: '2026-10-08T09:00:00+08:00', question: 'Keep P23?', status: 'used',
    answer: 'No', answered_at: '2026-10-08T10:00:00+08:00', used_by: 'Peter',
    used_at: '2026-10-08T11:00:00+08:00', used_note: 'Dropped P23 from the corpus' },
] });

test('validateQuestions accepts the design shape and names the first bad field', () => {
  assert.equal(P.ctx.validateQuestions(goodQ()), null);
  assert.equal(P.ctx.validateQuestions(run('SAMPLE_QUESTIONS')), null, 'sample is valid');
  assert.equal(P.ctx.validateQuestions(null), '$');
  assert.equal(P.ctx.validateQuestions({ version: 2, questions: [] }), 'version');
  assert.equal(P.ctx.validateQuestions({ version: 1, questions: {} }), 'questions');
  const cases = [
    [(d) => { delete d.questions[0].id; }, 'questions[0].id'],
    [(d) => { d.questions[1].status = 'done'; }, 'questions[1].status'],
    [(d) => { d.questions[2].project = 'Foo'; }, 'questions[2].project'],
    [(d) => { d.questions[1].id = d.questions[0].id; }, 'questions[1].id'],
    [(d) => { d.questions[0].answer = 5; }, 'questions[0].answer'],
    [(d) => { d.questions[0].question = ''; }, 'questions[0].question'],
    [(d) => { d.questions[0] = 'x'; }, 'questions[0]'],
  ];
  for (const [mutate, where] of cases) { const d = goodQ(); mutate(d); assert.equal(P.ctx.validateQuestions(d), where); }
});

test('applyAnswer changes only status, answer and answered_at of one question', () => {
  const before = goodQ(); const snap = JSON.stringify(before);
  const r = P.ctx.applyAnswer(before, 'q-2026-10-09-pcb-001', '  Use the BH-AA holder  ', '2026-10-09T13:00:00.000Z');
  assert.equal(r.error, undefined);
  assert.equal(JSON.stringify(before), snap, 'input not mutated');
  const exp = goodQ();
  Object.assign(exp.questions[0], { status: 'answered', answer: 'Use the BH-AA holder', answered_at: '2026-10-09T13:00:00.000Z' });
  assert.equal(JSON.stringify(r.doc), JSON.stringify(exp), 'every other field, order and question preserved');
  const again = P.ctx.applyAnswer(r.doc, 'q-2026-10-09-pcb-001', 'Changed my mind', '2026-10-09T14:00:00.000Z');
  assert.equal(again.doc.questions[0].answer, 'Changed my mind', 'answered can be revised');
  assert.equal(P.ctx.applyAnswer(goodQ(), 'nope', 'x', 'now').error, 'err.noQuestion');
  assert.equal(P.ctx.applyAnswer(goodQ(), 'q-2026-10-08-research-001', 'x', 'now').error, 'err.used');
  assert.equal(P.ctx.applyAnswer(goodQ(), 'q-2026-10-09-pcb-001', '   ', 'now').error, 'err.empty');
});

test('splitQuestions groups by status, newest first', () => {
  const d = goodQ(); d.questions.push({ ...d.questions[0], id: 'q-new', asked_at: '2026-10-09T23:00:00+08:00' });
  const s = P.ctx.splitQuestions(d);
  assert.deepEqual(plain(s.open.map((q) => q.id)), ['q-new', 'q-2026-10-09-pcb-001']);
  assert.deepEqual(plain(s.answered.map((q) => q.id)), ['q-2026-10-09-dataset-001']);
  assert.deepEqual(plain(s.used.map((q) => q.id)), ['q-2026-10-08-research-001']);
});

const goodS = () => ({ version: 1, generated_at: '2026-10-09T01:00:00+08:00',
  projects: { PCB: [{ title: 'V04-22 open', status: 'open', file: 'PCB Tools/x.md', line: 12 }], DATASET: [], Research: [] },
  library: { count: 2, entries: [{ name: 'markdown-format', kind: 'skill', collection: 'dev', summary: 'Markdown format', path: '.claude/skills/markdown-format' },
    { name: 'markitdown', kind: 'tool', collection: 'dev', summary: 'Convert documents', path: 'x' }] } });

test('validateSnapshot accepts the plan shape and names the first bad field', () => {
  assert.equal(P.ctx.validateSnapshot(goodS()), null);
  assert.equal(P.ctx.validateSnapshot(run('SAMPLE_SNAPSHOT')), null, 'sample is valid');
  const cases = [
    [(d) => { delete d.projects; }, 'projects'],
    [(d) => { delete d.projects.PCB[0].title; }, 'projects.PCB[0].title'],
    [(d) => { d.projects.PCB[0].line = '12'; }, 'projects.PCB[0].line'],
    [(d) => { d.projects.DATASET = 'x'; }, 'projects.DATASET'],
    [(d) => { d.library.entries = {}; }, 'library.entries'],
    [(d) => { d.library.entries[1].summary = 3; }, 'library.entries[1].summary'],
    [(d) => { d.version = '1'; }, 'version'],
  ];
  for (const [mutate, where] of cases) { const d = goodS(); mutate(d); assert.equal(P.ctx.validateSnapshot(d), where); }
});

const goodB = () => ({ kind: 'zack-dev-dashboard-notes', version: 1, exported_at: '2026-10-09T01:00:00Z',
  notes: [{ id: 'n1', text: 'hello', created_at: '2026-10-09T01:00:00Z' }],
  todos: [{ id: 't1', text: 'buy flux', done: false, created_at: '2026-10-09T01:00:00Z' }] });

test('validateBackup refuses malformed backups', () => {
  assert.equal(P.ctx.validateBackup(goodB()), null);
  const cases = [
    [(d) => { d.kind = 'other'; }, 'kind'],
    [(d) => { delete d.todos; }, 'todos'],
    [(d) => { d.notes[0].text = 1; }, 'notes[0].text'],
    [(d) => { d.todos[0].done = 'no'; }, 'todos[0].done'],
    [(d) => { d.notes[0] = null; }, 'notes[0]'],
  ];
  for (const [mutate, where] of cases) { const d = goodB(); mutate(d); assert.equal(P.ctx.validateBackup(d), where); }
  assert.equal(P.ctx.validateBackup([]), '$');
});

test('eventLine and itemLine turn bridge events and thread items into readable lines', () => {
  const e = (x) => P.ctx.eventLine(x);
  const i = (x) => P.ctx.itemLine(x);
  const done = (item) => ({ method: 'item/completed', params: { threadId: 'th', item } });
  assert.equal(e({ method: 'turn/started', params: {} }), null);
  assert.equal(e(done({ type: 'userMessage', content: [{ type: 'text', text: 'hi' }] })), null, 'the page logs the prompt itself');
  assert.deepEqual({ ...e(done({ type: 'agentMessage', text: 'Hello Zack' })) }, { kind: 'message', text: 'Hello Zack' });
  assert.equal(e({ method: 'item/started', params: { item: { type: 'commandExecution', command: 'ls' } } }).text, '$ ls');
  assert.equal(e({ method: 'item/started', params: { item: { type: 'agentMessage' } } }), null);
  assert.equal(e({ method: 'turn/completed', params: { turn: { status: 'completed' } } }).kind, 'done');
  assert.equal(e({ method: 'turn/completed', params: { turn: { status: 'interrupted' } } }).kind, 'exit');
  const failed = e({ method: 'turn/completed', params: { turn: { status: 'failed', error: { message: 'quota' } } } });
  assert.equal(failed.kind, 'error'); assert.match(failed.text, /quota/);
  assert.match(e({ method: 'bridge/declined', params: { request: 'item/commandExecution/requestApproval' } }).text, /requestApproval/);
  assert.equal(e({ method: 'error', params: { error: { message: 'boom' } } }).text, 'boom');
  assert.equal(e({ method: 'thread/status/changed', params: {} }), null);
  assert.equal(e(null), null);
  assert.equal(e({ type: 'item.completed' }), null, 'the old exec format is not read');
  const cmd = i({ type: 'commandExecution', command: 'git status', aggregatedOutput: 'clean\n', exitCode: 0 });
  assert.equal(cmd.kind, 'command'); assert.match(cmd.text, /git status/); assert.match(cmd.text, /clean/);
  assert.deepEqual({ ...i({ type: 'userMessage', content: [{ type: 'text', text: 'Q' }] }) }, { kind: 'you', text: 'Q' });
  const fc = i({ type: 'fileChange', changes: [{ path: 'a.txt', kind: { type: 'update' } }, { path: 'b.txt', kind: 'add' }] });
  assert.equal(fc.kind, 'file'); assert.match(fc.text, /update a\.txt/); assert.match(fc.text, /add b\.txt/);
  assert.equal(i({ type: 'reasoning', summary: [] }), null);
  assert.equal(i({ type: 'reasoning', summary: ['thinking'] }).kind, 'reasoning');
  assert.equal(i({ type: 'mcpToolCall', server: 's', tool: 't', status: 'completed' }).text, 's.t completed');
  assert.equal(i({ type: 'somethingNew' }).kind, 'event');
});

test('matches filters case-insensitively across fields', () => {
  const item = { title: 'Battery Holder', status: 'open', file: 'PCB Tools/a.md' };
  assert.equal(P.ctx.matches(item, ['title', 'file'], 'battery'), true);
  assert.equal(P.ctx.matches(item, ['title', 'file'], 'pcb tools'), true);
  assert.equal(P.ctx.matches(item, ['title'], 'pcb'), false);
  assert.equal(P.ctx.matches(item, ['title'], '  '), true);
});

test('data words: English shows the value as it is, zh-HK through the table, unknown values raw', () => {
  const en = run('TEXT.en'); const zh = run("TEXT['zh-HK']");
  for (const k of TASK_STATES) assert.equal(en['state.' + k], k, `en state.${k}`);
  for (const k of LIB_KINDS) assert.equal(en['libkind.' + k], k, `en libkind.${k}`);
  for (const k of run('PROJECTS')) assert.equal(en['project.' + k], k, `en project.${k}`);
  for (const k of [...TASK_STATES.map((s) => 'state.' + s), ...LIB_KINDS.map((s) => 'libkind.' + s)]) {
    assert.match(zh[k], /[一-鿿]|^Agent$/, `zh-HK ${k} is Chinese`);
  }
  assert.deepEqual(plain(run("PROJECTS.map(p => TEXT['zh-HK']['project.' + p])")),
    ['PCB', 'DATASET', '研究', '工具庫', '一般']);
  const Z = makePage({ withDom: false });
  assert.equal(Z.ctx.word('state.', 'needs-owner'), 'needs-owner', 'English by default');
  Z.run("lang = 'zh-HK'");
  assert.equal(Z.ctx.word('state.', 'blocked'), zh['state.blocked']);
  assert.equal(Z.ctx.word('project.', 'Research'), '研究');
  for (const odd of ['current', 'plugin', 'constructor', '__proto__', 'toString']) {
    assert.equal(Z.ctx.word('state.', odd), odd, `unknown ${odd} shown raw`);
  }
});

// ---------- smoke run against the fake DOM ----------
test('boots on sample data, labels it, shows the band and every route renders', async () => {
  const p = makePage();
  await tick();
  assert.match(p.el('band').textContent, /2/, 'band shows the open count');
  assert.match(p.el('band').textContent, /sample/i, 'band says sample');
  for (const id of ROUTES) {
    await go(p, id);
    assert.ok(p.el('page').children.length > 0, `route ${id} renders`);
  }
  await go(p, 'links');
  const text = p.el('page').textContent;
  assert.match(text, /taskboard start/);
  assert.ok(findAll(p.el('page'), (n) => n.tagName === 'A' && n.href === 'http://127.0.0.1:47823' && n.target === '_blank').length === 1);
  // The sidebar's Codex Taskboard link opens the page inside the dashboard, not a new tab.
  const side = findAll(p.el('sideLinks'), (n) => n.tagName === 'A' && n.textContent === p.run("t('link.taskboard')"));
  assert.equal(side.length, 1);
  assert.equal(side[0].href, '#taskboard');
  assert.equal(side[0].target, undefined, 'stays in this tab');
  assert.equal(p.el('connectBtn').hidden, true, 'no directory API: connect hidden');
  assert.equal(p.el('noApiNote').hidden, false, 'fallback note shown');
});

test('a hash that is not a page (the skip link) keeps the current page', async () => {
  const p = makePage();
  await go(p, 'notes');
  const notesH1 = p.run("t('nav.notes')");
  assert.equal(p.el('page').children[0].textContent, notesH1);
  await go(p, 'main');
  assert.equal(p.el('page').children[0].textContent, notesH1);
});

test('answering in fallback mode updates memory and the download carries it', async () => {
  const p = makePage();
  const input = p.el('fileQuestions');
  input.files = [new File([JSON.stringify(goodQ())], 'questions.json')];
  await input.dispatch('change'); await tick();
  assert.equal(p.run('state.qSample'), false, 'real questions, not the sample');
  await go(p, 'questions');
  const open = p.run('splitQuestions(state.questions).open');
  const box = findAll(p.el('page'), (n) => n.tagName === 'TEXTAREA' && n.dataset.qid === open[0].id)[0];
  assert.ok(box, 'answer box for the newest open question');
  box.value = 'Use footprint A'; await box.dispatch('input');
  await buttonByText(p.el('page'), p.run("t('q.save')")).click(); await tick();
  const q = p.run('state.questions.questions').find((x) => x.id === open[0].id);
  assert.equal(q.status, 'answered'); assert.equal(q.answer, 'Use footprint A'); assert.ok(q.answered_at);
  await buttonByText(p.el('page'), p.run("t('files.download')")).click(); await tick();
  const blob = p.downloads.at(-1); const doc = JSON.parse(await blob.text());
  assert.equal(p.ctx.validateQuestions(doc), null);
  assert.equal(doc.questions.find((x) => x.id === open[0].id).answer, 'Use footprint A');
});

test('importing a malformed questions.json is refused with a message', async () => {
  const p = makePage();
  await go(p, 'questions');
  const input = p.el('fileQuestions');
  input.files = [new File(['{"version":1,"questions":[{"id":1}]}'], 'questions.json')];
  await input.dispatch('change'); await tick();
  assert.match(p.el('message').textContent, /questions\[0\]\.id/);
  assert.equal(p.run('state.qSample'), true, 'sample still in place');
  input.files = [new File([JSON.stringify(goodQ())], 'questions.json')];
  await input.dispatch('change'); await tick();
  assert.equal(p.run('state.qSample'), false);
  assert.equal(p.run('state.questions.questions.length'), 3);
});

test('notes persist, back up, and a malformed restore is refused', async () => {
  const p = makePage();
  await go(p, 'notes');
  const ta = p.el('noteInput'); ta.value = 'Remember the flux'; await ta.dispatch('input');
  await buttonByText(p.el('page'), p.run("t('notes.add')")).click(); await tick();
  const saved = JSON.parse(p.ctx.localStorage.getItem('zdd.notes'));
  assert.equal(saved.notes[0].text, 'Remember the flux');
  await buttonByText(p.el('page'), p.run("t('notes.export')")).click(); await tick();
  const backup = JSON.parse(await p.downloads.at(-1).text());
  assert.equal(p.ctx.validateBackup(backup), null);
  const input = p.el('fileBackup');
  input.files = [new File(['{"kind":"zack-dev-dashboard-notes","version":1,"notes":"x","todos":[]}'], 'b.json')];
  await input.dispatch('change'); await tick();
  assert.match(p.el('message').textContent, /notes/);
  assert.equal(JSON.parse(p.ctx.localStorage.getItem('zdd.notes')).notes.length, 1, 'nothing replaced');
  backup.notes = []; backup.todos = [{ id: 't9', text: 'restored', done: true, created_at: 'x' }];
  input.files = [new File([JSON.stringify(backup)], 'b.json')];
  await input.dispatch('change'); await tick();
  const after = JSON.parse(p.ctx.localStorage.getItem('zdd.notes'));
  assert.equal(after.notes.length, 0); assert.equal(after.todos[0].text, 'restored');
});

test('language switch is remembered and changes the text', async () => {
  const p = makePage();
  await go(p, 'questions');
  const en = p.el('page').textContent;
  await p.el('langBtn').click(); await tick();
  assert.equal(p.ctx.localStorage.getItem('zdd.lang'), 'zh-HK');
  assert.equal(p.doc.documentElement.lang, 'zh-HK');
  assert.notEqual(p.el('page').textContent, en);
});

const importInto = async (p, inputId, doc) => {
  const input = p.el(inputId);
  input.files = [new File([JSON.stringify(doc)], inputId === 'fileQuestions' ? 'questions.json' : 'snapshot.json')];
  await input.dispatch('change'); await tick();
};
const tagTexts = (root) => findAll(root, (n) => n.tagName === 'SPAN' && /^tag( |$)/.test(n.className)).map((n) => n.textContent);
const generalQ = () => ({ id: 'q-2026-10-09-general-001', project: 'General', task: 'x', asked_by: 'Aster',
  asked_at: '2026-10-09T23:00:00+08:00', question: 'New one?', status: 'open', answer: '', answered_at: '',
  used_by: '', used_at: '', used_note: '' });

test('zh-HK shows statuses, kinds and project names through the table; the data stays English', async () => {
  const p = makePage();
  await p.el('langBtn').click(); await tick();
  const q = goodQ(); q.questions.push(generalQ());
  await importInto(p, 'fileQuestions', q);
  await go(p, 'questions');
  const band = p.el('band').textContent;
  assert.match(band, /一般 · New one\?/, 'band names the project in Chinese');
  assert.doesNotMatch(band, /General/);
  const metas = findAll(p.el('page'), (n) => n.tagName === 'DIV' && n.className === 'meta').map((n) => n.textContent).join('\n');
  assert.match(metas, /一般 · x/); assert.match(metas, /研究 · P46/); assert.match(metas, /PCB · CO detector/);
  assert.doesNotMatch(metas, /(General|Research) ·/);
  const qTags = tagTexts(p.el('page'));
  for (const s of ['open', 'answered', 'used']) assert.ok(qTags.includes(p.run(`t('status.${s}')`)), `status ${s} in Chinese`);
  for (const s of ['open', 'answered', 'used']) assert.ok(!qTags.includes(s), `no raw ${s}`);
  // Answering in Chinese writes English data.
  const box = findAll(p.el('page'), (n) => n.tagName === 'TEXTAREA' && n.dataset.qid === 'q-2026-10-09-general-001')[0];
  box.value = '可以'; await box.dispatch('input');
  const card = findAll(p.el('page'), (n) => n.tagName === 'ARTICLE' && findAll(n, (m) => m === box).length)[0];
  await buttonByText(card, p.run("t('q.save')")).click(); await tick();
  await buttonByText(p.el('page'), p.run("t('files.download')")).click(); await tick();
  const saved = JSON.parse(await p.downloads.at(-1).text());
  assert.deepEqual(saved.questions.map((x) => x.project), ['PCB', 'DATASET', 'Research', 'General']);
  assert.deepEqual(saved.questions.map((x) => x.status), ['open', 'answered', 'used', 'answered']);
  // Task pages and the library: the sample snapshot first, then one with values the table lacks.
  await go(p, 'pcb');
  assert.deepEqual(tagTexts(p.el('page')), [p.run("t('sample.tag')"), '未完成', '待負責人決定', '受阻']);
  await go(p, 'research');
  assert.deepEqual(tagTexts(p.el('page')).slice(1), ['部分完成']);
  await go(p, 'library');
  assert.deepEqual(tagTexts(p.el('page')).slice(1), ['技能', '工具', '工具', '技能']);
  const s = goodS(); s.projects.PCB[0].status = 'current';
  s.library.entries.push({ name: 'odd', kind: 'plugin' });
  await importInto(p, 'fileSnapshot', s);
  await go(p, 'pcb');
  assert.deepEqual(tagTexts(p.el('page')), ['current']);
  await go(p, 'library');
  assert.deepEqual(tagTexts(p.el('page')), ['技能', '工具', 'plugin']);
});

test('an empty library says so, a filter miss says so, and the snapshot note shows in both languages', async () => {
  const p = makePage();
  const note = 'library: no index yet';
  const s = goodS(); s.library = { count: 0, entries: [] }; s.note = note;
  await importInto(p, 'fileSnapshot', s);
  assert.equal(p.run("TEXT.en['lib.empty']"), 'No library entries in this snapshot.');
  for (const lng of ['en', 'zh-HK']) {
    if (lng === 'zh-HK') { await p.el('langBtn').click(); await tick(); }
    const has = (key, vars) => p.el('page').textContent.includes(p.run(`t('${key}', ${JSON.stringify(vars || {})})`));
    await go(p, 'library');
    assert.ok(has('lib.empty'), `${lng}: empty-library message`);
    assert.ok(!has('tasks.noMatch'), `${lng}: not the filter message`);
    assert.ok(has('tasks.note', { note }), `${lng}: note on the library page`);
    for (const id of ['pcb', 'dataset', 'research']) {
      await go(p, id);
      assert.ok(has('tasks.note', { note }), `${lng}: note on ${id}`);
    }
  }
  await importInto(p, 'fileSnapshot', goodS());
  await go(p, 'library');
  const box = p.el('filter-library'); box.value = 'zzz'; await box.dispatch('input');
  const text = p.el('page').textContent;
  assert.ok(text.includes(p.run("t('tasks.noMatch')")), 'a filter miss names the filter');
  assert.ok(!text.includes(p.run("t('lib.empty')")));
  assert.ok(!text.includes(note), 'no note when the snapshot has none');
});

// A fake bridge for the Codex panel: JSON routes, and an event stream the test feeds.
function fakeBridge() {
  const calls = []; const feed = []; let wake = null;
  const push = (event) => {
    feed.push(new TextEncoder().encode('data: ' + JSON.stringify(event) + '\n\n'));
    if (wake) { wake(); wake = null; }
  };
  const routes = {
    '/health': { ok: true, folder: 'C:/proj', codex: 'codex', appServer: { up: true, userAgent: 'dev-dashboard-bridge/0.160.0 (Windows)' } },
    '/account': { signedIn: true, type: 'chatgpt', plan: 'plus',
      rateLimits: { primary: { usedPercent: 78, windowDurationMins: 10080, resetsAt: 1791952884 }, secondary: null } },
    '/threads': { threads: [
      { id: 'th-live', name: null, preview: 'Aster audits the library', source: 'exec', cwd: 'C:/dev', updatedAt: 1791530000, state: 'active-elsewhere' },
      { id: 'th-old', name: 'Old work', preview: 'x', source: 'subAgent', nickname: 'Volta', cwd: 'C:/proj', updatedAt: 1791000000, state: 'idle' }] },
    '/thread': { id: 'th-old', name: 'Old work', preview: 'x', source: 'cli', cwd: 'C:/proj', state: 'idle', turns: [
      { id: 't1', status: 'completed', items: [
        { type: 'userMessage', content: [{ type: 'text', text: 'What changed?' }] }, { type: 'agentMessage', text: 'Two files.' }] }] },
    '/run': { thread: 'th-old', turn: 'turn-9' }, '/stop': { ok: true },
    '/login': { authUrl: 'https://auth.openai.com/oauth/x', loginId: 'l1' },
  };
  const bridge = { calls, push, routes, hold: null };
  const fetchImpl = async (url, opts = {}) => {
    calls.push({ url, opts });
    const path = new URL(url).pathname;
    if (path === '/run' && bridge.hold) await bridge.hold; // a test holds the run reply back
    if (path !== '/events') return { ok: true, status: 200, json: async () => structuredClone(routes[path]) };
    const read = async () => {
      while (!feed.length) await new Promise((r) => { wake = r; });
      return { value: feed.shift(), done: false };
    };
    return { ok: true, status: 200, body: { getReader: () => ({ read }) } };
  };
  return Object.assign(bridge, { fetchImpl });
}

async function typePrompt(p, text) {
  p.el('codexPrompt').value = text; await p.el('codexPrompt').dispatch('input');
}

async function connectCodex(b) {
  const p = makePage({ fetchImpl: b.fetchImpl });
  p.opened = []; p.ctx.open = (...args) => p.opened.push(args);
  await go(p, 'codex');
  p.el('bridgeKey').value = 'secret-key'; await p.el('bridgeKey').dispatch('input');
  assert.equal(p.ctx.sessionStorage.getItem('zdd.bridgeKey'), 'secret-key');
  await buttonByText(p.el('page'), p.run("t('codex.check')")).click(); await tick(10);
  return p;
}

test('codex panel: connect, account, activity, open a thread, run, stream, stop, all with the key', async () => {
  const b = fakeBridge();
  const p = await connectCodex(b);
  const text = () => p.el('page').textContent;
  assert.match(b.calls[0].url, /^http:\/\/127\.0\.0\.1:47901\/health$/);
  assert.match(text(), /C:\/proj · Codex 0\.160\.0/);
  assert.match(text(), /plus/); assert.match(text(), /7-day window: 78% used/);
  assert.match(text(), /Aster audits the library/);
  assert.ok(text().includes(p.run("t('cstate.active-elsewhere')")));
  assert.match(text(), /Sub-agent Volta/);
  assert.ok(!text().includes(p.run("t('codex.signIn')")), 'no sign-in button while signed in');
  // Open a thread: its last turns read as a log, and a prompt continues it.
  const row = findAll(p.el('codexThreads'), (n) => n.tagName === 'LI' && n.textContent.includes('Old work'))[0];
  await buttonByText(row, p.run("t('codex.open')")).click(); await tick();
  assert.match(b.calls.at(-1).url, /\/thread\?id=th-old$/);
  assert.match(p.el('codexView').textContent, /What changed\?/);
  assert.match(p.el('codexView').textContent, /Two files\./);
  assert.equal(p.el('codexThread').value, 'th-old');
  p.el('codexPrompt').value = 'Say hi'; await p.el('codexPrompt').dispatch('input');
  await buttonByText(p.el('page'), p.run("t('codex.run')")).click(); await tick();
  const runCall = b.calls.find((c) => c.url.endsWith('/run'));
  assert.deepEqual(JSON.parse(runCall.opts.body), { prompt: 'Say hi', sandbox: 'read-only', thread: 'th-old' });
  b.push({ method: 'item/completed', params: { threadId: 'th-old', item: { type: 'agentMessage', text: 'Hi Zack' } } });
  b.push({ method: 'item/completed', params: { threadId: 'th-other', item: { type: 'agentMessage', text: 'Not mine' } } });
  await tick();
  assert.match(p.el('codexLog').textContent, /Hi Zack/);
  assert.ok(!p.el('codexLog').textContent.includes('Not mine'), 'another thread stays out of the run log');
  await buttonByText(p.el('page'), p.run("t('codex.stop')")).click(); await tick();
  const stopCall = b.calls.find((c) => c.url.endsWith('/stop'));
  assert.deepEqual(JSON.parse(stopCall.opts.body), { thread: 'th-old', turn: 'turn-9' });
  b.push({ method: 'turn/completed', params: { threadId: 'th-old', turn: { id: 'turn-9', status: 'interrupted' } } }); await tick();
  assert.equal(p.run('codex.running'), null);
  assert.ok(p.el('codexLog').textContent.includes(p.run("t('log.interrupted')")));
  b.push({ method: 'bridge/declined', params: { request: 'item/commandExecution/requestApproval' } }); await tick();
  assert.match(p.el('codexLog').textContent, /requestApproval/);
  for (const c of b.calls) {
    assert.equal(c.opts.headers['X-Bridge-Key'], 'secret-key', c.url);
    assert.ok(!c.url.includes('secret-key'), 'the key never goes in an address');
  }
  assert.ok(!p.el('codexLog').textContent.includes('secret-key'), 'key never logged');
});

test('codex panel: signed out, Sign in opens the ChatGPT page and the finish refreshes the account', async () => {
  const b = fakeBridge();
  b.routes['/account'] = { signedIn: false, type: null, plan: null, rateLimits: null };
  const p = await connectCodex(b);
  assert.ok(p.el('codexAccount').textContent.includes(p.run("t('codex.notSignedIn')")));
  await buttonByText(p.el('page'), p.run("t('codex.signIn')")).click(); await tick();
  const login = b.calls.find((c) => c.url.endsWith('/login'));
  assert.equal(login.opts.method, 'POST');
  assert.deepEqual(p.opened, [['https://auth.openai.com/oauth/x', '_blank', 'noopener']]);
  b.routes['/account'] = { signedIn: true, type: 'chatgpt', plan: 'plus', rateLimits: null };
  b.push({ method: 'account/login/completed', params: { loginId: 'l1', success: true } }); await tick(10);
  assert.match(p.el('codexAccount').textContent, /plus/);
  assert.equal(p.el('message').textContent, p.run("t('codex.signInDone')"));
});

test('codex panel: a turn done before its run reply frees Run, and a double click sends one prompt', async () => {
  const b = fakeBridge();
  const p = await connectCodex(b);
  let release; b.hold = new Promise((r) => { release = r; });
  await typePrompt(p, 'Quick');
  const run = buttonByText(p.el('page'), p.run("t('codex.run')"));
  run.click(); run.click(); await tick();
  assert.equal(b.calls.filter((c) => c.url.endsWith('/run')).length, 1, 'one prompt for two clicks');
  assert.equal(p.el('codexRun').disabled, true, 'Run is off while the prompt starts');
  b.push({ method: 'item/completed', params: { threadId: 'th-old', turnId: 'turn-9', item: { type: 'agentMessage', text: 'Fast reply' } } });
  b.push({ method: 'turn/completed', params: { threadId: 'th-old', turn: { id: 'turn-9', status: 'completed' } } });
  await tick();
  release(); await tick(10);
  assert.equal(p.run('codex.running'), null);
  assert.equal(p.el('codexRun').disabled, false);
  assert.match(p.el('codexLog').textContent, /Fast reply/);
  assert.ok(p.el('codexLog').textContent.includes(p.run("t('log.done')")));
});

test('codex panel: a completion for an older turn of the same thread leaves the new run alone', async () => {
  const b = fakeBridge();
  const p = await connectCodex(b);
  await typePrompt(p, 'Again');
  await buttonByText(p.el('page'), p.run("t('codex.run')")).click(); await tick();
  b.push({ method: 'turn/completed', params: { threadId: 'th-old', turn: { id: 'turn-1', status: 'completed' } } }); await tick();
  assert.deepEqual(plain(p.run('codex.running')), { thread: 'th-old', turn: 'turn-9' });
});

test('codex panel: Codex stopping ends the run as unknown and says why', async () => {
  const b = fakeBridge();
  const p = await connectCodex(b);
  await typePrompt(p, 'Long');
  await buttonByText(p.el('page'), p.run("t('codex.run')")).click(); await tick();
  assert.ok(p.run('codex.running'));
  b.push({ method: 'bridge/appServer', params: { up: false, error: 'ended with code 1' } }); await tick();
  assert.equal(p.run('codex.running'), null);
  assert.equal(p.el('codexRun').disabled, false);
  assert.match(p.el('codexLog').textContent, /ended with code 1/);
});

test('codex panel: a new port or key drops the old stream, and the key never stays in the input', async () => {
  const b = fakeBridge();
  const p = await connectCodex(b);
  assert.equal(p.el('bridgeKey').value, '', 'the key is not put back into the page');
  assert.equal(p.el('bridgeKey').placeholder, p.run("t('codex.keySet')"));
  const first = b.calls.find((c) => c.url.endsWith('/events'));
  assert.equal(first.opts.signal.aborted, false);
  p.el('bridgePort').value = '47999'; await p.el('bridgePort').dispatch('change');
  assert.equal(first.opts.signal.aborted, true);
  assert.equal(p.run('codex.stream'), null);
});

test('codex panel: a bridge whose Codex did not start says why', async () => {
  const b = fakeBridge();
  b.routes['/health'] = { ok: true, folder: 'C:/proj', codex: 'codex', appServer: { up: false, error: 'spawn codex ENOENT' } };
  const p = await connectCodex(b);
  assert.match(p.el('page').textContent, /spawn codex ENOENT/);
  assert.ok(!b.calls.some((c) => c.url.endsWith('/threads')), 'nothing else is asked of a bridge without Codex');
});

function fakeDir(files) {
  return {
    name: 'dashboard', writes: [],
    async getFileHandle(name) {
      if (!(name in files)) throw Object.assign(new Error('missing'), { name: 'NotFoundError' });
      const dir = this;
      return {
        async getFile() { return { text: async () => files[name] }; },
        async createWritable() {
          let buf = '';
          return { async write(s) { buf += s; }, async close() { files[name] = buf; dir.writes.push(name); } };
        },
      };
    },
    async queryPermission() { return 'granted'; }, async requestPermission() { return 'granted'; },
  };
}

test('connected folder: reads both files, re-reads before writing, keeps agent-added questions', async () => {
  const files = { 'questions.json': JSON.stringify(goodQ(), null, 2), 'snapshot.json': JSON.stringify(goodS()) };
  const dir = fakeDir(files);
  const p = makePage();
  p.ctx.showDirectoryPicker = async (opts) => { assert.equal(opts.mode, 'readwrite'); return dir; };
  p.run('renderAll()');
  assert.equal(p.el('connectBtn').hidden, false, 'connect shown when the API exists');
  await p.el('connectBtn').click(); await tick();
  assert.equal(p.run('state.qSample'), false); assert.equal(p.run('state.sSample'), false);
  assert.match(p.el('sourceStatus').textContent, /dashboard/);
  // An agent adds a question after the page loaded the file.
  const onDisk = goodQ();
  onDisk.questions.push({ id: 'q-2026-10-09-general-001', project: 'General', task: 'x', asked_by: 'Aster',
    asked_at: '2026-10-09T12:30:00+08:00', question: 'New one?', status: 'open', answer: '', answered_at: '',
    used_by: '', used_at: '', used_note: '' });
  files['questions.json'] = JSON.stringify(onDisk, null, 2);
  await go(p, 'questions');
  const box = findAll(p.el('page'), (n) => n.tagName === 'TEXTAREA' && n.dataset.qid === 'q-2026-10-09-pcb-001')[0];
  box.value = 'Holder B'; await box.dispatch('input');
  const card = findAll(p.el('page'), (n) => n.tagName === 'ARTICLE' && findAll(n, (m) => m === box).length)[0];
  await buttonByText(card, p.run("t('q.save')")).click(); await tick();
  assert.deepEqual(dir.writes, ['questions.json']);
  const written = JSON.parse(files['questions.json']);
  assert.equal(written.questions.length, 4, 'the agent-added question survived');
  const exp = structuredClone(onDisk);
  Object.assign(exp.questions[0], { status: 'answered', answer: 'Holder B', answered_at: written.questions[0].answered_at });
  assert.deepEqual(written, exp, 'only the answered fields changed');
  assert.ok(!Number.isNaN(Date.parse(written.questions[0].answered_at)), 'answered_at is an ISO time');
  assert.ok(files['questions.json'].endsWith('}\n'));
});

test('sample questions can be answered to try the page, but are never downloaded or written', async () => {
  const p = makePage();
  await go(p, 'questions');
  for (const lng of ['en', 'zh-HK']) {
    if (lng === 'zh-HK') { await p.el('langBtn').click(); await tick(); }
    const dl = buttonByText(p.el('page'), p.run("t('files.download')"));
    assert.equal(dl.disabled, true, `${lng}: download is off while the sample shows`);
    const reason = p.run("t('files.sampleNoDownload')");
    assert.ok(reason !== 'files.sampleNoDownload' && p.el('page').textContent.includes(reason), `${lng}: the reason is shown`);
  }
  const id = p.run('splitQuestions(state.questions).open[0].id');
  const answer = async () => {
    const box = findAll(p.el('page'), (n) => n.tagName === 'TEXTAREA' && n.dataset.qid === id)[0];
    box.value = 'Just trying'; await box.dispatch('input');
    const card = findAll(p.el('page'), (n) => n.tagName === 'ARTICLE' && findAll(n, (m) => m === box).length)[0];
    await buttonByText(card, p.run("t('q.save')")).click(); await tick();
  };
  await answer();
  assert.equal(p.run(`state.questions.questions.find(q => q.id === '${id}').status`), 'answered', 'trying it still works');
  assert.equal(p.run('state.dirty'), false, 'a sample answer is nothing to keep');
  assert.equal(p.el('message').textContent, p.run("t('q.savedSample')"));
  await buttonByText(p.el('page'), p.run("t('files.download')")).click(); await tick();
  p.run('downloadQuestions()'); await tick();
  assert.equal(p.downloads.length, 0, 'neither a click nor a direct call downloads the sample');
  // A folder connected while its questions.json is missing keeps the sample; a file that appears
  // later with a matching id must still never receive an answer typed on a sample question.
  const files = { 'snapshot.json': JSON.stringify(goodS()) };
  const dir = fakeDir(files);
  p.ctx.showDirectoryPicker = async () => dir;
  await p.el('connectBtn').click(); await tick();
  assert.equal(p.run('state.qSample'), true);
  const real = goodQ(); real.questions[0].id = id;
  files['questions.json'] = JSON.stringify(real, null, 2);
  await go(p, 'questions');
  await answer();
  assert.deepEqual(dir.writes, [], 'nothing written to the folder');
  assert.equal(JSON.parse(files['questions.json']).questions[0].answer, '', 'the real file is untouched');
});

test('connected folder: a missing snapshot.json is named, questions still load', async () => {
  const files = { 'questions.json': JSON.stringify(goodQ()) };
  const p = makePage();
  p.ctx.showDirectoryPicker = async () => fakeDir(files);
  await p.el('connectBtn').click(); await tick();
  assert.equal(p.run('state.qSample'), false);
  assert.equal(p.run('state.sSample'), true);
  assert.match(p.el('message').textContent, /snapshot\.json/);
});

test('codex panel: a failed health check explains how to start the bridge', async () => {
  const p = makePage();
  await go(p, 'codex');
  await buttonByText(p.el('page'), p.run("t('codex.check')")).click(); await tick();
  assert.match(p.el('page').textContent, /node codex-bridge\.mjs --folder/);
});

// ---------- the taskboard page ----------
const BOARD = 'http://127.0.0.1:47823/';
const probes = (p) => p.fetches.filter((f) => f.url === BOARD);
const pageHas = (p, key) => p.el('page').textContent.includes(p.run(`t('${key}')`));

test('taskboard: when it does not answer, a card in both languages says how to start it', async () => {
  const p = makePage(); // every fetch fails, as when nothing listens on the port
  await go(p, 'taskboard');
  assert.equal(probes(p).length, 1, 'probed once on arrival');
  const { opts } = probes(p)[0];
  assert.equal(opts.mode, 'no-cors'); assert.equal(opts.cache, 'no-store'); assert.ok(opts.signal, 'with a timeout');
  assert.equal(p.el('boardFrame').hidden, true, 'no frame');
  assert.ok(!p.el('boardFrame').src, 'nothing loaded');
  for (const lng of ['en', 'zh-HK']) {
    if (lng === 'zh-HK') { await p.el('langBtn').click(); await tick(); }
    assert.ok(pageHas(p, 'board.down'), `${lng}: not running`);
    assert.ok(pageHas(p, 'board.local'), `${lng}: this computer only`);
    assert.ok(buttonByText(p.el('page'), p.run("t('board.check')")), `${lng}: Check again`);
  }
  assert.equal(probes(p).length, 1, 'switching language does not probe again');
  assert.equal(p.run("TEXT.en['board.down']"), 'The taskboard is not running. Start it on this computer with: taskboard start');
  assert.match(p.run("TEXT.en['board.local']"), /this computer only/);
  assert.match(p.run("TEXT['zh-HK']['board.down']"), /taskboard start/);
  assert.match(p.run("TEXT['zh-HK']['board.local']"), /這部電腦/);
});

test('taskboard: when it answers, it shows inside the page with a new-tab link and Check again', async () => {
  let up = true, read = false;
  const fetchImpl = async () => {
    if (!up) throw new TypeError('Failed to fetch');
    return { type: 'opaque', ok: false, status: 0, text: async () => { read = true; }, json: async () => { read = true; } };
  };
  const p = makePage({ fetchImpl });
  await go(p, 'taskboard');
  const frame = p.el('boardFrame');
  assert.equal(frame.hidden, false, 'the frame shows');
  assert.equal(frame.src, BOARD);
  assert.equal(frame.title, p.run("t('link.taskboard')"));
  assert.equal(read, false, 'the reply is never read');
  assert.ok(!pageHas(p, 'board.down'));
  const open = findAll(p.el('page'), (n) => n.tagName === 'A' && n.textContent === p.run("t('board.open')"));
  assert.equal(open.length, 1);
  assert.equal(open[0].href, BOARD); assert.equal(open[0].target, '_blank'); assert.equal(open[0].rel, 'noopener noreferrer');
  // Other pages hide the frame without unloading it, and re-renders never reload it.
  await go(p, 'notes'); assert.equal(frame.hidden, true);
  await go(p, 'taskboard'); assert.equal(frame.hidden, false);
  frame.src = 'kept'; await p.el('langBtn').click(); await tick();
  assert.equal(frame.src, 'kept', 'a language switch does not reload the board');
  // Stopped since: Check again swaps the frame for the card.
  up = false;
  await buttonByText(p.el('page'), p.run("t('board.check')")).click(); await tick();
  assert.equal(frame.hidden, true);
  assert.ok(pageHas(p, 'board.down'));
  // Started again: Check again loads it afresh.
  up = true;
  await buttonByText(p.el('page'), p.run("t('board.check')")).click(); await tick();
  assert.equal(frame.hidden, false); assert.equal(frame.src, BOARD);
  assert.equal(probes(p).length, 3, 'one probe on arrival and one per Check again');
});

test('taskboard: a board that never answers counts as not running after 2 seconds', async () => {
  const fetchImpl = (url, opts) => new Promise((resolve, reject) => {
    opts.signal.addEventListener('abort', () => reject(opts.signal.reason));
  });
  const p = makePage({ fetchImpl });
  await go(p, 'taskboard');
  assert.ok(pageHas(p, 'board.checking'), 'checking at first');
  assert.equal(buttonByText(p.el('page'), p.run("t('board.check')")).disabled, true, 'one check at a time');
  await new Promise((r) => setTimeout(r, 1500));
  assert.ok(pageHas(p, 'board.checking'), 'still checking at 1.5 s');
  await new Promise((r) => setTimeout(r, 1000));
  assert.ok(pageHas(p, 'board.down'), 'not running after 2 s');
  assert.equal(p.el('boardFrame').hidden, true);
});
