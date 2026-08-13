import json
from datetime import timedelta
from functools import lru_cache

from minio import Minio

from backend.core.config import get_settings


@lru_cache
def get_minio_client() -> Minio:
    settings = get_settings()
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def ensure_bucket(bucket: str) -> None:
    client = get_minio_client()
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def ensure_public_read_bucket(bucket: str) -> None:
    """Bucket cho ảnh marketing dự án — public GetObject để frontend load ảnh trực tiếp.

    Khác với bucket tài liệu nội bộ (`minio_bucket_documents`), vốn phải giữ private.
    """
    ensure_bucket(bucket)
    client = get_minio_client()
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/*"],
            }
        ],
    }
    client.set_bucket_policy(bucket, json.dumps(policy))


def public_object_url(bucket: str, object_name: str) -> str:
    """URL cong khai cho object — DUNG CHO TRINH DUYET, khong phai cho backend.

    Dung `minio_public_endpoint` chu khong phai `minio_endpoint`: trong Docker,
    backend noi toi MinIO qua service name `minio:9000`, nhung URL nay duoc tra
    ve cho frontend va render trong the <img>, ma trinh duyet tren may host
    khong phan giai duoc hostname `minio` — anh se hong. Khong dat bien thi quay
    ve `minio_endpoint` (dung khi chay backend ngoai Docker).
    """
    settings = get_settings()
    scheme = "https" if settings.minio_secure else "http"
    endpoint = settings.minio_public_endpoint or settings.minio_endpoint
    return f"{scheme}://{endpoint}/{bucket}/{object_name}"


def presigned_get_url(bucket: str, object_name: str, expires_minutes: int = 10) -> str:
    """Link tạm thời có chữ ký để xem file trong bucket private (kho tài liệu nội bộ)
    mà không cần đổi bucket sang public-read."""
    client = get_minio_client()
    return client.presigned_get_object(bucket, object_name, expires=timedelta(minutes=expires_minutes))
