import { useEffect, useState } from 'react';
import { Bell, Menu, Monitor, Moon, Sun } from 'lucide-react';
import { useI18n } from '../i18n';
import type { Page } from '../router';

type Theme = 'system' | 'light' | 'dark';
const THEMES: Theme[] = ['system', 'light', 'dark'];
const ICONS = { system: Monitor, light: Sun, dark: Moon };

// The theme is a per-viewer convenience: storage may be missing or refuse.
function savedTheme(): Theme {
  try {
    const v = localStorage.getItem('dash.theme');
    return v === 'light' || v === 'dark' ? v : 'system';
  } catch { return 'system'; }
}

type Props = { page: Page; openCount: number; onBell: () => void; menuOpen: boolean; onMenu: () => void };

// The global bar: menu (narrow screens), pages, the questions bell, language and theme.
export function TopBar({ page, openCount, onBell, menuOpen, onMenu }: Props) {
  const { t, lang, setLang } = useI18n();
  const [theme, setTheme] = useState(savedTheme);
  useEffect(() => {
    if (theme === 'system') delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('dash.theme', theme); } catch { /* kept for this visit only */ }
  }, [theme]);
  const ThemeIcon = ICONS[theme];
  const themeLabel = t('theme.label', { mode: t(`theme.${theme}`) });
  const bellLabel = t('agent.questions', { n: openCount });
  // The Claude and Codex pages are Peter's and Aster's, under Agents, so the link
  // stays filled there; it is the current page only on the Agents board itself.
  const agents = page === 'agents' || page === 'claude' || page === 'codex';
  return (
    <header className="top">
      <a className="skip" href="#content" onClick={(e) => { e.preventDefault(); document.getElementById('content')?.focus(); }}>{t('skip')}</a>
      <button type="button" className="iconbtn menubtn" aria-label={t('nav.menu')} aria-expanded={menuOpen} aria-controls="sidebar" onClick={onMenu}><Menu /></button>
      <div className="logo"><i aria-hidden="true">d</i>{t('app.name')}</div>
      <nav className="topnav" aria-label={t('top.nav')}>
        <a className={agents ? 'on' : undefined} href="#/" aria-current={page === 'agents' ? 'page' : undefined}>{t('nav.agents')}</a>
      </nav>
      <span className="grow" />
      <button type="button" className="iconbtn" aria-label={bellLabel} title={bellLabel} disabled={!openCount} onClick={onBell}>
        <Bell />{openCount > 0 && <span className="badge" aria-hidden="true">{openCount}</span>}
      </button>
      <button type="button" className="btn" lang={lang === 'en' ? 'zh-HK' : 'en'} aria-label={t('lang.aria')} onClick={() => setLang(lang === 'en' ? 'zh-HK' : 'en')}>{t('lang.switch')}</button>
      <button type="button" className="iconbtn" aria-label={themeLabel} title={themeLabel} onClick={() => setTheme(THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length])}><ThemeIcon /></button>
    </header>
  );
}
