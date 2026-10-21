import { useCallback, useEffect, useState } from 'react';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { errorCode, getTaskboard } from '../api';
import { useI18n } from '../i18n';

// The owner's local issue board, Codex Taskboard, framed while it runs; the
// server says whether it answers, and the dashboard never starts it.
export function TaskboardPage() {
  const { t, lang } = useI18n();
  const [board, setBoard] = useState<{ running: boolean; url: string } | null>(null);
  const [failed, setFailed] = useState<string | null>(null); // the server did not answer: its error code
  const [checking, setChecking] = useState(true);
  const check = useCallback(async () => {
    setChecking(true);
    try {
      setBoard(await getTaskboard());
      setFailed(null);
    } catch (err) {
      setFailed(errorCode(err));
    }
    setChecking(false);
  }, []);
  useEffect(() => { void check(); }, [check]);
  // The board speaks the dashboard's language: 中文 asks for its (Hong Kong) Chinese.
  const shown = board ? `${board.url}/?lang=${lang === 'zh-HK' ? 'zh' : 'en'}` : '';

  return (
    <main id="content" className="page" tabIndex={-1}>
      <div className="crumbs">{t('side.project')} / {t('side.tools')} / {t('nav.taskboard')}</div>
      <div className="headrow">
        <h1>{t('nav.taskboard')}</h1>
        <span className="grow" />
        {board?.running && <a className="btn" href={shown} target="_blank" rel="noopener noreferrer"><ExternalLink />{t('tb.open')}</a>}
        <button type="button" className="btn" disabled={checking} onClick={check}><RefreshCw />{t('tb.check')}</button>
      </div>
      <p className="lead">{t('tb.lead')}</p>
      {failed && <p className="banner" role="alert">{t(`err.${failed}`)}</p>}
      {!board && !failed && <p className="muted" role="status">{t('tb.checking')}</p>}
      {board?.running && <iframe className="tbframe" src={shown} title={t('tb.frame')} />}
      {board && !board.running && (
        <section className="tbcard">
          <p role="status"><b>{t('tb.down')}</b></p>
          <p>{t('tb.start')} <code>taskboard start</code></p>
          <p className="muted">{t('tb.local')}</p>
        </section>
      )}
    </main>
  );
}
