import { useEffect, useState } from 'react';

// The page, its view, its open side panel and its folded list groups live in the address.
export type Page = 'agents' | 'claude' | 'codex' | 'taskboard' | 'tasks';
export type View = 'board' | 'list';
export type Route = { page: Page; peek: string | null; view: View; fold: string[] };

const PAGES: Page[] = ['agents', 'claude', 'codex', 'taskboard', 'tasks'];

export function parseHash(hash: string): Route {
  const [path, query = ''] = hash.replace(/^#\/?/, '').split('?');
  const params = new URLSearchParams(query);
  return {
    page: (PAGES as string[]).includes(path) ? (path as Page) : 'agents',
    peek: params.get('peek') || null,
    view: params.get('view') === 'list' ? 'list' : 'board',
    fold: params.getAll('fold').filter(Boolean),
  };
}

export function formatHash({ page, peek, view, fold }: Route): string {
  const params = new URLSearchParams();
  if (peek) params.set('peek', peek);
  if (view === 'list') params.set('view', view);
  for (const id of fold) params.append('fold', id);
  const query = params.toString();
  return '#/' + (page === 'agents' ? '' : page) + (query ? '?' + query : '');
}

export function useRoute(): [Route, (route: Route) => void] {
  const [route, setRoute] = useState(() => parseHash(location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(location.hash));
    addEventListener('hashchange', onChange);
    return () => removeEventListener('hashchange', onChange);
  }, []);
  return [route, (next) => { location.hash = formatHash(next); }];
}
