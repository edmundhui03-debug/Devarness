// markers.mjs: whether a Codex session file's last turn is still open, from its
// turn markers (spec, "What this could not establish"). Only the marker is read;
// no text of the file leaves here. Peter checks the names on a real session
// file (plan task 11); until then they are the spec's.
import { closeSync, openSync, readSync, statSync } from 'node:fs';

const TAIL = 64 * 1024;
const START = ['task_started'];
const END = ['task_complete', 'turn_aborted'];

// true when the last marker in the file's final 64 KB is a start, false when it
// is an end; null when there is none or the file cannot be read.
export function lastTurnOpen(path) {
  try {
    const size = statSync(path).size;
    const length = Math.min(size, TAIL);
    const buf = Buffer.alloc(length);
    const fd = openSync(path, 'r');
    try { readSync(fd, buf, 0, length, size - length); } finally { closeSync(fd); }
    for (const line of buf.toString('utf8').split('\n').reverse()) {
      let entry;
      try { entry = JSON.parse(line); } catch { continue; } // a cut first line
      const type = entry?.payload?.type ?? entry?.type;
      if (START.includes(type)) return true;
      if (END.includes(type)) return false;
    }
  } catch { /* gone, locked or a folder */ }
  return null;
}
