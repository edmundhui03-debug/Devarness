import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import en from './en.json';
import zh from './zh-HK.json';

export type Lang = 'en' | 'zh-HK';
export const TABLES: Record<Lang, Record<string, string>> = { en, 'zh-HK': zh };
type Vars = Record<string, string | number>;

export function translate(lang: Lang, key: string, vars: Vars = {}): string {
  const text = TABLES[lang][key] ?? TABLES.en[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (whole, name) => (name in vars ? String(vars[name]) : whole));
}

// The choice is a per-viewer convenience: storage may be missing or refuse.
function savedLang(): Lang {
  try { return localStorage.getItem('dash.lang') === 'zh-HK' ? 'zh-HK' : 'en'; } catch { return 'en'; }
}

type I18n = { lang: Lang; setLang: (lang: Lang) => void; t: (key: string, vars?: Vars) => string };
const Context = createContext<I18n>({ lang: 'en', setLang: () => {}, t: (key, vars) => translate('en', key, vars) });

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setState] = useState<Lang>(savedLang);
  // <html lang> follows the language from the first render and after every switch.
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  const setLang = useCallback((next: Lang) => {
    setState(next);
    try { localStorage.setItem('dash.lang', next); } catch { /* kept for this visit only */ }
  }, []);
  const t = useCallback((key: string, vars?: Vars) => translate(lang, key, vars), [lang]);
  return <Context.Provider value={{ lang, setLang, t }}>{children}</Context.Provider>;
}

export const useI18n = () => useContext(Context);
