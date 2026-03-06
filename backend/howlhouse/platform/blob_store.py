from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

try:  # pragma: no cover - optional runtime dependency for s3 mode
    import boto3
    from botocore.exceptions import ClientError
except Exception:  # pragma: no cover
    boto3 = None

    class ClientError(Exception):
        pass


class BlobStore(Protocol):
    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None: ...

    def get_bytes(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def uri_for_key(self, key: str) -> str: ...

    def put_text(self, key: str, text: str, encoding: str = "utf-8") -> None:
        self.put_bytes(key, text.encode(encoding), content_type="text/plain; charset=utf-8")

    def get_text(self, key: str, encoding: str = "utf-8") -> str:
        return self.get_bytes(key).decode(encoding)


def _normalize_key(key: str) -> str:
    normalized = key.strip().lstrip("/")
    parts = [part for part in normalized.split("/") if part and part != "."]
    if not parts:
        raise ValueError("blob key must not be empty")
    if any(part == ".." for part in parts):
        raise ValueError("blob key must not contain '..'")
    return "/".join(parts)


@dataclass
class LocalBlobStore:
    base_dir: Path

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path_for_key(self, key: str) -> Path:
        normalized = _normalize_key(key)
        return self.base_dir / Path(normalized)

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None:
        path = self._path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get_bytes(self, key: str) -> bytes:
        return self._path_for_key(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path_for_key(key).exists()

    def uri_for_key(self, key: str) -> str:
        return f"local://{_normalize_key(key)}"

    def put_text(self, key: str, text: str, encoding: str = "utf-8") -> None:
        self.put_bytes(key, text.encode(encoding), content_type="text/plain; charset=utf-8")

    def get_text(self, key: str, encoding: str = "utf-8") -> str:
        return self.get_bytes(key).decode(encoding)


@dataclass
class S3BlobStore:
    bucket: str
    prefix: str
    _client: object

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        region: str,
        access_key: str,
        secret_key: str,
        prefix: str = "",
    ):
        if boto3 is None:
            raise RuntimeError("boto3 is required for HOWLHOUSE_BLOB_STORE=s3")
        clean_prefix = prefix.strip().strip("/")
        self.prefix = f"{clean_prefix}/" if clean_prefix else ""
        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def _object_key(self, key: str) -> str:
        return f"{self.prefix}{_normalize_key(key)}"

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None:
        kwargs: dict[str, object] = {
            "Bucket": self.bucket,
            "Key": self._object_key(key),
            "Body": data,
        }
        if content_type:
            kwargs["ContentType"] = content_type
        self._client.put_object(**kwargs)

    def get_bytes(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self.bucket, Key=self._object_key(key))
        return response["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=self._object_key(key))
            return True
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def uri_for_key(self, key: str) -> str:
        return f"s3://{self.bucket}/{self._object_key(key)}"

    def put_text(self, key: str, text: str, encoding: str = "utf-8") -> None:
        self.put_bytes(key, text.encode(encoding), content_type="text/plain; charset=utf-8")

    def get_text(self, key: str, encoding: str = "utf-8") -> str:
        return self.get_bytes(key).decode(encoding)


def create_blob_store(settings) -> BlobStore:
    mode = settings.blob_store.strip().lower()
    if mode == "local":
        return LocalBlobStore(settings.blob_base_dir)
    if mode == "s3":
        if not settings.s3_bucket:
            raise ValueError("HOWLHOUSE_S3_BUCKET is required when HOWLHOUSE_BLOB_STORE=s3")
        if not settings.s3_access_key or not settings.s3_secret_key:
            raise ValueError(
                "HOWLHOUSE_S3_ACCESS_KEY and HOWLHOUSE_S3_SECRET_KEY are required for s3 mode"
            )
        return S3BlobStore(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint,
            region=settings.s3_region,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            prefix=settings.s3_prefix,
        )
    raise ValueError("HOWLHOUSE_BLOB_STORE must be one of: local, s3")
