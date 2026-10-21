import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { App } from './App';
import { question, serve as serveRoutes } from './test-fakes';
import theme from './theme.css?raw';

const agents = [
  { name: 'Peter', client: 'Claude Code', availability: 'online', workload: 'working', openQuestions: 0,
    sessions: [{ id: 'abcd1234', title: 'dashboard work', cwd: 'D:/work/dev', state: 'working', updatedAt: '2026-10-09T10:00:00Z', source: 'cli' }] },
  { name: 'Aster', client: 'Codex', availability: 'offline', workload: 'idle', openQuestions: 0, sessions: [], note: 'spawn codex ENOENT' },
  { name: 'May', client: 'Pi', availability: 'online', workload: 'waiting', openQuestions: 1, sessions: [] },
];
const questions = [{ id: 'q-2026-10-09-library-001', project: 'Library', task: 'Wave 1', asked_by: 'May',
  asked_at: '2026-10-09T10:00:00+08:00', question: 'Which port?', status: 'open', answer: '', answered_at: '',
  used_by: '', used_at: '', used_note: '' }];

function serve(qs: object[] = questions) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({
    ok: true, status: 200,
    json: async () => (url.includes('agents') ? { agents, at: '2026-10-09T10:00:00Z' } : { version: 1, questions: qs }),
  })));
}

describe('the Agents page', () => {
  it('shows a column per state with its cards: the question waiting, Aster offline', async () => {
    serve();
    render(<App />);
    const waiting = await screen.findByRole('region', { name: 'Waiting for you' });
    expect(within(waiting).getByText('Which port?')).toBeTruthy();
    expect(within(waiting).getByText('LIBRARY-1009-001')).toBeTruthy();
    expect(within(screen.getByRole('region', { name: 'Offline' })).getByText('Aster: spawn codex ENOENT')).toBeTruthy();
    expect(within(screen.getByRole('region', { name: 'Working' })).getByText('dashboard work')).toBeTruthy();
  });

  it('opens a question in the side panel with its own address, ready to answer', async () => {
    serve();
    render(<App />);
    fireEvent.click(await screen.findByText('Which port?'));
    expect(location.hash).toBe('#/?peek=q%3Aq-2026-10-09-library-001');
    const panel = await screen.findByRole('dialog');
    expect(within(panel).getByLabelText('Your answer')).toBeTruthy();
  });

  it('keeps a typed answer when Esc closes the panel and the question opens again', async () => {
    serve();
    render(<App />);
    fireEvent.click(await screen.findByText('Which port?'));
    const box = within(await screen.findByRole('dialog')).getByLabelText('Your answer');
    fireEvent.change(box, { target: { value: '47900, please' } });
    fireEvent.keyDown(box, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    fireEvent.click(screen.getByText('Which port?'));
    const again = within(await screen.findByRole('dialog')).getByLabelText('Your answer') as HTMLTextAreaElement;
    expect(again.value).toBe('47900, please');
  });

  it('shows the list view by its tab and its address', async () => {
    serve();
    render(<App />);
    fireEvent.click(await screen.findByRole('tab', { name: 'List' }));
    expect(location.hash).toBe('#/?view=list');
    expect(await screen.findByRole('table')).toBeTruthy();
  });

  it('keeps only the cards a search names', async () => {
    serve();
    render(<App />);
    fireEvent.change(await screen.findByRole('searchbox'), { target: { value: 'DASHBOARD' } });
    expect(screen.getByText('dashboard work')).toBeTruthy();
    expect(screen.queryByText('Which port?')).toBeNull();
  });

  it('finds a card by its key and by its folder, not only its title', async () => {
    serve();
    render(<App />);
    const search = await screen.findByRole('searchbox');
    fireEvent.change(search, { target: { value: 'library-1009' } });
    expect(screen.getByText('Which port?')).toBeTruthy();
    expect(screen.queryByText('dashboard work')).toBeNull();
    fireEvent.change(search, { target: { value: 'DEV' } });
    expect(screen.getByText('dashboard work')).toBeTruthy();
    expect(screen.queryByText('Which port?')).toBeNull();
  });

  it('shows a question with no asker, an empty one or only spaces under Unknown, and the rest of the board', async () => {
    const { asked_by: _, ...noAsker } = questions[0];
    const titles = ['Who asks?', 'Empty asker?', 'Spaces asker?'];
    serve([{ ...noAsker, question: titles[0] },
      { ...questions[0], id: 'q-2026-10-09-library-002', asked_by: '', question: titles[1] },
      { ...questions[0], id: 'q-2026-10-09-library-003', asked_by: '   ', question: titles[2] }]);
    render(<App />);
    const waiting = await screen.findByRole('region', { name: 'Waiting for you' });
    const cards = titles.map((title) => within(waiting).getByText(title).closest('button') as HTMLElement);
    for (const card of cards) expect(within(card).getByTitle('Unknown').textContent).toBe('?');
    expect(within(screen.getByRole('region', { name: 'Working' })).getByText('dashboard work')).toBeTruthy();
    fireEvent.click(cards[2]);
    const panel = await screen.findByRole('dialog');
    expect(within(panel).getByText('Questions from Unknown')).toBeTruthy();
    // The List view's asker cell, read within its own row: the open panel says Unknown too.
    fireEvent.click(screen.getByRole('tab', { name: 'List' }));
    const table = await screen.findByRole('table');
    for (const title of titles) {
      const row = within(table).getByText(title).closest('tr') as HTMLElement;
      expect(within(row).getAllByRole('cell')[2].textContent, title).toBe('Unknown');
    }
    fireEvent.click(screen.getByRole('button', { name: 'Switch language' }));
    expect(await within(panel).findByText('不明提問者 的問題')).toBeTruthy();
  });

  it('shows a saved answer at once, from the question the server returns', async () => {
    const answered = { ...questions[0], status: 'answered', answer: '47900', answered_at: '2026-10-09T12:00:00.000Z' };
    let posted = false;
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        posted = true;
        return { ok: true, status: 200, json: async () => ({ question: answered }) };
      }
      if (posted) return new Promise(() => {}); // no poll comes back after the save
      return { ok: true, status: 200, json: async () => (url.includes('agents') ? { agents, at: '2026-10-09T10:00:00Z' } : { version: 1, questions }) };
    }));
    render(<App />);
    fireEvent.click(await screen.findByText('Which port?'));
    const panel = await screen.findByRole('dialog');
    fireEvent.change(within(panel).getByLabelText('Your answer'), { target: { value: '47900' } });
    fireEvent.click(within(panel).getByRole('button', { name: 'Save answer' }));
    expect(await within(panel).findByText('Answered; waiting for May to act')).toBeTruthy();
    expect(within(panel).queryByLabelText('Your answer')).toBeNull();
    expect(within(screen.getByRole('region', { name: 'Waiting for you' })).queryByText('Which port?')).toBeNull();
  });

  it('marks the selected sidebar agent with a 2 px ink bar on its left edge, in both themes', async () => {
    serve();
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: /^May · Pi/ }));
    await screen.findByRole('dialog');
    expect(screen.getByRole('button', { name: /^May · Pi/ }).className).toMatch(/\bsel\b/);
    // One rule drawn in --ink, which each theme sets: no theme overrides it.
    const rules = theme.match(/\.nav\.sel\s*\{[^}]*\}/g) ?? [];
    expect(rules).toHaveLength(1);
    expect(rules[0]).toMatch(/box-shadow:\s*inset 2px 0 0 var\(--ink\)/);
  });

  it('switches every word to Cantonese', async () => {
    serve();
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Switch language' }));
    expect(await screen.findByRole('region', { name: '等你回覆' })).toBeTruthy();
    expect(document.documentElement.lang).toBe('zh-HK');
  });
});

describe('the pages', () => {
  it('opens the Codex page from the sidebar\'s Aster row, marked as the current page there', async () => {
    serve();
    render(<App />);
    fireEvent.click(await screen.findByRole('link', { name: /^Aster · Codex/ }));
    expect(location.hash).toBe('#/codex');
    expect(await screen.findByRole('heading', { level: 1, name: 'Aster · Codex' })).toBeTruthy();
    expect(screen.getByText('dev workspace / Agents / Aster')).toBeTruthy();
    expect(screen.getByRole('link', { name: /^Aster · Codex/ }).getAttribute('aria-current')).toBe('page');
    // Only the page shown is current: neither Agents link, the top bar's included.
    const top = within(screen.getByRole('navigation', { name: 'Main pages' }));
    expect(top.getByRole('link', { name: 'Agents' }).getAttribute('aria-current')).toBeNull();
    expect(document.querySelectorAll('[aria-current="page"]')).toHaveLength(1);
  });

  it('opens the taskboard from Tools › Taskboard', async () => {
    serve();
    render(<App />);
    const tools = within(screen.getByRole('navigation', { name: 'Pages and agents' }));
    fireEvent.click(tools.getByRole('link', { name: 'Taskboard' }));
    expect(location.hash).toBe('#/taskboard');
    expect(await screen.findByRole('heading', { level: 1, name: 'Taskboard' })).toBeTruthy();
    expect(tools.getByRole('link', { name: 'Taskboard' }).getAttribute('aria-current')).toBe('page');
  });

  it('opens the Claude page from the sidebar\'s Peter row, from any page, marked as the current page there', async () => {
    location.hash = '#/codex';
    serveRoutes({ 'GET api/agents': { agents, at: '2026-10-09T10:00:00Z' } });
    render(<App />);
    fireEvent.click(await screen.findByRole('link', { name: /^Peter · Claude Code/ }));
    expect(location.hash).toBe('#/claude');
    await waitFor(() => expect(screen.getByRole('link', { name: /^Peter · Claude Code/ }).getAttribute('aria-current')).toBe('page'));
    expect(screen.getByRole('link', { name: /^Aster · Codex/ }).getAttribute('aria-current')).toBeNull();
    // The page is Peter's, under Agents: the top bar's link stays filled but is not the current page.
    const top = within(screen.getByRole('navigation', { name: 'Main pages' }));
    expect(top.getByRole('link', { name: 'Agents' }).className).toBe('on');
    expect(document.querySelectorAll('[aria-current="page"]')).toHaveLength(1);
  });

  it('keeps May\'s row opening her panel', async () => {
    serve();
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: /^May · Pi/ }));
    expect(location.hash).toBe('#/?peek=agent%3AMay');
    expect(await screen.findByRole('dialog', { name: 'May · Pi' })).toBeTruthy();
  });

  it('names the other language on the language button: 中文 in English, English in Cantonese', async () => {
    serve();
    render(<App />);
    const button = await screen.findByRole('button', { name: 'Switch language' });
    expect(button.textContent).toBe('中文');
    fireEvent.click(button);
    expect((await screen.findByRole('button', { name: '切換語言' })).textContent).toBe('English');
  });

  it('counts what waits beside Tasks in grey, with an orange dot only while a question waits', async () => {
    serveRoutes({
      'GET api/tasks': { code: 'ok', at: '2026-10-14T02:00:00Z', titles: {}, runs: [], sections: [
        { status: 'needs-owner', file: 'Setup/a.md', line: 7, heading: 'h1' },
        { status: 'blocked', file: 'Library/b.md', line: 3, heading: 'h2' },
        { status: 'open', file: 'README.md', line: 9, heading: 'h3' },
      ] },
      'GET api/questions': { version: 1, questions: [question('q-1', { status: 'open' })] },
    });
    render(<App />);
    const link = await screen.findByRole('link', { name: /Tasks/ });
    await waitFor(() => expect(link.querySelector('.cnt.quiet')?.textContent).toBe('3'));
    // The number is hidden from screen readers; they hear the words instead.
    expect(screen.getByRole('link', { name: 'Tasks, 3 waiting for you' })).toBeTruthy();
    expect(link.querySelector('.dot.wait')).not.toBeNull();
  });

  it('keeps the orange dot off while only sections wait', async () => {
    serveRoutes({
      'GET api/tasks': { code: 'ok', at: '2026-10-14T02:00:00Z', titles: {}, runs: [], sections: [
        { status: 'needs-owner', file: 'Setup/a.md', line: 7, heading: 'h1' },
        { status: 'blocked', file: 'Library/b.md', line: 3, heading: 'h2' },
      ] },
      'GET api/questions': { version: 1, questions: [question('q-1', { status: 'answered' })] },
    });
    render(<App />);
    const link = await screen.findByRole('link', { name: /Tasks/ });
    await waitFor(() => expect(link.querySelector('.cnt.quiet')?.textContent).toBe('2'));
    expect(link.querySelector('.dot.wait')).toBeNull();
  });

  it('leaves the top bar\'s Agents link unfilled on the Tasks page', async () => {
    location.hash = '#/tasks';
    serveRoutes();
    render(<App />);
    const top = within(screen.getByRole('navigation', { name: 'Main pages' }));
    await waitFor(() => expect(top.getByRole('link', { name: 'Agents' }).className).toBe(''));
    expect(top.getByRole('link', { name: 'Agents' }).getAttribute('aria-current')).toBeNull();
  });
});
