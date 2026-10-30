"""Build podcast RSS feeds from course catalogs using only the standard library."""

import argparse
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import quote

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM = "http://www.w3.org/2005/Atom"
CONTENT = "http://purl.org/rss/1.0/modules/content/"
ET.register_namespace("itunes", ITUNES)
ET.register_namespace("atom", ATOM)
ET.register_namespace("content", CONTENT)
FINGERPRINT = re.compile(r"-[0-9a-f]{8}")
LIST_ITEM = re.compile(r"(?:•|\d+\.)\s+")
STYLE = (
    "body{font-family:system-ui,sans-serif;max-width:42rem;margin:auto;padding:1rem;"
    "line-height:1.5;color:#222}img{max-width:100%;height:auto;border-radius:.5rem}"
    "audio{width:100%}details{margin:.75rem 0;border-bottom:1px solid #ddd;"
    "padding-bottom:.75rem}summary{cursor:pointer;font-weight:600}"
    ".card{display:flex;gap:1rem;margin:1.5rem 0}.card img{width:8rem;flex:none}"
)


def text_to_html(text: str) -> str:
    """Render plain description text: blank lines split paragraphs, • or N. lines form lists."""
    blocks = []
    for paragraph in text.strip().split("\n\n"):
        lines = paragraph.splitlines()
        heading = [line for line in lines if not LIST_ITEM.match(line)]
        items = [LIST_ITEM.sub("", line, count=1) for line in lines if LIST_ITEM.match(line)]
        if heading and not items:
            blocks.append("<p>" + "<br>".join(html.escape(line) for line in lines) + "</p>")
            continue
        if heading:
            blocks.append("<p>" + "<br>".join(html.escape(line) for line in heading) + "</p>")
        tag = "ol" if LIST_ITEM.match(lines[-1]) and lines[-1][0].isdigit() else "ul"
        blocks.append(
            f"<{tag}>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + f"</{tag}>"
        )
    return "".join(blocks)


def _page(title: str, body: str, language: str = "sv") -> str:
    return (
        f'<!doctype html><html lang="{html.escape(language, quote=True)}"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{STYLE}</style>{body}</html>\n"
    )


def _fingerprinted_versions(path: Path) -> list[Path]:
    return sorted(
        candidate for candidate in path.parent.glob(f"{path.stem}-*{path.suffix}")
        if FINGERPRINT.fullmatch(candidate.stem[len(path.stem):])
    )


def find_image(path: Path) -> Path | None:
    """Return the file currently published for a logical image path such as cover.jpeg."""
    if path.is_file():
        return path
    versions = _fingerprinted_versions(path)
    if len(versions) > 1:
        raise ValueError(f"Several published versions of {path.name}: {versions}")
    return versions[0] if versions else None


def fingerprint_image(path: Path) -> Path:
    """Publish an image under a content-hashed name so podcast apps fetch new artwork.

    A plain file (for example a newly dropped-in cover.jpeg) replaces older
    fingerprinted versions; only the current version is kept on disk.
    """
    current = find_image(path)
    if current is None or current.stat().st_size == 0:
        raise ValueError(f"Missing or empty image: {path}")
    digest = hashlib.sha256(current.read_bytes()).hexdigest()[:8]
    published = path.with_name(f"{path.stem}-{digest}{path.suffix}")
    if current != published:
        current.replace(published)
    for stale in _fingerprinted_versions(path):
        if stale != published:
            stale.unlink()
    return published


def remove_superseded_audio(course: Path, old_files: list[str]) -> list[Path]:
    """Delete episode MP3s that a re-render replaced and the catalog no longer uses."""
    catalog = json.loads((course / "course.json").read_text(encoding="utf-8"))
    referenced = {episode["file"] for episode in catalog["episodes"]}
    audio_root = (course / "audio").resolve()
    removed = []
    for old_file in sorted(set(old_files) - referenced):
        path = (audio_root / Path(*PurePosixPath(old_file).parts)).resolve()
        if path.parent.is_relative_to(audio_root) and path.is_file():
            path.unlink()
            removed.append(path)
    return removed


def build_feed(course: Path, base_url: str) -> None:
    config = json.loads((course / "course.json").read_text(encoding="utf-8"))
    url = f"{base_url.rstrip('/')}/{quote(course.name)}"
    if not base_url.startswith("https://"):
        raise ValueError("Podcast hosting requires an HTTPS base URL.")
    if find_image(course / "cover.jpeg") is None:
        raise ValueError(f"Missing cover: {course}")
    episodes = config["episodes"]
    if not episodes:
        raise ValueError(f"No episodes: {course}")
    cover = fingerprint_image(course / "cover.jpeg")
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
    ET.SubElement(channel, f"{{{ITUNES}}}image", href=url + "/" + quote(cover.name))
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
        if not isinstance(filename, str):
            raise ValueError(f"Invalid audio filename: {filename!r}")
        relative_audio_path = PurePosixPath(filename)
        if (
            "\\" in filename
            or relative_audio_path.is_absolute()
            or str(relative_audio_path) != filename
            or any(part in {"", ".", ".."} for part in relative_audio_path.parts)
            or relative_audio_path.suffix != ".mp3"
        ):
            raise ValueError(f"Invalid audio filename: {filename!r}")
        audio = course / "audio" / Path(*relative_audio_path.parts)
        if not audio.is_file() or audio.stat().st_size == 0:
            raise ValueError(f"Missing or empty audio: {audio}")
        if episode["id"] in seen:
            raise ValueError(f"Duplicate episode ID: {episode['id']}")
        seen.add(episode["id"])
        item = ET.SubElement(channel, "item")
        title = f"{number:02d} {episode['title']}"
        field(item, "title", title)
        field(item, "description", episode["description"])
        field(item, f"{{{CONTENT}}}encoded", text_to_html(episode["description"]))
        guid = field(item, "guid", episode["id"])
        guid.set("isPermaLink", "false")
        field(item, "pubDate", format_datetime(datetime.fromisoformat(episode["published"])))
        field(item, f"{{{ITUNES}}}episode", str(number))
        field(item, f"{{{ITUNES}}}season", str(season))
        field(item, f"{{{ITUNES}}}episodeType", "full")
        field(item, f"{{{ITUNES}}}duration", str(round(episode["duration_ms"] / 1000)))
        field(item, f"{{{ITUNES}}}explicit", "false")
        if "image" in episode:
            image_name = episode["image"]
            if not isinstance(image_name, str) or not image_name:
                raise ValueError(f"Invalid episode image: {image_name!r}")
            relative_image_path = PurePosixPath(image_name)
            if (
                "\\" in image_name
                or ":" in image_name
                or relative_image_path.is_absolute()
                or str(relative_image_path) != image_name
                or any(part in {"", ".", ".."} for part in relative_image_path.parts)
                or relative_image_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}
            ):
                raise ValueError(f"Invalid episode image: {image_name!r}")
            logical_image = course / Path(*relative_image_path.parts)
            published_image = find_image(logical_image)
            if published_image is None or published_image.stat().st_size == 0:
                raise ValueError(f"Missing or empty episode image: {logical_image}")
            image = fingerprint_image(logical_image)
            published_parts = (*relative_image_path.parts[:-1], image.name)
            ET.SubElement(
                item, f"{{{ITUNES}}}image",
                href=url + "/" + "/".join(quote(part) for part in published_parts),
            )
        ET.SubElement(
            item, "enclosure",
            url=url + "/audio/" + "/".join(
                quote(part) for part in relative_audio_path.parts
            ),
            length=str(audio.stat().st_size), type="audio/mpeg",
        )
    ET.indent(rss)
    ET.ElementTree(rss).write(course / "feed.xml", encoding="utf-8", xml_declaration=True)
    cover_label, listen_label, season_label, rss_label = {
        "pl": ("Okładka", "Słuchaj", "Sezon", "Kanał RSS"),
        "en": ("Cover", "Listen", "Season", "RSS feed"),
    }.get(config["language"], ("Omslag", "Lyssna", "Säsong", "RSS-flöde"))
    links = [
        f'<a href="{html.escape(link_url)}">{html.escape(name)}</a>'
        for name, link_url in config.get("links", {}).items()
    ] + [f'<a href="feed.xml">{rss_label}</a>']
    seasons: dict[int, list[str]] = {}
    season_names: dict[str, str] = config.get("seasons", {})
    for episode in sorted(episodes, key=lambda e: (e["season"], e["episode"])):
        audio_url = "audio/" + "/".join(
            quote(part) for part in PurePosixPath(episode["file"]).parts
        )
        seasons.setdefault(episode["season"], []).append(
            f'<details><summary>{episode["episode"]:02d} '
            f'{html.escape(episode["title"])}</summary>'
            f'{text_to_html(episode["description"])}'
            f'<audio controls preload="none" src="{html.escape(audio_url)}"></audio></details>'
        )
    (course / "index.html").write_text(_page(config["title"], (
        f'<h1>{html.escape(config["title"])}</h1>'
        f'<img src="{html.escape(quote(cover.name))}" alt="{cover_label}" width="300">'
        f'{text_to_html(config["description"])}'
        f'<p><strong>{listen_label}:</strong> {" · ".join(links)}</p>'
        + "".join(
            f"<h2>{season_label} {season}"
            + (f" – {html.escape(name)}" if (name := season_names.get(str(season))) else "")
            + f"</h2>{''.join(items)}"
            for season, items in seasons.items()
        )
    ), language=config["language"]), encoding="utf-8")


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
    cards = []
    for course in courses:
        config = json.loads((course / "course.json").read_text(encoding="utf-8"))
        cover = find_image(course / "cover.jpeg")
        assert cover is not None
        href = quote(course.name) + "/"
        intro = config["description"].strip().split("\n\n")[0]
        cards.append(
            f'<div class="card"><a href="{href}"><img src="{href}{quote(cover.name)}" '
            f'alt="Omslag"></a><div><h2><a href="{href}">{html.escape(config["title"])}</a>'
            f'</h2><p>{html.escape(intro)}</p></div></div>'
        )
    (args.root / "index.html").write_text(_page("Repeto – språkkurser att lyssna på", (
        "<h1>Repeto</h1><p>Språkkurser som podcast för nybörjare i alla "
        "åldrar. Hör ett ord eller en mening på svenska, säg det själv på det nya "
        "språket och lyssna sedan på svaret.</p>"
        '<p lang="pl">Kursy językowe dla początkujących: słuchaj wskazówek po polsku, '
        "odpowiadaj w przerwach i powtarzaj za nagraniem.</p>"
        '<p lang="en">Audio courses for beginners: listen to English prompts, '
        "answer in the pauses and repeat after the recording.</p>" + "".join(cards)
    )), encoding="utf-8")
    (args.root / ".nojekyll").touch()


if __name__ == "__main__":
    main()
