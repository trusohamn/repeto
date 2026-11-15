"""Infer published audio directions affected by changes to course source data."""

import argparse
import json
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PRACTICE_LANGUAGE_ALIASES = {"sv": "se"}


@dataclass(frozen=True, order=True)
class AudioTarget:
    kind: str
    course: str
    source: str
    target: str
    story_id: str | None = None


@dataclass
class StoryLanguageChanges:
    narration_targets: set[str]
    vocabulary_languages: set[str]


def _read_json(path: Path, root: Path | None = None) -> Any | None:
    boundary = root or path.parent
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError(f"Audio target input must not be a symlink: {parent}")
        if parent == boundary:
            break
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _entries_by_id(data: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(data, list):
        return {}
    return {
        str(entry["id"]): entry
        for entry in data
        if isinstance(entry, Mapping) and "id" in entry
    }


def _changed_practice_languages(base: Any, head: Any) -> set[str]:
    old_entries, new_entries = _entries_by_id(base), _entries_by_id(head)
    changed: set[str] = set()
    speech_fields = {
        key
        for entry in (*old_entries.values(), *new_entries.values())
        for key, value in entry.items()
        if isinstance(value, str) and key not in {"id", "topic"}
    }
    for entry_id in old_entries.keys() | new_entries.keys():
        old, new = old_entries.get(entry_id), new_entries.get(entry_id)
        if old is None or new is None:
            changed.update(
                language
                for language in speech_fields
                if (old or {}).get(language) != (new or {}).get(language)
            )
            continue
        if old.get("topic") != new.get("topic"):
            changed.update(
                language
                for language in speech_fields
                if language in old or language in new
            )
        else:
            changed.update(
                language
                for language in speech_fields
                if old.get(language) != new.get(language)
            )
    return changed


def _chapter_map(data: Any) -> tuple[str | None, dict[int, Mapping[str, Any]]]:
    if not isinstance(data, Mapping):
        return None, {}
    story_id = data.get("story_id")
    chapters = data.get("chapters")
    if not isinstance(chapters, list):
        return str(story_id) if story_id is not None else None, {}
    result: dict[int, Mapping[str, Any]] = {}
    for chapter in chapters:
        if not isinstance(chapter, Mapping):
            continue
        number = chapter.get("chapter_number")
        if isinstance(number, int):
            result[number] = chapter
    return str(story_id) if story_id is not None else None, result


def _changed_story_source_languages(
    base_root: Path, head_root: Path, story_slug: str
) -> set[str]:
    old_dir = base_root / "courses/stories" / story_slug / "complete"
    new_dir = head_root / "courses/stories" / story_slug / "complete"
    languages = {
        path.stem
        for root in (old_dir, new_dir)
        if root.is_dir()
        for path in root.glob("*.txt")
    }
    for directory in (old_dir, new_dir):
        if directory.is_symlink():
            raise ValueError(f"Audio target input must not be a symlink: {directory}")
    return {
        language
        for language in languages
        if not (old_dir / f"{language}.txt").is_symlink()
        and not (new_dir / f"{language}.txt").is_symlink()
        if (old_dir / f"{language}.txt").is_file() != (new_dir / f"{language}.txt").is_file()
        or (
            (old_dir / f"{language}.txt").is_file()
            and (new_dir / f"{language}.txt").is_file()
            and (old_dir / f"{language}.txt").read_bytes()
            != (new_dir / f"{language}.txt").read_bytes()
        )
    }


def _language_texts(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _changed_story_languages(
    base: Any, head: Any
) -> tuple[str | None, StoryLanguageChanges]:
    old_id, old_chapters = _chapter_map(base)
    new_id, new_chapters = _chapter_map(head)
    story_id = new_id or old_id
    changes = StoryLanguageChanges(set(), set())

    def include_all(chapter: Mapping[str, Any]) -> None:
        for field in ("chapter_text", "titles"):
            changes.narration_targets.update(_language_texts(chapter.get(field)))
        for word in chapter.get("vocabulary", []):
            if isinstance(word, Mapping):
                changes.vocabulary_languages.update(_language_texts(word.get("text")))

    if old_id != new_id:
        for chapter in (*old_chapters.values(), *new_chapters.values()):
            include_all(chapter)
        for data in (base, head):
            if isinstance(data, Mapping):
                changes.narration_targets.update(_language_texts(data.get("titles")))
        return story_id, changes

    for number in old_chapters.keys() | new_chapters.keys():
        old, new = old_chapters.get(number), new_chapters.get(number)
        if old is None or new is None:
            include_all(old or new or {})
            continue
        for field in ("chapter_text", "titles"):
            old_text, new_text = _language_texts(old.get(field)), _language_texts(new.get(field))
            changes.narration_targets.update(
                language
                for language in old_text.keys() | new_text.keys()
                if old_text.get(language) != new_text.get(language)
            )

        old_words = {
            str(word["id"]): word
            for word in old.get("vocabulary", [])
            if isinstance(word, Mapping) and "id" in word
        }
        new_words = {
            str(word["id"]): word
            for word in new.get("vocabulary", [])
            if isinstance(word, Mapping) and "id" in word
        }
        for word_id in old_words.keys() | new_words.keys():
            old_word, new_word = old_words.get(word_id), new_words.get(word_id)
            old_text = _language_texts((old_word or {}).get("text"))
            new_text = _language_texts((new_word or {}).get("text"))
            changes.vocabulary_languages.update(
                language
                for language in old_text.keys() | new_text.keys()
                if old_text.get(language) != new_text.get(language)
            )

    for field in ("titles",):
        old_text = _language_texts((base or {}).get(field) if isinstance(base, Mapping) else None)
        new_text = _language_texts((head or {}).get(field) if isinstance(head, Mapping) else None)
        changes.narration_targets.update(
            language
            for language in old_text.keys() | new_text.keys()
            if old_text.get(language) != new_text.get(language)
        )
    return story_id, changes


def _catalogs(root: Path) -> list[tuple[str, str, str, list[Mapping[str, Any]]]]:
    courses: list[tuple[str, str, str, list[Mapping[str, Any]]]] = []
    for catalog_path in sorted(root.glob("*/course.json")):
        data = _read_json(catalog_path, root)
        if not isinstance(data, Mapping):
            continue
        source, target = data.get("source_language"), data.get("target_language")
        episodes = data.get("episodes")
        if isinstance(source, str) and isinstance(target, str) and isinstance(episodes, list):
            courses.append(
                (
                    catalog_path.parent.name,
                    source,
                    target,
                    [episode for episode in episodes if isinstance(episode, Mapping)],
                )
            )
    return courses


def infer_audio_targets(base_root: Path, head_root: Path) -> list[AudioTarget]:
    """Return existing catalog directions whose spoken source data changed."""
    base_practice = _read_json(
        base_root / "courses/practice/transcript.json", base_root
    )
    head_practice = _read_json(
        head_root / "courses/practice/transcript.json", head_root
    )
    changed_practice = _changed_practice_languages(base_practice, head_practice)

    catalog_root = head_root / "podcast"
    if not catalog_root.is_dir():
        catalog_root = base_root / "podcast"
    courses = _catalogs(catalog_root)
    targets: set[AudioTarget] = set()

    if changed_practice:
        old_entries = _entries_by_id(base_practice)
        new_entries = _entries_by_id(head_practice)
        changed_ids = set(old_entries) ^ set(new_entries)
        for entry_id in set(old_entries) | set(new_entries):
            old = old_entries.get(entry_id, {})
            new = new_entries.get(entry_id, {})
            changed_languages = {
                language
                for language in old.keys() | new.keys()
                if language not in {"id", "topic"}
                and old.get(language) != new.get(language)
            }
            if old.get("topic") != new.get("topic") or entry_id in changed_ids:
                changed_languages.update(
                    key for key in old.keys() | new.keys() if key not in {"id", "topic"}
                )
            if not changed_languages:
                continue
            available = {
                language
                for entry in (old, new)
                for language, text in entry.items()
                if language not in {"id", "topic"}
                and isinstance(text, str)
                and text
            }
            for slug, catalog_source, catalog_target, _ in courses:
                source = PRACTICE_LANGUAGE_ALIASES.get(catalog_source, catalog_source)
                target = PRACTICE_LANGUAGE_ALIASES.get(catalog_target, catalog_target)
                if (
                    source != target
                    and source in available
                    and target in available
                    and ({catalog_source, catalog_target} & changed_languages
                         or {source, target} & changed_languages)
                ):
                    targets.add(AudioTarget("practice", slug, source, target))

    stories_base = base_root / "courses/stories"
    stories_head = head_root / "courses/stories"
    story_ids = {
        path.parent.parent.name
        for root in (stories_base, stories_head)
        for path in root.glob("*/generated/transcript.json")
    }
    for story_slug in sorted(story_ids):
        base_story = _read_json(
            stories_base / story_slug / "generated/transcript.json", base_root
        )
        head_story = _read_json(
            stories_head / story_slug / "generated/transcript.json", head_root
        )
        story_id, changes = _changed_story_languages(base_story, head_story)
        changes.narration_targets.update(
            _changed_story_source_languages(base_root, head_root, story_slug)
        )
        if not changes.narration_targets and not changes.vocabulary_languages:
            continue
        for slug, source, target, episodes in courses:
            has_story = any(
                str(episode.get("id", "")).startswith(f"{story_id}:")
                for episode in episodes
            )
            affects_narration = target in changes.narration_targets
            affects_vocabulary = bool(
                {source, target} & changes.vocabulary_languages
            )
            if has_story and (affects_narration or affects_vocabulary):
                targets.add(AudioTarget("story", slug, source, target, story_id))
    return sorted(targets)


def render_report(targets: list[AudioTarget]) -> str:
    if not targets:
        return (
            "No existing audio directions are affected by spoken-text changes. "
            "Topic titles and other catalog-only edits do not trigger TTS."
        )
    lines = ["Affected audio targets (no audio has been generated):"]
    for target in targets:
        label = f"{target.kind}: {target.course} ({target.source} -> {target.target})"
        if target.story_id:
            label += f", story `{target.story_id}`"
        lines.append(f"- {label}")
    lines.append(
        "\nAdd the `publish-audio` label to authorize generation. The run will "
        "reuse verified cached clips and synthesize only cache misses."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True, help="Base revision checkout")
    parser.add_argument("--head", type=Path, required=True, help="PR revision checkout")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    args = parser.parse_args(argv)
    try:
        targets = infer_audio_targets(args.base, args.head)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
        print(f"error: cannot infer audio targets: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps([asdict(target) for target in targets], ensure_ascii=False, indent=2))
    else:
        print(render_report(targets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
