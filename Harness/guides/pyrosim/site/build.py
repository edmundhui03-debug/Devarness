"""Assemble PyroSim_7Day_Guide.html from the site partials, the case files and the charts.

The FDS listings are copied from cases/*.fds at build time and the charts from
results/charts/*.html, so the page can never show a case or a number that has
drifted from the files that were actually run. After building, run i18n
extract / inject / check on the output; its keys are content hashes, so a
rebuild keeps every translation whose English did not change.

    python site/build.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent
OUT = ROOT / "PyroSim_7Day_Guide.html"


CASE_NOTE = {
    "iso9705_room": "The reference case, 10 cm cells",
    "iso9705_room_20cm": "The same room on 20 cm cells",
    "day6_broken": "Day 6 exercise: three faults, no error",
    "iso9705_template": "Day 7 template, filled by make_scenarios.py",
}


def fds_source(name: str) -> str:
    """The case text, carried once in a non-executing block the page reads."""
    text = (ROOT / "cases" / f"{name}.fds").read_text()
    if "</script" in text.lower():
        raise ValueError(f"{name}.fds contains '</script', which would end the block early")
    return f'<script type="text/plain" id="src-{name}">\n{text}</script>'


def fds_listing(name: str) -> str:
    """The visible listing: a bar with copy and save, and the highlighted text."""
    if name not in CASE_NOTE:
        raise ValueError(f"unknown case {name}")
    lines = (ROOT / "cases" / f"{name}.fds").read_text().count("\n")
    return (f'<div class="listing">\n'
            f'  <div class="listing-bar">\n'
            f'    <span class="listing-name">{name}.fds</span>\n'
            f'    <span class="listing-status" aria-live="polite"></span>\n'
            f'    <button class="btn" type="button" data-copy="{name}">Copy</button>\n'
            f'    <button class="btn" type="button" data-save="{name}" hidden>Save file</button>\n'
            f'  </div>\n'
            f'  <pre class="fds" data-src="{name}" tabindex="0" '
            f'aria-label="{CASE_NOTE[name]}, {lines} lines"></pre>\n'
            f'</div>\n')


def render(text: str, depth: int = 0) -> str:
    if depth > 4:
        raise RecursionError("includes nested too deeply")

    def include(m):
        return render((SITE / "parts" / m.group(1)).read_text(), depth + 1)

    def inline(m):
        return (SITE / m.group(1)).read_text()

    def chart(m):
        path = ROOT / "results" / "charts" / f"{m.group(1)}.html"
        if not path.exists():
            raise FileNotFoundError(f"chart {path.name} has not been generated; run results/make_charts.py")
        return path.read_text()

    text = re.sub(r"<!--INCLUDE:([\w.-]+)-->", include, text)
    text = re.sub(r"/\*INLINE:([\w.-]+)\*/", inline, text)
    text = re.sub(r"<!--CHART:([\w.-]+)-->", chart, text)
    text = re.sub(r"<!--FDSBLOCK:([\w.-]+)-->", lambda m: fds_listing(m.group(1)), text)
    text = re.sub(r"<!--FDS:([\w.-]+)-->", lambda m: fds_source(m.group(1)), text)
    return text


def main() -> int:
    page = render((SITE / "page.html").read_text())
    leftovers = re.findall(r"<!--(?:INCLUDE|CHART|FDS|FDSBLOCK):[^>]*-->|/\*INLINE:[^*]*\*/", page)
    if leftovers:
        print("unresolved markers:", leftovers, file=sys.stderr)
        return 1
    OUT.write_text(page)
    print(f"wrote {OUT.name}: {len(page):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
