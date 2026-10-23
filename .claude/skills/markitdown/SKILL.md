---
name: markitdown
description: Convert a PDF, Office file, spreadsheet, EPub or ZIP into Markdown before reading it. Use whenever a task needs the text or tables out of a binary document — datasheets, research papers, BOMs, decks. Use md-pages instead when a finding will cite a page number. Not for images or audio, and not for files that are already text.
---

# markitdown

Two commands, both on `PATH`, both free until called. Neither is an MCP server.

| Command | Gives you | Reach for it when |
| --- | --- | --- |
| `markitdown` | one flat Markdown stream, best table fidelity | you want the content and page numbers do not matter |
| `md-pages` | `=====PAGE N=====` markers, plus tables | a finding will cite a page — datasheets, papers, anything reviewed |

Measured on this workspace: a 5-page datasheet takes 1.8 s, a 31-page TI
datasheet 3.6 s, a research paper 5.2 s, a spreadsheet 2.2 s.

## Choosing between them

`md-pages` is the default for anything that will be reviewed or quoted. A
datasheet claim nobody can locate is not evidence, and the review convention in
this workspace is already `=====PAGE N=====`.

Use plain `markitdown` when you want every table and do not need pages. On the
same 31-page datasheet it recovered 299 table rows against `md-pages`'s 170,
because it runs a different extractor. If a table matters and looks mangled, try
the other command before concluding the table is unreadable.

## Use

```bash
md-pages datasheet.pdf                        # to stdout, page-marked
md-pages datasheet.pdf -o notes.md            # to a file
md-pages datasheets/*.pdf --outdir text/      # one .md per input, named after it
markitdown deck.pptx                          # flat, no pages
markitdown sheet.xlsx                         # tables straight out
```

Convert to a file and read that when the document is long. Piping a 30-page
datasheet into the conversation spends context you cannot get back.

`md-pages` passes anything that is not a PDF straight to `markitdown`, so it is
safe to use on a mixed folder. It prints the output path per file and warns on
stderr when a file yields under 20 words.

## What does not work, and what to do instead

**Images need the local OCR fallback.** Use `ocr scan.png -o extracted.md`;
read the shared `browser-docs` skill. Verify consequential content visually.

**Scanned PDFs come back nearly empty** with md-pages. Use `ocr scan.pdf -o
extracted.md` and inspect page images when OCR is uncertain.

**Subscripts and superscripts scatter.** `R_DS(ON)` arrives as `R` and `DS(ON)`
on separate lines. This is inherent to PDF text extraction and affects both
commands. Read around it; do not report it as a broken file.

**Headers, footers and page numbers survive** as ordinary lines. Do not quote
them as content.

## The datasheet workflow

This is the main use here. The Emergency Button review keeps datasheets in
`datasheets/` and their text in `datasheets/text/`:

```bash
md-pages datasheets/*.pdf --outdir datasheets/text/
```

Verified to reproduce the existing convention exactly — same page count, same
markers, on the same files the earlier pipeline handled. It replaces
`pdftotext`, which several kicad-happy scripts want but which was never
installed here.

## Options this workspace does not have

Azure Document Intelligence, LLM image descriptions, and the `markitdown-ocr`
plugin all need credentials that are not configured. Do not offer them as if
they were available.

## Source and upgrades

Pristine clone at `Harness/markitdown/`, never edited. The command is an
isolated uv tool: `uv tool upgrade markitdown`. `md-pages` is ours, at
`Harness/bin/md-pages`, symlinked into `~/.local/bin`.
