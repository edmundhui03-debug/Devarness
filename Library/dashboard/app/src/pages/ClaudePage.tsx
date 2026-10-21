import { useState, type ReactNode } from 'react';
import { RefreshCw, Search } from 'lucide-react';
import type { ClaudeSession, Question } from '../api';
import { askerOf, questionKey } from '../board';
import { claudeColumns, claudeKey, folderOf, sessionTitle } from '../claudeBoard';
import { Chip } from '../components/Chip';
import { ClaudePanel } from '../components/ClaudePanel';
import { PeekPanel } from '../components/PeekPanel';
import { QuestionsPanel } from '../components/QuestionsPanel';
import { ViewTabs } from '../components/ViewTabs';
import { fmtTime, named, sourceWord } from '../format';
import { useI18n } from '../i18n';
import type { Route } from '../router';
import { useClaude } from '../useClaude';
import type { useDashboard } from '../useDashboard';

type Props = { route: Route; go: (route: Route) => void; data: ReturnType<typeof useDashboard> };

// The filters' options; each also keeps the one chosen after its sessions leave the listing, so the select reads what filters.
const uniq = (values: string[]) => [...new Set(values.filter(Boolean))].sort();

// Peter's page, the Claude board: every Claude Code session on this computer in
// four columns, or the list, and the panel its address opens. Read-only: the
// page sends nothing to Claude.
export function ClaudePage({ route, go, data }: Props) {
  const { t, lang } = useI18n();
  const { sessions, loaded, error, refresh } = useClaude();
  const [text, setText] = useState('');
  const [source, setSource] = useState('');
  const [folder, setFolder] = useState('');
  // Typed answers by question id, kept here so closing the panel never loses one.
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const cols = claudeColumns(sessions, data.questions, { text, source, folder });
  const peek = (p: string | null) => go({ ...route, peek: p });

  const sessionCard = (s: ClaudeSession) => (
    <button key={s.id} type="button" onClick={() => peek(`c:${s.id}`)} className={`ticket${route.peek === `c:${s.id}` ? ' sel' : ''}`}>
      <span className="ttl">{sessionTitle(s)}</span>
      <span className="tmeta">
        <span className="key">{claudeKey(s.id)}</span>
        {s.source && <span className="lbl">{sourceWord(s.source, t)}</span>}
        {s.cwd && <span className="folder" title={s.cwd}>{folderOf(s)}</span>}
      </span>
    </button>
  );
  const questionCard = (q: Question) => (
    <button key={q.id} type="button" onClick={() => peek(`q:${q.id}`)} className={`ticket wait${route.peek === `q:${q.id}` ? ' sel' : ''}`}>
      <span className="ttl">{q.question}</span>
      <span className="tmeta"><span className="key">{questionKey(q.id)}</span><span className="lbl">{q.project}</span></span>
    </button>
  );
  const column = (id: string, cards: ReactNode[]) => (
    <section key={id} className="column" aria-label={t(`col.${id}`)}>
      <h2 className="colhead">{t(`col.${id}`)} <span className="n">{cards.length}</span></h2>
      {cards.length === 0 && <p className="addcard">{t('col.empty')}</p>}
      {cards}
    </section>
  );
  const rows = [
    ...cols.waiting.map((q) => ({ address: `q:${q.id}`, title: q.question, state: 'open', source: q.project, folder: '', path: '', when: fmtTime(q.asked_at, lang) })),
    ...[...cols.working, ...cols.idle, ...cols.ended].map((s) => ({
      address: `c:${s.id}`, title: sessionTitle(s), state: s.state, source: s.source ? sourceWord(s.source, t) : '',
      folder: folderOf(s), path: s.cwd, when: s.updatedAt ? fmtTime(s.updatedAt, lang) : '—',
    })),
  ];

  function detail() {
    if (!route.peek) return null;
    const address = route.peek;
    const close = () => peek(null);
    // c:<session id> or a:<session id>:<agent id>. The panel asks the server even for a session the
    // listing lacks, so one that ended long ago is worded by the server's 404; it remounts per address.
    const m = /^(?:c:([^:]+)|a:([^:]+):(.+))$/.exec(address);
    if (m) {
      const session = m[1] ?? m[2];
      const agent = m[3] ?? null;
      const key = claudeKey(session);
      const s = sessions.find((x) => x.id === session);
      return (
        <PeekPanel address={address} label={agent ? `${key} ${agent}` : s ? named(key, sessionTitle(s)) : key} head={<span className="key">{key}</span>} onClose={close}>
          <ClaudePanel key={address} session={session} agent={agent} onOpen={peek} />
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
    if (!data.loaded) return null;
    return (
      <PeekPanel address={address} label={t('peek.missing')} head={null} onClose={close}>
        <p className="muted">{t('peek.missing')}</p>
      </PeekPanel>
    );
  }

  const panel = detail();
  return (
    <main id="content" className="page" tabIndex={-1}>
      <div className="crumbs">{t('side.project')} / {t('nav.agents')} / Peter</div>
      <div className="headrow">
        <h1>Peter · Claude Code</h1>
        <span className="grow" />
        <button type="button" className="btn" onClick={refresh}><RefreshCw />{t('refresh')}</button>
      </div>
      <p className="lead">{t('claude.lead')}</p>
      {error && <p className="banner" role="alert">{t(`err.${error}`)}</p>}
      {!loaded && <p className="muted">{t('loading')}</p>}

      <ViewTabs route={route} go={go} />
      <div className="toolbar">
        <label className="filter box">
          <Search />
          <input type="search" value={text} placeholder={t('search.label')} aria-label={t('search.label')} onChange={(e) => setText(e.target.value)} />
        </label>
        <select className="choose" aria-label={t('filter.source')} value={source} onChange={(e) => setSource(e.target.value)}>
          <option value="">{t('filter.anySource')}</option>
          {uniq([...sessions.map((s) => s.source), source]).map((s) => <option key={s} value={s}>{sourceWord(s, t)}</option>)}
        </select>
        <select className="choose" aria-label={t('filter.folder')} value={folder} onChange={(e) => setFolder(e.target.value)}>
          <option value="">{t('filter.anyFolder')}</option>
          {uniq([...sessions.map(folderOf), folder]).map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </div>

      <div className={`work${panel ? ' peeking' : ''}`}>
        <div role="tabpanel" aria-labelledby={`tab-${route.view}`}>
          {route.view === 'board' ? (
            <div className="board">
              {column('waiting', cols.waiting.map(questionCard))}
              {column('working', cols.working.map(sessionCard))}
              {column('idle', cols.idle.map(sessionCard))}
              {column('ended', cols.ended.map(sessionCard))}
            </div>
          ) : (
            <div className="tablewrap">
              <table className="table">
                <thead>
                  <tr>{['title', 'state', 'source', 'folder', 'updated'].map((k) => <th key={k} scope="col">{t(`field.${k}`)}</th>)}</tr>
                </thead>
                <tbody>
                  {rows.length === 0 && <tr><td colSpan={5} className="muted">{t('col.empty')}</td></tr>}
                  {rows.map((r) => (
                    <tr key={r.address} className={route.peek === r.address ? 'sel' : ''}>
                      <td><button type="button" className="linkbtn" onClick={() => peek(r.address)}>{r.title}</button></td>
                      <td><Chip state={r.state} /></td>
                      <td>{r.source || '—'}</td>
                      <td><span className="folder" title={r.path}>{r.folder || '—'}</span></td>
                      <td className="nowrap">{r.when}</td>
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
