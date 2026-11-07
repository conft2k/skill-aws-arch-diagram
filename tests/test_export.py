#!/usr/bin/env python3
"""Tests of scripts/export.py: output paths are worked out before anything is written.

    uv run --no-project --with python-pptx --with cairosvg python3 tests/test_export.py
"""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORT = ROOT / "scripts" / "export.py"
MISSING = [m for m in ("pptx", "cairosvg") if importlib.util.find_spec(m) is None]
if MISSING:  # export.py imports them: skip, like test_examples' export column
    raise unittest.SkipTest(f"needs python-pptx and cairosvg (missing: {', '.join(MISSING)})")


def draft(path, color):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
                    f'<rect x="10" y="10" width="20" height="20" fill="{color}"/></svg>',
                    encoding="utf-8")
    return path


def export(*args):
    return subprocess.run([sys.executable, str(EXPORT), *map(str, args)],
                          capture_output=True, text=True)


class OutputClash(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name)
        self.out = self.work / "out"

    def tearDown(self):
        self._tmp.cleanup()

    def written(self):
        return sorted(p.name for p in self.out.iterdir()) if self.out.exists() else []

    def assert_refused(self, r, *names):
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("Output name clash", r.stdout)
        self.assertIn("Nothing written", r.stderr)
        for name in names:
            self.assertIn(str(name), r.stdout)

    def test_same_stem_in_two_directories(self):
        # the review's repro: document/ and slides/ drafts both named arch.draft.svg
        a = draft(self.work / "document" / "arch.draft.svg", "#FF0000")
        b = draft(self.work / "slides" / "arch.draft.svg", "#0000FF")
        r = export(a, b, "--svg", "--out-dir", self.out)
        self.assert_refused(r, a, b, self.out / "arch.svg")
        self.assertEqual(self.written(), [])

    def test_draft_and_plain_svg_share_a_name(self):
        a = draft(self.work / "arch.draft.svg", "#FF0000")
        b = draft(self.work / "arch.svg", "#0000FF")
        r = export(a, b, "--png", "--out-dir", self.out)
        self.assert_refused(r, a, b, self.out / "arch.png")
        self.assertEqual(self.written(), [])

    def test_no_partial_writes(self):
        # distinct outputs come first on the command line; still nothing may be written
        ok = draft(self.work / "a.draft.svg", "#00FF00")
        x = draft(self.work / "document" / "arch.draft.svg", "#FF0000")
        y = draft(self.work / "slides" / "arch.draft.svg", "#0000FF")
        deck = self.out / "deck.pptx"
        r = export(ok, x, y, "--svg", "--png", "--out-dir", self.out, "--pptx", deck)
        self.assert_refused(r, x, y)
        self.assertEqual(self.written(), [])

    def test_preview_lands_on_a_draft_png(self):
        a = draft(self.work / "deck-1.draft.svg", "#FF0000")
        deck = self.out / "deck.pptx"
        r = export(a, "--png", "--out-dir", self.out, "--pptx", deck, "--preview")
        self.assert_refused(r, a, "--preview slide 1", self.out / "deck-1.png")
        self.assertEqual(self.written(), [])

    def test_output_would_overwrite_a_draft(self):
        a = draft(self.work / "arch.svg", "#FF0000")
        before = a.read_text(encoding="utf-8")
        r = export(a, "--svg", "--out-dir", self.work)
        self.assert_refused(r, a)
        self.assertIn("would overwrite the draft", r.stdout)
        self.assertEqual(a.read_text(encoding="utf-8"), before)

    def test_distinct_names_and_repeated_draft_export(self):
        a = draft(self.work / "document" / "arch.draft.svg", "#FF0000")
        b = draft(self.work / "slides" / "arch-slide.draft.svg", "#0000FF")
        r = export(a, b, a, "--svg", "--out-dir", self.out)    # a twice: same bytes, no clash
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.written(), ["arch-slide.svg", "arch.svg"])
        fill = ET.parse(self.out / "arch.svg").getroot()[0].get("fill")
        self.assertEqual(fill, "#FF0000")


if __name__ == "__main__":
    unittest.main()
