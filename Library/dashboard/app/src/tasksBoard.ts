import type { Question, Run, Section, SectionStatus } from './api';

// What waits for the owner: open questions, and needs-owner and blocked sections.
export const waitingCount = (sections: Section[], questions: Question[]) =>
  questions.filter((q) => q.status === 'open').length
  + sections.filter((s) => s.status === 'needs-owner' || s.status === 'blocked').length;

export type TaskCard =
  | { kind: 'question'; key: string; q: Question }
  | { kind: 'run'; key: string; r: Run }
  | { kind: 'section'; key: string; s: Section; folder: string };
export type TasksColumns = { waiting: TaskCard[]; progress: TaskCard[]; todo: TaskCard[] };
export type TasksFilter = { text: string; folder: string }; // '' matches any; folder narrows documents only

// A document's top folder: its first segment, or Projects/<name>; '' at the root.
export function topFolder(file: string): string {
  const parts = file.split('/');
  if (parts.length < 2) return '';
  return parts[0] === 'Projects' && parts.length > 2 ? `Projects/${parts[1]}` : parts[0];
}

// A section's chip: open shows as a grey "to do", since orange means only a waiting question.
export const chipOf = (status: SectionStatus) => (status === 'open' ? 'todo' : status);

const has = (text: string, ...fields: string[]) =>
  !text || fields.some((f) => f.toLowerCase().includes(text.toLowerCase()));

export function tasksColumns(sections: Section[], runs: Run[], questions: Question[],
  titles: Record<string, string>, { text, folder }: TasksFilter): TasksColumns {
  const docs = sections
    .filter((s) => (!folder || topFolder(s.file) === folder) && has(text, s.heading, s.file, titles[s.file] ?? ''))
    .sort((a, b) => a.file.localeCompare(b.file) || a.line - b.line);
  const of = (status: SectionStatus): TaskCard[] => docs.filter((s) => s.status === status)
    .map((s) => ({ kind: 'section', key: `d:${s.file}#${s.line}`, s, folder: topFolder(s.file) }));
  return {
    waiting: [
      ...questions.filter((q) => q.status === 'open' && has(text, q.question, q.project, q.task))
        .map((q): TaskCard => ({ kind: 'question', key: `q:${q.id}`, q })),
      ...of('needs-owner'), ...of('blocked'),
    ],
    progress: [
      // A run's key is its place: ledger rows have no id, and a run card holds no state.
      ...runs.flatMap((r, i): TaskCard[] => (has(text, r.task, r.agent) ? [{ kind: 'run', key: `r:${i}`, r }] : [])),
      ...of('partial'),
    ],
    todo: of('open'),
  };
}

// The list's groups: questions ('q'), agent runs ('r'), then each top folder
// ('d:<folder>') by name, the root ('d:') last; empty groups are left out.
export function tasksGroups({ waiting, progress, todo }: TasksColumns): { id: string; cards: TaskCard[] }[] {
  const groups = new Map<string, TaskCard[]>();
  for (const c of [...waiting, ...progress, ...todo]) {
    const id = c.kind === 'question' ? 'q' : c.kind === 'run' ? 'r' : `d:${c.folder}`;
    groups.set(id, [...(groups.get(id) ?? []), c]);
  }
  const rank = (id: string) => (id === 'q' ? '0' : id === 'r' ? '1' : id === 'd:' ? '3' : `2${id}`);
  return [...groups].sort(([a], [b]) => rank(a).localeCompare(rank(b))).map(([id, cards]) => ({ id, cards }));
}
