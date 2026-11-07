#!/usr/bin/env python3
"""Tests that the converters run on their own (embed.py, svg2pptx.py, render_pptx.py) never
lose a file: a failed run leaves a file already at the output path as it was, an output that
is the input itself (by path, symlink or hard link) is refused, a result is written only once
complete, the output's directory is created once the input has passed, and the write is a
plain open(): umask, mode, read-only folders and long names behave as open() does.

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
# root may write any file, so a chmod 444 output cannot be refused for it (os.access is True)
IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0

GOOD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<rect x="10" y="10" width="20" height="20" fill="#FF0000"/></svg>')
# an <image> pointing at an external file: embed.py refuses it, without loading the icons
BAD_REF = '<svg xmlns="http://www.w3.org/2000/svg"><image href="missing.svg"/></svg>'
# a <path>: outside the draft subset, so svg2pptx.py refuses it
BAD_SHAPE = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
             '<path d="M0,0 L9,9"/></svg>')


def run(script, *args, umask=None):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                          capture_output=True, text=True,
                          preexec_fn=None if umask is None else (lambda: os.umask(umask)))


class umask_set:
    """Run a block under this process's umask `mask`, restoring the old one after."""
    def __init__(self, mask):
        self.mask = mask

    def __enter__(self):
        self.old = os.umask(self.mask)

    def __exit__(self, *exc):
        os.umask(self.old)


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

    def test_new_output_follows_umask(self):
        # the review's repro: under umask 077 the output came out 0644, not 0600
        src = self.file("draft.svg", GOOD)
        for mask, mode in ((0o077, 0o600), (0o002, 0o664)):
            dst = self.work / f"final-{mask:03o}.svg"
            r = run("embed.py", src, dst, umask=mask)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(dst.stat().st_mode & 0o777, mode, f"umask {mask:03o}")

    @unittest.skipIf(IS_ROOT, "root may write a read-only file")
    def test_read_only_output_is_refused(self):
        # the review's repro: a chmod 444 output was replaced instead of refused
        src = self.file("draft.svg", GOOD)
        dst = self.file("ro/final.svg", "old")
        dst.chmod(0o444)
        link = self.work / "link.svg"
        link.symlink_to(dst)
        for out in (dst, link):
            r = run("embed.py", src, out)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("not writable", r.stderr)
            self.assertEqual(dst.read_text(encoding="utf-8"), "old")
        self.assertTrue(link.is_symlink())
        self.assertEqual(self.leftovers(dst.parent), [])
        self.assertEqual(self.leftovers(), [])


    @unittest.skipIf(IS_ROOT, "root may write in a read-only folder")
    def test_writable_output_in_a_read_only_folder(self):
        # the review's repro: main rewrote it in place, a temp file beside it was refused
        src = self.file("draft.svg", GOOD)
        dst = self.file("locked/final.svg", "old")
        dst.chmod(0o640)
        dst.parent.chmod(0o555)
        self.addCleanup(dst.parent.chmod, 0o755)
        r = run("embed.py", src, dst)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(dst.read_text(encoding="utf-8"), GOOD)
        self.assertEqual(dst.stat().st_mode & 0o777, 0o640)
        r = run("embed.py", src, dst.parent / "new.svg")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("not writable", r.stderr)
        self.assertEqual(sorted(p.name for p in dst.parent.iterdir()), ["final.svg"])

    def test_long_output_name(self):
        # the review's repro: ENAMETOOLONG from the temp file's longer name
        src = self.file("draft.svg", GOOD)
        dst = self.work / ("b" * 245 + ".svg")
        r = run("embed.py", src, dst)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(dst.read_text(encoding="utf-8"), GOOD)


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

    def test_cli_new_deck_follows_umask(self):
        src = self.file("draft.svg", GOOD)
        for mask, mode in ((0o077, 0o600), (0o002, 0o664)):
            deck = self.work / f"deck-{mask:03o}.pptx"
            r = run("svg2pptx.py", src, "-o", deck, umask=mask)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(deck.stat().st_mode & 0o777, mode, f"umask {mask:03o}")

    @unittest.skipIf(IS_ROOT, "root may write a read-only file")
    def test_read_only_deck_is_refused(self):
        src = self.file("draft.svg", GOOD)
        deck = self.file("ro/deck.pptx", "previous deck")
        deck.chmod(0o444)
        link = self.work / "link.pptx"
        link.symlink_to(deck)
        for out in (deck, link):
            ok, log = self.build([src], out)
            self.assertFalse(ok)
            self.assertIn("not writable", log)
            self.assertEqual(deck.read_text(encoding="utf-8"), "previous deck")
        r = run("svg2pptx.py", src, "-o", deck)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(deck.read_text(encoding="utf-8"), "previous deck")
        self.assertTrue(link.is_symlink())
        self.assertEqual(self.leftovers(deck.parent), [])

    @unittest.skipIf(IS_ROOT, "root may write in a read-only folder")
    def test_cli_writable_deck_in_a_read_only_folder(self):
        # the review's repro: main rewrote it in place, a temp file beside it was refused
        src = self.file("draft.svg", GOOD)
        deck = self.file("locked/deck.pptx", "previous deck")
        deck.chmod(0o640)
        deck.parent.chmod(0o555)
        self.addCleanup(deck.parent.chmod, 0o755)
        r = run("svg2pptx.py", src, "-o", deck)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(deck.read_bytes().startswith(b"PK"))
        self.assertEqual(deck.stat().st_mode & 0o777, 0o640)
        ok, log = self.build([src], deck.parent / "new.pptx")
        self.assertFalse(ok)
        self.assertIn("not writable", log)
        self.assertEqual(sorted(p.name for p in deck.parent.iterdir()), ["deck.pptx"])

    def test_cli_long_deck_name(self):
        src = self.file("draft.svg", GOOD)
        deck = self.work / ("b" * 245 + ".pptx")
        r = run("svg2pptx.py", src, "-o", deck)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(deck.read_bytes().startswith(b"PK"))

    @unittest.skipIf(IS_ROOT, "root may write a read-only file")
    def test_preview_writes_nothing_when_one_slide_is_refused(self):
        src = self.file("draft.svg", GOOD)
        deck = self.work / "deck.pptx"
        self.assertTrue(self.build([src, src], deck)[0])
        locked = self.file("preview-2.png", "old")
        locked.chmod(0o444)
        r = run("render_pptx.py", deck, self.work / "preview")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("not writable", r.stdout)
        self.assertFalse((self.work / "preview-1.png").exists())
        self.assertEqual(locked.read_text(encoding="utf-8"), "old")
        locked.chmod(0o644)
        r = run("render_pptx.py", deck, self.work / "new" / "preview")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(p.name for p in (self.work / "new").iterdir()),
                         ["preview-1.png", "preview-2.png"])

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


class Outfile(Work):
    def test_symlinked_output_writes_its_target(self):
        target = self.file("real/out.svg", "old")
        link = self.work / "out.svg"
        link.symlink_to(target)
        outfile.write(link, b"new")
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_text(encoding="utf-8"), "new")

    def test_mode_kept_and_new_file_follows_umask(self):
        out = self.file("out.svg", "old")
        out.chmod(0o640)
        with umask_set(0o077):
            outfile.write(out, "new")
        self.assertEqual(out.stat().st_mode & 0o777, 0o640)  # a rewritten file keeps its mode
        for mask, mode in ((0o022, 0o644), (0o077, 0o600), (0o002, 0o664)):
            fresh = self.work / f"fresh-{mask:03o}.svg"
            with umask_set(mask):
                outfile.write(fresh, "new")
            self.assertEqual(fresh.stat().st_mode & 0o777, mode, f"umask {mask:03o}")

    def test_hard_linked_output_is_written_in_place(self):
        # as open() does: both names keep naming one file, now holding the new bytes
        out = self.file("out.svg", "old")
        os.link(out, self.work / "other.svg")
        outfile.write(out, "new")
        self.assertTrue(outfile.same_file(out, self.work / "other.svg"))
        self.assertEqual((self.work / "other.svg").read_text(encoding="utf-8"), "new")

    def test_umask_is_never_changed(self):
        # the review's repro: without /proc the umask was read by setting it to 077 and back,
        # so a file another thread created in that instant came out 0600 instead of 0664
        with patch.object(os, "umask", side_effect=AssertionError("umask changed")), \
                patch("builtins.open", wraps=open) as opened:
            outfile.write(self.work / "new.svg", "new")
            outfile.write(self.work / "new.svg", "again")
            outfile.blocked([self.work / "new.svg", self.work / "missing" / "x.svg"])
        self.assertNotIn("/proc/self/status", [str(c.args[0]) for c in opened.call_args_list])
        self.assertEqual((self.work / "new.svg").read_text(encoding="utf-8"), "again")

    def test_long_name(self):
        # the review's repro: a 249-byte name failed as its temp file's name was too long
        out = self.work / ("b" * 245 + ".svg")
        self.assertEqual(outfile.blocked([out]), [])
        outfile.write(out, "new")
        self.assertEqual(out.read_text(encoding="utf-8"), "new")
        self.assertEqual(sorted(p.name for p in self.work.iterdir()), [out.name])

    def test_new_folders_are_made(self):
        out = self.work / "a" / "b" / "out.svg"
        self.assertEqual(outfile.blocked([out]), [])
        outfile.write(out, b"new")
        self.assertEqual(out.read_bytes(), b"new")

    def test_blocked_names_what_open_could_not_write(self):
        flat = self.file("flat", "a file, not a folder")
        (self.work / "dir.svg").mkdir()
        found = dict(outfile.blocked([self.work / "ok.svg", self.work / "dir.svg",
                                      flat / "x.svg", flat / "deeper" / "x.svg"]))
        self.assertEqual(set(found), {self.work / "dir.svg", flat / "x.svg",
                                      flat / "deeper" / "x.svg"})
        self.assertIn("is a folder", found[self.work / "dir.svg"])
        self.assertIn("is not a folder", found[flat / "x.svg"])

    @unittest.skipIf(IS_ROOT, "root may write a read-only file")
    def test_read_only_output_is_blocked(self):
        out = self.file("out.svg", "old")
        out.chmod(0o444)
        link = self.work / "link.svg"
        link.symlink_to(out)
        found = outfile.blocked([out, link, self.work / "missing.svg"])
        self.assertEqual([p for p, _ in found], [out, link])
        self.assertTrue(all("not writable" in why for _, why in found))

    @unittest.skipIf(IS_ROOT, "root may write in a read-only folder")
    def test_read_only_folder(self):
        # the review's repro: a writable file in a 0555 folder is writable to open(), and
        # must stay so; only a new file there is refused
        folder = self.work / "locked"
        old = self.file("locked/out.svg", "old")
        old.chmod(0o640)
        folder.chmod(0o555)
        self.addCleanup(folder.chmod, 0o755)
        new = folder / "new.svg"
        dangling = self.work / "dangling.svg"
        dangling.symlink_to(folder / "target.svg")
        found = dict(outfile.blocked([old, new, folder / "sub" / "x.svg", dangling]))
        self.assertEqual(set(found), {new, folder / "sub" / "x.svg", dangling})
        self.assertTrue(all("not writable" in why for why in found.values()))
        outfile.write(old, "new")
        self.assertEqual(old.read_text(encoding="utf-8"), "new")
        self.assertEqual(old.stat().st_mode & 0o777, 0o640)
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["out.svg"])

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
