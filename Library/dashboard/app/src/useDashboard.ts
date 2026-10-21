import { useCallback, useEffect, useRef, useState } from 'react';
import { getAgents, getQuestions, type Agent, type Question } from './api';

export type Dashboard = {
  agents: Agent[]; questions: Question[]; at: string | null; loaded: boolean;
  error: string | null; // the server did not answer
  fileError: string | null; // the server answered, but questions.json cannot be read
};

const EMPTY: Dashboard = { agents: [], questions: [], at: null, loaded: false, error: null, fileError: null };

// Calls refresh now, every ms (10 s by default) while the tab is visible, and when it is shown again.
export function usePoll(refresh: () => unknown, ms = 10_000) {
  useEffect(() => {
    void refresh();
    const tick = () => { if (document.visibilityState === 'visible') void refresh(); };
    const timer = setInterval(tick, ms);
    document.addEventListener('visibilitychange', tick);
    return () => { clearInterval(timer); document.removeEventListener('visibilitychange', tick); };
  }, [refresh, ms]);
}

// Polls the agents and the questions every 10 s while the tab is visible, and on demand.
export function useDashboard(): Dashboard & { refresh: () => void; saved: (q: Question) => void } {
  const [data, setData] = useState(EMPTY);
  const latest = useRef(0);
  const refresh = useCallback(async () => {
    const ask = ++latest.current; // an older, slower answer never replaces a newer one
    try {
      const [a, q] = await Promise.all([getAgents(), getQuestions()]);
      if (ask === latest.current) setData({ agents: a.agents, at: a.at, questions: q.questions, loaded: true, error: null, fileError: q.error ?? null });
    } catch (err) {
      if (ask === latest.current) setData((d) => ({ ...d, loaded: true, error: err instanceof Error ? err.message : String(err) }));
    }
  }, []);
  usePoll(refresh);
  // A saved answer shows at once, from the question the server returned; the
  // refresh it starts also drops any poll already on its way with the old state.
  const saved = useCallback((q: Question) => {
    setData((d) => ({ ...d, questions: d.questions.map((x) => (x.id === q.id ? q : x)) }));
    void refresh();
  }, [refresh]);
  return { ...data, refresh, saved };
}
