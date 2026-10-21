import { describe, expect, it } from 'vitest';
import { claudeColumns, claudeKey, folderOf, sessionTitle } from './claudeBoard';
import { claudeSession, question } from './test-fakes';

const sessions = [
  claudeSession('0b1c2d3e-0000-4000-8000-00000000a001', { state: 'working', title: 'Build wave 4' }),
  claudeSession('0b1c2d3e-0000-4000-8000-00000000a002', { state: 'idle', title: 'Tidy the router', source: 'cli', cwd: 'D:\\work\\pcb' }),
  claudeSession('0b1c2d3e-0000-4000-8000-00000000a003', { state: 'ended', title: 'Read the spec' }),
  claudeSession('0b1c2d3e-0000-4000-8000-00000000a004', { state: 'working', title: 'Second worker', source: 'cli' }),
];
const questions = [question('q-2026-10-15-library-001', { asked_by: 'Peter', question: 'Which port?' }),
  question('q-2026-10-15-library-002', { asked_by: 'Aster', question: 'Aster asks' }),
  question('q-2026-10-15-library-003', { asked_by: 'Peter', status: 'answered', question: 'Already answered' })];
const all = { text: '', source: '', folder: '' };
const ids = (cols: ReturnType<typeof claudeColumns>) => ({
  waiting: cols.waiting.map((q) => q.id), working: cols.working.map((s) => s.id.slice(-4)),
  idle: cols.idle.map((s) => s.id.slice(-4)), ended: cols.ended.map((s) => s.id.slice(-4)),
});

describe('the Claude board', () => {
  it('sorts sessions by state, in the server\'s order, and holds only Peter\'s open questions as waiting', () => {
    expect(ids(claudeColumns(sessions, questions, all))).toEqual({
      waiting: ['q-2026-10-15-library-001'], working: ['a001', 'a004'], idle: ['a002'], ended: ['a003'],
    });
  });

  it('finds a session by its title, its id or its key, in any case, and a question by its text or key', () => {
    expect(ids(claudeColumns(sessions, questions, { ...all, text: 'TIDY' })).idle).toEqual(['a002']);
    expect(ids(claudeColumns(sessions, questions, { ...all, text: '00000000a003' })).ended).toEqual(['a003']);
    expect(ids(claudeColumns(sessions, questions, { ...all, text: 'pet-a004' }))).toEqual({ waiting: [], working: ['a004'], idle: [], ended: [] });
    expect(ids(claudeColumns(sessions, questions, { ...all, text: 'port' }))).toEqual({ waiting: ['q-2026-10-15-library-001'], working: [], idle: [], ended: [] });
    expect(ids(claudeColumns(sessions, questions, { ...all, text: 'library-1015-001' })).waiting).toEqual(['q-2026-10-15-library-001']);
  });

  it('narrows every column by Source and by Folder, and hides the questions, which have neither', () => {
    expect(ids(claudeColumns(sessions, questions, { ...all, source: 'cli' }))).toEqual({ waiting: [], working: ['a004'], idle: ['a002'], ended: [] });
    expect(ids(claudeColumns(sessions, questions, { ...all, folder: 'pcb' }))).toEqual({ waiting: [], working: [], idle: ['a002'], ended: [] });
  });

  it('keys a session as the Agents board keys Peter\'s, titles it, and names its folder', () => {
    expect(claudeKey('0b1c2d3e-0000-4000-8000-00000000a0bc')).toBe('PET-A0BC');
    expect(sessionTitle(claudeSession('x-1', { title: '' }))).toBe('x-1');
    expect(sessionTitle(sessions[0])).toBe('Build wave 4');
    expect(folderOf(sessions[1])).toBe('pcb');
    expect(folderOf(claudeSession('x-2', { cwd: '' }))).toBe('');
  });
});
