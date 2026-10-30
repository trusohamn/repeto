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
ENGLISH_ITEMS = [
    {"id": f"phrase_{n}", "topic": "Greetings", "pl": pl, "en": en}
    for n, (pl, en) in enumerate(
        [("Cześć!", "Hello!"), ("Dziękuję!", "Thank you!"), ("Pa!", "Bye!"), ("Tak.", "Yes.")]
    )
]
TITLES = {"Greetings": {"se": "Hälsningar", "pl": "Powitania"}}
ENGLISH_TITLES = {"Greetings": {"pl": "Powitania", "en": "Greetings"}}
STORY = {
    "story_id": "test_story",
    "titles": {"sv": "Testberättelsen", "pl": "Testowa historia"},
    "chapters": [
        {"chapter_number": 1, "summary": {"sv": "Något händer."}},
        {"chapter_number": 2},
    ],
}


class DescriptionTests(unittest.TestCase):
    def test_swedish_and_spain_spanish_targets_for_polish_listeners(self):
        for target, genitive, adverb in (
            ("sv", "szwedzkiego", "szwedzku"),
            ("es", "hiszpańskiego", "hiszpańsku"),
        ):
            with self.subTest(target=target):
                self.assertEqual(
                    descriptions.show_title(target, source="pl"),
                    f"Repeto – Ucz się {genitive}",
                )
                text = descriptions.show_description(target, 30, [], "a@b.se", source="pl")
                self.assertIn(f"po {adverb}", text)
                self.assertIn("po polsku", text)
        self.assertEqual(
            descriptions.show_title("se", source="pl"),
            descriptions.show_title("sv", source="pl"),
        )

    def test_show_copy_explains_audience_and_usage(self):
        self.assertEqual(descriptions.show_title("pl"), "Repeto – Lär dig polska")
        self.assertEqual(descriptions.show_title("en"), "Repeto – Lär dig engelska")
        self.assertEqual(descriptions.show_title("ru"), "Repeto – Lär dig ryska")
        self.assertEqual(descriptions.show_title("ru", source="pl"), "Repeto – Ucz się rosyjskiego")
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
        self.assertIn("Säg svaret högt i pausen – öva på att själv komma på orden.", text)
        self.assertIn(
            "Bakgrundslyssning kan hjälpa dig att bli bekant med språkets ljud och melodi.",
            text,
        )
        self.assertIn("Öva också aktivt genom att härma och svara i pauserna.", text)
        self.assertNotIn("det är där du lär dig", text)
        self.assertIn("AI-genererade", text)
        self.assertIn("rättelser och idéer till nya berättelser är varmt välkomna: a@b.se", text)

    def test_polish_source_copy(self):
        self.assertEqual(
            descriptions.show_title("en", source="pl"),
            "Repeto – Ucz się angielskiego",
        )
        text = descriptions.show_description(
            "en", 30,
            [descriptions.story_name(
                {"pl": "Magiczne radio", "en": "The Magic Radio"}, "en", source="pl",
            )],
            "a@b.se",
            source="pl",
        )
        self.assertIn("Ucz się angielskiego", text)
        self.assertIn("Sezon 1 – Ćwiczenia: 30 krótkich tematów", text)
        self.assertIn("„Magiczne radio” (The Magic Radio)", text)
        self.assertIn("słuchasz rozdziału po angielsku", text)
        self.assertNotIn("po angielskiego", text)
        self.assertIn("Odpowiadaj na głos w przerwie", text)
        self.assertIn("Słuchanie w tle może pomóc oswoić się", text)
        self.assertIn("Głosy zostały wygenerowane przez AI", text)
        self.assertNotIn("nauczysz się", text.lower())

    def test_practice_description_accepts_polish_source(self):
        text = descriptions.practice_description(
            "en", 2, 30, ENGLISH_TITLES["Greetings"], ENGLISH_ITEMS, source="pl",
        )
        self.assertTrue(text.startswith("Temat 2 z 30: Powitania (Greetings) – 4 zwroty."))
        self.assertIn("• Cześć! → Hello!\n• Dziękuję! → Thank you!\n• Pa! → Bye!", text)
        self.assertIn("słowo lub zdanie po polsku", text)
        self.assertIn("Każdy angielski zwrot", text)

    def test_polish_story_description_uses_polish_summary(self):
        chapter = {
            "chapter_number": 1,
            "summary": {"pl": "Tajemnicza przesyłka trafia do domu."},
        }
        text = descriptions.story_description(
            "en",
            {"pl": "Magiczne radio", "en": "The Magic Radio"},
            chapter,
            2,
            source="pl",
        )
        self.assertTrue(text.startswith(
            "Rozdział 1 z 2 opowieści „Magiczne radio” (The Magic Radio). "
            "Tajemnicza przesyłka trafia do domu."
        ))
        self.assertIn("podpowiedź po polsku, przerwa, odpowiedź po angielsku", text)
        self.assertIn("sprawdź, ile udało Ci się zrozumieć", text)

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

            self.assertEqual(catalog["title"], "Repeto – Lär dig polska")
            self.assertEqual(catalog["seasons"], {"1": "Övningar", "2": "Testberättelsen"})
            self.assertIn("1 kort ämne", catalog["description"])
            self.assertIn("”Testberättelsen” (Testowa historia)", catalog["description"])
            practice, story, other = catalog["episodes"]
            self.assertIn("Ämne 1 av 1", practice["description"])
            self.assertIn("Kapitel 2 av 2", story["description"])
            self.assertEqual(other["description"], "kept")
            saved = json.loads((course / "course.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, catalog)

    def test_refresh_course_supports_polish_source(self):
        story = {
            "story_id": "test_story",
            "titles": {"pl": "Magiczne radio", "en": "The Magic Radio"},
            "chapters": [
                {"chapter_number": 1, "summary": {"pl": "Pojawia się zagadka."}},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            course = Path(directory)
            (course / "course.json").write_text(json.dumps({
                "title": "Old", "description": "Old", "email": "a@b.se",
                "source_language": "pl", "target_language": "en",
                "episodes": [
                    {"id": "repeto:polish-english:topic-01", "description": "old", "season": 1},
                    {"id": "test_story:pl:en:chapter-01", "description": "old", "season": 2},
                ],
            }), encoding="utf-8")

            catalog = descriptions.refresh_course(
                course, {"test_story": story}, ({"Greetings": ENGLISH_ITEMS}, ENGLISH_TITLES),
                source="pl",
            )

            self.assertEqual(catalog["title"], "Repeto – Ucz się angielskiego")
            self.assertEqual(
                catalog["seasons"], {"1": "Ćwiczenia", "2": "Magiczne radio"},
            )
            practice, chapter = catalog["episodes"]
            self.assertIn("Temat 1 z 1", practice["description"])
            self.assertIn("Rozdział 1 z 1", chapter["description"])
            self.assertIn("Pojawia się zagadka.", chapter["description"])
            self.assertIn("„Magiczne radio” (The Magic Radio)", catalog["description"])


if __name__ == "__main__":
    unittest.main()
