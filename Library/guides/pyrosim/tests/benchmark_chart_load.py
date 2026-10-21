"""Compare chart CSV loading with its original buffering algorithm.

Run: python tests/benchmark_chart_load.py
No HTML is generated. Peaks are traced Python allocations, not process RSS.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "results"))
import make_charts as mc


def reference_load(chid, kind):
    """Original row-buffering algorithm from 5aa27c0, with explicit cleanup."""
    path = mc.HERE / chid / f"{chid}_{kind}.csv"
    with open(path) as stream:
        rows = list(csv.reader(stream))
    ids = [c.strip().strip('"') for c in rows[1]]
    return [dict(zip(ids, map(float, r))) for r in rows[2:] if r]


def main():
    real_files = 0
    for folder in sorted(mc.HERE.iterdir()):
        for kind in ("devc", "hrr"):
            path = folder / f"{folder.name}_{kind}.csv"
            if not path.is_file():
                continue
            original = reference_load(folder.name, kind)
            optimized = mc.load(folder.name, kind)
            assert original == optimized, f"Parsed records changed: {path}"
            if original:
                times = range(0, 1201, 5)
                for key in original[0]:
                    assert mc.every(original, key, times) == mc.every(optimized, key, times)
            real_files += 1

    count, repeats = 50000, 7
    with tempfile.TemporaryDirectory() as folder:
        previous_here = mc.HERE
        mc.HERE = Path(folder)
        try:
            case = mc.HERE / "room"
            case.mkdir()
            with (case / "room_devc.csv").open("w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["s"] + ["C", "ppm", "1/m", "m", ""] * 2)
                writer.writerow(["Time"] + [f"{zone}_{suffix}" for zone in ("S1", "S2")
                                           for suffix in ("T", "CO", "OD", "VIS", "FED")])
                for i in range(count):
                    writer.writerow([i * 0.1] + [20, 2, 0.00218, 30, 0] * 2)
            readers = {"baseline": reference_load, "optimized": mc.load}
            results, metrics = {}, {}
            for name, reader in readers.items():
                gc.collect()
                tracemalloc.start()
                try:
                    results[name] = reader("room", "devc")
                    peak = tracemalloc.get_traced_memory()[1]
                finally:
                    tracemalloc.stop()
                metrics[name] = {"peak_python_bytes": peak}
            assert results["baseline"] == results["optimized"], "Synthetic records changed"
            del results
            timings = {name: [] for name in readers}
            for round_number in range(repeats):
                order = list(readers) if round_number % 2 == 0 else list(reversed(readers))
                for name in order:
                    gc.collect()
                    start = time.perf_counter()
                    result = readers[name]("room", "devc")
                    timings[name].append(time.perf_counter() - start)
                    del result
            for name in readers:
                metrics[name]["median_seconds"] = statistics.median(timings[name])
        finally:
            mc.HERE = previous_here
    baseline, optimized = metrics["baseline"], metrics["optimized"]
    assert optimized["peak_python_bytes"] < baseline["peak_python_bytes"], "No memory reduction"
    print(json.dumps({
        "python": platform.python_version(), "platform": platform.platform(),
        "input_rows": count, "timing_repeats": repeats,
        "synthetic_records_equal": True, "real_csv_files_equal": real_files,
        "real_sampled_series_equal": True, **metrics,
        "peak_memory_reduction_pct": 100 * (1 - optimized["peak_python_bytes"]
                                               / baseline["peak_python_bytes"]),
        "median_time_reduction_pct": 100 * (1 - optimized["median_seconds"]
                                               / baseline["median_seconds"]),
    }, indent=2))


if __name__ == "__main__":
    main()
