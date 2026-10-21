import { useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { I18nProvider } from './i18n';
import { AgentsPage } from './pages/AgentsPage';
import { ClaudePage } from './pages/ClaudePage';
import { CodexPage } from './pages/CodexPage';
import { TaskboardPage } from './pages/TaskboardPage';
import { TasksPage } from './pages/TasksPage';
import { useRoute, type Page } from './router';
import { RunsProvider } from './runs';
import { waitingCount } from './tasksBoard';
import { useDashboard } from './useDashboard';
import { useTasks } from './useTasks';

// The Jira shell: top bar, project sidebar and the page the address names.
export function App() {
  const [route, go] = useRoute();
  const data = useDashboard();
  const tasks = useTasks();
  const [menu, setMenu] = useState(false);
  const open = data.questions.filter((q) => q.status === 'open');
  const waiting = waitingCount(tasks.tasks?.sections ?? [], data.questions);
  // Another page opens on its board with nothing folded; the same page keeps both.
  const pick = (page: Page, peek: string | null) => {
    setMenu(false);
    const same = page === route.page;
    go({ page, peek, view: same ? route.view : 'board', fold: same ? route.fold : [] });
  };
  return (
    <I18nProvider>
      <RunsProvider>
        <TopBar page={route.page} openCount={open.length} onBell={() => { if (open[0]) pick('agents', `q:${open[0].id}`); }} menuOpen={menu} onMenu={() => setMenu(!menu)} />
        <div className="shell">
          <Sidebar agents={data.agents} route={route} open={menu} waiting={waiting} asking={open.length > 0} onPick={pick} />
          {route.page === 'claude' ? <ClaudePage route={route} go={go} data={data} />
            : route.page === 'codex' ? <CodexPage route={route} go={go} data={data} />
            : route.page === 'taskboard' ? <TaskboardPage />
            : route.page === 'tasks' ? <TasksPage route={route} go={go} data={data} tasks={tasks} />
            : <AgentsPage route={route} go={go} data={data} />}
        </div>
      </RunsProvider>
    </I18nProvider>
  );
}
