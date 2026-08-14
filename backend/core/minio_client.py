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
    """Bucket for project marketing images — public GetObject so the frontend can
    load images directly.

    Unlike the internal document bucket (`minio_bucket_documents`), which must stay private.
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
    """Public URL for an object — FOR THE BROWSER, not for the backend.

    Uses `minio_public_endpoint` rather than `minio_endpoint`: inside Docker the
    backend reaches MinIO via the service name `minio:9000`, but this URL is
    returned to the frontend and rendered in an <img> tag, and a browser on the
    host machine cannot resolve the hostname `minio` — the image would break. If
    the variable is unset, falls back to `minio_endpoint` (correct when running
    the backend outside Docker).
    """
    settings = get_settings()
    scheme = "https" if settings.minio_secure else "http"
    endpoint = settings.minio_public_endpoint or settings.minio_endpoint
    return f"{scheme}://{endpoint}/{bucket}/{object_name}"


def presigned_get_url(bucket: str, object_name: str, expires_minutes: int = 10) -> str:
    """Temporary signed link to view a file in a private bucket (internal document
    store) without switching the bucket to public-read."""
    client = get_minio_client()
    return client.presigned_get_object(bucket, object_name, expires=timedelta(minutes=expires_minutes))
