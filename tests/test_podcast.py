import importlib.util
import json
import re
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
    def _site(self, root: Path) -> list[Path]:
        practice = {"topics": [
            {"topic": "Greetings", "names": {"se": "Hälsningar", "en": "Greetings"},
             "phrases": [{"se": "Hej", "en": "Hello", "es": "Hola"},
                         {"se": "Tack", "en": "Thank you", "es": "Gracias"}]},
        ]}
        self.stories = {"magical_radio": {"titles": {"pl": "Magiczne radio"}, "chapters": [{
            "chapter_number": 1, "titles": {"pl": "Stary stół"},
            "chapter_text": {"sv": "Det är lördag.\n\nMaja är nio.", "es": "Es sábado.", "en": "It is Saturday."},
            "vocabulary": [{"id": f"w{i}", "text": {"sv": f"ord{i}", "es": f"palabra{i}", "en": f"word{i}"}}
                           for i in range(6)],
        }]}}
        courses = []
        for slug, source, target, title, links in (
            ("swedish-spanish", "sv", "es", "Repeto.stream – Jag lär mig spanska & mer", {}),
            ("english-swedish", "en", "sv", "Repeto.stream – I learn Swedish", {
                "Spotify": "https://open.spotify.com/show/4pCmGojSZmODKl9qvxTrgq",
                "YouTube": "https://www.youtube.com/playlist?list=PLaiumH4cRmVQ",
            }),
        ):
            course = root / slug
            (course / "images/stories/magical_radio").mkdir(parents=True)
            (course / "cover.jpeg").write_bytes(slug.encode())
            (course / "images/stories/magical_radio/cover.jpeg").write_bytes(b"story")
            config = {
                "title": title, "language": source, "source_language": source, "target_language": target,
                "description": "First paragraph.\n\nMore details.",
                "seasons": {"1": "Practice", "2": "The Magical Radio"},
                "episodes": [
                    {"id": f"repeto:{slug}:topic-01", "title": "Greetings", "season": 1, "episode": 1,
                     "duration_ms": 300000, "description": "Topic one.\n\nMore."},
                    {"id": f"repeto:{slug}:topic-02", "title": "Missing", "season": 1, "episode": 2,
                     "duration_ms": 60000, "description": "No transcript data."},
                    {"id": f"magical_radio:{source}:{target}:chapter-01", "title": "Chapter 1",
                     "season": 2, "episode": 1, "duration_ms": 600000, "description": "Story.",
                     "image": "images/stories/magical_radio/cover.jpeg"},
                ],
            }
            if links:
                config["links"] = links
            (course / "course.json").write_text(json.dumps(config), encoding="utf-8")
            podcast.fingerprint_image(course / "cover.jpeg")
            podcast.fingerprint_image(course / "images/stories/magical_radio/cover.jpeg")
            courses.append(course)
        (root / "swedish-spanish/transcripts").mkdir()
        (root / "swedish-spanish/transcripts/stale.html").write_text("old")
        podcast.build_index(root, courses, "https://example.com", practice=practice, stories=self.stories)
        return courses

    def test_homepage_links_cards_to_course_pages_without_feeds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            courses = self._site(root)
            page = (root / "index.html").read_text(encoding="utf-8")
            self.assertEqual(page.count('<a class="card"'), 2)
            self.assertIn('<a class="card" href="swedish-spanish/" data-source="sv" data-target="es">', page)
            self.assertIn('<a class="card" href="english-swedish/" data-source="en" data-target="sv">', page)
            self.assertIn('<h4 lang="sv">Jag lär mig spanska &amp; mer</h4>', page)
            self.assertLess(page.index('data-source="sv"'), page.index('data-source="en"'))
            self.assertNotIn("feed.xml", page)
            self.assertNotIn("<audio", page)
            self.assertNotIn("<iframe", page)
            self.assertIn('href="https://github.com/trusohamn/repeto"', page)
            self.assertIn("MIT", page)
            self.assertIn("Suggest a correction", page)
            self.assertIn("Request a language", page)
            self.assertIn('class="steps"', page)
            css = re.search(r'<link rel="stylesheet" href="(assets/site-[0-9a-f]{10}\.css)">', page).group(1)
            self.assertIn("prefers-reduced-motion", (root / css).read_text(encoding="utf-8"))
            self.assertRegex(page, r'<script src="assets/site-[0-9a-f]{10}\.js" defer></script>')
            self.assertNotIn("<style", page)
            self.assertEqual(len(list((root / "assets").iterdir())), 2)
            self.assertIn('<option value="sv" lang="sv">svenska</option>', page)
            self.assertIn('"name": "spanska"', page)
            self.assertIn('"speak": "Jag talar"', page)
            self.assertNotIn('class="chip"', page)
            self.assertIn('<link rel="icon" type="image/png" sizes="32x32" href="favicon.png">', page)
            self.assertIn('<link rel="canonical" href="https://example.com/">', page)
            self.assertIn('<meta property="og:image" content="https://example.com/social.jpeg">', page)
            self.assertIn('src="images/stories/magical_radio/cover-', page.replace("swedish-spanish/", ""))
            original = page
            podcast.build_index(root, courses, "https://example.com", practice=None, stories=self.stories)
            podcast.build_index(root, courses, "https://example.com",
                                practice={"topics": []}, stories=self.stories)
            self.assertEqual((root / "index.html").read_text(encoding="utf-8"), original)

    def test_course_page_is_localized_with_listen_links_and_transcripts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._site(root)
            english = (root / "english-swedish/index.html").read_text(encoding="utf-8")
            swedish = (root / "swedish-spanish/index.html").read_text(encoding="utf-8")
            for page in (english, swedish):
                self.assertNotIn("<audio", page)
                self.assertNotIn("feed.xml", page)
                self.assertNotIn("<iframe", page)
                self.assertIn('href="../favicon.png"', page)
                self.assertIn('href="transcripts/season-1-episode-01.html"', page)
                self.assertIn('href="transcripts/season-2-episode-01.html"', page)
                self.assertIn('<h3><a href="transcripts/season-1-episode-02.html">', page)
                self.assertIn('href="transcripts/season-1.html"', page)
            self.assertIn('href="https://open.spotify.com/show/4pCmGojSZmODKl9qvxTrgq"', english)
            self.assertIn('<html lang="en">', english)
            self.assertIn("Listen on YouTube", english)
            self.assertIn('<html lang="sv">', swedish)
            self.assertNotIn("open.spotify.com", swedish)
            self.assertIn("Kursen kommer snart till Spotify.", swedish)
            self.assertIn("Svenska → Spanska", swedish)
            self.assertIn("<h1>Jag lär mig spanska &amp; mer</h1>", swedish)
            self.assertIn("3 avsnitt", swedish.replace("<b>3</b><span>", "3 "))
            self.assertIn("Hittat ett fel?", swedish)

    def test_transcripts_follow_spoken_order_and_replace_stale_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._site(root)
            folder = root / "swedish-spanish/transcripts"
            self.assertEqual(sorted(path.name for path in folder.iterdir()), [
                "season-1-episode-01.html", "season-1-episode-02.html", "season-1.html",
                "season-2-episode-01.html", "season-2.html",
            ])
            empty = (folder / "season-1-episode-02.html").read_text(encoding="utf-8")
            self.assertIn("Det finns inget transkript för det här avsnittet än.", empty)
            self.assertNotIn("data-print", empty)
            practice = (folder / "season-1-episode-01.html").read_text(encoding="utf-8")
            self.assertIn('<td lang="sv">Hej</td><td lang="es">Hola</td>', practice)
            self.assertLess(practice.index("Hola"), practice.index("Gracias"))
            self.assertIn('data-print', practice)
            self.assertRegex(practice, r'href="\.\./\.\./assets/site-[0-9a-f]{10}\.css"')
            self.assertIn('href="../../favicon.png"', practice)
            story = (folder / "season-2-episode-01.html").read_text(encoding="utf-8")
            self.assertIn('<div class="target" lang="es">', story)
            self.assertIn("<p>Det är lördag.</p><p>Maja är nio.</p>", story)
            chapter = self.stories["magical_radio"]["chapters"][0]
            vocabulary = list(chapter["vocabulary"])
            import random
            random.Random("1:Stary stół").shuffle(vocabulary)
            positions = [story.index(f'<td lang="es">{item["text"]["es"]}</td>') for item in vocabulary]
            self.assertEqual(positions, sorted(positions))
            self.assertNotEqual([item["id"] for item in vocabulary], [f"w{i}" for i in range(6)])
            season = (folder / "season-1.html").read_text(encoding="utf-8")
            self.assertEqual(season.count('<article class="sheet">'), 1)
            self.assertIn('<h2 class="title">Greetings</h2>', season)

    def test_sitemap_and_robots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._site(root)
            sitemap = (root / "sitemap.xml").read_text(encoding="utf-8")
            ET.fromstring(sitemap)
            self.assertIn("<loc>https://example.com/</loc>", sitemap)
            self.assertIn("<loc>https://example.com/swedish-spanish/</loc>", sitemap)
            self.assertIn("<loc>https://example.com/swedish-spanish/transcripts/season-2.html</loc>", sitemap)
            robots = (root / "robots.txt").read_text(encoding="utf-8")
            self.assertIn("Disallow: /*/audio/", robots)
            self.assertIn("Sitemap: https://example.com/sitemap.xml", robots)

    def test_homepage_rejects_unverified_spotify_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            course = root / "course"
            course.mkdir()
            (course / "cover.jpeg").write_bytes(b"cover")
            config = {"language": "sv", "title": "Repeto", "episodes": [{}]}
            for url in ("https://example.com/show/4pCmGojSZmODKl9qvxTrgq",
                        "https://open.spotify.com/search/Repeto", "javascript:alert(1)"):
                config["links"] = {"Spotify": url}
                (course / "course.json").write_text(json.dumps(config), encoding="utf-8")
                with self.subTest(url=url), self.assertRaisesRegex(ValueError, "Invalid Spotify"):
                    podcast.build_index(root, [course])

    def test_homepage_rejects_invalid_youtube_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            course = root / "course"
            course.mkdir()
            (course / "cover.jpeg").write_bytes(b"cover")
            config = {"language": "en", "title": "Repeto", "episodes": [{}]}
            for url in (
                "javascript:alert(1)",
                "https://example.com/playlist?list=PLXdnYK4NDPvE",
                "https://www.youtube.com/@repeto-ling/podcasts",
                "https://www.youtube.com/playlist?list=PLXdnYK4NDPvE&extra=1",
            ):
                config["links"] = {"YouTube": url}
                (course / "course.json").write_text(json.dumps(config), encoding="utf-8")
                with self.subTest(url=url), self.assertRaisesRegex(ValueError, "Invalid YouTube"):
                    podcast.build_index(root, [course])

    def test_text_to_html_renders_paragraphs_and_lists(self):
        self.assertEqual(
            podcast.text_to_html("Hej <du>!\nRad två\n\nSteg:\n1. Lyssna\n2. Prata\n\n• a\n• b"),
            "<p>Hej &lt;du&gt;!<br>Rad två</p><p>Steg:</p><ol><li>Lyssna</li>"
            "<li>Prata</li></ol><ul><li>a</li><li>b</li></ul>",
        )

    def test_story_rows_drop_repeated_story_name(self):
        website = __import__("website")
        self.assertEqual(website.story_title("Den magiska radion: Det gamla bordet — La mesa vieja", "Den magiska radion"),
                         "Det gamla bordet — La mesa vieja")
        self.assertEqual(website.story_title("Hälsningar — Saludos", "Övningar"), "Hälsningar — Saludos")
        for text, story in (
            ('Chapter 1 of 8 in "The Magical Radio" (La radio magique). Two siblings find a radio.', "The Magical Radio"),
            ("История «Волшебное радио» (La radio mágica). Глава 1 из 8. Two siblings find a radio.", "Волшебное радио"),
        ):
            with self.subTest(story=story):
                self.assertEqual(website.story_summary(text, story), "Two siblings find a radio.")

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
            self.assertFalse((course / "index.html").exists())
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
            page = "https://example.com/repeto/swedish-polish/transcripts/season-1-episode-01.html"
            self.assertEqual(items[0].findtext("link"), page)
            self.assertTrue(items[0].findtext("description", "").endswith(f"\n\nTranskript: {page}"))
            self.assertIn(f'<a href="{page}">', items[0].findtext(f"{{{podcast.CONTENT}}}encoded", ""))
            self.assertTrue(root.findtext("./channel/description", "").endswith(
                "\n\nAlla avsnitt och transkript: https://example.com/repeto/swedish-polish/"))
            self.assertEqual(items[0].findtext(f"{{{podcast.ITUNES}}}season"), "1")
            self.assertEqual(items[0].findtext(f"{{{podcast.ITUNES}}}episode"), "1")
            enclosure = items[0].find("enclosure")
            assert enclosure is not None
            self.assertEqual(enclosure.get("length"), "5")
            self.assertEqual(enclosure.get("type"), "audio/mpeg")
            self.assertTrue(enclosure.get("url", "").startswith(
                "https://example.com/repeto/swedish-polish/audio/practice/"
            ))
            podcast.build_feed(course, "https://repeto.stream")
            migrated = ET.parse(course / "feed.xml")
            self.assertEqual(
                [(item.findtext("guid"), item.findtext("pubDate")) for item in items],
                [(item.findtext("guid"), item.findtext("pubDate"))
                 for item in migrated.findall("./channel/item")],
            )
            self_link = migrated.find(f"./channel/{{{podcast.ATOM}}}link")
            assert self_link is not None
            self.assertEqual(self_link.get("href"), "https://repeto.stream/swedish-polish/feed.xml")
            self.assertNotIn("https://example.com/repeto", (course / "feed.xml").read_text())
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
