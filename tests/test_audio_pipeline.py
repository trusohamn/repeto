import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import audio_pipeline  # pyright: ignore[reportMissingImports]
from audio_staging import read_manifest  # pyright: ignore[reportMissingImports]


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


class AudioPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.root.joinpath("courses/practice").mkdir(parents=True)
        self.root.joinpath("podcast/english-polish").mkdir(parents=True)
        self.root.joinpath("courses/practice/transcript.json").write_text(
            json.dumps(
                [
                    {
                        "id": "phrase_000001",
                        "topic": "Greetings",
                        "se": "Hej",
                        "en": "Hello",
                        "pl": "Cześć",
                        "ru": "Привет",
                    }
                ]
            ),
            encoding="utf-8",
        )
        self.root.joinpath("courses/practice/topics.json").write_text(
            json.dumps({"Greetings": {"en": "Greetings", "pl": "Powitania"}}),
            encoding="utf-8",
        )
        (self.root / "podcast/english-polish/cover.jpeg").write_bytes(b"cover")
        (self.root / "podcast/english-polish/course.json").write_text(
            json.dumps(
                {
                    "source_language": "en",
                    "target_language": "pl",
                    "episodes": [
                        {
                            "id": "repeto:english-polish:topic-01",
                            "file": "practice/old.mp3",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Audio Pipeline Test"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"], cwd=self.root, check=True
        )
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "test input"], cwd=self.root, check=True)
        self.approved_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.targets = self.root / "targets.json"
        self.targets.write_text(
            json.dumps(
                [
                    {
                        "kind": "practice",
                        "course": "english-polish",
                        "source": "en",
                        "target": "pl",
                    }
                ]
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_preflight_accepts_fingerprinted_course_cover(self) -> None:
        cover = self.root / "podcast/english-polish/cover.jpeg"
        cover.rename(cover.with_name("cover-12345678.jpeg"))
        audio_pipeline._catalog_target(
            audio_pipeline.AudioTarget("practice", "english-polish", "en", "pl"),
            self.root,
        )

    def test_preflight_rejects_symlinked_fingerprinted_cover(self) -> None:
        cover = self.root / "podcast/english-polish/cover.jpeg"
        external = self.root / "outside.jpeg"
        cover.rename(external)
        cover.with_name("cover-12345678.jpeg").symlink_to(external)
        with self.assertRaisesRegex(audio_pipeline.StagingError, "must not be a symlink"):
            audio_pipeline._catalog_target(
                audio_pipeline.AudioTarget("practice", "english-polish", "en", "pl"),
                self.root,
            )

    def test_story_renderer_uses_approved_checkout_for_relative_root(self) -> None:
        self.targets.write_text(
            json.dumps([{
                "kind": "story",
                "course": "english-french",
                "source": "en",
                "target": "fr",
                "story_id": "magical_radio",
                "chapters": [4],
            }]),
            encoding="utf-8",
        )
        commands: list[list[str]] = []

        def fake_run(command: list[str], root: Path) -> None:
            commands.append(command)
            self.assertEqual(root, self.root.resolve())
            self.assertEqual(command[command.index("--chapter") + 1], "4")
            if "--validate-only" not in command:
                podcast_root = Path(command[command.index("--podcast-root") + 1])
                self.assertEqual(podcast_root, self.root.resolve() / "podcast")
                raise RuntimeError("renderer invoked")

        with (
            patch("audio_pipeline._catalog_target"),
            patch("audio_pipeline._validate_generation_environment"),
            patch("audio_pipeline.input_fingerprint", return_value="fingerprint"),
            patch("audio_pipeline._run", side_effect=fake_run),
            self.assertRaisesRegex(RuntimeError, "renderer invoked"),
        ):
            audio_pipeline.stage_audio(
                Path(os.path.relpath(self.root)),
                self.targets,
                42,
                self.approved_sha,
                self.root / "reports",
            )
        self.assertEqual(len(commands), 2)

    def test_rejects_invalid_story_chapter_selection(self) -> None:
        for chapters in ([1, 1], [True], [0], ["1"]):
            with self.subTest(chapters=chapters):
                self.targets.write_text(json.dumps([{
                    "kind": "story", "course": "english-french", "source": "en",
                    "target": "fr", "story_id": "magical_radio", "chapters": chapters,
                }]), encoding="utf-8")
                with self.assertRaisesRegex(audio_pipeline.PipelineError, "chapters"):
                    audio_pipeline._read_targets(self.targets)

    def test_stages_audio_and_commits_only_metadata_manifest(self) -> None:
        audio_bytes = b"generated practice audio"
        storage = FakeStorage()

        def fake_run(command: list[str], root: Path) -> None:
            if "transcription.py" in command[1]:
                if "--validate-only" in command:
                    return
                output = Path(command[command.index("--output") + 1])
                output.mkdir(parents=True, exist_ok=True)
                (output / "01_greetings_en_pl_double_test.mp3").write_bytes(audio_bytes)
            elif "package_practice.py" in command[1]:
                args = {
                    command[index]: command[index + 1]
                    for index in range(1, len(command) - 1)
                    if command[index].startswith("--")
                }
                render = next(Path(args["--renders"]).glob("*.mp3"))
                course = Path(args["--podcast-root"]) / args["--course"]
                audio = course / "audio/practice" / render.name
                audio.parent.mkdir(parents=True, exist_ok=True)
                audio.write_bytes(render.read_bytes())
                catalog_path = course / "course.json"
                catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
                catalog["episodes"] = [
                    {
                        "id": "repeto:english-polish:topic-01",
                        "file": f"practice/{render.name}",
                    }
                ]
                catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            else:
                raise AssertionError(f"Unexpected trusted command: {command}")

        with (
            patch.dict(
                "os.environ",
                {
                    "AZURE_SPEECH_KEY": "test",
                    "AZURE_SPEECH_REGION": "test",
                    "R2_ACCOUNT_ID": "test",
                    "R2_ACCESS_KEY_ID": "test",
                    "R2_SECRET_ACCESS_KEY": "test",
                    "R2_BUCKET": "test",
                    "R2_CACHE_BUCKET": "test",
                    "R2_CACHE_ACCESS_KEY_ID": "test",
                    "R2_CACHE_SECRET_ACCESS_KEY": "test",
                },
            ),
            patch("audio_pipeline._run", side_effect=fake_run),
            patch(
                "audio_pipeline.audio_publish.R2Storage.from_environment",
                return_value=storage,
            ),
            patch("audio_pipeline.audio_publish.podcast.build_feed"),
        ):
            manifest_path = audio_pipeline.stage_audio(
                self.root, self.targets, 42, self.approved_sha, self.root / "reports"
            )

        manifest = read_manifest(manifest_path)
        self.assertEqual(manifest.pull_request, 42)
        self.assertEqual(manifest.approved_sha, self.approved_sha)
        self.assertEqual(len(manifest.items), 1)
        staged = manifest.items[0]
        self.assertEqual(storage.objects[staged.staging_key], audio_bytes)
        self.assertNotIn(staged.production_key, storage.objects)
        self.assertFalse((self.root / "podcast/english-polish/audio" / staged.file).exists())
        self.assertTrue((self.root / "podcast/english-polish/course.json").is_file())
        report = (self.root / "reports/audio-report-1.md").read_text(encoding="utf-8")
        self.assertIn("Public audio staging is ready", report)
        self.assertIn(staged.staging_key, report)
        self.assertFalse(
            (
                self.root
                / "podcast/english-polish/audio/practice"
                / Path(staged.file).name
            ).exists()
        )

    def test_missing_service_credentials_fail_before_rendering(self) -> None:
        with (
            patch.dict(
                "os.environ",
                {
                    name: ""
                    for name in (
                        "AZURE_SPEECH_KEY",
                        "AZURE_SPEECH_REGION",
                        "R2_ACCOUNT_ID",
                        "R2_ACCESS_KEY_ID",
                        "R2_SECRET_ACCESS_KEY",
                        "R2_BUCKET",
                        "R2_CACHE_BUCKET",
                        "R2_CACHE_ACCESS_KEY_ID",
                        "R2_CACHE_SECRET_ACCESS_KEY",
                    )
                },
            ),
            patch("audio_pipeline._run") as run,
        ):
            with self.assertRaisesRegex(audio_pipeline.PipelineError, "Missing generation"):
                audio_pipeline.stage_audio(
                    self.root, self.targets, 42, self.approved_sha, self.root / "reports"
                )

        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
