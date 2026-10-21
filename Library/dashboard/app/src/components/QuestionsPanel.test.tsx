import { describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import { QuestionsPanel } from './QuestionsPanel';

const q = (id: string, extra = {}) => ({ id, project: 'Library', task: 'Wave 1', asked_by: 'May',
  asked_at: '2026-10-09T10:00:00+08:00', question: 'Use <b>47900</b>?', status: 'open', answer: '',
  answered_at: '', used_by: '', used_at: '', used_note: '', ...extra });

describe('the questions panel', () => {
  it('shows only this agent\'s questions, as plain text', () => {
    render(<QuestionsPanel agent="May" questions={[q('q-1'), q('q-2', { asked_by: 'Aster', question: 'Not mine' })]} fileError={null} onSaved={() => {}} />);
    expect(screen.getByText('Use <b>47900</b>?')).toBeTruthy();
    expect(screen.queryByText('Not mine')).toBeNull();
  });

  it('saves an answer as typed and says the agent carries on', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ question: q('q-1', { status: 'answered' }) }) }));
    vi.stubGlobal('fetch', fetchMock);
    const onSaved = vi.fn();
    render(<QuestionsPanel agent="May" questions={[q('q-1')]} fileError={null} onSaved={onSaved} />);
    const save = screen.getByRole('button', { name: 'Save answer' }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Your answer'), { target: { value: 'Yes,\nuse it' } });
    fireEvent.click(save);
    expect(await screen.findByText('Saved. May picks it up and carries on.')).toBeTruthy();
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('api/questions/q-1/answer');
    expect(JSON.parse(String(init.body))).toEqual({ answer: 'Yes,\nuse it' });
    // The question the server returns, so the page shows it answered at once.
    expect(onSaved).toHaveBeenCalledWith(q('q-1', { status: 'answered' }));
  });

  it('says a busy mailbox (503) in the page\'s own words, in either language, and keeps the text', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, json: async () => ({ error: 'the mailbox is busy, try again' }) })));
    for (const [lang, box, save, busy] of [['en', 'Your answer', 'Save answer', 'The mailbox is busy; try again in a moment.'],
      ['zh-HK', '你的回覆', '儲存回覆', '信箱正忙，請稍後再試。']]) {
      localStorage.setItem('dash.lang', lang);
      render(<I18nProvider><QuestionsPanel agent="May" questions={[q('q-1')]} fileError={null} onSaved={() => {}} /></I18nProvider>);
      fireEvent.change(screen.getByLabelText(box), { target: { value: 'Later' } });
      fireEvent.click(screen.getByRole('button', { name: save }));
      expect(await screen.findByText(busy)).toBeTruthy();
      expect(screen.queryByText(/the mailbox is busy, try again/)).toBeNull();
      expect((screen.getByLabelText(box) as HTMLTextAreaElement).value).toBe('Later');
      cleanup();
    }
  });

  it('shows a refused save as an error and keeps the text', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 409, json: async () => ({ error: 'this question is already used' }) })));
    render(<QuestionsPanel agent="May" questions={[q('q-1')]} fileError={null} onSaved={() => {}} />);
    fireEvent.change(screen.getByLabelText('Your answer'), { target: { value: 'Late' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save answer' }));
    expect(await screen.findByText('Not saved: this question is already used')).toBeTruthy();
    expect((screen.getByLabelText('Your answer') as HTMLTextAreaElement).value).toBe('Late');
  });
});
