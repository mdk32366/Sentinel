"""Record which `ui/src` the committed bundle was built from.

F-0027: the Dockerfile has no Node stage, so `api/static/` is the contract —
whatever is committed there is what production serves. A change to `ui/src`
that is not followed by `npm run build` and a copy into `api/static/` ships a
stale UI **with no signal at all**. That happened often enough this week that
it is worth a guard rather than a habit.

This writes a manifest naming the exact `ui/src` content the bundle came from.
`tests/test_ui_bundle_freshness.py` recomputes it, so forgetting the rebuild
fails the gate instead of shipping quietly.

Run it after every `npm run build` + copy:

    cd ui && npm run build
    cp dist/index.html ../api/static/index.html
    cp dist/assets/* ../api/static/assets/
    python tools/record_ui_build.py
"""
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
UI_SRC = REPO_ROOT / "ui" / "src"
STATIC = REPO_ROOT / "api" / "static"
MANIFEST = STATIC / "BUILD_MANIFEST.json"

# Only files that can change what the bundle contains.
SOURCE_SUFFIXES = {".js", ".jsx", ".ts", ".tsx", ".css"}


def ui_source_digest() -> str:
    """A stable hash over every source file Vite compiles into the bundle.

    Paths are included so a rename is a change, and files are walked in sorted
    order so the digest does not depend on filesystem ordering.
    """
    digest = hashlib.sha256()
    for path in sorted(UI_SRC.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        digest.update(path.relative_to(UI_SRC).as_posix().encode("utf-8"))
        # normalise line endings: git may check out CRLF on Windows and LF in
        # CI, and that must not read as a source change.
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def served_bundle() -> str:
    index = STATIC / "index.html"
    if not index.exists():
        return ""
    import re

    match = re.search(r"assets/(index-[A-Za-z0-9_-]+\.js)", index.read_text(encoding="utf-8"))
    return match.group(1) if match else ""


def main() -> int:
    payload = {
        "ui_src_sha256": ui_source_digest(),
        "bundle": served_bundle(),
        "recorded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    MANIFEST.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"ui/src sha256 : {payload['ui_src_sha256']}")
    print(f"bundle        : {payload['bundle'] or '(none found)'}")
    print(f"written       : {MANIFEST.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
