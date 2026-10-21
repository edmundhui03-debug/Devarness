import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { errorCode, getThreads, runPrompt, stopRun, type CodexEvent, type Sandbox } from './api';

// An event from Codex, or null when the stream came back after a drop and
// whatever it missed must be read again.
export type Listener = (event: CodexEvent | null) => void;
type Runs = {
  runs: Map<string, string>; // thread id to the turn this page started there
  start: (prompt: string, sandbox: Sandbox, thread: string | null) => Promise<{ thread: string; turn: string }>;
  stop: (thread: string, turn: string) => Promise<void>;
  listen: (fn: Listener) => () => void;
};

const Context = createContext<Runs | null>(null);
const RETRY_MS = 5000;

// The prompts this page started and Codex's one event stream, held above the
// pages, so a run keeps its Stop button while the owner looks elsewhere.
export function RunsProvider({ children }: { children: ReactNode }) {
  const [runs, setRuns] = useState(() => new Map<string, string>());
  const held = useRef(runs); // the runs as of the last render, for the stream's handlers
  held.current = runs;
  const listeners = useRef(new Set<Listener>());
  // Turns that ended, so a run whose end came before its reply is never held.
  const ended = useRef(new Set<string>());
  const drop = useCallback((thread: string, turn: string) => setRuns((m) => {
    if (m.get(thread) !== turn) return m;
    const next = new Map(m);
    next.delete(thread);
    return next;
  }), []);

  useEffect(() => {
    let source: EventSource;
    let opened = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const connect = () => {
      source = new EventSource('api/codex/events');
      source.onopen = () => {
        if (opened) {
          for (const fn of listeners.current) fn(null);
          // A run whose turn/completed came while the stream was down is let go
          // when the server no longer says its thread is running; one started
          // after the asking is not judged by this answer.
          const before = [...held.current];
          getThreads().then(({ threads }) => {
            for (const [thread, turn] of before) if (threads.find((t) => t.id === thread)?.state !== 'running') drop(thread, turn);
          }, () => {});
        }
        opened = true;
      };
      source.onmessage = (m) => {
        let event: CodexEvent;
        try { event = JSON.parse(m.data); } catch { return; }
        if (typeof event?.method !== 'string') return;
        const p = event.params as { threadId?: unknown; turn?: { id?: unknown }; up?: unknown } | null;
        if (event.method === 'turn/completed' && typeof p?.threadId === 'string' && typeof p.turn?.id === 'string') {
          ended.current.add(p.turn.id);
          drop(p.threadId, p.turn.id);
        }
        // Codex itself stopped: the server let go of every run, and no turn/completed will come.
        if (event.method === 'bridge/appServer' && p?.up === false) setRuns(new Map());
        for (const fn of listeners.current) fn(event);
      };
      // The browser retries a dropped stream by itself; one it gave up on is opened again.
      source.onerror = () => { if (source.readyState === EventSource.CLOSED) retry = setTimeout(connect, RETRY_MS); };
    };
    connect();
    return () => { clearTimeout(retry); source.close(); };
  }, [drop]);

  const start = useCallback(async (prompt: string, sandbox: Sandbox, thread: string | null) => {
    const run = await runPrompt(prompt, sandbox, thread);
    if (!ended.current.has(run.turn)) setRuns((m) => new Map(m).set(run.thread, run.turn));
    return run;
  }, []);
  const stop = useCallback(async (thread: string, turn: string) => {
    try {
      await stopRun(thread, turn);
    } catch (err) {
      // The server no longer knows the turn (it ended, or the server restarted): nothing is left to stop.
      if (errorCode(err) === 'unknown-turn') drop(thread, turn);
      throw err;
    }
  }, [drop]);
  const listen = useCallback((fn: Listener) => {
    listeners.current.add(fn);
    return () => { listeners.current.delete(fn); };
  }, []);
  const value = useMemo(() => ({ runs, start, stop, listen }), [runs, start, stop, listen]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useRuns(): Runs {
  const runs = useContext(Context);
  if (!runs) throw new Error('useRuns needs a RunsProvider above it');
  return runs;
}
