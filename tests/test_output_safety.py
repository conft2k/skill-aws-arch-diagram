#!/usr/bin/env python3
"""Tests that the converters run on their own (embed.py, svg2pptx.py) never lose a file:
a failed run leaves a file already at the output path as it was, an output that is the input
itself (by path, symlink or hard link) is refused, a result replaces the old file only once
complete, and the output's directory is created once the input has passed.

    uv run --no-project --with python-pptx --with cairosvg python3 tests/test_output_safety.py
"""
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import outfile  # noqa: E402

HAS_PPTX = all(importlib.util.find_spec(m) for m in ("pptx", "cairosvg"))

GOOD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<rect x="10" y="10" width="20" height="20" fill="#FF0000"/></svg>')
# an <image> pointing at an external file: embed.py refuses it, without loading the icons
BAD_REF = '<svg xmlns="http://www.w3.org/2000/svg"><image href="missing.svg"/></svg>'
# a <path>: outside the draft subset, so svg2pptx.py refuses it
BAD_SHAPE = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
             '<path d="M0,0 L9,9"/></svg>')


def run(script, *args):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                          capture_output=True, text=True)


class Work(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.work = Path(self._tmp.name)

    def file(self, name, text):
        path = self.work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def leftovers(self, folder=None):
        return sorted(p.name for p in (folder or self.work).iterdir() if p.name.endswith(".tmp"))


class EmbedKeepsFiles(Work):
    # the review's repro: a failed embed deleted the previous output, or the input itself
    def test_failure_keeps_an_existing_output(self):
        src = self.file("draft.svg", BAD_REF)
        dst = self.file("final.svg", "previous successful output")
        r = run("embed.py", src, dst)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"Nothing written to {dst}", r.stderr)
        self.assertEqual(dst.read_text(encoding="utf-8"), "previous successful output")

    def assert_refused_onto_input(self, src, dst):
        before = src.read_bytes()
        r = run("embed.py", src, dst)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("is the input", r.stderr)
        self.assertEqual(src.read_bytes(), before)

    def test_output_is_the_input(self):
        src = self.file("draft.svg", BAD_REF)
        self.assert_refused_onto_input(src, src)

    def test_good_output_is_the_input_too(self):
        # a passing draft is refused as well: embedding over it would lose the bundle: refs
        src = self.file("draft.svg", GOOD)
        self.assert_refused_onto_input(src, self.work / "." / "draft.svg")

    def test_output_symlinked_to_the_input(self):
        src = self.file("draft.svg", BAD_REF)
        link = self.work / "final.svg"
        link.symlink_to(src)
        self.assert_refused_onto_input(src, link)
        self.assertTrue(link.is_symlink())

    def test_output_hard_linked_to_the_input(self):
        src = self.file("draft.svg", BAD_REF)
        link = self.work / "final.svg"
        os.link(src, link)
        self.assert_refused_onto_input(src, link)

    def test_unembed_onto_the_input(self):
        src = self.file("final.svg", GOOD)
        r = run("embed.py", "--unembed", src, src)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(src.read_text(encoding="utf-8"), GOOD)

    def test_success_replaces_the_output_and_makes_its_folder(self):
        src = self.file("draft.svg", GOOD)
        old = self.file("final.svg", "previous successful output")
        r = run("embed.py", src, old)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(old.read_text(encoding="utf-8"), GOOD)
        new = self.work / "new" / "nested" / "final.svg"
        r = run("embed.py", src, new)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(new.read_text(encoding="utf-8"), GOOD)
        self.assertEqual(self.leftovers(), [])

    def test_failure_makes_no_folder(self):
        src = self.file("draft.svg", BAD_REF)
        r = run("embed.py", src, self.work / "new" / "final.svg")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertFalse((self.work / "new").exists())


@unittest.skipUnless(HAS_PPTX, "needs python-pptx and cairosvg")
class DeckKeepsFiles(Work):
    def build(self, svgs, out):
        import svg2pptx
        with redirect_stdout(io.StringIO()) as log:
            ok = svg2pptx.build(svgs, [], out)
        return ok, log.getvalue()

    def test_failure_keeps_an_existing_deck(self):
        src = self.file("draft.svg", BAD_SHAPE)
        deck = self.file("deck.pptx", "previous deck")
        ok, log = self.build([src], deck)
        self.assertFalse(ok)
        self.assertIn(f"Nothing written to {deck}", log)
        self.assertEqual(deck.read_text(encoding="utf-8"), "previous deck")

    def test_deck_is_the_input(self):
        # the review's repro: build([src], [], src) returned False and deleted src
        for body in (BAD_SHAPE, GOOD):
            src = self.file("draft.svg", body)
            for out in (src, self.work / "sub" / ".." / "draft.svg"):
                ok, log = self.build([src], out)
                self.assertFalse(ok)
                self.assertIn("is the input", log)
                self.assertEqual(src.read_text(encoding="utf-8"), body)

    def test_deck_linked_to_an_input(self):
        good = self.file("good.svg", GOOD)
        src = self.file("draft.svg", BAD_SHAPE)
        sym, hard = self.work / "sym.pptx", self.work / "hard.pptx"
        sym.symlink_to(src)
        os.link(src, hard)
        for out in (sym, hard):
            ok, log = self.build([good, src], out)
            self.assertFalse(ok)
            self.assertIn("is the input", log)
            self.assertEqual(src.read_text(encoding="utf-8"), BAD_SHAPE)
        self.assertTrue(sym.is_symlink())

    def test_cli_deck_in_a_new_folder(self):
        src = self.file("draft.svg", GOOD)
        deck = self.work / "new" / "nested" / "deck.pptx"
        r = run("svg2pptx.py", src, "-o", deck)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertGreater(deck.stat().st_size, 0)
        from pptx import Presentation
        self.assertEqual(len(Presentation(str(deck)).slides), 1)
        self.assertEqual(self.leftovers(deck.parent), [])

    def test_cli_failure_makes_no_folder(self):
        src = self.file("draft.svg", BAD_SHAPE)
        r = run("svg2pptx.py", src, "-o", self.work / "new" / "deck.pptx")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertFalse((self.work / "new").exists())

    def test_success_replaces_an_existing_deck(self):
        src = self.file("draft.svg", GOOD)
        deck = self.file("deck.pptx", "previous deck")
        ok, _ = self.build([src], deck)
        self.assertTrue(ok)
        self.assertTrue(deck.read_bytes().startswith(b"PK"))  # a zip, i.e. a real deck
        self.assertEqual(self.leftovers(), [])


class WriteAtomic(Work):
    def test_failed_write_keeps_the_old_file(self):
        out = self.file("out.svg", "old")
        with patch.object(outfile.os, "fsync", side_effect=OSError(28, "No space left on device")), \
                self.assertRaises(OSError):
            outfile.write_atomic(out, "new")
        self.assertEqual(out.read_text(encoding="utf-8"), "old")
        self.assertEqual(self.leftovers(), [])

    def test_symlinked_output_replaces_its_target(self):
        target = self.file("real/out.svg", "old")
        link = self.work / "out.svg"
        link.symlink_to(target)
        outfile.write_atomic(link, b"new")
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_text(encoding="utf-8"), "new")

    def test_mode_kept_and_new_file_readable(self):
        out = self.file("out.svg", "old")
        out.chmod(0o600)
        outfile.write_atomic(out, "new")
        self.assertEqual(out.stat().st_mode & 0o777, 0o600)
        fresh = self.work / "fresh.svg"
        outfile.write_atomic(fresh, "new")
        self.assertEqual(fresh.stat().st_mode & 0o777, 0o644)

    def test_same_file(self):
        a = self.file("a.svg", "x")
        os.link(a, self.work / "b.svg")
        (self.work / "c.svg").symlink_to(a)
        self.assertTrue(outfile.same_file(a, self.work / "b.svg"))
        self.assertTrue(outfile.same_file(a, self.work / "c.svg"))
        self.assertTrue(outfile.same_file(a, self.work / "d" / ".." / "a.svg"))
        self.assertFalse(outfile.same_file(a, self.work / "missing.svg"))
        self.assertFalse(outfile.same_file(a, self.file("e.svg", "x")))


if __name__ == "__main__":
    unittest.main()
