"""Export raw FDS device readings as five-second sensor frames.

The educational CSV contains temperature_c (degrees C), optical_density (1/m)
and co_ppm, with visibility_m and fed retained as additional measurements.
Rows are selected by decimation, not averaging, starting at ignition (t = 0).
No private project module or risk classifier is required.

    python fds_to_dataset.py room_000_devc.csv -o room_000_frames.csv

FDS writes two header rows: units, then device IDs. Devices are named
<zone>_T, <zone>_CO, <zone>_OD, <zone>_VIS and <zone>_FED. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import math
from itertools import islice

SAMPLE_S = 5.0
# What a CO device may be written in, and the factor that takes it to ppm.
# PyroSim's gas-phase dialog writes mol/mol unless a CONVERSION_FACTOR is set;
# an FDS device with CONVERSION_FACTOR=100, UNITS='%' writes 0.014 for 140 ppm,
# so guessing here is a factor-of-10,000 error.
CO_TO_PPM = {"ppm": 1.0, "mol/mol": 1.0e6, "%": 1.0e4}
ZONES = ("S1", "S2")
CHANNELS = {"temperature_c": "T", "optical_density": "OD", "co_ppm": "CO",
            "visibility_m": "VIS", "fed": "FED"}


def read_devc(path) -> tuple[dict[str, str], list[dict[str, float]]]:
    with open(path, newline="", encoding="utf-8") as stream:
        rows = csv.reader(stream)
        # Buffer only the headers; keep the existing IndexError for missing ones.
        headers = list(islice(rows, 2))
        units_row, ids = headers[0], [cell.strip().strip('"') for cell in headers[1]]
        units = {name: unit.strip() for name, unit in zip(ids, units_row)}
        data = [{name: float(value) for name, value in zip(ids, row)} for row in rows if row]
    return units, data


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


def to_dataset(rows: list[dict[str, float]], zones=ZONES,
              units: dict[str, str] | None = None) -> list[dict]:
    """units is the first header row from read_devc, and decides the CO scaling.

    Units are read, never assumed: an unrecognised one is refused. Readings are
    required to be finite. This exporter does not assign risk or safety labels.
    """
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
                                     "a non-finite reading cannot be exported")
                if channel == "co_ppm":
                    unit = (units.get(device) or "ppm").strip()
                    if unit not in CO_TO_PPM:
                        raise ValueError(f"device {device} is written in {unit!r}, which this script "
                                         f"cannot convert to ppm; expected one of {sorted(CO_TO_PPM)}")
                    value *= CO_TO_PPM[unit]
                frame[channel] = value
            frames.append(frame)
    return frames


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("devc_csv")
    parser.add_argument("-o", "--output", required=True)
    args = parser.parse_args(argv)
    units, rows = read_devc(args.devc_csv)
    frames = to_dataset(rows, units=units)
    with open(args.output, "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(frames[0]))
        writer.writeheader()
        writer.writerows(frames)


if __name__ == "__main__":
    main()
