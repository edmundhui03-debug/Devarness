"""How much a running workflow has spent, in the unit its completion notice reports.

    python3 .claude/skills/delegate/spend.py <workflow transcript dir> [stop-line tokens]

The notice's subagent_tokens is, per agent, the last message's context plus
its output; summing that over each agent's transcript so far came within 3% of
the notice on 2026-10-14 (3.45M counted, 3.36M reported), and read 18% high
on the TieItUp study the same day (2.26M counted, 1.91M reported), the safe
direction for a stop line. Reads only usage numbers and the phase names, never
transcript text. With a stop line, prints
STOP once the spend reaches 80% of it, so a Monitor can wake Peter in time.
"""
import glob, json, os, sys

folder = sys.argv[1]
stop = int(sys.argv[2]) if len(sys.argv) > 2 else 0
phases = {}
agents = 0
for path in glob.glob(os.path.join(folder, "agent-*.jsonl")):
    last = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if '"usage"' not in line:
                continue
            try:
                usage = (json.loads(line).get("message") or {}).get("usage")
            except ValueError:
                continue
            if usage:
                last = usage
    if last is None:
        continue
    agents += 1
    try:
        with open(path[:-len(".jsonl")] + ".meta.json", encoding="utf-8") as f:
            phase = json.load(f).get("workflowPhase") or "?"
    except (OSError, ValueError):
        phase = "?"
    spent = sum(last.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))
    phases[phase] = phases.get(phase, 0) + spent

total = sum(phases.values())
parts = ", ".join(f"{p} {n / 1e6:.2f}M" for p, n in sorted(phases.items()))
line = f"agents={agents} spent={total / 1e6:.2f}M ({parts})"
if stop and total >= 0.8 * stop:
    line = f"STOP: {line} has reached 80% of the {stop / 1e6:.2f}M stop line"
print(line)
