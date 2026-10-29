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
    def test_text_to_html_renders_paragraphs_and_lists(self):
        self.assertEqual(
            podcast.text_to_html("Hej <du>!\nRad två\n\nSteg:\n1. Lyssna\n2. Prata\n\n• a\n• b"),
            "<p>Hej &lt;du&gt;!<br>Rad två</p><p>Steg:</p><ol><li>Lyssna</li>"
            "<li>Prata</li></ol><ul><li>a</li><li>b</li></ul>",
        )

    def test_remove_superseded_audio_keeps_referenced_files(self):
        with tempfile.TemporaryDirectory() as directory:
            course = Path(directory)
            practice = course / "audio" / "practice"
            practice.mkdir(parents=True)
            for name in ("old.mp3", "new.mp3", "shared.mp3"):
                (practice / name).write_bytes(b"x")
            (course / "course.json").write_text(json.dumps({"episodes": [
                {"id": "a", "file": "practice/new.mp3"},
                {"id": "b", "file": "practice/shared.mp3"},
            ]}), encoding="utf-8")
            removed = podcast.remove_superseded_audio(
                course, ["practice/old.mp3", "practice/shared.mp3", "../course.json"]
            )
            self.assertEqual([path.name for path in removed], ["old.mp3"])
            self.assertEqual(
                sorted(path.name for path in practice.iterdir()), ["new.mp3", "shared.mp3"]
            )
            self.assertTrue((course / "course.json").is_file())
    def test_episode_artwork_is_optional_validated_and_url_encoded(self):
        source = Path(__file__).resolve().parents[1] / "podcast/swedish-polish/course.json"
        config = json.loads(source.read_text())
        config["episodes"] = config["episodes"][:2]
        with tempfile.TemporaryDirectory() as directory:
            course = Path(directory) / "swedish-polish"
            (course / "audio").mkdir(parents=True)
            (course / "cover.jpeg").write_bytes(b"show cover")
            for episode in config["episodes"]:
                audio = course / "audio" / episode["file"]
                audio.parent.mkdir(parents=True, exist_ok=True)
                audio.write_bytes(b"audio")
            image_path = "images/stories/test story/cover.jpeg"
            image = course / image_path
            image.parent.mkdir(parents=True)
            image.write_bytes(b"story cover")
            config["episodes"][0]["image"] = image_path
            catalog = course / "course.json"
            catalog.write_text(json.dumps(config))
            podcast.build_feed(course, "https://example.com/repeto")
            root = ET.parse(course / "feed.xml")
            items = root.findall("./channel/item")
            artwork = items[0].find(f"{{{podcast.ITUNES}}}image")
            self.assertIsNotNone(artwork)
            assert artwork is not None
            self.assertEqual(
                artwork.get("href"),
                "https://example.com/repeto/swedish-polish/"
                "images/stories/test%20story/cover-41b6d295.jpeg",
            )
            self.assertIsNone(items[1].find(f"{{{podcast.ITUNES}}}image"))
            show_artwork = root.find(f"./channel/{{{podcast.ITUNES}}}image")
            assert show_artwork is not None
            self.assertEqual(
                show_artwork.get("href"),
                "https://example.com/repeto/swedish-polish/cover-37fbc2b9.jpeg",
            )
            self.assertIn(
                'src="cover-37fbc2b9.jpeg"', (course / "index.html").read_text()
            )
            for invalid in (
                "../escape.jpeg", "/absolute.jpeg", "nested\\escape.jpeg",
                "nested/../escape.jpeg", "https://example.com/cover.jpeg",
                "", None, 42, "notes.txt",
            ):
                config["episodes"][0]["image"] = invalid
                catalog.write_text(json.dumps(config))
                with self.subTest(image=invalid):
                    with self.assertRaisesRegex(ValueError, "Invalid episode image"):
                        podcast.build_feed(course, "https://example.com/repeto")
            config["episodes"][0]["image"] = image_path
            catalog.write_text(json.dumps(config))
            for published in image.parent.iterdir():
                published.unlink()
            image.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "Missing or empty episode image"):
                podcast.build_feed(course, "https://example.com/repeto")
            image.unlink()
            with self.assertRaisesRegex(ValueError, "Missing or empty episode image"):
                podcast.build_feed(course, "https://example.com/repeto")

    def test_replaced_cover_gets_new_fingerprinted_url_without_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            cover = Path(directory) / "cover.jpeg"
            cover.write_bytes(b"old art")
            old = podcast.fingerprint_image(cover)
            self.assertFalse(cover.exists())
            self.assertEqual(podcast.fingerprint_image(cover), old)
            cover.write_bytes(b"new art")
            new = podcast.fingerprint_image(cover)
            self.assertNotEqual(new, old)
            self.assertEqual(sorted(Path(directory).iterdir()), [new])
            new.write_bytes(b"edited in place")
            edited = podcast.fingerprint_image(cover)
            self.assertNotEqual(edited, new)
            self.assertEqual(sorted(Path(directory).iterdir()), [edited])
            self.assertEqual(podcast.find_image(cover), edited)
            (Path(directory) / "cover-0000000a.jpeg").write_bytes(b"x")
            with self.assertRaisesRegex(ValueError, "Several published versions"):
                podcast.find_image(cover)

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
