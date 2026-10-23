---
name: browser-docs
description: Use shared browser testing tools or local OCR for scanned PDFs, images and difficult document tables.
---

# Shared browser and OCR tools

Peter, Aster and May automatically use these tools when the task calls for
browser interaction or OCR. The start check only runs lightweight inventory
checks. Read `Harness/SHARED_BROWSER_DOCS.md` for installation and
verification details.
Paths are relative to this Devarness checkout. From its root, run
`python3 Harness/bin/<tool>` to select this checkout explicitly.
The installed `browser` and `ocr` commands work from any folder.

## Browser testing

Use `Harness/bin/browser --agent aster COMMAND` for Aster, `--agent peter`
for Peter or `--agent may` for May. Start with `--help`, then `open URL`,
`snapshot`, `click REF`, and `close`. Use `find TEXT` or scoped snapshots to
limit output. Keep each agent's
browser session separate. Test the actual task: for house pages, verify both
languages, the toggle, relevant interactions, responsive layout and console
errors. bilingual-page and diagram-design still own page creation and rendering
conventions. Use isolated browser state; attach to an existing personal browser
only when the task requires it. Close your own session after the task. Do not
run upstream global installs or broad session cleanup. Full CLI reference:
`Harness/playwright-cli/skills/playwright-cli/SKILL.md` (read on demand).

## Document conversion

Run `md-pages` first for PDFs and other supported binary documents, as required
by the dev router. If a scan yields little text or a table remains unusable,
use:

```sh
Harness/bin/ocr source.pdf -o extracted.md
Harness/bin/ocr scan.png -o extracted.md
```

The output must be a new file. Read the resulting page-marked Markdown and
verify consequential numbers/symbols against the page image. OCR is extraction,
not evidence that a schematic or numeric table was interpreted correctly. Models
run locally; first use may download model assets. See the shared guide for
verified languages and limitations. Never install dependencies on startup.
