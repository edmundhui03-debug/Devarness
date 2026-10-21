---
name: bilingual-page
description: Build an HTML page in the dev workspace. Use whenever writing, publishing or updating any .html in dev — a report, review, spec, manual or dashboard. Every house page must carry the English/Cantonese toggle and the house tokens; this gives you the template, the i18n commands, and the rules for diagrams that survive translation.
---

# House pages

Every HTML page in this workspace is bilingual: English by default, Hong Kong
Cantonese on a toggle. That is a house rule, not a per-request feature. A page
shipped English-only is unfinished.

Paths are relative to this Devarness checkout. From its root, run
`bash Library/bin/i18n` to select this checkout explicitly. Windows uses
Git Bash. The launcher needs Python with Beautiful Soup installed; set
`DEVARNESS_I18N_PYTHON` to that interpreter's executable path when needed.

Before authoring or revising any page, read the Archify adapter at
`.claude/skills/archify/SKILL.md`. Decide whether a technical diagram adds
clarity; apply its review criteria to the whole page either way.

## The four steps

```bash
cp "Library/templates/bilingual-page.html" mypage.html
# ...write the page in English...
bash Library/bin/i18n extract mypage.html -o mypage.en.json
# ...translate mypage.en.json -> mypage.zh.json...
bash Library/bin/i18n inject mypage.html --zh mypage.zh.json
bash Library/bin/i18n check mypage.html        # must say full coverage
```

`i18n check` exits non-zero when anything is untranslated or the toggle is
missing. Run it before you call the page done, and before publishing. After
changing `Library/bin/i18n` itself, run `i18n selftest`: it builds a good
page and one page per defect, and fails if `check` stops catching any of them.

## Rules that matter

**Write English first, translate second.** Do not compose bilingually. The
extractor assigns stable content-hashed keys, so editing English later and
re-running `extract` only adds the new strings — existing translations survive.

**Never hand-write `data-i18n` keys.** They are generated. Hand-written keys
collide and break the round trip.

**Keep tags identical across languages.** `Some <b>bold</b> text` must stay
`<b>`-wrapped in Chinese. `i18n check` does not catch this; a careless
translation silently loses emphasis.

**Keep these English, in both languages:** KiCad, Altium, PCB, Gerber, BOM, DRC,
ERC, footprint, netlist, stackup, via, and every tool name, path, command and
number. Hong Kong engineers say these in English; a Chinese calque makes the
page harder to read, not easier. Gloss a term once on first use —
`footprint（封裝）` — then use the English alone.

**Cantonese means Hong Kong written Chinese**, Traditional, professional
register. Not Mainland Simplified phrasing, not stiff translationese, not
transcribed speech. Prefer 用 over 使用, 要 over 需要, 做 over 進行.

**After `inject`, move `<meta charset="utf-8">` back to the first line.**
`i18n inject` prepends its own `<style id="i18n-css">` block, which pushes
the charset declaration down — on 2026-09-18 it landed at byte 1357, past the
1024 bytes a browser reads when sniffing the encoding. The page then renders as
Latin-1: every em dash becomes `â€"` and the 中文 button becomes `ä¸­æ–‡`.
`i18n check` still reports full coverage, because coverage is not encoding.
Confirm with `document.characterSet` in a browser, not by eye.

**After every `inject`, put the doctype back too.** `extract` rewrites the
head as `<!DOCTYPE html>` and `<meta charset="utf-8"/>`, and `inject` puts its
style and toggle in front of them, so the doctype ends up stranded after the
toggle's `</div>`, mid-page, and the charset near line 20. It happens on a new
page (the old workspace's update page, 2026-10-07) as on a re-injected one
(its sync page, 2026-09-29); both are history, not on this device. Restore
the page's own first lines, `<!doctype html>` then `<meta charset="utf-8">`,
remove the stranded copies, and diff the result against the page before
`inject`: only the strings and the dictionary should differ.

**A value the page computes must not live inside a translated string.** The
toggle replaces a tagged element's `innerHTML`, so any `<b id="...">` inside it
is destroyed and recreated, and cached JavaScript references go stale. Look
elements up on every write, redraw on `window.load` (i18n applies its
dictionary after inline scripts run), and redraw again after a toggle click.

## Diagrams

A picture earns its place when it shows a mechanism words would take a paragraph
to describe. Draw it as **inline SVG** using the house tokens (`var(--ink)`,
`var(--line)`, `var(--copper)`), never as an external image:

- External images are blocked by the artifact CSP and will silently not load.
- Token colours keep the diagram correct in both light and dark themes.
- Put **every label in its own `<text>` element** so `i18n` can translate it.
  A label baked into a single multi-line string cannot be translated.

Mermaid also renders natively in artifacts via a `<pre class="mermaid">` block,
but its labels do not translate. Use it only for a diagram whose labels are code
identifiers.

## Publishing

Publish with the Artifact tool once `i18n check` passes, and save a copy
beside the source it documents. Record the artifact URL in the document it
belongs to, so the page can be updated in place later instead of forked.

## Where things are

| Thing | Path |
| --- | --- |
| Template | `Library/templates/bilingual-page.html` |
| Tool | `bash Library/bin/i18n`; no global launcher required |
| Worked example | `Library/guides/pyrosim/PyroSim_7Day_Guide.html` |
