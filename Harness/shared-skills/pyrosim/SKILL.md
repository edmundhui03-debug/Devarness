---
name: pyrosim
description: Use for any PyroSim, FDS (Fire Dynamics Simulator), Smokeview or room-fire simulation question — learning PyroSim, building or debugging a compartment fire model, reading FDS output, fixing an FDS error, or generating room-fire runs as DATASET training data. Points Peter, Aster and May at the 7-day guide, the verified ISO 9705 reference case, the error table, and the two tested Day 7 scripts, so every agent answers the way the guide does.
---

# PyroSim and FDS in dev

PyroSim is a Windows-only editor that writes FDS input; NIST's FDS
performs the simulation. Install and verify a compatible FDS version locally.
Write "an FDS simulation prepared in PyroSim" and rerun reference cases
before citing numerical results. No device or project readiness is inherited.

## Where everything is

Paths are relative to this Devarness checkout. From its root, run
`python3 Harness/bin/<tool>` to select this checkout explicitly.

The guide, cases, tools and tests are in `Harness/guides/pyrosim/`. The
reference runs (`results/`, with `summary.json`, the only source of the
guide's printed numbers) and the review log are history, not on this device:
for a number, rerun the case.

| Path in `Harness/guides/pyrosim/` | What |
| --- | --- |
| `PyroSim_7Day_Guide.html` | The bilingual guide: 7 days, error table, glossary, Ask Peter |
| `README.md` | The guide's record: the reference case, what was run, how to rebuild |
| `cases/iso9705_room.fds` | Reference ISO 9705 room, 10 cm cells, 100 kW then 300 kW |
| `cases/iso9705_template.fds` | Day 7 template; filled only by `make_scenarios.py` |
| `cases/day6_broken.fds` | The deliberately broken case for Day 6 |
| `tools/make_scenarios.py` | Valid t-squared room-fire variants plus `manifest.csv` |
| `tools/fds_to_dataset.py` | `_devc.csv` → DATASET 5 s frames and fuzzy risk level |
| `tests/` | The tools' tests |

## How to help

1. Find the owner's day in the guide and answer from it. Keep PyroSim menu
   names, FDS keywords and file names in English in both languages.
2. For a number, quote a rerun's `results/summary.json`, an FDS guide page
   or a cited source. Do not estimate a fire result from memory; run the case
   instead.
3. For an error, search the guide's error table first, then read the case's
   `.out` file: the last time-step block and any `ERROR` or `WARNING` line.
4. Day 7 output must follow the DATASET wire contract: per-zone
   `temperature_c`, `optical_density` per metre and `co_ppm`, one frame every
   5 s by decimation, t = 0 at ignition (the DATASET project's
   `dataset/forecast/schema.py:21`, once that project is in `Projects/`).
5. Say which machine produced a number: the guide's reference numbers came
   from the Mac's FDS, newer runs from the Windows PC.

## Commands

Git Bash on a Windows PC with PyroSim; `tests` passed 44 of 44 this way on
2026-10-06 (history, before dev).

```sh
export PATH="/c/Program Files/PyroSim 2026/fds:/c/Program Files/PyroSim 2026/fds/mpi:$PATH"
export OMP_NUM_THREADS=1
fds case.fds                          # one mesh; results land beside the file
mpiexec -n 4 fds case.fds             # one MPI process per mesh
cd Harness/guides/pyrosim             # results/ is not part of dev: point --out outside it
python3 tools/make_scenarios.py --n 6 --seed 7 --cell 0.2 --t-end 300 --out results/batch
python3 tools/fds_to_dataset.py results/batch/room_000_devc.csv -o results/batch/room_000_frames.csv
uv run --no-project --with pytest python -m pytest tests -q
```

`Harness/bin/fds-setup` installs FDS on macOS only; on Windows use the FDS
that PyroSim bundles.

## On the Windows PC

Verified on the owner's PyroSim PC on 2026-09-15. Evidence (history, not on
this device): the records named below are files of the DATASET_AI project's
pilot evidence and of its AC1 fire01 run, which are not in dev.

| Fact | Record |
| --- | --- |
| PyroSim and Pathfinder 2026.2.0715 are installed; their licences end on 24 Nov 2026 | `01-machine-software`, `01-machine-licences` |
| FDS `FDS-6.10.1-0-g12efa16-release` and Smokeview 6.10.1 ship in `C:\Program Files\PyroSim 2026\fds\`; run `fds.exe` with that folder and its `mpi\` subfolder on `PATH` and `OMP_NUM_THREADS=1` | `01-solver-fds-version` |
| Ten 600 s room fires on 20 cm cells took 21.5 min with eight FDS processes, median 44.6 ms per step | `06-pilot-queue`, `08-pilot-acceptance` |
| `PyroSim.exe case.fds` does not open an FDS input ("Could not open … The file may be corrupt"); use File, Import FDS/CAD File, and choose FDS6 | `12b`, `12c`, `12j` |
| The import moves `CONVERSION_FACTOR` and `UNITS` on gas devices into Additional Fields, one warning per device | `12t` |
| `PyroSimResultsConsole.exe -screenshot -ssname out.png -sstime 300 case.smv` renders without a window and accepts a raw `.smv` | `06d`, `11b` |
| A Smokeview script needs a relative `RENDERDIR`: an absolute one crashed 6.10.1. A `VISIBILITY` slice loads as `QUANTITY='SOOT VISIBILITY'` | `10b`, `10c` |
| FDS 6.10.1 crashed with heap corruption (`c0000374`, no `.out` written) on OBST lying wholly below the mesh floor, against its boundary, such as the storey's own slab under a one-storey mesh: drop them. Thin walls lying in a mesh split gave `ERROR(873)`: snap every OBST to the grid first and give a zero-thick box one cell | AC1 fire01, 2026-10-06: `build_case.py` |
| DEVC output is the average over the preceding `DT_DEVC` by default (FDS UG PDF p.320). A smoke detector's own, instantaneous activation time is in `CHID_devc_ctrl_log.csv`: take Smoke from that log, or set `TIME_AVERAGED=F` | AC1 fire01: `make_record.py` |
| A `REAC` on a `FORMULA` fuel with no `HEAT_OF_COMBUSTION` makes FDS derive one from `EPUMO2`: 24,550 kJ/kg for the UG polyurethane, whose UG example (PDF p.224-225) sets 26,200 | AC1 fire01: `AC1_4F_fire01.out`, line 387 |
| PyroSim is a Java app: UI Automation sees none of its menus, and keystrokes fail once the terminal takes the foreground back between calls. Mouse clicks sent in one process, each only while PyroSim owns the clicked screen point, drove Import, Save As and reopen. `PrintWindow` captures PyroSim even behind other windows. `PyroSim.exe file.psm` does open a `.psm` | AC1 fire01: `psdrive.py`, `shots/psm/` |
| Eight FDS ranks on a 1.7 M-cell case hold about 8 GB; with a 4 GB memory daemon also running, the 16 GB PC paged at 12-21k pages/s and FDS idled. Pausing the daemon for the run, on the owner's word, made FDS about 3x faster | AC1 fire01: `report/while_it_ran.json` |

## Every simulation report is named PRS and laid out like the pilot page

The owner's rule, 2026-09-15, for Peter and Aster.

**Name.** `DDMMYYYY_PRS_Running.html`: the Hong Kong date the runs finished,
`PRS` for PyroSim, and `Running` for a simulation-run report. A second report
that finishes on the same day adds `_2`, a third `_3`. The first is
`15092026_PRS_Running.html` (history, not on this device).

**Layout.** That first report is the template and is never edited. A new report
keeps these sections in this order:

| # | Section | Holds |
| --- | --- | --- |
| 1 | Verdict | the headline claim and numbers: runs, checks passed, wall time per run, time per step, queue time |
| 2 | What ran, in order | every command as a record: exit code, clock time, duration, output, SHA-256 of the full output |
| 3 | This machine | computer, processor, memory, free disk, OS, PyroSim and Pathfinder with licences, FDS, Smokeview, Python |
| 4 | Acceptance | each automated check as PASS or FAIL; a check that needs the owner stays OPEN |
| 5 | The runs | one table row per run |
| 6 | One section per featured run | heat release, temperature, visibility, CO, people and DATASET risk charts, each with a table view, then PyroSim Results and Smokeview screens |
| 7 | PyroSim | how PyroSim opened the case, with its screens and warnings |
| 8 | Coverage | what the runs cover of the full manifest |
| 9 | While it ran | the queue window and the processes during the run |
| 10 | Known gaps | what the report cannot tell |
| 11 | Reproduce | the commands that rebuild the runs, the checks and the page |

**File.** One self-contained HTML file that loads nothing from the network, in
English with the Hong Kong Cantonese toggle, passing `i18n check`, with its
`<meta charset>` in the first 1,024 bytes and LF line endings. The verdict says
that FDS computed the fires and PyroSim only prepared or opened them. On the
Windows PC the page is built in the DATASET_AI project with
`python -m page.build`, `i18n inject` and `python -m page.charset`, then
saved in that project's reports folder under the name above and given a row
in that folder's README.
