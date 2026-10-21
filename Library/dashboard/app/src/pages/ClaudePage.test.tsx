import { describe, expect, it } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { App } from '../App';
import { fmtTime } from '../format';
import { CLAUDE_ID, CLAUDE_VIEW, Fail, agentRow, calls, claudeSession, question, serve } from '../test-fakes';
import theme from '../theme.css?raw';

const id = (n: string) => `0b1c2d3e-0000-4000-8000-00000000${n}`;
const sessions = [
  claudeSession(id('a001'), { state: 'working', title: 'Build wave 4' }),
  claudeSession(id('a002'), { state: 'idle', title: 'Tidy the router', source: 'cli', cwd: 'D:\\work\\pcb', updatedAt: '2026-10-15T01:00:00Z' }),
  claudeSession(id('a003'), { state: 'ended', title: 'Read the spec', updatedAt: '2026-10-14T20:00:00Z' }),
];
const questions = [question('q-2026-10-15-library-001', { asked_by: 'Peter', question: 'Which port?' }),
  question('q-2026-10-15-library-002', { asked_by: 'May', question: 'May asks' })];

function open(routes = {}) {
  location.hash = '#/claude';
  const fetchMock = serve({ 'GET api/claude': { sessions, at: '2026-10-15T02:00:00Z' }, 'GET api/questions': { version: 1, questions }, ...routes });
  render(<App />);
  return fetchMock;
}
const column = async (name: string) => within(await screen.findByRole('region', { name }));
const count = (region: HTMLElement) => region.querySelector('.colhead .n')?.textContent;

describe('the Claude page', () => {
  it('reads "Peter · Claude Code" under Agents, with Refresh, which reads the sessions again', async () => {
    const fetchMock = open();
    expect(await screen.findByRole('heading', { level: 1, name: 'Peter · Claude Code' })).toBeTruthy();
    expect(screen.getByText('dev workspace / Agents / Peter')).toBeTruthy();
    await (await column('Working')).findByText('Build wave 4');
    const before = calls(fetchMock, 'GET api/claude').length;
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(calls(fetchMock, 'GET api/claude').length).toBe(before + 1));
  });

  it('shows the four columns with their counts: Peter\'s open question waiting, then working, idle and ended sessions', async () => {
    open();
    const waiting = await column('Waiting for you');
    expect(await waiting.findByText('Which port?')).toBeTruthy();
    expect(waiting.queryByText('May asks')).toBeNull();
    expect((await column('Working')).getByText('Build wave 4')).toBeTruthy();
    expect((await column('Idle')).getByText('Tidy the router')).toBeTruthy();
    expect((await column('Ended')).getByText('Read the spec')).toBeTruthy();
    const regions = screen.getAllByRole('region');
    expect(regions.map((r) => r.getAttribute('aria-label'))).toEqual(['Waiting for you', 'Working', 'Idle', 'Ended']);
    expect(regions.map(count)).toEqual(['1', '1', '1', '1']);
  });

  it('shows a session card\'s title, key, source word and folder, and opens it as c:<id>', async () => {
    open();
    const card = (await (await column('Working')).findByText('Build wave 4')).closest('button')!;
    expect(within(card).getByText('PET-A001')).toBeTruthy();
    expect(within(card).getByText('Desktop')).toBeTruthy();
    expect(within(card).getByText('dev').getAttribute('title')).toBe('C:\\work\\dev');
    fireEvent.click(card);
    expect(location.hash).toBe(`#/claude?peek=c%3A${id('a001')}`);
  });

  it('opens a question card as q:<id>, ready to answer', async () => {
    open();
    fireEvent.click(await (await column('Waiting for you')).findByText('Which port?'));
    expect(location.hash).toBe('#/claude?peek=q%3Aq-2026-10-15-library-001');
    expect(within(await screen.findByRole('dialog')).getByLabelText('Your answer')).toBeTruthy();
  });

  it('offers only the sources and folders present, and narrows the board by each', async () => {
    open();
    const idle = await column('Idle');
    await idle.findByText('Tidy the router');
    const options = (name: string) => Array.from(screen.getByRole('combobox', { name }).querySelectorAll('option')).map((o) => o.textContent);
    expect(options('Source')).toEqual(['All sources', 'Desktop', 'Terminal']);
    expect(options('Folder')).toEqual(['All folders', 'dev', 'pcb']);
    fireEvent.change(screen.getByRole('combobox', { name: 'Source' }), { target: { value: 'cli' } });
    expect(idle.getByText('Tidy the router')).toBeTruthy();
    expect((await column('Working')).queryByText('Build wave 4')).toBeNull();
    expect((await column('Waiting for you')).queryByText('Which port?')).toBeNull();
    fireEvent.change(screen.getByRole('combobox', { name: 'Source' }), { target: { value: '' } });
    fireEvent.change(screen.getByRole('combobox', { name: 'Folder' }), { target: { value: 'dev' } });
    expect(idle.queryByText('Tidy the router')).toBeNull();
    expect((await column('Ended')).getByText('Read the spec')).toBeTruthy();
  });

  it('keeps offering a chosen source and folder after their sessions leave the listing, so the select reads what filters', async () => {
    let listing = sessions;
    open({ 'GET api/claude': () => ({ sessions: listing, at: '2026-10-15T02:00:00Z' }) });
    await (await column('Idle')).findByText('Tidy the router');
    const select = (name: string) => screen.getByRole('combobox', { name }) as HTMLSelectElement;
    fireEvent.change(select('Source'), { target: { value: 'cli' } });
    fireEvent.change(select('Folder'), { target: { value: 'pcb' } });
    listing = sessions.filter((s) => s.source !== 'cli'); // the pcb session ended over 24 h ago
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => expect(screen.queryByText('Tidy the router')).toBeNull());
    expect([select('Source').value, select('Folder').value]).toEqual(['cli', 'pcb']);
    expect(Array.from(select('Folder').options).map((o) => o.textContent)).toEqual(['All folders', 'dev', 'pcb']);
    fireEvent.change(select('Source'), { target: { value: '' } });
    fireEvent.change(select('Folder'), { target: { value: '' } });
    expect((await column('Working')).getByText('Build wave 4')).toBeTruthy();
    expect((await column('Waiting for you')).getByText('Which port?')).toBeTruthy();
  });

  it('finds a session by its key in the search box', async () => {
    open();
    await (await column('Working')).findByText('Build wave 4');
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'pet-a003' } });
    expect((await column('Ended')).getByText('Read the spec')).toBeTruthy();
    expect((await column('Working')).queryByText('Build wave 4')).toBeNull();
  });

  it('lists title, state chip, source, folder and updated time, the ended chip grey as to do, and a row opens its session', async () => {
    open();
    fireEvent.click(await screen.findByRole('tab', { name: 'List' }));
    expect(location.hash).toBe('#/claude?view=list');
    const table = await screen.findByRole('table');
    const row = (await within(table).findByText('Tidy the router')).closest('tr')!;
    expect(within(row).getAllByRole('cell').map((c) => c.textContent)).toEqual(
      ['Tidy the router', 'idle', 'Terminal', 'pcb', fmtTime('2026-10-15T01:00:00Z', 'en')]);
    const ended = within(table).getByText('Read the spec').closest('tr')!;
    expect(within(ended).getByText('ended').className).toBe('chip chip-ended');
    expect(theme).toMatch(/\.chip-todo,[^{]*\.chip-ended[^{]*\{ background: var\(--card\); color: var\(--muted\)/);
    fireEvent.click(within(row).getByRole('button', { name: 'Tidy the router' }));
    expect(location.hash).toBe(`#/claude?peek=c%3A${id('a002')}&view=list`);
  });

  it('words a failed reading by its code, never the server\'s text, and still draws the columns', async () => {
    open({ 'GET api/claude': new Fail(500, 'internal') });
    expect((await screen.findByRole('alert')).textContent).toBe('The dashboard server hit an unexpected error; try again.');
    expect(document.body.textContent).not.toContain('C:\\secret\\path'); // the server's own error text
    expect(screen.getAllByRole('region')).toHaveLength(4);
  });

  it('draws its four columns, each with its empty note, when there is no session and no question', async () => {
    open({ 'GET api/claude': { sessions: [], at: '2026-10-15T02:00:00Z' }, 'GET api/questions': { version: 1, questions: [] } });
    await waitFor(() => expect(screen.queryByText('Loading…')).toBeNull());
    const regions = screen.getAllByRole('region');
    expect(regions.map((r) => r.getAttribute('aria-label'))).toEqual(['Waiting for you', 'Working', 'Idle', 'Ended']);
    for (const region of regions) {
      expect(within(region).getByText('Nothing here')).toBeTruthy();
      expect(count(region)).toBe('0');
    }
  });

  it('opens a session\'s console from its address, a subagent from there, and the session again from the subagent', async () => {
    location.hash = `#/claude?peek=c%3A${CLAUDE_ID}`;
    serve({ 'GET api/claude': { sessions: [claudeSession(CLAUDE_ID, { title: 'Build wave 4' })], at: '2026-10-15T02:00:00Z' },
      [`GET api/claude/sessions/${CLAUDE_ID}`]: CLAUDE_VIEW,
      [`GET api/claude/sessions/${CLAUDE_ID}/agents/agent-a1`]: { ...agentRow('agent-a1', { title: 'Review the server track' }), readable: true, steps: [] } });
    render(<App />);
    const panel = within(await screen.findByRole('dialog', { name: 'PET-C001 Build wave 4' }));
    expect(await panel.findByText('Reading the plan first.')).toBeTruthy();
    fireEvent.click(panel.getByRole('button', { name: 'Review the server track' }));
    expect(location.hash).toBe(`#/claude?peek=a%3A${CLAUDE_ID}%3Aagent-a1`);
    const sub = within(await screen.findByRole('dialog', { name: 'PET-C001 agent-a1' }));
    expect(await sub.findByRole('heading', { name: 'Review the server track' })).toBeTruthy();
    fireEvent.click(sub.getByRole('button', { name: 'Back to session PET-C001' }));
    expect(location.hash).toBe(`#/claude?peek=c%3A${CLAUDE_ID}`);
  });

  it('asks the server once for a session the listing does not hold, and words its 404 as not found', async () => {
    const gone = id('dead');
    const fetchMock = open({ [`GET api/claude/sessions/${gone}`]: new Fail(404, 'not-found') });
    location.hash = `#/claude?peek=c%3A${gone}`;
    const panel = within(await screen.findByRole('dialog', { name: 'PET-DEAD' }));
    expect(await panel.findByText('There is no such thread, session or subagent now.')).toBeTruthy();
    expect(calls(fetchMock, `GET api/claude/sessions/${gone}`)).toHaveLength(1);
  });

  it('words a path in the address as not found, and asks the server nothing for it', async () => {
    const fetchMock = open();
    for (const peek of ['c:../../.credentials', `a:${CLAUDE_ID}:../x`, `a:${CLAUDE_ID}:agent-a1/../../x`]) {
      act(() => { location.hash = `#/claude?peek=${encodeURIComponent(peek)}`; });
      expect(await within(await screen.findByRole('dialog')).findByText('There is no such thread, session or subagent now.'), peek).toBeTruthy();
    }
    expect(fetchMock.mock.calls.map(([url]) => url).filter((url) => url.startsWith('api/claude/'))).toEqual([]);
  });

  it('names the columns in Cantonese', async () => {
    open();
    fireEvent.click(await screen.findByRole('button', { name: 'Switch language' }));
    for (const name of ['等你回覆', '工作中', '閒置', '已結束']) expect(await screen.findByRole('region', { name })).toBeTruthy();
  });
});
