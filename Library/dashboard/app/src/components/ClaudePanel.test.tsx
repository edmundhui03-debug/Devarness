import { describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { AgentView } from '../api';
import { fmtTime } from '../format';
import { I18nProvider } from '../i18n';
import { CLAUDE_ID, CLAUDE_VIEW, Fail, agentRow, calls, serve, step } from '../test-fakes';
import { ClaudePanel } from './ClaudePanel';

const SESSION = `GET api/claude/sessions/${CLAUDE_ID}`;
const AGENT = `GET api/claude/sessions/${CLAUDE_ID}/agents/agent-a1`;
const AGENT_VIEW: AgentView = { ...agentRow('agent-a1', { title: 'Review the server track', state: 'idle' }), readable: true,
  steps: [step('prompt', 'Review server/claude.mjs'), step('reply', 'One finding.')] };

function show(routes = {}, agent: string | null = null, onOpen = vi.fn()) {
  const fetchMock = serve({ [SESSION]: CLAUDE_VIEW, [AGENT]: AGENT_VIEW, ...routes });
  const ui = (session: string) => <I18nProvider><ClaudePanel session={session} agent={agent} onOpen={onOpen} /></I18nProvider>;
  const { rerender, unmount } = render(ui(CLAUDE_ID));
  return { fetchMock, onOpen, unmount, rerender: (session: string) => rerender(ui(session)) };
}
const steps = () => within(screen.getByRole('list', { name: 'Last steps' })).queryAllByRole('listitem').map((li) => li.textContent);
const value = (name: string) => screen.getByText(name, { selector: 'dt' }).nextElementSibling as HTMLElement;
const wait = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));
// The tab hidden or shown, as a browser says it; the finally of each test that calls it restores the page's own.
const tab = (state: 'visible' | 'hidden') => {
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state });
  document.dispatchEvent(new Event('visibilitychange'));
};

describe('the session panel', () => {
  it('shows the session\'s fields, its last commits and its steps, each labelled by its kind', async () => {
    show();
    expect(await screen.findByRole('heading', { name: 'Build wave 4' })).toBeTruthy();
    expect(['State', 'Source', 'Folder', 'Branch', 'Updated'].map((n) => value(n).textContent)).toEqual(
      ['idle', 'Terminal', 'dev', 'worktree-dashboard-wave-4', fmtTime('2026-10-15T02:00:00Z', 'en')]);
    expect(value('Folder').getAttribute('title')).toBe('C:\\work\\dev');
    const commits = within(screen.getByRole('list', { name: 'Last commits' })).getAllByRole('listitem');
    expect(commits.map((li) => li.textContent)).toEqual([`c487c56 ${fmtTime('2026-10-15T01:00:00Z', 'en')} · Plan dashboard wave 4`]);
    expect(steps()).toEqual(['YouBuild the Claude page', 'Thinking', 'ClaudeReading the plan first.', 'Tool · Bashnpm test', 'Result · Bash error2 failed']);
  });

  it('filters the steps to Turns or Tools, and back to All', async () => {
    show();
    await screen.findByText('Reading the plan first.');
    fireEvent.click(screen.getByRole('button', { name: 'Turns' }));
    expect(steps()).toEqual(['YouBuild the Claude page', 'ClaudeReading the plan first.']);
    fireEvent.click(screen.getByRole('button', { name: 'Tools' }));
    expect(steps()).toEqual(['Tool · Bashnpm test', 'Result · Bash error2 failed']);
    expect(screen.getByRole('button', { name: 'Tools' }).getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: 'All' }));
    expect(steps()).toHaveLength(5);
  });

  it('says the commits are not readable when the server has none to give', async () => {
    show({ [SESSION]: { ...CLAUDE_VIEW, commits: null } });
    expect(await screen.findByText(/^Not readable/)).toBeTruthy();
    expect(screen.queryByRole('list', { name: 'Last commits' })).toBeNull();
    expect(screen.getByText('Reading the plan first.')).toBeTruthy();
  });

  it('says a history that cannot be read, and an empty one, without breaking the rest', async () => {
    show({ [SESSION]: { ...CLAUDE_VIEW, readable: false, steps: [] } });
    expect(await screen.findByText('This session\'s history cannot be read.')).toBeTruthy();
    expect(value('Branch').textContent).toBe('worktree-dashboard-wave-4');
    expect(screen.getByRole('button', { name: 'Review the server track' })).toBeTruthy();
    expect(screen.queryByText('No steps to show in the last 20.')).toBeNull();
  });

  it('shows the empty note when a readable history holds no step', async () => {
    show({ [SESSION]: { ...CLAUDE_VIEW, steps: [] } });
    expect(await screen.findByText('No steps to show in the last 20.')).toBeTruthy();
    expect(screen.queryByText('This session\'s history cannot be read.')).toBeNull();
  });

  it('lists the direct subagents and each workflow run with its agents, and a subagent opens as a:<session>:<agent>', async () => {
    const { onOpen } = show();
    const agents = within(await screen.findByRole('list', { name: 'Subagents' }));
    const row = agents.getByRole('button', { name: 'Review the server track' }).closest('li')!;
    expect(row.textContent).toBe(`Review the server track working · general-purpose · ${fmtTime('2026-10-15T01:58:00Z', 'en')}`);
    const run = screen.getByText('dashboard-wave-4').closest('li')!;
    expect(within(run).getByText('running').className).toBe('chip chip-running');
    expect(within(run).getByText('Agents: 2')).toBeTruthy();
    expect(run.textContent).toContain(`Agents: 2 · ${fmtTime('2026-10-15T01:58:00Z', 'en')}`); // a running run's last update: its newest agent's
    expect(within(run).getByText('Two tracks, one worktree')).toBeTruthy();
    fireEvent.click(within(run).getByRole('button', { name: 'App track' }));
    expect(onOpen).toHaveBeenLastCalledWith(`a:${CLAUDE_ID}:agent-r1`);
    fireEvent.click(agents.getByRole('button', { name: 'Review the server track' }));
    expect(onOpen).toHaveBeenLastCalledWith(`a:${CLAUDE_ID}:agent-a1`);
  });

  it('shows a finished run\'s last update as its end, its start and duration added, and a run with only a start by its start', async () => {
    const run = CLAUDE_VIEW.runs[0];
    show({ [SESSION]: { ...CLAUDE_VIEW, runs: [
      { ...run, status: 'completed', durationMs: 3 * 3_600_000, agents: [agentRow('agent-r1', { title: 'App track', updatedAt: '2026-10-15T03:59:00Z' })] },
      { ...run, id: 'wf_b', name: 'second run', agents: [] }] } });
    const head = (name: string) => screen.getByText(name).closest('li')!.textContent;
    expect(await screen.findByText('completed')).toBeTruthy();
    expect(head('dashboard-wave-4')).toContain(`Agents: 2 · ${fmtTime('2026-10-15T04:00:00Z', 'en')}`);
    expect(head('second run')).toContain(`Agents: 2 · ${fmtTime('2026-10-15T01:00:00Z', 'en')}`);
  });

  it('words a status it does not know as written, a killed run as stopped, and a failed run as an error', async () => {
    show({ [SESSION]: { ...CLAUDE_VIEW, runs: [{ ...CLAUDE_VIEW.runs[0], status: 'cancelled', agentCount: null },
      { ...CLAUDE_VIEW.runs[0], id: 'wf_b', name: 'second run', status: 'failed', agentCount: null, startedAt: null, agents: [] },
      { ...CLAUDE_VIEW.runs[0], id: 'wf_c', name: 'third run', status: 'killed', agentCount: null, agents: [] }] } });
    expect((await screen.findByText('cancelled')).className).toBe('chip');
    expect(screen.getByText('failed').className).toBe('chip chip-error');
    expect(screen.getByText('stopped').className).toBe('chip');
    expect(screen.queryByText(/^Agents: \d+$/)).toBeNull();
    expect(screen.getByText('second run').closest('li')!.textContent).toMatch(/^second run failed\s+· —/); // no start time known
  });

  it('renders step text, titles and summaries as text, never as markup', async () => {
    const markup = '<img src=x onerror=alert(1)>';
    show({ [SESSION]: { ...CLAUDE_VIEW, title: markup, steps: [step('reply', markup)],
      runs: [{ ...CLAUDE_VIEW.runs[0], summary: markup }], agents: [agentRow('agent-a1', { title: markup })] } });
    expect(await screen.findByRole('heading', { name: markup })).toBeTruthy();
    expect(steps()).toEqual([`Claude${markup}`]);
    expect(screen.getAllByText(markup)).toHaveLength(4);
    expect(document.querySelector('img')).toBeNull();
  });
});

describe('the panel reads again while it is open', () => {
  it('reads a working session again after 3 s, an ended or idle one not before 10 s, and stops once closed', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let state = 'working'; // what the next reading answers
      const { fetchMock, unmount } = show({ [SESSION]: () => ({ ...CLAUDE_VIEW, state }) });
      await screen.findByText('Reading the plan first.');
      const reads = () => calls(fetchMock, SESSION).length;
      expect(reads()).toBe(1);
      await wait(3_000);
      expect(reads()).toBe(2);
      state = 'ended';
      await wait(3_000);
      expect(reads()).toBe(3); // this reading answers ended, so the next waits 10 s
      await wait(3_000);
      expect(reads()).toBe(3);
      await wait(6_000);
      expect(reads()).toBe(3);
      await wait(1_000);
      expect(reads()).toBe(4);
      state = 'idle';
      await wait(10_000);
      expect(reads()).toBe(5); // this reading answers idle, so the next waits 10 s
      await wait(3_000);
      expect(reads()).toBe(5);
      await wait(6_000);
      expect(reads()).toBe(5);
      await wait(1_000);
      expect(reads()).toBe(6);
      unmount();
      await wait(30_000);
      expect(reads()).toBe(6);
    } finally {
      vi.useRealTimers();
    }
  });

  it('reads at once when a tab it opened in hidden is shown', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      tab('hidden');
      const { fetchMock } = show({ [SESSION]: { ...CLAUDE_VIEW, state: 'working' } });
      await wait(500);
      expect(calls(fetchMock, SESSION)).toHaveLength(0);
      expect(screen.getByText('Loading…')).toBeTruthy();
      act(() => tab('visible'));
      await wait(100);
      expect(calls(fetchMock, SESSION)).toHaveLength(1);
      expect(screen.getByText('Reading the plan first.')).toBeTruthy();
    } finally {
      Reflect.deleteProperty(document, 'visibilityState');
      vi.useRealTimers();
    }
  });

  it('reads a working session at once when its tab is shown again, and every 3 s after', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const { fetchMock } = show({ [SESSION]: { ...CLAUDE_VIEW, state: 'working' } });
      await screen.findByText('Reading the plan first.');
      const reads = () => calls(fetchMock, SESSION).length;
      act(() => tab('hidden'));
      await wait(3_000); // the reading due now is skipped while hidden
      expect(reads()).toBe(1);
      act(() => tab('visible'));
      await wait(100);
      expect(reads()).toBe(2);
      await wait(3_000);
      expect(reads()).toBe(3);
    } finally {
      Reflect.deleteProperty(document, 'visibilityState');
      vi.useRealTimers();
    }
  });

  it('reads one at a time: a slow reading holds back the next', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let release = () => {};
      let n = 0;
      const { fetchMock } = show({ [SESSION]: () => (++n === 1 ? { ...CLAUDE_VIEW, state: 'working' }
        : new Promise((done) => { release = () => done({ ...CLAUDE_VIEW, state: 'working', title: 'Second reading' }); })) });
      await screen.findByText('Reading the plan first.');
      await act(() => vi.advanceTimersByTimeAsync(3_000));
      expect(calls(fetchMock, SESSION)).toHaveLength(2);
      await act(() => vi.advanceTimersByTimeAsync(20_000));
      expect(calls(fetchMock, SESSION)).toHaveLength(2);
      act(() => tab('visible')); // the tab shown again while a reading is on its way asks nothing more
      await wait(100);
      expect(calls(fetchMock, SESSION)).toHaveLength(2);
      await act(async () => release());
      expect(await screen.findByRole('heading', { name: 'Second reading' })).toBeTruthy();
      await act(() => vi.advanceTimersByTimeAsync(3_000));
      expect(calls(fetchMock, SESSION)).toHaveLength(3);
    } finally {
      Reflect.deleteProperty(document, 'visibilityState');
      vi.useRealTimers();
    }
  });

  it('never lets a late answer for the session it showed before replace the one it shows now', async () => {
    const other = '0b1c2d3e-0000-4000-8000-00000000c002';
    let release = () => {};
    const { rerender } = show({
      [SESSION]: () => new Promise((done) => { release = () => done(CLAUDE_VIEW); }),
      [`GET api/claude/sessions/${other}`]: { ...CLAUDE_VIEW, id: other, title: 'The other session' },
    });
    rerender(other);
    expect(await screen.findByRole('heading', { name: 'The other session' })).toBeTruthy();
    await act(async () => release());
    await act(() => new Promise((done) => setTimeout(done, 20)));
    expect(screen.queryByRole('heading', { name: 'Build wave 4' })).toBeNull();
    expect(screen.getByRole('heading', { name: 'The other session' })).toBeTruthy();
  });
});

describe('the subagent panel', () => {
  it('shows the subagent\'s fields and steps, and links back to its session', async () => {
    const { onOpen, fetchMock } = show({}, 'agent-a1');
    expect(await screen.findByRole('heading', { name: 'Review the server track' })).toBeTruthy();
    expect(['State', 'Type', 'Updated'].map((n) => value(n).textContent)).toEqual(
      ['idle', 'general-purpose', fmtTime('2026-10-15T01:58:00Z', 'en')]);
    expect(steps()).toEqual(['YouReview server/claude.mjs', 'ClaudeOne finding.']);
    expect(calls(fetchMock, SESSION)).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: 'Back to session PET-C001' }));
    expect(onOpen).toHaveBeenCalledWith(`c:${CLAUDE_ID}`);
  });

  it('names the workflow run a run\'s agent belongs to', async () => {
    show({ [`GET api/claude/sessions/${CLAUDE_ID}/agents/agent-r1`]: { ...AGENT_VIEW, id: 'agent-r1', run: 'wf_build-1' } }, 'agent-r1');
    await screen.findByText('One finding.');
    expect(value('Workflow run').textContent).toBe('wf_build-1');
  });
});

describe('an address the server does not answer', () => {
  it('words a session or a subagent the server answers 404 as not found, in either language, never by the server\'s text', async () => {
    show({ [SESSION]: new Fail(404, 'not-found') });
    expect(await screen.findByText('There is no such thread, session or subagent now.')).toBeTruthy();
    expect(document.body.textContent).not.toContain('C:\\secret\\path'); // the server's own error text
    cleanup();
    localStorage.setItem('dash.lang', 'zh-HK');
    show({ [AGENT]: new Fail(404, 'not-found') }, 'agent-a1');
    expect(await screen.findByText('現時沒有這個對話串、工作階段或子代理。')).toBeTruthy();
  });

  it('asks nothing for an id that cannot be a session or an agent, and words it as not found', async () => {
    for (const [session, agent] of [['../../.credentials', null], ['..', null], [CLAUDE_ID.toUpperCase(), null],
      [CLAUDE_ID, '../x'], [CLAUDE_ID, '..'], [CLAUDE_ID, 'agent-a1/../agent-b2'], [CLAUDE_ID, '%2E%2E']] as const) {
      const fetchMock = serve();
      const { unmount } = render(<I18nProvider><ClaudePanel session={session} agent={agent} onOpen={() => {}} /></I18nProvider>);
      expect(screen.getByRole('alert').textContent, `${session} ${agent}`).toBe('There is no such thread, session or subagent now.');
      await act(() => new Promise((done) => setTimeout(done, 10)));
      expect(fetchMock.mock.calls.map(([url]) => url), `${session} ${agent}`).toEqual([]);
      unmount();
    }
  });

  it('keeps the last reading on screen when a later one fails, with the failure said above it', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      let n = 0;
      show({ [SESSION]: () => (++n === 1 ? { ...CLAUDE_VIEW, state: 'working' } : new Fail(500, 'internal')) });
      await screen.findByText('Reading the plan first.');
      await act(() => vi.advanceTimersByTimeAsync(3_000));
      await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('The dashboard server hit an unexpected error; try again.'));
      expect(screen.getByText('Reading the plan first.')).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });
});
