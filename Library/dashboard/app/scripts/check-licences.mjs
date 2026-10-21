// Every package in the lockfile must carry a licence on the allowlist.
import { readFileSync } from 'node:fs';

const ALLOWED = /^(MIT|MIT-0|ISC|Apache-2\.0|BSD-2-Clause|BSD-3-Clause|0BSD|BlueOak-1\.0\.0|CC0-1\.0|Python-2\.0)$/;
// Vite 8 needs lightningcss as an unmodified build tool, and MPL-2.0 binds only
// those who modify and redistribute its files: admitted for these packages alone.
const MPL_ONLY_FOR = /^lightningcss(-[a-z0-9-]+)?$/;
const lock = JSON.parse(readFileSync(new URL('../package-lock.json', import.meta.url), 'utf8'));
// A lockfile without a packages map (version 1) would check nothing and pass.
if (!lock.packages) {
  console.error('package-lock.json has no "packages" map: it must be lockfileVersion 2 or 3');
  process.exit(1);
}
const allowed = (path, l) => ALLOWED.test(l) || (l === 'MPL-2.0' && MPL_ONLY_FOR.test(path.split('node_modules/').pop()));
// A package with no licence has no tokens, and none is a failure, not a pass.
const tokens = (p) => String(p.license ?? '').split(/ OR | AND |[()]/).map((s) => s.trim()).filter(Boolean);
const bad = Object.entries(lock.packages)
  .filter(([path]) => path)
  .filter(([path, p]) => { const t = tokens(p); return !t.length || !t.every((l) => allowed(path, l)); });
for (const [path, p] of bad) console.error(`${path}: ${p.license || 'no licence'}`);
console.log(bad.length ? `${bad.length} package(s) outside the allowlist` : 'every package is on the allowlist');
process.exit(bad.length ? 1 : 0);
