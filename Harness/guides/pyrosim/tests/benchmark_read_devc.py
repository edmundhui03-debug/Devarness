"""Compare CSV loading with the pre-optimization reader, without running FDS.

Run with any Python 3.9+: python tests/benchmark_read_devc.py
Times are untraced medians; peaks are tracemalloc Python allocations, not RSS.
The reference reader is frozen from the old workspace's commit 969bb22 for reproducibility.
"""

import csv
import gc
import json
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import fds_to_dataset as fc


def reference_read_devc(path):
    """Frozen original, deliberately retaining the redundant full CSV copy."""
    with open(path, newline="") as stream:
        rows = list(csv.reader(stream))
    units_row, ids = rows[0], [cell.strip().strip('"') for cell in rows[1]]
    units = {name: unit.strip() for name, unit in zip(ids, units_row)}
    data = [{name: float(value) for name, value in zip(ids, row)} for row in rows[2:] if row]
    return units, data


def pipeline(reader, path):
    units, rows = reader(path)
    return units, rows, fc.to_dataset(rows, with_risk=False, units=units)


def main():
    count, repeats = 50000, 7
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "synthetic_devc.csv"
        with path.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["s"] + ["C", "ppm", "1/m", "m", ""] * 2)
            writer.writerow(["Time"] + [f"{zone}_{suffix}" for zone in fc.ZONES
                                       for suffix in ("T", "CO", "OD", "VIS", "FED")])
            for i in range(count):
                writer.writerow([i * 0.1] + [20, 2, 0.00218, 30, 0] * 2)

        readers = {"baseline": reference_read_devc, "optimized": fc.read_devc}
        results, metrics = {}, {}
        for name, reader in readers.items():
            gc.collect()
            tracemalloc.start()
            try:
                results[name] = pipeline(reader, path)
                peak = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
            metrics[name] = {"peak_python_bytes": peak}
        assert results["baseline"] == results["optimized"], "Parsed data or frames changed"
        frames = len(results["optimized"][2])
        del results

        timings = {name: [] for name in readers}
        for round_number in range(repeats):
            order = list(readers) if round_number % 2 == 0 else list(reversed(readers))
            for name in order:
                gc.collect()
                start = time.perf_counter()
                result = pipeline(readers[name], path)
                timings[name].append(time.perf_counter() - start)
                del result
        for name in readers:
            metrics[name]["median_seconds"] = statistics.median(timings[name])
        baseline, optimized = metrics["baseline"], metrics["optimized"]
        assert optimized["peak_python_bytes"] < baseline["peak_python_bytes"], "No memory reduction"
        print(json.dumps({
            "python": platform.python_version(), "platform": platform.platform(),
            "input_rows": count, "output_frames": frames, "timing_repeats": repeats,
            "risk_scoring": False, "parsed_data_and_frames_equal": True,
            **metrics,
            "peak_memory_reduction_pct": 100 * (1 - optimized["peak_python_bytes"]
                                                   / baseline["peak_python_bytes"]),
            "median_time_reduction_pct": 100 * (1 - optimized["median_seconds"]
                                                   / baseline["median_seconds"]),
        }, indent=2))


if __name__ == "__main__":
    main()
