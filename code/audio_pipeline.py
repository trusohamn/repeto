"""Generate, package, and publicly stage approved PR audio using trusted code."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import quote

import audio_publish
from audio_staging import (
    StagedAudio,
    StagingError,
    StagingPrefixStorage,
    StagingTarget,
    input_fingerprint,
    make_manifest,
    read_manifest,
    safe_input_path,
    write_manifest,
)
from audio_targets import AudioTarget

ROOT = Path(__file__).resolve().parents[1]
COURSE_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
LANGUAGE = re.compile(r"[a-z]{2,3}")
MAX_REPORT_CHARS = 40_000


class PipelineError(RuntimeError):
    pass


def _read_targets(path: Path) -> list[AudioTarget]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PipelineError(f"Cannot read inferred audio targets: {error}") from error
    if not isinstance(payload, list) or not payload:
        raise PipelineError("There are no inferred audio targets to generate.")
    targets: list[AudioTarget] = []
    for entry in payload:
        if not isinstance(entry, Mapping):
            raise PipelineError("Invalid inferred audio target.")
        target = AudioTarget(
            kind=str(entry.get("kind", "")),
            course=str(entry.get("course", "")),
            source=str(entry.get("source", "")),
            target=str(entry.get("target", "")),
            story_id=str(entry["story_id"]) if entry.get("story_id") is not None else None,
        )
        if (
            target.kind not in {"practice", "story"}
            or not COURSE_SLUG.fullmatch(target.course)
            or not LANGUAGE.fullmatch(target.source)
            or not LANGUAGE.fullmatch(target.target)
            or target.source == target.target
            or (target.kind == "practice" and target.story_id is not None)
            or (
                target.kind == "story"
                and (
                    target.story_id is None
                    or not re.fullmatch(r"[A-Za-z0-9_-]+", target.story_id)
                )
            )
        ):
            raise PipelineError(f"Invalid inferred audio target: {entry!r}")
        targets.append(target)
    if len(set(targets)) != len(targets):
        raise PipelineError("Inferred audio targets contain duplicates.")
    return sorted(targets)


def _catalog_target(target: AudioTarget, root: Path) -> None:
    catalog_path = safe_input_path(root, f"podcast/{target.course}/course.json")
    if catalog_path is None:
        raise PipelineError(f"Missing or unsafe course catalog: {catalog_path}")
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PipelineError(f"Cannot read course catalog {catalog_path}: {error}") from error
    catalog_source = "sv" if target.kind == "practice" and target.source == "se" else target.source
    catalog_target = "sv" if target.kind == "practice" and target.target == "se" else target.target
    if (
        not isinstance(catalog, Mapping)
        or (catalog.get("source_language"), catalog.get("target_language"))
        != (catalog_source, catalog_target)
        or not isinstance(catalog.get("episodes"), list)
    ):
        raise PipelineError(
            f"Course catalog direction does not match target {target.course}: "
            f"{catalog_source} -> {catalog_target}"
        )
    if not any(
        isinstance(episode, Mapping)
        and str(episode.get("id", "")).startswith(
            f"{target.story_id}:" if target.kind == "story" else f"repeto:{target.course}:"
        )
        for episode in catalog["episodes"]
    ):
        raise PipelineError(f"No matching episodes found in {catalog_path}")
    cover_name = f"podcast/{target.course}/cover.jpeg"
    safe_input_path(root, cover_name, optional=True)
    cover = audio_publish.podcast.find_image(root / cover_name)
    if cover is None:
        raise PipelineError(f"Missing course cover: {root / cover_name}")
    safe_input_path(root, cover.relative_to(root).as_posix())
    if target.kind == "practice":
        topic_titles = safe_input_path(root, "courses/practice/topics.json")
        assert topic_titles is not None
        from package_practice import load_topic_titles
        from transcription import load_topics

        try:
            topics = load_topics(root / "courses/practice/transcript.json")
            load_topic_titles(topic_titles, list(topics), (target.source, target.target))
        except (OSError, TypeError, ValueError, AttributeError) as error:
            raise PipelineError(f"Invalid practice packaging inputs: {error}") from error
    if target.kind == "story":
        story_root = f"courses/stories/{target.story_id}"
        cover_source = "se" if target.source == "sv" else target.source
        candidates = [
            f"{story_root}/cover_{cover_source}_{target.target}.jpeg",
            f"{story_root}/cover.jpeg",
            f"{story_root}/cover.jpg",
        ]
        for candidate in candidates:
            path = safe_input_path(root, candidate, optional=True)
            if path is not None:
                break
        else:
            raise PipelineError(f"Missing story cover for target {target.story_id}.")


def _run(command: Sequence[str], root: Path) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=root, check=True)


def _renderer_command(
    target: AudioTarget, root: Path, work: Path, *, validate_only: bool
) -> list[str]:
    prefix = [sys.executable]
    if target.kind == "practice":
        command = [
            *prefix,
            str(ROOT / "code/transcription.py"),
            "--transcript",
            str(root / "courses/practice/transcript.json"),
            "--output",
            str(work / target.course / "renders"),
            "--cache",
            str(work / "cache"),
            "--source",
            target.source,
            "--target",
            target.target,
            "--double-output",
            "--tts-engine",
            "azure",
        ]
    else:
        story_root = root / "courses/stories" / str(target.story_id)
        command = [
            *prefix,
            str(ROOT / "code/story_course.py"),
            "--transcript",
            str(story_root / "generated/transcript.json"),
            "--source-text",
            str(story_root / "complete/pl.txt"),
            "--output",
            str(work / target.course / "renders"),
            "--cache",
            str(work / "cache"),
            "--build-manifest",
            str(work / target.course / "story-manifest.json"),
            "--source-language",
            target.source,
            "--target",
            target.target,
            "--narration-engine",
            "azure",
            "--tts-engine",
            "azure",
        ]
    if validate_only:
        command.append("--validate-only")
    else:
        command.append("--r2-cache")
        if target.kind == "story":
            command.extend(
                [
                    "--package-podcast",
                    "--podcast-course",
                    target.course,
                    "--podcast-root",
                    str(root / "podcast"),
                    "--retain-superseded-audio",
                    "--skip-site-build",
                ]
            )
    return command


def _package_practice(target: AudioTarget, root: Path, work: Path) -> None:
    _run(
        [
            sys.executable,
            str(ROOT / "code/package_practice.py"),
            "--source",
            target.source,
            "--target",
            target.target,
            "--course",
            target.course,
            "--transcript",
            str(root / "courses/practice/transcript.json"),
            "--topic-titles",
            str(root / "courses/practice/topics.json"),
            "--renders",
            str(work / target.course / "renders"),
            "--podcast-root",
            str(root / "podcast"),
            "--retain-superseded-audio",
            "--skip-site-build",
        ],
        root,
    )


def _audio_snapshot(root: Path, targets: Sequence[AudioTarget]) -> dict[Path, tuple[int, str]]:
    snapshot: dict[Path, tuple[int, str]] = {}
    for course in sorted({target.course for target in targets}):
        audio_root = root / "podcast" / course / "audio"
        if audio_root.is_dir():
            for path in audio_root.rglob("*.mp3"):
                if path.is_file() and not path.is_symlink():
                    snapshot[path.resolve()] = audio_publish.file_digest(path)
    return snapshot


def _report_files(
    report_dir: Path,
    targets: Sequence[AudioTarget],
    items: Sequence[StagedAudio],
    pull_request: int,
    approved_sha: str,
) -> list[Path]:
    base_url = os.environ.get("AUDIO_PUBLIC_BASE_URL", "https://audio.repeto.stream").rstrip("/")
    heading = [
        f"Public audio staging is ready for PR #{pull_request}.",
        f"Approved revision: `{approved_sha}`. Production audio is unchanged until merge.",
        "",
        "Affected targets:",
        *[
            f"- {target.kind}: `{target.course}` ({target.source} -> {target.target})"
            for target in targets
        ],
        "",
        "Reviewed audio links:",
    ]
    audio_lines = [
        f"- [`{item.course}/{item.file}`]({base_url}/{quote(item.staging_key, safe='/')})"
        for item in items
    ]
    pages: list[list[str]] = []
    current: list[str] = []
    length = sum(len(line) + 1 for line in heading)
    for line in audio_lines:
        if current and length + len(line) + 1 > MAX_REPORT_CHARS:
            pages.append(current)
            current = []
            length = 0
        current.append(line)
        length += len(line) + 1
    if current:
        pages.append(current)
    report_dir.mkdir(parents=True, exist_ok=True)
    files = []
    total = max(1, len(pages))
    for index, page in enumerate(pages or [[]], start=1):
        lines = heading + ([""] if total > 1 else [])
        if total > 1:
            lines.insert(2, f"Audio links, part {index} of {total}.")
        lines.extend(page)
        path = report_dir / f"audio-report-{index}.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        files.append(path)
    return files


def _validate_generation_environment() -> None:
    required = (
        "AZURE_SPEECH_KEY",
        "AZURE_SPEECH_REGION",
        "R2_ACCOUNT_ID",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET",
        "R2_CACHE_BUCKET",
        "R2_CACHE_ACCESS_KEY_ID",
        "R2_CACHE_SECRET_ACCESS_KEY",
    )
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise PipelineError(f"Missing generation or storage settings: {', '.join(missing)}")


def stage_audio(
    root: Path,
    targets_path: Path,
    pull_request: int,
    approved_sha: str,
    report_dir: Path,
) -> Path:
    if pull_request < 1:
        raise PipelineError("Pull request number must be positive.")
    if not re.fullmatch(r"[0-9a-f]{40}", approved_sha):
        raise PipelineError("Approved revision must be a full Git commit SHA.")
    if subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip() != approved_sha:
        raise PipelineError("Checked-out PR revision does not match the approved revision.")
    targets = _read_targets(targets_path)
    manifest_targets = [
        StagingTarget(target.kind, target.course, target.source, target.target, target.story_id)
        for target in targets
    ]
    source_sha256 = input_fingerprint(root, manifest_targets)
    for target in targets:
        _catalog_target(target, root)
    _validate_generation_environment()
    with tempfile.TemporaryDirectory(prefix="audio-pipeline-") as directory:
        work = Path(directory)
        for target in targets:
            _run(_renderer_command(target, root, work, validate_only=True), root)
        if input_fingerprint(root, manifest_targets) != source_sha256:
            raise PipelineError("Source data changed during validation.")
        before = _audio_snapshot(root, targets)
        for target in targets:
            _run(_renderer_command(target, root, work, validate_only=False), root)
            if target.kind == "practice":
                _package_practice(target, root, work)
        candidates = [
            path
            for path, digest in _audio_snapshot(root, targets).items()
            if before.get(path) != digest
        ]
        if not candidates:
            raise PipelineError("Audio targets were approved, but no new audio was produced.")
        items = audio_publish.pending_audio(root / "podcast", candidates)
        if not items:
            raise PipelineError("Generated audio contains no unpublished course episodes.")
        if input_fingerprint(root, manifest_targets) != source_sha256:
            raise PipelineError("Source data changed during audio generation.")
        storage = audio_publish.R2Storage.from_environment()
        staging_storage = StagingPrefixStorage(storage, pull_request, approved_sha)
        audio_publish.publish(staging_storage, items)
        audio_publish.save_metadata(items)
        for course in sorted({item.course for item in items}):
            audio_publish.podcast.build_feed(course, audio_publish.SITE_URL)
        staged_items = [
            StagedAudio(
                course=item.course.name,
                episode_id=item.episode_id,
                file=item.file,
                staging_key=f"staging/pr-{pull_request}/{approved_sha}/{item.key}",
                size=item.size,
                sha256=item.sha256,
            )
            for item in items
        ]
        manifest = make_manifest(
            pull_request, approved_sha, source_sha256, manifest_targets, staged_items
        )
        for path in (root / ".audio-staging").glob(f"pr-{pull_request}-*.json"):
            if path != root / ".audio-staging" / f"pr-{pull_request}-{approved_sha}.json":
                previous = read_manifest(path)
                for item in previous.items:
                    storage.delete(item.staging_key)
                path.unlink()
        manifest_file = write_manifest(root, manifest)
        for item in items:
            item.path.unlink()
        _report_files(report_dir, targets, staged_items, pull_request, approved_sha)
        return manifest_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Approved PR checkout")
    parser.add_argument("--targets", type=Path, required=True, help="Trusted inferred-target JSON")
    parser.add_argument("--pull-request", type=int, required=True)
    parser.add_argument("--approved-sha", required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = stage_audio(
            args.root, args.targets, args.pull_request, args.approved_sha, args.report_dir
        )
    except (
        OSError,
        subprocess.CalledProcessError,
        audio_publish.PublishError,
        PipelineError,
        StagingError,
        ValueError,
    ) as error:
        print(f"error: audio generation and staging failed: {error}", file=sys.stderr)
        return 1
    print(f"Staged reviewed audio and wrote {manifest}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
