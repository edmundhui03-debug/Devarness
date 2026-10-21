// A stand-in for Library/bin/md-format in the Tasks tests. Its behaviour is read
// from <root>/fake-index.txt, since the server gives it only a small environment:
// ok, junk (bad entries mixed in), fail, garbage or hang.
const { readFileSync } = require('node:fs');
const { join } = require('node:path');

if (process.argv.slice(2).join(' ') !== 'status --json') process.exit(9);
const mode = readFileSync(join(__dirname, '..', '..', 'fake-index.txt'), 'utf8').trim();
const index = {
  sections: [
    { status: 'needs-owner', file: 'Setup/a.md', line: 7, heading: 'The owner picks a colour', live: true },
    { status: 'open', file: 'Projects/demo/docs/b.md', line: 12, heading: 'The icon is open', live: true },
    { status: 'fixed', file: 'README.md', line: 3, heading: 'Done', live: false },
  ],
  files: ['Setup/a.md', 'Projects/demo/docs/b.md', 'README.md'],
  titles: { 'Setup/a.md': 'A', 'Projects/demo/docs/b.md': 'B', 'README.md': 'dev' },
  counts: { marked: 3, live: 2, dormant: 0, absent: 0 },
};
const junk = [{ status: 'weird', file: 'x.md', line: 1, heading: 'h' }, { status: 'open', file: 'y.md', line: '2', heading: 'h' }, null];
if (mode === 'fail') {
  process.stderr.write(`Traceback: md-format in ${__dirname}\n`);
  process.exit(3);
} else if (mode === 'garbage') process.stdout.write('not json');
else if (mode === 'hang') setTimeout(() => {}, 60_000);
else if (mode === 'junk') process.stdout.write(JSON.stringify({ ...index, sections: [...index.sections, ...junk] }));
else process.stdout.write(JSON.stringify(index));
