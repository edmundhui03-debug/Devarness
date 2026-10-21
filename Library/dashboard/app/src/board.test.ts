import { describe, expect, it } from 'vitest';
import type { Agent, Question } from './api';
import { buildBoard, filterCards, parsePeek, peekOf } from './board';

const agents: Agent[] = [
  { name: 'Peter', client: 'Claude Code', availability: 'online', workload: 'working', openQuestions: 0, sessions: [
    { id: 'abcd1234', title: 'dashboard work', cwd: 'D:/work/dev', state: 'working', updatedAt: '2026-10-09T10:00:00Z', source: 'cli' }] },
  { name: 'Aster', client: 'Codex', availability: 'offline', workload: 'idle', openQuestions: 1, sessions: [], note: 'spawn codex ENOENT' },
  { name: 'May', client: 'Pi', availability: 'online', workload: 'idle', openQuestions: 0,
    sessions: Array.from({ length: 10 }, (_, i) => ({ id: `pi-${i}`, title: `Pi session ${i}`, cwd: 'C--dev',
      state: i === 9 ? 'error' as const : 'idle' as const, updatedAt: `2026-10-0${(i % 9) + 1}T10:00:00Z`, source: 'pi' })) },
];
const question = (id: string, extra: Partial<Question> = {}): Question => ({ id, project: 'PCB', task: 'Order', asked_by: 'Aster',
  asked_at: '2026-10-09T10:00:00+08:00', question: 'Which holder?', status: 'open', answer: '', answered_at: '',
  used_by: '', used_at: '', used_note: '', ...extra });
const questions = [question('q-2026-10-09-pcb-001'), question('q-2026-10-09-library-002', { asked_by: 'Peter', status: 'answered' })];

describe('the Agents board', () => {
  it('puts open questions, working and idle sessions and offline agents in their columns', () => {
    const board = buildBoard(agents, questions);
    expect(board.waiting.map((c) => c.key)).toEqual(['PCB-1009-001']);
    expect(board.working.map((c) => [c.key, c.agent])).toEqual([['PET-1234', 'Peter']]);
    expect(board.idle).toHaveLength(10);
    expect(board.idle.some((c) => c.state === 'error')).toBe(true);
    expect(board.offline.map((c) => [c.key, c.title])).toEqual([['AST', 'Aster: spawn codex ENOENT']]);
  });

  it('shows a path by its last folder and keeps the whole path', () => {
    const card = buildBoard(agents, []).working[0];
    expect([card.folder, card.path]).toEqual(['dev', 'D:/work/dev']);
  });

  it('filters by text in any case and by agent', () => {
    const board = buildBoard(agents, questions);
    const all = [...board.waiting, ...board.working, ...board.idle, ...board.offline];
    expect(filterCards(all, 'DASHBOARD', new Set(['Peter', 'Aster', 'May'])).map((c) => c.key)).toEqual(['PET-1234']);
    expect(filterCards(all, '', new Set(['Aster'])).map((c) => c.key)).toEqual(['PCB-1009-001', 'AST']);
  });

  it('finds a card by its key and by its folder too, as Jira\'s search does', () => {
    const board = buildBoard(agents, questions);
    const all = [...board.waiting, ...board.working, ...board.idle, ...board.offline];
    const everyone = new Set(['Peter', 'Aster', 'May']);
    expect(filterCards(all, 'pcb-1009', everyone).map((c) => c.key)).toEqual(['PCB-1009-001']);
    expect(filterCards(all, 'C--DEV', everyone).map((c) => c.agent)).toEqual(Array(10).fill('May'));
  });

  it('gives a question with no asker, or one of only spaces, an empty agent, not undefined', () => {
    const { asked_by: _, ...noAsker } = question('q-2026-10-09-pcb-003');
    const spaces = question('q-2026-10-09-pcb-004', { asked_by: '   ' });
    expect(buildBoard([], [noAsker as Question, spaces]).waiting.map((c) => c.agent)).toEqual(['', '']);
  });

  it('keeps a padded asker as written, as the server counts it by exact name', () => {
    const padded = question('q-2026-10-09-pcb-005', { asked_by: 'May ' });
    expect(buildBoard([], [padded]).waiting.map((c) => c.agent)).toEqual(['May ']);
  });

  it('reads back the side-panel address of every card', () => {
    const board = buildBoard(agents, questions);
    for (const c of [...board.waiting, ...board.working, ...board.idle, ...board.offline]) {
      expect(parsePeek(peekOf(c))).toEqual({ kind: c.kind, agent: c.kind === 'question' ? null : c.agent, id: c.id });
    }
    expect(parsePeek('s:May:2026-10-07T18:48:23Z_01a1')).toEqual({ kind: 'session', agent: 'May', id: '2026-10-07T18:48:23Z_01a1' });
    expect([null, '', 'q:', 's:Peter', 'board'].map(parsePeek)).toEqual([null, null, null, null, null]);
  });
});
