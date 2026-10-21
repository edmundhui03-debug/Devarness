---
name: archify
description: Review every new or edited house HTML page for diagram suitability and visual quality; create validated architecture, workflow, sequence, data-flow and lifecycle diagrams through pinned Archify.
---

# Archify improves technical diagrams within house pages

Paths are relative to this Devarness checkout. From its root, run
`python3 Library/bin/<tool>` to select this checkout explicitly.

Read `Library/ARCHIFY.md` for the installation, bilingual integration and
acceptance contract. This adapter applies to every new or edited house HTML
page, including reports without a diagram: first decide whether a diagram
clarifies a mechanism. Record that decision in the task evidence, not as a badge
on the reader's page.

## Choose the renderer from the information being explained

- For architecture, workflow, sequence, data-flow or lifecycle diagrams, read
  `Library/archify/archify/SKILL.md`, one matching schema and one example.
- For other diagram types, use diagram-design and its house profile.
- For prose, tables and plots, improve hierarchy, spacing, contrast, source
  traceability and responsive behavior without forcing a diagram into the page.

Use `python3 Library/bin/archify` instead of upstream's bare Node invocation. It
preserves the pin and disables optional update networking. `bilingual-page` owns
all HTML shells, house branding and English/Hong Kong Cantonese completion. The
router overrides overlapping upstream defaults; vendored code stays intact.

## Separate three kinds of acceptance

1. Source/schema and deterministic delivery: upstream `validate` and `deliver`.
2. Final page: translation coverage and browser behavior after integration.
3. Perceptual review: inspect screenshots of the actual final page in both
   languages; an automated geometry pass does not grade visual clarity.

The upstream interactive viewer has no complete Cantonese localization yet.
For bilingual delivery use validated static SVG inside a house page, translate
its labels with i18n, and test the final page separately. Keep raw upstream
HTML outside published deliverables as build evidence. Preserve source JSON and
receipts so a later edit can be reproduced. Never call a modified wrapper's
hash the upstream-validated HTML hash.

For existing pages, review in batches, preserve evidence and interactions,
and leave vendor files untouched; the old workspace's page audit did not come
to dev.
