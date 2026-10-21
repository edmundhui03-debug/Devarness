#!/usr/bin/env python3
"""briefs — print the full prompt of each agent launch whose description has a word.

usage: python3 .claude/skills/delegate/briefs.py <session transcript .jsonl> WORD [WORD ...]

A session that dies mid-run still has its transcript under
~/.claude/projects/<project>/, and every Agent call in it carries the brief.
This is how batch H's brief was recovered on 2026-09-25.
"""
import json
import sys

path, words = sys.argv[1], sys.argv[2:]
sys.stdout.reconfigure(encoding="utf-8")
for line in open(path, encoding="utf-8"):
    if '"Agent"' not in line:
        continue
    record = json.loads(line)
    for block in (record.get("message") or {}).get("content") or []:
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Agent":
            description = block["input"].get("description", "")
            if any(w.lower() in description.lower() for w in words):
                print("=====", record.get("timestamp", "")[:19], description)
                print(block["input"].get("prompt", ""))
