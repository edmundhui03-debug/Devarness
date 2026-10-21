import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { App } from './App';
import { FakeEventSource, Fail, VIEW, calls, serve, thread } from './test-fakes';

// The Codex page with th-dev's panel open; Run answers with turn-9 unless a test says otherwise.
function open(routes = {}) {
  location.hash = '#/codex?peek=t%3Ath-dev';
  const fetchMock = serve({ 'GET api/codex/threads': { threads: [thread('th-dev', { name: 'Tidy the router' })] },
    'GET api/codex/threads/th-dev': VIEW, 'POST api/codex/run': { thread: 'th-dev', turn: 'turn-9' }, ...routes });
  render(<App />);
  return fetchMock;
}
async function run() {
  const panel = within(await screen.findByRole('dialog'));
  fireEvent.change(await panel.findByLabelText('Reply to continue this thread'), { target: { value: 'Go on' } });
  fireEvent.click(panel.getByRole('button', { name: 'Run' }));
  return panel;
}

describe('a run started from the page', () => {
  it('keeps its Stop button after the owner goes to Agents and comes back', async () => {
    open();
    await (await run()).findByRole('button', { name: 'Stop' });
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Pages and agents' })).getByRole('link', { name: 'Agents' }));
    await screen.findByRole('heading', { level: 1, name: 'Agents' });
    act(() => { location.hash = '#/codex?peek=t%3Ath-dev'; });
    expect(await within(await screen.findByRole('dialog')).findByRole('button', { name: 'Stop' })).toBeTruthy();
  });

  it('ends when Codex says its turn completed, and Run comes back', async () => {
    open();
    const panel = await run();
    await panel.findByRole('button', { name: 'Stop' });
    act(() => FakeEventSource.current.emit('turn/completed', { threadId: 'th-dev', turn: { id: 'turn-8', status: 'completed' } }));
    expect(panel.getByRole('button', { name: 'Stop' })).toBeTruthy(); // another turn's end is not this run's
    act(() => FakeEventSource.current.emit('turn/completed', { threadId: 'th-dev', turn: { id: 'turn-9', status: 'interrupted' } }));
    expect(await panel.findByRole('button', { name: 'Run' })).toBeTruthy();
  });

  it('never holds a turn that ended before its reply came back', async () => {
    let reply = (_: unknown) => {};
    open({ 'POST api/codex/run': () => new Promise((done) => { reply = done; }) });
    const panel = await run();
    act(() => FakeEventSource.current.emit('turn/completed', { threadId: 'th-dev', turn: { id: 'turn-9', status: 'completed' } }));
    await act(async () => reply({ thread: 'th-dev', turn: 'turn-9' }));
    expect(panel.queryByRole('button', { name: 'Stop' })).toBeNull();
    expect(panel.getByRole('button', { name: 'Run' })).toBeTruthy();
  });

  it('lets go of a turn the server no longer knows, and says so', async () => {
    const fetchMock = open({ 'POST api/codex/stop': new Fail(404, 'unknown-turn') });
    const panel = await run();
    fireEvent.click(await panel.findByRole('button', { name: 'Stop' }));
    expect(await panel.findByText('This turn was not started from this page, or it has ended.')).toBeTruthy();
    expect(panel.getByRole('button', { name: 'Run' })).toBeTruthy();
    expect(calls(fetchMock, 'POST api/codex/stop')).toEqual([{ thread: 'th-dev', turn: 'turn-9' }]);
  });

  it('ends when Codex itself stops mid-turn, since no turn/completed will come', async () => {
    const fetchMock = open();
    const panel = await run();
    await panel.findByRole('button', { name: 'Stop' });
    act(() => FakeEventSource.current.emit('bridge/appServer', { up: false }));
    expect(await panel.findByRole('button', { name: 'Run' })).toBeTruthy();
    expect(calls(fetchMock, 'POST api/codex/stop')).toEqual([]);
  });

  it('after a reconnect, keeps Stop while the thread runs and lets go once the server says it does not', async () => {
    let state: 'running' | 'idle' = 'running';
    open({ 'GET api/codex/threads': () => ({ threads: [thread('th-dev', { name: 'Tidy the router', state })] }) });
    const panel = await run();
    await panel.findByRole('button', { name: 'Stop' });
    const stream = FakeEventSource.current;
    // The laptop sleeps and wakes with the turn still running.
    act(() => { stream.open(); stream.drop(); stream.open(); });
    await act(() => new Promise((done) => setTimeout(done, 0)));
    expect(panel.getByRole('button', { name: 'Stop' })).toBeTruthy();
    // It sleeps again, and the turn's end comes while the stream is down.
    state = 'idle';
    act(() => { stream.drop(); stream.open(); });
    expect(await panel.findByRole('button', { name: 'Run' })).toBeTruthy();
  });

  it('opens the event stream again when the browser gave up on it', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      open();
      await screen.findByRole('dialog');
      const first = FakeEventSource.current;
      expect(first.url).toBe('api/codex/events');
      act(() => { first.open(); first.drop(FakeEventSource.CLOSED); });
      await act(async () => { vi.advanceTimersByTime(5000); });
      const second = FakeEventSource.current;
      expect(second).not.toBe(first);
      expect(second.url).toBe('api/codex/events');
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('the composer', () => {
  it('starts a thread from the Create button and opens it, with its Stop', async () => {
    location.hash = '#/codex';
    const fetchMock = serve({ 'POST api/codex/run': { thread: 'th-new', turn: 'turn-1' },
      'GET api/codex/threads/th-new': { ...VIEW, id: 'th-new', name: 'Read the router', turns: [] } });
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: 'Create a thread' }));
    expect(location.hash).toBe('#/codex?peek=new');
    const panel = within(await screen.findByRole('dialog', { name: 'New thread' }));
    fireEvent.change(panel.getByLabelText('Prompt for a new thread'), { target: { value: 'Read the router' } });
    fireEvent.click(panel.getByRole('button', { name: 'Run' }));
    await waitFor(() => expect(location.hash).toBe('#/codex?peek=t%3Ath-new'));
    const opened = within(await screen.findByRole('dialog'));
    expect(await opened.findByRole('heading', { name: 'Read the router' })).toBeTruthy();
    expect(opened.getByRole('button', { name: 'Stop' })).toBeTruthy();
    expect(calls(fetchMock, 'POST api/codex/run')).toEqual([{ prompt: 'Read the router', sandbox: 'read-only', thread: null }]);
  });
});
