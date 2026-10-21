import { useCallback, useRef, useState } from 'react';
import { errorCode, getTasks, type Tasks } from './api';
import { usePoll } from './useDashboard';

export type TasksData = { tasks: Tasks | null; loaded: boolean; error: string | null };
const EMPTY: TasksData = { tasks: null, loaded: false, error: null };

// The section index and the running ledger rows, every 30 s while the tab is
// visible, and on demand. md-format runs on each reading, so it polls slower than the agents.
export function useTasks(): TasksData & { refresh: () => void } {
  const [data, setData] = useState(EMPTY);
  const latest = useRef(0);
  const refresh = useCallback(async () => {
    const ask = ++latest.current; // an older, slower answer never replaces a newer one
    try {
      const tasks = await getTasks();
      if (ask === latest.current) setData({ tasks, loaded: true, error: null });
    } catch (err) {
      if (ask === latest.current) setData((d) => ({ ...d, loaded: true, error: errorCode(err) }));
    }
  }, []);
  usePoll(refresh, 30_000);
  return { ...data, refresh };
}
