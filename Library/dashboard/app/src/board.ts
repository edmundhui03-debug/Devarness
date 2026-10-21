import type { Agent, AgentName, Question } from './api';

// The Agents board: one card per open question, session and offline agent,
// sorted into four columns. Pure, so the components only render it.
export type Card = {
  // agent is Peter, Aster or May, or for a question whoever asked it (AGENTS.md names the three; the server does not
  // check), '' when the question names no one.
  key: string; kind: 'question' | 'session' | 'agent'; id: string; agent: string;
  title: string; label: string; folder: string; path: string; updatedAt: string | null; state: string;
};
export type Board = { waiting: Card[]; working: Card[]; idle: Card[]; offline: Card[] };

export const AGENTS: AgentName[] = ['Peter', 'Aster', 'May'];
export const PREFIX: Record<AgentName, string> = { Peter: 'PET', Aster: 'AST', May: 'MAY' };
export const isAgent = (name: string): name is AgentName => (AGENTS as string[]).includes(name);

// Who asked: '' when the question names no one or only spaces, which the page shows as Unknown;
// any other name stays as written, as the server counts it by exact name.
export const askerOf = (q: Question) => (q.asked_by?.trim() ? q.asked_by : '');

// q-2026-10-09-pcb-001 gives PCB-1009-001: numbers restart each day, so the date stays in the key.
export function questionKey(id: string): string {
  const m = /^q-\d{4}-(\d{2})-(\d{2})-(.+)-([^-]+)$/.exec(id);
  return (m ? `${m[3]}-${m[1]}${m[2]}-${m[4]}` : id).toUpperCase();
}

// The last four characters: Pi ids begin with a date and Codex ids with a time, so their starts repeat.
export const sessionKey = (agent: AgentName, id: string) => `${PREFIX[agent]}-${id.slice(-4).toUpperCase()}`;
export const lastFolder = (path: string) => path.split(/[\\/]/).filter(Boolean).pop() ?? '';
const time = (c: Card) => (c.updatedAt ? Date.parse(c.updatedAt) || 0 : 0);
const newestFirst = (a: Card, b: Card) => time(b) - time(a);

export function buildBoard(agents: Agent[], questions: Question[]): Board {
  const waiting = questions.filter((q) => q.status === 'open').map((q): Card => ({
    key: questionKey(q.id), kind: 'question', id: q.id, agent: askerOf(q),
    title: q.question, label: q.project, folder: '', path: '', updatedAt: q.asked_at, state: q.status,
  }));
  const sessions = agents.flatMap((a) => a.sessions.map((s): Card => ({
    key: sessionKey(a.name, s.id), kind: 'session', id: s.id, agent: a.name,
    title: s.title, label: s.source || a.client, folder: lastFolder(s.cwd), path: s.cwd, updatedAt: s.updatedAt, state: s.state,
  }))).sort(newestFirst);
  const offline = agents.filter((a) => a.availability === 'offline').map((a): Card => ({
    key: PREFIX[a.name], kind: 'agent', id: a.name, agent: a.name, title: a.note ? `${a.name}: ${a.note}` : a.name,
    label: a.client, folder: '', path: '', updatedAt: null, state: 'offline',
  }));
  return { waiting, working: sessions.filter((c) => c.state === 'working'), idle: sessions.filter((c) => c.state !== 'working'), offline };
}

// The agent pills filter the three agents; a question from anyone else always passes.
// The text matches a card's title, key or folder, as Jira's search does.
export function filterCards(cards: Card[], text: string, agents: Set<string>): Card[] {
  const needle = text.trim().toLowerCase();
  return cards.filter((c) => (agents.has(c.agent) || !isAgent(c.agent))
    && [c.title, c.key, c.folder].some((s) => s.toLowerCase().includes(needle)));
}

// The List view: working first, then the newest.
export const listOrder = (cards: Card[]) =>
  [...cards].sort((a, b) => Number(b.state === 'working') - Number(a.state === 'working') || newestFirst(a, b));

// The side panel's address for a card: q:<id>, s:<agent>:<session id> or agent:<Name>.
export const peekOf = (c: Card) => (c.kind === 'question' ? `q:${c.id}` : c.kind === 'session' ? `s:${c.agent}:${c.id}` : `agent:${c.agent}`);

// peekOf read back; a session id may itself hold colons. null for anything else.
export type Peek = { kind: Card['kind']; agent: string | null; id: string };
export function parsePeek(peek: string | null): Peek | null {
  const [kind, first = '', ...more] = (peek ?? '').split(':');
  const whole = [first, ...more].join(':');
  const rest = more.join(':');
  if (kind === 'q' && whole) return { kind: 'question', agent: null, id: whole };
  if (kind === 's' && first && rest) return { kind: 'session', agent: first, id: rest };
  if (kind === 'agent' && whole) return { kind: 'agent', agent: whole, id: whole };
  return null;
}
