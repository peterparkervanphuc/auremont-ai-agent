"""Nap du lieu demo (anh -> MinIO, catalogue -> MySQL) ngay khi backend khoi dong.

Truoc day phai chay tay 3 script sau khi `docker compose up`; ai bo qua buoc do se
thay trang Tra cuu trong tron va toan bo anh vo — khong co tin hieu nao chi ra
nguyen nhan. Muc tieu cua module nay: clone repo, `docker compose up`, xong.

Anh du an KHONG nam trong git (~58 MB). Chung song tren S3/R2 va duoc tai
ve MinIO o day, theo danh sach trong seed-data/project_images_manifest.json.

Co hai nguon:

* `PROJECT_IMAGES_BASE_URL` — thu muc cong khai (R2 public URL, S3 public, CDN),
  ghep base + duong dan trong manifest. Doc an danh: khong can credentials, nen
  khong phai phat tan API key cho ca team chi de xem anh.
* `PROJECT_IMAGES_ARCHIVE_URL` — mot file .tar.gz duy nhat; mot request thay vi ~180.

Ba tinh chat bat buoc:

* **Idempotent** — bo qua anh da co tren MinIO va bo qua han buoc nap khi catalogue
  da co du lieu, nen restart khong ton cong tai lai ~180 anh.
* **Khong bao gio chan khoi dong** — nguon loi, MinIO chua san sang hay thieu bien
  moi truong chi lam hong du lieu demo, khong phai ly do de ca API sap.
* **Khong tu y ra Internet khi chua duoc cau hinh** — thieu ca hai bien thi bo qua
  im lang kem mot dong log, khong doan mo URL.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import BinaryIO, cast
from urllib.parse import urljoin

from backend.core.config import get_settings
from backend.core.mysql_client import SessionLocal
from backend.models.project import Project

logger = logging.getLogger(__name__)

# Tai song song: ~180 file nho, phan lon thoi gian la doi mang chu khong phai CPU.
_DOWNLOAD_WORKERS = 8
_DOWNLOAD_TIMEOUT_SECONDS = 30
# Archive ~53 MB: rong rai hon nhieu so voi mot anh le, de mang cham van kip.
_ARCHIVE_TIMEOUT_SECONDS = 300


def _catalogue_is_loaded() -> bool:
    """True khi da co it nhat mot project kem `details` (tuc da nap catalogue).

    `/projects` loc bo row khong co `details`, nen day dung la dieu kien quyet
    dinh trang Tra cuu co hien gi hay khong.
    """
    db = SessionLocal()
    try:
        # Loc o tang Python chu khong bang `.isnot(None)`: cot JSON cua MySQL phan
        # biet JSON `null` voi SQL NULL, nen `IS NOT NULL` van khop voi row co
        # details = JSON null — dung query se tuong catalogue da nap va bo qua.
        return any(row.details for row in db.query(Project).all())
    finally:
        db.close()


def _read_manifest() -> list[str]:
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "seed-data" / "project_images_manifest.json"
    if not path.exists():
        logger.warning("Khong thay manifest anh tai %s — bo qua buoc tai anh.", path)
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("images", [])


def _download_archive_to_minio(archive_url: str) -> int:
    """Tai mot .tar.gz chua toan bo anh roi nap vao MinIO. Tra ve so anh da nap moi."""
    import tarfile
    import tempfile

    import httpx
    from minio.error import S3Error

    from backend.core.minio_client import ensure_public_read_bucket, get_minio_client

    settings = get_settings()
    bucket = settings.minio_bucket_project_images
    ensure_public_read_bucket(bucket)
    client = get_minio_client()

    existing = {o.object_name for o in client.list_objects(bucket, recursive=True)}
    wanted = set(_read_manifest())
    if wanted and wanted <= existing:
        return 0

    # Ghi ra dia thay vi giu trong RAM: tarfile can seek, va 53 MB nen khong nen
    # nam trong bo nho cua process web.
    with tempfile.TemporaryDirectory() as tmp:
        archive_path = f"{tmp}/images.tar.gz"
        with httpx.stream("GET", archive_url, timeout=_ARCHIVE_TIMEOUT_SECONDS, follow_redirects=True) as resp:
            resp.raise_for_status()
            with open(archive_path, "wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                    fh.write(chunk)

        loaded = 0
        with tarfile.open(archive_path, "r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                # `tar -czf . ` sinh tien to "./"; manifest thi khong co.
                name = member.name.lstrip("./")
                # Chan path traversal: mot archive doc hai co the chua "../.."
                # va ghi de object ngoai pham vi du dinh.
                if name.startswith("/") or ".." in name.split("/"):
                    logger.warning("Bo qua duong dan bat thuong trong archive: %r", member.name)
                    continue
                if name in existing:
                    continue
                member_stream = tar.extractfile(member)
                if member_stream is None:
                    continue
                try:
                    client.put_object(bucket, name, cast(BinaryIO, member_stream), length=member.size)
                    loaded += 1
                except S3Error:
                    logger.warning("Nap anh '%s' vao MinIO that bai.", name, exc_info=True)
    return loaded


def _download_images_to_minio(base_url: str) -> int:
    """Tai anh tu CDN vao MinIO. Tra ve so anh da tai moi."""
    import httpx
    from minio.error import S3Error

    from backend.core.minio_client import ensure_public_read_bucket, get_minio_client

    settings = get_settings()
    bucket = settings.minio_bucket_project_images
    ensure_public_read_bucket(bucket)
    client = get_minio_client()

    images = _read_manifest()
    if not images:
        return 0

    def fetch_one(object_name: str) -> bool:
        try:
            # Da co tren MinIO thi thoi — day la phan lam cho restart re.
            try:
                client.stat_object(bucket, object_name)
                return False
            except S3Error:
                pass

            url = urljoin(base_url.rstrip("/") + "/", object_name)
            resp = httpx.get(url, timeout=_DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True)
            resp.raise_for_status()
            # put_object doi doi tuong co .read(); generator cua httpx khong dung duoc.
            # Anh du an chi vai tram KB nen giu ca file trong RAM la chap nhan duoc.
            client.put_object(
                bucket,
                object_name,
                BytesIO(resp.content),
                length=len(resp.content),
                content_type=resp.headers.get("content-type", "image/jpeg"),
            )
            return True
        except Exception:
            logger.warning("Tai anh '%s' that bai.", object_name, exc_info=True)
            return False

    with ThreadPoolExecutor(max_workers=_DOWNLOAD_WORKERS) as pool:
        return sum(pool.map(fetch_one, images))


def load_demo_data() -> None:
    settings = get_settings()
    if not settings.auto_load_demo_data:
        return

    try:
        if _catalogue_is_loaded():
            logger.info("Catalogue da co du lieu — bo qua buoc nap demo.")
            return
    except Exception:
        # Bang chua ton tai (chua `alembic upgrade head`) hay MySQL chua san sang.
        # Cu thu nap ben duoi; neu van hong thi cac khoi except o do se ghi log.
        logger.warning("Khong kiem tra duoc trang thai catalogue.", exc_info=True)

    # Archive truoc (mot request thay vi ~180), roi base URL.
    archive_url = settings.project_images_archive_url
    base_url = settings.project_images_base_url

    if archive_url:
        try:
            count = _download_archive_to_minio(archive_url)
            logger.info("Nap anh du an tu archive xong — %d anh moi.", count)
        except Exception:
            logger.error("Nap anh du an tu archive that bai — trang Tra cuu se thieu anh.", exc_info=True)
    elif base_url:
        try:
            count = _download_images_to_minio(base_url)
            logger.info("Tai anh du an vao MinIO xong — %d anh moi.", count)
        except Exception:
            logger.error("Tai anh du an that bai — trang Tra cuu se thieu anh.", exc_info=True)
    else:
        logger.warning(
            "Chua dat PROJECT_IMAGES_BASE_URL hay PROJECT_IMAGES_ARCHIVE_URL — bo qua "
            "buoc tai anh, catalogue se hien thi khong co anh."
        )

    # Import trong ham: cac script nay cham MinIO/MySQL ngay o module scope, khong
    # nen keo theo luc import app (test va alembic cung import backend.main).
    from scripts.load_apartment_projects import main as load_apartments
    from scripts.load_villa_shop_projects import main as load_villas_and_shops
    from scripts.load_vinhomes_ocean_park import main as load_ocean_park

    for label, loader in (
        ("vinhomes-ocean-park", load_ocean_park),
        ("villas-shops", load_villas_and_shops),
        ("apartments", load_apartments),
    ):
        try:
            loader()
            logger.info("Nap catalogue '%s' thanh cong.", label)
        except Exception:
            logger.error("Nap catalogue '%s' that bai — trang Tra cuu se thieu du lieu.", label, exc_info=True)
