import asyncio
import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydub import AudioSegment
from pydub.generators import Sine

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "story_course", ROOT / "code/story_course.py"
)
assert SPEC and SPEC.loader
story_course = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(story_course)


def tone(duration: int = 100) -> AudioSegment:
    return Sine(440, sample_rate=44100).to_audio_segment(duration=duration)


def mini_story() -> dict:
    return {
        "story_id": "test_story",
        "titles": {"pl": "Kot", "sv": "Katten", "en": "The Cat"},
        "chapters": [
            {
                "chapter_number": 1,
                "titles": {"pl": "Kot", "sv": "Katten", "en": "The Cat"},
                "chapter_text": {
                    "pl": "Kot śpi.",
                    "sv": "Katten sover.",
                    "en": "The cat is sleeping.",
                },
                "vocabulary": [
                    {"id": 1, "text": {"pl": "mały kot", "sv": "liten katt", "en": "little cat"}}
                ],
            }
        ],
    }


class StoryCourseTests(unittest.TestCase):
    def test_real_story_validates_and_reconstructs_source(self):
        story = story_course.load_transcript(
            ROOT / "courses/swedish-polish/stories/magical_radio/generated/transcript.json",
            ROOT / "courses/swedish-polish/stories/magical_radio/complete/pl.txt",
        )
        self.assertEqual(story["story_id"], "magical_radio")
        self.assertEqual(len(story["chapters"]), 8)
        identifiers = [
            item["id"]
            for chapter in story["chapters"]
            for collection in ("vocabulary",)
            for item in chapter[collection]
        ]
        self.assertEqual(len(set(identifiers)), len(identifiers))

    def test_each_chapter_has_beginner_vocabulary_coverage(self):
        story = story_course.load_transcript(
            ROOT / "courses/swedish-polish/stories/magical_radio/generated/transcript.json",
            ROOT / "courses/swedish-polish/stories/magical_radio/complete/pl.txt",
        )
        for chapter in story["chapters"]:
            with self.subTest(chapter=chapter["chapter_number"]):
                self.assertGreaterEqual(len(chapter["vocabulary"]), 15)

    def test_vocabulary_ids_are_unique_across_story(self):
        data = mini_story()
        data["chapters"][0]["vocabulary"].append(
            {"id": 1, "text": {"pl": "kot", "sv": "katt", "en": "cat"}}
        )
        with self.assertRaisesRegex(ValueError, "duplicate story-wide id"):
            story_course.validate_transcript(data)

    def test_text_languages_must_match_titles(self):
        data = mini_story()
        data["chapters"][0]["vocabulary"][0]["text"].pop("en")
        with self.assertRaisesRegex(ValueError, "exactly"):
            story_course.validate_transcript(data)

    def test_additional_languages_do_not_require_renderer_changes(self):
        data = mini_story()
        data["titles"]["de"] = "Die Katze"
        data["chapters"][0]["titles"]["de"] = "Die Katze"
        data["chapters"][0]["vocabulary"][0]["text"]["de"] = "kleine Katze"
        data["chapters"][0]["chapter_text"]["de"] = "Die Katze schläft."
        self.assertIs(story_course.validate_transcript(data), data)

    def test_parse_source_requires_consecutive_chapters(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pl.txt"
            path.write_text(
                "Rozdział 1: Jeden\nTekst.\nRozdział 3: Trzy\nDalej.",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "consecutive"):
                story_course.parse_source(path)

    def test_polish_text_must_match_source_exactly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "pl.txt"
            transcript = root / "transcript.json"
            source.write_text("Rozdział 1: Kot\nKot śpi.", encoding="utf-8")
            data = mini_story()
            data["chapters"][0]["chapter_text"]["pl"] = "Kot biega."
            transcript.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "chapter text does not reproduce"):
                story_course.load_transcript(transcript, source)

    def test_language_overrides_are_parsed(self):
        self.assertEqual(
            story_course._parse_language_settings(
                ["pl=pl-PL-ZofiaNeural", "sv=sv-SE-SofieNeural"], "--voice"
            ),
            {"pl": "pl-PL-ZofiaNeural", "sv": "sv-SE-SofieNeural"},
        )
        with self.assertRaisesRegex(ValueError, "LANG=VALUE"):
            story_course._parse_language_settings(["pl"], "--voice")

    def test_practice_precedes_complete_chapter_reading(self):
        chapter = mini_story()["chapters"][0]
        clips = {1: (tone(), tone())}
        track, manifest = story_course._compose_track(
            chapter,
            "sv",
            "pl",
            clips,
            tone(300),
            lead_in_ms=10,
            thinking_ms=20,
            repetition_ms=30,
        )
        self.assertEqual([entry["kind"] for entry in manifest["practice"]], [
            "vocabulary"
        ])
        self.assertEqual(manifest["practice"][0]["prompt_language"], "pl")
        for entry in manifest["practice"]:
            self.assertEqual(len(entry["target_playbacks"]), 2)
            prompt = entry["prompt"]
            first, second = entry["target_playbacks"]
            self.assertEqual(first["start_ms"] - prompt["end_ms"], 20)
            self.assertEqual(second["start_ms"] - first["end_ms"], 30)
        self.assertEqual(
            manifest["chapter_reading"]["start_ms"],
            manifest["practice"][-1]["end_ms"],
        )
        self.assertEqual(track[manifest["chapter_reading"]["start_ms"]:].rms, tone(300).rms)

    def test_vocabulary_practice_order_is_shuffled_and_reproducible(self):
        chapter = mini_story()["chapters"][0]
        for identifier in range(2, 7):
            chapter["vocabulary"].append({
                "id": identifier,
                "text": {
                    "pl": f"polish {identifier}",
                    "sv": f"swedish {identifier}",
                    "en": f"english {identifier}",
                },
            })
        clips = {identifier: (tone(), tone()) for identifier in range(1, 7)}
        first_manifest = story_course._compose_track(
            chapter, "sv", "pl", clips, tone(300), 10, 20, 30
        )[1]
        second_manifest = story_course._compose_track(
            chapter, "sv", "pl", clips, tone(300), 10, 20, 30
        )[1]
        first_order = [entry["id"] for entry in first_manifest["practice"]]
        self.assertNotEqual(first_order, list(range(1, 7)))
        self.assertEqual(first_order, [entry["id"] for entry in second_manifest["practice"]])
        self.assertEqual(first_manifest["practice_order"], "deterministically_shuffled")

    def test_book_title_is_introduced_before_practice_in_first_chapter_only(self):
        chapter = mini_story()["chapters"][0]
        _, first = story_course._compose_track(
            chapter, "pl", "sv", {1: (tone(), tone())}, tone(300),
            10, 20, 30, story_title="Kot. Wielka przygoda",
            book_intro_clip=tone(150),
        )
        self.assertEqual(first["book_introduction"]["text"], "Kot. Wielka przygoda.")
        self.assertEqual(first["book_introduction"]["start_ms"], 10)
        self.assertEqual(
            first["practice"][0]["start_ms"],
            first["book_introduction"]["end_ms"],
        )
        self.assertEqual(first["chapter_reading"]["text"], "Kot śpi.")
        second_chapter = {**chapter, "chapter_number": 2}
        _, second = story_course._compose_track(
            second_chapter, "pl", "sv", {1: (tone(), tone())}, tone(300),
            10, 20, 30, story_title="Kot. Wielka przygoda",
        )
        self.assertIsNone(second["book_introduction"])
        self.assertEqual(second["chapter_reading"]["text"], "Kot śpi.")

    def test_render_exports_all_targets_and_timestamp_manifests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "transcript.json"
            source = root / "pl.txt"
            output = root / "audio"
            cache = root / "cache"
            build_manifest = root / "manifest.json"
            transcript.write_text(json.dumps(mini_story()), encoding="utf-8")
            source.write_text("Rozdział 1: Kot\nKot śpi.", encoding="utf-8")
            args = story_course.create_parser().parse_args([
                "--transcript", str(transcript),
                "--source-text", str(source),
                "--output", str(output),
                "--cache", str(cache),
                "--build-manifest", str(build_manifest),
                "--target", "sv", "en",
                "--source-language", "pl",
                "--format", "wav",
            ])
            with patch.object(
                story_course, "_clip", new_callable=AsyncMock, return_value=tone()
            ):
                result = asyncio.run(story_course.render_story(args))
            self.assertEqual(set(result["chapters"]["1"]["targets"]), {"sv", "en"})
            for target in ("sv", "en"):
                data = result["chapters"]["1"]["targets"][target]
                self.assertTrue((output / data["audio_file"]).is_file())
                manifest = json.loads((output / data["manifest_file"]).read_text())
                self.assertEqual(manifest["target_language"], target)
                self.assertEqual(len(manifest["practice"]), 1)

    def test_story_packaging_appends_to_existing_matching_feed(self):
        source_catalog = ROOT / "podcast/swedish-polish/course.json"
        catalog_data = json.loads(source_catalog.read_text(encoding="utf-8"))
        catalog_data["episodes"] = catalog_data["episodes"][:2]
        catalog_data["source_language"] = "sv"
        catalog_data["target_language"] = "pl"
        chapter = mini_story()["chapters"][0]
        transcript = {
            "story_id": "test_story",
            "titles": {"pl": "Testowa historia", "sv": "Testberättelsen", "en": "Test Story"},
            "chapters": [chapter],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            course = root / "podcast" / "swedish-polish"
            audio_dir = course / "audio"
            audio_dir.mkdir(parents=True)
            (course / "cover.jpeg").write_bytes(b"existing cover")
            for episode in catalog_data["episodes"]:
                audio = audio_dir / episode["file"]
                audio.parent.mkdir(parents=True, exist_ok=True)
                audio.write_bytes(b"existing audio")
            catalog_path = course / "course.json"
            catalog_path.write_text(json.dumps(catalog_data), encoding="utf-8")
            audio_source_dir = root / "render"
            audio_source_dir.mkdir()
            audio_name = "01_chapter_01_sv_pl_2026-10-27_22-00-00.mp3"
            (audio_source_dir / audio_name).write_bytes(b"story audio")
            args = argparse.Namespace(
                podcast_course="swedish-polish",
                source_language="sv",
                transcript=root / "story" / "generated" / "transcript.json",
                cover=None,
                email="repeto.lingo@gmail.com",
                podcast_root=root / "podcast",
                podcast_base_url="https://example.com/repeto",
                author="Repeto",
                output=audio_source_dir,
            )
            build = {
                "settings": {"target_languages": ["pl"]},
                "chapters": {
                    "1": {
                        "targets": {
                            "pl": {
                                "audio_file": audio_name,
                                "total_duration_ms": 8400,
                            }
                        }
                    }
                },
            }
            story_course.package_podcasts(args, transcript, build)
            original_dates = [
                episode["published"] for episode in catalog_data["episodes"]
            ]
            result = json.loads(catalog_path.read_text(encoding="utf-8"))
            self.assertEqual(len(result["episodes"]), 3)
            self.assertEqual(
                [episode["published"] for episode in result["episodes"][:2]],
                original_dates,
            )
            added = result["episodes"][2]
            self.assertEqual(added["id"], "test_story:sv:pl:chapter-01")
            self.assertEqual((added["season"], added["episode"]), (2, 1))
            self.assertEqual(added["file"], f"stories/test_story/{audio_name}")
            self.assertEqual(
                (audio_dir / added["file"]).read_bytes(), b"story audio"
            )
            story_course.package_podcasts(args, transcript, build)
            rerun = json.loads(catalog_path.read_text(encoding="utf-8"))
            self.assertEqual(len(rerun["episodes"]), 3)
            self.assertEqual(rerun["episodes"][2]["published"], added["published"])

    def test_duration_limit_rejects_complete_chapter_without_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "transcript.json"
            source = root / "pl.txt"
            output = root / "audio"
            transcript.write_text(json.dumps(mini_story()), encoding="utf-8")
            source.write_text("Rozdział 1: Kot\nKot śpi.", encoding="utf-8")
            args = story_course.create_parser().parse_args([
                "--transcript", str(transcript),
                "--source-text", str(source),
                "--output", str(output),
                "--cache", str(root / "cache"),
                "--build-manifest", str(root / "manifest.json"),
                "--target", "sv",
                "--source-language", "pl",
                "--format", "wav",
                "--max-duration", "0.1",
            ])
            with patch.object(
                story_course, "_clip", new_callable=AsyncMock, return_value=tone()
            ):
                with self.assertRaisesRegex(ValueError, "no outputs published"):
                    asyncio.run(story_course.render_story(args))
            self.assertFalse(list(output.glob("*.wav")))


if __name__ == "__main__":
    unittest.main()
