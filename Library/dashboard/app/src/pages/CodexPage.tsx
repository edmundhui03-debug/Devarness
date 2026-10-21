import { useEffect, useState, type ReactNode } from 'react';
import { Plus, RefreshCw, Search } from 'lucide-react';
import { errorCode, signIn, type Question, type RateWindow, type Thread } from '../api';
import { askerOf, questionKey } from '../board';
import { codexColumns, folderOf, threadKey, threadTitle } from '../codexBoard';
import { Chip } from '../components/Chip';
import { PeekPanel } from '../components/PeekPanel';
import { QuestionsPanel } from '../components/QuestionsPanel';
import { ThreadPanel } from '../components/ThreadPanel';
import { ViewTabs } from '../components/ViewTabs';
import { fmtSeconds, fmtTime, named, sourceWord } from '../format';
import { useI18n } from '../i18n';
import type { Route } from '../router';
import { useRuns } from '../runs';
import { useCodex } from '../useCodex';
import type { useDashboard } from '../useDashboard';

type Props = { route: Route; go: (route: Route) => void; data: ReturnType<typeof useDashboard> };

const IDLE_SHOWN = 8;
const BOARD_EVENTS = /^(thread\/(started|status\/changed)|turn\/completed|account\/)/;
const uniq = (values: string[]) => [...new Set(values.filter(Boolean))].sort();

// Aster's page, the Codex board: Codex's state in the header, then the board of
// four columns or the list, and the panel its address opens. Nothing is drawn
// as a board while Codex is down, so a stopped Codex never looks idle.
export function CodexPage({ route, go, data }: Props) {
  const { t, lang } = useI18n();
  const { status, threads, loaded, error, refresh } = useCodex();
  const { listen } = useRuns();
  const [text, setText] = useState('');
  const [source, setSource] = useState('');
  const [folder, setFolder] = useState('');
  const [allIdle, setAllIdle] = useState(false);
  // Typed answers by question id, kept here so closing the panel never loses one.
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [note, setNote] = useState<string | null>(null); // how the last Sign in went, as a key
  const cols = codexColumns(threads, data.questions, { text, source, folder });
  const peek = (p: string | null) => go({ ...route, peek: p });
  // A thread that starts or stops, a finished sign-in, or Codex coming up shows at once rather than
  // at the next poll. Codex going down waits for the poll: each asking makes the server try Codex
  // again, and each failed try says up:false once more, so asking on it would never end.
  useEffect(() => listen((e) => {
    const up = e?.method === 'bridge/appServer' && (e.params as { up?: unknown } | null)?.up === true;
    if (!e || up || BOARD_EVENTS.test(e.method)) refresh();
  }), [listen, refresh]);

  async function startSignIn() {
    setNote(null);
    try {
      const { authUrl } = await signIn();
      // Only an https:// address opens, in a tab that cannot reach back to this page.
      if (typeof authUrl !== 'string' || !authUrl.startsWith('https://')) throw Object.assign(new Error(), { code: 'bad-sign-in' });
      window.open(authUrl, '_blank', 'noopener,noreferrer');
      setNote('codex.signInOpened');
    } catch (err) {
      setNote(`err.${errorCode(err)}`);
    }
  }

  const threadCard = (th: Thread) => (
    <button key={th.id} type="button" onClick={() => peek(`t:${th.id}`)} className={`ticket${route.peek === `t:${th.id}` ? ' sel' : ''}`}>
      <span className="ttl">{threadTitle(th)}</span>
      <span className="tmeta">
        <span className="key">{threadKey(th.id)}</span>
        {th.source && <span className="lbl">{sourceWord(th.source, t)}</span>}
        {th.state === 'error' && <Chip state="error" />}
        {th.nickname && <span>{th.nickname}</span>}
        {th.cwd && <span className="folder" title={th.cwd}>{folderOf(th)}</span>}
      </span>
    </button>
  );
  const questionCard = (q: Question) => (
    <button key={q.id} type="button" onClick={() => peek(`q:${q.id}`)} className={`ticket wait${route.peek === `q:${q.id}` ? ' sel' : ''}`}>
      <span className="ttl">{q.question}</span>
      <span className="tmeta"><span className="key">{questionKey(q.id)}</span><span className="lbl">{q.project}</span></span>
    </button>
  );
  const column = (id: string, cards: ReactNode[], hidden = 0) => (
    <section key={id} className="column" aria-label={t(`col.${id}`)}>
      <h2 className="colhead">{t(`col.${id}`)} <span className="n">{cards.length + hidden}</span></h2>
      {cards.length === 0 && <p className="addcard">{t('col.empty')}</p>}
      {cards}
      {hidden > 0 && <button type="button" className="addcard more" onClick={() => setAllIdle(true)}>{t('col.more', { n: hidden })}</button>}
    </section>
  );
  const idle = allIdle ? cols.idle : cols.idle.slice(0, IDLE_SHOWN);
  const rows = [
    ...cols.waiting.map((q) => ({ address: `q:${q.id}`, title: q.question, state: 'open', source: q.project, folder: '', path: '', when: fmtTime(q.asked_at, lang) })),
    ...[...cols.running, ...cols.elsewhere, ...cols.idle].map((th) => ({
      address: `t:${th.id}`, title: threadTitle(th), state: th.state, source: th.source ? sourceWord(th.source, t) : '',
      folder: folderOf(th), path: th.cwd ?? '', when: fmtSeconds(th.updatedAt, lang),
    })),
  ];

  const quota = (w: RateWindow, i: number) => {
    const mins = w.windowDurationMins ?? 0;
    const name = !mins ? t('codex.quota') : mins % 1440 === 0 ? t('codex.days', { n: mins / 1440 }) : t('codex.hours', { n: Math.round(mins / 60) });
    return (
      <span key={i}>
        {name}<meter min={0} max={100} value={w.usedPercent ?? 0} aria-label={name} />
        <b>{t('codex.used', { used: w.usedPercent ?? '?' })}</b> · {t('codex.resets', { when: fmtSeconds(w.resetsAt, lang) })}
      </span>
    );
  };

  function detail() {
    if (!route.peek || !status?.up) return null;
    const address = route.peek;
    const close = () => peek(null);
    // The thread panel remounts per address (a fresh box and reading); the
    // PeekPanel around it stays, so focus still returns to the first opener.
    const open = (thread: string) => peek(`t:${thread}`);
    if (address === 'new') return (
      <PeekPanel address={address} label={t('run.newTitle')} head={null} onClose={close}>
        <ThreadPanel key={address} id={null} onOpen={open} />
      </PeekPanel>
    );
    if (address.startsWith('t:') && address.length > 2) {
      const id = address.slice(2);
      const th = threads.find((x) => x.id === id);
      return (
        <PeekPanel address={address} label={th ? named(threadKey(id), threadTitle(th)) : threadKey(id)} head={<span className="key">{threadKey(id)}</span>} onClose={close}>
          <ThreadPanel key={address} id={id} onOpen={open} />
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
  const windows = [status?.rateLimits?.primary, status?.rateLimits?.secondary].filter((w): w is RateWindow => !!w);
  return (
    <main id="content" className="page" tabIndex={-1}>
      <div className="crumbs">{t('side.project')} / {t('nav.agents')} / Aster</div>
      <div className="headrow">
        <h1>Aster · Codex</h1>
        <span className="grow" />
        {status?.signedIn && <span className="info">{t('codex.plan', { plan: status.plan ?? status.type ?? '?' })}</span>}
        {status?.version && <span className="info">{t('codex.version', { version: status.version })}</span>}
        {status?.up && <button type="button" className="btn" onClick={() => peek('new')}><Plus />{t('codex.new')}</button>}
        <button type="button" className="btn" onClick={refresh}><RefreshCw />{t('refresh')}</button>
      </div>
      <p className="lead">{t('codex.lead')}</p>
      {error && <p className="banner" role="alert">{t(`err.${error}`)}</p>}
      {!loaded && <p className="muted">{t('loading')}</p>}
      {status && !status.up && <p className="banner" role="alert"><b>{t('codex.notStarted')}</b> {t('codex.notStartedFix')}</p>}
      {status?.up && !status.signedIn && (
        <p className="banner" role="alert">
          {t('codex.signedOut')} <button type="button" className="btn" onClick={startSignIn}>{t('codex.signIn')}</button>
        </p>
      )}
      {note && <p className={note.startsWith('err.') ? 'err' : 'ok'} role="status">{t(note)}</p>}

      {status?.up && <>
        <ViewTabs route={route} go={go} />
        <div className="toolbar">
          <label className="filter box">
            <Search />
            <input type="search" value={text} placeholder={t('search.label')} aria-label={t('search.label')} onChange={(e) => setText(e.target.value)} />
          </label>
          <select className="choose" aria-label={t('filter.source')} value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">{t('filter.anySource')}</option>
            {uniq(threads.map((th) => th.source ?? '')).map((s) => <option key={s} value={s}>{sourceWord(s, t)}</option>)}
          </select>
          <select className="choose" aria-label={t('filter.folder')} value={folder} onChange={(e) => setFolder(e.target.value)}>
            <option value="">{t('filter.anyFolder')}</option>
            {uniq(threads.map(folderOf)).map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
          {windows.length > 0 && <div className="quota">{windows.map(quota)}</div>}
        </div>

        <div className={`work${panel ? ' peeking' : ''}`}>
          <div role="tabpanel" aria-labelledby={`tab-${route.view}`}>
            {route.view === 'board' ? (
              <div className="board">
                {column('running', cols.running.map(threadCard))}
                {column('waiting', cols.waiting.map(questionCard))}
                {column('elsewhere', cols.elsewhere.map(threadCard))}
                {column('idle', idle.map(threadCard), cols.idle.length - idle.length)}
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
      </>}
    </main>
  );
}
