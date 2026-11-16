import json
import hashlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
import package_draft
import podcast


class DraftPackagingTests(unittest.TestCase):
    def test_install_preserves_cover_is_idempotent_and_feed_keeps_artwork(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "output") as directory:
            root = Path(directory)
            draft_root = root / "draft"
            args = package_draft.create_parser().parse_args([
                "--source", "pl", "--target", "de", "--course", "polish-german",
                "--output-root", str(draft_root), "--cover", str(ROOT / "podcast/english-russian/cover.jpeg"),
            ])
            package_draft.package(args)
            destination = root / "podcast/polish-german"
            destination.mkdir(parents=True)
            cover = destination / "cover.jpeg"
            cover.write_bytes(args.cover.read_bytes())
            unrelated = destination / "keep.txt"
            unrelated.write_text("unchanged")
            package_draft.install_draft(draft_root, "polish-german", root / "podcast")
            first = {p.relative_to(destination): p.read_bytes() for p in destination.rglob("*") if p.is_file()}
            package_draft.install_draft(draft_root, "polish-german", root / "podcast")
            self.assertEqual(first, {p.relative_to(destination): p.read_bytes() for p in destination.rglob("*") if p.is_file()})
            self.assertEqual(cover.read_bytes(), args.cover.read_bytes())
            digest = hashlib.sha256(cover.read_bytes()).hexdigest()[:8]
            self.assertEqual((destination / f"cover-{digest}.jpeg").read_bytes(), cover.read_bytes())
            feed = ET.parse(destination / "feed.xml")
            items = feed.findall("./channel/item")
            self.assertEqual(len(items), 38)
            self.assertTrue(all(item.find("enclosure") is None for item in items))
            catalog = json.loads((destination / "course.json").read_text())
            for episode in catalog["episodes"]:
                episode.pop("pending_audio")
                episode.update(file="practice/ready.mp3", duration_ms=1000,
                               bytes=4, sha256="a" * 64)
            (destination / "course.json").write_text(json.dumps(catalog))
            podcast.build_feed(destination, "https://example.com")
            self.assertEqual(cover.read_bytes(), args.cover.read_bytes())
            self.assertEqual((destination / f"cover-{digest}.jpeg").read_bytes(), cover.read_bytes())
            self.assertEqual(unrelated.read_text(), "unchanged")

    def test_install_rejects_collisions_before_writing(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "output") as directory:
            root = Path(directory)
            draft_root = root / "draft"
            args = package_draft.create_parser().parse_args([
                "--source", "pl", "--target", "de", "--course", "polish-german",
                "--output-root", str(draft_root), "--cover", str(ROOT / "podcast/english-russian/cover.jpeg"),
            ])
            package_draft.package(args)
            destination = root / "podcast/polish-german"
            destination.mkdir(parents=True)
            (destination / "cover.jpeg").write_bytes(b"different")
            with self.assertRaisesRegex(FileExistsError, "different artwork"):
                package_draft.install_draft(draft_root, "polish-german", root / "podcast")
            self.assertEqual([p.name for p in destination.iterdir()], ["cover.jpeg"])
            (destination / "cover.jpeg").write_bytes(args.cover.read_bytes())
            (destination / "course.json").write_text("authored")
            with self.assertRaisesRegex(FileExistsError, "different file"):
                package_draft.install_draft(draft_root, "polish-german", root / "podcast")
            self.assertEqual((destination / "course.json").read_text(), "authored")
            self.assertEqual(len(list(destination.iterdir())), 2)

    def test_real_sources_produce_stable_two_season_draft_and_transcripts(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "output") as directory:
            root = Path(directory)
            args = package_draft.create_parser().parse_args([
                "--source", "en", "--target", "ru", "--course", "english-russian",
                "--output-root", str(root), "--cover", str(ROOT / "podcast/english-russian/cover.jpeg"),
            ])
            first = package_draft.package(args)
            course = root / "english-russian"
            self.assertEqual(len(first["episodes"]), 38)
            self.assertEqual({ep["season"] for ep in first["episodes"]}, {1, 2})
            self.assertTrue(all(ep["pending_audio"] is True for ep in first["episodes"]))
            for episode in first["episodes"]:
                self.assertFalse({"file", "duration_ms", "bytes", "sha256"} & episode.keys())
            self.assertEqual(first, package_draft.package(args))
            feed = ET.parse(course / "feed.xml")
            items = feed.findall("./channel/item")
            self.assertEqual(len(items), 38)
            self.assertTrue(all(item.find("enclosure") is None for item in items))
            self.assertTrue(all(item.find(f"{{{podcast.ITUNES}}}duration") is None for item in items))
            self.assertEqual(items[0].findtext("guid"), first["episodes"][0]["id"])
            transcript = (course / "transcripts/season-1-episode-01.html").read_text()
            self.assertIn("Привет!", transcript)
            self.assertNotIn('class="length"', transcript)
            self.assertTrue((course / "transcripts/season-2-episode-01.html").is_file())
            original_feed = (course / "feed.xml").read_bytes()
            with self.assertRaisesRegex(ValueError, "Pending audio"):
                podcast.build_feed(course, "https://example.com")
            self.assertEqual((course / "feed.xml").read_bytes(), original_feed)
            catalog = json.loads((course / "course.json").read_text())
            completed = catalog["episodes"][0]
            completed.pop("pending_audio")
            completed.update(file="practice/ready.mp3", duration_ms=3000)
            audio = course / "audio/practice/ready.mp3"
            audio.parent.mkdir(parents=True)
            audio.write_bytes(b"audio")
            (course / "course.json").write_text(json.dumps(catalog))
            podcast.build_feed(course, "https://example.com", draft=True)
            mixed = ET.parse(course / "feed.xml").findall("./channel/item")
            self.assertEqual(mixed[0].find("enclosure").get("length"), "5")
            self.assertEqual(mixed[0].findtext(f"{{{podcast.ITUNES}}}duration"), "3")
            self.assertIsNone(mixed[1].find("enclosure"))
            with self.assertRaisesRegex(ValueError, "Pending audio"):
                podcast.build_feed(course, "https://example.com")
            with self.assertRaisesRegex(ValueError, "completed episodes"):
                package_draft.package(args)

    def test_draft_rejects_pending_audio_metadata_and_invalid_flag(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "output") as directory:
            course = Path(directory)
            (course / "cover.jpeg").write_bytes(b"cover")
            catalog = {"episodes": [{"id": "test", "pending_audio": True, "file": "fake.mp3"}]}
            (course / "course.json").write_text(json.dumps(catalog))
            with self.assertRaisesRegex(ValueError, "audio metadata"):
                podcast.build_feed(course, "https://example.com", draft=True)
            catalog["episodes"] = [{"id": "test", "pending_audio": False}]
            (course / "course.json").write_text(json.dumps(catalog))
            with self.assertRaisesRegex(ValueError, "pending_audio"):
                podcast.build_feed(course, "https://example.com", draft=True)

    def test_draft_refuses_production_root(self):
        args = package_draft.create_parser().parse_args([
            "--source", "en", "--target", "ru", "--course", "english-russian",
            "--output-root", str(ROOT / "podcast"),
            "--cover", str(ROOT / "podcast/english-russian/cover.jpeg"),
        ])
        with self.assertRaisesRegex(ValueError, "separate"):
            package_draft.package(args)


if __name__ == "__main__":
    unittest.main()
