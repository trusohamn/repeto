"""Validate, render, and package multilingual story courses."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import importlib.util
import json
import logging
import math
import random
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Sequence
from typing import Any
from urllib.parse import quote

from aiohttp import ClientConnectionError
from pydub import AudioSegment
from pydub.generators import Sine

ROOT = Path(__file__).resolve().parents[1]
LANGUAGE_PATTERN = re.compile(r"^[a-z]{2}$")
CHAPTER_PATTERN = re.compile(r"^Rozdział\s+(\d+):\s*(.+?)\s*$")
DEFAULT_VOICES = {
    "pl": "pl-PL-ZofiaNeural",
    "sv": "sv-SE-SofieNeural",
    "en": "en-GB-SoniaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "es": "es-ES-ElviraNeural",
}
DEFAULT_RATES = {"pl": "-15%", "sv": "-15%", "en": "-5%", "ru": "-15%", "es": "-15%"}
DEFAULT_TARGETS = ("pl",)
# Spoken before each chapter title; short bare titles let expressive narrators
# drift into character voices (e.g. "Głos z radia." read as a deep radio voice).
CHAPTER_HEADINGS = {
    "pl": ("Rozdział", ["pierwszy", "drugi", "trzeci", "czwarty", "piąty", "szósty",
                        "siódmy", "ósmy", "dziewiąty", "dziesiąty"]),
    "sv": ("Kapitel", ["ett", "två", "tre", "fyra", "fem", "sex", "sju", "åtta",
                       "nio", "tio"]),
    "en": ("Chapter", ["one", "two", "three", "four", "five", "six", "seven", "eight",
                       "nine", "ten"]),
    "ru": ("Глава", ["первая", "вторая", "третья", "четвёртая", "пятая", "шестая",
                     "седьмая", "восьмая", "девятая", "десятая"]),
    "es": ("Capítulo", ["uno", "dos", "tres", "cuatro", "cinco", "seis",
                       "siete", "ocho", "nueve", "diez"]),
}
SAMPLE_RATE = 44100
BITRATE = "192k"
LOGGER = logging.getLogger(__name__)


def _azure() -> Any:
    path = ROOT / "code/azure_speech.py"
    spec = importlib.util.spec_from_file_location("azure_speech", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load Azure helpers from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _narration_clip(
    ssml: str, cache: Path, key: str, region: str,
) -> AudioSegment:
    azure = _azure()
    digest = hashlib.sha256(
        ("azure:audio-24khz-160kbitrate-mono-mp3:" + ssml).encode("utf-8")
    ).hexdigest()
    path = cache / f"azure_{digest}.mp3"
    if path.is_file():
        audio = AudioSegment.from_file(path)
    else:
        for attempt in range(1, 7):
            try:
                data = await asyncio.to_thread(azure.synthesize, ssml, key, region)
                break
            except azure.AzureSpeechError as error:
                if not error.retryable or attempt == 6:
                    raise
                delay = min(2 ** attempt, 30)
                LOGGER.warning(
                    "Azure narration retry %s/6 in %ss: %s", attempt, delay, error,
                )
                await asyncio.sleep(delay)
        audio = AudioSegment.from_file(io.BytesIO(data), format="mp3")
        if len(audio) == 0 or audio.rms == 0:
            raise RuntimeError("Azure narration is empty or silent.")
        with tempfile.TemporaryDirectory(dir=cache) as directory:
            pending = Path(directory) / "narration.mp3"
            pending.write_bytes(data)
            pending.replace(path)
    if len(audio) == 0 or audio.rms == 0:
        raise RuntimeError(f"Azure narration cache is empty or silent: {path}")
    return audio.set_frame_rate(SAMPLE_RATE).set_channels(1)


def _renderer() -> Any:
    path = ROOT / "code" / "transcription.py"
    spec = importlib.util.spec_from_file_location("course_transcription", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load audio helpers from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_module(name: str) -> Any:
    path = ROOT / "code" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"repeto_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _podcast_builder() -> Any:
    return _load_module("podcast")


def parse_source(path: Path) -> dict[str, Any]:
    """Parse Polish source chapters headed by `Rozdział N: title`."""
    chapters: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    story_title: str | None = None
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line:
            continue
        match = CHAPTER_PATTERN.fullmatch(line)
        if match:
            if current is not None:
                if not current["source_text"]:
                    raise ValueError(f"Chapter {current['chapter_number']} has no text.")
                current["source_text"] = " ".join(current["source_text"])
                chapters.append(current)
            current = {
                "chapter_number": int(match.group(1)),
                "title": match.group(2),
                "source_text": [],
                "source_line": line_number,
            }
        elif current is None:
            if story_title is not None:
                raise ValueError(
                    f"Expected a chapter heading before source text on line {line_number}."
                )
            story_title = line
        else:
            current["source_text"].append(line)
    if current is not None:
        if not current["source_text"]:
            raise ValueError(f"Chapter {current['chapter_number']} has no text.")
        current["source_text"] = " ".join(current["source_text"])
        chapters.append(current)
    if not chapters:
        raise ValueError(f"No chapter headings found in {path}.")
    numbers = [chapter["chapter_number"] for chapter in chapters]
    if numbers != list(range(1, len(chapters) + 1)):
        raise ValueError(f"Chapter numbers must be consecutive from 1; found {numbers}.")
    return {"title": story_title, "chapters": chapters}


def validate_transcript(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Transcript root must be a JSON object.")
    story_id = data.get("story_id")
    if not isinstance(story_id, str) or not re.fullmatch(r"[a-z0-9_-]+", story_id):
        raise ValueError("story_id must contain lowercase letters, digits, _ or -.")
    chapters = data.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("Transcript must contain a nonempty chapters array.")
    story_titles = data.get("titles")
    if story_titles is not None and (
        not isinstance(story_titles, dict)
        or not story_titles
        or any(
            not isinstance(language, str)
            or not LANGUAGE_PATTERN.fullmatch(language)
            or not isinstance(title, str)
            or not title.strip()
            or title != title.strip()
            for language, title in story_titles.items()
        )
    ):
        raise ValueError("Story titles must be a language map of nonempty text.")
    seen_ids: set[int] = set()
    expected_languages: set[str] | None = None
    for chapter_index, chapter in enumerate(chapters, start=1):
        if not isinstance(chapter, dict) or chapter.get("chapter_number") != chapter_index:
            raise ValueError("Chapter numbers must be unique and consecutive from 1.")
        titles = chapter.get("titles")
        if not isinstance(titles, dict) or not titles:
            raise ValueError(f"Chapter {chapter_index}: titles must be a language map.")
        if expected_languages is None:
            expected_languages = set(titles)
        if set(titles) != expected_languages:
            raise ValueError("Every chapter title must use the same language set.")
        for language, title in titles.items():
            if not isinstance(language, str) or not LANGUAGE_PATTERN.fullmatch(language):
                raise ValueError(f"Invalid ISO 639-1 title language: {language!r}")
            if not isinstance(title, str) or not title.strip() or title != title.strip():
                raise ValueError(f"Chapter {chapter_index}: title {language} must be nonempty.")
        chapter_text = chapter.get("chapter_text")
        if not isinstance(chapter_text, dict) or "pl" not in chapter_text:
            raise ValueError(f"Chapter {chapter_index}: chapter_text must include Polish.")
        if not set(chapter_text) <= expected_languages:
            raise ValueError(
                f"Chapter {chapter_index}: chapter_text has languages absent from titles."
            )
        for language, text in chapter_text.items():
            if (
                not isinstance(language, str)
                or not LANGUAGE_PATTERN.fullmatch(language)
                or not isinstance(text, str)
                or not text.strip()
                or text != text.strip()
            ):
                raise ValueError(f"Chapter {chapter_index}: invalid chapter_text for {language}.")
        summary = chapter.get("summary", {})
        if not isinstance(summary, dict) or any(
            language not in expected_languages
            or not isinstance(text, str) or not text.strip() or text != text.strip()
            for language, text in summary.items()
        ):
            raise ValueError(
                f"Chapter {chapter_index}: summary must map known languages to trimmed text."
            )
        for collection_name in ("vocabulary",):
            collection = chapter.get(collection_name)
            if not isinstance(collection, list) or not collection:
                raise ValueError(
                    f"Chapter {chapter_index}: {collection_name} must be a nonempty array."
                )
            for item_index, item in enumerate(collection, start=1):
                location = f"chapter {chapter_index} {collection_name} item {item_index}"
                if not isinstance(item, dict):
                    raise ValueError(f"{location}: item must be an object.")
                identifier = item.get("id")
                if type(identifier) is not int or identifier < 1:
                    raise ValueError(f"{location}: id must be a positive integer.")
                if identifier in seen_ids:
                    raise ValueError(f"{location}: duplicate story-wide id {identifier}.")
                seen_ids.add(identifier)
                texts = item.get("text")
                if not isinstance(texts, dict) or set(texts) != expected_languages:
                    raise ValueError(
                        f"{location}: text must contain exactly {sorted(expected_languages)}."
                    )
                for language, text in texts.items():
                    if not isinstance(text, str) or not text.strip() or text != text.strip():
                        raise ValueError(f"{location}: {language} text must be nonempty and trimmed.")
    if expected_languages is None:
        raise ValueError("Transcript must declare its supported language set.")
    if story_titles is not None and set(story_titles) != expected_languages:
        raise ValueError("Story titles must use the same language set as chapter titles.")
    return data


def load_transcript(transcript_path: Path, source_path: Path) -> dict[str, Any]:
    try:
        data = json.loads(transcript_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot load transcript JSON {transcript_path}: {error}") from error
    validated = validate_transcript(data)
    parsed_source = parse_source(source_path)
    source_chapters = parsed_source["chapters"]
    if parsed_source["title"] is not None and data.get("titles", {}).get("pl") != parsed_source["title"]:
        raise ValueError("Polish story title differs from the source title.")
    if len(source_chapters) != len(validated["chapters"]):
        raise ValueError("Source and translated transcript have different chapter counts.")
    for source, translated in zip(source_chapters, validated["chapters"]):
        number = translated["chapter_number"]
        if source["chapter_number"] != number:
            raise ValueError(f"Source chapter order differs at chapter {number}.")
        if translated["titles"]["pl"] != source["title"]:
            raise ValueError(f"Chapter {number}: Polish title differs from source heading.")
        transcript_text = translated["chapter_text"]["pl"]
        if transcript_text != source["source_text"]:
            raise ValueError(
                f"Chapter {number}: Polish chapter text does not reproduce the source exactly."
            )
    return validated


def _language_key(language: str) -> str:
    return "se" if language == "sv" else language


def _parse_language_settings(values: list[str], option: str) -> dict[str, str]:
    settings: dict[str, str] = {}
    for value in values:
        language, separator, setting = value.partition("=")
        if not separator or not LANGUAGE_PATTERN.fullmatch(language) or not setting:
            raise ValueError(f"{option} expects LANG=VALUE, got {value!r}.")
        settings[language] = setting
    return settings


def _segment(text: str, start: int, end: int) -> dict[str, Any]:
    return {"text": text, "start_ms": start, "end_ms": end}


def _speech_key(
    text: str, language: str, voice: str, rate: str, pitch: str, engine: str = "edge",
) -> str:
    renderer = _renderer()
    synthesis_text = renderer.speech_text(text)
    data = [synthesis_text, language, voice, rate, pitch]
    # Edge keys stay unchanged so existing cached Edge clips remain valid.
    if engine != "edge":
        data.append(engine)
    digest = hashlib.sha256(
        json.dumps(data, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    prefix = f"{language}_" if engine == "edge" else f"{language}_{engine}_"
    return f"{prefix}{digest}.mp3"


async def _clip(
    text: str,
    language: str,
    cache: Path,
    voice: str,
    rate: str,
    pitch: str,
    engine: str = "azure",
) -> AudioSegment:
    renderer = _renderer()
    engine_language = _language_key(language)
    renderer.VOICES[engine_language] = voice
    renderer.RATES[engine_language] = rate
    cache_path = cache / _speech_key(text, language, voice, rate, pitch, engine)
    if not cache_path.is_file():
        for attempt in range(1, 9):
            try:
                await renderer.generate_clip(
                    text, engine_language, cache_path,
                    voice=voice, rate=rate, pitch=pitch, engine=engine,
                )
                break
            except RuntimeError as error:
                if (
                    not isinstance(error.__cause__, renderer.NoAudioReceived)
                    or attempt == 8
                ):
                    raise
                delay = min(10 * attempt, 60)
                LOGGER.warning(
                    "TTS recovery %s/8 for %s %r; retrying in %ss.",
                    attempt, language, text, delay,
                )
                await asyncio.sleep(delay)
            except (TimeoutError, ClientConnectionError) as error:
                if attempt == 8:
                    raise
                delay = min(10 * attempt, 60)
                LOGGER.warning(
                    "Network recovery %s/8 for %s %r (%s); retrying in %ss.",
                    attempt, language, text, error, delay,
                )
                await asyncio.sleep(delay)
    raw = AudioSegment.from_file(str(cache_path), format="mp3")
    return renderer.prepare_clip(raw, str(cache_path))


def _read_chapter_text(chapter: dict[str, Any], language: str) -> str:
    try:
        return chapter["chapter_text"][language]
    except KeyError as error:
        raise ValueError(
            f'Chapter {chapter["chapter_number"]} has no full chapter text in {language}.'
        ) from error


def chapter_heading(chapter: dict[str, Any], language: str) -> str:
    """Return the spoken chapter announcement, e.g. "Rozdział drugi. Głos z radia."."""
    title = f'{chapter["titles"][language]}.'
    if language not in CHAPTER_HEADINGS:
        raise ValueError(f"No spoken chapter heading configured for {language!r}.")
    word, ordinals = CHAPTER_HEADINGS[language]
    number = chapter["chapter_number"]
    if not 1 <= number <= len(ordinals):
        raise ValueError(f"No spoken ordinal for chapter {number} in {language!r}.")
    return f"{word} {ordinals[number - 1]}. {title}"


def _transition_cue() -> AudioSegment:
    first = Sine(523.25, sample_rate=SAMPLE_RATE).to_audio_segment(
        duration=220, volume=-24,
    ).fade_in(20).fade_out(160)
    second = Sine(659.25, sample_rate=SAMPLE_RATE).to_audio_segment(
        duration=320, volume=-24,
    ).fade_in(20).fade_out(240)
    return first + _renderer().silence(80) + second


def _compose_track(
    chapter: dict[str, Any],
    language: str,
    source_language: str,
    practice_clips: dict[int, tuple[AudioSegment, AudioSegment]],
    chapter_clip: AudioSegment,
    lead_in_ms: int,
    thinking_ms: int,
    repetition_ms: int,
    story_title: str | None = None,
    book_intro_clip: AudioSegment | None = None,
    chapter_intro_clip: AudioSegment | None = None,
) -> tuple[AudioSegment, dict[str, Any]]:
    if chapter_intro_clip is None:
        raise ValueError("Each chapter requires a generated chapter title clip.")
    renderer = _renderer()
    track = renderer.silence(lead_in_ms)
    book_introduction = None
    if chapter["chapter_number"] == 1 and story_title:
        if book_intro_clip is None:
            raise ValueError("Chapter 1 book title requires a generated introduction clip.")
        intro_start = len(track)
        track += book_intro_clip
        book_introduction = _segment(f"{story_title}.", intro_start, len(track))
        track += renderer.silence(repetition_ms)
    title_start = len(track)
    track += chapter_intro_clip
    chapter_introduction = _segment(
        chapter_heading(chapter, language), title_start, len(track),
    )
    track += renderer.silence(repetition_ms)
    chapter_text = _read_chapter_text(chapter, language)
    first_reading_start = len(track)
    track += chapter_clip
    first_reading = _segment(chapter_text, first_reading_start, len(track))
    track += renderer.silence(repetition_ms)
    cue = _transition_cue()
    cue_start = len(track)
    track += cue
    transitions = [{
        "kind": "chime", "from": "story", "to": "practice",
        "start_ms": cue_start, "end_ms": len(track),
    }]
    track += renderer.silence(repetition_ms)
    practice_items = list(chapter["vocabulary"])
    shuffle_seed = f'{chapter["chapter_number"]}:{chapter["titles"]["pl"]}'
    random.Random(shuffle_seed).shuffle(practice_items)
    entries: list[dict[str, Any]] = []
    for item in practice_items:
        start = len(track)
        source_clip, target_clip = practice_clips[item["id"]]
        prompt_start = len(track)
        track += source_clip
        prompt = _segment(item["text"][source_language], prompt_start, len(track))
        track += renderer.silence(thinking_ms)
        playbacks = []
        for _ in range(2):
            target_start = len(track)
            track += target_clip
            playbacks.append(_segment(item["text"][language], target_start, len(track)))
            track += renderer.silence(repetition_ms)
        entries.append({
            "id": item["id"],
            "kind": "vocabulary",
            "start_ms": start,
            "end_ms": len(track),
            "prompt_language": source_language,
            "prompt": prompt,
            "target_playbacks": playbacks,
        })
    cue_start = len(track)
    track += cue
    transitions.append({
        "kind": "chime", "from": "practice", "to": "story",
        "start_ms": cue_start, "end_ms": len(track),
    })
    track += renderer.silence(repetition_ms)
    chapter_start = len(track)
    track += chapter_clip
    chapter_end = len(track)
    final_reading = _segment(chapter_text, chapter_start, chapter_end)
    manifest = {
        "chapter_number": chapter["chapter_number"],
        "title": chapter["titles"],
        "source_language": source_language,
        "target_language": language,
        "practice_order": "deterministically_shuffled",
        "sequence": ["story", "practice", "story"],
        "total_duration_ms": len(track),
        "practice": entries,
        "book_introduction": book_introduction,
        "chapter_introduction": chapter_introduction,
        "transitions": transitions,
        "chapter_readings": [first_reading, final_reading],
        "chapter_reading": final_reading,
    }
    return track, manifest


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _export_chapter(
    output: Path,
    tracks: dict[str, AudioSegment],
    manifests: dict[str, dict[str, Any]],
    file_format: str,
    bitrate: str,
    timestamp: str,
) -> dict[str, dict[str, Any]]:
    output.mkdir(parents=True, exist_ok=True)
    staged_results: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix=".story-stage-", dir=output) as temp:
        staging = Path(temp)
        for language, track in tracks.items():
            chapter_number = manifests[language]["chapter_number"]
            suffix = "wav" if file_format == "wav" else "mp3"
            filename = (
                f"{chapter_number:02d}_chapter_{chapter_number:02d}_"
                    f"{manifests[language]['source_language']}_{language}_{timestamp}.{suffix}"
            )
            audio_path = staging / filename
            parameters = ["-ar", str(SAMPLE_RATE)]
            export_options: dict[str, Any] = {"format": file_format}
            if file_format == "mp3":
                export_options["bitrate"] = bitrate
                parameters.extend(["-write_xing", "1"])
            with audio_path.open("w+b") as output_file:
                track.export(output_file, parameters=parameters, **export_options)
            with audio_path.open("rb") as staged_audio:
                decoded = AudioSegment.from_file(staged_audio, format=file_format)
            if decoded.frame_rate != SAMPLE_RATE or abs(
                len(decoded) - manifests[language]["total_duration_ms"]
            ) > 1:
                raise RuntimeError(f"Exported chapter failed timing validation: {filename}")
            manifest_name = Path(filename).with_suffix(".json").name
            complete_manifest = {**manifests[language], "audio_file": filename}
            manifest_path = staging / manifest_name
            _write_json(manifest_path, complete_manifest)
            staged_results[language] = {
                "audio": audio_path,
                "manifest": manifest_path,
                "audio_file": filename,
                "manifest_file": manifest_name,
                "data": complete_manifest,
            }

        replaced: list[tuple[Path, Path | None]] = []
        try:
            for result in staged_results.values():
                for kind in ("audio", "manifest"):
                    staged_path = result[kind]
                    destination = output / result[f"{kind}_file"]
                    backup = None
                    if destination.exists():
                        backup = staging / f"backup-{destination.name}"
                        destination.replace(backup)
                    replaced.append((destination, backup))
                    staged_path.replace(destination)
        except OSError:
            for destination, backup in reversed(replaced):
                if destination.exists():
                    destination.unlink()
                if backup is not None and backup.exists():
                    backup.replace(destination)
            raise

    return {language: result["data"] for language, result in staged_results.items()}


def default_output(transcript_path: Path, source_language: str, targets: Sequence[str]) -> Path:
    return transcript_path.parent / "audio" / "_".join([source_language, *targets])


def _relative_to_root(path: Path) -> str:
    resolved = path.resolve()
    return (
        resolved.relative_to(ROOT).as_posix()
        if resolved.is_relative_to(ROOT) else resolved.as_posix()
    )


def _load_existing_build(path: Path, story_id: str) -> dict[str, Any]:
    if not path.exists():
        return {"story_id": story_id, "chapters": {}, "podcasts": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("story_id") != story_id:
        raise ValueError(f"Existing manifest belongs to another story: {path}")
    if not isinstance(data.get("chapters"), dict):
        raise ValueError(f"Invalid chapters map in {path}")
    return data


async def render_story(args: argparse.Namespace) -> dict[str, Any]:
    transcript = load_transcript(args.transcript, args.source_text)
    available = set(transcript["chapters"][0]["titles"])
    targets = args.target or list(DEFAULT_TARGETS)
    if args.source_language not in available:
        raise ValueError(f"Source language {args.source_language!r} is missing from transcript.")
    if not targets or len(set(targets)) != len(targets):
        raise ValueError("Select one or more distinct target languages.")
    if args.source_language in targets:
        raise ValueError("Source and target languages must differ.")
    missing = (set(targets) | {args.source_language}) - available
    if missing:
        raise ValueError(f"Transcript is missing languages: {', '.join(sorted(missing))}")
    if any(not LANGUAGE_PATTERN.fullmatch(lang) for lang in [args.source_language, *targets]):
        raise ValueError("Language codes must be two-letter ISO 639-1 codes.")
    pauses = (args.lead_in_ms, args.thinking_ms, args.repetition_ms)
    if any(value < 0 for value in pauses):
        raise ValueError("Pause durations must not be negative.")
    if args.max_duration is not None and (
        not math.isfinite(args.max_duration) or args.max_duration <= 0
    ):
        raise ValueError("Maximum duration must be a finite positive number.")
    if args.file_format not in {"mp3", "wav"}:
        raise ValueError(f"Unsupported audio format: {args.file_format}")
    if args.package_podcast and args.file_format != "mp3":
        raise ValueError("Podcast packaging requires MP3 chapter audio.")
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("Install ffmpeg and ffprobe before rendering.")

    voices = {**DEFAULT_VOICES, **_parse_language_settings(args.voice, "--voice")}
    rates = {**DEFAULT_RATES, **_parse_language_settings(args.rate, "--rate")}
    pitches = _parse_language_settings(args.pitch, "--pitch")
    pitch = {language: "+0Hz" for language in available}
    pitch.update(pitches)
    for language in {args.source_language, *targets}:
        if language not in voices:
            raise ValueError(
                f"No voice configured for {language}; pass --voice {language}=VOICE."
            )
        if language not in rates:
            raise ValueError(
                f"No rate configured for {language}; pass --rate {language}=RATE."
            )

    narration: dict[str, dict[str, Any]] = {}
    azure = _azure()
    narration_voices = {
        **azure.NARRATION_VOICES,
        **_parse_language_settings(args.narration_voice, "--narration-voice"),
    }
    narration_rates = {
        lang: "-12%" for lang in targets
    }
    narration_rates.update(_parse_language_settings(args.narration_rate, "--narration-rate"))
    narration_styles: dict[str, str | None] = {
        lang: azure.NARRATION_STYLES.get(lang, "audiobook") for lang in targets
    }
    narration_styles.update(_parse_language_settings(args.narration_style, "--narration-style"))
    azure.load_dotenv(ROOT / ".env", override=False)
    key = azure.os.environ.get("AZURE_SPEECH_KEY", "")
    region = azure.os.environ.get("AZURE_SPEECH_REGION", "")
    if args.narration_engine == "azure":
        for target in targets:
            if target not in narration_voices or target not in azure.LOCALES:
                raise ValueError(f"No Azure narration locale/voice configured for {target}.")
            capabilities = await asyncio.to_thread(
                azure.check_voice, key, region, narration_voices[target],
                narration_styles[target], azure.LOCALES[target],
            )
            narration[target] = {
                "engine": "azure", "voice": narration_voices[target],
                "style": narration_styles[target], "rate": narration_rates[target],
                "locale": azure.LOCALES[target], "capabilities": capabilities,
            }
    direction_map = {}
    directions_path = args.narration_directions
    if directions_path is None and args.narration_engine == "azure":
        candidate = args.transcript.parent / "narration.json"
        if candidate.is_file():
            directions_path = candidate
    if directions_path:
        direction_map = json.loads(directions_path.read_text(encoding="utf-8"))
        if not isinstance(direction_map, dict):
            raise ValueError("Narration directions must map language to chapter number to passages.")
        if args.narration_engine != "azure":
            raise ValueError("Narration directions require --narration-engine azure.")
        chapters_by_number = {
            str(chapter["chapter_number"]): chapter for chapter in transcript["chapters"]
        }
        for language, chapters in direction_map.items():
            if language not in available or not isinstance(chapters, dict):
                raise ValueError(f"Invalid narration direction language/map: {language}")
            for number, passages in chapters.items():
                if number not in chapters_by_number:
                    raise ValueError(f"Unknown narration chapter: {number}")
                if isinstance(passages, str):
                    passages = json.loads(
                        (directions_path.parent / passages).read_text(encoding="utf-8")
                    )
                chapters[number] = azure.validate_passages(
                    passages, _read_chapter_text(chapters_by_number[number], language),
                )
    ssml_by_chapter = {}
    for chapter in transcript["chapters"]:
        for target in targets:
            text = _read_chapter_text(chapter, target)
            if args.narration_engine == "azure":
                passages = direction_map.get(target, {}).get(str(chapter["chapter_number"]))
                ssml_by_chapter[(chapter["chapter_number"], target)] = azure.build_ssml(
                    text, narration_rates[target], 0,
                    voice_name=narration_voices[target], style=narration_styles[target],
                    locale=azure.LOCALES[target],
                    passages=azure.validate_passages(passages, text) if passages is not None else None,
                )

    if args.output is None:
        args.output = default_output(args.transcript, args.source_language, targets)
    args.cache.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S")
    build_path = args.build_manifest
    build = _load_existing_build(build_path, transcript["story_id"])
    previous_settings = build.get("settings")
    if isinstance(previous_settings, dict) and "target_languages" in previous_settings:
        build.setdefault("renders", {}).setdefault(
            "_".join([previous_settings["source_language"], *previous_settings["target_languages"]]),
            previous_settings,
        )
    build["settings"] = {
        "source_language": args.source_language,
        "target_languages": targets,
        "voices": {lang: voices[lang] for lang in {args.source_language, *targets}},
        "rates": {lang: rates[lang] for lang in {args.source_language, *targets}},
        "pitches": {lang: pitch[lang] for lang in {args.source_language, *targets}},
        "format": args.file_format,
        "bitrate": args.bitrate if args.file_format == "mp3" else None,
        "lead_in_ms": args.lead_in_ms,
        "thinking_ms": args.thinking_ms,
        "repetition_ms": args.repetition_ms,
        "practice_order": "deterministically_shuffled",
        "sequence": ["story", "practice", "story"],
        "timestamp": timestamp,
        "narration": narration,
        "narration_engine": args.narration_engine,
        "tts_engine": args.tts_engine,
        "output": _relative_to_root(args.output),
    }
    # One manifest serves every direction: keep other targets' renders intact.
    direction = "_".join([args.source_language, *targets])
    build.setdefault("renders", {})[direction] = build["settings"]
    previous_chapters = build.get("chapters", {})
    build["chapters"] = {}
    for chapter in transcript["chapters"]:
        previous_targets = previous_chapters.get(str(chapter["chapter_number"]), {}).get(
            "targets", {}
        )
        build["chapters"][str(chapter["chapter_number"])] = {
            "titles": chapter["titles"],
            "targets": {
                language: data for language, data in previous_targets.items()
                if language not in targets
            },
        }
    for chapter in transcript["chapters"]:
        chapter_number = chapter["chapter_number"]
        print(
            f'Rendering chapter {chapter_number}: {chapter["titles"]["pl"]}...',
            flush=True,
        )
        practice_items = chapter["vocabulary"]
        clip_cache: dict[tuple[int, str], AudioSegment] = {}
        for item_index, item in enumerate(practice_items, start=1):
            print(f"  Practice item {item_index}/{len(practice_items)}", flush=True)
            for language in [args.source_language, *targets]:
                clip_cache[(item["id"], language)] = await _clip(
                    item["text"][language], language, args.cache,
                    voices[language], rates[language], pitch[language],
                    args.tts_engine,
                )

        tracks: dict[str, AudioSegment] = {}
        manifests: dict[str, dict[str, Any]] = {}
        for target in targets:
            story_title = (
                transcript.get("titles", {}).get(target)
                if chapter_number == 1 else None
            )
            chapter_text = _read_chapter_text(chapter, target)
            if args.narration_engine == "azure":
                chapter_ssml = ssml_by_chapter[(chapter_number, target)]
                chapter_clip = await _narration_clip(chapter_ssml, args.cache, key, region)
                title_ssml = azure.build_ssml(
                    chapter_heading(chapter, target), narration_rates[target], 0,
                    voice_name=narration_voices[target], style=narration_styles[target],
                    locale=azure.LOCALES[target],
                )
                chapter_intro_clip = await _narration_clip(
                    title_ssml, args.cache, key, region,
                )
            else:
                chapter_clip = await _clip(
                    chapter_text, target, args.cache,
                    voices[target], rates[target], pitch[target], "edge",
                )
                chapter_intro_clip = await _clip(
                    chapter_heading(chapter, target), target, args.cache,
                    voices[target], rates[target], pitch[target], "edge",
                )
            book_intro_clip = None
            if story_title:
                if args.narration_engine == "azure":
                    intro_ssml = azure.build_ssml(
                        f"{story_title}.", narration_rates[target], 0,
                        voice_name=narration_voices[target], style=narration_styles[target],
                        locale=azure.LOCALES[target],
                    )
                    book_intro_clip = await _narration_clip(intro_ssml, args.cache, key, region)
                else:
                    book_intro_clip = await _clip(
                        f"{story_title}.", target, args.cache,
                        voices[target], rates[target], pitch[target], "edge",
                    )
            practice_clips = {
                item["id"]: (
                    clip_cache[(item["id"], args.source_language)],
                    clip_cache[(item["id"], target)],
                )
                for item in practice_items
            }
            track, manifest = _compose_track(
                chapter, target, args.source_language, practice_clips, chapter_clip,
                args.lead_in_ms, args.thinking_ms, args.repetition_ms,
                story_title=story_title,
                book_intro_clip=book_intro_clip,
                chapter_intro_clip=chapter_intro_clip,
            )
            manifest["narration"] = (
                {**narration[target], "ssml": chapter_ssml}
                if args.narration_engine == "azure"
                else {"engine": "edge", "voice": voices[target], "rate": rates[target],
                      "pitch": pitch[target]}
            )
            if args.max_duration is not None and len(track) > args.max_duration * 1000:
                raise ValueError(
                    f"Chapter {chapter_number} {target} would take {len(track) / 1000:.1f}s, "
                    f"exceeding --max-duration {args.max_duration}s; no outputs published."
                )
            tracks[target] = track
            manifests[target] = manifest

        files = _export_chapter(
            args.output, tracks, manifests, args.file_format, args.bitrate, timestamp
        )
        build["chapters"][str(chapter_number)]["targets"].update({
                language: {
                    "source_language": args.source_language,
                    "audio_file": data["audio_file"],
                    "manifest_file": Path(data["audio_file"]).with_suffix(".json").name,
                    "total_duration_ms": data["total_duration_ms"],
                    "chapter_reading": data["chapter_reading"],
                    "chapter_introduction": data["chapter_introduction"],
                    "chapter_readings": data["chapter_readings"],
                    "sequence": data["sequence"],
                    "transitions": data["transitions"],
                    "narration": data["narration"],
                }
                for language, data in files.items()
        })
        _write_json(build_path, build)
        for language, data in files.items():
            print(
                f'Finished {language}: {args.output / data["audio_file"]} '
                f'({data["total_duration_ms"] / 1000:.1f}s)',
                flush=True,
            )

    if args.package_podcast:
        package_podcasts(args, transcript, build)
        _write_json(build_path, build)
    return build


def package_podcasts(
    args: argparse.Namespace, transcript: dict[str, Any], build: dict[str, Any]
) -> None:
    if args.podcast_course and not re.fullmatch(r"[a-z0-9-]+", args.podcast_course):
        raise ValueError("--podcast-course must be a lowercase URL-safe course slug.")
    source_language = args.source_language
    story_root = args.transcript.parent.parent
    if not args.podcast_course and not args.email:
        raise ValueError("Podcast packaging requires --email for the public RSS owner contact.")
    podcast_root = args.podcast_root
    if not podcast_root.is_absolute():
        podcast_root = ROOT / podcast_root
    base_url = args.podcast_base_url.rstrip("/")
    if not base_url.startswith("https://"):
        raise ValueError("Podcast hosting requires an HTTPS base URL.")

    builder = _podcast_builder()
    copy = _load_module("descriptions")
    if args.output is None:
        args.output = default_output(
            args.transcript, source_language, build["settings"]["target_languages"]
        )
    feed_catalogs: dict[str, dict[str, Any]] = {}
    for target in build["settings"]["target_languages"]:
        cover_source_language = "se" if source_language == "sv" else source_language
        direction_cover = story_root / f"cover_{cover_source_language}_{target}.jpeg"
        cover = args.cover or next(
            (
                candidate for candidate in (
                    direction_cover, story_root / "cover.jpeg", story_root / "cover.jpg"
                )
                if candidate.is_file()
            ),
            story_root / "cover.jpeg",
        )
        if not cover.is_file():
            raise FileNotFoundError(
                f"Podcast packaging requires the story cover image; not found: {cover}"
            )
        if cover.stat().st_size == 0:
            raise ValueError(f"Empty story cover image: {cover}")
        slug = args.podcast_course or f'{transcript["story_id"]}-{source_language}-{target}'
        course = podcast_root / slug
        audio_dir = course / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        story_titles = transcript.get("titles", transcript["chapters"][0]["titles"])
        target_title = story_titles[target]
        source_title = story_titles[source_language]
        existing_catalog = course / "course.json"
        if args.podcast_course:
            if not existing_catalog.is_file():
                raise FileNotFoundError(
                    f"Existing podcast course catalog not found: {existing_catalog}"
                )
            if builder.find_image(course / "cover.jpeg") is None:
                raise FileNotFoundError(f"Existing podcast cover not found: {course / 'cover.jpeg'}")
            catalog = json.loads(existing_catalog.read_text(encoding="utf-8"))
            if (
                catalog.get("source_language") != source_language
                or catalog.get("target_language") != target
                or catalog.get("language") != source_language
            ):
                raise ValueError(
                    f"Podcast course {slug!r} does not match direction "
                    f"{source_language} to {target}."
                )
            if not isinstance(catalog.get("episodes"), list):
                raise ValueError(f"Podcast course {slug!r} has no valid episodes list.")
        else:
            if not args.email:
                raise ValueError("Podcast packaging requires --email for the public RSS owner contact.")
            course.mkdir(parents=True, exist_ok=True)
            packaged_cover = builder.find_image(course / "cover.jpeg")
            if packaged_cover is not None and packaged_cover.read_bytes() != cover.read_bytes():
                raise FileExistsError(
                    f"Refusing to overwrite a different podcast cover: {packaged_cover}"
                )
            if packaged_cover is None:
                shutil.copyfile(cover, course / "cover.jpeg")
            catalog = {
                "title": f'{story_titles["pl"]} — {source_title} to {target_title}',
                "description": (
                    f'A story course for beginners of all ages: hear each chapter in {target_title}, '
                    f'practice vocabulary with {source_title} prompts, then hear '
                    "the same chapter again. "
                    "Voices are AI-generated."
                ),
                "language": source_language,
                "source_language": source_language,
                "target_language": target,
                "author": args.author,
                "email": args.email,
                "episodes": [],
            }

        relative_cover_name = f'images/stories/{transcript["story_id"]}/cover.jpeg'
        packaged_story_cover = builder.find_image(course / relative_cover_name)
        if (
            packaged_story_cover is not None
            and packaged_story_cover.read_bytes() != cover.read_bytes()
        ):
            raise FileExistsError(
                f"Refusing to overwrite a different story cover: {packaged_story_cover}"
            )
        if packaged_story_cover is None:
            (course / relative_cover_name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cover, course / relative_cover_name)

        episodes = catalog["episodes"]
        previous_by_id = {episode["id"]: episode for episode in episodes}
        story_id_prefix = f'{transcript["story_id"]}:{source_language}:{target}:chapter-'
        previous_story_episodes = [
            episode for episode in episodes
            if isinstance(episode.get("id"), str)
            and episode["id"].startswith(story_id_prefix)
        ]
        if previous_story_episodes:
            story_season = previous_story_episodes[0]["season"]
            if any(episode.get("season") != story_season for episode in previous_story_episodes):
                raise ValueError("Existing story chapters use inconsistent podcast seasons.")
        else:
            existing_seasons = [
                episode.get("season") for episode in episodes
                if type(episode.get("season")) is int and episode["season"] > 0
            ]
            story_season = max(existing_seasons, default=0) + 1 if args.podcast_course else 1

        superseded: list[str] = []
        for chapter in transcript["chapters"]:
            number = chapter["chapter_number"]
            data = build["chapters"][str(number)]["targets"][target]
            audio_name = data["audio_file"]
            audio_source = args.output / audio_name
            relative_audio_name = f'stories/{transcript["story_id"]}/{audio_name}'
            audio_destination = audio_dir / relative_audio_name
            # Packaging moves the render so each episode MP3 exists only once;
            # reruns accept audio that an earlier run already moved.
            if audio_source.is_file():
                if audio_destination.exists():
                    if audio_destination.read_bytes() != audio_source.read_bytes():
                        raise FileExistsError(
                            f"Refusing to overwrite different episode audio: {audio_destination}"
                        )
                    audio_source.unlink()
                else:
                    audio_destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(audio_source, audio_destination)
            elif not audio_destination.is_file():
                raise FileNotFoundError(f"Missing completed story audio: {audio_source}")
            data["packaged_audio"] = (
                audio_destination.relative_to(podcast_root).as_posix()
            )
            episode_id = f'{transcript["story_id"]}:{source_language}:{target}:chapter-{number:02d}'
            previous = previous_by_id.get(episode_id, {})
            if "file" in previous:
                superseded.append(previous["file"])
            episode = {
                "id": episode_id,
                "title": (
                    f'{source_title}: {chapter["titles"][source_language]} — '
                    f'{chapter["titles"][target]}'
                ),
                "file": relative_audio_name,
                "image": relative_cover_name,
                "duration_ms": data["total_duration_ms"],
                "published": previous.get(
                    "published", datetime.now(timezone.utc).isoformat(timespec="seconds")
                ),
                "description": (
                    copy.story_description(
                        target, story_titles, chapter, len(transcript["chapters"]),
                        source=source_language,
                    )
                    if source_language in ("sv", "pl", "en") and target in copy.LANGUAGES
                    else "Listen to the complete chapter in the target language, "
                    "practice vocabulary with native-language prompts, then listen "
                    "to the same chapter again."
                ),
                "season": previous.get("season", story_season),
                "episode": previous.get("episode", number),
            }
            if episode_id in previous_by_id:
                episode_index = next(
                    index for index, existing in enumerate(episodes)
                    if existing["id"] == episode_id
                )
                episodes[episode_index] = episode
            else:
                episodes.append(episode)
                previous_by_id[episode_id] = episode
        _write_json(existing_catalog, catalog)
        if source_language in ("sv", "pl", "en") and target in copy.LANGUAGES:
            catalog = copy.refresh_course(course, {transcript["story_id"]: transcript})
        for path in builder.remove_superseded_audio(course, superseded):
            print(f"Removed superseded audio: {path.relative_to(course)}", flush=True)
            stale_timing = args.output / f"{path.stem}.json"
            if stale_timing.is_file():
                stale_timing.unlink()
        builder.build_feed(course, base_url)
        feed_catalogs[target] = {
            "slug": slug,
            "feed_url": f"{base_url}/{quote(slug)}/feed.xml",
            "episodes": len(catalog["episodes"]),
            "title": catalog["title"],
            "author": catalog["author"],
            "owner_email": catalog["email"],
        }
    script = ROOT / "code" / "podcast.py"
    subprocess.run(
        [sys.executable, str(script), "--root", str(podcast_root), "--base-url", base_url],
        cwd=ROOT,
        check=True,
    )
    build["podcasts"] = {**build.get("podcasts", {}), **feed_catalogs}


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--narration-engine", choices=("azure", "edge"), default="azure")
    parser.add_argument(
        "--tts-engine", choices=("azure", "edge"), default="azure",
        help="Speech service for practice prompts and vocabulary clips (default: azure).",
    )
    parser.add_argument("--narration-voice", action="append", default=[], metavar="LANG=VOICE")
    parser.add_argument("--narration-rate", action="append", default=[], metavar="LANG=RATE")
    parser.add_argument("--narration-style", action="append", default=[], metavar="LANG=STYLE")
    parser.add_argument("--narration-directions", type=Path)
    default_story = ROOT / "courses" / "stories" / "magical_radio"
    parser.add_argument("--transcript", type=Path, default=default_story / "generated/transcript.json")
    parser.add_argument("--source-text", type=Path, default=default_story / "complete/pl.txt")
    parser.add_argument(
        "--output", type=Path,
        help="Render folder; defaults to generated/audio/<source>_<targets> beside the transcript.",
    )
    parser.add_argument("--cache", type=Path, default=ROOT / ".audio_cache")
    parser.add_argument(
        "--build-manifest", type=Path,
        default=default_story / "generated/manifest.json",
    )
    parser.add_argument("--source-language", default="sv")
    parser.add_argument(
        "--target", nargs="+", default=None, metavar="LANG",
        help="Target languages; defaults to pl.",
    )
    parser.add_argument(
        "--voice", action="append", default=[], metavar="LANG=VOICE",
        help="Override the TTS voice for a language (repeatable).",
    )
    parser.add_argument(
        "--rate", action="append", default=[], metavar="LANG=RATE",
        help="Override TTS rate, for example --rate pl=-10%%.",
    )
    parser.add_argument(
        "--pitch", action="append", default=[], metavar="LANG=PITCH",
        help="Override TTS pitch, for example --pitch en=+0Hz.",
    )
    parser.add_argument("--lead-in-ms", type=int, default=1000)
    parser.add_argument("--thinking-ms", type=int, default=2000)
    parser.add_argument("--repetition-ms", type=int, default=2500)
    parser.add_argument("--max-duration", type=float)
    parser.add_argument("--format", dest="file_format", choices=("mp3", "wav"), default="mp3")
    parser.add_argument("--bitrate", default=BITRATE)
    parser.add_argument("--package-podcast", action="store_true")
    parser.add_argument("--cover", type=Path)
    parser.add_argument("--podcast-root", type=Path, default=Path("podcast"))
    parser.add_argument(
        "--podcast-base-url", default="https://trusohamn.github.io/repeto"
    )
    parser.add_argument("--author", default="Repeto")
    parser.add_argument("--email", default="repeto.lingo@gmail.com")
    parser.add_argument(
        "--podcast-course",
        help="Add story chapters to an existing podcast course slug instead of creating a new feed.",
    )
    parser.add_argument("--list", action="store_true", help="Validate and list chapters without TTS.")
    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()
    if args.list:
        transcript = load_transcript(args.transcript, args.source_text)
        for chapter in transcript["chapters"]:
            print(
                f'{chapter["chapter_number"]:02d} {chapter["titles"]["pl"]}: '
                f'{len(chapter["vocabulary"])} vocabulary items, '
                f'{len(chapter["chapter_text"]["pl"])} Polish chapter characters'
            )
        return
    asyncio.run(render_story(args))


if __name__ == "__main__":
    main()
