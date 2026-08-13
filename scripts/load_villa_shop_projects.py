"""Load 7 newly crawled projects (3 Villa sub-zones + 4 Retail Shop units) into the `projects` table.

Source: seed-data/villas-shops/ (Hai Au, Ngoc Trai, Sao Bien, Shop BH9B/HA08/SB11A/SH09)
— each JSON file follows the same shape as the_zurich.json/the_sapphire.json...
(project/pricing/amenities/images/contact); images have already been copied into
project-images-source/<slug>/ (see upload_project_images.py).

The JSON files live INSIDE the repo (not an external path) so that cloning the repo
on any machine and running this script produces identical results.

Run IN ORDER:
    1. python scripts/upload_project_images.py   (upload images to MinIO first)
    2. python scripts/load_villa_shop_projects.py (load JSON + attach gallery URLs)
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.core.config import get_settings  # noqa: E402
from backend.core.minio_client import public_object_url  # noqa: E402
from backend.core.mysql_client import SessionLocal  # noqa: E402
from backend.models.project import Project  # noqa: E402

SOURCE_JSON_DIR = REPO_ROOT / "seed-data" / "villas-shops"
IMAGES_SOURCE_DIR = REPO_ROOT / "project-images-source"

# (json filename, project slug — MUST match "project.id" inside the file
# and the folder name in project-images-source/ where images were copied).
PROJECTS = [
    ("hai_au.json", "hai-au"),
    ("ngoc_trai.json", "ngoc-trai"),
    ("sao_bien.json", "sao-bien"),
    ("shop_thuong_mai_bh9b.json", "shop-thuong-mai-bh9b"),
    ("shop_thuong_mai_ha08.json", "shop-thuong-mai-ha08"),
    ("shop_thuong_mai_sb11a.json", "shop-thuong-mai-sb11a"),
    ("shop_thuong_mai_sh09.json", "shop-thuong-mai-sh09"),
]


def main() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        for json_name, slug in PROJECTS:
            json_path = SOURCE_JSON_DIR / json_name
            details = json.loads(json_path.read_text(encoding="utf-8"))

            project_info = details["project"]
            if project_info["id"] != slug:
                raise ValueError(f"Slug mismatch: config={slug} but json project.id={project_info['id']}")

            images_dir = IMAGES_SOURCE_DIR / slug
            gallery = [
                public_object_url(settings.minio_bucket_project_images, f"{slug}/{p.name}")
                for p in sorted(images_dir.glob("*"))
                if p.is_file()
            ]
            details.setdefault("images", {})["gallery"] = gallery

            location = project_info.get("location") or {}
            location_str = ", ".join(filter(None, [location.get("district"), location.get("city")])) or None

            row = db.get(Project, slug)
            if row is None:
                row = Project(id=slug)
                db.add(row)
            # The 3 Villa sub-zones have full_name already starting with "Tieu khu ..." —
            # the FE (TowerSpotlight) prepends "Tieu khu" itself when rendering, so using
            # full_name as-is would duplicate it ("Tieu khu Tieu khu Hai Au..."). Use the
            # short name + project suffix instead, for consistency with other projects
            # (e.g. "The Zurich - Vinhomes Ocean Park").
            short_name = project_info.get("name") or ""
            row.name = (
                f"{short_name} - Vinhomes Ocean Park"
                if short_name and "tiểu khu" in (project_info.get("full_name") or "").lower()
                else project_info.get("full_name") or short_name
            )
            row.location = location_str
            row.description = project_info.get("description")
            row.details = details

            print(f"[db] upsert {slug} — {len(gallery)} anh gallery")

        db.commit()
        print(f"\nXong — da nap {len(PROJECTS)} du an.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
