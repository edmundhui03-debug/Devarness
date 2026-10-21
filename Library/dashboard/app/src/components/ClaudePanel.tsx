import { useEffect, useState } from 'react';
import { errorCode, getClaudeAgent, getClaudeSession, type AgentRow, type AgentView, type ClaudeView, type RunRow } from '../api';
import { claudeKey, folderOf } from '../claudeBoard';
import { fmtTime, knownWord, sourceWord } from '../format';
import { useI18n } from '../i18n';
import { Chip } from './Chip';

// The filters over a session's steps, by kind.
const SHOW: Record<string, string[] | null> = { all: null, turns: ['prompt', 'reply'], tools: ['tool', 'result'] };
// The address is untrusted: only ids of the contract's shape are asked for, so no
// dot segment or separator from it ever reaches a URL.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const AGENT = /^agent-[A-Za-z0-9]{1,64}$/;

type Props = { session: string; agent: string | null; onOpen: (address: string) => void }; // agent null: the session itself

// A Claude Code session, or one of its subagents, in the side panel: its fields,
// then its last steps as the server read and masked them, read again every 3 s
// while it works and every 10 s otherwise. Read-only: nothing is sent to Claude.
export function ClaudePanel({ session, agent, onOpen }: Props) {
  const { t, lang } = useI18n();
  const [view, setView] = useState<ClaudeView | AgentView | null>(null);
  const [failed, setFailed] = useState<string | null>(null); // the reading's error code
  const [show, setShow] = useState('all');
  const wellFormed = UUID.test(session) && (agent === null || AGENT.test(agent));

  useEffect(() => {
    if (!wellFormed) return;
    let live = true;
    let reading = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    // One reading at a time: the next is set only once this one has answered; a hidden tab skips its reading.
    const read = async () => {
      let working = false;
      if (document.visibilityState === 'visible') {
        reading = true;
        try {
          const next = agent === null ? await getClaudeSession(session) : await getClaudeAgent(session, agent);
          working = next.state === 'working';
          if (live) { setView(next); setFailed(null); }
        } catch (err) {
          if (live) setFailed(errorCode(err));
        }
        reading = false;
      }
      if (live) timer = setTimeout(read, working ? 3_000 : 10_000);
    };
    // A tab shown again reads at once, as the board does (usePoll), unless a reading is on its way.
    const shown = () => {
      if (document.visibilityState === 'visible' && !reading) { clearTimeout(timer); void read(); }
    };
    document.addEventListener('visibilitychange', shown);
    void read();
    return () => { live = false; clearTimeout(timer); document.removeEventListener('visibilitychange', shown); };
  }, [session, agent, wellFormed]);

  const code = wellFormed ? failed : 'not-found';
  const when = (at: string | null) => (at ? fmtTime(at, lang) : '—');
  const agentRow = (row: AgentRow) => (
    <li key={row.id}>
      <button type="button" className="linkbtn" onClick={() => onOpen(`a:${session}:${row.id}`)}>{row.title}</button> <Chip state={row.state} />
      {row.type && <span className="muted"> · {row.type}</span>}
      <span className="muted"> · {when(row.updatedAt)}</span>
    </li>
  );
  // A run's last update, unlabelled as an agent row's: its end when the start and duration are known,
  // else its newest agent's update (agents come newest first), else its start.
  const lastUpdate = (r: RunRow) => {
    const end = r.startedAt && r.durationMs !== null ? Date.parse(r.startedAt) + r.durationMs : NaN;
    return Number.isFinite(end) ? new Date(end).toISOString() : r.agents[0]?.updatedAt ?? r.startedAt;
  };
  // A run's status as written; running is ink and failed outlined, as the states they match.
  const status = (r: RunRow) => (
    <span className={`chip${r.status === 'running' ? ' chip-running' : r.status === 'failed' ? ' chip-error' : ''}`}>{knownWord('state', r.status, t)}</span>
  );

  const kinds = SHOW[show];
  const steps = (view?.steps ?? []).filter((s) => !kinds || kinds.includes(s.kind));
  // A session's view holds its commits, subagents and runs; a subagent's its type and run.
  const s = view && 'commits' in view ? view : null;
  const a = view && !('commits' in view) ? view : null;
  return (
    <>
      {code && <p className="banner" role="alert">{t(`err.${code}`)}</p>}
      {!view && !code && <p className="muted">{t('loading')}</p>}
      {view && <>
        <h2>{view.title || view.id}</h2>
        {a && <button type="button" className="linkbtn" onClick={() => onOpen(`c:${session}`)}>{t('claude.back', { key: claudeKey(session) })}</button>}
        <dl className="fields">
          <dt>{t('field.state')}</dt><dd><Chip state={view.state} /></dd>
          {s && <>
            <dt>{t('field.source')}</dt><dd>{s.source ? sourceWord(s.source, t) : '—'}</dd>
            <dt>{t('field.folder')}</dt><dd title={s.cwd || undefined}>{folderOf(s) || '—'}</dd>
            <dt>{t('field.branch')}</dt><dd>{s.branch ?? '—'}</dd>
          </>}
          {a && <>
            <dt>{t('field.type')}</dt><dd>{a.type ?? '—'}</dd>
            {a.run && <><dt>{t('field.run')}</dt><dd>{a.run}</dd></>}
          </>}
          <dt>{t('field.updated')}</dt><dd>{when(view.updatedAt)}</dd>
        </dl>
        {s && <>
          <h3>{t('tasks.commits')}</h3>
          {!s.commits ? <p className="muted">{t('claude.commitsUnreadable')}</p>
            : s.commits.length === 0 ? <p className="muted">{t('claude.noCommits')}</p>
            : <ul className="turns" aria-label={t('tasks.commits')}>{s.commits.map((c) => <li key={c.hash}><span className="key">{c.hash}</span> {fmtTime(c.at, lang)} · {c.subject}</li>)}</ul>}
        </>}
        {!view.readable ? <p className="muted">{t('claude.unreadable')}</p> : <>
          <div className="acts" role="group" aria-label={t('thread.show')}>
            {Object.keys(SHOW).map((k) => (
              <button key={k} type="button" className={`act${show === k ? ' on' : ''}`} aria-pressed={show === k} onClick={() => setShow(k)}>{t(`thread.${k}`)}</button>
            ))}
          </div>
          {steps.length === 0 && <p className="muted">{t('claude.noSteps')}</p>}
          <ol className="turns" aria-label={t('claude.steps')}>
            {steps.map((st, i) => (
              <li key={i} className="entry">
                <span className="who">{t(`step.${st.kind}`)}{st.tool && ` · ${st.tool}`}{st.error && <> <Chip state="error" /></>}</span>
                {st.text && <div className={st.kind === 'tool' || st.kind === 'result' ? 'cmd pre' : 'pre'}>{st.text}</div>}
              </li>
            ))}
          </ol>
        </>}
        {s && s.agents.length > 0 && <>
          <h3>{t('claude.agents')}</h3>
          <ul className="turns" aria-label={t('claude.agents')}>{s.agents.map(agentRow)}</ul>
        </>}
        {s && s.runs.length > 0 && <>
          <h3>{t('claude.runs')}</h3>
          <ul className="turns" aria-label={t('claude.runs')}>
            {s.runs.map((r) => (
              <li key={r.id} className="entry">
                <b>{r.name || r.id}</b> {status(r)} {r.agentCount !== null && <span className="muted">{t('claude.agentCount', { n: r.agentCount })}</span>}<span className="muted"> · {when(lastUpdate(r))}</span>
                {r.summary && <div className="pre muted">{r.summary}</div>}
                {r.agents.length > 0 && <ul className="turns">{r.agents.map(agentRow)}</ul>}
              </li>
            ))}
          </ul>
        </>}
      </>}
    </>
  );
}
