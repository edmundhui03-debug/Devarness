import { useState } from 'react';
import { ChevronDown, ChevronRight, RefreshCw, Search } from 'lucide-react';
import { askerOf, questionKey } from '../board';
import { Chip } from '../components/Chip';
import { DocPanel } from '../components/DocPanel';
import { PeekPanel } from '../components/PeekPanel';
import { QuestionsPanel } from '../components/QuestionsPanel';
import { ViewTabs } from '../components/ViewTabs';
import { fmtTime, named } from '../format';
import { useI18n } from '../i18n';
import type { Route } from '../router';
import { chipOf, tasksColumns, tasksGroups, topFolder, type TaskCard } from '../tasksBoard';
import type { useDashboard } from '../useDashboard';
import type { useTasks } from '../useTasks';

type Props = { route: Route; go: (route: Route) => void; data: ReturnType<typeof useDashboard>; tasks: ReturnType<typeof useTasks> };

// The Tasks page: what waits for the owner and what is in progress, as three
// columns or a list grouped by top folder, and the panel its address opens. A
// missing Python, a failed index or unreadable questions is said in a banner,
// never drawn as an empty board.
export function TasksPage({ route, go, data, tasks }: Props) {
  const { t, lang } = useI18n();
  const [text, setText] = useState('');
  const [folder, setFolder] = useState('');
  // Typed answers by question id, kept here so closing the panel never loses one.
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const index = tasks.tasks;
  const sections = index?.sections ?? [];
  const titles = index?.titles ?? {};
  const cols = tasksColumns(sections, index?.runs ?? [], data.questions, titles, { text, folder });
  const peek = (p: string | null) => go({ ...route, peek: p });
  const fold = (id: string) => go({ ...route, fold: route.fold.includes(id) ? route.fold.filter((f) => f !== id) : [...route.fold, id] });
  const folders = [...new Set(sections.map((s) => topFolder(s.file)).filter(Boolean))].sort();
  const groupName = (id: string) => (id === 'q' ? t('tasks.group.questions') : id === 'r' ? t('tasks.group.runs') : id === 'd:' ? t('tasks.group.root') : id.slice(2));
  const when = (iso: string | null, raw: string) => (iso ? fmtTime(iso, lang) : raw);

  function card(c: TaskCard) {
    if (c.kind === 'question') return (
      <button key={c.key} type="button" onClick={() => peek(c.key)} className={`ticket wait${route.peek === c.key ? ' sel' : ''}`}>
        <span className="ttl">{c.q.question}</span>
        <span className="tmeta"><span className="key">{questionKey(c.q.id)}</span><span className="lbl">{c.q.project}</span></span>
      </button>
    );
    if (c.kind === 'run') return (
      <div key={c.key} className="ticket" title={c.r.task}>
        <span className="ttl">{c.r.task}</span>
        <span className="tmeta">
          <Chip state="running" />{c.r.stale && <Chip state="stale" />}
          <span>{c.r.agent}</span><span className="nowrap">{when(c.r.at, c.r.launched)}</span><span>{c.r.budget}</span>
        </span>
      </div>
    );
    const address = `d:${c.s.file}`;
    return (
      <button key={c.key} type="button" onClick={() => peek(address)} className={`ticket${route.peek === address ? ' sel' : ''}`}>
        <span className="ttl">{c.s.heading}</span>
        <span className="tmeta">
          <Chip state={chipOf(c.s.status)} />
          <span className="key">{`${c.s.file}:${c.s.line}`}</span>
          {c.folder && <span className="folder">{c.folder}</span>}
        </span>
      </button>
    );
  }
  const column = (id: string, cards: TaskCard[]) => (
    <section key={id} className="column" aria-label={t(`col.${id}`)}>
      <h2 className="colhead">{t(`col.${id}`)} <span className="n">{cards.length}</span></h2>
      {cards.length === 0 && <p className="addcard">{t('col.empty')}</p>}
      {cards.map(card)}
    </section>
  );
  const rowOf = (c: TaskCard) => (c.kind === 'question'
    ? { address: c.key, title: c.q.question, state: 'open', where: c.q.project, at: fmtTime(c.q.asked_at, lang) }
    : c.kind === 'run'
      ? { address: null, title: c.r.task, state: c.r.stale ? 'stale' : 'running', where: c.r.agent, at: when(c.r.at, c.r.launched) }
      : { address: `d:${c.s.file}`, title: c.s.heading, state: chipOf(c.s.status), where: `${c.s.file}:${c.s.line}`, at: '' });

  function detail() {
    if (!route.peek) return null;
    const address = route.peek;
    const close = () => peek(null);
    // Only a document the index lists opens, so no other path reaches git.
    if (address.startsWith('d:') && address.length > 2) {
      const file = address.slice(2);
      if (Object.hasOwn(titles, file) || sections.some((s) => s.file === file)) return (
        <PeekPanel address={address} label={named(file, titles[file] ?? file)} head={<span className="key">{file}</span>} onClose={close}>
          <DocPanel key={address} file={file} sections={sections} />
        </PeekPanel>
      );
    }
    const q = address.startsWith('q:') ? data.questions.find((x) => x.id === address.slice(2)) : undefined;
    if (q) return (
      <PeekPanel address={address} label={named(questionKey(q.id), q.question)} head={<span className="key">{questionKey(q.id)}</span>} onClose={close}>
        <QuestionsPanel agent={askerOf(q)} questions={[q]} fileError={null} onSaved={data.saved} drafts={drafts}
          onDraft={(id, value) => setDrafts((d) => ({ ...d, [id]: value }))} />
      </PeekPanel>
    );
    if (!data.loaded || !tasks.loaded) return null;
    return (
      <PeekPanel address={address} label={t('peek.missing')} head={null} onClose={close}>
        <p className="muted">{t('peek.missing')}</p>
      </PeekPanel>
    );
  }

  const panel = detail();
  const groups = tasksGroups(cols);
  return (
    <main id="content" className="page" tabIndex={-1}>
      <div className="crumbs">{t('side.project')} / {t('nav.tasks')}</div>
      <div className="headrow">
        <h1>{t('nav.tasks')}</h1>
        <span className="grow" />
        {index && <span className="info">{t('tasks.at', { when: fmtTime(index.at, lang) })}</span>}
        <button type="button" className="btn" onClick={tasks.refresh}><RefreshCw />{t('refresh')}</button>
      </div>
      <p className="lead">{t('tasks.lead')}</p>
      {tasks.error && <p className="banner" role="alert">{t(`err.${tasks.error}`)}</p>}
      {index && index.code !== 'ok' && <p className="banner" role="alert">{t(`err.${index.code}`)}</p>}
      {data.error && <p className="banner" role="alert">{t('loadError', { error: data.error })}</p>}
      {data.fileError && <p className="banner" role="alert">{t('q.fileError', { error: data.fileError })}</p>}
      {!tasks.loaded && <p className="muted">{t('loading')}</p>}
      {tasks.loaded && <>
        <ViewTabs route={route} go={go} />
        <div className="toolbar">
          <label className="filter box">
            <Search />
            <input type="search" value={text} placeholder={t('search.label')} aria-label={t('search.label')} onChange={(e) => setText(e.target.value)} />
          </label>
          <select className="choose" aria-label={t('filter.docFolder')} value={folder} onChange={(e) => setFolder(e.target.value)}>
            <option value="">{t('filter.anyFolder')}</option>
            {folders.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </div>
        <div className={`work${panel ? ' peeking' : ''}`}>
          <div role="tabpanel" aria-labelledby={`tab-${route.view}`}>
            {route.view === 'board' ? (
              <div className="board three">
                {column('waiting', cols.waiting)}
                {column('progress', cols.progress)}
                {column('todo', cols.todo)}
              </div>
            ) : (
              <div className="tablewrap">
                <table className="table">
                  <thead><tr>{['title', 'state', 'where', 'when'].map((k) => <th key={k} scope="col">{t(`field.${k}`)}</th>)}</tr></thead>
                  {groups.length === 0 && <tbody><tr><td colSpan={4} className="muted">{t('col.empty')}</td></tr></tbody>}
                  {groups.map((g) => {
                    const shut = route.fold.includes(g.id);
                    return (
                      <tbody key={g.id}>
                        <tr className="grouprow">
                          <th colSpan={4} scope="rowgroup">
                            <button type="button" className="linkbtn" aria-expanded={!shut} onClick={() => fold(g.id)}>
                              {shut ? <ChevronRight /> : <ChevronDown />}{groupName(g.id)} <span className="n">{g.cards.length}</span>
                            </button>
                          </th>
                        </tr>
                        {!shut && g.cards.map((c) => {
                          const r = rowOf(c);
                          return (
                            <tr key={c.key} className={r.address && route.peek === r.address ? 'sel' : ''}>
                              <td>{r.address ? <button type="button" className="linkbtn" onClick={() => peek(r.address)}>{r.title}</button> : r.title}</td>
                              <td><Chip state={r.state} /></td>
                              <td><span className="key">{r.where}</span></td>
                              <td className="nowrap">{r.at || '—'}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    );
                  })}
                </table>
              </div>
            )}
          </div>
          {panel}
        </div>
      </>}
    </main>
  );
}
