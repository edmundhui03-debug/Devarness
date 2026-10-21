# The brand is black and white on grey, with one orange for a waiting question

> **2026-10-09** · Peter · `current`
>
> The look of the new dev dashboard app, laid out like Jira: a grey canvas,
> white cards with soft corners, black as the only emphasis, and one orange
> kept for a question that waits. The tokens live in
> `Library/dashboard/app/src/theme.css`; this file records them, so change
> both together. The prototype `index.html` keeps its own square black and
> white until wave 6 retires it.

## Contents

- [Grey, white and black colour everything; orange marks a waiting question](#grey-white-and-black-colour-everything-orange-marks-a-waiting-question)
- [Type is the system face, small and tight](#type-is-the-system-face-small-and-tight)
- [Shape follows Jira: a top bar, a project sidebar, columns of cards](#shape-follows-jira-a-top-bar-a-project-sidebar-columns-of-cards)
- [Changing the look keeps the black, the white and the one orange](#changing-the-look-keeps-the-black-the-white-and-the-one-orange)

## Grey, white and black colour everything; orange marks a waiting question

`fixed` · the owner, 2026-10-09: "Jira like and in black and white style",
after the Crisply dashboard shot and the Jira mockup

Light and dark follow the system and can be forced from the top bar. Every
colour in the app is one of these tokens; a new colour is a change to this
file first.

| Token | Light | Dark | Used for |
| --- | --- | --- | --- |
| `--canvas` | `#f1f1f4` | `#0a0a0a` | The page behind everything |
| `--card` | `#ffffff` | `#1c1c1c` | Cards, the top bar, the sidebar, the side panel |
| `--col` | `#e9e9ee` | `#141414` | Board columns; a selected sidebar row |
| `--soft` | `#f5f5f7` | `#262626` | Hover, labels, chips |
| `--ink` | `#0a0a0a` | `#f2f2f2` | Text; the only emphasis: the current page, the main button, a working agent, a selected card, a selected sidebar row's left bar |
| `--muted` | `#5f5f69` | `#a6a6a6` | Keys, times, paths, column titles |
| `--line` | `#e2e2e8` | `#2f2f2f` | Hairlines between parts |
| `--accent` | `#c8370a` | `#ff6a33` | Only a question that waits |
| `--accent-fg` | `#ffffff` | `#0a0a0a` | Text on an accent fill |
| `--accent-soft` | `#fbe9e2` | `#2b1308` | The open-question chip behind ink text |

Contrast, computed from these values: ink on a card 19.8 to 1 (light) and
15.2 (dark); ink on the canvas 17.6 and 17.7; muted text on a card 6.3 and
7.0, on a column 5.2 and 7.6; text on the accent 5.2 and 6.9; ink on the
soft accent 16.8 and 15.6. Lines are decoration, so nothing relies on them
alone.

**The orange has six places and no others:** the bell's count, a waiting
agent's dot, the count beside an agent in the sidebar, the left edge of a
waiting card on the board, the left edge of an open question in a panel, and
the open-question chip's border (`app/src/theme.css:51`, `:69`, `:70`,
`:106`, `:151`, `:123`). If anything else is orange, it is a mistake.

## Type is the system face, small and tight

`fixed`

Nothing is downloaded: the stack is the system face with Hong Kong Chinese
faces last (`system-ui`, Segoe UI, Roboto, Noto Sans HK, Microsoft
JhengHei), at 14 px with a 1.45 line height.

| Role | Size and weight |
| --- | --- |
| Page title | 1.4 rem, 750, tracking -0.01 em |
| The logo | 1.05 rem, 800 |
| Detail panel title | 1.05 rem |
| Question text | 0.95 rem, 600 |
| Card title | 0.86 rem, 600, two lines at most |
| Buttons, pills, view tabs | 0.82 rem, 600 |
| Breadcrumbs, lead, fields | 0.8 to 0.85 rem |
| Keys, labels, chips | 0.68 to 0.78 rem, 600 to 700 |
| Group and column titles | 0.68 to 0.72 rem, 700, upper case, tracking 0.06 em |

## Shape follows Jira: a top bar, a project sidebar, columns of cards

`fixed`

- A 52 px top bar: the logo, the page links, the questions bell, the language
  and theme switches.
- A 236 px project sidebar: the workspace, the pages, then the agents with
  their live dots (filled when working, orange when a question waits,
  hollow when idle); the selected agent has a 2 px ink bar on its left edge.
- The page: breadcrumbs, the title, view tabs (Board, List) with a 2 px ink
  underline on the current one, then a toolbar of search and filter pills.
- The board: columns at least 240 px wide on `--col` with 10 px corners,
  scrolling sideways inside the board, never the page; white cards with 8 px
  corners, a hairline, a 1 px shadow, and a 3 px orange left edge when a
  question waits; a selected card has a 2 px ink border.
- The side panel opens a card in place: beside the board from 1680 px, a
  drawer over it below that, full width on a phone.
- Focus is a 2 px ink outline 3 px off the element; a disabled control drops
  to half opacity.
- At 760 px and below the sidebar sits behind a menu button and the columns
  stack; nothing scrolls sideways at 375 px.

## Changing the look keeps the black, the white and the one orange

`fixed`

Change a token in `app/src/theme.css`, in the light block and both dark
blocks, then update the table above in the same edit, with its contrast
recomputed. Keep text at 4.5 to 1 or better, keep the orange for a question
that waits, and keep every new visible word in English and Hong Kong
Cantonese (see [`AGENTS.md`](AGENTS.md)).
