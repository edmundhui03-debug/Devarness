import { useCallback, useRef, useState } from 'react';
import { errorCode, getClaude, type ClaudeSession } from './api';
import { usePoll } from './useDashboard';

export type ClaudeData = {
  sessions: ClaudeSession[]; loaded: boolean;
  error: string | null; // the server did not answer: its error code, which the page words
};
const EMPTY: ClaudeData = { sessions: [], loaded: false, error: null };

// Claude Code's sessions on this computer, every 10 s while the tab is visible, and on demand.
export function useClaude(): ClaudeData & { refresh: () => void } {
  const [data, setData] = useState(EMPTY);
  const latest = useRef(0);
  const refresh = useCallback(async () => {
    const ask = ++latest.current; // an older, slower answer never replaces a newer one
    try {
      const { sessions } = await getClaude();
      if (ask === latest.current) setData({ sessions, loaded: true, error: null });
    } catch (err) {
      if (ask === latest.current) setData((d) => ({ ...d, loaded: true, error: errorCode(err) }));
    }
  }, []);
  usePoll(refresh);
  return { ...data, refresh };
}
