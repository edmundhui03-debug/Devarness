import { TABLES } from './i18n';

export function fmtTime(value: string | number, lang: string): string {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString(lang, { dateStyle: 'medium', timeStyle: 'short' });
}

// Codex counts its times in seconds since 1970.
export const fmtSeconds = (seconds: number | null, lang: string) => (seconds ? fmtTime(seconds * 1000, lang) : '—');

// A dialog's name: the key and the start of the text, by characters, not UTF-16 halves.
export const named = (key: string, text: string) => `${key} ${Array.from(text).slice(0, 60).join('')}`;

// A word the tables know under `group.` reads in the chosen language; anything new shows as given.
export const knownWord = (group: string, raw: string, t: (key: string) => string) => (Object.hasOwn(TABLES.en, `${group}.${raw}`) ? t(`${group}.${raw}`) : raw);
// A known source (vscode, cli, exec...) reads as a word; a project, a client or anything new shows as given.
export const sourceWord = (raw: string, t: (key: string) => string) => knownWord('source', raw, t);
