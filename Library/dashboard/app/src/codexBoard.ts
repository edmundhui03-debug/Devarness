import type { Question, Thread } from './api';
import { askerOf, lastFolder, questionKey, sessionKey } from './board';
import { knownWord } from './format';
import type { useI18n } from './i18n';

// The Codex board: Codex's threads by state, and Aster's open questions, in
// four columns. Pure, so the page only renders it.
export type CodexFilter = { text: string; source: string; folder: string }; // '' matches any
export type CodexColumns = { running: Thread[]; waiting: Question[]; elsewhere: Thread[]; idle: Thread[] };

export const threadTitle = (t: Thread) => t.name || t.preview || t.id;
export const threadKey = (id: string) => sessionKey('Aster', id);
export const folderOf = (t: Thread) => lastFolder(t.cwd ?? '');

// Search matches a thread's title, preview, id or key, and a question's text,
// id or key. A question has no source or folder, so either filter hides it.
export function codexColumns(threads: Thread[], questions: Question[], { text, source, folder }: CodexFilter): CodexColumns {
  const needle = text.trim().toLowerCase();
  const has = (...fields: (string | null)[]) => fields.some((s) => (s ?? '').toLowerCase().includes(needle));
  const shown = threads.filter((t) => (!source || t.source === source) && (!folder || folderOf(t) === folder)
    && has(t.name, t.preview, t.id, threadKey(t.id)));
  const waiting = source || folder ? [] : questions.filter((q) => q.status === 'open' && askerOf(q) === 'Aster'
    && has(q.question, q.id, questionKey(q.id)));
  return {
    running: shown.filter((t) => t.state === 'running'),
    waiting,
    elsewhere: shown.filter((t) => t.state === 'active-elsewhere'),
    // An error thread sits in Idle with its chip; a state this page does not know too.
    idle: shown.filter((t) => t.state !== 'running' && t.state !== 'active-elsewhere'),
  };
}

// --- a thread's turns, as lines ---------------------------------------------------

export type Line = { kind: string; text: string };
type Translate = ReturnType<typeof useI18n>['t'];

const get = (v: unknown, key: string): unknown => (v !== null && typeof v === 'object' ? (v as Record<string, unknown>)[key] : undefined);
const str = (v: unknown) => String(v ?? '');
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
// A long output keeps its end, as a terminal shows it last; the server cuts it
// from its start too (contract A3), so the one cut mark is at the start.
const tail = (text: string, size: number) => (text.length <= size ? text : '…' + text.slice(-size));

// One line per item, kinds as the prototype's itemLine names them
// (Library/dashboard/index.html:802); null for a reasoning item with no summary.
function itemLine(it: unknown, t: Translate): Line | null {
  switch (get(it, 'type')) {
    case 'userMessage': return { kind: 'prompt', text: list(get(it, 'content')).map((c) => str(get(c, 'text'))).join('\n') };
    case 'agentMessage': return { kind: 'reply', text: str(get(it, 'text')) };
    case 'reasoning': {
      const text = list(get(it, 'summary')).map(str).join('\n').trim();
      return text ? { kind: 'reasoning', text } : null;
    }
    case 'plan': return { kind: 'plan', text: str(get(it, 'text')) };
    case 'commandExecution': {
      const out = tail(str(get(it, 'aggregatedOutput')).trimEnd(), 1500);
      return { kind: 'command', text: t('thread.command', { cmd: str(get(it, 'command')), code: str(get(it, 'exitCode') ?? '?') }) + (out ? '\n' + out : '') };
    }
    case 'fileChange': return {
      kind: 'file',
      text: list(get(it, 'changes')).map((c) => {
        const kind = get(c, 'kind'); // { type: 'update' }, or the word itself
        return `${knownWord('change', str(typeof kind === 'object' ? get(kind, 'type') : kind), t)} ${str(get(c, 'path'))}`;
      }).join('\n'),
    };
    case 'mcpToolCall': return { kind: 'tool', text: `${str(get(it, 'server'))}.${str(get(it, 'tool'))} ${knownWord('tool', str(get(it, 'status')), t)}`.trim() };
    case 'webSearch': return { kind: 'search', text: str(get(it, 'query')) };
  }
  return { kind: 'other', text: str(get(it, 'type')) || '?' };
}

// Every item of the given turns, oldest first; text only, never markup.
export const threadLines = (turns: unknown[], t: Translate): Line[] =>
  turns.flatMap((turn) => list(get(turn, 'items'))).flatMap((it) => itemLine(it, t) ?? []);
