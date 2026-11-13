import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
import unittest.mock
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

CODE = Path(__file__).resolve().parents[1] / "code"


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, CODE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audio_publish = _load("audio_publish")
podcast = audio_publish.podcast


class CorruptingStorage(audio_publish.DirectoryStorage):
    def put_new(self, key: str, path: Path, sha256: str) -> bool:
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"truncated")
        return True


class ClientError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeBody:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def iter_chunks(self, size: int):
        for start in range(0, len(self.data), size):
            yield self.data[start:start + size]


class FakeR2Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.puts: list[dict[str, Any]] = []

    def get_object(self, Bucket: str, Key: str) -> dict[str, Any]:
        if Key not in self.objects:
            raise ClientError("NoSuchKey")
        return {"Body": FakeBody(self.objects[Key])}

    def put_object(self, **kwargs: Any) -> None:
        self.puts.append({key: value for key, value in kwargs.items() if key != "Body"})
        if kwargs.get("IfNoneMatch") == "*" and kwargs["Key"] in self.objects:
            raise ClientError("PreconditionFailed")
        self.objects[kwargs["Key"]] = kwargs["Body"].read()


class AudioPublishTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / "podcast"
        self.bucket = base / "bucket"
        self.course = self.root / "swedish-polish"
        (self.course / "audio/practice").mkdir(parents=True)
        (self.course / "cover.jpeg").write_bytes(b"cover")
        self.catalog_path = self.course / "course.json"
        self.catalog = {
            "title": "Kurs", "description": "Beskrivning", "language": "sv",
            "author": "Repeto.stream", "email": "repeto.stream@gmail.com",
            "episodes": [
                {"id": f"repeto:swedish-polish:topic-0{number}", "title": f"Ämne {number}",
                 "file": f"practice/0{number}_topic.mp3", "duration_ms": 1000,
                 "published": "2026-10-27T14:00:00+00:00", "description": "Text.",
                 "season": 1, "episode": number}
                for number in (1, 2)
            ],
        }
        self._write_catalog()
        self.first = self.course / "audio/practice/01_topic.mp3"
        self.second = self.course / "audio/practice/02_topic.mp3"
        self.first.write_bytes(b"first audio")
        self.second.write_bytes(b"second audio")

    def _write_catalog(self) -> None:
        self.catalog_path.write_text(
            json.dumps(self.catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def _episodes(self) -> list[dict[str, Any]]:
        return json.loads(self.catalog_path.read_text(encoding="utf-8"))["episodes"]

    def _run(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = audio_publish.main([*args])
        return code, out.getvalue(), err.getvalue()

    def test_plan_lists_unpublished_audio_without_storage(self):
        code, out, _ = self._run("plan", "--root", str(self.root))
        self.assertEqual(code, 0)
        self.assertIn("swedish-polish/audio/practice/01_topic.mp3\t11\t", out)
        self.assertIn("2 file(s) to publish.", out)
        self.assertFalse(self.bucket.exists())

    def test_publish_uploads_verifies_records_and_removes_local_audio(self):
        code, out, err = self._run(
            "publish", "--root", str(self.root), "--storage", str(self.bucket), "--remove-local",
        )
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Published 2 file(s).", out)
        stored = self.bucket / "swedish-polish/audio/practice/01_topic.mp3"
        self.assertEqual(stored.read_bytes(), b"first audio")
        self.assertFalse(self.first.exists())
        first = self._episodes()[0]
        self.assertEqual(first["bytes"], 11)
        self.assertEqual(first["sha256"], hashlib.sha256(b"first audio").hexdigest())
        self.assertEqual(self._run("plan", "--root", str(self.root))[1].strip(),
                         "0 file(s) to publish.")
        self.assertEqual(self._run("check", "--root", str(self.root),
                                   "--storage", str(self.bucket))[0], 0)

        podcast.build_feed(self.course, "https://repeto.stream", "https://audio.example")
        enclosure = ET.parse(self.course / "feed.xml").find("./channel/item/enclosure")
        assert enclosure is not None
        self.assertEqual(enclosure.get("url"),
                         "https://audio.example/swedish-polish/audio/practice/01_topic.mp3")
        self.assertEqual(enclosure.get("length"), "11")

    def test_paths_limit_publishing_and_must_be_referenced(self):
        code, _, _ = self._run("publish", "--root", str(self.root),
                               "--storage", str(self.bucket), str(self.second))
        self.assertEqual(code, 0)
        self.assertNotIn("sha256", self._episodes()[0])
        self.assertIn("sha256", self._episodes()[1])

        stray = self.course / "audio/practice/stray.mp3"
        stray.write_bytes(b"stray")
        code, _, err = self._run("publish", "--root", str(self.root),
                                 "--storage", str(self.bucket), str(stray))
        self.assertEqual(code, 1)
        self.assertIn("not referenced by any course.json", err)

    def test_identical_stored_audio_is_reused_and_different_audio_is_refused(self):
        key = self.bucket / "swedish-polish/audio/practice/01_topic.mp3"
        key.parent.mkdir(parents=True)
        key.write_bytes(b"first audio")
        logs: list[str] = []
        items = audio_publish.pending_audio(self.root, [self.first])
        audio_publish.publish(audio_publish.DirectoryStorage(self.bucket), items, logs.append)
        self.assertEqual(logs, ["Reused and verified: swedish-polish/audio/practice/01_topic.mp3"])

        key.write_bytes(b"other audio")
        with self.assertRaisesRegex(audio_publish.PublishError, "Different audio is already"):
            audio_publish.publish(audio_publish.DirectoryStorage(self.bucket), items, logs.append)
        self.assertEqual(key.read_bytes(), b"other audio")

    def test_failed_verification_records_nothing_and_keeps_local_audio(self):
        items = audio_publish.pending_audio(self.root)
        with self.assertRaisesRegex(audio_publish.PublishError, "failed verification"):
            audio_publish.publish(CorruptingStorage(self.bucket), items, lambda _: None)
        self.assertTrue(self.first.exists())
        self.assertNotIn("sha256", self._episodes()[0])

    def test_local_audio_that_differs_from_published_metadata_is_refused(self):
        self._run("publish", "--root", str(self.root), "--storage", str(self.bucket))
        self.first.write_bytes(b"changed audio")
        with self.assertRaisesRegex(audio_publish.PublishError, "differs from published"):
            audio_publish.pending_audio(self.root)
        with self.assertRaisesRegex(ValueError, "differs from published metadata"):
            podcast.build_feed(self.course, "https://repeto.stream")

    def test_check_reports_missing_and_changed_objects(self):
        self._run("publish", "--root", str(self.root), "--storage", str(self.bucket))
        (self.bucket / "swedish-polish/audio/practice/01_topic.mp3").unlink()
        (self.bucket / "swedish-polish/audio/practice/02_topic.mp3").write_bytes(b"x")
        problems = audio_publish.check_published(
            audio_publish.DirectoryStorage(self.bucket), self.root,
        )
        self.assertEqual(problems, [
            "Missing: swedish-polish/audio/practice/01_topic.mp3",
            "Different: swedish-polish/audio/practice/02_topic.mp3",
        ])

    def test_require_audio_fails_when_nothing_is_pending(self):
        self._run("publish", "--root", str(self.root), "--storage", str(self.bucket))
        code, _, err = self._run("publish", "--root", str(self.root),
                                 "--storage", str(self.bucket), "--require-audio")
        self.assertEqual(code, 1)
        self.assertIn("No audio to publish", err)

    def test_r2_storage_uses_conditional_immutable_uploads(self):
        client = FakeR2Client()
        storage = audio_publish.R2Storage(client, "repeto-audio")
        items = audio_publish.pending_audio(self.root, [self.first])
        audio_publish.publish(storage, items, lambda _: None)
        key = "swedish-polish/audio/practice/01_topic.mp3"
        self.assertEqual(client.objects[key], b"first audio")
        self.assertEqual(client.puts[0], {
            "Bucket": "repeto-audio", "Key": key, "ContentType": "audio/mpeg",
            "CacheControl": "public, max-age=31536000, immutable",
            "Metadata": {"sha256": items[0].sha256}, "IfNoneMatch": "*",
        })
        self.assertFalse(storage.put_new(key, self.second, "unused"))
        self.assertEqual(client.objects[key], b"first audio")
        self.assertIsNone(storage.digest("absent.mp3"))

    def test_r2_settings_are_required(self):
        with unittest.mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(audio_publish.PublishError, "R2_ACCOUNT_ID"):
                audio_publish.R2Storage.from_environment()


class FeedMetadataTests(unittest.TestCase):
    def test_invalid_or_partial_metadata_is_rejected(self):
        for episode in ({"bytes": 5}, {"bytes": 0, "sha256": "a" * 64},
                        {"bytes": 5, "sha256": "not-a-digest"}, {"bytes": True, "sha256": "a" * 64}):
            with self.subTest(episode=episode):
                with self.assertRaisesRegex(ValueError, "Invalid published audio metadata"):
                    podcast.published_audio({"id": "x", **episode})
        self.assertIsNone(podcast.published_audio({"id": "x"}))

    def test_repackaging_keeps_metadata_only_for_the_same_file(self):
        previous = {"file": "practice/a.mp3", "bytes": 5, "sha256": "a" * 64}
        self.assertEqual(
            podcast.carry_audio_metadata(previous, {"file": "practice/a.mp3"}),
            {"file": "practice/a.mp3", "bytes": 5, "sha256": "a" * 64},
        )
        self.assertEqual(
            podcast.carry_audio_metadata(previous, {"file": "practice/b.mp3"}),
            {"file": "practice/b.mp3"},
        )


if __name__ == "__main__":
    unittest.main()
