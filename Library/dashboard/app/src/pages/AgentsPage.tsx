import { useState } from 'react';
import { RefreshCw, Search } from 'lucide-react';
import { AGENTS, PREFIX, askerOf, buildBoard, filterCards, isAgent, listOrder, parsePeek, peekOf, questionKey, type Card } from '../board';
import { Chip } from '../components/Chip';
import { PeekPanel } from '../components/PeekPanel';
import { QuestionsPanel } from '../components/QuestionsPanel';
import { ViewTabs } from '../components/ViewTabs';
import { fmtTime, named, sourceWord } from '../format';
import { useI18n } from '../i18n';
import type { Route } from '../router';
import type { useDashboard } from '../useDashboard';

type Props = { route: Route; go: (route: Route) => void; data: ReturnType<typeof useDashboard> };

const IDLE_SHOWN = 8;

// The Agents page: breadcrumbs, title, view tabs, toolbar, then the board of
// four status columns or the list, and the detail panel its address opens.
export function AgentsPage({ route, go, data }: Props) {
  const { t, lang } = useI18n();
  const [text, setText] = useState('');
  const [shown, setShown] = useState<Set<string>>(() => new Set(AGENTS));
  const [allIdle, setAllIdle] = useState(false);
  // Typed answers by question id, kept here so closing or switching the panel never loses one.
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const onDraft = (id: string, value: string) => setDrafts((d) => ({ ...d, [id]: value }));
  const board = buildBoard(data.agents, data.questions);
  const sessions = [...board.working, ...board.idle];
  const pick = (cards: Card[]) => filterCards(cards, text, shown);
  const columns = [
    { id: 'waiting', cards: pick(board.waiting) },
    { id: 'working', cards: pick(board.working) },
    { id: 'idle', cards: pick(board.idle) },
    { id: 'offline', cards: pick(board.offline) },
  ];
  const peek = (p: string | null) => go({ ...route, peek: p });
  const when = (iso: string | null) => (iso ? fmtTime(iso, lang) : '—');
  const label = (raw: string) => sourceWord(raw, t);
  // A question that names no asker shows a neutral "?" and reads Unknown.
  const who = (agent: string) => agent || t('agent.unknown');
  const avatar = (agent: string) => (
    <span className={`mini ${isAgent(agent) ? `av-${agent}` : 'av-other'}`} title={who(agent)} aria-hidden="true">{agent[0]?.toUpperCase() ?? '?'}</span>
  );
  const toggle = (name: string) => setShown((s) => {
    const next = new Set(s);
    if (!next.delete(name)) next.add(name);
    return next;
  });

  const ticket = (c: Card) => (
    <button key={peekOf(c)} type="button" onClick={() => peek(peekOf(c))}
      className={`ticket${c.kind === 'question' ? ' wait' : ''}${route.peek === peekOf(c) ? ' sel' : ''}`}>
      <span className="ttl">{c.title}</span>
      <span className="tmeta">
        <span className="key">{c.key}</span>
        <span className="lbl">{label(c.label)}</span>
        {c.state === 'error' && <Chip state="error" />}
        {c.folder && <span className="folder" title={c.path}>{c.folder}</span>}
        {avatar(c.agent)}
      </span>
    </button>
  );

  function detail() {
    if (!route.peek || !data.loaded) return null;
    const address = route.peek;
    const close = () => peek(null);
    const p = parsePeek(address);
    // The page's banner already reports a broken questions.json, so the panels do not repeat it.
    const questionsOf = (agent: string, questions: typeof data.questions) => (
      <QuestionsPanel agent={agent} questions={questions} fileError={null} onSaved={data.saved} drafts={drafts} onDraft={onDraft} />
    );
    if (p?.kind === 'question') {
      const q = data.questions.find((x) => x.id === p.id);
      if (q) return (
        <PeekPanel address={address} label={named(questionKey(q.id), q.question)} head={<span className="key">{questionKey(q.id)}</span>} onClose={close}>
          {questionsOf(askerOf(q), [q])}
        </PeekPanel>
      );
    }
    if (p?.kind === 'session') {
      const c = sessions.find((x) => x.agent === p.agent && x.id === p.id);
      if (c) return (
        <PeekPanel address={address} label={named(c.key, c.title)} head={<span className="key">{c.key}</span>} onClose={close}>
          <h2>{c.title}</h2>
          <dl className="fields">
            <dt>{t('field.assignee')}</dt><dd>{c.agent}</dd>
            <dt>{t('field.state')}</dt><dd><Chip state={c.state} /></dd>
            <dt>{t('field.source')}</dt><dd>{label(c.label)}</dd>
            <dt>{t('field.folder')}</dt><dd title={c.path}>{c.folder || '—'}</dd>
            <dt>{t('field.updated')}</dt><dd>{when(c.updatedAt)}</dd>
          </dl>
        </PeekPanel>
      );
    }
    if (p?.kind === 'agent') {
      const a = data.agents.find((x) => x.name === p.id);
      const mine = a ? sessions.filter((c) => c.agent === a.name) : [];
      if (a) return (
        <PeekPanel address={address} label={`${a.name} · ${a.client}`} head={<span className="key">{PREFIX[a.name]}</span>} onClose={close}>
          <h2>{a.name} · {a.client}</h2>
          {a.note && <p className="banner">{t('agent.note', { note: a.note })}</p>}
          <dl className="fields">
            <dt>{t('field.availability')}</dt><dd>{t(`avail.${a.availability}`)}</dd>
            <dt>{t('field.workload')}</dt><dd>{t(`work.${a.workload}`)}</dd>
          </dl>
          <h3 className="group">{t('agent.sessions')}</h3>
          {mine.length ? (
            <ul className="slist">
              {mine.map((c) => (
                <li key={peekOf(c)}>
                  <button type="button" className="linkbtn" onClick={() => peek(peekOf(c))}>{c.title}</button>
                  <span className="tmeta">
                    <span className="key">{c.key}</span><Chip state={c.state} />
                    {c.folder && <span className="folder" title={c.path}>{c.folder}</span>}
                    <span>{when(c.updatedAt)}</span>
                  </span>
                </li>
              ))}
            </ul>
          ) : <p className="muted">{t('agent.noSessions')}</p>}
          {questionsOf(a.name, data.questions)}
        </PeekPanel>
      );
    }
    return (
      <PeekPanel address={address} label={t('peek.missing')} head={null} onClose={close}>
        <p className="muted">{t('peek.missing')}</p>
      </PeekPanel>
    );
  }

  const panel = detail();
  const all = columns.flatMap((col) => col.cards);
  const loading = <p className="addcard">{t('loading')}</p>;
  return (
    <main id="content" className="page" tabIndex={-1}>
      <div className="crumbs">{t('side.project')} / {t('nav.agents')}</div>
      <div className="headrow">
        <h1>{t('nav.agents')}</h1>
        <span className="grow" />
        {data.at && <span className="muted small">{t('updated', { time: fmtTime(data.at, lang) })}</span>}
        <button type="button" className="btn" onClick={data.refresh}><RefreshCw />{t('refresh')}</button>
      </div>
      <p className="lead">{t('agents.lead')}</p>
      {data.error && <p className="banner" role="alert">{t('loadError', { error: data.error })}</p>}
      {data.fileError && <p className="banner" role="alert">{t('q.fileError', { error: data.fileError })}</p>}

      <ViewTabs route={route} go={go} />

      <div className="toolbar">
        <label className="filter box">
          <Search />
          <input type="search" value={text} placeholder={t('search.label')} aria-label={t('search.label')} onChange={(e) => setText(e.target.value)} />
        </label>
        <div className="pills" role="group" aria-label={t('filter.agents')}>
          {AGENTS.map((name) => (
            <button key={name} type="button" aria-pressed={shown.has(name)} className={`pill${shown.has(name) ? ' on' : ''}`} onClick={() => toggle(name)}>
              {avatar(name)}{name}
            </button>
          ))}
        </div>
      </div>

      <div className={`work${panel ? ' peeking' : ''}`}>
        <div role="tabpanel" aria-labelledby={`tab-${route.view}`}>
          {route.view === 'board' ? (
            <div className="board">
              {columns.map(({ id, cards }) => {
                const cut = id === 'idle' && !allIdle && cards.length > IDLE_SHOWN;
                return (
                  <section key={id} className="column" aria-label={t(`col.${id}`)}>
                    <h2 className="colhead">{t(`col.${id}`)} {data.loaded && <span className="n">{cards.length}</span>}</h2>
                    {!data.loaded ? loading : cards.length === 0 && <p className="addcard">{t('col.empty')}</p>}
                    {(cut ? cards.slice(0, IDLE_SHOWN) : cards).map(ticket)}
                    {cut && <button type="button" className="addcard more" onClick={() => setAllIdle(true)}>{t('col.more', { n: cards.length - IDLE_SHOWN })}</button>}
                  </section>
                );
              })}
            </div>
          ) : (
            <div className="tablewrap">
              <table className="table">
                <thead>
                  <tr>{['key', 'title', 'agent', 'state', 'folder', 'updated'].map((k) => <th key={k} scope="col">{t(`field.${k}`)}</th>)}</tr>
                </thead>
                <tbody>
                  {all.length === 0 && <tr><td colSpan={6} className="muted">{data.loaded ? t('col.empty') : t('loading')}</td></tr>}
                  {listOrder(all).map((c) => (
                    <tr key={peekOf(c)} className={route.peek === peekOf(c) ? 'sel' : ''}>
                      <td className="key">{c.key}</td>
                      <td><button type="button" className="linkbtn" onClick={() => peek(peekOf(c))}>{c.title}</button></td>
                      <td>{who(c.agent)}</td>
                      <td><Chip state={c.state} /></td>
                      <td><span className="folder" title={c.path}>{c.folder}</span></td>
                      <td className="nowrap">{when(c.updatedAt)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        {panel}
      </div>
    </main>
  );
}
