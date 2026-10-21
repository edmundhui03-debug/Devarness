// The dashboard server's JSON API (Library/dashboard/server/server.mjs), on
// relative URLs so the page works wherever the server serves it.
import { TABLES } from './i18n';

export type AgentName = 'Peter' | 'Aster' | 'May';
export type Session = { id: string; title: string; cwd: string; state: 'working' | 'idle' | 'error'; updatedAt: string | null; source: string };
export type Agent = {
  name: AgentName; client: string; availability: 'online' | 'offline'; workload: 'working' | 'waiting' | 'idle';
  sessions: Session[]; openQuestions: number; note?: string;
};
// status is 'open', 'answered' or 'used' (Library/dashboard/AGENTS.md); kept a string as the file gives it.
export type Question = {
  id: string; project: string; task: string; asked_by: string; asked_at: string; question: string; status: string;
  answer: string; answered_at: string; used_by: string; used_at: string; used_note: string;
};

// Codex, as the server's /api/codex routes give it (Setup/superpowers/plans/2026-10-10-dashboard-wave-2.md,
// the API contract). Times are Codex's own: seconds since 1970.
export type RateWindow = { usedPercent: number | null; windowDurationMins: number | null; resetsAt: number | null };
export type CodexStatus = {
  up: boolean; version: string | null; signedIn: boolean; type: string | null; plan: string | null;
  rateLimits: { primary: RateWindow | null; secondary: RateWindow | null } | null;
  code: 'ok' | 'codex-not-started' | 'codex-signed-out';
};
export type ThreadState = 'running' | 'active-elsewhere' | 'idle' | 'error';
export type Thread = {
  id: string; name: string | null; preview: string; source: string | null; nickname: string | null;
  cwd: string | null; inDev: boolean; createdAt: number | null; updatedAt: number | null; state: ThreadState;
  turn: string | null; // the turn this server started there and has not seen complete: Stop ends it
};
export type ThreadView = Thread & { turns: unknown[] };
export type CodexEvent = { method: string; params: unknown };
export type Sandbox = 'read-only' | 'workspace-write';

// The Tasks routes (Setup/superpowers/plans/2026-10-14-dashboard-wave-3.md, the API contract).
export type SectionStatus = 'open' | 'partial' | 'blocked' | 'needs-owner' | 'fixed';
// file is '/'-separated and relative to the dev root, as md-format prints it.
export type Section = { status: SectionStatus; file: string; line: number; heading: string };
// launched is the ledger cell as written; at is its time in ISO form, or null when it holds none.
export type Run = { launched: string; at: string | null; session: string; task: string; agent: string; budget: string; stale: boolean };
export type Tasks = {
  code: 'ok' | 'tasks-no-python' | 'tasks-index-failed'; // the index's state; the runs are read either way
  sections: Section[];            // every marked section, fixed ones included; [] unless code is 'ok'
  titles: Record<string, string>; // every indexed document's H1, by path; {} unless code is 'ok'
  runs: Run[];                    // the ledger's running rows, in file order
  at: string;                     // when this reading was made, ISO
};
export type Commit = { hash: string; at: string; subject: string }; // an abbreviated hash; at is ISO 8601

// The Claude routes (Setup/superpowers/plans/2026-10-15-dashboard-wave-4.md, the API contract). Every
// string is masked by the server; times are ISO.
export type ClaudeState = 'working' | 'idle' | 'ended';
export type ClaudeSession = { id: string; title: string; cwd: string; state: ClaudeState; source: string; updatedAt: string | null };
export type StepKind = 'prompt' | 'reply' | 'tool' | 'result' | 'thinking';
export type Step = { kind: StepKind; text: string; tool: string | null; error: boolean; at: string | null };
export type AgentRow = { id: string; title: string; type: string | null; run: string | null; state: 'working' | 'idle'; updatedAt: string | null };
export type RunRow = {
  id: string; name: string; status: string; summary: string;
  agentCount: number | null; startedAt: string | null; durationMs: number | null;
  agents: AgentRow[]; // newest first, at most 30
};
export type ClaudeView = ClaudeSession & {
  branch: string | null;
  commits: Commit[] | null; // null when the folder is gone, not a repository, or git fails
  readable: boolean;        // false when the transcript cannot be read; steps is then []
  steps: Step[];            // oldest first, at most 20
  agents: AgentRow[];       // direct subagents, newest first, at most 10
  runs: RunRow[];           // workflow runs, newest first, at most 5
};
export type AgentView = AgentRow & { readable: boolean; steps: Step[] };

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  const body = await res.json().catch(() => ({}));
  // The status and the code stay on the error, so the page can word a known one itself.
  if (!res.ok) throw Object.assign(new Error(body.error || `HTTP ${res.status}`), { status: res.status, code: body.code });
  return body as T;
}
const post = <T>(url: string, body: object) => call<T>(url, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
});

// The codes the page words are the tables' err.* keys; any other failure, a
// server that does not answer included, is 'other'. The server's own text is never shown.
export function errorCode(err: unknown): string {
  const code = (err as { code?: unknown } | null)?.code;
  return typeof code === 'string' && Object.hasOwn(TABLES.en, `err.${code}`) ? code : 'other';
}

export const getAgents = () => call<{ agents: Agent[]; at: string }>('api/agents');
export const getQuestions = () => call<{ version: number; questions: Question[]; error?: string }>('api/questions');
export const answer = (id: string, text: string) => post<{ question: Question }>(`api/questions/${encodeURIComponent(id)}/answer`, { answer: text });

export const getCodex = () => call<CodexStatus>('api/codex');
export const getThreads = () => call<{ threads: Thread[] }>('api/codex/threads');
export const getThread = (id: string) => call<ThreadView>(`api/codex/threads/${encodeURIComponent(id)}`);
export const runPrompt = (prompt: string, sandbox: Sandbox, thread: string | null) =>
  post<{ thread: string; turn: string }>('api/codex/run', { prompt, sandbox, thread });
export const stopRun = (thread: string, turn: string) => post<{ ok: true }>('api/codex/stop', { thread, turn });
export const signIn = () => post<{ authUrl: string }>('api/codex/login', {});
export const getTaskboard = () => call<{ running: boolean; url: string }>('api/taskboard');
export const getTasks = () => call<Tasks>('api/tasks');
export const getCommits = (file: string) => call<{ commits: Commit[] }>(`api/tasks/commits?file=${encodeURIComponent(file)}`);
export const getClaude = () => call<{ sessions: ClaudeSession[]; at: string }>('api/claude');
export const getClaudeSession = (id: string) => call<ClaudeView>(`api/claude/sessions/${encodeURIComponent(id)}`);
export const getClaudeAgent = (session: string, agent: string) =>
  call<AgentView>(`api/claude/sessions/${encodeURIComponent(session)}/agents/${encodeURIComponent(agent)}`);
