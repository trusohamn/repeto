"""Manifest and promotion helpers for reviewed, staged audio objects."""

import argparse
import hashlib
import json
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

MANIFEST_VERSION = 1
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
COMMIT_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
COURSE_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class StagingError(RuntimeError):
    pass


class StagingStorage(Protocol):
    def digest(self, key: str) -> tuple[int, str] | None: ...

    def put_new(self, key: str, path: Path, sha256: str) -> bool: ...

    def download(self, key: str, destination: Path) -> bool: ...

    def delete(self, key: str) -> None: ...


class StagingPrefixStorage:
    def __init__(
        self, storage: StagingStorage, pull_request: int, approved_sha: str
    ) -> None:
        if pull_request < 1 or not COMMIT_SHA_PATTERN.fullmatch(approved_sha):
            raise StagingError("Invalid PR revision for staging storage.")
        self.storage = storage
        self.prefix = f"staging/pr-{pull_request}/{approved_sha}/"

    def _key(self, key: str) -> str:
        path = PurePosixPath(key)
        if path.is_absolute() or ".." in path.parts or path.as_posix() != key:
            raise StagingError(f"Unsafe staging object key: {key!r}")
        return f"{self.prefix}{key}"

    def digest(self, key: str) -> tuple[int, str] | None:
        return self.storage.digest(self._key(key))

    def put_new(self, key: str, path: Path, sha256: str) -> bool:
        return self.storage.put_new(self._key(key), path, sha256)

    def download(self, key: str, destination: Path) -> bool:
        return self.storage.download(self._key(key), destination)

    def delete(self, key: str) -> None:
        self.storage.delete(self._key(key))


@dataclass(frozen=True)
class StagingTarget:
    kind: str
    course: str
    source: str
    target: str
    story_id: str | None = None


@dataclass(frozen=True)
class StagedAudio:
    course: str
    episode_id: str
    file: str
    staging_key: str
    size: int
    sha256: str

    @property
    def production_key(self) -> str:
        return f"{self.course}/audio/{self.file}"


@dataclass(frozen=True)
class StagingManifest:
    pull_request: int
    approved_sha: str
    input_sha256: str
    targets: tuple[StagingTarget, ...]
    items: tuple[StagedAudio, ...]


def _validate_relative_file(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise StagingError(f"Unsafe audio filename in staging manifest: {value!r}")
    if len(path.parts) < 2 or path.parts[0] not in {"practice", "stories"}:
        raise StagingError(f"Unexpected audio path in staging manifest: {value!r}")
    return value


def safe_input_path(root: Path, relative: str, *, optional: bool = False) -> Path | None:
    root = root.resolve()
    path = root / relative
    for parent in (path, *path.parents):
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise StagingError(f"Staging input must not be a symlink: {parent}")
        if parent == root:
            break
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise StagingError(f"Staging input escapes repository root: {relative}")
    if not resolved.is_file():
        if optional and not resolved.exists():
            return None
        raise StagingError(f"Required staging input is missing: {relative}")
    return resolved


def input_fingerprint(root: Path, targets: Sequence[StagingTarget]) -> str:
    digest = hashlib.sha256()
    target_data = [
        asdict(target)
        for target in sorted(targets, key=lambda value: (
            value.kind, value.course, value.source, value.target, value.story_id or ""
        ))
    ]
    digest.update(json.dumps(target_data, sort_keys=True).encode("utf-8"))
    inputs: set[str] = set()
    for target in targets:
        if target.kind == "practice":
            inputs.add("courses/practice/transcript.json")
        else:
            story_root = f"courses/stories/{target.story_id}"
            inputs.update(
                {
                    f"{story_root}/generated/transcript.json",
                    f"{story_root}/complete/pl.txt",
                    f"{story_root}/generated/narration.json",
                }
            )
    for relative in sorted(inputs):
        optional = relative.endswith("/generated/narration.json")
        path = safe_input_path(root, relative, optional=optional)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if path is None:
            digest.update(b"<missing>")
        else:
            with path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _validate_catalog_entry(root: Path, item: StagedAudio) -> None:
    catalog_path = safe_input_path(
        root, f"podcast/{item.course}/course.json"
    )
    assert catalog_path is not None
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StagingError(f"Cannot read catalog {catalog_path}: {error}") from error
    if not isinstance(catalog, Mapping) or not isinstance(catalog.get("episodes"), list):
        raise StagingError(f"Invalid podcast catalog: {catalog_path}")
    episode = next(
        (
            entry for entry in catalog["episodes"]
            if isinstance(entry, Mapping) and entry.get("id") == item.episode_id
        ),
        None,
    )
    if (
        episode is None
        or episode.get("file") != item.file
        or type(episode.get("bytes")) is not int
        or episode.get("bytes") != item.size
        or episode.get("sha256") != item.sha256
    ):
        raise StagingError(
            f"Catalog metadata does not match staged audio for {item.episode_id}."
        )


def _validate_manifest(manifest: StagingManifest) -> None:
    if manifest.pull_request < 1:
        raise StagingError("Staging manifest PR number must be positive.")
    if not COMMIT_SHA_PATTERN.fullmatch(manifest.approved_sha):
        raise StagingError("Staging manifest has an invalid approved revision.")
    if not SHA256_PATTERN.fullmatch(manifest.input_sha256):
        raise StagingError("Staging manifest has an invalid source-data digest.")
    if not manifest.targets:
        raise StagingError("Staging manifest contains no audio targets.")
    if not manifest.items:
        raise StagingError("Staging manifest contains no audio objects.")
    for target in manifest.targets:
        if target.kind not in {"practice", "story"}:
            raise StagingError(f"Unknown audio target kind: {target.kind!r}")
        if not COURSE_PATTERN.fullmatch(target.course):
            raise StagingError(f"Invalid course slug in staging target: {target.course!r}")
        if target.source == target.target or not re.fullmatch(r"[a-z]{2,3}", target.source):
            raise StagingError(f"Invalid audio source language: {target.source!r}")
        if not re.fullmatch(r"[a-z]{2,3}", target.target):
            raise StagingError(f"Invalid audio target language: {target.target!r}")
        if target.kind == "story" and (
            target.story_id is None
            or not re.fullmatch(r"[A-Za-z0-9_-]+", target.story_id)
        ):
            raise StagingError("Story targets must identify a valid story ID.")
        if target.kind == "practice" and target.story_id is not None:
            raise StagingError("Practice targets cannot have a story ID.")
    seen: set[str] = set()
    covered_targets: set[StagingTarget] = set()
    for item in manifest.items:
        if not COURSE_PATTERN.fullmatch(item.course):
            raise StagingError(f"Invalid course slug in staging manifest: {item.course!r}")
        targets = [target for target in manifest.targets if target.course == item.course]
        matching_targets = [
            target
            for target in targets
            if (
                target.kind == "practice"
                and item.episode_id.startswith(f"repeto:{item.course}:topic-")
            )
            or (
                target.kind == "story"
                and item.episode_id.startswith(
                    f"{target.story_id}:{target.source}:{target.target}:chapter-"
                )
            )
        ]
        if not matching_targets:
            raise StagingError(f"Audio item has no matching target: {item.course!r}")
        covered_targets.update(matching_targets)
        if not item.episode_id:
            raise StagingError("Staging manifest episode IDs must not be empty.")
        _validate_relative_file(item.file)
        expected_key = (
            f"staging/pr-{manifest.pull_request}/{manifest.approved_sha}/"
            f"{item.production_key}"
        )
        if item.staging_key != expected_key:
            raise StagingError(
                f"Staging key does not match PR revision and production path: "
                f"{item.staging_key!r}"
            )
        if item.size <= 0:
            raise StagingError("Staging manifest audio sizes must be positive.")
        if not SHA256_PATTERN.fullmatch(item.sha256):
            raise StagingError("Staging manifest contains an invalid audio SHA-256.")
        if item.production_key in seen:
            raise StagingError(f"Duplicate production audio key: {item.production_key}")
        seen.add(item.production_key)
    if covered_targets != set(manifest.targets):
        raise StagingError("Staging manifest contains a target with no audio items.")


def make_manifest(
    pull_request: int,
    approved_sha: str,
    input_sha256: str,
    targets: Sequence[StagingTarget],
    items: Sequence[StagedAudio],
) -> StagingManifest:
    manifest = StagingManifest(
        pull_request, approved_sha, input_sha256, tuple(targets), tuple(items)
    )
    _validate_manifest(manifest)
    return manifest


def manifest_path(root: Path, manifest: StagingManifest) -> Path:
    return (
        root
        / ".audio-staging"
        / f"pr-{manifest.pull_request}-{manifest.approved_sha}.json"
    )


def write_manifest(root: Path, manifest: StagingManifest) -> Path:
    _validate_manifest(manifest)
    path = manifest_path(root, manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": MANIFEST_VERSION,
        "pull_request": manifest.pull_request,
        "approved_sha": manifest.approved_sha,
        "input_sha256": manifest.input_sha256,
        "targets": [asdict(target) for target in manifest.targets],
        "items": [asdict(item) for item in manifest.items],
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)
    return path


def read_manifest(path: Path) -> StagingManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StagingError(f"Cannot read staging manifest {path}: {error}") from error
    if not isinstance(payload, Mapping) or payload.get("schema_version") != MANIFEST_VERSION:
        raise StagingError(f"Unsupported staging manifest format: {path}")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise StagingError(f"Invalid items in staging manifest: {path}")
    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, list):
        raise StagingError(f"Invalid targets in staging manifest: {path}")
    targets: list[StagingTarget] = []
    for raw_target in raw_targets:
        if not isinstance(raw_target, Mapping):
            raise StagingError(f"Invalid target entry in staging manifest: {path}")
        try:
            targets.append(
                StagingTarget(
                    kind=str(raw_target["kind"]),
                    course=str(raw_target["course"]),
                    source=str(raw_target["source"]),
                    target=str(raw_target["target"]),
                    story_id=(
                        str(raw_target["story_id"])
                        if raw_target.get("story_id") is not None else None
                    ),
                )
            )
        except (KeyError, TypeError, ValueError) as error:
            raise StagingError(f"Invalid target entry in staging manifest: {path}") from error
    items: list[StagedAudio] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, Mapping):
            raise StagingError(f"Invalid audio entry in staging manifest: {path}")
        try:
            items.append(
                StagedAudio(
                    course=str(raw_item["course"]),
                    episode_id=str(raw_item["episode_id"]),
                    file=str(raw_item["file"]),
                    staging_key=str(raw_item["staging_key"]),
                    size=int(raw_item["size"]),
                    sha256=str(raw_item["sha256"]),
                )
            )
        except (KeyError, TypeError, ValueError) as error:
            raise StagingError(f"Invalid audio entry in staging manifest: {path}") from error
    try:
        manifest = StagingManifest(
            pull_request=int(payload["pull_request"]),
            approved_sha=str(payload["approved_sha"]),
            input_sha256=str(payload["input_sha256"]),
            targets=tuple(targets),
            items=tuple(items),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise StagingError(f"Invalid staging manifest metadata: {path}") from error
    _validate_manifest(manifest)
    return manifest


def promote_manifest(
    manifest: StagingManifest,
    storage: StagingStorage,
    root: Path,
    *,
    remove_staging: bool = True,
) -> int:
    """Promote verified staging bytes to production keys without replacing content."""
    _validate_manifest(manifest)
    expected_by_key = {
        item.production_key: (item.size, item.sha256) for item in manifest.items
    }
    production_state = {
        key: storage.digest(key) for key in expected_by_key
    }
    for key, stored in production_state.items():
        if stored is not None and stored != expected_by_key[key]:
            raise StagingError(f"Production object {key} differs from reviewed audio.")
    if all(
        production_state[key] == expected_by_key[key] for key in expected_by_key
    ):
        if remove_staging:
            for item in manifest.items:
                storage.delete(item.staging_key)
        return 0
    if input_fingerprint(root, manifest.targets) != manifest.input_sha256:
        raise StagingError(
            "Source data no longer matches the staged audio; regenerate and review it."
        )
    for item in manifest.items:
        _validate_catalog_entry(root, item)
    promoted = 0
    with tempfile.TemporaryDirectory(prefix="audio-promotion-") as directory:
        temp_root = Path(directory)
        for index, item in enumerate(manifest.items):
            expected = (item.size, item.sha256)
            production = storage.digest(item.production_key)
            if production is not None:
                if production != expected:
                    raise StagingError(
                        f"Production object {item.production_key} differs from reviewed audio."
                    )
            else:
                staging = storage.digest(item.staging_key)
                if staging != expected:
                    raise StagingError(
                        f"Staging object {item.staging_key} is missing or differs from "
                        "the reviewed audio."
                    )
                local_path = temp_root / f"{index}.mp3"
                if not storage.download(item.staging_key, local_path):
                    raise StagingError(f"Cannot download staged audio {item.staging_key}.")
                size, sha256 = _file_digest(local_path)
                if (size, sha256) != expected:
                    raise StagingError(
                        f"Downloaded staging object {item.staging_key} failed verification."
                    )
                storage.put_new(item.production_key, local_path, sha256)
                production = storage.digest(item.production_key)
                if production != expected:
                    raise StagingError(
                        f"Production object {item.production_key} failed verification."
                    )
                promoted += 1
            if remove_staging:
                storage.delete(item.staging_key)
    return promoted


def _file_digest(path: Path) -> tuple[int, str]:
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def promote_all(root: Path, storage: StagingStorage, *, remove_staging: bool = True) -> int:
    total = 0
    manifests = sorted((root / ".audio-staging").glob("*.json"))
    for path in manifests:
        total += promote_manifest(
            read_manifest(path), storage, root, remove_staging=remove_staging
        )
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--storage", default="r2")
    args = parser.parse_args(argv)
    try:
        from audio_publish import DirectoryStorage, R2Storage

        if args.storage == "r2":
            storage: StagingStorage = R2Storage.from_environment()
        else:
            storage = DirectoryStorage(Path(args.storage))
        promoted = promote_all(args.root, storage)
    except StagingError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Promoted {promoted} staged audio object(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
