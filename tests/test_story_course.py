import asyncio
import argparse
import importlib.util
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
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


STORY_COVER_HASH = "41b6d295"
EXISTING_COVER_HASH = "7be87c5d"

class StoryCourseTests(unittest.TestCase):
    def test_azure_is_default_and_practice_stays_on_edge_for_all_languages(self):
        azure = story_course._azure()
        self.assertEqual(story_course.create_parser().parse_args([]).narration_engine, "azure")
        for source_language, target in (("sv", "pl"), ("pl", "sv"), ("sv", "en"), ("en", "sv")):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                transcript = root / "transcript.json"
                transcript.write_text(json.dumps(mini_story()), encoding="utf-8")
                source = root / "pl.txt"
                source.write_text("Rozdział 1: Kot\nKot śpi.", encoding="utf-8")
                passage = {
                    "text": mini_story()["chapters"][0]["chapter_text"][target],
                    "intent": "Gentle narration", "rate": "-15%",
                    "pitch": "+2%", "volume": "-5%", "pause_after_ms": 0,
                }
                (root / "delivery.json").write_text(json.dumps([passage]), encoding="utf-8")
                (root / "narration.json").write_text(
                    json.dumps({target: {"1": "delivery.json"}}), encoding="utf-8",
                )
                args = story_course.create_parser().parse_args([
                    "--transcript", str(transcript), "--source-text", str(source),
                    "--output", str(root / "audio"), "--cache", str(root / "cache"),
                    "--build-manifest", str(root / "manifest.json"),
                    "--source-language", source_language, "--target", target, "--format", "wav",
                ])
                with patch.object(story_course, "_azure", return_value=azure), patch.object(
                    azure, "check_voice", return_value={"advertised_styles": ["audiobook"]}
                ), patch.object(
                    story_course, "_clip", new_callable=AsyncMock, return_value=tone()
                ) as practice, patch.object(
                    story_course, "_narration_clip", new_callable=AsyncMock, return_value=tone()
                ) as narration:
                    result = asyncio.run(story_course.render_story(args))
                self.assertEqual(practice.await_count, 2)
                self.assertEqual(narration.await_count, 3)
                data = result["chapters"]["1"]["targets"][target]
                settings = data["narration"]
                title = data["chapter_introduction"]
                self.assertEqual(
                    title["text"],
                    story_course.chapter_heading(mini_story()["chapters"][0], target),
                )
                self.assertLess(title["end_ms"], data["chapter_readings"][0]["start_ms"])
                self.assertIn(title["text"], narration.await_args_list[1].args[0])
                self.assertEqual(len(data["chapter_readings"]), 2)
                self.assertEqual(data["sequence"], ["story", "practice", "story"])
                with (args.output / data["audio_file"]).open("rb") as audio_file:
                    decoded = AudioSegment.from_file(audio_file)
                before, after = data["chapter_readings"]
                self.assertEqual(
                    decoded[before["start_ms"]:before["end_ms"]].raw_data,
                    decoded[after["start_ms"]:after["end_ms"]].raw_data,
                )
                self.assertEqual(settings["voice"], azure.NARRATION_VOICES[target])
                self.assertEqual(settings["style"], "audiobook")
                self.assertIn(azure.LOCALES[target], settings["ssml"])
                self.assertIn('volume="-5%"', settings["ssml"])
                self.assertIn('rate="-15%"', settings["ssml"])
                previous_manifest = args.build_manifest.read_bytes()
                with patch.object(story_course, "_azure", return_value=azure), patch.object(
                    azure, "check_voice", side_effect=RuntimeError("Azure unavailable")
                ), patch.object(story_course, "_clip", new_callable=AsyncMock) as practice:
                    with self.assertRaisesRegex(RuntimeError, "Azure unavailable"):
                        asyncio.run(story_course.render_story(args))
                    practice.assert_not_awaited()
                self.assertEqual(args.build_manifest.read_bytes(), previous_manifest)

    def test_azure_cache_reuses_audio_and_keys_include_ssml(self):
        azure = story_course._azure()
        import io
        buffer = io.BytesIO()
        tone().export(buffer, format="mp3")
        with tempfile.TemporaryDirectory() as directory, patch.object(
            story_course, "_azure", return_value=azure
        ), patch.object(azure, "synthesize", return_value=buffer.getvalue()) as synthesis:
            for ssml in ("first", "first", "changed"):
                clip = asyncio.run(story_course._narration_clip(
                    ssml, Path(directory), "fake", "swedencentral"
                ))
                self.assertEqual(clip.frame_rate, 44100)
            self.assertEqual(synthesis.call_count, 2)

    def test_azure_narration_retries_transient_errors_only(self):
        import io
        azure = story_course._azure()
        buffer = io.BytesIO()
        tone().export(buffer, format="mp3")
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            with patch.object(story_course, "_azure", return_value=azure), patch.object(
                azure, "synthesize", side_effect=[
                    azure.AzureSpeechError("Temporary failure", retryable=True),
                    buffer.getvalue(),
                ],
            ) as synthesis, patch.object(
                story_course.asyncio, "sleep", new_callable=AsyncMock,
            ) as sleep, self.assertLogs(story_course.LOGGER, level="WARNING"):
                clip = asyncio.run(story_course._narration_clip(
                    "retryable", cache, "fake", "swedencentral",
                ))
            self.assertGreater(len(clip), 0)
            self.assertEqual(synthesis.call_count, 2)
            sleep.assert_awaited_once_with(2)
            files_before = set(cache.iterdir())
            with patch.object(story_course, "_azure", return_value=azure), patch.object(
                azure, "synthesize", side_effect=azure.AzureSpeechError("Invalid request"),
            ) as synthesis, patch.object(
                story_course.asyncio, "sleep", new_callable=AsyncMock,
            ) as sleep:
                with self.assertRaisesRegex(azure.AzureSpeechError, "Invalid request"):
                    asyncio.run(story_course._narration_clip(
                        "nonretryable", cache, "fake", "swedencentral",
                    ))
            synthesis.assert_called_once()
            sleep.assert_not_awaited()
            self.assertEqual(set(cache.iterdir()), files_before)

    def test_real_story_validates_and_reconstructs_source(self):
        story = story_course.load_transcript(
            ROOT / "courses/stories/magical_radio/generated/transcript.json",
            ROOT / "courses/stories/magical_radio/complete/pl.txt",
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

    def test_english_story_uses_localized_character_names(self):
        story = story_course.load_transcript(
            ROOT / "courses/stories/magical_radio/generated/transcript.json",
            ROOT / "courses/stories/magical_radio/complete/pl.txt",
        )
        english = " ".join(chapter["chapter_text"]["en"] for chapter in story["chapters"])
        for polish_name in ("Maja", "Mai ", "Tomek", "Tomka", "Radiofon "):
            self.assertNotIn(polish_name, english)
        for english_name in ("Maya", "Tom", "Radiophone", "Reparo"):
            self.assertIn(english_name, english)
        for chapter in story["chapters"]:
            self.assertTrue(chapter["summary"]["en"])
        self.assertIn("Tomek", " ".join(
            chapter["chapter_text"]["pl"] for chapter in story["chapters"]
        ))

    def test_story_language_review_corrections(self):
        story = story_course.load_transcript(
            ROOT / "courses/stories/magical_radio/generated/transcript.json",
            ROOT / "courses/stories/magical_radio/complete/pl.txt",
        )
        chapter = story["chapters"][3]
        self.assertEqual(chapter["titles"]["en"], "Down the Stairs")
        self.assertIn("some of them are flying just below the ceiling", chapter["chapter_text"]["en"])
        self.assertIn("is glowing with a golden light", chapter["chapter_text"]["en"])
        self.assertIn("светится золотым светом", chapter["chapter_text"]["ru"])
        vocabulary = {
            item["id"]: item["text"]
            for entry in story["chapters"] for item in entry["vocabulary"]
        }
        self.assertEqual(vocabulary[133]["en"], "go to the tree")
        self.assertEqual(vocabulary[160]["en"], "begin to speak")
        self.assertEqual(vocabulary[227]["en"], "glow with a golden light")
        self.assertEqual(vocabulary[147]["es"], "conducir hacia abajo")
        self.assertEqual(vocabulary[234]["sv"], "på den andra vingen")

    def test_swedish_story_is_complete_and_has_localized_heading(self):
        story = story_course.load_transcript(
            ROOT / "courses/stories/magical_radio/generated/transcript.json",
            ROOT / "courses/stories/magical_radio/complete/pl.txt",
        )
        swedish = " ".join(chapter["chapter_text"]["sv"] for chapter in story["chapters"])
        for name in ("Maja", "Tom", "Radiofon", "Reparo"):
            self.assertIn(name, swedish)
        self.assertNotIn("Tomek", swedish)
        self.assertIn("flyger uppe vid taket", story["chapters"][3]["chapter_text"]["sv"])
        self.assertEqual(
            story_course.chapter_heading(story["chapters"][3], "sv"),
            "Kapitel fyra. Trappan ner.",
        )

    def test_spain_spanish_story_and_narration_defaults(self):
        story = story_course.load_transcript(
            ROOT / "courses/stories/magical_radio/generated/transcript.json",
            ROOT / "courses/stories/magical_radio/complete/pl.txt",
        )
        self.assertEqual(story["titles"]["es"], "La radio mágica")
        for chapter in story["chapters"]:
            self.assertTrue(chapter["chapter_text"]["es"])
            self.assertTrue(all(item["text"]["es"] for item in chapter["vocabulary"]))
        self.assertIn("¡Llevadme con vosotros!", story["chapters"][1]["chapter_text"]["es"])
        self.assertIn("están volando", story["chapters"][3]["chapter_text"]["es"])
        self.assertEqual(
            story_course.chapter_heading(story["chapters"][3], "es"),
            "Capítulo cuatro. Escaleras abajo.",
        )
        azure = story_course._azure()
        self.assertEqual(azure.LOCALES["es"], "es-ES")
        self.assertEqual(azure.NARRATION_VOICES["es"], "es-ES-ElviraNeural")
        self.assertIsNone(azure.NARRATION_STYLES["es"])

    def test_russian_story_uses_localized_character_names(self):
        story = story_course.load_transcript(
            ROOT / "courses/stories/magical_radio/generated/transcript.json",
            ROOT / "courses/stories/magical_radio/complete/pl.txt",
        )
        russian = " ".join(chapter["chapter_text"]["ru"] for chapter in story["chapters"])
        for foreign_name in ("Томек", "Майя", "Tom", "Maja", "Reparo"):
            self.assertNotIn(foreign_name, russian)
        for russian_name in ("Маша", "Миша", "Радиофон", "Репаро"):
            self.assertIn(russian_name, russian)

    def test_each_chapter_has_beginner_vocabulary_coverage(self):
        story = story_course.load_transcript(
            ROOT / "courses/stories/magical_radio/generated/transcript.json",
            ROOT / "courses/stories/magical_radio/complete/pl.txt",
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

    def test_identical_chapter_readings_surround_practice(self):
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
            chapter_intro_clip=tone(150),
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
        self.assertEqual(manifest["sequence"], ["story", "practice", "story"])
        before, after = manifest["chapter_readings"]
        self.assertEqual(manifest["chapter_introduction"]["start_ms"], 10)
        self.assertEqual(before["start_ms"], 190)
        self.assertEqual(before["text"], "Katten sover.")
        self.assertEqual(after["text"], before["text"])
        cue = story_course._transition_cue()
        self.assertEqual(
            manifest["practice"][0]["start_ms"] - before["end_ms"], 60 + len(cue)
        )
        self.assertEqual(after, manifest["chapter_reading"])
        for reading in (before, after):
            self.assertEqual(
                track[reading["start_ms"]:reading["end_ms"]].raw_data,
                tone(300).raw_data,
            )
        self.assertEqual(
            manifest["chapter_reading"]["start_ms"],
            manifest["practice"][-1]["end_ms"] + len(cue) + 30,
        )
        self.assertEqual(track[manifest["chapter_reading"]["start_ms"]:].rms, tone(300).rms)
        to_practice, to_story = manifest["transitions"]
        self.assertEqual((to_practice["from"], to_practice["to"]), ("story", "practice"))
        self.assertEqual((to_story["from"], to_story["to"]), ("practice", "story"))
        self.assertEqual(to_practice["start_ms"], before["end_ms"] + 30)
        self.assertEqual(to_practice["end_ms"] + 30, manifest["practice"][0]["start_ms"])
        self.assertEqual(to_story["start_ms"], manifest["practice"][-1]["end_ms"])
        self.assertEqual(to_story["end_ms"] + 30, after["start_ms"])
        for transition in manifest["transitions"]:
            self.assertEqual(
                track[transition["start_ms"]:transition["end_ms"]].raw_data,
                cue.raw_data,
            )

    def test_transition_cue_is_short_quiet_and_fades_without_clicks(self):
        cue = story_course._transition_cue()
        self.assertEqual(cue.frame_rate, 44100)
        self.assertEqual(len(cue), 620)
        self.assertGreater(cue.rms, 0)
        self.assertLessEqual(cue.max_dBFS, -23.9)
        self.assertEqual(cue[220:300].rms, 0)
        samples = cue.get_array_of_samples()
        self.assertEqual(samples[0], 0)
        self.assertLess(abs(samples[-1]) / 32768, 0.0002)

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
            chapter, "sv", "pl", clips, tone(300), 10, 20, 30,
            chapter_intro_clip=tone(150),
        )[1]
        second_manifest = story_course._compose_track(
            chapter, "sv", "pl", clips, tone(300), 10, 20, 30,
            chapter_intro_clip=tone(150),
        )[1]
        first_order = [entry["id"] for entry in first_manifest["practice"]]
        self.assertNotEqual(first_order, list(range(1, 7)))
        self.assertEqual(first_order, [entry["id"] for entry in second_manifest["practice"]])
        self.assertEqual(first_manifest["practice_order"], "deterministically_shuffled")

    def test_chapter_heading_announces_localized_ordinal(self):
        chapter = {"chapter_number": 2, "titles": {
            "pl": "Głos z radia", "en": "A Voice from the Radio",
            "ru": "Голос из радио", "sv": "En röst från radion",
        }}
        self.assertEqual(
            story_course.chapter_heading(chapter, "pl"), "Rozdział drugi. Głos z radia."
        )
        self.assertEqual(
            story_course.chapter_heading(chapter, "en"),
            "Chapter two. A Voice from the Radio.",
        )
        self.assertEqual(
            story_course.chapter_heading(chapter, "ru"), "Глава вторая. Голос из радио."
        )
        self.assertEqual(
            story_course.chapter_heading(chapter, "sv"), "Kapitel två. En röst från radion."
        )
        with self.assertRaises(ValueError):
            story_course.chapter_heading({**chapter, "chapter_number": 11}, "pl")

    def test_book_title_is_introduced_before_first_reading_in_first_chapter_only(self):
        chapter = mini_story()["chapters"][0]
        _, first = story_course._compose_track(
            chapter, "pl", "sv", {1: (tone(), tone())}, tone(300),
            10, 20, 30, story_title="Kot. Wielka przygoda",
            book_intro_clip=tone(150),
            chapter_intro_clip=tone(150),
        )
        self.assertEqual(first["book_introduction"]["text"], "Kot. Wielka przygoda.")
        self.assertEqual(first["book_introduction"]["start_ms"], 10)
        self.assertEqual(
            first["chapter_introduction"]["start_ms"],
            first["book_introduction"]["end_ms"] + 30,
        )
        self.assertEqual(first["chapter_introduction"]["text"], "Rozdział pierwszy. Kot.")
        self.assertEqual(
            first["chapter_readings"][0]["start_ms"],
            first["chapter_introduction"]["end_ms"] + 30,
        )
        self.assertEqual(first["chapter_reading"]["text"], "Kot śpi.")
        second_chapter = {**chapter, "chapter_number": 2}
        _, second = story_course._compose_track(
            second_chapter, "pl", "sv", {1: (tone(), tone())}, tone(300),
            10, 20, 30, story_title="Kot. Wielka przygoda",
            chapter_intro_clip=tone(150),
        )
        self.assertIsNone(second["book_introduction"])
        self.assertEqual(second["chapter_reading"]["text"], "Kot śpi.")
        self.assertEqual(second["chapter_introduction"]["start_ms"], 10)
        self.assertEqual(second["chapter_readings"][0]["start_ms"], 190)

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
                "--narration-engine", "edge",
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
                self.assertEqual(len(manifest["chapter_readings"]), 2)
                self.assertEqual(data["chapter_readings"], manifest["chapter_readings"])
                self.assertEqual(data["sequence"], ["story", "practice", "story"])
                self.assertEqual(data["transitions"], manifest["transitions"])
                self.assertEqual(data["chapter_introduction"], manifest["chapter_introduction"])
                self.assertEqual(
                    manifest["chapter_introduction"]["text"],
                    story_course.chapter_heading(mini_story()["chapters"][0], target),
                )

    def test_missing_chapter_title_clip_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "chapter title clip"):
            story_course._compose_track(
                mini_story()["chapters"][0], "pl", "sv",
                {1: (tone(), tone())}, tone(300), 10, 20, 30,
            )

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
            story_root = root / "story"
            story_root.mkdir()
            (story_root / "cover_se_pl.jpeg").write_bytes(b"story cover")
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
            self.assertEqual(added["image"], "images/stories/test_story/cover.jpeg")
            self.assertEqual(
                added["description"],
                "Kapitel 1 av 1 i berättelsen ”Testberättelsen” (Testowa historia).\n\n"
                "Så går avsnittet till:\n"
                "1. Lyssna på hela kapitlet på polska – du behöver inte förstå allt.\n"
                "2. Öva orden och uttrycken ur kapitlet: svensk ledtråd, paus, svar på polska.\n"
                "3. Lyssna på kapitlet igen – nu förstår du mycket mer.\n\n"
                "En ljudsignal hörs mellan delarna. Lyssna i ordning från kapitel 1.",
            )
            story_cover = course / f"images/stories/test_story/cover-{STORY_COVER_HASH}.jpeg"
            self.assertEqual(story_cover.read_bytes(), b"story cover")
            self.assertFalse((course / added["image"]).exists())
            self.assertEqual(
                (course / f"cover-{EXISTING_COVER_HASH}.jpeg").read_bytes(), b"existing cover"
            )
            feed = ET.parse(course / "feed.xml")
            artwork = feed.findall("./channel/item")[2].find(
                "{http://www.itunes.com/dtds/podcast-1.0.dtd}image"
            )
            assert artwork is not None
            self.assertEqual(
                artwork.get("href"),
                "https://example.com/repeto/swedish-polish/"
                f"images/stories/test_story/cover-{STORY_COVER_HASH}.jpeg",
            )
            self.assertEqual(
                (audio_dir / added["file"]).read_bytes(), b"story audio"
            )
            self.assertFalse((audio_source_dir / audio_name).exists())
            self.assertEqual(
                build["chapters"]["1"]["targets"]["pl"]["packaged_audio"],
                f"swedish-polish/audio/stories/test_story/{audio_name}",
            )
            story_course.package_podcasts(args, transcript, build)
            self.assertEqual(
                (audio_dir / added["file"]).read_bytes(), b"story audio"
            )
            (audio_source_dir / audio_name).write_bytes(b"story audio")
            story_course.package_podcasts(args, transcript, build)
            self.assertFalse((audio_source_dir / audio_name).exists())
            (audio_source_dir / audio_name).write_bytes(b"changed audio")
            with self.assertRaisesRegex(FileExistsError, "different episode audio"):
                story_course.package_podcasts(args, transcript, build)
            (audio_source_dir / audio_name).unlink()
            rerun = json.loads(catalog_path.read_text(encoding="utf-8"))
            self.assertEqual(len(rerun["episodes"]), 3)
            self.assertEqual(rerun["episodes"][2]["published"], added["published"])
            self.assertEqual(rerun["episodes"][2]["image"], added["image"])
            (story_root / "cover_se_pl.jpeg").write_bytes(b"different cover")
            with self.assertRaisesRegex(FileExistsError, "different story cover"):
                story_course.package_podcasts(args, transcript, build)
            (story_root / "cover_se_pl.jpeg").unlink()
            with self.assertRaisesRegex(FileNotFoundError, "story cover image"):
                story_course.package_podcasts(args, transcript, build)
            (story_root / "cover.jpeg").write_bytes(b"story cover")
            story_course.package_podcasts(args, transcript, build)
            self.assertEqual(story_cover.read_bytes(), b"story cover")
            self.assertEqual(
                sorted(path.name for path in story_cover.parent.iterdir()), [story_cover.name]
            )

    def test_swedish_english_story_episode_has_swedish_description(self):
        chapter = mini_story()["chapters"][0]
        transcript = {
            "story_id": "test_story",
            "titles": {"pl": "Testowa historia", "sv": "Testberättelsen", "en": "Test Story"},
            "chapters": [chapter],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            course = root / "podcast" / "swedish-english"
            course.mkdir(parents=True)
            (course / "cover.jpeg").write_bytes(b"existing cover")
            catalog_path = course / "course.json"
            catalog_path.write_text(json.dumps({
                "title": "Repeto", "description": "Kurs", "language": "sv",
                "author": "Repeto", "email": "repeto.lingo@gmail.com",
                "source_language": "sv", "target_language": "en", "episodes": [],
            }), encoding="utf-8")
            story_root = root / "story"
            (story_root / "generated").mkdir(parents=True)
            (story_root / "cover.jpeg").write_bytes(b"story cover")
            audio_name = "01_chapter_01_sv_en_2026-10-28_16-00-00.mp3"
            transcript_path = story_root / "generated" / "transcript.json"
            output = story_course.default_output(transcript_path, "sv", ["en"])
            output.mkdir(parents=True)
            (output / audio_name).write_bytes(b"story audio")
            args = argparse.Namespace(
                podcast_course="swedish-english", source_language="sv",
                transcript=transcript_path, cover=None,
                email="repeto.lingo@gmail.com", podcast_root=root / "podcast",
                podcast_base_url="https://example.com/repeto", author="Repeto",
                output=None,
            )
            build = {
                "settings": {"target_languages": ["en"]},
                "chapters": {"1": {"targets": {"en": {
                    "audio_file": audio_name, "total_duration_ms": 8400,
                }}}},
                "podcasts": {"pl": {"slug": "swedish-polish"}},
            }
            story_course.package_podcasts(args, transcript, build)
            episode = json.loads(catalog_path.read_text(encoding="utf-8"))["episodes"][0]
            self.assertEqual(output, story_root / "generated" / "audio" / "sv_en")
            self.assertEqual(episode["id"], "test_story:sv:en:chapter-01")
            self.assertEqual(episode["season"], 1)
            self.assertEqual(
                episode["description"],
                "Kapitel 1 av 1 i berättelsen ”Testberättelsen” (Test Story).\n\n"
                "Så går avsnittet till:\n"
                "1. Lyssna på hela kapitlet på engelska – du behöver inte förstå allt.\n"
                "2. Öva orden och uttrycken ur kapitlet: svensk ledtråd, paus, svar på engelska.\n"
                "3. Lyssna på kapitlet igen – nu förstår du mycket mer.\n\n"
                "En ljudsignal hörs mellan delarna. Lyssna i ordning från kapitel 1.",
            )
            self.assertEqual(set(build["podcasts"]), {"pl", "en"})
            self.assertFalse((output / audio_name).exists())

    def test_polish_english_story_packaging_localizes_copy(self):
        chapter = mini_story()["chapters"][0]
        chapter["summary"] = {"pl": "Zaczyna się przygoda."}
        transcript = {
            "story_id": "test_story",
            "titles": {"pl": "Testowa historia", "sv": "Testberättelsen", "en": "Test Story"},
            "chapters": [chapter],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            course = root / "podcast" / "polish-english"
            course.mkdir(parents=True)
            (course / "cover.jpeg").write_bytes(b"existing cover")
            catalog_path = course / "course.json"
            catalog_path.write_text(json.dumps({
                "title": "Repeto", "description": "Kurs", "language": "pl",
                "author": "Repeto", "email": "repeto.lingo@gmail.com",
                "source_language": "pl", "target_language": "en", "episodes": [],
            }), encoding="utf-8")
            story_root = root / "story"
            (story_root / "generated").mkdir(parents=True)
            (story_root / "cover.jpeg").write_bytes(b"story cover")
            transcript_path = story_root / "generated" / "transcript.json"
            output = story_course.default_output(transcript_path, "pl", ["en"])
            output.mkdir(parents=True)
            audio_name = "01_chapter_01_pl_en_2026-10-29_21-00-00.mp3"
            (output / audio_name).write_bytes(b"story audio")
            args = argparse.Namespace(
                podcast_course="polish-english", source_language="pl",
                transcript=transcript_path, cover=None,
                email="repeto.lingo@gmail.com", podcast_root=root / "podcast",
                podcast_base_url="https://example.com/repeto", author="Repeto",
                output=None,
            )
            build = {
                "settings": {"target_languages": ["en"]},
                "chapters": {"1": {"targets": {"en": {
                    "audio_file": audio_name, "total_duration_ms": 8400,
                }}}},
            }
            story_course.package_podcasts(args, transcript, build)
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            episode = catalog["episodes"][0]
            self.assertEqual(episode["id"], "test_story:pl:en:chapter-01")
            self.assertIn("Zaczyna się przygoda.", episode["description"])
            self.assertNotIn("svensk", episode["description"])
            self.assertEqual(catalog["seasons"], {"1": "Testowa historia"})
            self.assertTrue((course / "audio" / episode["file"]).is_file())

    def test_english_swedish_story_packaging_localizes_copy(self):
        chapter = mini_story()["chapters"][0]
        chapter["summary"] = {"en": "An adventure begins."}
        transcript = {
            "story_id": "test_story",
            "titles": {"pl": "Testowa historia", "sv": "Testberättelsen", "en": "Test Story"},
            "chapters": [chapter],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            course = root / "podcast" / "english-swedish"
            course.mkdir(parents=True)
            (course / "cover.jpeg").write_bytes(b"existing cover")
            catalog_path = course / "course.json"
            catalog_path.write_text(json.dumps({
                "title": "Repeto", "description": "Course", "language": "en",
                "author": "Repeto", "email": "repeto.lingo@gmail.com",
                "source_language": "en", "target_language": "sv", "episodes": [],
            }), encoding="utf-8")
            story_root = root / "story"
            (story_root / "generated").mkdir(parents=True)
            (story_root / "cover.jpeg").write_bytes(b"story cover")
            transcript_path = story_root / "generated" / "transcript.json"
            output = story_course.default_output(transcript_path, "en", ["sv"])
            output.mkdir(parents=True)
            audio_name = "01_chapter_01_en_sv_2026-10-30_13-00-00.mp3"
            (output / audio_name).write_bytes(b"story audio")
            args = argparse.Namespace(
                podcast_course="english-swedish", source_language="en",
                transcript=transcript_path, cover=None,
                email="repeto.lingo@gmail.com", podcast_root=root / "podcast",
                podcast_base_url="https://example.com/repeto", author="Repeto",
                output=None,
            )
            build = {
                "settings": {"target_languages": ["sv"]},
                "chapters": {"1": {"targets": {"sv": {
                    "audio_file": audio_name, "total_duration_ms": 8400,
                }}}},
            }
            story_course.package_podcasts(args, transcript, build)
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            episode = catalog["episodes"][0]
            self.assertEqual(episode["id"], "test_story:en:sv:chapter-01")
            self.assertIn("An adventure begins.", episode["description"])
            self.assertIn("an English prompt", episode["description"])
            self.assertEqual(catalog["title"], "Repeto – Learn Swedish")
            self.assertEqual(catalog["seasons"], {"1": "Test Story"})
            self.assertTrue((course / "audio" / episode["file"]).is_file())
            story_course.package_podcasts(args, transcript, build)
            self.assertEqual(
                catalog["episodes"],
                json.loads(catalog_path.read_text(encoding="utf-8"))["episodes"],
            )

    def test_rendering_one_target_keeps_other_targets_in_build_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "generated" / "transcript.json"
            transcript.parent.mkdir()
            source = root / "pl.txt"
            build_manifest = root / "generated" / "manifest.json"
            transcript.write_text(json.dumps(mini_story()), encoding="utf-8")
            source.write_text("Rozdział 1: Kot\nKot śpi.", encoding="utf-8")
            previous_settings = {"source_language": "sv", "target_languages": ["pl"]}
            pl_entry = {"audio_file": "01_chapter_01_sv_pl_old.mp3"}
            build_manifest.write_text(json.dumps({
                "story_id": mini_story()["story_id"],
                "settings": previous_settings,
                "chapters": {"1": {"titles": {}, "targets": {"pl": pl_entry}}},
                "podcasts": {},
            }), encoding="utf-8")
            args = story_course.create_parser().parse_args([
                "--narration-engine", "edge",
                "--transcript", str(transcript),
                "--source-text", str(source),
                "--cache", str(root / "cache"),
                "--build-manifest", str(build_manifest),
                "--target", "en",
                "--format", "wav",
            ])
            with patch.object(
                story_course, "_clip", new_callable=AsyncMock, return_value=tone()
            ):
                result = asyncio.run(story_course.render_story(args))
            targets = result["chapters"]["1"]["targets"]
            self.assertEqual(targets["pl"], pl_entry)
            self.assertEqual(targets["en"]["source_language"], "sv")
            output = root / "generated" / "audio" / "sv_en"
            self.assertTrue((output / targets["en"]["audio_file"]).is_file())
            self.assertEqual(result["renders"]["sv_pl"], previous_settings)
            self.assertEqual(result["renders"]["sv_en"]["target_languages"], ["en"])
            self.assertEqual(result["settings"]["target_languages"], ["en"])

    def test_duration_limit_rejects_complete_chapter_without_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "transcript.json"
            source = root / "pl.txt"
            output = root / "audio"
            transcript.write_text(json.dumps(mini_story()), encoding="utf-8")
            source.write_text("Rozdział 1: Kot\nKot śpi.", encoding="utf-8")
            args = story_course.create_parser().parse_args([
                "--narration-engine", "edge",
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
