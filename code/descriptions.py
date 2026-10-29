"""Listener-facing podcast copy (show and episode descriptions) for Swedish-source courses.

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
}
EXAMPLES = 3
PRACTICE_ID = re.compile(r"repeto:[a-z0-9-]+:topic-(\d+)")
STORY_ID = re.compile(r"([a-z0-9_-]+):sv:([a-z]{2}):chapter-(\d+)")


def _names(target: str) -> tuple[str, str]:
    if target not in LANGUAGES:
        raise ValueError(f"No Swedish language name configured for {target!r}.")
    return LANGUAGES[target]


def show_title(target: str) -> str:
    return f"Repeto – {_names(target)[0].capitalize()} för svensktalande"


def story_name(titles: dict[str, str], target: str) -> str:
    """Swedish story title with the target-language title in parentheses."""
    return f"”{titles['sv']}” ({titles[target]})"


def show_description(
    target: str, practice_topics: int, story_titles: list[str], email: str,
) -> str:
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
        "• Säg svaret högt i pausen – det är där du lär dig.",
        "• Lyssna på avsnittet igen tills du hinner svara före rösten.",
        "• Även att lyssna i bakgrunden hjälper – du vänjer dig vid ljuden och "
        "språkets melodi.",
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
    language, adjective = _names(target)
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
) -> str:
    language, _ = _names(target)
    summary = chapter.get("summary", {}).get("sv")
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
) -> dict[str, Any]:
    """Rewrite show and episode copy in course.json from the course sources.

    ``stories`` maps story IDs to already loaded transcripts and ``practice`` is a
    ``(topic entries, topic titles)`` pair; anything not given is read from
    ``courses/``.
    """
    path = course / "course.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("source_language", "sv") != "sv":
        raise ValueError(f"{course.name}: only Swedish-source courses are supported.")
    target = catalog["target_language"]
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
                target, number, len(topic_names), topic_titles[topic], topics[topic],
            )
            practice_count += 1
        elif match := STORY_ID.fullmatch(episode["id"]):
            story_id, story_target, number = match[1], match[2], int(match[3])
            if story_target != target:
                raise ValueError(f"{episode['id']} does not match target {target!r}.")
            if story_id not in stories:
                transcript = STORIES / story_id / "generated" / "transcript.json"
                stories[story_id] = json.loads(transcript.read_text(encoding="utf-8"))
            story = stories[story_id]
            if story_name(story["titles"], target) not in story_names:
                story_names.append(story_name(story["titles"], target))
            episode["description"] = story_description(
                target, story["titles"], story["chapters"][number - 1], len(story["chapters"]),
            )
    season_names = {}
    for episode in catalog["episodes"]:
        if PRACTICE_ID.fullmatch(episode["id"]):
            season_names[str(episode["season"])] = "Övningar"
        elif match := STORY_ID.fullmatch(episode["id"]):
            season_names[str(episode["season"])] = stories[match[1]]["titles"]["sv"]
    catalog["seasons"] = season_names
    catalog["title"] = show_title(target)
    catalog["description"] = show_description(
        target, practice_count, story_names, catalog["email"],
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
