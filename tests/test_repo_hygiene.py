"""Repository rules: no emoji anywhere, every vendored brand asset is credited."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}
SKIP_TOP = {"data", "logs", "secrets"}
TEXT_SUFFIXES = {".py", ".md", ".txt", ".toml", ".json", ".html", ".js", ".css", ".svg", ".sh",
                 ".yml", ".yaml", ".cfg", ".ini", ""}

# Emoji and pictographic symbol blocks, plus the emoji variation selector.
_RANGES = [(0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF), (0x2300, 0x23FF),
           (0xFE0F, 0xFE0F), (0x200D, 0x200D)]
EMOJI = re.compile("[" + "".join(f"{chr(a)}-{chr(b)}" for a, b in _RANGES) + "]")


def _text_files():
    for p in ROOT.rglob("*"):
        parts = p.relative_to(ROOT).parts
        if any(part in SKIP_DIRS for part in parts) or (parts and parts[0] in SKIP_TOP):
            continue
        if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES and p.stat().st_size < 5_000_000:
            yield p


def test_no_emoji_anywhere():
    offenders = []
    for p in _text_files():
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            m = EMOJI.search(line)
            if m:
                offenders.append(f"{p.relative_to(ROOT)}:{i}: U+{ord(m.group()):04X}")
    assert not offenders, "emoji found:\n" + "\n".join(offenders[:20])


def test_brand_assets_have_licences_and_credits():
    brand = ROOT / "vitalwatch" / "web" / "static" / "brand"
    for sub, lic in (("carbon-icons", "LICENSE"), ("carbon-pictograms", "LICENSE"),
                     ("simple-icons", "LICENSE.md"), ("fonts", "LICENSE.txt")):
        assert (brand / sub / lic).is_file(), f"missing licence for {sub}"
    credits = (ROOT / "docs" / "OSS_CREDITS.md").read_text(encoding="utf-8")
    for name in ("Carbon", "simple-icons", "IBM Plex", "llama.cpp"):
        assert name in credits, f"{name} not credited"
    for svg in (brand / "simple-icons").glob("*.svg"):
        assert svg.stem in credits.lower().replace("-", ""), f"{svg.name} not credited"
