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
            self.assertEqual(catalog["title"], "Repeto – Ucz się szwedzkiego")
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
            self.assertIn("Sezon 1", page)
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

            self.assertEqual(catalog["title"], "Repeto – Lär dig ryska")
            self.assertIn("nybörjare i alla åldrar", catalog["description"])
            self.assertIn("Säsong 1 – Övningar: 1 kort ämne", catalog["description"])
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
