import { describe, expect, it } from 'vitest';
import { codexColumns, threadLines } from './codexBoard';
import { translate } from './i18n';
import { VIEW, question, thread } from './test-fakes';

const threads = [
  thread('th-run', { state: 'running', name: 'Running here' }),
  thread('th-else', { state: 'active-elsewhere', source: 'vscode', cwd: 'D:\\work\\pcb' }),
  thread('th-idle', { name: 'Tidy the router' }),
  thread('th-err', { state: 'error', source: 'exec', cwd: 'D:\\work\\pcb' }),
];
const questions = [question('q-2026-10-10-library-001'), question('q-2026-10-10-pcb-002', { asked_by: 'May', question: 'May asks' }),
  question('q-2026-10-10-pcb-003', { status: 'answered', question: 'Already answered' })];
const all = { text: '', source: '', folder: '' };
const ids = (cols: ReturnType<typeof codexColumns>) => ({
  running: cols.running.map((t) => t.id), waiting: cols.waiting.map((q) => q.id),
  elsewhere: cols.elsewhere.map((t) => t.id), idle: cols.idle.map((t) => t.id),
});

describe('the Codex board', () => {
  it('sorts threads by state, error threads in Idle, and holds only Aster\'s open questions as waiting', () => {
    expect(ids(codexColumns(threads, questions, all))).toEqual({
      running: ['th-run'], waiting: ['q-2026-10-10-library-001'], elsewhere: ['th-else'], idle: ['th-idle', 'th-err'],
    });
    expect(codexColumns(threads, questions, all).idle[1].state).toBe('error');
  });

  it('finds a thread by its title, its preview or its id, in any case', () => {
    expect(ids(codexColumns(threads, questions, { ...all, text: 'TIDY' })).idle).toEqual(['th-idle']);
    expect(ids(codexColumns(threads, questions, { ...all, text: 'PROMPT OF TH-EL' }))).toEqual({ running: [], waiting: [], elsewhere: ['th-else'], idle: [] });
    expect(ids(codexColumns(threads, questions, { ...all, text: 'th-run' })).running).toEqual(['th-run']);
    expect(ids(codexColumns(threads, questions, { ...all, text: 'sandbox' }))).toEqual({ running: [], waiting: ['q-2026-10-10-library-001'], elsewhere: [], idle: [] });
  });

  it('narrows every column by Source and by Folder; a question has neither', () => {
    expect(ids(codexColumns(threads, questions, { ...all, source: 'exec' }))).toEqual({ running: [], waiting: [], elsewhere: [], idle: ['th-err'] });
    expect(ids(codexColumns(threads, questions, { ...all, folder: 'pcb' }))).toEqual({ running: [], waiting: [], elsewhere: ['th-else'], idle: ['th-err'] });
    expect(ids(codexColumns(threads, questions, { ...all, folder: 'dev', source: 'cli' }))).toEqual({ running: ['th-run'], waiting: [], elsewhere: [], idle: ['th-idle'] });
  });
});

describe('a thread\'s lines', () => {
  it('reads each item as one line of its kind, a reasoning item without a summary as none', () => {
    const t = (key: string, vars?: Record<string, string | number>) => translate('en', key, vars);
    expect(threadLines(VIEW.turns, t)).toEqual([
      { kind: 'prompt', text: 'List the hooks' },
      { kind: 'command', text: '$ ls .claude/hooks → exit 0\nguard.sh' },
      { kind: 'file', text: 'update CLAUDE.md' },
      { kind: 'reply', text: 'There are eleven hooks.' },
    ]);
  });

  it('keeps the end of a long output, cut once at its start, and reads an unknown item by its type', () => {
    const t = (key: string, vars?: Record<string, string | number>) => translate('en', key, vars);
    // As the server sends a long output (contract A3): '…' and its last 3,999 characters.
    const served = '…' + 'x'.repeat(3996) + 'END';
    const [command, other] = threadLines([{ items: [{ type: 'commandExecution', command: 'build', aggregatedOutput: served }, { type: 'imageView' }] }, null, { items: 'none' }], t);
    expect(command.text).toBe('$ build → exit ?\n…' + served.slice(-1500));
    expect(other).toEqual({ kind: 'other', text: 'imageView' });
  });

  it('words Codex\'s change kinds and tool statuses in Cantonese, an unknown one as Codex gives it', () => {
    const t = (key: string, vars?: Record<string, string | number>) => translate('zh-HK', key, vars);
    const changes = ['add', 'update', 'delete', 'rename'].map((type) => ({ kind: { type }, path: 'a.md' }));
    const tools = ['inProgress', 'completed', 'failed', 'paused'].map((status) => ({ type: 'mcpToolCall', server: 'git', tool: 'log', status }));
    expect(threadLines([{ items: [{ type: 'fileChange', changes }, ...tools] }], t).map((l) => l.text)).toEqual([
      '新增 a.md\n修改 a.md\n刪除 a.md\nrename a.md', 'git.log 進行中', 'git.log 已完成', 'git.log 失敗', 'git.log paused']);
  });
});
