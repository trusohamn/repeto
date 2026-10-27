"""Build podcast RSS feeds from course catalogs using only the standard library."""

import argparse
import html
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM = "http://www.w3.org/2005/Atom"
ET.register_namespace("itunes", ITUNES)
ET.register_namespace("atom", ATOM)


def build_feed(course: Path, base_url: str) -> None:
    config = json.loads((course / "course.json").read_text(encoding="utf-8"))
    url = f"{base_url.rstrip('/')}/{quote(course.name)}"
    if not base_url.startswith("https://"):
        raise ValueError("Podcast hosting requires an HTTPS base URL.")
    if not (course / "cover.jpeg").is_file():
        raise ValueError(f"Missing cover: {course}")
    episodes = config["episodes"]
    if not episodes:
        raise ValueError(f"No episodes: {course}")
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    def field(parent: ET.Element, name: str, text: str) -> ET.Element:
        element = ET.SubElement(parent, name)
        element.text = text
        return element

    field(channel, "title", config["title"])
    field(channel, "link", url + "/")
    field(channel, "description", config["description"])
    field(channel, "language", config["language"])
    field(channel, f"{{{ITUNES}}}author", config["author"])
    field(channel, f"{{{ITUNES}}}explicit", "false")
    field(channel, f"{{{ITUNES}}}type", "serial")
    owner = ET.SubElement(channel, f"{{{ITUNES}}}owner")
    field(owner, f"{{{ITUNES}}}name", config["author"])
    field(owner, f"{{{ITUNES}}}email", config["email"])
    ET.SubElement(channel, f"{{{ITUNES}}}image", href=url + "/cover.jpeg")
    category = ET.SubElement(channel, f"{{{ITUNES}}}category", text="Education")
    ET.SubElement(category, f"{{{ITUNES}}}category", text="Language Learning")
    ET.SubElement(
        channel, f"{{{ATOM}}}link", href=url + "/feed.xml",
        rel="self", type="application/rss+xml",
    )
    seen = set()
    seen_numbers = set()
    for episode in episodes:
        season = episode["season"]
        number = episode["episode"]
        if (
            type(season) is not int or season < 1
            or type(number) is not int or number < 1
        ):
            raise ValueError("Season and episode numbers must be positive integers.")
        if (season, number) in seen_numbers:
            raise ValueError(f"Duplicate season/episode: {season}/{number}")
        seen_numbers.add((season, number))
        filename = episode["file"]
        if Path(filename).name != filename or not filename.endswith(".mp3"):
            raise ValueError(f"Invalid audio filename: {filename!r}")
        audio = course / "audio" / filename
        if not audio.is_file() or audio.stat().st_size == 0:
            raise ValueError(f"Missing or empty audio: {audio}")
        if episode["id"] in seen:
            raise ValueError(f"Duplicate episode ID: {episode['id']}")
        seen.add(episode["id"])
        item = ET.SubElement(channel, "item")
        title = f"{number:02d} {episode['title']}"
        field(item, "title", title)
        field(item, "description", episode["description"])
        guid = field(item, "guid", episode["id"])
        guid.set("isPermaLink", "false")
        field(item, "pubDate", format_datetime(datetime.fromisoformat(episode["published"])))
        field(item, f"{{{ITUNES}}}episode", str(number))
        field(item, f"{{{ITUNES}}}season", str(season))
        field(item, f"{{{ITUNES}}}episodeType", "full")
        field(item, f"{{{ITUNES}}}duration", str(round(episode["duration_ms"] / 1000)))
        field(item, f"{{{ITUNES}}}explicit", "false")
        ET.SubElement(
            item, "enclosure", url=url + "/audio/" + quote(filename),
            length=str(audio.stat().st_size), type="audio/mpeg",
        )
    ET.indent(rss)
    ET.ElementTree(rss).write(course / "feed.xml", encoding="utf-8", xml_declaration=True)
    title = html.escape(config["title"])
    (course / "index.html").write_text(
        f'<!doctype html><html lang="sv"><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width">'
        f"<title>{title}</title><h1>{title}</h1>"
        f'<img src="cover.jpeg" alt="Podcast cover" width="300">'
        f'<p>{html.escape(config["description"])}</p>'
        f'<p><a href="feed.xml">Podcast RSS feed</a></p></html>\n',
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("podcast"))
    parser.add_argument("--base-url", default="https://trusohamn.github.io/repeto")
    args = parser.parse_args()
    courses = sorted(path.parent for path in args.root.glob("*/course.json"))
    if not courses:
        raise ValueError("No course catalogs found.")
    for course in courses:
        build_feed(course, args.base_url)
    links = "".join(
        f'<li><a href="{quote(course.name)}/">{html.escape(course.name)}</a></li>'
        for course in courses
    )
    (args.root / "index.html").write_text(
        f'<!doctype html><html lang="en"><meta charset="utf-8">'
        f"<title>Repeto</title><h1>Repeto language courses</h1><ul>{links}</ul></html>\n",
        encoding="utf-8",
    )
    (args.root / ".nojekyll").touch()


if __name__ == "__main__":
    main()
