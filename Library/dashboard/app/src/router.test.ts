import { describe, expect, it } from 'vitest';
import { formatHash, parseHash } from './router';

describe('the address of a page, its view and its side panel', () => {
  it('reads and writes the same route, on every page', () => {
    for (const route of [
      { page: 'agents' as const, peek: null, view: 'board' as const, fold: [] },
      { page: 'agents' as const, peek: 'agent:Peter', view: 'board' as const, fold: [] },
      { page: 'agents' as const, peek: 'q:q-2026-10-09-pcb-001', view: 'list' as const, fold: [] },
      { page: 'codex' as const, peek: 't:019a-thread', view: 'list' as const, fold: [] },
      { page: 'codex' as const, peek: 'new', view: 'board' as const, fold: [] },
      { page: 'taskboard' as const, peek: null, view: 'board' as const, fold: [] },
    ]) expect(parseHash(formatHash(route))).toEqual(route);
  });
  it('reads the Codex page with its panel and view', () => {
    expect(parseHash('#/codex?peek=t:abc&view=list')).toEqual({ page: 'codex', peek: 't:abc', view: 'list', fold: [] });
    expect(formatHash({ page: 'taskboard', peek: null, view: 'board', fold: [] })).toBe('#/taskboard');
  });
  it('treats an empty or unknown hash as the Agents board', () => {
    expect(parseHash('')).toEqual({ page: 'agents', peek: null, view: 'board', fold: [] });
    expect(parseHash('#/?view=list')).toEqual({ page: 'agents', peek: null, view: 'list', fold: [] });
    expect(parseHash('#/nope?peek=agent:May')).toEqual({ page: 'agents', peek: 'agent:May', view: 'board', fold: [] });
    expect(formatHash({ page: 'agents', peek: null, view: 'board', fold: [] })).toBe('#/');
  });
  it('maps #/claude with its peek and its view, and back', () => {
    const route = parseHash('#/claude?peek=a%3A0b1c2d3e-0000-4000-8000-000000000001%3Aagent-a1&view=list');
    expect(route).toEqual({ page: 'claude', peek: 'a:0b1c2d3e-0000-4000-8000-000000000001:agent-a1', view: 'list', fold: [] });
    expect(parseHash(formatHash(route))).toEqual(route);
    expect(formatHash({ page: 'claude', peek: null, view: 'board', fold: [] })).toBe('#/claude');
  });
  it('maps #/tasks with its folded groups and its peek, and back', () => {
    const route = parseHash('#/tasks?view=list&fold=d%3ASetup&fold=r&peek=d%3ASetup%2Fa.md');
    expect(route).toEqual({ page: 'tasks', peek: 'd:Setup/a.md', view: 'list', fold: ['d:Setup', 'r'] });
    expect(parseHash(formatHash(route))).toEqual(route);
    expect(formatHash({ page: 'agents', peek: null, view: 'board', fold: [] })).toBe('#/');
  });
});
