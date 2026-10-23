---
name: pyrosim
description: Use for PyroSim, FDS, Smokeview and introductory room-fire simulation questions. Consult the public 7-day guide, ISO 9705 cases, error table and standalone scenario/export tools; verify each installation and simulation locally.
---

# PyroSim prepares input and FDS computes the fire

PyroSim is a Windows editor that writes FDS input. Install and verify a
compatible solver locally. Never inherit device, licence or project readiness
from the guide's historical examples.

## The guide is an educational example with public source

Paths are relative to this Devarness checkout. Read
`Harness/guides/pyrosim/README.md` before using the guide.

| Path within `Harness/guides/pyrosim/` | Purpose |
| --- | --- |
| `PyroSim_7Day_Guide.html` | English and Hong Kong Cantonese teaching guide |
| `cases/iso9705_room.fds` | 10 cm ISO-room reference input |
| `cases/iso9705_room_20cm.fds` | 20 cm reference input |
| `cases/day6_broken.fds` | Deliberately broken Day 6 exercise |
| `cases/iso9705_template.fds` | Day 7 generator template |
| `tools/make_scenarios.py` | Validated seeded room-fire variants |
| `tools/fds_to_dataset.py` | Raw five-second sensor frames; no risk classifier |
| `tests/` | Synthetic exporter, generator and page-build checks |

Historical reference tables are illustrations, not a current run receipt.
Original logs and chart inputs are not distributed. Reproduce a measurement
from the public cases before citing it as evidence.

## Assistance follows the selected case and its actual output

1. Find the relevant day and keep menu names, keywords and paths in English
   in both languages.
2. Record the solver version, case inputs and actual output behind every
   numerical claim. Read warnings and the completion message; exit status
   alone does not establish that FDS completed successfully.
3. For errors, consult the guide's error table and the current `.out` file.
4. The educational exporter writes `temperature_c`, `optical_density` per
   metre and `co_ppm`, plus visibility and FED. It decimates to five-second
   intervals starting at ignition and validates gaps, finiteness and CO units.
   It requires no project-specific module and makes no safety classification.
5. Keep local results and licensed-software details outside the public source.
   State limits: one room and two sensor positions do not establish building
   transfer, evacuation performance or a fire-safety assessment.

## Commands require your own solver installation

```sh
cd Harness/guides/pyrosim
python tools/make_scenarios.py --n 6 --seed 7 --cell 0.2 --t-end 300 --out results/batch
# Run FDS with your verified installation before converting its output.
python tools/fds_to_dataset.py results/batch/room_000_devc.csv -o results/batch/room_000_frames.csv
python -m pytest tests -q -p no:cacheprovider
```

`Harness/bin/fds-setup` offers an explicit macOS install. On Windows, inspect
the FDS installation bundled with your licensed PyroSim. Never assume a
particular version, installation path, licence expiry or machine capacity.
