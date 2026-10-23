"""Render room-fire variants of the ISO 9705 reference case for DATASET.

Each scenario changes four things a real room fire changes: how big the fire
gets (peak HRR), how fast it grows (a t-squared class), where it is (burner
corner position) and how wide the door is. Everything is snapped to the mesh
so obstructions land on cell faces, and a burner may not sit on the floor heat
flux gauge or under the layer-height line, which would corrupt those readings.

    python make_scenarios.py --template ../cases/iso9705_template.fds \
        --n 6 --seed 7 --cell 0.2 --t-end 300 --out ../results/batch

Writes one .fds per scenario plus manifest.csv. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path

ROOM_X, ROOM_Y = 3.6, 2.4            # interior plan, metres; the front wall starts at x = 3.6
DOOR_HEIGHT, DOOR_CENTRE_Y = 2.0, 1.2
HRRPUA_TARGET = 1000.0               # kW/m2; sizes the burner so bigger fires are wider, not hotter
BURNER_HEIGHT = 0.3
# t-squared growth coefficients, kW/s2 (slow 600 s, medium 300 s, fast 150 s,
# ultrafast 75 s to reach 1055 kW).
ALPHA = {"slow": 0.00293, "medium": 0.01172, "fast": 0.0469, "ultrafast": 0.1876}
PEAKS_KW = (100.0, 200.0, 300.0, 500.0, 750.0, 1000.0)
# Plan positions of line/floor devices a burner must not cover.
PROTECTED_POINTS = {"floor heat flux gauge": (1.85, 1.25), "layer-height line": (3.25, 2.15)}
# Coordinates are written to one decimal, which is exact at 0.1 and 0.2 m and
# silently wrong below it: at 0.05 m a 100 kW burner rendered as 73 kW because
# its edges moved. The API refuses what the CLI already refuses.
CELLS = (0.1, 0.2)


@dataclass(frozen=True)
class Scenario:
    chid: str
    peak_kw: float
    growth: str
    burner_x0: float
    burner_y0: float
    door_width: float


def on_grid(value: float, cell: float) -> bool:
    return abs(value / cell - round(value / cell)) < 1e-6


def snap(value: float, cell: float) -> float:
    return round(round(value / cell) * cell, 6)


def burner_side(peak_kw: float, cell: float = 0.1) -> float:
    side = math.sqrt(peak_kw / HRRPUA_TARGET)
    return round(max(2 * cell, math.ceil(side / cell - 1e-9) * cell), 6)


def tau_seconds(peak_kw: float, growth: str) -> float:
    return math.sqrt(peak_kw / ALPHA[growth])


def validate(s: Scenario, cell: float = 0.1) -> list[str]:
    if cell not in CELLS:
        raise ValueError(f"unsupported cell size {cell} m; this template is written for {CELLS}")
    problems = []
    if s.growth not in ALPHA:
        problems.append(f"unknown growth class {s.growth!r}")
        return problems
    if not 50.0 <= s.peak_kw <= 2000.0:
        problems.append(f"peak {s.peak_kw} kW is outside 50-2000 kW")
    side = burner_side(s.peak_kw, cell)
    x1, y1 = s.burner_x0 + side, s.burner_y0 + side
    if not (on_grid(s.burner_x0, cell) and on_grid(s.burner_y0, cell)):
        problems.append(f"burner corner ({s.burner_x0}, {s.burner_y0}) is off the {cell} m grid")
    if s.burner_x0 < -1e-9 or s.burner_y0 < -1e-9 or y1 > ROOM_Y + 1e-9:
        problems.append("burner extends outside the room")
    if x1 > ROOM_X + 1e-9:
        problems.append("burner extends through the front wall")
    for name, (px, py) in PROTECTED_POINTS.items():
        cx0, cy0 = math.floor(px / cell) * cell, math.floor(py / cell) * cell
        if s.burner_x0 < cx0 + cell - 1e-9 and x1 > cx0 + 1e-9 and s.burner_y0 < cy0 + cell - 1e-9 and y1 > cy0 + 1e-9:
            problems.append(f"burner covers the {name}")
    edge0, edge1 = DOOR_CENTRE_Y - s.door_width / 2, DOOR_CENTRE_Y + s.door_width / 2
    if not 0.4 - 1e-9 <= s.door_width <= 2.0 + 1e-9:
        problems.append(f"door width {s.door_width} m is outside 0.4-2.0 m")
    elif not (on_grid(edge0, cell) and on_grid(edge1, cell)):
        problems.append(f"door edges {edge0:.2f}/{edge1:.2f} m are off the {cell} m grid")
    return problems


def render(template: str, s: Scenario, cell: float = 0.1, t_end: float = 600.0) -> str:
    problems = validate(s, cell)
    if problems:
        raise ValueError(f"{s.chid}: " + "; ".join(problems))
    side = burner_side(s.peak_kw, cell)
    wall_x1 = ROOM_X + cell
    y0, y1 = DOOR_CENTRE_Y - s.door_width / 2, DOOR_CENTRE_Y + s.door_width / 2
    top = max(cell, snap(BURNER_HEIGHT, cell))
    values = {
        "CHID": s.chid,
        "TITLE": (f"{s.chid}: {s.peak_kw:.0f} kW {s.growth} t-squared fire, "
                  f"burner at ({s.burner_x0:.1f}, {s.burner_y0:.1f}), door {s.door_width:.1f} m"),
        "T_END": f"{t_end:.1f}",
        "ROOM_IJK": f"{round(3.6 / cell)},{round(2.4 / cell)},{round(2.4 / cell)}",
        "OUT_IJK": f"{round(2.4 / cell)},{round(3.6 / cell)},{round(3.0 / cell)}",
        "WALL_XB": f"{ROOM_X:.1f},{wall_x1:.1f}, 0.0,2.4, 0.0,2.4",
        "HOLE_XB": f"{ROOM_X - 0.01:.2f},{wall_x1 + 0.01:.2f}, {y0:.1f},{y1:.1f}, 0.0,{DOOR_HEIGHT:.1f}",
        "HRRPUA": f"{s.peak_kw / side ** 2:.1f}",
        "TAU_Q": f"{-tau_seconds(s.peak_kw, s.growth):.1f}",
        "BURNER_XB": (f"{s.burner_x0:.1f},{s.burner_x0 + side:.1f}, "
                      f"{s.burner_y0:.1f},{s.burner_y0 + side:.1f}, 0.0,{top:.1f}"),
        "DOOR_Y": f"{y0:.1f},{y1:.1f}",
    }
    text = template
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    if "{{" in text:
        raise ValueError("template placeholder left unfilled: " + text[text.index("{{"):text.index("{{") + 30])
    return text


def sample(n: int, seed: int, cell: float = 0.1) -> list[Scenario]:
    rng = random.Random(seed)
    doors = [w for w in (0.4, 0.6, 0.8, 1.0, 1.2)
             if on_grid(DOOR_CENTRE_Y - w / 2, cell) and on_grid(DOOR_CENTRE_Y + w / 2, cell)]
    scenarios = []
    for i in range(n):
        for _ in range(1000):
            peak = rng.choice(PEAKS_KW)
            side = burner_side(peak, cell)
            s = Scenario(
                chid=f"room_{i:03d}", peak_kw=peak, growth=rng.choice(sorted(ALPHA)),
                burner_x0=snap(rng.randrange(0, round((ROOM_X - side) / cell) + 1) * cell, cell),
                burner_y0=snap(rng.randrange(0, round((ROOM_Y - side) / cell) + 1) * cell, cell),
                door_width=rng.choice(doors))
            if not validate(s, cell):
                scenarios.append(s)
                break
        else:
            raise RuntimeError(f"no valid scenario found for index {i}")
    return scenarios


def main(argv: list[str] | None = None) -> None:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--template", default=str(here.parent / "cases" / "iso9705_template.fds"))
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--cell", type=float, choices=(0.1, 0.2), default=0.1)
    parser.add_argument("--t-end", type=float, default=600.0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    template = Path(args.template).read_text()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fields = list(Scenario.__dataclass_fields__) + ["alpha_kw_s2", "tau_s", "burner_side_m",
                                                     "hrrpua_kw_m2", "cell_m", "t_end_s"]
    with open(out / "manifest.csv", "w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for s in sample(args.n, args.seed, args.cell):
            (out / f"{s.chid}.fds").write_text(render(template, s, args.cell, args.t_end))
            side = burner_side(s.peak_kw, args.cell)
            writer.writerow({**asdict(s), "alpha_kw_s2": ALPHA[s.growth],
                             "tau_s": round(tau_seconds(s.peak_kw, s.growth), 1),
                             "burner_side_m": side, "hrrpua_kw_m2": round(s.peak_kw / side ** 2, 1),
                             "cell_m": args.cell, "t_end_s": args.t_end})


if __name__ == "__main__":
    main()
