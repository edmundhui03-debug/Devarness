import csv
import tracemalloc

import pytest

import fds_to_dataset as fc

HEADER = ("s,C,ppm,1/m,m,,C,ppm,1/m,m,\n"
          "Time,S1_T,S1_CO,S1_OD,S1_VIS,S1_FED,S2_T,S2_CO,S2_OD,S2_VIS,S2_FED\n")


def devc_text(rows):
    return HEADER + "".join(",".join(f"{v}" for v in r) + "\n" for r in rows)


@pytest.fixture
def devc(tmp_path):
    rows = []
    for t in range(0, 11):   # 1 s output with FDS's slightly irregular clock
        clock = t + (0.0004 if t % 2 else 0.0)
        rows.append([clock, 20.0 + 10 * t, 14.0 * t, 0.0, 30.0, 0.0,
                     20.0 + 5 * t, 7.0 * t, 0.0, 30.0, 0.0])
    path = tmp_path / "case_devc.csv"
    path.write_text(devc_text(rows))
    return path


def test_default_export_is_self_contained_raw_sensor_data(devc):
    units, rows = fc.read_devc(devc)
    frames = fc.to_dataset(rows, units=units)
    assert set(frames[0]) == {
        "time_s", "zone", "temperature_c", "optical_density", "co_ppm",
        "visibility_m", "fed",
    }
    assert [frame["time_s"] for frame in frames if frame["zone"] == "S1"] == [0, 5, 10]


def test_read_devc_uses_both_header_rows(devc):
    units, rows = fc.read_devc(devc)
    assert units["S1_CO"] == "ppm"
    assert rows[3]["S1_T"] == pytest.approx(50.0)


def test_read_devc_does_not_keep_a_second_full_csv_copy(tmp_path):
    # Reintroducing list(csv.reader(...)) must exceed this allocation budget.
    path = tmp_path / "large_devc.csv"
    with path.open("w", newline="") as stream:
        stream.write(HEADER)
        writer = csv.writer(stream)
        for t in range(5000):
            writer.writerow([t, 20, 2, 0.00218, 30, 0, 20, 2, 0.00218, 30, 0])
    tracemalloc.start()
    try:
        units, rows = fc.read_devc(path)
        retained, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert len(rows) == 5000 and units["S1_CO"] == "ppm"
    assert rows[-1]["Time"] == 4999.0
    # Allow parser buffers and allocator noise, but not another full CSV copy.
    assert peak < retained * 1.25 + 128 * 1024, (retained, peak)


@pytest.mark.parametrize("text", ["", "s,C,ppm\n"])
def test_read_devc_preserves_missing_header_error(tmp_path, text):
    path = tmp_path / "missing_header.csv"
    path.write_text(text)
    with pytest.raises(IndexError):
        fc.read_devc(path)


def test_read_devc_preserves_header_cleanup_blank_rows_and_zip_semantics(tmp_path):
    path = tmp_path / "uneven.csv"
    path.write_text(' s , C ,ppm\n Time , "S1_T" ,S1_CO\n\n0,20,2,999\n5,30\n')
    units, rows = fc.read_devc(path)
    assert units == {"Time": "s", "S1_T": "C", "S1_CO": "ppm"}
    assert rows == [{"Time": 0.0, "S1_T": 20.0, "S1_CO": 2.0},
                    {"Time": 5.0, "S1_T": 30.0}]


def test_read_devc_still_rejects_invalid_numbers_in_late_rows(tmp_path):
    path = tmp_path / "invalid.csv"
    path.write_text("s,C\nTime,S1_T\n0,20\n5,not-a-number\n")
    with pytest.raises(ValueError):
        fc.read_devc(path)


def test_frames_are_every_fifth_second_by_decimation_not_averaging(devc):
    frames = fc.to_dataset(fc.read_devc(devc)[1])
    s1 = [f for f in frames if f["zone"] == "S1"]
    assert [f["time_s"] for f in s1] == [0.0, 5.0, 10.0]
    assert [f["temperature_c"] for f in s1] == [20.0, 70.0, 120.0]   # raw samples, not bin means


def test_one_frame_per_zone_per_time(devc):
    frames = fc.to_dataset(fc.read_devc(devc)[1])
    assert [(f["time_s"], f["zone"]) for f in frames][:4] == [
        (0.0, "S1"), (0.0, "S2"), (5.0, "S1"), (5.0, "S2")]
    assert set(frames[0]) >= {"temperature_c", "optical_density", "co_ppm", "visibility_m", "fed"}


def test_co_written_as_mol_per_mol_is_converted_to_ppm(tmp_path):
    # A gas-phase device made in PyroSim writes VOLUME FRACTION in mol/mol.
    path = tmp_path / "pyrosim_devc.csv"
    path.write_text(HEADER.replace("s,C,ppm,1/m,m,,C,ppm", "s,C,mol/mol,1/m,m,,C,mol/mol")
                    + "0.0,20.0,1.4E-4,0.0,30.0,0.0,20.0,7.0E-5,0.0,30.0,0.0\n")
    units, rows = fc.read_devc(path)
    frames = fc.to_dataset(rows, units=units)
    assert frames[0]["co_ppm"] == pytest.approx(140.0)
    assert frames[1]["co_ppm"] == pytest.approx(70.0)


def test_missing_device_names_the_id(tmp_path):
    path = tmp_path / "bad_devc.csv"
    path.write_text(HEADER.replace("S2_CO", "S2_CARBON") + "0.0,20,0,0,30,0,20,0,0,30,0\n")
    with pytest.raises(KeyError, match="S2_CO"):
        fc.to_dataset(fc.read_devc(path)[1])


def test_cli_writes_a_csv(devc, tmp_path):
    out = tmp_path / "frames.csv"
    fc.main([str(devc), "-o", str(out)])
    with open(out, newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 6
    assert rows[0]["zone"] == "S1" and "temperature_c" in rows[0]
    assert set(rows[0]) == set(fc.to_dataset(fc.read_devc(devc)[1])[0])


# --- Invalid readings and sampling regressions ----------------------------

def test_non_finite_readings_are_refused(tmp_path):
    path = tmp_path / "nan_devc.csv"
    path.write_text(HEADER + "0.0,nan,0.0,0.0,30.0,0.0,20.0,0.0,0.0,30.0,0.0\n")
    with pytest.raises(ValueError, match="S1_T"):
        fc.to_dataset(fc.read_devc(path)[1])


def test_non_finite_time_is_refused(tmp_path):
    path = tmp_path / "nantime_devc.csv"
    path.write_text(HEADER + "nan,20.0,0.0,0.0,30.0,0.0,20.0,0.0,0.0,30.0,0.0\n")
    with pytest.raises(ValueError, match="Time"):
        fc.to_dataset(fc.read_devc(path)[1])


@pytest.mark.parametrize("unit,value,expected", [
    ("ppm", 140.0, 140.0),
    ("mol/mol", 1.4e-4, 140.0),
    ("%", 0.014, 140.0),
])
def test_every_supported_co_unit_reaches_ppm(unit, value, expected):
    rows = [{"Time": 0.0, "S1_T": 20.0, "S1_CO": value, "S1_OD": 0.0, "S1_VIS": 30.0, "S1_FED": 0.0,
             "S2_T": 20.0, "S2_CO": value, "S2_OD": 0.0, "S2_VIS": 30.0, "S2_FED": 0.0}]
    f = fc.to_dataset(rows, units={"S1_CO": unit, "S2_CO": unit})[0]
    assert f["co_ppm"] == pytest.approx(expected)


def test_an_unknown_co_unit_is_refused_rather_than_assumed_to_be_ppm():
    # 0.014 in '%' is 140 ppm; passing it through as ppm is a 10,000x error.
    rows = [{"Time": 0.0, "S1_T": 20.0, "S1_CO": 0.014, "S1_OD": 0.0, "S1_VIS": 30.0, "S1_FED": 0.0,
             "S2_T": 20.0, "S2_CO": 0.0, "S2_OD": 0.0, "S2_VIS": 30.0, "S2_FED": 0.0}]
    with pytest.raises(ValueError, match="kg/kg"):
        fc.to_dataset(rows, units={"S1_CO": "kg/kg"})


def test_a_missing_frame_is_reported_not_silently_dropped():
    rows = [{"Time": t, **{k: 1.0 for k in ("S1_T", "S1_CO", "S1_OD", "S1_VIS", "S1_FED",
                                            "S2_T", "S2_CO", "S2_OD", "S2_VIS", "S2_FED")}}
            for t in (0.0, 4.49, 5.51, 10.0)]
    with pytest.raises(ValueError, match="missing from the series: 5 s"):
        fc.to_dataset(rows)


def test_a_series_that_does_not_start_at_ignition_is_refused():
    rows = [{"Time": t, **{k: 1.0 for k in ("S1_T", "S1_CO", "S1_OD", "S1_VIS", "S1_FED",
                                            "S2_T", "S2_CO", "S2_OD", "S2_VIS", "S2_FED")}}
            for t in (5.0, 10.0, 15.0)]
    with pytest.raises(ValueError, match="t = 0"):
        fc.to_dataset(rows)
