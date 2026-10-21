import { useId, useState } from 'react';
import { answer, type Question } from '../api';
import { askerOf } from '../board';
import { fmtTime } from '../format';
import { useI18n } from '../i18n';

type Drafts = Record<string, string>;
type Props = {
  // agent is an asker as askerOf gives it, '' for none; onSaved gets the question as the server saved it.
  agent: string; questions: Question[]; fileError: string | null; onSaved: (q: Question) => void;
  // Typed answers, kept by the page so they outlive the panel; without them the panel keeps its own.
  drafts?: Drafts; onDraft?: (id: string, text: string) => void;
};
// busy: the server answered 503, which the page says in its own words.
type Note = { error: string | null; busy?: boolean };

// One agent's questions: each open one with an answer box, answered ones
// until the agent uses them, then the used ones as history. All read-only but the box.
export function QuestionsPanel({ agent, questions, fileError, onSaved, drafts: given, onDraft }: Props) {
  const { t, lang } = useI18n();
  const base = useId();
  const [own, setOwn] = useState<Drafts>({});
  const drafts = given ?? own;
  const setDraft = onDraft ?? ((id: string, text: string) => setOwn((d) => ({ ...d, [id]: text })));
  const [notes, setNotes] = useState<Record<string, Note>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const mine = questions.filter((q) => askerOf(q) === agent);
  const current = mine.filter((q) => q.status !== 'used');
  const used = mine.filter((q) => q.status === 'used');
  const who = agent || t('agent.unknown');

  async function save(q: Question) {
    setBusy(q.id);
    try {
      const { question } = await answer(q.id, drafts[q.id] ?? '');
      setDraft(q.id, '');
      setNotes((n) => ({ ...n, [q.id]: { error: null } }));
      onSaved(question);
    } catch (err) {
      // The typed text stays in the box, so a refused answer is not lost.
      const status = err instanceof Error ? (err as Error & { status?: number }).status : undefined;
      setNotes((n) => ({ ...n, [q.id]: { error: err instanceof Error ? err.message : String(err), busy: status === 503 } }));
    } finally {
      setBusy(null);
    }
  }

  const item = (q: Question, i: number) => {
    const id = `${base}-${i}`;
    const draft = drafts[q.id] ?? '';
    const note = notes[q.id];
    return (
      <article key={q.id} className={`qitem${q.status === 'open' ? ' wait' : ''}`}>
        <p className="qtext" id={id}>{q.question}</p>
        <dl className="fields">
          <dt>{t('field.askedBy')}</dt><dd>{who}</dd>
          <dt>{t('field.project')}</dt><dd>{q.project}</dd>
          <dt>{t('field.task')}</dt><dd>{q.task || '—'}</dd>
          <dt>{t('field.asked')}</dt><dd>{fmtTime(q.asked_at, lang)}</dd>
          {q.status !== 'open' && <><dt>{t('field.answer')}</dt><dd className="pre">{q.answer}</dd></>}
          {q.status === 'used' && <>
            <dt>{t('field.usedBy')}</dt><dd>{q.used_by || '—'}{q.used_at && ` · ${fmtTime(q.used_at, lang)}`}</dd>
            <dt>{t('field.usedNote')}</dt><dd className="pre">{q.used_note || '—'}</dd>
          </>}
        </dl>
        {q.status === 'open' && (
          <div className="answer">
            <label htmlFor={`${id}-a`}>{t('q.answer')}</label>
            <textarea id={`${id}-a`} aria-describedby={id} value={draft} onChange={(e) => setDraft(q.id, e.target.value)} />
            <div className="row">
              <span className="grow" />
              <button type="button" className="btn primary" disabled={!draft.trim() || busy === q.id} onClick={() => save(q)}>{t('q.save')}</button>
            </div>
          </div>
        )}
        {q.status === 'answered' && <p className="muted">{t('q.waitingAgent', { agent: who })}</p>}
        {note && (note.error
          ? <p className="err" role="alert">{note.busy ? t('q.busy') : t('q.error', { error: note.error })}</p>
          : <p className="ok" role="status">{t('q.saved', { agent: who })}</p>)}
      </article>
    );
  };

  return (
    <section className="qpanel">
      <h3 className="group">{t('q.title', { agent: who })}</h3>
      {fileError && <p className="banner" role="alert">{t('q.fileError', { error: fileError })}</p>}
      {mine.length === 0 && <p className="muted">{t('q.none')}</p>}
      {current.map(item)}
      {used.length > 0 && <>
        <h4 className="group">{t('q.history', { n: used.length })}</h4>
        {used.map((q, i) => item(q, current.length + i))}
      </>}
    </section>
  );
}
