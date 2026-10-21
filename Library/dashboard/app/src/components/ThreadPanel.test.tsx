import { describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { fmtTime } from '../format';
import { I18nProvider } from '../i18n';
import { RunsProvider } from '../runs';
import { FakeEventSource, Fail, VIEW, calls, serve } from '../test-fakes';
import { ThreadPanel } from './ThreadPanel';

function show(routes = {}, view = VIEW) {
  const fetchMock = serve({ 'GET api/codex/threads/th-dev': view, ...routes });
  render(<I18nProvider><RunsProvider><ThreadPanel id="th-dev" onOpen={() => {}} /></RunsProvider></I18nProvider>);
  return fetchMock;
}
const lines = () => screen.getAllByRole('listitem').map((li) => li.textContent);
const reads = (fetchMock: ReturnType<typeof serve>) => calls(fetchMock, 'GET api/codex/threads/th-dev').length;

describe('the thread panel', () => {
  it('shows the thread\'s title, state, source, folder and times, then its turns as text', async () => {
    show({}, { ...VIEW, turns: [...VIEW.turns, { items: [{ type: 'agentMessage', text: '<img src=x onerror=alert(1)>' }] }] });
    expect(await screen.findByRole('heading', { name: 'Tidy the router' })).toBeTruthy();
    const value = (name: string) => screen.getByText(name, { selector: 'dt' }).nextElementSibling?.textContent;
    expect([value('State'), value('Source'), value('Folder'), value('Created'), value('Updated')]).toEqual(
      ['idle', 'Terminal', 'dev', fmtTime(1790000000 * 1000, 'en'), fmtTime(1790000500 * 1000, 'en')]);
    expect(lines()).toEqual(['PromptList the hooks', 'Command$ ls .claude/hooks → exit 0\nguard.sh', 'Filesupdate CLAUDE.md',
      'CodexThere are eleven hooks.', 'Codex<img src=x onerror=alert(1)>']);
    expect(document.querySelector('img')).toBeNull();
  });

  it('filters the items to Turns, Commands or Files, and back to All', async () => {
    show();
    await screen.findByText('There are eleven hooks.');
    fireEvent.click(screen.getByRole('button', { name: 'Commands' }));
    expect(lines()).toEqual(['Command$ ls .claude/hooks → exit 0\nguard.sh']);
    fireEvent.click(screen.getByRole('button', { name: 'Files' }));
    expect(lines()).toEqual(['Filesupdate CLAUDE.md']);
    fireEvent.click(screen.getByRole('button', { name: 'Turns' }));
    expect(lines()).toEqual(['PromptList the hooks', 'CodexThere are eleven hooks.']);
    expect(screen.getByRole('button', { name: 'Turns' }).getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: 'All' }));
    expect(lines()).toHaveLength(4);
  });

  it('offers workspace-write only on a thread whose folder is the dev workspace', async () => {
    show();
    const options = async () => Array.from((await screen.findByRole('combobox', { name: 'Sandbox' })).querySelectorAll('option')).map((o) => o.value);
    expect(await options()).toEqual(['read-only', 'workspace-write']);
    cleanup();
    show({}, { ...VIEW, inDev: false, cwd: 'D:\\work\\pcb' });
    expect(await options()).toEqual(['read-only']);
  });

  it('runs the prompt with its sandbox, then offers Stop, which posts the turn', async () => {
    const fetchMock = show({ 'POST api/codex/run': { thread: 'th-dev', turn: 'turn-9' }, 'POST api/codex/stop': { ok: true } });
    const box = await screen.findByLabelText('Reply to continue this thread');
    const run = screen.getByRole('button', { name: 'Run' }) as HTMLButtonElement;
    expect(run.disabled).toBe(true);
    fireEvent.change(box, { target: { value: 'Now tidy them' } });
    fireEvent.change(screen.getByRole('combobox', { name: 'Sandbox' }), { target: { value: 'workspace-write' } });
    fireEvent.click(run);
    fireEvent.click(await screen.findByRole('button', { name: 'Stop' }));
    expect(calls(fetchMock, 'POST api/codex/run')).toEqual([{ prompt: 'Now tidy them', sandbox: 'workspace-write', thread: 'th-dev' }]);
    // workspace-write is for one reply: the box empties and goes back to read-only.
    expect((box as HTMLTextAreaElement).value).toBe('');
    expect((screen.getByRole('combobox', { name: 'Sandbox' }) as HTMLSelectElement).value).toBe('read-only');
    await waitFor(() => expect(calls(fetchMock, 'POST api/codex/stop')).toEqual([{ thread: 'th-dev', turn: 'turn-9' }]));
  });

  it('offers Stop for the turn the server holds, as after a reload, until the server lets it go', async () => {
    let turn: string | null = 'turn-7';
    const fetchMock = show({ 'GET api/codex/threads/th-dev': () => ({ ...VIEW, state: turn ? 'running' : 'idle', turn }),
      'POST api/codex/stop': { ok: true } });
    fireEvent.click(await screen.findByRole('button', { name: 'Stop' }));
    await waitFor(() => expect(calls(fetchMock, 'POST api/codex/stop')).toEqual([{ thread: 'th-dev', turn: 'turn-7' }]));
    turn = null;
    act(() => FakeEventSource.current.emit('turn/completed', { threadId: 'th-dev', turn: { id: 'turn-7', status: 'interrupted' } }));
    expect(await screen.findByRole('button', { name: 'Run' })).toBeTruthy();
  });

  it('lets go of the turn when Codex stops, without reading the thread, and reads it when Codex is back', async () => {
    const fetchMock = show({ 'GET api/codex/threads/th-dev': { ...VIEW, state: 'running', turn: 'turn-7' } });
    await screen.findByRole('button', { name: 'Stop' });
    // The app-server ended mid-turn: the server let the turn go, and no turn/completed came.
    act(() => FakeEventSource.current.emit('bridge/appServer', { up: false }));
    expect(await screen.findByRole('button', { name: 'Run' })).toBeTruthy();
    expect(reads(fetchMock)).toBe(1);
    act(() => FakeEventSource.current.emit('bridge/appServer', { up: true }));
    await waitFor(() => expect(reads(fetchMock)).toBe(2));
  });

  it('makes no reading loop when Codex cannot start again', async () => {
    let n = 0;
    // As the server does: each reading tries Codex once more, and a failed try says up:false on the stream.
    const fetchMock = show({ 'GET api/codex/threads/th-dev': () => {
      if (++n === 1) return VIEW;
      setTimeout(() => FakeEventSource.current?.emit('bridge/appServer', { up: false }), 10);
      return new Fail(502, 'codex-not-started');
    } });
    await screen.findByText('There are eleven hooks.');
    act(() => FakeEventSource.current.emit('bridge/appServer', { up: false }));
    await act(() => new Promise((done) => setTimeout(done, 200)));
    expect(reads(fetchMock)).toBe(1);
  });

  it('offers Run again when Stop finds the server no longer holds the turn, though the reading after its end failed', async () => {
    let n = 0;
    const fetchMock = show({
      'GET api/codex/threads/th-dev': () => (++n === 1 ? { ...VIEW, state: 'running', turn: 'turn-7' } : new Fail(504, 'codex-timeout')),
      'POST api/codex/stop': new Fail(404, 'unknown-turn'),
    });
    await screen.findByRole('button', { name: 'Stop' });
    act(() => FakeEventSource.current.emit('turn/completed', { threadId: 'th-dev', turn: { id: 'turn-7', status: 'completed' } }));
    expect(await screen.findByText('Codex did not answer in time; try again.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Stop' }));
    expect(await screen.findByText('This turn was not started from this page, or it has ended.')).toBeTruthy();
    expect(await screen.findByRole('button', { name: 'Run' })).toBeTruthy();
    expect(reads(fetchMock)).toBe(2);
  });

  it('words a refused run by its code in either language, never by the server\'s text, and keeps the prompt', async () => {
    for (const [lang, box, run, busy] of [
      ['en', 'Reply to continue this thread', 'Run', 'This thread is already running, here or in another Codex window.'],
      ['zh-HK', '回覆以繼續此對話串', '執行', '此對話串正在執行，可能在此頁或另一個 Codex 視窗。'],
    ]) {
      localStorage.setItem('dash.lang', lang);
      show({ 'POST api/codex/run': new Fail(409, 'thread-busy') });
      fireEvent.change(await screen.findByLabelText(box), { target: { value: 'Again' } });
      fireEvent.click(screen.getByRole('button', { name: run }));
      expect(await screen.findByText(busy)).toBeTruthy();
      expect(screen.queryByText(/secret/)).toBeNull();
      expect((screen.getByLabelText(box) as HTMLTextAreaElement).value).toBe('Again');
      cleanup();
    }
  });

  it('reads the thread again on its own events, one reading at a time, and ignores other threads', async () => {
    let n = 0;
    let release = () => {};
    const fetchMock = show({ 'GET api/codex/threads/th-dev': () => (++n === 1 ? VIEW : new Promise((done) => { release = () => done(VIEW); })) });
    await screen.findByText('There are eleven hooks.');
    const stream = FakeEventSource.current;
    act(() => { stream.open(); stream.emit('item/completed', { threadId: 'th-other', turnId: 't1', item: {} }); });
    expect(reads(fetchMock)).toBe(1);
    act(() => {
      stream.emit('turn/started', { threadId: 'th-dev', turn: { id: 't9' } });
      stream.emit('item/completed', { threadId: 'th-dev', turnId: 't9', item: {} });
      stream.emit('turn/completed', { threadId: 'th-dev', turn: { id: 't9', status: 'completed' } });
    });
    expect(reads(fetchMock)).toBe(2);
    await act(async () => release());
    // What came in meanwhile is read once more, and no more than that.
    await waitFor(() => expect(reads(fetchMock)).toBe(3));
    await act(async () => release());
    expect(reads(fetchMock)).toBe(3);
  });

  it('reads the thread once when the event stream comes back, and shows no line twice', async () => {
    const fetchMock = show();
    await screen.findByText('There are eleven hooks.');
    const stream = FakeEventSource.current;
    act(() => stream.open());
    expect(reads(fetchMock)).toBe(1);
    act(() => { stream.drop(); stream.open(); });
    await waitFor(() => expect(reads(fetchMock)).toBe(2));
    await act(async () => {});
    expect(reads(fetchMock)).toBe(2);
    expect(screen.getAllByText('There are eleven hooks.')).toHaveLength(1);
    expect(lines()).toHaveLength(4);
  });

  it('says a thread Codex does not have is not found', async () => {
    show({ 'GET api/codex/threads/th-dev': new Fail(404, 'not-found') });
    expect(await screen.findByText('There is no such thread, session or subagent now.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Run' })).toBeNull();
  });

  it('posts Stop once however fast it is clicked, and offers it again once the request returns', async () => {
    let release!: () => void;
    const held = new Promise<{ ok: true }>((done) => { release = () => done({ ok: true }); });
    const fetchMock = show({ 'POST api/codex/run': { thread: 'th-dev', turn: 'turn-9' }, 'POST api/codex/stop': () => held });
    fireEvent.change(await screen.findByLabelText('Reply to continue this thread'), { target: { value: 'Go on' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    const stop = await screen.findByRole('button', { name: 'Stop' }) as HTMLButtonElement;
    fireEvent.click(stop);
    fireEvent.click(stop);
    await waitFor(() => expect(stop.disabled).toBe(true));
    expect(calls(fetchMock, 'POST api/codex/stop')).toHaveLength(1);
    await act(async () => release());
    await waitFor(() => expect(stop.disabled).toBe(false));
  });
});

describe('the composer', () => {
  it('starts a new thread, read-only by default, and opens it', async () => {
    const onOpen = vi.fn();
    const fetchMock = serve({ 'POST api/codex/run': { thread: 'th-new', turn: 'turn-1' } });
    render(<I18nProvider><RunsProvider><ThreadPanel id={null} onOpen={onOpen} /></RunsProvider></I18nProvider>);
    expect(screen.getByRole('heading', { name: 'New thread' })).toBeTruthy();
    fireEvent.change(screen.getByLabelText('Prompt for a new thread'), { target: { value: 'Read the router' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    await waitFor(() => expect(onOpen).toHaveBeenCalledWith('th-new'));
    expect(calls(fetchMock, 'POST api/codex/run')).toEqual([{ prompt: 'Read the router', sandbox: 'read-only', thread: null }]);
  });
});
