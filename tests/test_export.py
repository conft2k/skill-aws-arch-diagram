#!/usr/bin/env python3
"""Tests of scripts/export.py: output paths are worked out before anything is written.

    uv run --no-project --with python-pptx --with cairosvg python3 tests/test_export.py
"""
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unicodedata
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

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


# root may write any file, so a chmod 444 output cannot be refused for it (os.access is True)
IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


def export(*args, cwd=None, umask=None):
    # UTF-8 both ways: the Korean (NFC / NFD) file names below are printed in the report
    return subprocess.run([sys.executable, str(EXPORT), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8", cwd=cwd,
                          env={**os.environ, "PYTHONUTF8": "1"},
                          preexec_fn=None if umask is None else (lambda: os.umask(umask)))


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
        # one file under both spellings: on macOS APFS the NFD name already is that file;
        # elsewhere a hard link stands in for it
        nfc, nfd = (unicodedata.normalize(f, "아키텍처") for f in ("NFC", "NFD"))
        a = draft(self.work / f"{nfc}.draft.svg", "#FF0000")
        b = self.work / f"{nfd}.draft.svg"
        if not b.exists():
            os.link(a, b)
        self.assertTrue(os.path.samefile(a, b))
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

    # Two existing outputs can be one file under two names (a hard link): writing both would
    # leave one draft's result under both names, so they clash like a shared name.
    def assert_linked_outputs_refused(self, first, second, *args):
        first.parent.mkdir(parents=True, exist_ok=True)
        second.parent.mkdir(parents=True, exist_ok=True)
        first.write_bytes(b"previous output")
        os.link(first, second)
        r = export(*args)
        self.assert_refused(r, first, second)
        self.assertIn("hard links to one file", r.stdout)
        self.assertEqual(first.read_bytes(), b"previous output")
        self.assertEqual(second.read_bytes(), b"previous output")
        return r

    def test_svg_outputs_hard_linked(self):
        # the review's repro: out/a.svg and out/b.svg one inode, b's rect ended up in both
        a = draft(self.work / "a.draft.svg", "#FF0000")
        b = draft(self.work / "b.draft.svg", "#0000FF")
        self.assert_linked_outputs_refused(self.out / "a.svg", self.out / "b.svg",
                                           a, b, "--svg", "--png", "--out-dir", self.out)
        self.assertEqual(self.written(), ["a.svg", "b.svg"])  # no PNG written either

    def test_svg_and_png_outputs_hard_linked(self):
        a = draft(self.work / "a.draft.svg", "#FF0000")
        b = draft(self.work / "b.draft.svg", "#0000FF")
        self.assert_linked_outputs_refused(self.out / "a.svg", self.out / "b.png",
                                           a, b, "--svg", "--png", "--out-dir", self.out)
        self.assertEqual(self.written(), ["a.svg", "b.png"])

    def test_one_drafts_svg_and_png_hard_linked(self):
        # one draft, but SVG text and PNG bytes are different results for one file
        a = draft(self.work / "a.draft.svg", "#FF0000")
        self.assert_linked_outputs_refused(self.out / "a.svg", self.out / "a.png",
                                           a, "--svg", "--png", "--out-dir", self.out)

    def test_svg_output_and_deck_hard_linked(self):
        a = draft(self.work / "a.draft.svg", "#FF0000")
        deck = self.work / "slides" / "deck.pptx"
        self.assert_linked_outputs_refused(self.out / "a.svg", deck,
                                           a, "--svg", "--out-dir", self.out, "--pptx", deck)
        self.assertEqual(self.written(), ["a.svg"])

    def test_png_output_and_preview_hard_linked(self):
        a = draft(self.work / "a.draft.svg", "#FF0000")
        deck = self.work / "slides" / "deck.pptx"
        self.assert_linked_outputs_refused(self.out / "a.png", self.work / "slides" / "deck-1.png",
                                           a, "--png", "--out-dir", self.out, "--pptx", deck,
                                           "--preview")
        self.assertFalse(deck.exists())

    def test_same_draft_twice_onto_existing_outputs(self):
        # the same draft by two names writes identical bytes: still not a clash with outputs there
        a = draft(self.work / "a.draft.svg", "#FF0000")
        b = self.work / "A.draft.svg"
        os.link(a, b)
        self.out.mkdir()
        (self.out / "a.svg").write_text("old", encoding="utf-8")
        r = export(a, b, "--svg", "--out-dir", self.out)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(ET.parse(self.out / "a.svg").getroot()[0].get("fill"), "#FF0000")

    # The deck goes to its own path: its directory is made once every check has passed.
    def test_pptx_alone_in_a_new_directory(self):
        # the review's repro: FileNotFoundError, as only --out-dir was ever created
        a = draft(self.work / "a.draft.svg", "#FF0000")
        r = export(a, "--pptx", "new/nested/deck.pptx", cwd=self.work)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertGreater((self.work / "new" / "nested" / "deck.pptx").stat().st_size, 0)

    def test_svg_png_and_pptx_in_different_new_directories(self):
        a = draft(self.work / "a.draft.svg", "#FF0000")
        deck = self.work / "slides" / "new" / "deck.pptx"
        r = export(a, "--svg", "--png", "--out-dir", self.out, "--pptx", deck, "--preview")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.written(), ["a.png", "a.svg"])
        self.assertEqual(sorted(p.name for p in deck.parent.iterdir()), ["deck-1.png", "deck.pptx"])

    def test_pptx_replaces_a_deck_in_an_existing_directory(self):
        a = draft(self.work / "a.draft.svg", "#FF0000")
        deck = self.out / "deck.pptx"
        self.out.mkdir()
        deck.write_bytes(b"previous deck")
        r = export(a, "--pptx", deck)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(deck.read_bytes().startswith(b"PK"))
        self.assertEqual(self.written(), ["deck.pptx"])  # and no temp file left beside it

    def test_refused_export_makes_no_deck_directory(self):
        bad = self.work / "bad.draft.svg"
        bad.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
                       '<path d="M0,0 L9,9"/></svg>', encoding="utf-8")
        r = export(bad, "--pptx", self.work / "new" / "deck.pptx")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertFalse((self.work / "new").exists())
        x = draft(self.work / "document" / "arch.draft.svg", "#FF0000")
        y = draft(self.work / "slides" / "arch.draft.svg", "#0000FF")
        r = export(x, y, "--svg", "--out-dir", self.out, "--pptx", self.work / "new" / "deck.pptx")
        self.assert_refused(r, x, y)
        self.assertFalse((self.work / "new").exists())
        self.assertFalse(self.out.exists())

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


class OutputPermissions(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.work = Path(self._tmp.name)
        self.out = self.work / "out"

    def written(self):
        return sorted(p.name for p in self.out.iterdir()) if self.out.exists() else []

    def test_new_outputs_follow_umask(self):
        # the review's repro: under umask 077 every output came out 0644, not 0600
        a = draft(self.work / "a.draft.svg", "#FF0000")
        for mask, mode in ((0o077, 0o600), (0o002, 0o664)):
            out = self.work / f"out-{mask:03o}"
            r = export(a, "--svg", "--png", "--out-dir", out, "--pptx", out / "deck.pptx",
                       umask=mask)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for name in ("a.svg", "a.png", "deck.pptx"):
                self.assertEqual((out / name).stat().st_mode & 0o777, mode,
                                 f"{name} under umask {mask:03o}")

    @unittest.skipIf(IS_ROOT, "root may write a read-only file")
    def test_one_read_only_output_stops_every_write(self):
        a = draft(self.work / "a.draft.svg", "#FF0000")
        b = draft(self.work / "b.draft.svg", "#0000FF")
        self.out.mkdir()
        locked = self.out / "b.svg"
        locked.write_text("old", encoding="utf-8")
        locked.chmod(0o444)
        r = export(a, b, "--svg", "--png", "--out-dir", self.out, "--pptx", self.out / "deck.pptx")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("not writable", r.stdout)
        self.assertIn(str(locked), r.stdout)
        self.assertIn("Nothing written", r.stderr)
        self.assertEqual(locked.read_text(encoding="utf-8"), "old")
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["b.svg"])

    @unittest.skipIf(IS_ROOT, "root may write a read-only file")
    def test_deck_symlinked_to_a_read_only_file(self):
        a = draft(self.work / "a.draft.svg", "#FF0000")
        target = self.work / "ro" / "deck.pptx"
        target.parent.mkdir()
        target.write_bytes(b"previous deck")
        target.chmod(0o444)
        link = self.work / "deck.pptx"
        link.symlink_to(target)
        r = export(a, "--svg", "--out-dir", self.out, "--pptx", link, "--preview")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("not writable", r.stdout)
        self.assertEqual(target.read_bytes(), b"previous deck")
        self.assertTrue(link.is_symlink())
        self.assertFalse(self.out.exists())
        self.assertEqual(sorted(p.name for p in target.parent.iterdir()), ["deck.pptx"])


    @unittest.skipIf(IS_ROOT, "root may write in a read-only folder")
    def test_writable_outputs_in_read_only_folders(self):
        # the review's repro: main wrote every output; the temp file + rename wrote the SVG
        # and PNG, then failed on the deck's temp file in its 0555 folder
        a = draft(self.work / "a.draft.svg", "#FF0000")
        locked = self.work / "locked"
        locked.mkdir()
        deck = locked / "deck.pptx"
        deck.write_bytes(b"previous deck")
        deck.chmod(0o640)
        self.out.mkdir()
        for name in ("a.svg", "a.png", "deck-1.png"):
            (self.out / name).write_bytes(b"old")
        os.replace(self.out / "deck-1.png", locked / "deck-1.png")
        for folder in (locked, self.out):
            folder.chmod(0o555)
            self.addCleanup(folder.chmod, 0o755)
        r = export(a, "--svg", "--png", "--out-dir", self.out, "--pptx", deck, "--preview")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(ET.parse(self.out / "a.svg").getroot()[0].get("fill"), "#FF0000")
        self.assertTrue((self.out / "a.png").read_bytes().startswith(b"\x89PNG"))
        self.assertTrue((locked / "deck-1.png").read_bytes().startswith(b"\x89PNG"))
        self.assertTrue(deck.read_bytes().startswith(b"PK"))
        self.assertEqual(deck.stat().st_mode & 0o777, 0o640)
        self.assertEqual(sorted(p.name for p in locked.iterdir()), ["deck-1.png", "deck.pptx"])

    @unittest.skipIf(IS_ROOT, "root may write in a read-only folder")
    def test_new_output_in_a_read_only_folder_stops_every_write(self):
        a = draft(self.work / "a.draft.svg", "#FF0000")
        locked = self.work / "locked"
        locked.mkdir()
        locked.chmod(0o555)
        self.addCleanup(locked.chmod, 0o755)
        r = export(a, "--svg", "--png", "--out-dir", self.out, "--pptx", locked / "deck.pptx")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("not writable", r.stdout)
        self.assertIn(str(locked / "deck.pptx"), r.stdout)
        self.assertFalse(self.out.exists())
        self.assertEqual(list(locked.iterdir()), [])

    def test_long_names(self):
        # the review's repro: names open() accepts failed with ENAMETOOLONG on the temp file
        a = draft(self.work / ("a" * 240 + ".draft.svg"), "#FF0000")
        deck = self.out / ("b" * 245 + ".pptx")
        r = export(a, "--svg", "--png", "--out-dir", self.out, "--pptx", deck, "--preview")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.written(), sorted(["a" * 240 + ".png", "a" * 240 + ".svg",
                                                 "b" * 245 + "-1.png", deck.name]))
        self.assertTrue(all(p.stat().st_size > 0 for p in self.out.iterdir()))

    def test_failed_conversion_writes_nothing(self):
        # every result is built before the first write: a deck or preview that fails to
        # convert leaves no SVG or PNG behind, and the existing files as they were
        sys.path.insert(0, str(ROOT / "scripts"))
        import export as export_module
        a = draft(self.work / "a.draft.svg", "#FF0000")
        self.out.mkdir()
        (self.out / "a.svg").write_bytes(b"old")
        argv = ["export.py", str(a), "--svg", "--png", "--out-dir", str(self.out),
                "--pptx", str(self.out / "deck.pptx"), "--preview"]
        for target in ("svg2pptx.convert", "render_pptx.pngs"):
            with self.subTest(target), patch.object(sys, "argv", argv), \
                    patch(f"export.{target}", side_effect=RuntimeError("conversion failed")), \
                    redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
                export_module.main()
            self.assertEqual(self.written(), ["a.svg"])
            self.assertEqual((self.out / "a.svg").read_bytes(), b"old")


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


    def test_hidden_elements_refused_before_any_output(self):
        # display="none" / visibility="hidden" | "collapse": CairoSVG draws some into the PNG
        # (and style= can show them again) while the slide would not, so nothing is written
        bodies = {
            "display-style": '<rect x="10" y="10" width="20" height="20" fill="#FF0000" display="none" '
                             'style="display:inline"/>',
            "image-display": '<image x="10" y="10" width="32" height="32" href="bundle:service/AWS-Lambda" '
                             'display="none"/>',
            "image-hidden": '<image x="10" y="10" width="32" height="32" href="bundle:service/AWS-Lambda" '
                            'visibility="hidden"/>',
            "rect-collapse": '<rect x="10" y="10" width="20" height="20" fill="#FF0000" visibility="collapse"/>',
            "text-collapse": '<text x="10" y="30" font-size="14" fill="#FF0000" visibility="collapse">Hi</text>',
            "group-display": '<g display="none"><rect x="10" y="10" width="20" height="20" fill="#FF0000"/></g>',
        }
        with tempfile.TemporaryDirectory() as tmp:
            ok = draft(Path(tmp) / "ok.draft.svg", "#00FF00")
            for name, body in bodies.items():
                with self.subTest(name=name):
                    bad = Path(tmp) / f"{name}.draft.svg"
                    bad.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 100">{body}</svg>',
                                   encoding="utf-8")
                    out = Path(tmp) / f"out-{name}"
                    r = export(ok, bad, "--svg", "--png", "--out-dir", out, "--pptx", out / "deck.pptx")
                    self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                    self.assertNotIn("Traceback", r.stderr)
                    self.assertIn(f"{bad}:", r.stdout)
                    self.assertIn("delete the element", r.stdout)
                    self.assertIn("Nothing written", r.stderr)
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
