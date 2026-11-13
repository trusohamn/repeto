"""Build podcast RSS feeds from course catalogs using only the standard library."""

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import website  # noqa: E402
from website import text_to_html  # noqa: E402,F401

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM = "http://www.w3.org/2005/Atom"
CONTENT = "http://purl.org/rss/1.0/modules/content/"
ET.register_namespace("itunes", ITUNES)
ET.register_namespace("atom", ATOM)
ET.register_namespace("content", CONTENT)
FINGERPRINT = re.compile(r"-[0-9a-f]{8}")
AUDIO_BASE_URL = "https://audio.repeto.stream"
AUDIO_METADATA = ("bytes", "sha256")
SHA256 = re.compile(r"[0-9a-f]{64}")

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


def audio_key(course_name: str, filename: str) -> str:
    """Return the storage key for an episode; it mirrors the GitHub Pages path."""
    return f"{course_name}/audio/{filename}"


def safe_audio_path(filename: object) -> PurePosixPath:
    if not isinstance(filename, str):
        raise ValueError(f"Invalid audio filename: {filename!r}")
    relative = PurePosixPath(filename)
    if (
        "\\" in filename
        or relative.is_absolute()
        or str(relative) != filename
        or any(part in {"", ".", ".."} for part in relative.parts)
        or relative.suffix != ".mp3"
    ):
        raise ValueError(f"Invalid audio filename: {filename!r}")
    return relative


def published_audio(episode: dict) -> tuple[int, str] | None:
    """Return verified upload metadata (size, SHA-256), or None if not uploaded."""
    present = [name for name in AUDIO_METADATA if name in episode]
    if not present:
        return None
    size, digest = episode.get("bytes"), episode.get("sha256")
    if (
        len(present) != len(AUDIO_METADATA)
        or type(size) is not int or size < 1
        or not isinstance(digest, str) or SHA256.fullmatch(digest) is None
    ):
        raise ValueError(f"Invalid published audio metadata: {episode.get('id')!r}")
    return size, digest


def carry_audio_metadata(previous: dict, episode: dict) -> dict:
    """Keep upload metadata when a repackaged episode still uses the same audio file."""
    if previous.get("file") == episode.get("file"):
        for name in AUDIO_METADATA:
            if name in previous:
                episode[name] = previous[name]
    return episode


def build_feed(course: Path, base_url: str, audio_base_url: str = AUDIO_BASE_URL) -> None:
    config = json.loads((course / "course.json").read_text(encoding="utf-8"))
    url = f"{base_url.rstrip('/')}/{quote(course.name)}"
    if not base_url.startswith("https://") or not audio_base_url.startswith("https://"):
        raise ValueError("Podcast hosting requires HTTPS base URLs.")
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
    labels = website.UI[website.course_ui(config)]
    field(channel, "description", f'{config["description"]}\n\n{labels["all_episodes"]}: {url}/')
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
        relative_audio_path = safe_audio_path(episode["file"])
        audio = course / "audio" / Path(*relative_audio_path.parts)
        audio_path = "/".join(quote(part) for part in relative_audio_path.parts)
        published = published_audio(episode)
        if published is not None:
            audio_length = published[0]
            if audio.is_file() and audio.stat().st_size != audio_length:
                raise ValueError(f"Local audio differs from published metadata: {audio}")
            audio_url = (
                f"{audio_base_url.rstrip('/')}/{quote(course.name)}/audio/{audio_path}"
            )
        else:
            if not audio.is_file() or audio.stat().st_size == 0:
                raise ValueError(f"Missing or empty audio: {audio}")
            audio_length = audio.stat().st_size
            audio_url = f"{url}/audio/{audio_path}"
        if episode["id"] in seen:
            raise ValueError(f"Duplicate episode ID: {episode['id']}")
        seen.add(episode["id"])
        item = ET.SubElement(channel, "item")
        title = f"{number:02d} {episode['title']}"
        field(item, "title", title)
        page = website.episode_url(base_url, quote(course.name), episode)
        field(item, "link", page)
        field(item, "description", f'{episode["description"]}\n\n{labels["transcript"]}: {page}')
        field(item, f"{{{CONTENT}}}encoded",
              text_to_html(episode["description"]) + f'<p>{labels["transcript"]}: <a href="{page}">{page}</a></p>')
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
            item, "enclosure", url=audio_url, length=str(audio_length), type="audio/mpeg",
        )
    ET.indent(rss)
    ET.ElementTree(rss).write(course / "feed.xml", encoding="utf-8", xml_declaration=True)


def build_index(root: Path, courses: list[Path], base_url: str = "https://repeto.stream",
                practice: dict | None = None, stories: dict | None = None) -> None:
    """Validate store links and build the website (homepage, course pages, transcripts)."""
    catalogs = []
    for course in courses:
        config = json.loads((course / "course.json").read_text(encoding="utf-8"))
        config.setdefault("source_language", config.get("language"))
        if config["source_language"] not in website.UI:
            raise ValueError(f"Unsupported homepage audience: {config['source_language']!r}")
        cover = find_image(course / "cover.jpeg")
        if cover is None:
            raise ValueError(f"Missing cover: {course}")
        spotify = config.get("links", {}).get("Spotify")
        youtube = config.get("links", {}).get("YouTube")
        if youtube and re.fullmatch(
            r"https://www\.youtube\.com/playlist\?list=PL[A-Za-z0-9_-]{10,}", youtube
        ) is None:
            raise ValueError(f"Invalid YouTube playlist URL for {course.name}: {youtube!r}")
        if spotify and website.SPOTIFY_SHOW.fullmatch(spotify) is None:
            raise ValueError(f"Invalid Spotify show URL for {course.name}: {spotify!r}")
        config["slug"] = course.name
        config["cover"] = quote(cover.name)
        for episode in config["episodes"]:
            if "image" in episode:
                image = find_image(course / Path(*PurePosixPath(episode["image"]).parts))
                if image is not None:
                    episode["cover"] = "/".join(
                        quote(part) for part in (*PurePosixPath(episode["image"]).parts[:-1], image.name)
                    )
                    config.setdefault("story_cover", f"{quote(course.name)}/{episode['cover']}")
        catalogs.append(config)
    website.build_site(root, catalogs, base_url, practice=practice, stories=stories)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("podcast"))
    parser.add_argument("--base-url", default="https://repeto.stream")
    parser.add_argument(
        "--audio-base-url", default=AUDIO_BASE_URL,
        help="Public URL for audio that has verified upload metadata in course.json.",
    )
    args = parser.parse_args()
    courses = sorted(path.parent for path in args.root.glob("*/course.json"))
    if not courses:
        raise ValueError("No course catalogs found.")
    for course in courses:
        build_feed(course, args.base_url, args.audio_base_url)
    build_index(args.root, courses, args.base_url)
    (args.root / ".nojekyll").touch()


if __name__ == "__main__":
    main()
