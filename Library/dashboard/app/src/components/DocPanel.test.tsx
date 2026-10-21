import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import { Fail, calls, serve } from '../test-fakes';
import { DocPanel } from './DocPanel';

const SECTIONS = [
  { status: 'fixed' as const, file: 'Projects/demo/docs/c.md', line: 30, heading: 'Settled' },
  { status: 'partial' as const, file: 'Projects/demo/docs/c.md', line: 9, heading: 'Half done' },
  { status: 'open' as const, file: 'Setup/other.md', line: 1, heading: 'Elsewhere' },
];
const COMMITS = 'GET api/tasks/commits?file=Projects%2Fdemo%2Fdocs%2Fc.md';
const show = (answer: unknown) => {
  const fetchMock = serve({ [COMMITS]: answer });
  render(<I18nProvider><DocPanel file="Projects/demo/docs/c.md" sections={SECTIONS} /></I18nProvider>);
  return fetchMock;
};

describe('the document panel', () => {
  it('lists the document\'s own sections by line, then its last commits', async () => {
    const fetchMock = show({ commits: [{ hash: 'abc1234', at: '2026-10-14T02:00:00+08:00', subject: 'Draw the icons' }] });
    expect(await screen.findByText(/Draw the icons/)).toBeTruthy();
    expect(screen.getAllByRole('listitem').slice(0, 2).map((li) => li.textContent)).toEqual([
      expect.stringContaining('Half done'), expect.stringContaining('Settled')]);
    expect(screen.queryByText('Elsewhere')).toBeNull();
    expect(calls(fetchMock, COMMITS)).toHaveLength(1);
  });
  it('says when no commit has touched it', async () => {
    show({ commits: [] });
    expect(await screen.findByText('No commit has touched this document yet.')).toBeTruthy();
  });
  it('words a refusal by its code, never by the server\'s text', async () => {
    show(new Fail(404, 'unknown-file'));
    expect(await screen.findByText('That document is not in the index.')).toBeTruthy();
    expect(screen.queryByText(/secret/)).toBeNull();
  });
});
