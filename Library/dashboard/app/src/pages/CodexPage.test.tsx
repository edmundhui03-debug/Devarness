import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { App } from '../App';
import { fmtTime } from '../format';
import { FakeEventSource, Fail, STATUS, calls, question, serve, thread } from '../test-fakes';

const threads = [
  thread('th-run', { state: 'running', name: 'Running here' }),
  thread('th-else', { state: 'active-elsewhere', name: 'In the app', source: 'vscode', cwd: 'D:\\work\\pcb' }),
  thread('th-idle', { name: 'Tidy the router' }),
  thread('th-err', { state: 'error', name: 'Broke once', source: 'exec', cwd: 'D:\\work\\pcb' }),
];
const questions = [question('q-2026-10-10-library-001'), question('q-2026-10-10-pcb-002', { asked_by: 'May', question: 'May asks' })];

function open(routes = {}) {
  location.hash = '#/codex';
  const fetchMock = serve({ 'GET api/codex/threads': { threads }, 'GET api/questions': { version: 1, questions }, ...routes });
  render(<App />);
  return fetchMock;
}

describe('the Codex page', () => {
  it('says Codex did not start, with the fix, and draws no board that could look idle', async () => {
    const fetchMock = open({ 'GET api/codex': { ...STATUS, up: false, version: null, signedIn: false, type: null, plan: null, rateLimits: null, code: 'codex-not-started' } });
    const banner = await screen.findByRole('alert');
    expect(banner.textContent).toMatch(/^Codex did not start\./);
    // The server takes CODEX_CMD only as a JSON array of strings (server/server.mjs).
    expect(banner.textContent).toMatch(/CODEX_CMD to a JSON array/);
    expect(banner.textContent).toContain('["C:\\\\…\\\\codex.exe"]');
    expect(screen.queryAllByRole('region')).toHaveLength(0);
    expect(calls(fetchMock, 'GET api/codex/threads')).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: 'Switch language' }));
    expect(screen.getByRole('alert').textContent).toMatch(/CODEX_CMD 設為.*JSON 陣列，例如 \["C:\\\\…\\\\codex\.exe"\]/);
  });

  it('asks again when Codex comes up, but not on each "still down" its own asking brings', async () => {
    // As the server does: each GET api/codex tries Codex once more, and a failed try says up:false on the stream.
    const down = { ...STATUS, up: false, version: null, signedIn: false, type: null, plan: null, rateLimits: null, code: 'codex-not-started' };
    const fetchMock = open({ 'GET api/codex': () => { setTimeout(() => FakeEventSource.current?.emit('bridge/appServer', { up: false })); return down; } });
    await screen.findByRole('alert');
    await act(() => new Promise((done) => setTimeout(done, 50)));
    expect(calls(fetchMock, 'GET api/codex')).toHaveLength(1);
    act(() => FakeEventSource.current.emit('bridge/appServer', { up: true }));
    await waitFor(() => expect(calls(fetchMock, 'GET api/codex')).toHaveLength(2));
  });

  it('says Codex is signed out, and Sign in opens only an https:// address, in a new tab without a way back', async () => {
    const authUrl = 'https://auth.openai.com/oauth/authorize?fake=1';
    const fetchMock = open({ 'GET api/codex': { ...STATUS, signedIn: false, plan: null, type: null, rateLimits: null, code: 'codex-signed-out' },
      'POST api/codex/login': { authUrl } });
    const opened = vi.spyOn(window, 'open').mockReturnValue(null);
    expect((await screen.findByRole('alert')).textContent).toMatch(/not signed in/);
    expect(screen.queryByText(/^Sign-in:/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText(/sign-in opened in a new tab/)).toBeTruthy();
    expect(calls(fetchMock, 'POST api/codex/login')).toEqual([{}]);
    expect(opened).toHaveBeenCalledWith(authUrl, '_blank', 'noopener,noreferrer');
    opened.mockRestore();
  });

  it('never opens a sign-in address that is not https://, and words the server\'s refusal by its code', async () => {
    let answer: unknown = { authUrl: 'http://127.0.0.1:1455/steal' };
    open({ 'GET api/codex': { ...STATUS, signedIn: false, code: 'codex-signed-out' }, 'POST api/codex/login': () => answer });
    const opened = vi.spyOn(window, 'open').mockReturnValue(null);
    fireEvent.click(await screen.findByRole('button', { name: 'Sign in' }));
    const refused = /sign-in address that is not https:\/\/, so it was not opened/;
    expect(await screen.findByText(refused)).toBeTruthy();
    answer = new Fail(502, 'bad-sign-in');
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(screen.queryByText(refused)).toBeNull();
    expect(await screen.findByText(refused)).toBeTruthy();
    expect(opened).not.toHaveBeenCalled();
    expect(screen.queryByText(/secret/)).toBeNull();
    opened.mockRestore();
  });

  it('shows the sign-in plan, the Codex version and a quota meter per window with its reset time', async () => {
    open();
    expect(await screen.findByText('Sign-in: plus')).toBeTruthy();
    expect(screen.getByText('Codex 0.162.0')).toBeTruthy();
    const meters = screen.getAllByRole('meter');
    expect(meters.map((m) => [m.getAttribute('aria-label'), (m as HTMLMeterElement).value])).toEqual([['7-day quota', 40], ['5-hour quota', 12]]);
    expect(meters[0].parentElement?.textContent).toBe(`7-day quota40% used · resets ${fmtTime(1900000000 * 1000, 'en')}`);
  });

  it('puts each thread in its state\'s column, an error thread in Idle with its chip, and Aster\'s question in Waiting for you', async () => {
    open();
    const column = async (name: string) => within(await screen.findByRole('region', { name }));
    expect((await column('Running')).getByText('Running here')).toBeTruthy();
    expect((await column('Working elsewhere')).getByText('In the app')).toBeTruthy();
    const idle = await column('Idle');
    expect(idle.getByText('Tidy the router')).toBeTruthy();
    expect(within(idle.getByText('Broke once').closest('button')!).getByText('error')).toBeTruthy();
    const waiting = await column('Waiting for you');
    expect(waiting.queryByText('May asks')).toBeNull();
    fireEvent.click(waiting.getByText('Which sandbox?'));
    expect(location.hash).toBe('#/codex?peek=q%3Aq-2026-10-10-library-001');
    expect(within(await screen.findByRole('dialog')).getByLabelText('Your answer')).toBeTruthy();
  });

  it('shows the first 8 idle threads, then the rest on Show N more', async () => {
    open({ 'GET api/codex/threads': { threads: Array.from({ length: 11 }, (_, i) => thread(`th-${i}`, { name: `Idle ${i}` })) } });
    const idle = within(await screen.findByRole('region', { name: 'Idle' }));
    await idle.findByText('Idle 0');
    expect(idle.getAllByRole('button', { name: /^Idle \d/ })).toHaveLength(8);
    fireEvent.click(idle.getByRole('button', { name: 'Show 3 more' }));
    expect(idle.getAllByRole('button', { name: /^Idle \d/ })).toHaveLength(11);
  });

  it('narrows the board by Source and by Folder', async () => {
    open();
    const idle = within(await screen.findByRole('region', { name: 'Idle' }));
    await idle.findByText('Broke once');
    fireEvent.change(screen.getByRole('combobox', { name: 'Source' }), { target: { value: 'exec' } });
    expect(idle.queryByText('Tidy the router')).toBeNull();
    expect(idle.getByText('Broke once')).toBeTruthy();
    fireEvent.change(screen.getByRole('combobox', { name: 'Source' }), { target: { value: '' } });
    fireEvent.change(screen.getByRole('combobox', { name: 'Folder' }), { target: { value: 'dev' } });
    expect(idle.getByText('Tidy the router')).toBeTruthy();
    expect(idle.queryByText('Broke once')).toBeNull();
    expect(within(screen.getByRole('region', { name: 'Working elsewhere' })).queryByText('In the app')).toBeNull();
  });

  it('lists the same threads in a table, and a row opens the thread\'s panel', async () => {
    open({ 'GET api/codex/threads/th-idle': { ...thread('th-idle', { name: 'Tidy the router' }), turns: [] } });
    fireEvent.click(await screen.findByRole('tab', { name: 'List' }));
    expect(location.hash).toBe('#/codex?view=list');
    const table = await screen.findByRole('table');
    const row = within(table).getByText('Tidy the router').closest('tr')!;
    expect(within(row).getAllByRole('cell').map((c) => c.textContent).slice(1, 4)).toEqual(['idle', 'Terminal', 'dev']);
    fireEvent.click(within(row).getByRole('button', { name: 'Tidy the router' }));
    expect(location.hash).toBe('#/codex?peek=t%3Ath-idle&view=list');
  });

  it('keeps the owner on the page they went to when a new thread\'s run answers late', async () => {
    let reply = (_: unknown) => {};
    open({ 'POST api/codex/run': () => new Promise((done) => { reply = done; }) });
    fireEvent.click(await screen.findByRole('button', { name: 'Create a thread' }));
    fireEvent.change(await screen.findByLabelText('Prompt for a new thread'), { target: { value: 'Read the router' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run' }));
    fireEvent.click(within(screen.getByRole('navigation', { name: 'Pages and agents' })).getByRole('link', { name: 'Agents' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Agents' })).toBeTruthy();
    expect(location.hash).toBe('#/');
    await act(async () => reply({ thread: 'th-new', turn: 'turn-1' }));
    await act(() => new Promise((done) => setTimeout(done, 20)));
    expect(location.hash).toBe('#/');
  });

  it('names the columns in Cantonese', async () => {
    open();
    fireEvent.click(await screen.findByRole('button', { name: 'Switch language' }));
    for (const name of ['執行中', '等你回覆', '在其他視窗工作', '閒置']) expect(await screen.findByRole('region', { name })).toBeTruthy();
  });
});
