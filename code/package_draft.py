"""Package a local, audio-free podcast draft in an isolated output root."""

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import descriptions
import package_practice
import podcast
import story_course
import website

ROOT = Path(__file__).resolve().parent.parent


def package(args: argparse.Namespace) -> dict:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.course):
        raise ValueError("Course must be a lowercase URL-safe slug.")
    source = "sv" if args.source in ("se", "sv") else args.source
    target = "sv" if args.target in ("se", "sv") else args.target
    if source not in ("sv", "pl", "en", "ru", "es") or target not in descriptions.LANGUAGES:
        raise ValueError("Unsupported podcast language direction.")
    if source == target:
        raise ValueError("Source and target must differ.")
    practice_source = "se" if source == "sv" else source
    practice_target = "se" if target == "sv" else target
    topics = package_practice.renderer.load_topics(args.transcript)
    titles = package_practice.load_topic_titles(
        args.topic_titles, list(topics), (practice_source, practice_target)
    )
    for topic, items in topics.items():
        if any(not item.get(practice_source) or not item.get(practice_target) for item in items):
            raise ValueError(f"Missing practice translations in {topic!r}.")
    story = story_course.load_transcript(args.story_transcript, args.story_source)
    for chapter in story["chapters"]:
        for language in (source, target):
            if language not in chapter["chapter_text"] or language not in chapter["titles"]:
                raise ValueError(f"Missing {language} story text in chapter {chapter['chapter_number']}.")
    if not args.cover.is_file() or not args.cover.stat().st_size:
        raise ValueError(f"Missing or empty podcast cover: {args.cover}")
    if not args.story_cover.is_file() or not args.story_cover.stat().st_size:
        raise ValueError(f"Missing or empty story cover: {args.story_cover}")
    root = args.output_root.resolve()
    production_root = (ROOT / "podcast").resolve()
    if root == production_root or root.is_relative_to(production_root) or production_root.is_relative_to(root):
        raise ValueError("Draft output root must be separate from the production podcast directory.")
    marker = root / ".repeto-draft"
    if root.exists() and any(root.iterdir()) and not marker.is_file():
        raise ValueError("Draft output root must be empty or an existing Repeto draft root.")
    other_catalogs = [path for path in root.glob("*/course.json") if path.parent.name != args.course]
    if other_catalogs:
        raise ValueError("Draft output root must not contain other course catalogs.")
    course = root / args.course
    catalog_path = course / "course.json"
    had_catalog = catalog_path.exists()
    if had_catalog:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        if (catalog.get("source_language"), catalog.get("target_language")) != (source, target):
            raise ValueError("Existing draft has a different language direction.")
        if any(
            ep.get("pending_audio") is not True
            or any(key in ep for key in ("file", "duration_ms", "bytes", "sha256"))
            for ep in catalog["episodes"]
        ):
            raise ValueError("Refusing to overwrite a draft with completed episodes.")
    else:
        catalog = {
            "language": source, "source_language": source, "target_language": target,
            "author": args.author, "email": args.email, "episodes": [],
        }
    previous = {ep["id"]: ep for ep in catalog["episodes"]}
    if len(previous) != len(catalog["episodes"]):
        raise ValueError("Existing draft has duplicate episode IDs.")
    published = datetime.now(timezone.utc).isoformat(timespec="seconds")
    episodes = []
    for number, (topic, items) in enumerate(topics.items(), 1):
        episode_id = f"repeto:{args.course}:topic-{number:02d}"
        old = previous.get(episode_id, {})
        episode = {
            "id": episode_id, "title": f"{titles[topic][practice_source]} — {titles[topic][practice_target]}",
            "pending_audio": True, "published": old.get("published", published),
            "description": descriptions.practice_description(
                practice_target, number, len(topics), titles[topic], items, practice_source,
            ),
            "season": old.get("season", 1), "episode": old.get("episode", number),
        }
        episode.update(old)
        episodes.append(episode)
    story_titles = story["titles"]
    image = f'images/stories/{story["story_id"]}/cover.jpeg'
    for chapter in story["chapters"]:
        number = chapter["chapter_number"]
        episode_id = f'{story["story_id"]}:{source}:{target}:chapter-{number:02d}'
        old = previous.get(episode_id, {})
        episode = {
            "id": episode_id,
            "title": f'{story_titles[source]}: {chapter["titles"][source]} — {chapter["titles"][target]}',
            "pending_audio": True, "published": old.get("published", published),
            "description": descriptions.story_description(target, story_titles, chapter, len(story["chapters"]), source),
            "image": image, "season": old.get("season", 2), "episode": old.get("episode", number),
        }
        episode.update(old)
        episodes.append(episode)
    if set(previous) - {ep["id"] for ep in episodes}:
        raise ValueError("Existing draft contains episodes absent from source data.")
    catalog["episodes"] = episodes
    course.mkdir(parents=True, exist_ok=True)
    marker.touch()
    for logical, source_path in ((course / "cover.jpeg", args.cover), (course / image, args.story_cover)):
        existing = podcast.find_image(logical)
        if existing and existing.read_bytes() != source_path.read_bytes():
            raise ValueError(f"Refusing to overwrite different artwork: {existing}")
        if not existing:
            logical.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, logical)
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not had_catalog:
        catalog = descriptions.refresh_course(course, {story["story_id"]: story}, (topics, titles))
    podcast.build_feed(course, args.base_url, draft=True)
    practice = {"topics": [{"topic": name, "names": titles[name], "phrases": items}
                           for name, items in topics.items()]}
    podcast.build_index(root, [course], args.base_url, practice=practice, stories={story["story_id"]: story})
    return catalog


def install_draft(draft_root: Path, course_name: str, podcast_root: Path) -> Path:
    """Install the catalog, draft feed and artwork without replacing existing files."""
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", course_name):
        raise ValueError("Course must be a lowercase URL-safe slug.")
    draft_root = draft_root.resolve()
    if not (draft_root / ".repeto-draft").is_file():
        raise ValueError("Missing draft root marker.")
    draft = draft_root / course_name
    destination = podcast_root.resolve() / course_name
    if draft.is_symlink() or destination.is_symlink():
        raise ValueError("Draft and destination course directories must not be symlinks.")
    if draft.resolve() == destination.resolve():
        raise ValueError("Draft and destination must be separate.")
    catalog_path = draft / "course.json"
    if catalog_path.is_symlink():
        raise ValueError("Draft catalog must not be a symlink.")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    episodes = catalog["episodes"]
    if not episodes or any(
        episode.get("pending_audio") is not True
        or any(key in episode for key in ("file", "duration_ms", "bytes", "sha256"))
        for episode in episodes
    ):
        raise ValueError("Only a completely pending draft can be installed.")
    feed_path = draft / "feed.xml"
    if feed_path.is_symlink() or not feed_path.is_file():
        raise ValueError("Missing or unsafe draft feed.")
    files = {
        Path("course.json"): catalog_path.read_bytes(),
        Path("feed.xml"): feed_path.read_bytes(),
    }
    image_names = {"cover.jpeg"}
    for episode in episodes:
        if "image" in episode:
            name = episode["image"]
            if not isinstance(name, str) or not re.fullmatch(
                r"images/stories/[a-z0-9_]+/cover\.jpeg", name
            ):
                raise ValueError(f"Invalid story image path: {name!r}")
            image_names.add(name)
    for name in sorted(image_names):
        logical = Path(name)
        source = podcast.find_image(draft / logical)
        if source is None or not source.is_file() or any(
            part.is_symlink() for part in (source, *source.parents) if part != draft_root.parent
        ):
            raise ValueError(f"Missing draft artwork: {name}")
        data = source.read_bytes()
        if not data:
            raise ValueError(f"Empty draft artwork: {name}")
        fingerprint = hashlib.sha256(data).hexdigest()[:8]
        files[logical.with_name(f"{logical.stem}-{fingerprint}{logical.suffix}")] = data
        existing = podcast.find_image(destination / logical)
        if existing and (existing.is_symlink() or existing.read_bytes() != data):
            raise FileExistsError(f"Refusing to overwrite different artwork: {existing}")
    for relative, data in files.items():
        path = destination / relative
        if any(part.is_symlink() for part in (path, *path.parents) if part != podcast_root.parent):
            raise ValueError(f"Symlink in destination path: {path}")
        if path.exists() and (not path.is_file() or path.read_bytes() != data):
            raise FileExistsError(f"Refusing to overwrite different file: {path}")
    for relative, data in files.items():
        path = destination / relative
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as output:
                output.write(data)
    return destination


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--course", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--cover", required=True, type=Path)
    parser.add_argument("--story-cover", type=Path, default=ROOT / "courses/stories/magical_radio/cover.jpeg")
    parser.add_argument("--transcript", type=Path, default=ROOT / "courses/practice/transcript.json")
    parser.add_argument("--topic-titles", type=Path, default=ROOT / "courses/practice/topics.json")
    parser.add_argument("--story-transcript", type=Path, default=ROOT / "courses/stories/magical_radio/generated/transcript.json")
    parser.add_argument("--story-source", type=Path, default=ROOT / "courses/stories/magical_radio/complete/pl.txt")
    parser.add_argument("--base-url", default="https://repeto.stream")
    parser.add_argument("--author", default="Repeto.stream")
    parser.add_argument("--email", default="repeto.stream@gmail.com")
    parser.add_argument(
        "--install", action="store_true",
        help="Install the generated catalog, draft feed and artwork into podcast/ without overwriting files.",
    )
    return parser


def main() -> None:
    args = create_parser().parse_args()
    catalog = package(args)
    print(f'Packaged {len(catalog["episodes"])} pending episodes in {args.output_root / args.course}')
    if args.install:
        print(f"Installed draft: {install_draft(args.output_root, args.course, ROOT / 'podcast')}")


if __name__ == "__main__":
    main()
