import { useCallback, useRef, useState } from 'react';
import { errorCode, getCodex, getThreads, type CodexStatus, type Thread } from './api';
import { usePoll } from './useDashboard';

export type Codex = {
  status: CodexStatus | null; threads: Thread[]; loaded: boolean;
  error: string | null; // the server did not answer: its error code, which the page words
};

const EMPTY: Codex = { status: null, threads: [], loaded: false, error: null };

// Polls Codex's state, then its threads while it is up, every 10 s while the
// tab is visible, and on demand.
export function useCodex(): Codex & { refresh: () => void } {
  const [data, setData] = useState(EMPTY);
  const latest = useRef(0);
  const refresh = useCallback(async () => {
    const ask = ++latest.current; // an older, slower answer never replaces a newer one
    try {
      const status = await getCodex();
      const { threads } = status.up ? await getThreads() : { threads: [] };
      if (ask === latest.current) setData({ status, threads, loaded: true, error: null });
    } catch (err) {
      if (ask === latest.current) setData((d) => ({ ...d, loaded: true, error: errorCode(err) }));
    }
  }, []);
  usePoll(refresh);
  return { ...data, refresh };
}
