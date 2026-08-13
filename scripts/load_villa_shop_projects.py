"""Nap 7 du an moi crawl (3 tieu khu Biet thu + 4 Shop TMDV) vao bang `projects`.

Nguon: seed-data/villas-shops/ (Hai Au, Ngoc Trai, Sao Bien, Shop BH9B/HA08/SB11A/SH09)
— moi file JSON dung dinh dang giong het the_zurich.json/the_sapphire.json...
(project/pricing/amenities/images/contact), anh da duoc copy vao
project-images-source/<slug>/ (xem upload_project_images.py).

File JSON nam TRONG repo (khong phai duong dan ngoai may) de may nao clone repo
ve chay script nay cung ra ket qua giong nhau.

Chay THEO THU TU:
    1. python scripts/upload_project_images.py   (nap anh len MinIO truoc)
    2. python scripts/load_villa_shop_projects.py (nap JSON + gan gallery URL)
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

# (ten file json, slug du an — phai KHOP dung id "project.id" ben trong file
# va ten thu muc trong project-images-source/ da copy anh vao).
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
                raise ValueError(f"Slug lech: config={slug} nhung json project.id={project_info['id']}")

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
            # 3 tieu khu Biet thu co full_name da bat dau bang "Tieu khu ..." —
            # FE (TowerSpotlight) tu them chu "Tieu khu" truoc ten khi hien thi,
            # dung full_name se bi lap ("Tieu khu Tieu khu Hai Au..."). Dung ten
            # ngan + hau to du an cho nhat quan voi cac du an khac (vd "The
            # Zurich - Vinhomes Ocean Park").
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
