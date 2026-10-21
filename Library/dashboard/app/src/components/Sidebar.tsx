import type { MouseEvent } from 'react';
import { ClipboardList, ListTodo, SquareKanban } from 'lucide-react';
import type { Agent, AgentName } from '../api';
import { useI18n } from '../i18n';
import type { Page, Route } from '../router';

type Props = {
  agents: Agent[]; route: Route; open: boolean; onPick: (page: Page, peek: string | null) => void;
  waiting: number; // what waits for the owner on the Tasks page
  asking: boolean; // a question waits
};

// An agent whose client has its own page: Peter's row opens the Claude page, Aster's the Codex page.
const PAGE_OF: Partial<Record<AgentName, Page>> = { Peter: 'claude', Aster: 'codex' };

// The project sidebar: the pages, Tasks with what waits in grey, then each
// agent with its live dot and its open questions in orange; an agent with a
// page links to it, May opens her own panel, and the tools follow.
export function Sidebar({ agents, route, open, waiting, asking, onPick }: Props) {
  const { t } = useI18n();
  // A page link: the current page is filled in ink and named so to a screen reader.
  const page = (to: Page) => ({
    href: to === 'agents' ? '#/' : `#/${to}`,
    'aria-current': route.page === to ? 'page' as const : undefined,
    onClick: (e: MouseEvent) => { e.preventDefault(); onPick(to, null); },
  });
  return (
    <aside id="sidebar" className={`side${open ? ' open' : ''}`}>
      <div className="proj">
        <i aria-hidden="true">d</i>
        <div><b>{t('side.project')}</b><span>{t('side.sub')}</span></div>
      </div>
      <nav aria-label={t('nav.label')}>
        <div className="group">{t('side.pages')}</div>
        <a className={`nav${route.page === 'agents' ? ' on' : ''}`} {...page('agents')}>
          <SquareKanban />{t('nav.agents')}
        </a>
        <a className={`nav${route.page === 'tasks' ? ' on' : ''}`} {...page('tasks')}>
          <ListTodo />{t('nav.tasks')}
          {asking && <span className="dot wait" aria-hidden="true" />}
          {waiting > 0 && <><span className="cnt quiet" aria-hidden="true">{waiting}</span><span className="sr">, {t('tasks.waiting', { n: waiting })}</span></>}
        </a>
        <div className="group">{t('side.agents')}</div>
        {agents.map((a) => {
          // Orange is the one colour that means a question waits.
          const dot = a.openQuestions ? ' wait' : a.workload === 'working' ? ' work' : '';
          const state = `${t(`avail.${a.availability}`)}, ${t(`work.${a.workload}`)}`;
          const row = (
            <>
              <span className={`dot${dot}`} aria-hidden="true" />
              {a.name} · {a.client}
              <span className="sr">{state}</span>
              {a.openQuestions > 0 && <span className="cnt">{a.openQuestions}</span>}
            </>
          );
          const to = PAGE_OF[a.name];
          if (to) {
            // Muted text would vanish on the ink fill, so the current row is never drawn offline.
            const on = route.page === to;
            return <a key={a.name} title={state} className={`nav${on ? ' on' : a.availability === 'offline' ? ' off' : ''}`} {...page(to)}>{row}</a>;
          }
          return (
            <button key={a.name} type="button" title={state} onClick={() => onPick('agents', `agent:${a.name}`)}
              className={`nav${route.page === 'agents' && route.peek === `agent:${a.name}` ? ' sel' : ''}${a.availability === 'offline' ? ' off' : ''}`}>
              {row}
            </button>
          );
        })}
        <div className="group">{t('side.tools')}</div>
        <a className={`nav${route.page === 'taskboard' ? ' on' : ''}`} {...page('taskboard')}>
          <ClipboardList />{t('nav.taskboard')}
        </a>
      </nav>
    </aside>
  );
}
