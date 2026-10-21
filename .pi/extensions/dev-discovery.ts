import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const hook = fileURLToPath(new URL('../../tools/session.py', import.meta.url));

export default function (pi) {
  pi.on('before_agent_start', async (event, ctx) => {
    if (typeof event.prompt !== 'string') return;
    const content = await new Promise((resolve) => {
      const child = spawn('python3', [hook, '--prompt-hook'], { windowsHide: true, stdio: ['pipe', 'pipe', 'ignore'] });
      let output = '';
      const timer = setTimeout(() => { child.kill(); resolve('Discovery unavailable; follow CLAUDE.md and Karpathy guidelines.'); }, 8000);
      child.stdout.setEncoding('utf8');
      child.stdout.on('data', (data) => { output += data; });
      child.on('error', () => { clearTimeout(timer); resolve('Discovery unavailable; follow CLAUDE.md and Karpathy guidelines.'); });
      child.stdin.on('error', () => {});
      child.on('close', () => {
        clearTimeout(timer);
        try { resolve(JSON.parse(output).hookSpecificOutput.additionalContext); }
        catch { resolve('Discovery unavailable; follow CLAUDE.md and Karpathy guidelines.'); }
      });
      child.stdin.end(JSON.stringify({ hook_event_name: 'UserPromptSubmit', prompt: event.prompt, cwd: ctx.cwd }));
    });
    return { message: { customType: 'devarness-discovery', content, display: false } };
  });
}
