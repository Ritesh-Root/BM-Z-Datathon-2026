"""Create light/dark colour variants of the vendored logos for the README.

simple-icons and IBM Carbon pictograms ship as single-colour SVG paths without
a fill. GitHub renders README images on light or dark backgrounds, so we write
one variant per theme (brand colour or near-black for light, near-white for
dark) into docs/assets/logos. Run: python scripts/make_logo_variants.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "vitalwatch" / "web" / "static" / "brand"
OUT = ROOT / "docs" / "assets" / "logos"

SIMPLE = {"python": "#3776AB", "flask": "#3BABC3", "pandas": "#150458", "numpy": "#013243",
          "scikitlearn": "#F7931E", "tensorflow": "#FF6F00", "docker": "#2496ED", "ubuntu": "#E95420",
          "jupyter": "#F37626", "pytest": "#0A9EDC"}
PICTOS = ("ibm--z17", "linuxone-5", "ai--privacy", "audit-trail", "ai--explainability", "heart--health",
          "doctor-patient", "hospital")
ICONS = ("ibm--granite", "ibm--ai-on-z", "linux", "logo--python", "logo--jupyter")


def recolor(svg: str, color: str) -> str:
    svg = re.sub(r"<svg\b", f'<svg fill="{color}"', svg, count=1)
    return svg


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, color in SIMPLE.items():
        svg = (BRAND / "simple-icons" / f"{name}.svg").read_text()
        (OUT / f"{name}-light.svg").write_text(recolor(svg, color))
        (OUT / f"{name}-dark.svg").write_text(recolor(svg, "#f4f4f4"))
    for name in PICTOS:
        svg = (BRAND / "carbon-pictograms" / f"{name}.svg").read_text()
        (OUT / f"{name}-light.svg").write_text(recolor(svg, "#0f62fe"))
        (OUT / f"{name}-dark.svg").write_text(recolor(svg, "#78a9ff"))
    for name in ICONS:
        svg = (BRAND / "carbon-icons" / f"{name}.svg").read_text()
        (OUT / f"{name}-light.svg").write_text(recolor(svg, "#161616"))
        (OUT / f"{name}-dark.svg").write_text(recolor(svg, "#f4f4f4"))
    print(f"wrote {len(list(OUT.glob('*.svg')))} files to {OUT}")


if __name__ == "__main__":
    main()
