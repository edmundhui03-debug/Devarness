import { describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { App } from '../App';
import theme from '../theme.css?raw';
import { Fail, question, serve } from '../test-fakes';

const TASKS = {
  code: 'ok', at: '2026-10-14T02:00:00Z',
  sections: [
    { status: 'needs-owner', file: 'Setup/a.md', line: 7, heading: 'The owner picks a colour' },
    { status: 'blocked', file: 'Library/b.md', line: 3, heading: 'Blocked on a licence' },
    { status: 'partial', file: 'Projects/demo/docs/c.md', line: 9, heading: 'Half the icons are done' },
    { status: 'open', file: 'README.md', line: 20, heading: 'A root task' },
    { status: 'fixed', file: 'Setup/a.md', line: 30, heading: 'Already settled' },
  ],
  titles: { 'Setup/a.md': 'A', 'Library/b.md': 'B', 'Projects/demo/docs/c.md': 'C', 'README.md': 'dev' },
  runs: [{ launched: '2026-10-14 09:00', at: '2026-10-14T01:00:00.000Z', session: '`abcd`', task: 'Review the plan', agent: 'one Opus agent', budget: '0.5M', stale: true }],
};
function show(hash: string, routes = {}) {
  location.hash = hash;
  const fetchMock = serve({ 'GET api/tasks': TASKS, 'GET api/questions': { version: 1, questions: [question('q-1', { status: 'open', question: 'Which colour?' })] }, ...routes });
  render(<App />);
  return fetchMock;
}
const column = (name: string) => within(screen.getByRole('region', { name }));
// test-setup.ts cleans up and clears the address after each test.

describe('the tasks page', () => {
  it('shows what waits, what is in progress and what is to do, and leaves fixed sections off', async () => {
    show('#/tasks');
    await screen.findByText('The owner picks a colour');
    expect(column('Waiting for you').getAllByRole('button').map((b) => b.textContent)).toEqual([
      expect.stringContaining('Which colour?'), expect.stringContaining('The owner picks a colour'), expect.stringContaining('Blocked on a licence')]);
    expect(column('In progress').getByText('Review the plan')).toBeTruthy();
    expect(column('In progress').getByText('stale?')).toBeTruthy();
    expect(column('To do').getByText('A root task')).toBeTruthy();
    expect(screen.queryByText('Already settled')).toBeNull();
  });
  it('says when Python is missing, and still shows questions and runs', async () => {
    show('#/tasks', { 'GET api/tasks': { ...TASKS, code: 'tasks-no-python', sections: [], titles: {} } });
    expect(await screen.findByText(/dashboard serve/)).toBeTruthy();
    expect(screen.getByText('Which colour?')).toBeTruthy();
    expect(screen.getByText('Review the plan')).toBeTruthy();
  });
  it('says when md-format fails, and still shows questions and runs', async () => {
    show('#/tasks', { 'GET api/tasks': { ...TASKS, code: 'tasks-index-failed', sections: [], titles: {} } });
    expect((await screen.findByRole('alert')).textContent).toMatch(/md-format could not read the documents/);
    expect(screen.getByText('Which colour?')).toBeTruthy();
    expect(screen.getByText('Review the plan')).toBeTruthy();
  });
  it('says when the tasks reading fails, and still shows questions', async () => {
    show('#/tasks', { 'GET api/tasks': new Fail(500, 'internal') });
    expect((await screen.findByRole('alert')).textContent).toMatch(/unexpected error/);
    expect(screen.getByText('Which colour?')).toBeTruthy();
  });
  it.each([
    ['questions.json cannot be read', { version: 1, questions: [], error: 'questions.json is not valid JSON' }, /^Questions cannot be shown: questions.json is not valid JSON$/],
    ['the questions reading fails', new Fail(500, 'internal'), /^The dashboard server did not answer:/],
  ])('says when %s, never an empty Waiting column alone', async (_, answer, said) => {
    show('#/tasks', { 'GET api/questions': answer });
    expect((await screen.findByRole('alert')).textContent).toMatch(said);
    expect(column('Waiting for you').getByText('The owner picks a colour')).toBeTruthy();
  });
  it('lists the groups in order and keeps a folded group folded after a reload', async () => {
    show('#/tasks?view=list');
    const names = async () => (await screen.findAllByRole('button', { expanded: true })).map((b) => b.textContent);
    expect(await names()).toEqual([
      expect.stringContaining('Questions'), expect.stringContaining('Agent runs'), expect.stringContaining('Library'),
      expect.stringContaining('Projects/demo'), expect.stringContaining('Setup'), expect.stringContaining('dev root')]);
    // A group's name heads its own rows, never the columns.
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['Title', 'State', 'Where', 'When']);
    expect(screen.getAllByRole('rowheader').map((h) => h.textContent)).toEqual([
      expect.stringContaining('Questions'), expect.stringContaining('Agent runs'), expect.stringContaining('Library'),
      expect.stringContaining('Projects/demo'), expect.stringContaining('Setup'), expect.stringContaining('dev root')]);
    fireEvent.click(screen.getByRole('button', { name: /Setup/ }));
    await waitFor(() => expect(location.hash).toContain('fold=d%3ASetup'));
    cleanup();
    show(location.hash);
    expect(await screen.findByRole('button', { name: /Setup/, expanded: false })).toBeTruthy();
    expect(screen.queryByText('The owner picks a colour')).toBeNull();
  });
  it('opens a question in the side panel from its card', async () => {
    show('#/tasks');
    fireEvent.click(await screen.findByText('Which colour?'));
    await waitFor(() => expect(location.hash).toContain('peek=q%3Aq-1'));
    const panel = await screen.findByRole('dialog', { name: /Which colour\?/ });
    expect(within(panel).getByLabelText('Your answer')).toBeTruthy();
  });
  it('lets a long budget wrap inside its run card, so the page never scrolls sideways', async () => {
    const budget = 'estimate30Ktokens,20minincludingprep,35manualinputs;deadline17:59:08UTC';
    show('#/tasks', { 'GET api/tasks': { ...TASKS, runs: [{ ...TASKS.runs[0], budget }] } });
    const meta = (await screen.findByText(budget)).parentElement!;
    // jsdom draws nothing, so the rule is read: the meta row may break any word.
    const rule = theme.match(new RegExp(`^\\.${meta.className}\\s*\\{[^}]*\\}`, 'm'))?.[0];
    expect(rule).toMatch(/overflow-wrap:\s*anywhere/);
  });
  it('opens a document from its card and reopens it from the address', async () => {
    show('#/tasks', { 'GET api/tasks/commits?file=Setup%2Fa.md': { commits: [] } });
    fireEvent.click(await screen.findByText('The owner picks a colour'));
    await waitFor(() => expect(location.hash).toContain('peek=d%3ASetup%2Fa.md'));
    expect(await screen.findByText('Already settled')).toBeTruthy(); // the panel lists the fixed section too
    cleanup();
    show(location.hash, { 'GET api/tasks/commits?file=Setup%2Fa.md': { commits: [] } });
    expect(await screen.findByText('Already settled')).toBeTruthy();
  });
  it('says a document is not on the board once it leaves the index after its panel opens', async () => {
    let index: object = TASKS;
    show('#/tasks?peek=d%3ASetup%2Fa.md', { 'GET api/tasks': () => index, 'GET api/tasks/commits?file=Setup%2Fa.md': { commits: [] } });
    expect(await screen.findByText('No commit has touched this document yet.')).toBeTruthy();
    index = { ...TASKS, sections: TASKS.sections.filter((s) => s.file !== 'Setup/a.md'), titles: { 'Library/b.md': 'B' } };
    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    expect(await screen.findByRole('dialog', { name: 'This item is not on the board now.' })).toBeTruthy();
  });
  it.each(['d%3A..%2F..%2Fx', 'd%3A-p'])('never asks git about a path the index does not list (%s)', async (peek) => {
    const fetchMock = show(`#/tasks?peek=${peek}`);
    expect(await screen.findByRole('dialog', { name: 'This item is not on the board now.' })).toBeTruthy();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).startsWith('api/tasks/commits'))).toHaveLength(0);
  });
});
