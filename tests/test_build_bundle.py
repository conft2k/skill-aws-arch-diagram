#!/usr/bin/env python3
"""build_bundle.build() writes the icon bundle safely under concurrency and failure.

    python3 tests/test_build_bundle.py

Every test packs a tiny fake package into a bundle in a temporary directory (OUT patched),
so the real assets/icons.json is never read or written and nothing is downloaded.
  - two builds that reach the rename at the same moment both succeed, and the bundle left
    behind is complete JSON with no temp file beside it;
  - a write or rename that fails keeps the previous bundle byte for byte and removes that
    run's temp file.
"""
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_bundle  # noqa: E402


class BuildBundleTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.work = Path(self._dir.name)
        self.package = self.work / "package"
        icon = (self.package / "Architecture-Service-Icons_test" / "Compute" / "64"
                / "Arch_Test_64.svg")
        icon.parent.mkdir(parents=True)
        icon.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
        self.bundle_dir = self.work / "assets"
        self.out = self.bundle_dir / "icons.json"
        patcher = patch.object(build_bundle, "OUT", self.out)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._dir.cleanup)

    def build(self, label="test"):
        with redirect_stderr(io.StringIO()):
            build_bundle.build(self.package, label)

    def leftovers(self):
        return sorted(p.name for p in self.bundle_dir.iterdir() if p != self.out)

    def test_concurrent_builds_both_succeed(self):
        # Hold both runs at the rename onto the bundle until both have written their temp
        # file: the interleaving that made the second run's rename miss a shared temp path.
        barrier = threading.Barrier(2)
        original_replace = os.replace
        sources = []

        def synchronized_replace(src, dst):
            if Path(dst) == self.out:
                sources.append(Path(src))
                barrier.wait(timeout=5)
            return original_replace(src, dst)

        def worker(label):
            try:
                self.build(label)
                return "ok"
            except Exception as error:  # noqa: BLE001 - report the failure kind
                return type(error).__name__

        with patch.object(build_bundle.os, "replace", synchronized_replace), \
                ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, ["run-a", "run-b"]))

        self.assertEqual(results, ["ok", "ok"])
        self.assertEqual(len(set(sources)), 2, "each run must write its own temp file")
        self.assertTrue(all(src.parent == self.bundle_dir for src in sources))
        bundle = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertIn(bundle["package"], {"run-a", "run-b"})
        self.assertEqual(list(bundle["sets"]["service"]), ["Test"])
        self.assertEqual(self.leftovers(), [])

    def test_bundle_is_readable_file(self):
        self.build()
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o644)
        self.assertEqual(self.leftovers(), [])

    def assert_failure_keeps_old_bundle(self, target, error):
        self.build("old")
        before = self.out.read_bytes()
        with patch.object(build_bundle.os, target, side_effect=error), \
                self.assertRaises(type(error)):
            self.build("new")
        self.assertEqual(self.out.read_bytes(), before)
        self.assertEqual(self.leftovers(), [])

    def test_failed_write_keeps_old_bundle(self):
        # fsync runs after the text is written, so this is a failure mid-write (disk full).
        self.assert_failure_keeps_old_bundle("fsync", OSError(28, "No space left on device"))

    def test_failed_rename_keeps_old_bundle(self):
        self.assert_failure_keeps_old_bundle("replace", PermissionError(13, "Permission denied"))

    def test_interrupted_write_keeps_old_bundle(self):
        self.assert_failure_keeps_old_bundle("fsync", KeyboardInterrupt())


if __name__ == "__main__":
    unittest.main()
