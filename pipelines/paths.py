"""Single source of truth for filesystem locations.

Every pipeline resolves data files through the constants defined here rather
than computing a repository root of its own.

D-0025 records why this module exists: three pipelines each computed their
own repository root, one of them resolved a directory too shallow, and the
result was the shadow-copy defect in F-0004. See docs/decisions.md.
"""

from pathlib import Path

# pipelines/paths.py -> parents[0] is pipelines/, parents[1] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
