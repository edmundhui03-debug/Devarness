# The title is a sentence that says what this document concludes

> **2026-09-11** · Peter · `current`
>
> This blockquote is the header block and every dev document carries one. The
> first line is the date, the agent who wrote it, and whether the document is
> still true. The rest is two to four sentences saying what the document
> concludes — not what it covers. Someone who reads only this should know the
> answer and whether it still applies.

Replace everything below. The shape is the point: a claim as a heading, its
state on the first line, then the evidence.

## A heading states a claim, not a category

`open` · one line for where this stands and what it still needs

"The 0.2 mm vias are a regression" tells the reader something. "Findings" does
not. Write headings that survive being read on their own, because that is how a
document gets skimmed.

The status line is optional and belongs only on a section that has a state. It
is the first line under the heading, always, so the states of a long document
line up down the left edge where they can be seen at a glance — and found from
anywhere with `md-format status`. Use `open`, `fixed`, `blocked`, `partial` or
`needs-owner`.

Prose wraps at 80 columns. Tables, code and links do not have to.

## Cite what you checked

Point at the repository with `path/to/file.md:42`. It is clickable in Claude
Code, greppable everywhere else, and it lets the owner audit a claim without
asking. External facts get a link; files get a hash where the bytes matter.

| What | Where | State |
| --- | --- | --- |
| Keep tables narrow enough to read | `Harness/templates/markdown-doc.md` | `fixed` |
| Give every column a header | — | `fixed` |

## Warn once, if at all

> [!WARNING]
> One alert per document, saved for the single thing that blocks. A document
> with three warnings has none.

## What this could not establish

Say what you did not do, and what would settle it. A document that lists only
what worked is not evidence, and the next agent will not know where the edge
was.

Run `python3 Harness/bin/md-format check FILE` before calling it done.
