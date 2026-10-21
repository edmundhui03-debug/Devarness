import type { ClaudeSession, Question } from './api';
import { askerOf, lastFolder, questionKey, sessionKey } from './board';

// The Claude board: Claude Code's sessions by state, and Peter's open
// questions, in four columns. Pure, so the page only renders it.
export type ClaudeFilter = { text: string; source: string; folder: string }; // '' matches any
export type ClaudeColumns = { waiting: Question[]; working: ClaudeSession[]; idle: ClaudeSession[]; ended: ClaudeSession[] };

export const sessionTitle = (s: ClaudeSession) => s.title || s.id;
export const claudeKey = (id: string) => sessionKey('Peter', id);
export const folderOf = (s: { cwd: string }) => lastFolder(s.cwd);

// Search matches a session's title, id or key, and a question's text, id or
// key. A question has no source or folder, so either filter hides it. Each
// column keeps the server's order: newest first.
export function claudeColumns(sessions: ClaudeSession[], questions: Question[], { text, source, folder }: ClaudeFilter): ClaudeColumns {
  const needle = text.trim().toLowerCase();
  const has = (...fields: string[]) => fields.some((s) => s.toLowerCase().includes(needle));
  const shown = sessions.filter((s) => (!source || s.source === source) && (!folder || folderOf(s) === folder)
    && has(s.title, s.id, claudeKey(s.id)));
  const waiting = source || folder ? [] : questions.filter((q) => q.status === 'open' && askerOf(q) === 'Peter'
    && has(q.question, q.id, questionKey(q.id)));
  return {
    waiting,
    working: shown.filter((s) => s.state === 'working'),
    // A state this page does not know sits in Idle, as the server reads any live status but busy.
    idle: shown.filter((s) => s.state !== 'working' && s.state !== 'ended'),
    ended: shown.filter((s) => s.state === 'ended'),
  };
}
