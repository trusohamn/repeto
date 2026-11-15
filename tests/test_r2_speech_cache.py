import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from r2_speech_cache import R2SpeechCache, SpeechCacheError  # pyright: ignore[reportMissingImports]
from botocore.exceptions import ClientError


class FakeR2Client:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, dict[str, str]]] = {}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        try:
            data, metadata = self.objects[Key]
        except KeyError as error:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject") from error
        return {
            "Body": io.BytesIO(data),
            "ContentLength": len(data),
            "Metadata": metadata,
        }

    def put_object(self, *, Bucket: str, Key: str, Body: Any, Metadata: dict[str, str],
                   IfNoneMatch: str, **kwargs: Any) -> None:
        if Key in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.objects[Key] = (Body.read(), Metadata)


class R2SpeechCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.client = FakeR2Client()
        self.cache = R2SpeechCache(self.client, "private-cache")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_fetch_verifies_metadata_and_writes_only_requested_clip(self) -> None:
        key, content = "en_azure_abc.mp3", b"speech clip"
        self.client.objects[f"clips/v1/{key}"] = (
            content,
            {"sha256": hashlib.sha256(content).hexdigest()},
        )
        destination = self.root / key

        self.assertTrue(self.cache.fetch(key, destination))
        self.assertEqual(destination.read_bytes(), content)
        self.assertEqual(list(self.root.iterdir()), [destination])

    def test_fetch_returns_false_for_missing_object(self) -> None:
        self.assertFalse(self.cache.fetch("missing.mp3", self.root / "missing.mp3"))

    def test_fetch_refuses_corrupt_object_without_replacing_existing_file(self) -> None:
        key = "en_azure_corrupt.mp3"
        self.client.objects[f"clips/v1/{key}"] = (b"bad", {"sha256": "wrong"})
        destination = self.root / key
        destination.write_bytes(b"keep")

        with self.assertRaises(SpeechCacheError):
            self.cache.fetch(key, destination)

        self.assertEqual(destination.read_bytes(), b"keep")
        self.assertEqual(list(self.root.iterdir()), [destination])

    def test_store_is_immutable_and_reuses_canonical_existing_clip(self) -> None:
        key, canonical, generated = "en_azure_abc.mp3", b"canonical", b"generated"
        self.client.objects[f"clips/v1/{key}"] = (
            canonical,
            {"sha256": hashlib.sha256(canonical).hexdigest()},
        )
        source = self.root / key
        source.write_bytes(generated)

        self.cache.store(key, source)

        self.assertEqual(source.read_bytes(), canonical)
        self.assertEqual(self.client.objects[f"clips/v1/{key}"][0], canonical)

    def test_store_rejects_empty_clips(self) -> None:
        source = self.root / "empty.mp3"
        source.touch()

        with self.assertRaises(SpeechCacheError):
            self.cache.store(source.name, source)

    def test_rejects_cache_path_traversal(self) -> None:
        with self.assertRaises(SpeechCacheError):
            self.cache.fetch("../outside.mp3", self.root / "outside.mp3")


if __name__ == "__main__":
    unittest.main()
