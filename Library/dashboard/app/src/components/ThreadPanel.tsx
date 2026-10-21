import { useEffect, useId, useRef, useState } from 'react';
import { errorCode, getThread, type Sandbox, type ThreadView } from '../api';
import { folderOf, threadLines, threadTitle } from '../codexBoard';
import { fmtSeconds, sourceWord } from '../format';
import { useI18n } from '../i18n';
import { useRuns } from '../runs';
import { Chip } from './Chip';

// The events that change what an open thread shows.
const RELOAD = ['item/completed', 'turn/started', 'turn/completed'];
// The filters over a thread's items, by the kinds threadLines gives.
const SHOW: Record<string, string[] | null> = { all: null, turns: ['prompt', 'reply'], commands: ['command'], files: ['file'] };
// The server holds no turn on the thread any more: Stop gives way to Run.
const noTurn = (v: ThreadView | null) => v && { ...v, turn: null };

type Props = { id: string | null; onOpen: (thread: string) => void }; // id null: the composer of a new thread

// A Codex thread in the side panel: its fields, the items of its last turns,
// and the reply box; with no id, the box that starts a new thread in the dev
// workspace. The panel shows the server's reading of the thread, read again on
// each of its events, so a line never shows twice.
export function ThreadPanel({ id, onOpen }: Props) {
  const { t, lang } = useI18n();
  const { runs, start, stop, listen } = useRuns();
  const box = useId();
  const [view, setView] = useState<ThreadView | null>(null);
  const [failed, setFailed] = useState<string | null>(null); // the reading's error code
  const [show, setShow] = useState('all');
  const [prompt, setPrompt] = useState('');
  const [sandbox, setSandbox] = useState<Sandbox>('read-only');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null); // a refused Run or Stop, by its code

  useEffect(() => {
    if (id === null) return;
    let live = true;
    let reading = false;
    let again = false;
    // One reading at a time; events that come meanwhile make one more, so the last word is never missed.
    const read = async () => {
      if (reading) { again = true; return; }
      reading = true;
      try {
        const next = await getThread(id);
        if (live) { setView(next); setFailed(null); }
      } catch (err) {
        if (live) setFailed(errorCode(err));
      }
      reading = false;
      if (again && live) { again = false; void read(); }
    };
    void read();
    const off = listen((e) => {
      const up = e?.method === 'bridge/appServer' ? (e.params as { up?: unknown } | null)?.up : undefined;
      // Codex stopping lets go of every turn without a turn/completed. Reading now would make the
      // server try Codex again, and each failed try says up:false once more, so the turn goes here.
      if (up === false) setView(noTurn);
      else if (e === null || up === true
        || (RELOAD.includes(e.method) && (e.params as { threadId?: unknown } | null)?.threadId === id)) void read();
    });
    return () => { live = false; off(); };
  }, [id, listen]);

  // A run this page started, or the turn the server says it holds, so Stop
  // survives a reload and a Run that timed out.
  const turn = id === null ? undefined : runs.get(id) ?? view?.turn;
  // The latest onOpen while the panel is shown, so a late answer neither pulls the
  // owner back to a page they left nor undoes a view they chose meanwhile.
  const opener = useRef<Props['onOpen'] | null>(null);
  useEffect(() => { opener.current = onOpen; return () => { opener.current = null; }; });
  async function run() {
    setBusy(true);
    setNote(null);
    try {
      const started = await start(prompt, sandbox, id);
      // workspace-write is for this one reply.
      setPrompt('');
      setSandbox('read-only');
      if (id === null) opener.current?.(started.thread);
    } catch (err) {
      setNote(errorCode(err)); // the typed prompt stays in the box
    } finally {
      setBusy(false);
    }
  }
  const [stopping, setStopping] = useState(false); // a Stop request is on its way
  async function halt() {
    setNote(null);
    setStopping(true);
    try {
      await stop(id!, turn!);
    } catch (err) {
      const code = errorCode(err);
      if (code === 'unknown-turn') setView(noTurn); // the turn shown came from a reading now stale
      setNote(code);
    } finally {
      setStopping(false);
    }
  }

  const kinds = SHOW[show];
  const lines = threadLines(view?.turns ?? [], t).filter((l) => !kinds || kinds.includes(l.kind));
  const reply = (id === null || view) && (
    <div className="answer">
      <label htmlFor={box}>{t(id === null ? 'run.new' : 'run.reply')}</label>
      <textarea id={box} value={prompt} onChange={(e) => setPrompt(e.target.value)} />
      <div className="row">
        <select className="choose" aria-label={t('run.sandbox')} value={sandbox} onChange={(e) => setSandbox(e.target.value as Sandbox)}>
          <option value="read-only">{t('run.readOnly')}</option>
          {/* Codex may write only in the dev workspace, where new threads start. */}
          {(id === null || view?.inDev) && <option value="workspace-write">{t('run.workspaceWrite')}</option>}
        </select>
        <span className="grow" />
        {turn
          ? <button type="button" className="btn" onClick={halt} disabled={stopping}>{t('run.stop')}</button>
          : <button type="button" className="btn primary" disabled={!prompt.trim() || busy} onClick={run}>{t('run.run')}</button>}
      </div>
      {note && <p className="err" role="alert">{t(`err.${note}`)}</p>}
    </div>
  );

  if (id === null) return (
    <>
      <h2>{t('run.newTitle')}</h2>
      <p className="muted">{t('run.newLead')}</p>
      {reply}
    </>
  );
  return (
    <>
      {failed && <p className="banner" role="alert">{t(`err.${failed}`)}</p>}
      {!view && !failed && <p className="muted">{t('loading')}</p>}
      {view && <>
        <h2>{threadTitle(view)}</h2>
        <dl className="fields">
          <dt>{t('field.state')}</dt><dd><Chip state={view.state} /></dd>
          <dt>{t('field.source')}</dt><dd>{view.source ? sourceWord(view.source, t) : '—'}{view.nickname && ` · ${view.nickname}`}</dd>
          <dt>{t('field.folder')}</dt><dd title={view.cwd ?? undefined}>{folderOf(view) || '—'}</dd>
          <dt>{t('field.created')}</dt><dd>{fmtSeconds(view.createdAt, lang)}</dd>
          <dt>{t('field.updated')}</dt><dd>{fmtSeconds(view.updatedAt, lang)}</dd>
        </dl>
        <div className="acts" role="group" aria-label={t('thread.show')}>
          {Object.keys(SHOW).map((k) => (
            <button key={k} type="button" className={`act${show === k ? ' on' : ''}`} aria-pressed={show === k} onClick={() => setShow(k)}>{t(`thread.${k}`)}</button>
          ))}
        </div>
        {lines.length === 0 && <p className="muted">{t('thread.none')}</p>}
        <ol className="turns">
          {lines.map((l, i) => (
            <li key={i} className="entry">
              <span className="who">{t(`kind.${l.kind}`)}</span>
              <div className={l.kind === 'command' ? 'cmd pre' : 'pre'}>{l.text}</div>
            </li>
          ))}
        </ol>
      </>}
      {reply}
    </>
  );
}
