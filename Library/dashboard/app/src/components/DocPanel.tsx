import { useEffect, useState } from 'react';
import { errorCode, getCommits, type Commit, type Section } from '../api';
import { useI18n } from '../i18n';
import { fmtTime } from '../format';
import { chipOf } from '../tasksBoard';
import { Chip } from './Chip';

type Props = { file: string; sections: Section[] };

// A document's side panel: every marked section it holds, by line, and the last
// three commits that touched it, read once when the panel opens.
export function DocPanel({ file, sections }: Props) {
  const { t, lang } = useI18n();
  const [commits, setCommits] = useState<Commit[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    getCommits(file).then((r) => { if (live) setCommits(r.commits); }, (err) => { if (live) setError(errorCode(err)); });
    return () => { live = false; };
  }, [file]);
  const own = sections.filter((s) => s.file === file).sort((a, b) => a.line - b.line);
  return (
    <div className="docpanel">
      <h3>{t('tasks.sections')}</h3>
      <ul className="plain">
        {own.map((s) => <li key={s.line}><Chip state={chipOf(s.status)} /> {s.heading} <span className="key">:{s.line}</span></li>)}
      </ul>
      <h3>{t('tasks.commits')}</h3>
      {error ? <p className="err" role="status">{t(`err.${error}`)}</p>
        : !commits ? <p className="muted">{t('loading')}</p>
        : commits.length === 0 ? <p className="muted">{t('tasks.noCommits')}</p>
        : <ul className="plain">{commits.map((c) => <li key={c.hash}><span className="key">{c.hash}</span> {fmtTime(c.at, lang)} · {c.subject}</li>)}</ul>}
    </div>
  );
}
