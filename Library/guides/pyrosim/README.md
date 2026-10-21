# The PyroSim guide is built from cases that were actually run

> **2026-09-13** · Peter · `current`
>
> A 7-day bilingual guide to PyroSim for the DATASET role, plus the ISO 9705
> reference case it teaches, the deliberately broken case Day 6 uses, two
> tested scripts that turn one room into a dataset, and the runs that produced
> every number the page quotes. PyroSim itself is Windows-only; the reference
> runs were made on this Mac with the same FDS 6.10.1 that PyroSim 2026.1
> bundles.

## Contents

- [What is here](#what-is-here)
- [The reference case is an ISO 9705 room with DATASET sensors](#the-reference-case-is-an-iso-9705-room-with-dataset-sensors)
- [The 20 cm run is complete; the 10 cm run is not](#the-20-cm-run-is-complete-the-10-cm-run-is-not)
- [Day 6 teaches from five faults that FDS does not object to](#day-6-teaches-from-five-faults-that-fds-does-not-object-to)
- [The two Day 7 scripts are tested](#the-two-day-7-scripts-are-tested)
- [Rebuilding the page](#rebuilding-the-page)
- [What this could not establish](#what-this-could-not-establish)

## What is here

| Path | What it is |
| --- | --- |
| `PyroSim_7Day_Guide.html` | The guide, English with a Hong Kong Cantonese toggle. Published privately at [https://claude.ai/code/artifact/b22eb9d9-f1a1-4fca-8adf-156b327629bb](https://claude.ai/code/artifact/b22eb9d9-f1a1-4fca-8adf-156b327629bb) |
| `site/` | The page's source: `page.html`, `parts/`, `style.css`, `app.js`, `build.py` |
| `cases/iso9705_room.fds` | The reference case, 10 cm cells, full 1200 s programme |
| `cases/iso9705_room_20cm.fds` | The same room on 20 cm cells; this is what produced the guide's numbers |
| `cases/day6_broken.fds` | Three faults, no error. The Day 6 exercise |
| `cases/iso9705_template.fds` | Placeholders only; filled by `tools/make_scenarios.py` |
| `tools/make_scenarios.py` | Renders valid room-fire variants plus a manifest |
| `tools/fds_to_dataset.py` | Turns `_devc.csv` into DATASET 5 s frames with a fuzzy hazard score |
| `tests/` | 32 pytest tests over both tools |
| `results/` | In the old workspace only: the runs, `make_charts.py`, and the charts the page inlines |

Run the tests from this directory:

```sh
uv run --no-project --with pytest python -m pytest tests -q
```

## The reference case is an ISO 9705 room with DATASET sensors

`fixed` · parses and runs under FDS 6.10.1

ISO 9705-1:2016 fixes the room at 3.6 × 2.4 × 2.4 m with a 0.8 × 2.0 m door and
a 170 mm propane sand burner in the corner opposite the door, held at 100 kW for
ten minutes and 300 kW for ten more. The case follows that, with three modelling
choices recorded in its own comments: the burner is drawn 0.2 × 0.2 m with its
top at 0.1 m, the nearest cell faces to the standard's 170 mm and 146 mm; the
lining is aerated concrete from NUREG-1805 Table 2-3, because the standard fixes
only density and thickness; and a second mesh extends 2.4 m beyond the door so
the doorway flow is not cut off by an open boundary, which the FDS User's Guide
recommends.

Sensors are placed for DATASET rather than for the standard: two zone nodes with
thermocouple, CO and optical density at the ceiling and visibility, FED, O₂ and
CO₂ at 1.85 m; a seven-bead corner tree; a doorway tree; layer height and layer
temperatures on one vertical line; a floor heat flux gauge; and doorway mass
flow in and out.

## The 20 cm run is complete; the 10 cm run is not

`partial` · the 10 cm case needs about a day and a half on this hardware

| Run | State | Cost |
| --- | --- | --- |
| `results/iso9705_room_20cm/` | complete, 1200 s | 8868 s wall clock, 2 MPI processes |
| `results/iso9705_room_10cm/` | stopped at 234 s | roughly 16× the 20 cm cost for a full run |

The first 10 cm attempt died with `ERROR(123): MPI exchange of pressure timed
out` while the machine was carrying both runs and a research fleet; the retry
raises `MPI_TIMEOUT` to 7200 s and reached 234 s before being stopped, which is
well past the 90 s the mesh-study chart is drawn over. NIST's FDS binaries for
macOS are x86-64 and run under Rosetta on this M1, without AVX, so these costs
are an upper bound and say nothing about the office desktop.

The 20 cm run reads cooler than measurements of a real ISO 9705 room — 147 °C at
the ceiling for 100 kW against Dillon's 305 °C, and 342 °C against 615 °C at
300 kW. Its D*/δx is 1.9 and 3.0, below the 3.8–14 range NIST used for its own
ISO 9705 validation. The guide states this rather than hiding it, and Day 6 is
built around the question.

## Day 6 teaches from five faults that FDS does not object to

`fixed` · every message reproduced on this machine

`results/day6/errors.json` records what each fault actually produced: the sealed
room appears only as a `Pressure Zone Information` line in the `.out` file; a
hole that misses the wall does the same and zeroes the doorway flow; a device
outside the mesh drops its column from the CSV with a console-only warning;
HRRPUA typed as total kilowatts gives 2.2 kW where the reference gives 52 kW;
and only a misspelt keyword stops FDS outright, with `ERROR(101)`.
`cases/day6_broken.fds` combines three of them in one file that runs to
completion with a single warning.

## The two Day 7 scripts are tested

`fixed` · 32 tests, standard library only

`make_scenarios.py` varies peak heat release, the t-squared growth class, the
burner's position and the door width, and refuses any variant whose geometry
falls off the cell grid, reaches through the front wall, or covers the floor
gauge or the layer-height line. Its template sets
`TEMPORAL_STATISTIC='INSTANT VALUE'` on every training channel, because FDS
otherwise averages each device over the output interval and the DATASET contract
decimates precisely so that nothing is averaged.

`fds_to_dataset.py` decimates device output to the 5 s frames that contract asks
for, refuses a series with a gap or one that does not start at ignition, rejects
non-finite readings rather than scoring them, converts CO from whichever of ppm,
`mol/mol` or `%` the file declares, and scores each frame with the project's
fuzzy index.

## Rebuilding the page

```sh
python results/make_charts.py          # charts from the run data
python site/build.py                   # assembles PyroSim_7Day_Guide.html
i18n extract PyroSim_7Day_Guide.html -o site/en.json
#   translate site/en.json -> site/zh.json
i18n inject  PyroSim_7Day_Guide.html --zh site/zh.json
i18n check   PyroSim_7Day_Guide.html
```

The build copies the case files and charts in at assembly time, so the page can
never show a case or a number that has drifted from the files that were run.
`i18n` keys are content hashes, so a rebuild keeps every translation whose
English did not change.

## What this could not establish

No PyroSim screenshot exists here, because PyroSim does not run on macOS; the
page marks each slot for the owner to fill from the office desktop. Several
interface details are flagged in the guide as needing one look at the real
screen. The independent verification pass over the research notes did not
complete — it failed on a session limit and then on authentication — so claims
were checked directly against runs and cited pages instead of by a second agent.
Aster did review the cases, the scripts and the arithmetic, and its seven
findings are recorded with their fixes in `_review/review-log.md`.

The reference numbers predate the `INSTANT VALUE` change, so they are means over
each one-second output interval rather than instantaneous samples.
