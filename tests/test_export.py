#!/usr/bin/env python3
"""Tests of scripts/export.py: output paths are worked out before anything is written.

    uv run --no-project --with python-pptx --with cairosvg python3 tests/test_export.py
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unicodedata
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


def export(*args, cwd=None):
    # UTF-8 both ways: the Korean (NFC / NFD) file names below are printed in the report
    return subprocess.run([sys.executable, str(EXPORT), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8", cwd=cwd,
                          env={**os.environ, "PYTHONUTF8": "1"})


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

    # Names that differ only in case are one file on macOS (APFS) and Windows: refuse them
    # everywhere, since on such a file system one result would silently replace the other.
    def test_stems_differing_only_in_case(self):
        a = draft(self.work / "docs" / "Arch.draft.svg", "#FF0000")
        b = draft(self.work / "slides" / "arch.draft.svg", "#0000FF")
        r = export(a, b, "--svg", "--out-dir", self.out)
        self.assert_refused(r, a, b, self.out / "Arch.svg", self.out / "arch.svg")
        self.assertEqual(self.written(), [])

    def test_preview_differing_only_in_case_from_a_draft_png(self):
        a = draft(self.work / "deck-1.draft.svg", "#FF0000")
        r = export(a, "--png", "--out-dir", self.out, "--pptx", self.out / "Deck.pptx", "--preview")
        self.assert_refused(r, a, "--preview slide 1", self.out / "deck-1.png", self.out / "Deck-1.png")
        self.assertEqual(self.written(), [])

    def test_output_on_a_draft_differing_only_in_case(self):
        a = draft(self.work / "docs" / "arch.svg", "#FF0000")
        before = a.read_text(encoding="utf-8")
        r = export(a, "--svg", "--out-dir", self.work / "DOCS")
        self.assert_refused(r, a)
        self.assertIn("would overwrite the draft", r.stdout)
        self.assertEqual(a.read_text(encoding="utf-8"), before)
        self.assertFalse((self.work / "DOCS").exists())

    def test_same_file_under_case_different_names(self):
        # what passing Arch.draft.svg and arch.draft.svg means on macOS: one file, two
        # spellings (a hard link stands in for it here); same bytes, so not a clash
        a = draft(self.work / "arch.draft.svg", "#FF0000")
        b = self.work / "Arch.draft.svg"
        os.link(a, b)
        r = export(a, b, "--svg", "--out-dir", self.out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    # APFS also treats the NFC (precomposed) and NFD (decomposed jamo) spellings of a name as
    # one file; Korean names typed on a Mac or copied from Finder can come in either form.
    def test_stems_differing_only_in_unicode_normalisation(self):
        nfc, nfd = (unicodedata.normalize(f, "아키텍처") for f in ("NFC", "NFD"))
        self.assertNotEqual(nfc, nfd)
        a = draft(self.work / "docs" / f"{nfc}.draft.svg", "#FF0000")
        b = draft(self.work / "slides" / f"{nfd}.draft.svg", "#0000FF")
        r = export(a, b, "--svg", "--out-dir", self.out)
        self.assert_refused(r, a, b, self.out / f"{nfc}.svg", self.out / f"{nfd}.svg")
        self.assertEqual(self.written(), [])

    def test_same_file_under_nfc_and_nfd_names(self):
        # one file under both spellings, as on macOS (a hard link stands in for it here)
        nfc, nfd = (unicodedata.normalize(f, "아키텍처") for f in ("NFC", "NFD"))
        a = draft(self.work / f"{nfc}.draft.svg", "#FF0000")
        b = self.work / f"{nfd}.draft.svg"
        os.link(a, b)
        r = export(a, b, "--svg", "--out-dir", self.out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_same_draft_as_relative_and_absolute_path(self):
        a = draft(self.work / "src" / "arch.draft.svg", "#FF0000")
        r = export("src/arch.draft.svg", a, "--svg", "--png", "--out-dir", "out", cwd=self.work)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.written(), ["arch.png", "arch.svg"])

    def test_output_through_a_symlink_to_a_draft(self):
        a = draft(self.work / "src" / "arch.draft.svg", "#FF0000")
        before = a.read_text(encoding="utf-8")
        self.out.mkdir()
        (self.out / "arch.svg").symlink_to(a)
        r = export(a, "--svg", "--out-dir", self.out)
        self.assert_refused(r, a)
        self.assertIn("would overwrite the draft", r.stdout)
        self.assertEqual(a.read_text(encoding="utf-8"), before)

    def test_out_dir_symlinked_to_the_drafts_directory(self):
        a = draft(self.work / "src" / "arch.svg", "#FF0000")
        before = a.read_text(encoding="utf-8")
        self.out.symlink_to(self.work / "src", target_is_directory=True)
        r = export(a, "--svg", "--out-dir", self.out)
        self.assert_refused(r, a)
        self.assertIn("would overwrite the draft", r.stdout)
        self.assertEqual(a.read_text(encoding="utf-8"), before)

    def test_output_hard_linked_to_a_draft(self):
        a = draft(self.work / "src" / "arch.draft.svg", "#FF0000")
        self.out.mkdir()
        os.link(a, self.out / "arch.png")
        r = export(a, "--png", "--out-dir", self.out)
        self.assert_refused(r, a)
        self.assertIn("would overwrite the draft", r.stdout)

    def test_pptx_on_a_draft(self):
        a = draft(self.work / "arch.draft.svg", "#FF0000")
        before = a.read_text(encoding="utf-8")
        r = export(a, "--pptx", a)
        self.assert_refused(r, a, "would overwrite the draft")
        self.assertEqual(a.read_text(encoding="utf-8"), before)

    def test_pptx_on_an_svg_output(self):
        a = draft(self.work / "arch.draft.svg", "#FF0000")
        r = export(a, "--svg", "--out-dir", self.out, "--pptx", self.out / "ARCH.svg")
        self.assert_refused(r, a, "--pptx", self.out / "arch.svg")
        self.assertEqual(self.written(), [])

    def test_every_format_end_to_end(self):
        a = draft(self.work / "a.draft.svg", "#FF0000")
        b = draft(self.work / "b.draft.svg", "#0000FF")
        deck = self.out / "deck.pptx"
        r = export(a, b, "--svg", "--png", "--out-dir", self.out, "--pptx", deck,
                   "--title", "A", "--title", "B", "--preview")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.written(), ["a.png", "a.svg", "b.png", "b.svg",
                                          "deck-1.png", "deck-2.png", "deck.pptx"])
        for name in self.written():
            self.assertGreater((self.out / name).stat().st_size, 0, name)
        self.assertEqual(ET.parse(self.out / "b.svg").getroot()[0].get("fill"), "#0000FF")


class DraftProblems(unittest.TestCase):
    def test_bad_root_opacity_reported_with_the_other_drafts(self):
        # used to escape collect() as a ValueError traceback before any draft was reported
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.draft.svg"
            bad.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" '
                           'opacity="50 %"><rect width="9" height="9" fill="#FF0000"/></svg>',
                           encoding="utf-8")
            other = Path(tmp) / "other.draft.svg"
            other.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
                             '<path d="M0,0 L9,9"/></svg>', encoding="utf-8")
            out = Path(tmp) / "out"
            r = export(bad, other, "--svg", "--out-dir", out)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            self.assertIn("unsupported opacity '50 %'", r.stdout)
            self.assertIn(f"{other}:", r.stdout)
            self.assertIn("<path> is not supported", r.stdout)
            self.assertFalse(out.exists())


class PathKey(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(EXPORT.parent))
        import export as module
        self.key = module.path_key

    def test_nfc_and_nfd_share_a_key(self):
        nfc, nfd = (unicodedata.normalize(f, "아키텍처.svg") for f in ("NFC", "NFD"))
        self.assertEqual(self.key(Path(nfc)), self.key(Path(nfd)))

    def test_key_is_nfc_after_casefold(self):
        # casefold() decomposes U+01F0 (j with caron); the key is normalised again after it
        key = self.key(Path("\u01f0.svg"))
        self.assertTrue(unicodedata.is_normalized("NFC", key), ascii(key))
        self.assertEqual(key, self.key(Path("J\u030c.svg")))


class IconsLoadedLazily(unittest.TestCase):
    """The clash check and --help run before, and without, the icon bundle."""

    def run_without_icons(self, *argv):
        code = ("import sys; sys.path.insert(0, sys.argv[1]); import fetch_icons\n"
                "def boom(): raise SystemExit('icons loaded')\n"
                "fetch_icons.load_sets = boom\n"
                "import export; sys.argv = ['export.py', *sys.argv[2:]]; export.main()")
        return subprocess.run([sys.executable, "-c", code, str(EXPORT.parent), *map(str, argv)],
                              capture_output=True, text=True)

    def test_help(self):
        r = self.run_without_icons("--help")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("icons loaded", r.stderr)

    def test_refused_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = draft(Path(tmp) / "docs" / "arch.draft.svg", "#FF0000")
            b = draft(Path(tmp) / "slides" / "arch.draft.svg", "#0000FF")
            r = self.run_without_icons(a, b, "--svg", "--out-dir", Path(tmp) / "out")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("Output name clash", r.stdout)
        self.assertNotIn("icons loaded", r.stderr)

    def test_checked_export_loads_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "arch.draft.svg"
            a.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
                         '<image href="bundle:service/AWS-Lambda" x="10" y="10" width="48" '
                         'height="48"/></svg>', encoding="utf-8")
            r = self.run_without_icons(a, "--svg", "--out-dir", Path(tmp) / "out")
        self.assertIn("icons loaded", r.stderr)


if __name__ == "__main__":
    unittest.main()
