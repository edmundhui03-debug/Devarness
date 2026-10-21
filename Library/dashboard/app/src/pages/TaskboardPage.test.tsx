import { describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nProvider, useI18n } from '../i18n';
import theme from '../theme.css?raw';
import { calls, serve } from '../test-fakes';
import { TaskboardPage } from './TaskboardPage';

const url = 'http://127.0.0.1:47823';
const show = () => render(<I18nProvider><TaskboardPage /></I18nProvider>);

describe('the taskboard page', () => {
  it('frames the running board at least 70% of the window high, with Open in new tab', async () => {
    serve({ 'GET api/taskboard': { running: true, url } });
    show();
    const frame = await screen.findByTitle('Codex Taskboard');
    expect(frame.tagName).toBe('IFRAME');
    expect(frame.getAttribute('src')).toBe(`${url}/?lang=en`);
    // One rule sizes the frame; jsdom draws nothing, so the rule is read.
    const rule = theme.match(new RegExp(`\\.${frame.className}\\s*\\{[^}]*\\}`, 'g')) ?? [];
    expect(rule).toHaveLength(1);
    expect(rule[0]).toMatch(/min-height:\s*70vh/);
    const link = screen.getByRole('link', { name: 'Open in new tab' });
    expect([link.getAttribute('href'), link.getAttribute('target'), link.getAttribute('rel')]).toEqual([`${url}/?lang=en`, '_blank', 'noopener noreferrer']);
  });

  it('shows the board in the dashboard\'s language: 中文 asks for its Chinese, English for its English', async () => {
    localStorage.setItem('dash.lang', 'zh-HK');
    serve({ 'GET api/taskboard': { running: true, url } });
    const ToEnglish = () => {
      const { setLang } = useI18n();
      return <button type="button" onClick={() => setLang('en')}>to English</button>;
    };
    render(<I18nProvider><TaskboardPage /><ToEnglish /></I18nProvider>);
    const frame = await screen.findByTitle(/Taskboard|工作看板/);
    expect(frame.getAttribute('src')).toBe(`${url}/?lang=zh`);
    fireEvent.click(screen.getByRole('button', { name: 'to English' }));
    await waitFor(() => expect(frame.getAttribute('src')).toBe(`${url}/?lang=en`));
  });

  it('says in either language that the board is not running, how to start it, and checks again', async () => {
    for (const [lang, down, again] of [['en', 'The taskboard is not running.', 'Check again'], ['zh-HK', '工作看板未有運行。', '再檢查一次']]) {
      localStorage.setItem('dash.lang', lang);
      const fetchMock = serve();
      show();
      expect(await screen.findByText(down)).toBeTruthy();
      expect(screen.getByText('taskboard start').tagName).toBe('CODE');
      expect(screen.queryByTitle(/Taskboard/)).toBeNull();
      fireEvent.click(screen.getByRole('button', { name: again }));
      await waitFor(() => expect(calls(fetchMock, 'GET api/taskboard')).toHaveLength(2));
      cleanup();
    }
  });

  it('frames the board once a check finds it running', async () => {
    let running = false;
    serve({ 'GET api/taskboard': () => ({ running, url }) });
    show();
    await screen.findByText('The taskboard is not running.');
    running = true;
    fireEvent.click(screen.getByRole('button', { name: 'Check again' }));
    expect((await screen.findByTitle('Codex Taskboard')).getAttribute('src')).toBe(`${url}/?lang=en`);
    expect(screen.queryByText('The taskboard is not running.')).toBeNull();
  });
});
