import { vi } from 'vitest';
import type { AgentRow, ClaudeSession, ClaudeView, CodexStatus, Question, Step, Thread, ThreadView } from './api';

// What the Codex tests share: the server's answers as the API contract gives
// them (Setup/superpowers/plans/2026-10-10-dashboard-wave-2.md), a fetch that
// serves them, and an EventSource the tests drive, since jsdom has none.

export const STATUS: CodexStatus = {
  up: true, version: '0.162.0', signedIn: true, type: 'chatgpt', plan: 'plus', code: 'ok',
  rateLimits: {
    primary: { usedPercent: 40, windowDurationMins: 10080, resetsAt: 1900000000 },
    secondary: { usedPercent: 12, windowDurationMins: 300, resetsAt: 1790003600 },
  },
};

export const thread = (id: string, extra: Partial<Thread> = {}): Thread => ({
  id, name: null, preview: `first prompt of ${id}`, source: 'cli', nickname: null, cwd: 'C:\\work\\dev',
  inDev: true, createdAt: 1790000000, updatedAt: 1790000500, state: 'idle', turn: null, ...extra,
});

export const question = (id: string, extra: Partial<Question> = {}): Question => ({
  id, project: 'Library', task: 'Wave 2', asked_by: 'Aster', asked_at: '2026-10-10T10:00:00+08:00',
  question: 'Which sandbox?', status: 'open', answer: '', answered_at: '', used_by: '', used_at: '', used_note: '', ...extra,
});

// A Claude session as GET api/claude lists it (Setup/superpowers/plans/2026-10-15-dashboard-wave-4.md).
export const claudeSession = (id: string, extra: Partial<ClaudeSession> = {}): ClaudeSession => ({
  id, title: `session ${id}`, cwd: 'C:\\work\\dev', state: 'idle', source: 'claude-desktop', updatedAt: '2026-10-15T02:00:00Z', ...extra,
});
export const step = (kind: Step['kind'], text: string, extra: Partial<Step> = {}): Step => ({ kind, text, tool: null, error: false, at: '2026-10-15T01:59:00Z', ...extra });
export const agentRow = (id: string, extra: Partial<AgentRow> = {}): AgentRow => ({
  id, title: `agent ${id}`, type: 'general-purpose', run: null, state: 'idle', updatedAt: '2026-10-15T01:58:00Z', ...extra,
});

// A session's view as GET api/claude/sessions/<id> answers it: one step of each kind, one subagent, one run.
export const CLAUDE_ID = '0b1c2d3e-0000-4000-8000-00000000c001';
export const CLAUDE_VIEW: ClaudeView = {
  ...claudeSession(CLAUDE_ID, { title: 'Build wave 4', source: 'cli' }),
  branch: 'worktree-dashboard-wave-4',
  commits: [{ hash: 'c487c56', at: '2026-10-15T01:00:00Z', subject: 'Plan dashboard wave 4' }],
  readable: true,
  steps: [
    step('prompt', 'Build the Claude page'),
    step('thinking', ''),
    step('reply', 'Reading the plan first.'),
    step('tool', 'npm test', { tool: 'Bash' }),
    step('result', '2 failed', { tool: 'Bash', error: true }),
  ],
  agents: [agentRow('agent-a1', { title: 'Review the server track', state: 'working' })],
  runs: [{
    id: 'wf_build-1', name: 'dashboard-wave-4', status: 'running', summary: 'Two tracks, one worktree', agentCount: 2,
    startedAt: '2026-10-15T01:00:00Z', durationMs: null,
    agents: [agentRow('agent-r1', { title: 'App track', type: null, run: 'wf_build-1' })],
  }],
};

export const VIEW: ThreadView = {
  ...thread('th-dev', { name: 'Tidy the router' }),
  turns: [
    { id: 'turn-1', status: 'completed', items: [
      { type: 'userMessage', id: 'u1', content: [{ type: 'text', text: 'List the hooks' }] },
      { type: 'reasoning', id: 'r1', summary: [] },
      { type: 'commandExecution', id: 'c1', command: 'ls .claude/hooks', exitCode: 0, aggregatedOutput: 'guard.sh\n' },
      { type: 'fileChange', id: 'f1', changes: [{ kind: { type: 'update' }, path: 'CLAUDE.md' }] },
      { type: 'agentMessage', id: 'a1', text: 'There are eleven hooks.' },
    ] },
  ],
};

// A server answer the page must word by its code; the error text is never shown.
export class Fail {
  constructor(readonly status: number, readonly code: string) {}
}
type Answer = unknown | ((body: unknown) => unknown);

// fetch answering 'METHOD url' from the routes given over the defaults; a route
// that is missing rejects, as a server that does not answer would.
export function serve(routes: Record<string, Answer> = {}) {
  const all: Record<string, Answer> = {
    'GET api/agents': { agents: [], at: '2026-10-10T10:00:00Z' },
    'GET api/questions': { version: 1, questions: [] },
    'GET api/codex': STATUS,
    'GET api/codex/threads': { threads: [] },
    'GET api/taskboard': { running: false, url: 'http://127.0.0.1:47823' },
    'GET api/tasks': { code: 'ok', sections: [], titles: {}, runs: [], at: '2026-10-10T10:00:00Z' },
    'GET api/claude': { sessions: [], at: '2026-10-10T10:00:00Z' },
    ...routes,
  };
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const route = `${init?.method ?? 'GET'} ${url}`;
    if (!(route in all)) throw new TypeError(`no route ${route}`);
    const given = all[route];
    const answer = typeof given === 'function' ? given(init?.body ? JSON.parse(String(init.body)) : undefined) : given;
    if (answer instanceof Fail) return { ok: false, status: answer.status, json: async () => ({ error: 'C:\\secret\\path', code: answer.code }) };
    return { ok: true, status: 200, json: async () => answer };
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

// The requests made to one route, with their JSON bodies.
export const calls = (fetchMock: ReturnType<typeof serve>, route: string) => fetchMock.mock.calls
  .filter(([url, init]) => `${init?.method ?? 'GET'} ${url}` === route)
  .map(([, init]) => (init?.body ? JSON.parse(String(init.body)) : undefined));

export class FakeEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  static all: FakeEventSource[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = FakeEventSource.CONNECTING;
  constructor(readonly url: string) { FakeEventSource.all.push(this); }
  close() { this.readyState = FakeEventSource.CLOSED; }
  // The one stream the page holds open now.
  static get current() { return FakeEventSource.all.filter((s) => s.readyState !== FakeEventSource.CLOSED).at(-1)!; }
  open() { this.readyState = FakeEventSource.OPEN; this.onopen?.(); }
  emit(method: string, params: unknown) { this.onmessage?.({ data: JSON.stringify({ method, params }) }); }
  // A dropped stream the browser retries by itself (CONNECTING), or one it gave up on (CLOSED).
  drop(state = FakeEventSource.CONNECTING) { this.readyState = state; this.onerror?.(); }
}
