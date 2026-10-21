import builtins
import csv
import sys
import tracemalloc
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "results"))
import make_charts as mc


@pytest.fixture
def chart_csv(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "HERE", tmp_path)
    folder = tmp_path / "room"
    folder.mkdir()
    return folder / "room_devc.csv"


def test_load_does_not_keep_a_second_full_csv_copy(chart_csv):
    with chart_csv.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["s"] + ["C", "ppm", "1/m", "m", ""] * 2)
        writer.writerow(["Time"] + [f"{zone}_{suffix}" for zone in ("S1", "S2")
                                   for suffix in ("T", "CO", "OD", "VIS", "FED")])
        for t in range(5000):
            writer.writerow([t] + [20, 2, 0.00218, 30, 0] * 2)
    tracemalloc.start()
    try:
        rows = mc.load("room", "devc")
        retained, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(rows) == 5000 and rows[-1]["Time"] == 4999.0
    # Catch full raw-record buffering, allowing parser/allocator overhead.
    assert peak < retained * 1.25 + 128 * 1024, (retained, peak)


@pytest.mark.parametrize("text,error", [
    ("s,C\nTime,T\n0,20\n", None),
    ("s,C\nTime,T\n0,not-a-number\n", ValueError),
])
def test_load_closes_its_input_on_success_and_error(chart_csv, monkeypatch, text, error):
    chart_csv.write_text(text)
    opened = []

    def tracked_open(*args, **kwargs):
        stream = builtins.open(*args, **kwargs)
        opened.append(stream)
        return stream

    # Keep real handles alive so garbage collection cannot hide a missing close.
    monkeypatch.setattr(mc, "open", tracked_open, raising=False)
    try:
        if error:
            with pytest.raises(error):
                mc.load("room", "devc")
        else:
            assert mc.load("room", "devc") == [{"Time": 0.0, "T": 20.0}]
        assert opened and all(stream.closed for stream in opened)
    finally:
        for stream in opened:
            stream.close()


@pytest.mark.parametrize("text", ["", "s,C\n"])
def test_load_preserves_missing_header_error(chart_csv, text):
    chart_csv.write_text(text)
    with pytest.raises(IndexError):
        mc.load("room", "devc")


def test_load_preserves_header_cleanup_blank_rows_and_zip_semantics(chart_csv):
    chart_csv.write_text('s,C,ppm\n Time , "T" ,CO\n\n0,20,2,not-read\n5,30\n')
    assert mc.load("room", "devc") == [
        {"Time": 0.0, "T": 20.0, "CO": 2.0}, {"Time": 5.0, "T": 30.0}]


def test_loaded_series_keeps_last_rounded_time_and_missing_values(chart_csv):
    chart_csv.write_text("s,C\nTime,T\n0,20.123456\n4.9,30\n5.1,40.123456\n10\n")
    assert mc.every(mc.load("room", "devc"), "T", [0, 5, 10, 15]) == [
        20.1235, 40.1235, None, None]
