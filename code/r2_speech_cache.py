"""Content-addressed speech-clip cache backed by a private Cloudflare R2 bucket."""

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError
from speech_cache import SpeechCache

CHUNK_SIZE = 1024 * 1024
CACHE_PREFIX = "clips/v1/"
SAFE_CACHE_KEY = re.compile(r"[A-Za-z0-9_.-]+")


class SpeechCacheError(RuntimeError):
    pass


class R2SpeechCache(SpeechCache):
    def __init__(self, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    @classmethod
    def from_environment(cls) -> "R2SpeechCache":
        names = (
            "R2_ACCOUNT_ID",
            "R2_CACHE_ACCESS_KEY_ID",
            "R2_CACHE_SECRET_ACCESS_KEY",
            "R2_CACHE_BUCKET",
        )
        missing = [name for name in names if not os.environ.get(name)]
        if missing:
            raise SpeechCacheError(f"Missing R2 cache settings: {', '.join(missing)}")
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "s3",
            endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ["R2_CACHE_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_CACHE_SECRET_ACCESS_KEY"],
            region_name="auto",
            config=Config(
                retries={"max_attempts": 5, "mode": "standard"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
        return cls(client, os.environ["R2_CACHE_BUCKET"])

    @staticmethod
    def _object_key(key: str) -> str:
        if not SAFE_CACHE_KEY.fullmatch(key) or key in {".", ".."}:
            raise SpeechCacheError(f"Unsafe speech cache key: {key!r}")
        return f"{CACHE_PREFIX}{key}"

    @staticmethod
    def _error_code(error: Exception) -> str:
        response = getattr(error, "response", None) or {}
        return str(response.get("Error", {}).get("Code", ""))

    @staticmethod
    def _digest(path: Path) -> tuple[int, str]:
        digest, size = hashlib.sha256(), 0
        with path.open("rb") as source:
            while chunk := source.read(CHUNK_SIZE):
                digest.update(chunk)
                size += len(chunk)
        return size, digest.hexdigest()

    def fetch(self, key: str, destination: Path) -> bool:
        object_key = self._object_key(key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=object_key)
        except ClientError as error:
            if self._error_code(error) in {"NoSuchKey", "404", "NotFound"}:
                return False
            raise

        body = response["Body"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=destination.parent, prefix=f".{destination.name}.", delete=False
            ) as output:
                temp_path = Path(output.name)
                while chunk := body.read(CHUNK_SIZE):
                    output.write(chunk)
            actual_size, actual_sha256 = self._digest(temp_path)
            expected_size = response.get("ContentLength")
            expected_sha256 = response.get("Metadata", {}).get("sha256")
            if (
                actual_size == 0
                or actual_size != expected_size
                or actual_sha256 != expected_sha256
            ):
                raise SpeechCacheError(
                    f"Corrupt speech cache object {object_key}: "
                    f"expected {expected_size} bytes and SHA-256 {expected_sha256}, "
                    f"got {actual_size} bytes and SHA-256 {actual_sha256}"
                )
            temp_path.replace(destination)
            return True
        finally:
            body.close()
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def store(self, key: str, source: Path) -> None:
        object_key = self._object_key(key)
        size, sha256 = self._digest(source)
        if size == 0:
            raise SpeechCacheError(f"Refusing to cache empty speech clip: {source}")
        try:
            with source.open("rb") as body:
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=object_key,
                    Body=body,
                    ContentType="audio/mpeg",
                    Metadata={"sha256": sha256},
                    IfNoneMatch="*",
                )
        except ClientError as error:
            if self._error_code(error) not in {"PreconditionFailed", "412"}:
                raise
            if not self.fetch(key, source):
                raise SpeechCacheError(
                    f"Speech cache object {object_key} already exists but could not be fetched"
                ) from error
