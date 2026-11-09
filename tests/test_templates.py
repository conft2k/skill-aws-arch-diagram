#!/usr/bin/env python3
"""The starter templates (templates/*.layout.yaml) draw cleanly in every mode, as SKILL.md promises.

    python3 tests/test_templates.py

Each template is run through layout.py's main() as a document, a titled slide and an untitled
slide (a `mode: slide` template, the slide twin of a document template, as a slide only); the engine's last line must be a plain `Layout OK` (no rule violation left) and no
`rule:` line may be printed. The corpus also tags them good; this test fails the suite when one
stops passing.
"""
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import layout  # noqa: E402

TEMPLATES = sorted((ROOT / "templates").glob("*.layout.yaml"))
MODES = {"document": ["--mode", "document"], "slide": ["--mode", "slide"],
         "slide-no-title": ["--mode", "slide", "--no-title"]}


class Templates(unittest.TestCase):
    def test_the_templates(self):
        self.assertEqual([p.name for p in TEMPLATES],
                         ["cloudfront-vpc-origin.layout.yaml", "dx-vpn-tgw-slide.layout.yaml",
                          "dx-vpn-tgw.layout.yaml", "multi-account-egress.layout.yaml"])

    def test_every_template_is_clean_in_every_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            for spec in TEMPLATES:
                slide_only = "\nmode: slide" in spec.read_text(encoding="utf-8")
                for mode, args in MODES.items():
                    if slide_only and mode == "document":
                        continue
                    with self.subTest(template=spec.name, mode=mode):
                        out = io.StringIO()
                        with redirect_stdout(out):
                            status = layout.main([str(spec), "-o", str(Path(tmp) / f"{spec.stem}-{mode}.draft.svg"), *args])
                        lines = out.getvalue().strip().splitlines()
                        self.assertEqual(status, 0, out.getvalue())
                        self.assertEqual(lines[-1], "Layout OK", out.getvalue())
                        self.assertFalse([ln for ln in lines if ln.startswith("rule:")], out.getvalue())

    def test_every_line_to_change_is_marked(self):
        for spec in TEMPLATES:
            with self.subTest(template=spec.name):
                text = spec.read_text(encoding="utf-8")
                self.assertTrue(text.startswith("# Starter template:"))
                self.assertIn("# EDIT", text)


if __name__ == "__main__":
    unittest.main()
