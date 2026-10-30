"""Listener-facing podcast copy (show and episode descriptions).

Packagers call the episode helpers; run this module to refresh the titles and
descriptions of already packaged courses without re-rendering any audio:

    .venv/bin/python code/descriptions.py podcast/swedish-polish
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PRACTICE_TRANSCRIPT = ROOT / "courses" / "practice" / "transcript.json"
PRACTICE_TOPICS = ROOT / "courses" / "practice" / "topics.json"
STORIES = ROOT / "courses" / "stories"
LANGUAGES = {
    "pl": ("polska", "polsk"),
    "en": ("engelska", "engelsk"),
    "ru": ("ryska", "rysk"),
    "sv": ("svenska", "svensk"),
    "es": ("spanska", "spansk"),
}
EXAMPLES = 3
PRACTICE_ID = re.compile(r"repeto:[a-z0-9-]+:topic-(\d+)")
STORY_ID = re.compile(r"([a-z0-9_-]+):(sv|pl|en|ru):([a-z]{2}):chapter-(\d+)")


def _names(target: str) -> tuple[str, str]:
    target = "sv" if target == "se" else target
    if target not in LANGUAGES:
        raise ValueError(f"No Swedish language name configured for {target!r}.")
    return LANGUAGES[target]


def _polish_language(target: str) -> tuple[str, str]:
    target = "sv" if target == "se" else target
    languages = {
        "pl": ("polskiego", "polski"),
        "en": ("angielskiego", "angielski"),
        "ru": ("rosyjskiego", "rosyjski"),
        "sv": ("szwedzkiego", "szwedzki"),
        "es": ("hiszpańskiego", "hiszpański"),
    }
    if target not in languages:
        raise ValueError(f"No Polish language name configured for {target!r}.")
    return languages[target]


def _polish_adverb(target: str) -> str:
    target = "sv" if target == "se" else target
    adverbs = {
        "pl": "polsku", "en": "angielsku", "ru": "rosyjsku",
        "sv": "szwedzku", "es": "hiszpańsku",
    }
    if target not in adverbs:
        raise ValueError(f"No Polish language name configured for {target!r}.")
    return adverbs[target]


def _polish_count(number: int, singular: str, few: str, many: str) -> str:
    last_two = number % 100
    if number == 1:
        word = singular
    elif 2 <= number % 10 <= 4 and not 12 <= last_two <= 14:
        word = few
    else:
        word = many
    return f"{number} {word}"


def _russian_count(number: int, singular: str, few: str, many: str) -> str:
    if number % 10 == 1 and number % 100 != 11:
        word = singular
    elif 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        word = few
    else:
        word = many
    return f"{number} {word}"


def _english_language(target: str) -> str:
    target = "sv" if target == "se" else target
    languages = {
        "pl": "Polish", "en": "English", "ru": "Russian",
        "sv": "Swedish", "es": "Spanish",
    }
    if target not in languages:
        raise ValueError(f"No English language name configured for {target!r}.")
    return languages[target]


def _russian_language(target: str) -> tuple[str, str]:
    target = "sv" if target == "se" else target
    languages = {
        "pl": ("польский", "по-польски"),
        "en": ("английский", "по-английски"),
        "ru": ("русский", "по-русски"),
        "sv": ("шведский", "по-шведски"),
        "es": ("испанский", "по-испански"),
    }
    if target not in languages:
        raise ValueError(f"No Russian language name configured for {target!r}.")
    return languages[target]


def show_title(target: str, source: str = "sv") -> str:
    if source == "sv":
        return f"Repeto – Lär dig {_names(target)[0]}"
    if source == "pl":
        genitive, _ = _polish_language(target)
        return f"Repeto – Ucz się {genitive}"
    if source == "en":
        return f"Repeto – Learn {_english_language(target)}"
    if source == "ru":
        return f"Repeto – Учи {_russian_language(target)[0]}"
    raise ValueError(f"Unsupported source language {source!r}.")


def story_name(titles: dict[str, str], target: str, source: str = "sv") -> str:
    """Story title in the source language with the target title in parentheses."""
    if source not in ("sv", "pl", "en", "ru"):
        raise ValueError(f"Unsupported source language {source!r}.")
    if source == "ru":
        return f"«{titles[source]}» ({titles[target]})"
    if source == "en":
        return f'"{titles[source]}" ({titles[target]})'
    return f"„{titles[source]}” ({titles[target]})" if source == "pl" else (
        f"”{titles[source]}” ({titles[target]})"
    )


def show_description(
    target: str, practice_topics: int, story_titles: list[str], email: str,
    source: str = "sv",
) -> str:
    if source == "ru":
        language, adverb = _russian_language(target)
        parts = [
            f"Учи {language}: слушай и говори с подсказками на русском. "
            "Repeto — аудиокурс для начинающих любого возраста: детей, родителей, "
            f"бабушек, дедушек и всех, кто хочет начать учить {language}. "
            "Предварительные знания и учебник не нужны.",
            "Как это работает: ты слышишь слово или предложение по-русски, "
            f"а затем во время паузы пробуешь сказать то же самое {adverb}. "
            "После этого ответ звучит дважды, с паузами для повторения.",
        ]
        contents = []
        if practice_topics:
            contents.append(
                "• Сезон 1 — Практика: "
                f"{_russian_count(practice_topics, 'короткая тема', 'короткие темы', 'коротких тем')} "
                "— от приветствий и чисел до еды, чувств и повседневных ситуаций."
            )
        for title in story_titles:
            contents.append(
                f"• Сезон 2 — История {title}: по одной главе в каждом выпуске. "
                f"Сначала слушай главу {adverb}, затем тренируй слова "
                "и слушай главу ещё раз."
            )
        contents.append(
            "• Новые истории уже в работе. Подпишись на подкаст, чтобы не пропустить выпуски."
        )
        parts.append("Что входит в курс:\n" + "\n".join(contents))
        parts.append("Как заниматься:\n" + "\n".join([
            "• Начни с первого выпуска первого сезона и слушай по порядку.",
            "• Отвечай вслух во время пауз — попробуй вспомнить слова самостоятельно.",
            "• Слушай выпуск снова, пока не начнёшь отвечать раньше диктора.",
            "• Фоновое прослушивание помогает привыкнуть к звукам и ритму языка. "
            "Занимайся и активно: повторяй и отвечай во время пауз.",
        ]))
        parts.append(
            "Нравится такой формат? У Repeto есть курсы и для других языков "
            "с такой же структурой. Ищи Repeto в своём приложении для подкастов."
        )
        parts.append(
            "Напиши нам! Предложения новых языков, исправления и идеи для историй "
            f"приветствуются: {email}"
        )
        parts.append("Голоса созданы с помощью ИИ (Microsoft Azure).")
        return "\n\n".join(parts)
    if source == "en":
        language = _english_language(target)
        parts = [
            f"Learn {language} by listening and speaking, with English prompts to guide you. "
            "Repeto is an audio course for beginners of all ages: children, parents, "
            f"grandparents and anyone who wants to start learning {language}. "
            "No previous knowledge or textbook is needed.",
            "How it works: you hear a word or sentence in English, then have a pause "
            f"to say it in {language}. Next, you hear the answer twice, with time "
            "to repeat it and practise the pronunciation.",
        ]
        contents = []
        if practice_topics:
            contents.append(
                f"• Season 1 – Practice: {practice_topics} short "
                f"{'topic' if practice_topics == 1 else 'topics'}, from greetings and "
                "numbers to food, feelings and everyday situations."
            )
        for title in story_titles:
            contents.append(
                f"• Season 2 – Story: {title}, one chapter per episode. "
                f"Listen to the chapter in {language}, practise its vocabulary, "
                "then listen to the chapter again."
            )
        contents.append(
            "• More stories are on the way. Follow the podcast to hear new episodes."
        )
        parts.append("What's included:\n" + "\n".join(contents))
        parts.append("How to use the course:\n" + "\n".join([
            "• Start with season 1, episode 1 and listen in order.",
            "• Answer out loud during each pause. Try to recall the words yourself.",
            "• Replay an episode until you can answer before the recorded voice.",
            "• Listening in the background can help you get used to the sounds and "
            "rhythm of the language. Practise actively too, by repeating and answering "
            "during the pauses.",
        ]))
        parts.append(
            "Enjoy this format? Repeto is also available in other languages, with "
            "the same familiar structure. Search for Repeto in your podcast app."
        )
        parts.append(
            "Get in touch! Suggestions for new languages, corrections and story ideas "
            f"are welcome: {email}"
        )
        parts.append("Voices are AI-generated (Microsoft Azure).")
        return "\n\n".join(parts)
    if source == "pl":
        language, _ = _polish_language(target)
        adverb = _polish_adverb(target)
        parts = [
            f"Ucz się {language}, słuchając i mówiąc – z polskim jako wsparciem. "
            "Repeto to kurs audio dla początkujących w każdym wieku: dzieci, rodziców, "
            f"dziadków i wszystkich, którzy chcą zacząć naukę {language}. "
            "Nie potrzebujesz wcześniejszej wiedzy ani podręcznika.",
            f"Jak to działa: słyszysz słowo lub zdanie po polsku, a potem masz chwilę, "
            f"by powiedzieć je po {adverb}. Następnie usłyszysz odpowiedź dwa razy "
            "i będziesz mieć czas, by powtórzyć wymowę.",
        ]
        contents = []
        if practice_topics:
            contents.append(
                f"• Sezon 1 – Ćwiczenia: "
                f"{_polish_count(practice_topics, 'krótki temat', 'krótkie tematy', 'krótkich tematów')}, "
                "od powitań i liczb po jedzenie, emocje i codzienne sytuacje."
            )
        for title in story_titles:
            contents.append(
                f"• Sezon 2 – Opowieść {title}: jeden rozdział w każdym odcinku. "
                f"Najpierw słuchasz rozdziału po {adverb}, ćwiczysz słownictwo, "
                "a potem słuchasz go ponownie."
            )
        contents.append(
            "• Kolejne opowieści są w przygotowaniu – nowe odcinki będą dodawane "
            "regularnie. Obserwuj podcast, żeby ich nie przegapić."
        )
        parts.append("W kursie znajdziesz:\n" + "\n".join(contents))
        parts.append("Jak korzystać z kursu:\n" + "\n".join([
            "• Zacznij od sezonu 1, odcinka 1 i słuchaj po kolei.",
            "• Odpowiadaj na głos w przerwie – spróbuj samodzielnie przypomnieć sobie słowa.",
            "• Odtwórz odcinek ponownie, aż zdążysz odpowiedzieć przed głosem lektora.",
            "• Słuchanie w tle może pomóc oswoić się z brzmieniem i melodią języka. "
            "Ćwicz też aktywnie, powtarzając i odpowiadając w przerwach.",
        ]))
        parts.append(
            "Podoba Ci się ten format? Repeto jest dostępne także w innych językach – "
            "ten sam układ pozwoli Ci od razu poczuć się swobodnie. Wyszukaj „Repeto” "
            "w swojej aplikacji do podcastów."
        )
        parts.append(
            "Napisz do nas! Sugestie dotyczące nowych języków, poprawki i pomysły na "
            f"opowieści są mile widziane: {email}"
        )
        parts.append("Głosy zostały wygenerowane przez AI (Microsoft Azure).")
        return "\n\n".join(parts)
    if source != "sv":
        raise ValueError(f"Unsupported source language {source!r}.")
    language, _ = _names(target)
    parts = [
        f"Lär dig {language} genom att lyssna och prata – med svenska som stöd. "
        "Repeto är en lyssningskurs för nybörjare i alla åldrar: barn, föräldrar, "
        f"mor- och farföräldrar och alla som vill komma igång med {language}. "
        "Ingen förkunskap och ingen bok behövs.",
        f"Så fungerar det: du hör ett ord eller en mening på svenska och får en paus "
        f"att säga det på {language}. Sedan kommer svaret – två gånger, med pauser så att du hinner "
        "härma uttalet.",
    ]
    contents = []
    if practice_topics:
        contents.append(
            f"• Säsong 1 – Övningar: {practice_topics} "
            f"{'kort ämne' if practice_topics == 1 else 'korta ämnen'}, från hälsningar och "
            "siffror till mat, känslor och vardag."
        )
    for title in story_titles:
        contents.append(
            f"• Säsong 2 – Berättelsen {title}: ett kapitel per avsnitt. Du hör "
            f"kapitlet på {language}, övar orden och hör kapitlet igen."
        )
    contents.append(
        "• Fler berättelser är på väg – vi lägger till nya löpande. Följ podden så "
        "missar du inget."
    )
    parts.append("Det här ingår:\n" + "\n".join(contents))
    parts.append("Så använder du kursen:\n" + "\n".join([
        "• Börja med säsong 1, avsnitt 1, och lyssna i ordning.",
        "• Säg svaret högt i pausen – öva på att själv komma på orden.",
        "• Lyssna på avsnittet igen tills du hinner svara före rösten.",
        "• Bakgrundslyssning kan hjälpa dig att bli bekant med språkets ljud och "
        "melodi. Öva också aktivt genom att härma och svara i pauserna.",
    ]))
    parts.append(
        "Gillar du upplägget? Repeto finns även på andra språk – samma format, så du "
        "känner igen dig direkt. Sök på ”Repeto” där du lyssnar på poddar."
    )
    parts.append(
        "Hör gärna av dig! Önskemål om nya språk, rättelser och idéer till nya "
        f"berättelser är varmt välkomna: {email}"
    )
    parts.append("Rösterna är AI-genererade (Microsoft Azure).")
    return "\n\n".join(parts)


def practice_description(
    target: str, number: int, total: int, titles: dict[str, str],
    items: list[dict[str, str]], source: str = "se",
) -> str:
    if source == "ru":
        _, adverb = _russian_language(target)
        examples = "\n".join(
            f"• {item[source]} → {item[target]}" for item in items[:EXAMPLES]
        )
        phrase_count = _russian_count(len(items), "фраза", "фразы", "фраз")
        return (
            f"Тема {number} из {total}: {titles[source]} ({titles[target]}) — "
            f"{phrase_count}.\n\n"
            "Ты услышишь слово или предложение по-русски. "
            f"Скажи то же самое {adverb} во время паузы, прежде чем прозвучит ответ. "
            "Каждая фраза на изучаемом языке звучит дважды: слушай и повторяй.\n\n"
            f"Примеры из выпуска:\n{examples}\n\n"
            "Совет: слушай снова, пока не начнёшь отвечать раньше диктора."
        )
    if source == "en":
        language = _english_language(target)
        examples = "\n".join(
            f"• {item[source]} → {item[target]}" for item in items[:EXAMPLES]
        )
        phrase_count = f"{len(items)} {'phrase' if len(items) == 1 else 'phrases'}"
        return (
            f"Topic {number} of {total}: {titles[source]} ({titles[target]}) – "
            f"{phrase_count}.\n\n"
            "You hear a word or sentence in English. "
            f"Say it in {language} during the pause, before you hear the answer. "
            f"Each {language} phrase is played twice: listen and repeat.\n\n"
            f"Examples from this episode:\n{examples}\n\n"
            "Tip: listen again until you can answer before the recorded voice."
        )
    if source not in ("se", "sv", "pl"):
        raise ValueError(f"Unsupported source language {source!r}.")
    language, adjective = _names(target)
    if source == "pl":
        language, adjective = _polish_language(target)
        adverb = _polish_adverb(target)
        phrase_count = _polish_count(len(items), "zwrot", "zwroty", "zwrotów")
        examples = "\n".join(
            f"• {item[source]} → {item[target]}" for item in items[:EXAMPLES]
        )
        return (
            f"Temat {number} z {total}: {titles[source]} ({titles[target]}) – "
            f"{phrase_count}.\n\n"
            f"Usłyszysz słowo lub zdanie po polsku. Powiedz je po {adverb} w przerwie, "
            f"zanim usłyszysz odpowiedź. Każdy {adjective} zwrot usłyszysz dwa razy: "
            "słuchaj i powtarzaj.\n\n"
            f"Przykłady z odcinka:\n{examples}\n\n"
            "Wskazówka: słuchaj ponownie, aż zdążysz odpowiedzieć przed głosem lektora."
        )
    examples = "\n".join(f"• {item[source]} → {item[target]}" for item in items[:EXAMPLES])
    return (
        f"Ämne {number} av {total}: {titles[source]} ({titles[target]}) – "
        f"{len(items)} fraser.\n\n"
        f"Du hör ett ord eller en mening på svenska. Säg det på {language} i pausen "
        f"innan svaret kommer. Varje {adjective} fras spelas två gånger: lyssna och härma.\n\n"
        f"Exempel ur avsnittet:\n{examples}\n\n"
        "Tips: lyssna igen tills du hinner svara före rösten."
    )


def story_description(
    target: str, story_titles: dict[str, str], chapter: dict[str, Any], total: int,
    source: str = "sv",
) -> str:
    if source == "ru":
        _, adverb = _russian_language(target)
        summary = chapter.get("summary", {}).get(source)
        opening = (
            f"История «{story_titles[source]}» ({story_titles[target]}). "
            f"Глава {chapter['chapter_number']} из {total}."
        )
        if summary:
            opening += f" {summary}"
        return (
            f"{opening}\n\n"
            "Как устроен выпуск:\n"
            f"1. Послушай всю главу {adverb} — не обязательно понимать всё.\n"
            "2. Потренируй слова и выражения из главы: подсказка по-русски, "
            f"пауза, ответ {adverb}.\n"
            "3. Послушай главу ещё раз и проверь, сколько удалось понять.\n\n"
            "Между частями звучит сигнал. Слушай по порядку, начиная с первой главы."
        )
    if source == "en":
        language = _english_language(target)
        summary = chapter.get("summary", {}).get(source)
        opening = (
            f"Chapter {chapter['chapter_number']} of {total} in "
            f'"{story_titles[source]}" ({story_titles[target]}).'
        )
        if summary:
            opening += f" {summary}"
        return (
            f"{opening}\n\n"
            "How the episode works:\n"
            f"1. Listen to the whole chapter in {language}. You don't need to understand everything.\n"
            "2. Practise words and expressions from the chapter: an English prompt, "
            f"a pause, then the answer in {language}.\n"
            "3. Listen to the chapter again and see how much you can understand.\n\n"
            "A chime separates the sections. Listen in order, starting with chapter 1."
        )
    if source == "pl":
        language, _ = _polish_language(target)
        adverb = _polish_adverb(target)
        summary = chapter.get("summary", {}).get(source)
        opening = (
            f"Rozdział {chapter['chapter_number']} z {total} opowieści "
            f"„{story_titles[source]}” ({story_titles[target]})."
        )
        if summary:
            opening += f" {summary}"
        return (
            f"{opening}\n\n"
            "Jak wygląda odcinek:\n"
            f"1. Posłuchaj całego rozdziału po {adverb} – nie musisz rozumieć wszystkiego.\n"
            f"2. Poćwicz słowa i wyrażenia z rozdziału: podpowiedź po polsku, przerwa, "
            f"odpowiedź po {adverb}.\n"
            "3. Posłuchaj rozdziału ponownie i sprawdź, ile udało Ci się zrozumieć.\n\n"
            "Między częściami usłyszysz sygnał dźwiękowy. Słuchaj po kolei, zaczynając "
            "od rozdziału 1."
        )
    if source != "sv":
        raise ValueError(f"Unsupported source language {source!r}.")
    language, _ = _names(target)
    summary = chapter.get("summary", {}).get(source)
    opening = (
        f"Kapitel {chapter['chapter_number']} av {total} i berättelsen "
        f"”{story_titles['sv']}” ({story_titles[target]})."
    )
    if summary:
        opening += f" {summary}"
    return (
        f"{opening}\n\n"
        "Så går avsnittet till:\n"
        f"1. Lyssna på hela kapitlet på {language} – du behöver inte förstå allt.\n"
        f"2. Öva orden och uttrycken ur kapitlet: svensk ledtråd, paus, svar på {language}.\n"
        "3. Lyssna på kapitlet igen – nu förstår du mycket mer.\n\n"
        "En ljudsignal hörs mellan delarna. Lyssna i ordning från kapitel 1."
    )


def _load_practice() -> tuple[dict[str, list[dict[str, str]]], dict[str, dict[str, str]]]:
    topics: dict[str, list[dict[str, str]]] = {}
    for entry in json.loads(PRACTICE_TRANSCRIPT.read_text(encoding="utf-8")):
        topics.setdefault(entry["topic"], []).append(entry)
    titles = json.loads(PRACTICE_TOPICS.read_text(encoding="utf-8"))
    return topics, titles


def refresh_course(
    course: Path,
    stories: dict[str, dict[str, Any]] | None = None,
    practice: tuple[dict[str, list[dict[str, str]]], dict[str, dict[str, str]]] | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Rewrite show and episode copy in course.json from the course sources.

    ``stories`` maps story IDs to already loaded transcripts and ``practice`` is a
    ``(topic entries, topic titles)`` pair; anything not given is read from
    ``courses/``.
    """
    path = course / "course.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    course_source = catalog.get("source_language", "sv")
    if source is not None and source != course_source:
        raise ValueError(
            f"{course.name}: requested source {source!r} does not match "
            f"course source {course_source!r}."
        )
    source = course_source
    if source not in ("sv", "pl", "en", "ru"):
        raise ValueError(f"{course.name}: unsupported source language {source!r}.")
    target = catalog["target_language"]
    practice_target = "se" if target == "sv" else target
    practice_source = "se" if source == "sv" else source
    topics: dict[str, list[dict[str, str]]] = {}
    topic_titles: dict[str, dict[str, str]] = {}
    if practice is not None:
        topics, topic_titles = practice
    elif any(PRACTICE_ID.fullmatch(episode["id"]) for episode in catalog["episodes"]):
        topics, topic_titles = _load_practice()
    topic_names = list(topics)
    stories = dict(stories or {})
    practice_count = 0
    story_names: list[str] = []
    for episode in catalog["episodes"]:
        if match := PRACTICE_ID.fullmatch(episode["id"]):
            number = int(match[1])
            topic = topic_names[number - 1]
            episode["description"] = practice_description(
                practice_target, number, len(topic_names), topic_titles[topic], topics[topic],
                source=practice_source,
            )
            practice_count += 1
        elif match := STORY_ID.fullmatch(episode["id"]):
            story_id, story_source, story_target, number = (
                match[1], match[2], match[3], int(match[4])
            )
            if story_source != source:
                raise ValueError(f"{episode['id']} does not match source {source!r}.")
            if story_target != target:
                raise ValueError(f"{episode['id']} does not match target {target!r}.")
            if story_id not in stories:
                transcript = STORIES / story_id / "generated" / "transcript.json"
                stories[story_id] = json.loads(transcript.read_text(encoding="utf-8"))
            story = stories[story_id]
            if story_name(story["titles"], target, source) not in story_names:
                story_names.append(story_name(story["titles"], target, source))
            episode["description"] = story_description(
                target, story["titles"], story["chapters"][number - 1],
                len(story["chapters"]), source,
            )
    season_names = {}
    for episode in catalog["episodes"]:
        if PRACTICE_ID.fullmatch(episode["id"]):
            season_names[str(episode["season"])] = (
                {"sv": "Övningar", "pl": "Ćwiczenia", "en": "Practice", "ru": "Практика"}[source]
            )
        elif match := STORY_ID.fullmatch(episode["id"]):
            season_names[str(episode["season"])] = (
                stories[match[1]]["titles"][source]
            )
    catalog["seasons"] = season_names
    catalog["title"] = show_title(target, source)
    catalog["description"] = show_description(
        target, practice_count, story_names, catalog["email"], source,
    )
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("courses", nargs="+", type=Path, help="podcast/<course> folders")
    parser.add_argument("--podcast-root", type=Path, default=ROOT / "podcast")
    parser.add_argument("--podcast-base-url", default="https://trusohamn.github.io/repeto")
    args = parser.parse_args()
    for course in args.courses:
        refresh_course(course)
        print(f"Refreshed: {course}")
    subprocess.run(
        [sys.executable, str(ROOT / "code" / "podcast.py"),
         "--root", str(args.podcast_root), "--base-url", args.podcast_base_url],
        cwd=ROOT, check=True,
    )


if __name__ == "__main__":
    main()
