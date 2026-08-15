"""Gallery URLs derived from the image manifest.

Original images live on a public R2 bucket and are never checked into git, so a
fresh clone has the manifest but no local image directory to scan.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.config import get_settings  # noqa: E402

MANIFEST_PATH = REPO_ROOT / "seed-data" / "project_images_manifest.json"


def gallery_by_slug() -> dict[str, list[str]]:
    if not MANIFEST_PATH.exists():
        return {}

    base_url = get_settings().project_images_base_url.rstrip("/")
    grouped: dict[str, list[str]] = {}
    for key in json.loads(MANIFEST_PATH.read_text(encoding="utf-8")).get("images", []):
        slug, _, filename = key.partition("/")
        if filename:
            grouped.setdefault(slug, []).append(f"{base_url}/{key}")
    return grouped
