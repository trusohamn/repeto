"""Validate double-output practice renders and package them as podcast season 1."""

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydub import AudioSegment

import transcription as renderer

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str) -> Any:
    path = ROOT / "code" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"repeto_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _podcast_builder() -> Any:
    return _load("podcast")


def load_topic_titles(path: Path, topics: list[str], languages: tuple[str, ...]) -> dict:
    titles = json.loads(path.read_text(encoding="utf-8"))
    missing = [
        topic for topic in topics
        if any(not titles.get(topic, {}).get(language) for language in languages)
    ]
    if missing:
        raise ValueError(f"Topic titles are missing for: {', '.join(missing)}")
    return titles


def select_manifests(
    renders: Path, topics: dict[str, list[renderer.Entry]], source: str, target: str,
    selected: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    for path in sorted(renders.glob(f"*_{source}_{target}_double_*.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        title = manifest["section"]
        if selected is not None and title not in selected:
            continue
        if title in manifests:
            raise ValueError(f"Multiple renders for {title!r}; remove the stale one.")
        manifests[title] = manifest
    expected = set(topics) if selected is None else selected
    if set(manifests) != expected:
        missing = sorted(expected - set(manifests))
        extra = sorted(set(manifests) - expected)
        raise ValueError(f"Renders do not match topics; missing={missing}, extra={extra}")
    return manifests


def validate_render(
    audio_path: Path, manifest: dict[str, Any], items: list[renderer.Entry],
    number: int, source: str, target: str,
) -> None:
    if (manifest["source_language"], manifest["target_language"]) != (source, target):
        raise ValueError(f"Wrong direction in {audio_path.name}")
    if not manifest["audio_file"].startswith(f"{number:02d}_"):
        raise ValueError(f"Topic number mismatch: {manifest['audio_file']}")
    audio = AudioSegment.from_file(str(audio_path), format="mp3")
    if audio.frame_rate != renderer.SAMPLE_RATE:
        raise ValueError(f"Unexpected sample rate in {audio_path.name}")
    if abs(len(audio) - manifest["total_duration_ms"]) > 1:
        raise ValueError(f"Duration differs from manifest: {audio_path.name}")
    entries = manifest["entries"]
    if [entry["id"] for entry in entries] != [item["id"] for item in items]:
        raise ValueError(f"Entries are stale or incomplete: {audio_path.name}")
    cursor = renderer.LEAD_IN_MS
    for entry, item in zip(entries, items):
        if entry[source]["text"] != item[source] or entry[target]["text"] != item[target]:
            raise ValueError(f"Stale text for {item['id']} in {audio_path.name}")
        if entry["entry_start_ms"] != cursor or entry[source]["start_ms"] != cursor:
            raise ValueError(f"Timing gap before {item['id']} in {audio_path.name}")
        playbacks = entry["target_playbacks"]
        if len(playbacks) != 2 or playbacks[0] != entry[target]:
            raise ValueError(f"Expected two target playbacks for {item['id']}")
        first, second = playbacks
        if (
            first["start_ms"] - entry[source]["end_ms"] != renderer.THINKING_MS
            or second["start_ms"] - first["end_ms"] != renderer.REPETITION_MS
            or entry["entry_end_ms"] - second["end_ms"] != renderer.REPETITION_MS
        ):
            raise ValueError(f"Unexpected pauses for {item['id']} in {audio_path.name}")
        for segment in (entry[source], first, second):
            if not 0 <= segment["start_ms"] < segment["end_ms"] <= len(audio):
                raise ValueError(f"Segment out of bounds for {item['id']}")
            if audio[segment["start_ms"]:segment["end_ms"]].rms == 0:
                raise ValueError(f"Silent segment for {item['id']}")
        cursor = entry["entry_end_ms"]
    if abs(cursor - len(audio)) > 1:
        raise ValueError(f"Trailing audio mismatch in {audio_path.name}")


def move_audio(source: Path, destination: Path) -> None:
    """Move a render into the podcast so each episode MP3 exists only once."""
    if source.is_file():
        if destination.exists():
            if destination.read_bytes() != source.read_bytes():
                raise FileExistsError(f"Refusing to overwrite different audio: {destination}")
            source.unlink()
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(source, destination)
    elif not destination.is_file():
        raise FileNotFoundError(f"Missing practice audio: {source}")


def package(args: argparse.Namespace) -> dict[str, Any]:
    """Validate renders, move them into the course, and rebuild every feed."""
    source, target = args.source, args.target
    catalog_target = "sv" if target == "se" else target
    if catalog_target not in _load("descriptions").LANGUAGES:
        raise ValueError(f"No Swedish language name configured for {target!r}.")
    if source not in ("se", "pl", "en", "ru", "es"):
        raise ValueError("Podcast copy supports only --source se, pl, en, ru or es.")
    catalog_source = "sv" if source == "se" else source
    topics = renderer.load_topics(args.transcript)
    requested = getattr(args, "topic", None)
    selected = set(requested) if requested else None
    if selected is not None:
        unknown = sorted(selected - set(topics))
        if unknown:
            raise ValueError(f"Unknown topics: {', '.join(unknown)}")
    titles = load_topic_titles(args.topic_titles, list(topics), (source, target))
    manifests = select_manifests(args.renders, topics, source, target, selected)
    course = args.podcast_root / args.course
    if _podcast_builder().find_image(course / "cover.jpeg") is None:
        raise FileNotFoundError(f"Podcast cover not found: {course / 'cover.jpeg'}")
    catalog_path = course / "course.json"
    copy = _load("descriptions")
    had_catalog = catalog_path.is_file()
    if had_catalog:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        if (
            catalog.get("source_language", "sv"), catalog.get("target_language", catalog_target)
        ) != (catalog_source, catalog_target):
            raise ValueError(f"Podcast course {args.course!r} has another direction.")
    else:
        catalog = {
            "title": copy.show_title(target, source=catalog_source),
            "description": copy.show_description(
                target, len(topics), [], args.email, source=catalog_source,
            ),
            "language": catalog_source,
            "author": args.author,
            "email": args.email,
            "source_language": catalog_source,
            "target_language": catalog_target,
            "episodes": [],
        }
    previous = {episode["id"]: episode for episode in catalog["episodes"]}
    published = datetime.now(timezone.utc).isoformat(timespec="seconds")
    practice_episodes = []
    for number, (topic, items) in enumerate(topics.items(), start=1):
        if selected is not None and topic not in selected:
            continue
        manifest = manifests[topic]
        filename = manifest["audio_file"]
        render = args.renders / filename
        destination = course / "audio" / "practice" / filename
        episode_id = f"repeto:{args.course}:topic-{number:02d}"
        old = previous.get(episode_id, {})
        # Published audio lives in R2, not the checkout; it was validated before upload.
        in_storage_only = (
            not render.is_file() and not destination.is_file()
            and old.get("file") == f"practice/{filename}"
            and _podcast_builder().published_audio(old) is not None
        )
        if not in_storage_only:
            validate_render(
                render if render.is_file() else destination,
                manifest, items, number, source, target,
            )
        source_title = titles[topic][source]
        practice_episodes.append((render, destination, _podcast_builder().preserve_episode_metadata(old, {
            "id": episode_id,
            "title": f"{source_title} — {titles[topic][target]}",
            "file": f"practice/{filename}",
            "duration_ms": manifest["total_duration_ms"],
            "published": old.get("published", published),
            "description": copy.practice_description(
                target, number, len(topics), titles[topic], items, source,
            ),
            "season": old.get("season", 1),
            "episode": old.get("episode", number),
        })))
        print(f"Validated: {topic} ({len(items)} entries)", flush=True)
    for render, destination, episode in practice_episodes:
        if render.is_file() or destination.is_file() or "sha256" not in episode:
            move_audio(render, destination)
    new_ids = {episode["id"] for _, _, episode in practice_episodes}
    if not had_catalog:
        catalog["episodes"] = [episode for _, _, episode in practice_episodes] + [
            episode for episode in catalog["episodes"] if episode["id"] not in new_ids
        ]
    else:
        replacements = {episode["id"]: episode for _, _, episode in practice_episodes}
        catalog["episodes"] = [
            replacements.get(episode["id"], episode) for episode in catalog["episodes"]
        ] + [
            episode for _, _, episode in practice_episodes if episode["id"] not in previous
        ]
    if had_catalog and practice_episodes:
        catalog.setdefault("seasons", {}).setdefault(
            str(practice_episodes[0][2]["season"]),
            {"sv": "Övningar", "pl": "Ćwiczenia", "en": "Practice",
             "ru": "Практика", "es": "Práctica"}[catalog_source],
        )
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not had_catalog:
        catalog = copy.refresh_course(course, practice=(topics, titles))
    superseded = [
        previous[episode["id"]]["file"] for _, _, episode in practice_episodes
        if episode["id"] in previous and "file" in previous[episode["id"]]
    ]
    if not getattr(args, "retain_superseded_audio", False):
        for path in _podcast_builder().remove_superseded_audio(course, superseded):
            print(f"Removed superseded audio: {path.relative_to(course)}", flush=True)
    if not getattr(args, "skip_site_build", False):
        subprocess.run(
            [sys.executable, str(ROOT / "code" / "podcast.py"),
             "--root", str(args.podcast_root.resolve()), "--base-url", args.podcast_base_url],
            cwd=ROOT, check=True,
        )
    return catalog


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="se", choices=renderer.LANGUAGES)
    parser.add_argument("--target", required=True, choices=renderer.LANGUAGES)
    parser.add_argument("--course", required=True, help="Podcast course slug.")
    parser.add_argument("--renders", type=Path, required=True)
    parser.add_argument(
        "--topic", action="append", help="Package this exact topic title; may be repeated.",
    )
    parser.add_argument(
        "--transcript", type=Path, default=ROOT / "courses/practice/transcript.json"
    )
    parser.add_argument(
        "--topic-titles", type=Path, default=ROOT / "courses/practice/topics.json"
    )
    parser.add_argument("--podcast-root", type=Path, default=ROOT / "podcast")
    parser.add_argument(
        "--podcast-base-url", default="https://repeto.stream"
    )
    parser.add_argument("--author", default="Repeto.stream")
    parser.add_argument("--email", default="repeto.stream@gmail.com")
    parser.add_argument(
        "--retain-superseded-audio",
        action="store_true",
        help="Keep old versioned MP3s on disk after replacing their catalog entries.",
    )
    parser.add_argument(
        "--skip-site-build",
        action="store_true",
        help="Do not rebuild the complete podcast website after packaging.",
    )
    return parser


def main() -> None:
    catalog = package(create_parser().parse_args())
    print(f'Packaged {len(catalog["episodes"])} episodes: {catalog["title"]}')


if __name__ == "__main__":
    main()
