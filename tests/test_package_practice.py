import argparse
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from pydub import AudioSegment
from pydub.generators import Sine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
SPEC = importlib.util.spec_from_file_location(
    "package_practice", ROOT / "code/package_practice.py"
)
assert SPEC and SPEC.loader
package_practice = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_practice)
renderer = package_practice.renderer


def tone(duration: int = 300) -> AudioSegment:
    return Sine(440, sample_rate=44100).to_audio_segment(duration=duration)


def write_render(
    renders: Path, number: int, topic: str, entries: list[dict],
    source_language: str = "se", target_language: str = "ru",
) -> str:
    audio = AudioSegment.silent(renderer.LEAD_IN_MS, frame_rate=44100)
    timed = []
    for item in entries:
        start = len(audio)
        audio += tone()
        source = {"text": item[source_language], "start_ms": start, "end_ms": len(audio)}
        audio += AudioSegment.silent(renderer.THINKING_MS, frame_rate=44100)
        playbacks = []
        for _ in range(2):
            begin = len(audio)
            audio += tone()
            playbacks.append({"text": item[target_language], "start_ms": begin, "end_ms": len(audio)})
            audio += AudioSegment.silent(renderer.REPETITION_MS, frame_rate=44100)
        timed.append({
            "id": item["id"], "entry_start_ms": start, "entry_end_ms": len(audio),
            source_language: source, target_language: dict(playbacks[0]),
            "target_playbacks": playbacks,
        })
    name = f"{number:02d}_topic_{source_language}_{target_language}_double_2026-01-01_00-00-00"
    audio.export(
        renders / f"{name}.mp3", format="mp3",
        parameters=["-ar", "44100", "-write_xing", "1"],
    )
    duration = len(audio)
    manifest = {
        "section": topic, "source_language": source_language, "target_language": target_language,
        "audio_file": f"{name}.mp3", "total_duration_ms": duration, "entries": timed,
    }
    (renders / f"{name}.json").write_text(json.dumps(manifest), encoding="utf-8")
    return f"{name}.mp3"


class PackagePracticeTests(unittest.TestCase):
    def test_selected_topics_update_in_place_without_touching_other_episodes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            items = [
                {"id": f"phrase_{n:06}", "topic": topic, "se": "Hej!",
                 "pl": "Cześć!", "en": "Hi!", "ru": "Привет!"}
                for n, topic in enumerate(("Greetings", "Numbers", "Colors"), 1)
            ]
            transcript = root / "transcript.json"
            transcript.write_text(json.dumps(items), encoding="utf-8")
            titles = root / "topics.json"
            titles.write_text(json.dumps({
                item["topic"]: {"se": item["topic"], "ru": item["topic"]}
                for item in items
            }), encoding="utf-8")
            renders = root / "renders"
            renders.mkdir()
            write_render(renders, 1, "Greetings", items[:1])
            write_render(renders, 3, "Colors", items[2:])
            for suffix in ("old", "older"):
                (renders / f"02_se_ru_double_{suffix}.json").write_text(
                    json.dumps({"section": "Numbers"}), encoding="utf-8"
                )
            course = root / "podcast/swedish-russian"
            course.mkdir(parents=True)
            (course / "cover.jpeg").write_bytes(b"jpeg")
            pending = [
                {"id": f"repeto:swedish-russian:topic-{n:02}",
                 "title": f"Existing {n}", "description": f"Keep {n}",
                 "season": 1, "episode": n, "published": "2026-01-02T00:00:00+00:00",
                 "pending_audio": True}
                for n in range(1, 4)
            ]
            story = {"id": "untouched-story", "title": "Original",
                     "pending_audio": True, "season": 2, "episode": 1}
            catalog = {"title": "Original show", "source_language": "sv",
                       "target_language": "ru", "episodes": [pending[0], story, pending[1], pending[2]]}
            (course / "course.json").write_text(json.dumps(catalog), encoding="utf-8")
            args = package_practice.create_parser().parse_args([
                "--target", "ru", "--course", "swedish-russian", "--renders", str(renders),
                "--transcript", str(transcript), "--topic-titles", str(titles),
                "--podcast-root", str(root / "podcast"), "--skip-site-build",
                "--topic", "Colors", "--topic", "Greetings",
            ])
            result = package_practice.package(args)
            self.assertEqual([ep["id"] for ep in result["episodes"]],
                             [ep["id"] for ep in catalog["episodes"]])
            self.assertEqual(result["episodes"][1:3], [story, pending[1]])
            for index in (0, 3):
                episode = result["episodes"][index]
                self.assertNotIn("pending_audio", episode)
                self.assertEqual(episode["published"], "2026-01-02T00:00:00+00:00")
                self.assertEqual(episode["title"], catalog["episodes"][index]["title"])
                self.assertEqual(episode["description"], catalog["episodes"][index]["description"])
                self.assertIn("file", episode)
                self.assertIn("duration_ms", episode)
            self.assertEqual(result["title"], "Original show")
            self.assertEqual(package_practice.package(args), result)

    def test_selection_rejects_unknown_missing_and_duplicate_selected_manifests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            items = [{"id": "phrase_000001", "topic": "Greetings", "se": "Hej!",
                      "pl": "Cześć!", "en": "Hi!", "ru": "Привет!"}]
            transcript = root / "transcript.json"
            transcript.write_text(json.dumps(items), encoding="utf-8")
            titles = root / "topics.json"
            titles.write_text(json.dumps({"Greetings": {"se": "Hej", "ru": "Привет"}}))
            renders = root / "renders"
            renders.mkdir()
            base = ["--target", "ru", "--course", "swedish-russian", "--renders", str(renders),
                    "--transcript", str(transcript), "--topic-titles", str(titles),
                    "--podcast-root", str(root / "podcast"), "--skip-site-build"]
            parser = package_practice.create_parser()
            with self.assertRaisesRegex(ValueError, "Unknown topics"):
                package_practice.package(parser.parse_args(base + ["--topic", "greetings"]))
            with self.assertRaisesRegex(ValueError, "missing=.*Greetings"):
                package_practice.package(parser.parse_args(base + ["--topic", "Greetings"]))
            with self.assertRaisesRegex(ValueError, "missing=.*Greetings"):
                package_practice.package(parser.parse_args(base))
            manifest = {"section": "Greetings"}
            for suffix in ("one", "two"):
                (renders / f"01_se_ru_double_{suffix}.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "Multiple renders"):
                package_practice.package(parser.parse_args(base + ["--topic", "Greetings"]))

    def test_full_packaging_preserves_draft_copy_and_other_season(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = {"id": "phrase_000001", "topic": "Greetings", "se": "Hej!",
                    "pl": "Cześć!", "en": "Hi!", "ru": "Привет!"}
            transcript = root / "transcript.json"
            transcript.write_text(json.dumps([item]))
            titles = root / "topics.json"
            titles.write_text(json.dumps({"Greetings": {"se": "Hälsningar", "ru": "Приветствия"}}))
            renders = root / "renders"
            renders.mkdir()
            write_render(renders, 1, "Greetings", [item])
            course = root / "podcast/swedish-russian"
            course.mkdir(parents=True)
            (course / "cover.jpeg").write_bytes(b"jpeg")
            pending = {"id": "repeto:swedish-russian:topic-01", "title": "Custom title",
                       "description": "Custom copy", "published": "2025-01-01T00:00:00+00:00",
                       "season": 1, "episode": 1, "pending_audio": True, "extra": "keep"}
            story = {"id": "test_story:sv:ru:chapter-01", "title": "Story title",
                     "description": "Story copy", "season": 2, "episode": 1,
                     "published": "2025-01-01T00:00:00+00:00", "pending_audio": True}
            catalog = {"title": "Custom show", "description": "Custom show copy",
                       "source_language": "sv", "target_language": "ru",
                       "seasons": {"1": "Custom season", "2": "Custom story"},
                       "episodes": [story, pending]}
            (course / "course.json").write_text(json.dumps(catalog))
            args = package_practice.create_parser().parse_args([
                "--target", "ru", "--course", "swedish-russian", "--renders", str(renders),
                "--transcript", str(transcript), "--topic-titles", str(titles),
                "--podcast-root", str(root / "podcast"), "--skip-site-build",
            ])
            result = package_practice.package(args)
            self.assertEqual(result["title"], "Custom show")
            self.assertEqual(result["description"], "Custom show copy")
            self.assertEqual(result["seasons"], catalog["seasons"])
            self.assertEqual(result["episodes"][0], story)
            filled = result["episodes"][1]
            self.assertEqual({key: filled[key] for key in pending if key != "pending_audio"},
                             {key: value for key, value in pending.items() if key != "pending_audio"})
            self.assertNotIn("pending_audio", filled)

    def test_russian_source_spanish_answers_and_page_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = {"id": "phrase_000001", "topic": "Greetings", "se": "Hej!",
                    "pl": "Cześć!", "en": "Hello!", "ru": "Привет!", "es": "¡Hola!"}
            transcript = root / "transcript.json"
            transcript.write_text(json.dumps([item]), encoding="utf-8")
            titles = root / "topics.json"
            titles.write_text(json.dumps(
                {"Greetings": {"ru": "Приветствия", "es": "Saludos"}}
            ), encoding="utf-8")
            renders = root / "renders"
            renders.mkdir()
            write_render(renders, 1, "Greetings", [item], "ru", "es")
            podcast_root = root / "podcast"
            course = podcast_root / "russian-spanish"
            course.mkdir(parents=True)
            (course / "cover.jpeg").write_bytes(b"jpeg")
            args = package_practice.create_parser().parse_args([
                "--source", "ru", "--target", "es", "--course", "russian-spanish",
                "--renders", str(renders), "--transcript", str(transcript),
                "--topic-titles", str(titles), "--podcast-root", str(podcast_root),
            ])
            catalog = package_practice.package(args)
            self.assertEqual(catalog["language"], "ru")
            self.assertEqual(catalog["source_language"], "ru")
            self.assertEqual(catalog["target_language"], "es")
            self.assertEqual(catalog["title"], "Repeto.stream – Я учу испанский")
            self.assertIn("Привет! → ¡Hola!", catalog["episodes"][0]["description"])
            self.assertEqual(catalog["episodes"][0]["title"], "Приветствия — Saludos")
            page = (course / "index.html").read_text(encoding="utf-8")
            self.assertIn('lang="ru"', page)
            self.assertIn("36 фраз", page)
            self.assertIn("Слушайте и повторяйте", page)
            self.assertNotIn("feed.xml", page)
            self.assertNotIn("Lyssna", page)
            again = package_practice.package(args)
            self.assertEqual(catalog["episodes"], again["episodes"])

    def test_english_source_swedish_answers_and_page_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = {"id": "phrase_000001", "topic": "Greetings", "se": "Hej!",
                    "pl": "Cześć!", "en": "Hello!", "ru": "Привет!"}
            transcript = root / "transcript.json"
            transcript.write_text(json.dumps([item]), encoding="utf-8")
            titles = root / "topics.json"
            titles.write_text(json.dumps(
                {"Greetings": {"en": "Greetings", "se": "Hälsningar"}}
            ), encoding="utf-8")
            renders = root / "renders"
            renders.mkdir()
            write_render(renders, 1, "Greetings", [item], "en", "se")
            podcast_root = root / "podcast"
            course = podcast_root / "english-swedish"
            course.mkdir(parents=True)
            (course / "cover.jpeg").write_bytes(b"jpeg")
            args = package_practice.create_parser().parse_args([
                "--source", "en", "--target", "se", "--course", "english-swedish",
                "--renders", str(renders), "--transcript", str(transcript),
                "--topic-titles", str(titles), "--podcast-root", str(podcast_root),
            ])
            catalog = package_practice.package(args)
            self.assertEqual(catalog["language"], "en")
            self.assertEqual(catalog["source_language"], "en")
            self.assertEqual(catalog["target_language"], "sv")
            self.assertEqual(catalog["title"], "Repeto.stream – I learn Swedish")
            self.assertIn("Hello! → Hej!", catalog["episodes"][0]["description"])
            self.assertEqual(catalog["episodes"][0]["title"], "Greetings — Hälsningar")
            page = (course / "index.html").read_text(encoding="utf-8")
            self.assertIn('lang="en"', page)
            self.assertNotIn("Phrase practice", page)
            self.assertNotIn("Season", page)
            self.assertIn("Listen", page)
            self.assertNotIn("feed.xml", page)
            self.assertNotIn("Lyssna", page)
            again = package_practice.package(args)
            self.assertEqual(catalog["episodes"], again["episodes"])

    def test_swedish_target_uses_canonical_catalog_language_and_practice_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = {"id": "phrase_000001", "topic": "Greetings", "se": "Hej!",
                    "pl": "Cześć!", "en": "Hi!", "ru": "Привет!", "es": "¡Hola!"}
            transcript = root / "transcript.json"
            transcript.write_text(json.dumps([item]), encoding="utf-8")
            titles = root / "topics.json"
            titles.write_text(json.dumps(
                {"Greetings": {"pl": "Powitania", "se": "Hälsningar"}}
            ), encoding="utf-8")
            renders = root / "renders"
            renders.mkdir()
            write_render(renders, 1, "Greetings", [item], "pl", "se")
            podcast_root = root / "podcast"
            course = podcast_root / "polish-swedish"
            course.mkdir(parents=True)
            (course / "cover.jpeg").write_bytes(b"jpeg")
            args = package_practice.create_parser().parse_args([
                "--source", "pl", "--target", "se", "--course", "polish-swedish",
                "--renders", str(renders), "--transcript", str(transcript),
                "--topic-titles", str(titles), "--podcast-root", str(podcast_root),
            ])
            catalog = package_practice.package(args)
            self.assertEqual(catalog["target_language"], "sv")
            self.assertEqual(catalog["title"], "Repeto.stream – Uczę się szwedzkiego")
            self.assertIn("Cześć! → Hej!", catalog["episodes"][0]["description"])
            self.assertIn("po szwedzku", catalog["description"])
            again = package_practice.package(args)
            self.assertEqual(catalog["episodes"], again["episodes"])

    def test_packages_polish_source_with_polish_page_and_prompts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = {"id": "phrase_000001", "topic": "Greetings", "se": "Hej!",
                    "pl": "Cześć!", "en": "Hi!", "ru": "Привет!"}
            transcript = root / "transcript.json"
            transcript.write_text(json.dumps([item]), encoding="utf-8")
            titles = root / "topics.json"
            titles.write_text(json.dumps(
                {"Greetings": {"pl": "Powitania", "en": "Greetings"}}
            ), encoding="utf-8")
            renders = root / "renders"
            renders.mkdir()
            filename = write_render(renders, 1, "Greetings", [item], "pl", "en")
            podcast_root = root / "podcast"
            course = podcast_root / "polish-english"
            course.mkdir(parents=True)
            (course / "cover.jpeg").write_bytes(b"jpeg")
            args = package_practice.create_parser().parse_args([
                "--source", "pl", "--target", "en", "--course", "polish-english",
                "--renders", str(renders), "--transcript", str(transcript),
                "--topic-titles", str(titles), "--podcast-root", str(podcast_root),
            ])
            catalog = package_practice.package(args)
            self.assertEqual(catalog["language"], "pl")
            self.assertEqual(catalog["source_language"], "pl")
            self.assertEqual(catalog["episodes"][0]["title"], "Powitania — Greetings")
            self.assertIn("Cześć! → Hi!", catalog["episodes"][0]["description"])
            self.assertTrue((course / "audio/practice" / filename).is_file())
            page = (course / "index.html").read_text(encoding="utf-8")
            self.assertIn('lang="pl"', page)
            self.assertNotIn("Ćwiczenia z frazami", page)
            self.assertIn("Słuchaj", page)
            self.assertNotIn("Lyssna", page)
            again = package_practice.package(args)
            self.assertEqual(catalog["episodes"], again["episodes"])

    def test_packages_new_course_by_moving_validated_renders(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = {"id": "phrase_000001", "topic": "Greetings", "se": "Hej!",
                    "pl": "Cześć!", "en": "Hi!", "ru": "Привет!"}
            transcript = root / "transcript.json"
            transcript.write_text(json.dumps([item]), encoding="utf-8")
            titles = root / "topics.json"
            titles.write_text(json.dumps(
                {"Greetings": {"se": "Hälsningar", "ru": "Приветствия"}}
            ), encoding="utf-8")
            renders = root / "renders"
            renders.mkdir()
            filename = write_render(renders, 1, "Greetings", [item])
            podcast_root = root / "podcast"
            course = podcast_root / "swedish-russian"
            course.mkdir(parents=True)
            (course / "cover.jpeg").write_bytes(b"jpeg")
            args = package_practice.create_parser().parse_args([
                "--target", "ru", "--course", "swedish-russian",
                "--renders", str(renders), "--transcript", str(transcript),
                "--topic-titles", str(titles), "--podcast-root", str(podcast_root),
            ])

            catalog = package_practice.package(args)

            self.assertEqual(catalog["title"], "Repeto.stream – Jag lär mig ryska")
            self.assertIn("nybörjare i alla åldrar", catalog["description"])
            self.assertIn("Fraser: 1 kort ämne", catalog["description"])
            self.assertEqual(catalog["target_language"], "ru")
            episode = catalog["episodes"][0]
            self.assertEqual(episode["id"], "repeto:swedish-russian:topic-01")
            self.assertEqual(episode["title"], "Hälsningar — Приветствия")
            self.assertIn("Ämne 1 av 1: Hälsningar (Приветствия)", episode["description"])
            self.assertIn("• Hej! → Привет!", episode["description"])
            self.assertFalse((renders / filename).exists())
            self.assertTrue((course / "audio/practice" / filename).is_file())
            self.assertTrue((renders / filename.replace(".mp3", ".json")).is_file())
            self.assertTrue((course / "feed.xml").is_file())
            self.assertIn("swedish-russian", (podcast_root / "index.html").read_text())

            again = package_practice.package(args)
            self.assertEqual(again["episodes"][0]["published"], episode["published"])

            audio = course / "audio/practice" / filename
            catalog_path = course / "course.json"
            published = json.loads(catalog_path.read_text(encoding="utf-8"))
            published["episodes"][0].update(bytes=audio.stat().st_size, sha256="a" * 64)
            catalog_path.write_text(json.dumps(published), encoding="utf-8")
            audio.unlink()
            repackaged = package_practice.package(args)
            self.assertEqual(repackaged["episodes"][0]["sha256"], "a" * 64)
            self.assertIn(
                "https://audio.repeto.stream/swedish-russian/audio/practice/",
                (course / "feed.xml").read_text(encoding="utf-8"),
            )

            published["episodes"][0]["file"] = "practice/other.mp3"
            catalog_path.write_text(json.dumps(published), encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                package_practice.package(args)

    def test_rejects_stale_render_text(self):
        with tempfile.TemporaryDirectory() as directory:
            renders = Path(directory)
            item = {"id": "phrase_000001", "se": "Hej!", "ru": "Привет!"}
            filename = write_render(renders, 1, "Greetings", [item])
            manifest = json.loads(
                (renders / filename.replace(".mp3", ".json")).read_text(encoding="utf-8")
            )
            changed = renderer.Entry(
                id="phrase_000001", topic="Greetings", se="Hej!",
                pl="Cześć!", en="Hi!", ru="Здравствуй!",
            )
            with self.assertRaisesRegex(ValueError, "Stale text"):
                package_practice.validate_render(
                    renders / filename, manifest, [changed], 1, "se", "ru"
                )

    def test_missing_topic_titles_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "topics.json"
            path.write_text(json.dumps({"Greetings": {"se": "Hälsningar"}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Greetings"):
                package_practice.load_topic_titles(path, ["Greetings"], ("se", "ru"))


if __name__ == "__main__":
    unittest.main()
