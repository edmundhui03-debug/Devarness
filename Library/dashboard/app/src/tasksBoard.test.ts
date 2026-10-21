import { describe, expect, it } from 'vitest';
import type { Run, Section } from './api';
import { chipOf, tasksColumns, tasksGroups, topFolder, waitingCount } from './tasksBoard';
import { question } from './test-fakes';

const S = (status: Section['status'], file: string, line: number, heading: string): Section => ({ status, file, line, heading });
const SECTIONS = [
  S('open', 'README.md', 20, 'A root task'),
  S('partial', 'Projects/demo/docs/c.md', 9, 'Half the icons are done'),
  S('blocked', 'Library/b.md', 3, 'Blocked on a licence'),
  S('needs-owner', 'Setup/a.md', 7, 'The owner picks a colour'),
  S('fixed', 'Setup/a.md', 30, 'Already settled'),
];
const RUN: Run = { launched: '2026-10-14 09:00', at: '2026-10-14T01:00:00.000Z', session: '`abcd`', task: 'Review the plan', agent: 'one Opus agent', budget: '0.5M', stale: true };
const QS = [question('q-1', { status: 'open', question: 'Which colour?' }), question('q-2', { status: 'answered' })];
const TITLES = { 'Setup/a.md': 'A', 'Library/b.md': 'B', 'Projects/demo/docs/c.md': 'C', 'README.md': 'dev' };
const keys = (cards: { key: string }[]) => cards.map((c) => c.key);

describe('the tasks board', () => {
  it('names a document\'s top folder, a project by its own name, the root as empty', () => {
    expect(['Setup/a.md', 'Projects/demo/docs/c.md', 'Projects/x.md', 'README.md'].map(topFolder))
      .toEqual(['Setup', 'Projects/demo', 'Projects', '']);
  });
  it('waits on questions then needs-owner then blocked, runs before partial, open last, fixed nowhere', () => {
    const cols = tasksColumns(SECTIONS, [RUN], QS, TITLES, { text: '', folder: '' });
    expect(keys(cols.waiting)).toEqual(['q:q-1', 'd:Setup/a.md#7', 'd:Library/b.md#3']);
    expect(keys(cols.progress)).toEqual(['r:0', 'd:Projects/demo/docs/c.md#9']);
    expect(keys(cols.todo)).toEqual(['d:README.md#20']);
  });
  it('filters documents by folder and text, and keeps questions and runs unless the text leaves them out', () => {
    const setup = tasksColumns(SECTIONS, [RUN], QS, TITLES, { text: '', folder: 'Setup' });
    expect(keys(setup.waiting)).toEqual(['q:q-1', 'd:Setup/a.md#7']);
    expect(keys(setup.progress)).toEqual(['r:0']);
    expect(setup.todo).toEqual([]);
    const licence = tasksColumns(SECTIONS, [RUN], QS, TITLES, { text: 'LICENCE', folder: '' });
    expect(keys([...licence.waiting, ...licence.progress, ...licence.todo])).toEqual(['d:Library/b.md#3']);
  });
  it('groups the list: questions, runs, each folder by name, the root last', () => {
    const groups = tasksGroups(tasksColumns(SECTIONS, [RUN], QS, TITLES, { text: '', folder: '' }));
    expect(groups.map((g) => g.id)).toEqual(['q', 'r', 'd:Library', 'd:Projects/demo', 'd:Setup', 'd:']);
  });
  it('counts what waits, and shows open as a grey to-do chip', () => {
    expect(waitingCount(SECTIONS, QS)).toBe(3);
    expect([chipOf('open'), chipOf('needs-owner')]).toEqual(['todo', 'needs-owner']);
  });
});
