# The PyroSim guide teaches a reproducible public sensor-data exercise

> **2026-10-23** · Aster · `current`
>
> This introductory bilingual guide includes an ISO 9705 room, a deliberately
> broken exercise, a scenario generator and a standalone raw-frame exporter.
> It requires no private research module. Reference tables are historical
> illustrations; rerun the public cases before using their numbers as evidence.

## The public case and tools form a small educational example

| Path | Purpose |
| --- | --- |
| `PyroSim_7Day_Guide.html` | English and Hong Kong Cantonese guide |
| `site/` | Page source, translations and build script |
| `cases/iso9705_room.fds` | 10 cm ISO-room reference input |
| `cases/iso9705_room_20cm.fds` | 20 cm reference input |
| `cases/day6_broken.fds` | Deliberately broken exercise |
| `cases/iso9705_template.fds` | Validated scenario-generator template |
| `tools/make_scenarios.py` | Seeded room-fire variants and manifest |
| `tools/fds_to_dataset.py` | Raw five-second sensor-frame CSV exporter |
| `tests/` | Exporter, scenario and clean-source-build checks |

The room is 3.6 × 2.4 × 2.4 m with a 0.8 × 2.0 m doorway. Modelling choices
and scientific references are recorded in `cases/iso9705_room.fds:1` and the
page's Sources section. S1 and S2 are teaching sensor positions in one room,
not an instrument layout prescribed by ISO 9705.

Historical tables retain a 1200 s reference run on 20 cm cells. The 10 cm
run was partial, reaching 234 s. Original logs and chart inputs are not
included, so rebuilding displays an explicit note at each missing plot.
The historical device values are one-second means; the current public cases
request instantaneous sensor output. No current simulation validation is
inherited from those historical measurements.

## The exporter writes measurements without assigning safety labels

From this directory, after installing pytest in your chosen environment:

```sh
python -m pytest tests -q -p no:cacheprovider
python tools/make_scenarios.py --n 6 --seed 7 --cell 0.2 --t-end 300 --out results/batch
python tools/fds_to_dataset.py results/batch/room_000_devc.csv -o results/batch/room_000_frames.csv
```

Run FDS on the generated cases before converting their output. The tools
use the standard library; tests require pytest. No FDS run occurs during
the Python tests.

Each CSV frame contains `time_s`, `zone`, `temperature_c`, `optical_density`
per metre, `co_ppm`, `visibility_m` and `fed`. The exporter selects the raw
reading nearest each five-second mark, beginning at ignition, and rejects
gaps or non-finite readings. CO units may be ppm, mol/mol or %; unknown
units are rejected. FED remains an accumulated measurement, not a risk
classification. This is teaching code, not a fire-safety assessment.

## A clean checkout builds the page without private run folders

From the repository root:

```sh
python Harness/guides/pyrosim/site/build.py
bash Harness/bin/i18n extract Harness/guides/pyrosim/PyroSim_7Day_Guide.html -o Harness/guides/pyrosim/site/en.json
# Translate changed English fragments into site/zh.json.
bash Harness/bin/i18n inject Harness/guides/pyrosim/PyroSim_7Day_Guide.html --zh Harness/guides/pyrosim/site/zh.json
bash Harness/bin/i18n check Harness/guides/pyrosim/PyroSim_7Day_Guide.html
```

Set `DEVARNESS_I18N_PYTHON` to an interpreter with Beautiful Soup when
needed. After injection, keep the doctype first and the UTF-8 charset within
the first 1024 bytes. Verify both languages and page behavior before sharing.

## Current installation and simulation results require fresh evidence

PyroSim is a Windows editor; FDS performs the simulation. Verify the solver
version and each run's completion message locally. Screenshots in the guide
are placeholders. Source cleanup and synthetic tests do not establish a
licensed installation, an FDS run, mesh convergence or a scientific result.
