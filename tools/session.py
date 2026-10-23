#!/usr/bin/env python3
"""Current-checkout startup and offline prompt guidance for all clients."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

from bootstrap import readiness

ROOT = Path(__file__).resolve().parents[1]
GUIDANCE = ('Follow CLAUDE.md. grill-first: ask open decisions together; an instruction to just do it ends the interview. '
            'karpathy-guidelines: use TieItUp with Ponytail first, concrete verification and a final review. '
            'Use library discovery locally. retro-last: finish with one bounded retrospective. '
            'Credentials, notifications, paid probes and external discovery require explicit local setup.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--text', action='store_true')
    parser.add_argument('--hook', action='store_true')
    parser.add_argument('--prompt-hook', action='store_true')
    args = parser.parse_args()
    if args.prompt_hook:
        event = json.load(sys.stdin)
        context = GUIDANCE
        index_path = ROOT / '.claude/hooks/library/index.json'
        if index_path.is_file():
            spec = importlib.util.spec_from_file_location('devarness_library', ROOT / 'Harness/library.py')
            library = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(library)
            try:
                index, warnings = library._usable_index(index_path)
                picks = library.pick(index, str(event.get('prompt', ''))[:2000], '.', 3)
                context += '\n' + '\n'.join(warnings)
                context += '\n' + '\n'.join(p['entry']['id'] + ' - ' + p['entry']['path'] for p in picks)
            except library.CliError:
                context += '\nLocal catalogue unavailable; run python3 Harness/bin/library refresh.'
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'UserPromptSubmit',
                                                'additionalContext': context}}))
        return 0
    state = readiness()
    summary = ('START COMPLETE — READY: Devarness core' if state['core_ready'] else
               'START FAILED: ' + ', '.join(state['missing']))
    optional = ('Optional upstream source checkouts present: %d/%d; runtime readiness is separate.' %
                (state['optional_sources_present'], state['optional_sources_total']))
    if args.hook:
        print(json.dumps({'systemMessage': summary,
                          'hookSpecificOutput': {'hookEventName': 'SessionStart',
                              'additionalContext': summary + '\n' + optional + '\n' + GUIDANCE}}))
    else:
        print(summary + '\n' + optional)
    return 0 if state['core_ready'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
