"""F-0027 — the committed bundle must match the committed `ui/src`.

The Dockerfile has no Node stage, so `api/static/` IS the contract: whatever is
committed there is what production serves. A change to `ui/src` that is not
followed by `npm run build` and a copy into `api/static/` ships a stale UI, and
**nothing anywhere says so** — the app loads, every endpoint answers, and the
interface is simply the old one.

This turns that silence into a failed gate. It needs no Node: the manifest
written by `tools/record_ui_build.py` records the `ui/src` digest the bundle
came from, and this recomputes it.

What it does NOT prove: that the bundle was built from that source correctly,
only that the source has not moved since it was recorded. Building in CI would
prove more, and `F-0027` remains open for that reason.
"""
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "api" / "static" / "BUILD_MANIFEST.json"

import sys

sys.path.insert(0, str(REPO_ROOT / "tools"))
from record_ui_build import served_bundle, ui_source_digest  # noqa: E402


class TestUiBundleFreshness(unittest.TestCase):
    def setUp(self):
        self.assertTrue(
            MANIFEST.exists(),
            "api/static/BUILD_MANIFEST.json is missing. Run "
            "`python tools/record_ui_build.py` after building the UI.",
        )
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_ui_src_matches_the_recorded_build(self):
        """The one that fails when someone edits ui/src and forgets to build."""
        self.assertEqual(
            ui_source_digest(),
            self.manifest["ui_src_sha256"],
            "ui/src has changed since the committed bundle was built. Run:\n"
            "  cd ui && npm run build\n"
            "  cp dist/index.html ../api/static/index.html\n"
            "  cp dist/assets/* ../api/static/assets/\n"
            "  python tools/record_ui_build.py\n"
            "Production serves api/static/, so without this it ships the old UI "
            "with no signal (F-0027).",
        )

    def test_the_recorded_bundle_is_the_one_being_served(self):
        """A manifest naming a bundle that index.html does not reference would
        pass the digest check while describing a different build."""
        self.assertEqual(served_bundle(), self.manifest["bundle"])

    def test_the_served_bundle_exists_on_disk(self):
        """index.html referencing a missing asset is a blank page in
        production and a 200 from every health check."""
        bundle = served_bundle()
        self.assertTrue(bundle, "index.html references no JS bundle")
        self.assertTrue(
            (REPO_ROOT / "api" / "static" / "assets" / bundle).exists(),
            f"index.html references {bundle}, which is not in api/static/assets/",
        )

    def test_the_digest_actually_discriminates(self):
        """Clause (c). A digest that ignored file contents would match
        everything and prove nothing."""
        real = ui_source_digest()
        self.assertEqual(len(real), 64)
        self.assertNotEqual(real, "0" * 64)

    def test_only_one_bundle_is_present(self):
        """A leftover bundle from a previous build is dead weight in the image
        and makes it ambiguous which one was meant to ship."""
        bundles = list((REPO_ROOT / "api" / "static" / "assets").glob("index-*.js"))
        self.assertEqual(
            len(bundles), 1,
            f"expected exactly one JS bundle, found {[b.name for b in bundles]}",
        )


if __name__ == "__main__":
    unittest.main()
