import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from audio_targets import AudioTarget, infer_audio_targets, render_report  # pyright: ignore[reportMissingImports]


class AudioTargetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.base = self.root / "base"
        self.head = self.root / "head"
        for root in (self.base, self.head):
            root.mkdir()
            self._write(
                root / "courses/practice/transcript.json",
                [
                    {
                        "id": 1, "topic": "Greetings", "en": "Hello.",
                        "pl": "Cześć.", "se": "Hej.", "fr": "Bonjour.",
                    },
                    {
                        "id": 2, "topic": "Greetings", "en": "Goodbye.",
                        "pl": "Do widzenia.", "se": "Hej då.", "fr": "Au revoir.",
                    },
                ],
            )
            self._write(
                root / "courses/stories/magical_radio/generated/transcript.json",
                {
                    "story_id": "magical_radio",
                    "titles": {"pl": "Magiczne radio", "en": "The Magic Radio"},
                    "chapters": [
                        {
                            "chapter_number": 1,
                            "titles": {"pl": "Początek", "en": "The Beginning"},
                            "summary": {"pl": "Streszczenie.", "en": "A summary."},
                            "chapter_text": {"pl": "Tekst.", "en": "Story text."},
                            "vocabulary": [
                                {"id": "word-1", "text": {"pl": "dom", "en": "house"}}
                            ],
                        }
                    ],
                },
            )
            (root / "courses/stories/magical_radio/complete").mkdir(parents=True)
            (root / "courses/stories/magical_radio/complete/pl.txt").write_text(
                "Tekst.", encoding="utf-8"
            )
            self._write_catalogs(root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _write(path: Path, data: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def _write_catalogs(self, root: Path) -> None:
        catalogs = {
            "english-polish": ("en", "pl", ["repeto:english-polish:topic-01", "magical_radio:en:pl:chapter-01"]),
            "polish-english": ("pl", "en", ["repeto:polish-english:topic-01", "magical_radio:pl:en:chapter-01"]),
            "english-swedish": ("en", "sv", ["repeto:english-swedish:topic-01", "magical_radio:en:sv:chapter-01"]),
            "english-french": ("en", "fr", ["repeto:english-french:topic-01"]),
        }
        for slug, (source, target, episode_ids) in catalogs.items():
            self._write(
                root / "podcast" / slug / "course.json",
                {
                    "source_language": source,
                    "target_language": target,
                    "episodes": [{"id": episode_id} for episode_id in episode_ids],
                },
            )

    def test_practice_text_change_reports_all_catalog_directions(self) -> None:
        transcript = json.loads(
            (self.head / "courses/practice/transcript.json").read_text(encoding="utf-8")
        )
        transcript[0]["en"] = "Hi there."
        self._write(self.head / "courses/practice/transcript.json", transcript)

        targets = infer_audio_targets(self.base, self.head)

        self.assertEqual(
            targets,
            [
                AudioTarget("practice", "english-french", "en", "fr"),
                AudioTarget("practice", "english-polish", "en", "pl"),
                AudioTarget("practice", "english-swedish", "en", "se"),
                AudioTarget("practice", "polish-english", "pl", "en"),
            ],
        )

    def test_topic_title_or_story_summary_only_does_not_trigger_tts(self) -> None:
        story_path = self.head / "courses/stories/magical_radio/generated/transcript.json"
        story = json.loads(story_path.read_text(encoding="utf-8"))
        story["chapters"][0]["summary"]["en"] = "A revised summary."
        self._write(story_path, story)

        self.assertEqual(infer_audio_targets(self.base, self.head), [])
        self.assertIn("do not trigger TTS", render_report([]))

    def test_story_spoken_text_change_reports_only_packaged_story_directions(self) -> None:
        story_path = self.head / "courses/stories/magical_radio/generated/transcript.json"
        story = json.loads(story_path.read_text(encoding="utf-8"))
        story["chapters"][0]["chapter_text"]["en"] = "Revised story text."
        self._write(story_path, story)

        self.assertEqual(
            infer_audio_targets(self.base, self.head),
            [
                AudioTarget("story", "polish-english", "pl", "en", "magical_radio", (1,)),
            ],
        )

    def test_story_vocabulary_change_affects_source_and_target_directions(self) -> None:
        story_path = self.head / "courses/stories/magical_radio/generated/transcript.json"
        story = json.loads(story_path.read_text(encoding="utf-8"))
        story["chapters"][0]["vocabulary"][0]["text"]["en"] = "home"
        self._write(story_path, story)

        self.assertEqual(
            infer_audio_targets(self.base, self.head),
            [
                AudioTarget("story", "english-polish", "en", "pl", "magical_radio", (1,)),
                AudioTarget("story", "english-swedish", "en", "sv", "magical_radio", (1,)),
                AudioTarget("story", "polish-english", "pl", "en", "magical_radio", (1,)),
            ],
        )

    def test_story_source_text_change_reports_narration_target(self) -> None:
        source_text = self.head / "courses/stories/magical_radio/complete/pl.txt"
        source_text.write_text("Zmieniony tekst.", encoding="utf-8")

        self.assertEqual(
            infer_audio_targets(self.base, self.head),
            [
                AudioTarget("story", "english-polish", "en", "pl", "magical_radio", (1,)),
            ],
        )

    def test_story_changes_are_scoped_per_chapter_and_language(self) -> None:
        for root in (self.base, self.head):
            story_path = root / "courses/stories/magical_radio/generated/transcript.json"
            story = json.loads(story_path.read_text(encoding="utf-8"))
            second = json.loads(json.dumps(story["chapters"][0]))
            second["chapter_number"] = 2
            story["chapters"].append(second)
            self._write(story_path, story)
        story_path = self.head / "courses/stories/magical_radio/generated/transcript.json"
        story = json.loads(story_path.read_text(encoding="utf-8"))
        story["chapters"][1]["vocabulary"][0]["text"]["en"] = "home"
        story["chapters"][0]["chapter_text"]["pl"] = "Zmiana."
        self._write(story_path, story)

        targets = infer_audio_targets(self.base, self.head)

        self.assertEqual(targets, [
            AudioTarget("story", "english-polish", "en", "pl", "magical_radio", (1, 2)),
            AudioTarget("story", "english-swedish", "en", "sv", "magical_radio", (2,)),
            AudioTarget("story", "polish-english", "pl", "en", "magical_radio", (2,)),
        ])
        self.assertIn("chapters 1, 2", render_report(targets))

    def test_narration_directions_change_triggers_only_its_chapter(self) -> None:
        directions = self.head / "courses/stories/magical_radio/generated/narration.json"
        self._write(directions, {"pl": {"1": [{"text": "Tekst."}]}})
        self.assertEqual(infer_audio_targets(self.base, self.head), [
            AudioTarget("story", "english-polish", "en", "pl", "magical_radio", (1,))
        ])

    def test_story_title_change_only_affects_first_chapter(self) -> None:
        for root in (self.base, self.head):
            story_path = root / "courses/stories/magical_radio/generated/transcript.json"
            story = json.loads(story_path.read_text(encoding="utf-8"))
            second = json.loads(json.dumps(story["chapters"][0]))
            second["chapter_number"] = 2
            story["chapters"].append(second)
            self._write(story_path, story)
        story_path = self.head / "courses/stories/magical_radio/generated/transcript.json"
        story = json.loads(story_path.read_text(encoding="utf-8"))
        story["titles"]["en"] = "A new title"
        self._write(story_path, story)
        self.assertEqual(infer_audio_targets(self.base, self.head), [
            AudioTarget("story", "polish-english", "pl", "en", "magical_radio", (1,))
        ])

    def test_vocabulary_reordering_changes_the_chapter(self) -> None:
        for root in (self.base, self.head):
            story_path = root / "courses/stories/magical_radio/generated/transcript.json"
            story = json.loads(story_path.read_text(encoding="utf-8"))
            story["chapters"][0]["vocabulary"].append(
                {"id": "word-2", "text": {"pl": "kot", "en": "cat"}}
            )
            if root == self.head:
                story["chapters"][0]["vocabulary"].reverse()
            self._write(story_path, story)
        self.assertEqual(infer_audio_targets(self.base, self.head), [
            AudioTarget("story", "english-polish", "en", "pl", "magical_radio", (1,)),
            AudioTarget("story", "english-swedish", "en", "sv", "magical_radio", (1,)),
            AudioTarget("story", "polish-english", "pl", "en", "magical_radio", (1,)),
        ])

    def test_removing_story_chapter_fails_explicitly(self) -> None:
        story_path = self.head / "courses/stories/magical_radio/generated/transcript.json"
        story = json.loads(story_path.read_text(encoding="utf-8"))
        story["chapters"] = []
        self._write(story_path, story)
        with self.assertRaisesRegex(ValueError, "Removing story chapter 1"):
            infer_audio_targets(self.base, self.head)

    def test_report_lists_generation_scope_and_cache_behavior(self) -> None:
        report = render_report([AudioTarget("practice", "english-polish", "en", "pl")])

        self.assertIn("practice: english-polish (en -> pl)", report)
        self.assertIn("reuse verified cached clips", report)
        self.assertIn("no audio has been generated", report)


if __name__ == "__main__":
    unittest.main()
