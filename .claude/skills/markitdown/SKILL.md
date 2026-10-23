---
name: markitdown
description: Convert a PDF, Office file, spreadsheet, EPub or ZIP into Markdown before reading it. Use whenever a task needs the text or tables out of a binary document — datasheets, research papers, BOMs, decks. Use md-pages instead when a finding will cite a page number. Not for images or audio, and not for files that are already text.
---

# markitdown

Two optional commands, available after local setup. Neither is an MCP server.

| Command | Gives you | Reach for it when |
| --- | --- | --- |
| `markitdown` | one flat Markdown stream, best table fidelity | you want the content and page numbers do not matter |
| `md-pages` | `=====PAGE N=====` markers, plus tables | a finding will cite a page — datasheets, papers, anything reviewed |

Verify the selected command and its dependencies in the current checkout.

## Choosing between them

`md-pages` is the default for anything that will be reviewed or quoted. A
datasheet claim nobody can locate is not evidence, and the review convention in
this workspace is already `=====PAGE N=====`.

Use plain `markitdown` when you want tables and do not need pages. The
extractors can recover different content; compare them on the actual input
when an important table looks incomplete or mangled.

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

A project can keep datasheets in `datasheets/` and their extracted text in
`datasheets/text/`, outside the public reusable harness:

```bash
md-pages datasheets/*.pdf --outdir datasheets/text/
```

Check page counts, markers and important tables against the source document.
An extracted file does not establish that another tool's PDF dependency is
installed or interchangeable.

## Optional backends need their own setup

Azure Document Intelligence, LLM image descriptions and OCR plugins have
their own dependencies and may require credentials. Check their configuration
and permissions before offering them; source presence is not readiness.

## Source and upgrades

The optional upstream clone belongs at `Harness/markitdown/`; keep it
unmodified. If installed as an isolated uv tool, upgrade it with
`uv tool upgrade markitdown`. The local page-marked adapter is
`Harness/bin/md-pages`; no pre-existing home-folder launcher is required.
