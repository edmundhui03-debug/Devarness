import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "pyrosim_build", Path(__file__).resolve().parents[1] / "site" / "build.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


def test_source_checkout_build_needs_no_private_run_files(tmp_path, monkeypatch):
    output = tmp_path / "guide.html"
    monkeypatch.setattr(build, "OUT", output)
    assert build.main() == 0
    page = output.read_text(encoding="utf-8")
    assert '<script type="text/plain" id="src-iso9705_room">' in page
    assert "Historical chart not included" in page
    assert "<!--CHART:" not in page
