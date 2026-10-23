import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import discovery from '../../.pi/extensions/dev-discovery.ts';

const handlers = {};
discovery({ on: (name, callback) => { handlers[name] = callback; } });
assert.equal(typeof handlers.before_agent_start, 'function');
assert.equal(await handlers.before_agent_start({ messageType: 'custom' }, {}), undefined);
const cwd = fileURLToPath(new URL('../../', import.meta.url));
// 'yes' matches no curated keyword, so it gets no Vercel search (owner, 2026-10-20).
for (const prompt of ['yes', 'find skills for react testing']) {
  const result = await handlers.before_agent_start({ prompt }, { cwd });
  assert.equal(result.message.display, false);
  assert.match(result.message.content, /karpathy-guidelines:/);
  assert.equal(/vercel-find/.test(result.message.content), false);
  assert.match(result.message.content, /retro-last:/);
}
console.log('PASS: Pi event adapter delivers shared discovery on short and task prompts.');
