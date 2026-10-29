import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("descriptions", ROOT / "code" / "descriptions.py")
assert SPEC is not None and SPEC.loader is not None
descriptions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(descriptions)

ITEMS = [
    {"id": f"phrase_{n}", "topic": "Greetings", "se": se, "pl": pl}
    for n, (se, pl) in enumerate(
        [("Hej!", "Cześć!"), ("Tack!", "Dziękuję!"), ("Hejdå!", "Pa!"), ("Ja.", "Tak.")]
    )
]
TITLES = {"Greetings": {"se": "Hälsningar", "pl": "Powitania"}}
STORY = {
    "story_id": "test_story",
    "titles": {"sv": "Testberättelsen", "pl": "Testowa historia"},
    "chapters": [
        {"chapter_number": 1, "summary": {"sv": "Något händer."}},
        {"chapter_number": 2},
    ],
}


class DescriptionTests(unittest.TestCase):
    def test_show_copy_explains_audience_and_usage(self):
        self.assertEqual(descriptions.show_title("pl"), "Repeto – Polska för svensktalande")
        text = descriptions.show_description(
            "pl", 30, [descriptions.story_name({"sv": "Den magiska radion", "pl": "Magiczne Radio"}, "pl")],
            "a@b.se",
        )
        self.assertIn("nybörjare i alla åldrar", text)
        self.assertIn("Säsong 1 – Övningar: 30 korta ämnen", text)
        self.assertIn("Säsong 2 – Berättelsen ”Den magiska radion” (Magiczne Radio)", text)
        self.assertIn("Repeto finns även på andra språk", text)
        self.assertNotIn("http", text)
        self.assertIn("Fler berättelser är på väg", text)
        self.assertIn("Även att lyssna i bakgrunden hjälper", text)
        self.assertIn("AI-genererade", text)
        self.assertIn("rättelser och idéer till nya berättelser är varmt välkomna: a@b.se", text)

    def test_unknown_language_is_rejected(self):
        with self.assertRaises(ValueError):
            descriptions.show_title("de")

    def test_practice_description_lists_examples(self):
        text = descriptions.practice_description("pl", 2, 30, TITLES["Greetings"], ITEMS)
        self.assertTrue(text.startswith("Ämne 2 av 30: Hälsningar (Powitania) – 4 fraser."))
        self.assertIn("• Hej! → Cześć!\n• Tack! → Dziękuję!\n• Hejdå! → Pa!", text)
        self.assertNotIn("Ja.", text)
        self.assertIn("Varje polsk fras", text)

    def test_story_description_uses_optional_summary(self):
        first = descriptions.story_description("pl", STORY["titles"], STORY["chapters"][0], 2)
        second = descriptions.story_description("pl", STORY["titles"], STORY["chapters"][1], 2)
        self.assertTrue(first.startswith(
            "Kapitel 1 av 2 i berättelsen ”Testberättelsen” (Testowa historia). Något händer."
        ))
        self.assertTrue(second.startswith(
            "Kapitel 2 av 2 i berättelsen ”Testberättelsen” (Testowa historia).\n\n"
        ))

    def test_refresh_course_rewrites_titles_and_descriptions(self):
        with tempfile.TemporaryDirectory() as directory:
            course = Path(directory)
            (course / "course.json").write_text(json.dumps({
                "title": "Old", "description": "Old", "email": "a@b.se",
                "source_language": "sv", "target_language": "pl",
                "episodes": [
                    {"id": "repeto:swedish-polish:topic-01", "description": "old", "season": 1},
                    {"id": "test_story:sv:pl:chapter-02", "description": "old", "season": 2},
                    {"id": "something-else", "description": "kept"},
                ],
            }), encoding="utf-8")

            catalog = descriptions.refresh_course(
                course, {"test_story": STORY}, ({"Greetings": ITEMS}, TITLES),
            )

            self.assertEqual(catalog["title"], "Repeto – Polska för svensktalande")
            self.assertEqual(catalog["seasons"], {"1": "Övningar", "2": "Testberättelsen"})
            self.assertIn("1 kort ämne", catalog["description"])
            self.assertIn("”Testberättelsen” (Testowa historia)", catalog["description"])
            practice, story, other = catalog["episodes"]
            self.assertIn("Ämne 1 av 1", practice["description"])
            self.assertIn("Kapitel 2 av 2", story["description"])
            self.assertEqual(other["description"], "kept")
            saved = json.loads((course / "course.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, catalog)


if __name__ == "__main__":
    unittest.main()
