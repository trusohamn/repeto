import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from audio_staging import (  # pyright: ignore[reportMissingImports]
    StagingTarget,
    StagingPrefixStorage,
    StagedAudio,
    StagingError,
    input_fingerprint,
    make_manifest,
    promote_manifest,
    read_manifest,
    safe_input_path,
    write_manifest,
)


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def digest(self, key: str) -> tuple[int, str] | None:
        content = self.objects.get(key)
        if content is None:
            return None
        return len(content), hashlib.sha256(content).hexdigest()

    def put_new(self, key: str, path: Path, sha256: str) -> bool:
        if key in self.objects:
            return False
        self.objects[key] = path.read_bytes()
        return True

    def download(self, key: str, destination: Path) -> bool:
        content = self.objects.get(key)
        if content is None:
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return True

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


class AudioStagingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.content = b"reviewed episode"
        self.sha256 = hashlib.sha256(self.content).hexdigest()
        self.item = StagedAudio(
            course="english-polish",
            episode_id="repeto:english-polish:topic-01",
            file="practice/01_greetings_en_pl.mp3",
            staging_key=(
                "staging/pr-12/"
                "0123456789abcdef0123456789abcdef01234567/"
                "english-polish/audio/practice/01_greetings_en_pl.mp3"
            ),
            size=len(self.content),
            sha256=self.sha256,
        )
        self.target = StagingTarget("practice", "english-polish", "en", "pl")
        input_path = self.root / "courses/practice/transcript.json"
        input_path.parent.mkdir(parents=True)
        input_path.write_text('[{"id": 1, "en": "Hello", "pl": "Cześć"}]', encoding="utf-8")
        self._write(
            self.root / "podcast/english-polish/course.json",
            {
                "episodes": [
                    {
                        "id": self.item.episode_id,
                        "file": self.item.file,
                        "bytes": self.item.size,
                        "sha256": self.item.sha256,
                    }
                ]
            },
        )
        self.input_sha256 = input_fingerprint(self.root, [self.target])
        self.manifest = make_manifest(
            12,
            "0123456789abcdef0123456789abcdef01234567",
            self.input_sha256,
            [self.target],
            [self.item],
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _write(path: Path, data: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_manifest_round_trips_and_retains_revision_binding(self) -> None:
        path = write_manifest(self.root, self.manifest)

        self.assertEqual(
            path,
            self.root
            / ".audio-staging"
            / "pr-12-0123456789abcdef0123456789abcdef01234567.json",
        )
        self.assertEqual(read_manifest(path), self.manifest)
        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8"))["items"][0]["episode_id"],
            self.item.episode_id,
        )

    def test_promotes_exact_verified_bytes_and_removes_public_staging_copy(self) -> None:
        storage = FakeStorage()
        storage.objects[self.item.staging_key] = self.content

        count = promote_manifest(self.manifest, storage, self.root)

        self.assertEqual(count, 1)
        self.assertEqual(storage.objects[self.item.production_key], self.content)
        self.assertNotIn(self.item.staging_key, storage.objects)

    def test_prefix_storage_binds_object_keys_to_reviewed_pr_revision(self) -> None:
        storage = FakeStorage()
        prefixed = StagingPrefixStorage(
            storage, self.manifest.pull_request, self.manifest.approved_sha
        )
        path = self.root / "episode.mp3"
        path.write_bytes(self.content)

        self.assertTrue(prefixed.put_new(self.item.production_key, path, self.sha256))
        self.assertEqual(storage.objects, {self.item.staging_key: self.content})

    def test_matching_production_object_makes_retry_idempotent(self) -> None:
        storage = FakeStorage()
        storage.objects[self.item.production_key] = self.content
        storage.objects[self.item.staging_key] = self.content

        self.assertEqual(promote_manifest(self.manifest, storage, self.root), 0)
        self.assertEqual(storage.objects, {self.item.production_key: self.content})
        self.assertEqual(promote_manifest(self.manifest, storage, self.root), 0)

    def test_completed_promotion_does_not_block_on_later_source_edits(self) -> None:
        source = self.root / "courses/practice/transcript.json"
        source.write_text('[{"id": 1, "en": "Later edit", "pl": "Cześć"}]', encoding="utf-8")
        storage = FakeStorage()
        storage.objects[self.item.production_key] = self.content

        self.assertEqual(promote_manifest(self.manifest, storage, self.root), 0)

    def test_refuses_different_production_content_without_deleting_stage(self) -> None:
        storage = FakeStorage()
        storage.objects[self.item.production_key] = b"different production audio"
        storage.objects[self.item.staging_key] = self.content

        with self.assertRaisesRegex(StagingError, "differs from reviewed audio"):
            promote_manifest(self.manifest, storage, self.root)

        self.assertIn(self.item.staging_key, storage.objects)

    def test_refuses_missing_or_corrupt_stage_content(self) -> None:
        storage = FakeStorage()
        with self.assertRaisesRegex(StagingError, "missing or differs"):
            promote_manifest(self.manifest, storage, self.root)

        storage.objects[self.item.staging_key] = b"different bytes"
        with self.assertRaisesRegex(StagingError, "missing or differs"):
            promote_manifest(self.manifest, storage, self.root)

    def test_refuses_promotion_after_source_data_changes(self) -> None:
        source = self.root / "courses/practice/transcript.json"
        source.write_text('[{"id": 1, "en": "Changed", "pl": "Cześć"}]', encoding="utf-8")
        storage = FakeStorage()
        storage.objects[self.item.staging_key] = self.content

        with self.assertRaisesRegex(StagingError, "Source data no longer matches"):
            promote_manifest(self.manifest, storage, self.root)

    def test_refuses_promotion_when_catalog_audio_metadata_differs(self) -> None:
        catalog = self.root / "podcast/english-polish/course.json"
        data = json.loads(catalog.read_text(encoding="utf-8"))
        data["episodes"][0]["sha256"] = "0" * 64
        catalog.write_text(json.dumps(data), encoding="utf-8")
        storage = FakeStorage()
        storage.objects[self.item.staging_key] = self.content

        with self.assertRaisesRegex(StagingError, "Catalog metadata does not match"):
            promote_manifest(self.manifest, storage, self.root)

    def test_input_paths_reject_symlinks_within_the_checkout(self) -> None:
        external = self.root / "outside.json"
        external.write_text("{}", encoding="utf-8")
        link = self.root / "courses/practice/linked.json"
        link.symlink_to(external)

        with self.assertRaisesRegex(StagingError, "must not be a symlink"):
            safe_input_path(self.root, "courses/practice/linked.json")

    def test_manifest_rejects_path_traversal_and_revision_mismatch(self) -> None:
        unsafe = StagedAudio(
            course="english-polish",
            episode_id=self.item.episode_id,
            file="../secrets.mp3",
            staging_key=self.item.staging_key,
            size=self.item.size,
            sha256=self.item.sha256,
        )
        with self.assertRaises(StagingError):
            make_manifest(
                self.manifest.pull_request,
                self.manifest.approved_sha,
                self.input_sha256,
                [self.target],
                [unsafe],
            )

        changed_key = StagedAudio(
            course=self.item.course,
            episode_id=self.item.episode_id,
            file=self.item.file,
            staging_key=self.item.staging_key.replace("pr-12", "pr-13"),
            size=self.item.size,
            sha256=self.item.sha256,
        )
        with self.assertRaises(StagingError):
            make_manifest(
                self.manifest.pull_request,
                self.manifest.approved_sha,
                self.input_sha256,
                [self.target],
                [changed_key],
            )


if __name__ == "__main__":
    unittest.main()
