"""Turn an FDS _devc.csv into DATASET zone frames.

The DATASET wire contract (07Aug-07Sep Research/dataset/forecast/schema.py) has a
fire simulator publish three channels per zone -- temperature_c, optical_density
(per metre) and co_ppm -- once every SAMPLE_S = 5 s, with t = 0 at ignition.
Frames are taken by decimation, never by averaging, because averaging low-passes
the rate of rise the forecaster exists to see (DATASET_CData_Sampling_Method.html
:1303-1307). Visibility and FED are carried alongside as tenability labels, and
each frame is scored by the node-level fuzzy index, which reads smoke as
obscuration in %/m, so optical density is converted for that score only.

    python fds_to_dataset.py ../results/batch/room_000_devc.csv -o room_000_frames.csv

FDS writes two header rows: units, then device IDs. Devices are named
<zone>_T, <zone>_CO, <zone>_OD, <zone>_VIS and <zone>_FED, as in
cases/iso9705_room.fds. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import math
from itertools import islice
from pathlib import Path

SAMPLE_S = 5.0
# What a CO device may be written in, and the factor that takes it to ppm.
# PyroSim's gas-phase dialog writes mol/mol unless a CONVERSION_FACTOR is set;
# an FDS device with CONVERSION_FACTOR=100, UNITS='%' writes 0.014 for 140 ppm,
# so guessing here is a factor-of-10,000 error.
CO_TO_PPM = {"ppm": 1.0, "mol/mol": 1.0e6, "%": 1.0e4}
ZONES = ("S1", "S2")
CHANNELS = {"temperature_c": "T", "optical_density": "OD", "co_ppm": "CO",
            "visibility_m": "VIS", "fed": "FED"}
FIS_PATH = Path(__file__).resolve().parents[3] / "07Aug-07Sep Research" / "dataset_fuzzy_fis.py"


def read_devc(path) -> tuple[dict[str, str], list[dict[str, float]]]:
    with open(path, newline="") as stream:
        rows = csv.reader(stream)
        # Buffer only the headers; keep the existing IndexError for missing ones.
        headers = list(islice(rows, 2))
        units_row, ids = headers[0], [cell.strip().strip('"') for cell in headers[1]]
        units = {name: unit.strip() for name, unit in zip(ids, units_row)}
        data = [{name: float(value) for name, value in zip(ids, row)} for row in rows if row]
    return units, data


def obscuration_pct_per_m(optical_density: float) -> float:
    """Percent obscuration over one metre from base-10 optical density per metre."""
    return 100.0 * (1.0 - 10.0 ** (-optical_density))


def load_fis():
    spec = importlib.util.spec_from_file_location("dataset_fuzzy_fis", FIS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def decimate(rows: list[dict[str, float]], interval: float = SAMPLE_S) -> list[dict[str, float]]:
    """Keep the raw row nearest each multiple of the interval, within half a second.

    The sequence must start at ignition and have no gaps: a window built from a
    series with a hole in it silently misreads how fast the fire grew. A gap is
    reported rather than interpolated, because inventing a frame is worse than
    refusing one.
    """
    chosen = {}
    for row in rows:
        if not math.isfinite(row["Time"]):
            raise ValueError("Time column holds a non-finite value")
        k = round(row["Time"] / interval)
        if abs(row["Time"] - k * interval) <= 0.5:
            best = chosen.get(k)
            if best is None or abs(row["Time"] - k * interval) < abs(best["Time"] - k * interval):
                chosen[k] = row
    if not chosen:
        raise ValueError("no row falls within half a second of any sample time")
    keys = sorted(chosen)
    if keys[0] != 0:
        raise ValueError(f"the series starts at {keys[0] * interval:g} s, not at t = 0 (ignition)")
    missing = [k * interval for k in range(keys[0], keys[-1] + 1) if k not in chosen]
    if missing:
        shown = ", ".join(f"{m:g} s" for m in missing[:5]) + (" …" if len(missing) > 5 else "")
        raise ValueError(f"{len(missing)} frame(s) missing from the series: {shown}")
    return [chosen[k] for k in keys]


def to_dataset(rows: list[dict[str, float]], zones=ZONES, with_risk: bool = True,
              units: dict[str, str] | None = None) -> list[dict]:
    """units is the first header row from read_devc, and decides the CO scaling.

    Units are read, never assumed: an unrecognised one is refused. Readings are
    required to be finite, so a dead sensor cannot acquire a risk label.
    """
    fis = load_fis() if with_risk else None
    units = units or {}
    frames = []
    for row in decimate(rows):
        k = round(row["Time"] / SAMPLE_S)
        for zone in zones:
            frame = {"time_s": k * SAMPLE_S, "zone": zone}
            for channel, suffix in CHANNELS.items():
                device = f"{zone}_{suffix}"
                if device not in row:
                    raise KeyError(f"device {device} is not in the _devc.csv header")
                value = row[device]
                if not math.isfinite(value):
                    raise ValueError(f"device {device} reads {value} at t = {row['Time']:g} s; "
                                     "a non-finite reading cannot be scored")
                if channel == "co_ppm":
                    unit = (units.get(device) or "ppm").strip()
                    if unit not in CO_TO_PPM:
                        raise ValueError(f"device {device} is written in {unit!r}, which this script "
                                         f"cannot convert to ppm; expected one of {sorted(CO_TO_PPM)}")
                    value *= CO_TO_PPM[unit]
                frame[channel] = value
            if fis:
                smoke = obscuration_pct_per_m(frame["optical_density"])
                risk, _ = fis.infer(frame["temperature_c"], smoke, frame["co_ppm"])
                frame.update(smoke_obs_pct_per_m=round(smoke, 3), fis_risk=round(risk, 2),
                             fis_level=fis.band(risk))
            frames.append(frame)
    return frames


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("devc_csv")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--no-risk", action="store_true", help="skip the fuzzy index score")
    args = parser.parse_args(argv)
    units, rows = read_devc(args.devc_csv)
    frames = to_dataset(rows, with_risk=not args.no_risk, units=units)
    with open(args.output, "w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(frames[0]))
        writer.writeheader()
        writer.writerows(frames)


if __name__ == "__main__":
    main()
