import importlib.util
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "podcast", Path(__file__).resolve().parents[1] / "code/podcast.py"
)
assert SPEC and SPEC.loader
podcast = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(podcast)


class PodcastTests(unittest.TestCase):
    def test_feed_and_stable_ids(self):
        source = Path(__file__).resolve().parents[1] / "podcast/swedish-polish/course.json"
        config = json.loads(source.read_text())
        config["episodes"] = config["episodes"][:2]
        with tempfile.TemporaryDirectory() as directory:
            course = Path(directory) / "swedish-polish"
            (course / "audio" / "practice").mkdir(parents=True)
            (course / "cover.jpeg").write_bytes(b"cover")
            for episode in config["episodes"]:
                if not episode["file"].startswith("practice/"):
                    episode["file"] = "practice/" + episode["file"]
                audio = course / "audio" / episode["file"]
                audio.parent.mkdir(parents=True, exist_ok=True)
                audio.write_bytes(b"audio")
            catalog = course / "course.json"
            catalog.write_text(json.dumps(config))
            podcast.build_feed(course, "https://example.com/repeto")
            root = ET.parse(course / "feed.xml")
            items = root.findall("./channel/item")
            self.assertEqual(len(items), 2)
            self.assertEqual(
                items[0].findtext("title"), "01 Hälsningar — Powitania"
            )
            self.assertEqual(items[0].findtext("guid"), config["episodes"][0]["id"])
            self.assertEqual(items[0].findtext(f"{{{podcast.ITUNES}}}season"), "1")
            self.assertEqual(items[0].findtext(f"{{{podcast.ITUNES}}}episode"), "1")
            enclosure = items[0].find("enclosure")
            assert enclosure is not None
            self.assertEqual(enclosure.get("length"), "5")
            self.assertEqual(enclosure.get("type"), "audio/mpeg")
            self.assertTrue(enclosure.get("url", "").startswith(
                "https://example.com/repeto/swedish-polish/audio/practice/"
            ))
            config["episodes"][0]["title"] = "Updated & improved"
            catalog.write_text(json.dumps(config))
            podcast.build_feed(course, "https://example.com/repeto")
            updated = ET.parse(course / "feed.xml")
            self.assertEqual(
                updated.findtext("./channel/item/guid"), config["episodes"][0]["id"]
            )
            config["episodes"][0]["season"] = 2
            config["episodes"][0]["episode"] = 7
            catalog.write_text(json.dumps(config))
            podcast.build_feed(course, "https://example.com/repeto")
            updated = ET.parse(course / "feed.xml")
            self.assertEqual(updated.findtext(
                f"./channel/item/{{{podcast.ITUNES}}}episode"
            ), "7")
            self.assertEqual(updated.findtext(
                f"./channel/item/{{{podcast.ITUNES}}}season"
            ), "2")
            self.assertTrue(updated.findtext("./channel/item/title", "").startswith("07 "))
            (course / "audio" / config["episodes"][1]["file"]).unlink()
            with self.assertRaisesRegex(ValueError, "Missing or empty audio"):
                podcast.build_feed(course, "https://example.com/repeto")

    def test_audio_paths_must_be_safe_relative_mp3_paths(self):
        source = Path(__file__).resolve().parents[1] / "podcast/swedish-polish/course.json"
        config = json.loads(source.read_text())
        config["episodes"] = config["episodes"][:1]
        with tempfile.TemporaryDirectory() as directory:
            course = Path(directory) / "swedish-polish"
            (course / "audio").mkdir(parents=True)
            (course / "cover.jpeg").write_bytes(b"cover")
            catalog = course / "course.json"
            for filename in ("../escape.mp3", "/absolute.mp3", "nested\\escape.mp3",
                             "nested/../escape.mp3", "notes.txt"):
                config["episodes"][0]["file"] = filename
                catalog.write_text(json.dumps(config))
                with self.subTest(filename=filename):
                    with self.assertRaisesRegex(ValueError, "Invalid audio filename"):
                        podcast.build_feed(course, "https://example.com/repeto")


if __name__ == "__main__":
    unittest.main()
