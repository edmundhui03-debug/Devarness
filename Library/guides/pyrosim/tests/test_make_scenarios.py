import re
from pathlib import Path

import pytest

import make_scenarios as ms

CASES = Path(__file__).resolve().parents[1] / "cases"
TEMPLATE = (CASES / "iso9705_template.fds").read_text()
REFERENCE = (CASES / "iso9705_room.fds").read_text()


def scenario(**kw):
    base = dict(chid="room_000", peak_kw=500.0, growth="fast",
                burner_x0=0.0, burner_y0=0.0, door_width=0.8)
    base.update(kw)
    return ms.Scenario(**base)


def xb_values(text, record):
    for line in text.splitlines():
        if line.startswith("&" + record):
            m = re.search(r"XB=([-\d.,\s]+?)(?:,\s*[A-Z_]+=|\s*/)", line)
            yield [float(v) for v in m.group(1).split(",")]


def test_burner_side_keeps_heat_release_per_area_near_1000():
    assert ms.burner_side(100, 0.1) == pytest.approx(0.4)
    assert ms.burner_side(500, 0.1) == pytest.approx(0.8)
    assert ms.burner_side(1000, 0.1) == pytest.approx(1.0)
    assert ms.burner_side(1000, 0.2) == pytest.approx(1.0)
    assert ms.burner_side(50, 0.2) == pytest.approx(0.4)   # never under two cells


def test_tau_follows_t_squared_growth():
    assert ms.tau_seconds(1000, "fast") == pytest.approx(146.0, abs=0.1)
    assert ms.tau_seconds(1000, "slow") == pytest.approx(584.2, abs=0.1)


def test_render_fills_every_placeholder():
    text = ms.render(TEMPLATE, scenario())
    assert "{{" not in text
    assert "CHID='room_000'" in text
    assert "TAU_Q=-" in text and "HRRPUA=781.2" in text


@pytest.mark.parametrize("cell", [0.1, 0.2])
def test_rendered_geometry_sits_on_the_grid(cell):
    s = scenario(burner_x0=0.4, burner_y0=1.2, door_width=1.2)
    text = ms.render(TEMPLATE, s, cell=cell)
    assert ms.validate(s, cell) == []
    for record in ("OBST", "VENT"):
        for xb in xb_values(text, record):
            assert all(abs(v / cell - round(v / cell)) < 1e-6 for v in xb), (record, xb)
    for xb in xb_values(text, "HOLE"):          # holes overhang the wall by 0.01 m
        assert all(abs(v / cell - round(v / cell)) * cell <= 0.0100001 for v in xb), xb


def devices(text):
    return [l for l in text.splitlines() if l.startswith("&DEVC")]


def test_a_rendered_scenario_measures_exactly_where_the_reference_does():
    # Every batch run must be measured where the reference was, or the two
    # cannot be compared. The device block is identical, line for line.
    text = ms.render(TEMPLATE, scenario(door_width=0.8))
    assert devices(text) == devices(REFERENCE)


def test_every_training_channel_samples_instantaneously():
    # FDS reports a device as a TIME AVERAGE over the output interval unless
    # told otherwise. DATASET decimates precisely so that nothing is averaged,
    # so an averaged channel would be averaged twice.
    training = [f"{z}_{q}" for z in ("S1", "S2") for q in ("T", "CO", "OD", "VIS", "O2", "CO2")]
    for text, where in ((ms.render(TEMPLATE, scenario()), "template"), (REFERENCE, "reference")):
        for name in training:
            line = next(l for l in devices(text) if f"ID='{name}'" in l)
            assert "TEMPORAL_STATISTIC='INSTANT VALUE'" in line, (where, name)
        for name in ("S1_FED", "S2_FED"):        # FED means a running integral
            assert "TEMPORAL_STATISTIC" not in next(l for l in devices(text) if f"ID='{name}'" in l)


def test_validate_rejects_burner_through_the_front_wall():
    assert ms.validate(scenario(burner_x0=3.4))


def test_validate_rejects_burner_over_the_floor_gauge():
    assert ms.validate(scenario(burner_x0=1.5, burner_y0=0.9))


def test_validate_rejects_burner_under_the_layer_tree():
    assert ms.validate(scenario(peak_kw=100.0, burner_x0=3.0, burner_y0=1.9))


def test_validate_rejects_off_grid_positions_and_doors():
    assert ms.validate(scenario(burner_x0=0.1), cell=0.2)
    assert ms.validate(scenario(door_width=1.0), cell=0.2)    # edges at 0.7 and 1.7
    assert ms.validate(scenario(door_width=2.4))


def test_render_refuses_an_invalid_scenario():
    with pytest.raises(ValueError, match="front wall"):
        ms.render(TEMPLATE, scenario(burner_x0=3.4))


@pytest.mark.parametrize("cell", [0.1, 0.2])
def test_sample_is_deterministic_and_valid(cell):
    a, b = ms.sample(25, seed=1, cell=cell), ms.sample(25, seed=1, cell=cell)
    assert a == b
    assert len({s.chid for s in a}) == 25
    assert all(ms.validate(s, cell) == [] for s in a)
    assert ms.sample(25, seed=2, cell=cell) != a


def test_cli_writes_cases_and_a_manifest(tmp_path):
    ms.main(["--template", str(CASES / "iso9705_template.fds"), "--n", "3",
             "--seed", "4", "--cell", "0.2", "--t-end", "300", "--out", str(tmp_path)])
    rows = (tmp_path / "manifest.csv").read_text().splitlines()
    assert rows[0].startswith("chid,peak_kw,growth")
    assert len(rows) == 4
    assert sorted(p.name for p in tmp_path.glob("*.fds")) == ["room_000.fds", "room_001.fds", "room_002.fds"]
    assert "T_END=300.0" in (tmp_path / "room_000.fds").read_text()


# --- Regression from Aster's review, 2026-09-13 ------------------------------

def test_an_unsupported_cell_size_is_refused_by_the_api_not_just_the_cli():
    # At 0.05 m the one-decimal coordinates silently move the burner and the
    # door: a 100 kW scenario rendered as 73 kW. The API must refuse, as the
    # CLI already does.
    s = scenario(peak_kw=100.0, burner_x0=0.05, burner_y0=0.05, door_width=0.7)
    with pytest.raises(ValueError, match="cell size"):
        ms.validate(s, 0.05)
    with pytest.raises(ValueError, match="cell size"):
        ms.render(TEMPLATE, s, cell=0.05)
