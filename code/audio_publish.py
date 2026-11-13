"""Publish episode MP3s to Cloudflare R2 and record verified metadata in course.json.

Storage keys mirror the GitHub Pages paths (``<course>/audio/<file>``) and are
never overwritten: identical audio is reused, different audio is refused.
After upload, the stored bytes are downloaded and compared with the local file
before ``bytes`` and ``sha256`` are written to the episode.  Feeds then link
those episodes to R2 (see ``podcast.build_feed``).

Use ``--storage DIR`` to rehearse locally without credentials; ``--storage r2``
reads ``R2_ACCOUNT_ID``, ``R2_ACCESS_KEY_ID``, ``R2_SECRET_ACCESS_KEY`` and
``R2_BUCKET`` from the environment.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parents[1]
CHUNK = 1024 * 1024
CACHE_CONTROL = "public, max-age=31536000, immutable"


def _load_podcast() -> Any:
    spec = importlib.util.spec_from_file_location("podcast", ROOT / "code" / "podcast.py")
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load code/podcast.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


podcast = _load_podcast()


class PublishError(RuntimeError):
    pass


class Storage(Protocol):
    def digest(self, key: str) -> tuple[int, str] | None:
        """Return (size, SHA-256) of the stored bytes, or None if the key is absent."""
        ...

    def put_new(self, key: str, path: Path, sha256: str) -> bool:
        """Store a file only if the key is absent; return False if it already exists."""
        ...


def _hash_chunks(chunks: Iterable[bytes]) -> tuple[int, str]:
    digest, size = hashlib.sha256(), 0
    for chunk in chunks:
        digest.update(chunk)
        size += len(chunk)
    return size, digest.hexdigest()


def _read_file(path: Path) -> Iterator[bytes]:
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            yield chunk


def file_digest(path: Path) -> tuple[int, str]:
    return _hash_chunks(_read_file(path))


class DirectoryStorage:
    """Local stand-in for R2, used for rehearsals and tests."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, key: str) -> Path:
        path = (self.directory / key).resolve()
        if not path.is_relative_to(self.directory.resolve()):
            raise PublishError(f"Unsafe storage key: {key}")
        return path

    def digest(self, key: str) -> tuple[int, str] | None:
        path = self._path(key)
        return file_digest(path) if path.is_file() else None

    def put_new(self, key: str, path: Path, sha256: str) -> bool:
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("xb") as handle:
                for chunk in _read_file(path):
                    handle.write(chunk)
        except FileExistsError:
            return False
        return True


class R2Storage:
    def __init__(self, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    @classmethod
    def from_environment(cls) -> "R2Storage":
        names = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
        missing = [name for name in names if not os.environ.get(name)]
        if missing:
            raise PublishError(f"Missing R2 settings: {', '.join(missing)}")
        import boto3
        from botocore.config import Config

        client = boto3.client(
            "s3",
            endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            region_name="auto",
            config=Config(
                retries={"max_attempts": 5, "mode": "standard"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
        return cls(client, os.environ["R2_BUCKET"])

    @staticmethod
    def _error_code(error: Exception) -> str:
        response = getattr(error, "response", None) or {}
        return str(response.get("Error", {}).get("Code", ""))

    def digest(self, key: str) -> tuple[int, str] | None:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except Exception as error:
            if self._error_code(error) in {"NoSuchKey", "404", "NotFound"}:
                return None
            raise
        return _hash_chunks(response["Body"].iter_chunks(CHUNK))

    def put_new(self, key: str, path: Path, sha256: str) -> bool:
        try:
            with path.open("rb") as body:
                self.client.put_object(
                    Bucket=self.bucket, Key=key, Body=body,
                    ContentType="audio/mpeg", CacheControl=CACHE_CONTROL,
                    Metadata={"sha256": sha256}, IfNoneMatch="*",
                )
        except Exception as error:
            if self._error_code(error) in {"PreconditionFailed", "412"}:
                return False
            raise
        return True


@dataclass(frozen=True)
class AudioItem:
    course: Path
    episode_id: str
    file: str
    path: Path
    key: str
    size: int
    sha256: str


def pending_audio(root: Path, paths: Iterable[Path] | None = None) -> list[AudioItem]:
    """List catalog episodes whose local audio still needs publishing.

    With ``paths``, only those MP3s are considered and each must belong to an
    episode.  Already published episodes are skipped when their local copy
    matches the recorded metadata and refused when it differs.
    """
    wanted = None if paths is None else {path.resolve() for path in paths}
    matched: set[Path] = set()
    items = []
    for catalog_path in sorted(root.glob("*/course.json")):
        course = catalog_path.parent
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        for episode in catalog["episodes"]:
            relative = podcast.safe_audio_path(episode["file"])
            path = course / "audio" / Path(*relative.parts)
            if wanted is not None:
                if path.resolve() not in wanted:
                    continue
                matched.add(path.resolve())
            published = podcast.published_audio(episode)
            if published is not None:
                if path.is_file() and file_digest(path) != published:
                    raise PublishError(f"Local audio differs from published metadata: {path}")
                continue
            if not path.is_file():
                if wanted is not None:
                    raise PublishError(f"Missing audio: {path}")
                continue
            size, sha256 = file_digest(path)
            if size == 0:
                raise PublishError(f"Empty audio: {path}")
            items.append(AudioItem(
                course, episode["id"], episode["file"], path,
                podcast.audio_key(course.name, episode["file"]), size, sha256,
            ))
    if wanted is not None and wanted - matched:
        unreferenced = ", ".join(sorted(str(path) for path in wanted - matched))
        raise PublishError(f"Audio is not referenced by any course.json: {unreferenced}")
    return items


def publish(storage: Storage, items: Iterable[AudioItem], log: Any = print) -> None:
    """Upload each item unless identical audio is stored, then verify the stored bytes."""
    for item in items:
        expected = (item.size, item.sha256)
        stored = storage.digest(item.key)
        if stored is None and not storage.put_new(item.key, item.path, item.sha256):
            stored = storage.digest(item.key)
        if stored is not None and stored != expected:
            raise PublishError(f"Different audio is already stored at {item.key}")
        if storage.digest(item.key) != expected:
            raise PublishError(f"Stored audio failed verification: {item.key}")
        log(f"{'Reused' if stored else 'Uploaded'} and verified: {item.key}")


def record(items: Iterable[AudioItem]) -> None:
    """Write verified size and digest into each episode of its course.json."""
    by_course: dict[Path, dict[str, AudioItem]] = {}
    for item in items:
        by_course.setdefault(item.course, {})[item.episode_id] = item
    for course, updates in by_course.items():
        catalog_path = course / "course.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        for episode in catalog["episodes"]:
            item = updates.pop(episode["id"], None)
            if item is None:
                continue
            if episode["file"] != item.file:
                raise PublishError(f"Catalog changed during publishing: {item.episode_id}")
            episode["bytes"] = item.size
            episode["sha256"] = item.sha256
        if updates:
            raise PublishError(f"Episodes disappeared during publishing: {sorted(updates)}")
        catalog_path.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def check_published(storage: Storage, root: Path) -> list[str]:
    """Download every published episode and report missing or different objects."""
    problems = []
    for catalog_path in sorted(root.glob("*/course.json")):
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        for episode in catalog["episodes"]:
            published = podcast.published_audio(episode)
            if published is None:
                continue
            key = podcast.audio_key(catalog_path.parent.name, episode["file"])
            stored = storage.digest(key)
            if stored != published:
                problems.append(f"{'Missing' if stored is None else 'Different'}: {key}")
    return problems


def _storage(value: str) -> Storage:
    return R2Storage.from_environment() if value == "r2" else DirectoryStorage(Path(value))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("plan", "List audio that would be published (no storage access)."),
        ("publish", "Upload, verify and record audio."),
        ("check", "Verify that every published episode is stored unchanged."),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--root", type=Path, default=ROOT / "podcast")
        if name != "check":
            command.add_argument("paths", nargs="*", type=Path,
                                 help="Limit to these MP3s (default: all unpublished).")
        if name != "plan":
            command.add_argument("--storage", required=True,
                                 help='"r2" or a local directory for rehearsals.')
    publish_command = commands.choices["publish"]
    publish_command.add_argument("--remove-local", action="store_true",
                                 help="Delete local MP3s after they are verified and recorded.")
    publish_command.add_argument("--require-audio", action="store_true",
                                 help="Fail when there is nothing to publish.")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            problems = check_published(_storage(args.storage), args.root)
            for problem in problems:
                print(problem, file=sys.stderr)
            return 1 if problems else 0
        items = pending_audio(args.root, args.paths or None)
        if args.command == "plan":
            for item in items:
                print(f"{item.key}\t{item.size}\t{item.sha256}")
            print(f"{len(items)} file(s) to publish.")
            return 0
        if args.require_audio and not items:
            raise PublishError("No audio to publish.")
        publish(_storage(args.storage), items)
        record(items)
        if args.remove_local:
            for item in items:
                item.path.unlink()
        print(f"Published {len(items)} file(s).")
    except (PublishError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
