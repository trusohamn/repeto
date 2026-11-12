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
    def test_russian_audience_copy_and_counts(self):
        self.assertEqual(descriptions.show_title("es", source="ru"), "Repeto.stream – Я учу испанский")
        self.assertEqual(
            descriptions.show_title("se", source="ru"),
            descriptions.show_title("sv", source="ru"),
        )
        text = descriptions.show_description("es", 30, [], "a@b.se", source="ru")
        self.assertIn("30 коротких тем", text)
        self.assertIn("по-русски", text)
        self.assertIn("по-испански", text)
        self.assertIn("ответ звучит дважды", text)
        self.assertIn("Голоса созданы с помощью ИИ", text)
        for count, phrase in ((1, "1 фраза"), (2, "2 фразы"), (5, "5 фраз"),
                              (11, "11 фраз"), (21, "21 фраза"), (22, "22 фразы"),
                              (25, "25 фраз"), (111, "111 фраз")):
            with self.subTest(count=count):
                text = descriptions.practice_description(
                    "es", 1, 30, {"ru": "Приветствия", "es": "Saludos"},
                    [{"ru": "Привет!", "es": "¡Hola!"}] * count, source="ru",
                )
                self.assertIn(phrase + ".", text)
                self.assertIn("Привет! → ¡Hola!", text)
                self.assertIn("Каждая фраза на изучаемом языке звучит дважды", text)
        with self.assertRaises(ValueError):
            descriptions.show_title("it", source="ru")

    def test_refresh_russian_source_includes_teaser_and_seasons(self):
        story = {
            "story_id": "test_story",
            "titles": {"ru": "Волшебное радио", "es": "La radio mágica"},
            "chapters": [
                {"chapter_number": 1, "summary": {"ru": "Начинается приключение."}},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            course = Path(directory)
            (course / "course.json").write_text(json.dumps({
                "title": "Old", "description": "Old", "email": "a@b.se",
                "source_language": "ru", "target_language": "es",
                "episodes": [
                    {"id": "repeto:russian-spanish:topic-01", "description": "old", "season": 1},
                    {"id": "test_story:ru:es:chapter-01", "description": "old", "season": 2},
                ],
            }), encoding="utf-8")
            catalog = descriptions.refresh_course(
                course, {"test_story": story},
                ({"Greetings": [{"ru": "Привет!", "es": "¡Hola!"}]},
                 {"Greetings": {"ru": "Приветствия", "es": "Saludos"}}),
                source="ru",
            )
            self.assertEqual(catalog["title"], "Repeto.stream – Я учу испанский")
            self.assertEqual(catalog["seasons"], {"1": "Практика", "2": "Волшебное радио"})
            self.assertIn("«Волшебное радио» (La radio mágica)", catalog["description"])
            practice, chapter = catalog["episodes"]
            self.assertIn("Тема 1 из 1", practice["description"])
            self.assertIn("Привет! → ¡Hola!", practice["description"])
            self.assertIn("Начинается приключение.", chapter["description"])
            self.assertIn("подсказка по-русски, пауза, ответ по-испански", chapter["description"])
            without_summary = descriptions.story_description(
                "es", story["titles"], {"chapter_number": 1}, 8, source="ru",
            )
            self.assertTrue(without_summary.startswith(
                "История «Волшебное радио» (La radio mágica). Глава 1 из 8.\n\n"
            ))

    def test_english_audience_copy_and_swedish_alias(self):
        self.assertEqual(descriptions.show_title("sv", source="en"), "Repeto.stream – I learn Swedish")
        self.assertEqual(descriptions.show_title("se", source="en"), "Repeto.stream – I learn Swedish")
        text = descriptions.show_description("sv", 30, [], "a@b.se", source="en")
        self.assertIn("English prompts", text)
        self.assertIn("Phrases: 30 short topics", text)
        self.assertIn("answer twice", text)
        self.assertIn("AI-generated", text)
        self.assertIn("corrections and story ideas are welcome: a@b.se", text)
        items = [{"en": "Hello!", "se": "Hej!"}]
        text = descriptions.practice_description(
            "se", 1, 30, {"en": "Greetings", "se": "Hälsningar"}, items, source="en",
        )
        self.assertIn("Topic 1 of 30: Greetings (Hälsningar) – 1 phrase.", text)
        self.assertIn("Hello! → Hej!", text)
        self.assertIn("Each Swedish phrase is played twice", text)

    def test_refresh_english_source_includes_story_summary_and_seasons(self):
        story = {
            "story_id": "test_story",
            "titles": {"en": "The Magical Radio", "sv": "Den magiska radion"},
            "chapters": [
                {"chapter_number": 1, "summary": {"en": "An adventure begins."}},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            course = Path(directory)
            (course / "course.json").write_text(json.dumps({
                "title": "Old", "description": "Old", "email": "a@b.se",
                "source_language": "en", "target_language": "sv",
                "episodes": [
                    {"id": "repeto:english-swedish:topic-01", "description": "old", "season": 1},
                    {"id": "test_story:en:sv:chapter-01", "description": "old", "season": 2},
                ],
            }), encoding="utf-8")
            catalog = descriptions.refresh_course(
                course, {"test_story": story},
                ({"Greetings": [{"en": "Hello!", "se": "Hej!"}]},
                 {"Greetings": {"en": "Greetings", "se": "Hälsningar"}}),
                source="en",
            )
            self.assertEqual(catalog["title"], "Repeto.stream – I learn Swedish")
            self.assertEqual(catalog["seasons"], {"1": "Practice", "2": "The Magical Radio"})
            self.assertIn('"The Magical Radio" (Den magiska radion)', catalog["description"])
            practice, chapter = catalog["episodes"]
            self.assertIn("Hello! → Hej!", practice["description"])
            self.assertIn("Chapter 1 of 1", chapter["description"])
            self.assertIn("An adventure begins.", chapter["description"])
            self.assertIn("an English prompt, a pause, then the answer in Swedish", chapter["description"])
            without_summary = descriptions.story_description(
                "sv", story["titles"], {"chapter_number": 1}, 8, source="en",
            )
            self.assertTrue(without_summary.startswith(
                'Chapter 1 of 8 in "The Magical Radio" (Den magiska radion).\n\n'
            ))

    def test_spanish_audience_copy_and_new_target_languages(self):
        self.assertEqual(descriptions.show_title("en", source="es"), "Repeto.stream – Aprendo inglés")
        text = descriptions.show_description("en", 30, [], "a@b.se", source="es")
        self.assertIn("indicaciones en español", text)
        self.assertIn("Frases: 30 temas cortos", text)
        self.assertIn("sugerencias de nuevos idiomas", text)
        self.assertIn("a@b.se", text)
        text = descriptions.practice_description(
            "en", 1, 30, {"es": "Saludos", "en": "Greetings"},
            [{"es": "¡Hola!", "en": "Hi!"}], source="es",
        )
        self.assertIn("Tema 1 de 30: Saludos (Greetings) – 1 frase.", text)
        self.assertIn("¡Hola! → Hi!", text)
        story = {"es": "La radio mágica", "en": "The Magical Radio"}
        chapter = descriptions.story_description(
            "en", story, {"chapter_number": 2, "summary": {"es": "Algo pasa."}}, 8, source="es",
        )
        self.assertTrue(chapter.startswith(
            "Capítulo 2 de 8 del cuento «La radio mágica» (The Magical Radio). Algo pasa."
        ))
        self.assertEqual(
            descriptions.story_name(story, "en", "es"), "«La radio mágica» (The Magical Radio)"
        )
        for target, english, swedish, polish, russian in (
            ("de", "German", "tyska", "niemieckiego", "немецкий"),
            ("fr", "French", "franska", "francuskiego", "французский"),
        ):
            self.assertEqual(descriptions.show_title(target, "en"), f"Repeto.stream – I learn {english}")
            self.assertEqual(descriptions.show_title(target, "sv"), f"Repeto.stream – Jag lär mig {swedish}")
            self.assertEqual(descriptions.show_title(target, "pl"), f"Repeto.stream – Uczę się {polish}")
            self.assertEqual(descriptions.show_title(target, "ru"), f"Repeto.stream – Я учу {russian}")

    def test_refresh_spanish_source_names_seasons(self):
        with tempfile.TemporaryDirectory() as directory:
            course = Path(directory)
            (course / "course.json").write_text(json.dumps({
                "title": "Old", "description": "Old", "email": "a@b.se",
                "source_language": "es", "target_language": "en",
                "episodes": [
                    {"id": "repeto:spanish-english:topic-01", "description": "old", "season": 1},
                    {"id": "test_story:es:en:chapter-01", "description": "old", "season": 2},
                ],
            }), encoding="utf-8")
            catalog = descriptions.refresh_course(
                course,
                {"test_story": {
                    "story_id": "test_story",
                    "titles": {"es": "La radio mágica", "en": "The Magical Radio"},
                    "chapters": [{"chapter_number": 1}],
                }},
                ({"Greetings": [{"es": "¡Hola!", "en": "Hi!"}]},
                 {"Greetings": {"es": "Saludos", "en": "Greetings"}}),
            )
            self.assertEqual(catalog["title"], "Repeto.stream – Aprendo inglés")
            self.assertEqual(catalog["seasons"], {"1": "Práctica", "2": "La radio mágica"})

    def test_swedish_and_spain_spanish_targets_for_polish_listeners(self):
        for target, genitive, adverb in (
            ("sv", "szwedzkiego", "szwedzku"),
            ("es", "hiszpańskiego", "hiszpańsku"),
        ):
            with self.subTest(target=target):
                self.assertEqual(
                    descriptions.show_title(target, source="pl"),
                    f"Repeto.stream – Uczę się {genitive}",
                )
                text = descriptions.show_description(target, 30, [], "a@b.se", source="pl")
                self.assertIn(f"po {adverb}", text)
                self.assertIn("po polsku", text)
        self.assertEqual(
            descriptions.show_title("se", source="pl"),
            descriptions.show_title("sv", source="pl"),
        )

    def test_show_copy_explains_audience_and_usage(self):
        self.assertEqual(descriptions.show_title("pl"), "Repeto.stream – Jag lär mig polska")
        self.assertEqual(descriptions.show_title("en"), "Repeto.stream – Jag lär mig engelska")
        self.assertEqual(descriptions.show_title("ru"), "Repeto.stream – Jag lär mig ryska")
        self.assertEqual(descriptions.show_title("ru", source="pl"), "Repeto.stream – Uczę się rosyjskiego")
        text = descriptions.show_description(
            "pl", 30, [descriptions.story_name({"sv": "Den magiska radion", "pl": "Magiczne Radio"}, "pl")],
            "a@b.se",
        )
        self.assertIn("nybörjare i alla åldrar", text)
        self.assertIn("Fraser: 30 korta ämnen", text)
        self.assertIn("Berättelsen ”Den magiska radion” (Magiczne Radio)", text)
        self.assertIn("Repeto.stream finns även på andra språk", text)
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
            "Repeto.stream – Uczę się angielskiego",
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
        self.assertIn("Frazy: 30 krótkich tematów", text)
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
            descriptions.show_title("it")

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

            self.assertEqual(catalog["title"], "Repeto.stream – Jag lär mig polska")
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

            self.assertEqual(catalog["title"], "Repeto.stream – Uczę się angielskiego")
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
