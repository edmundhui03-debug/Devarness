import { afterEach, vi } from 'vitest';
import { cleanup, configure } from '@testing-library/react';
import { FakeEventSource } from './test-fakes';

vi.stubGlobal('EventSource', FakeEventSource);
// findBy and waitFor wait 10 s, not 1 s: under another build's load a panel's first reading
// outlasts 1 s (runs.test.tsx, 2026-10-15). A passing wait still ends as soon as it holds.
configure({ asyncUtilTimeout: 10_000 });

afterEach(() => { cleanup(); localStorage.clear(); location.hash = ''; document.documentElement.lang = 'en'; FakeEventSource.all = []; });
