import argparse
import asyncio
import hashlib
import json
import logging
import math
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal, TypedDict

import edge_tts
from edge_tts.exceptions import NoAudioReceived
from pydub import AudioSegment
from pydub.effects import compress_dynamic_range
from pydub.silence import detect_nonsilent

ROOT = Path(__file__).resolve().parent.parent
Language = Literal["se", "en", "pl"]
LANGUAGES: tuple[Language, ...] = ("se", "pl", "en")
TARGETS: tuple[Language, ...] = ("pl", "en")
VOICES = {
    "se": "sv-SE-SofieNeural",
    "en": "en-GB-SoniaNeural",
    "pl": "pl-PL-ZofiaNeural",
}
RATES = {"se": "-5%", "en": "-5%", "pl": "-15%"}
SAMPLE_RATE = 44100
LEAD_IN_MS = 1000
THINKING_MS = 2000
REPETITION_MS = 2500
VOICE_DBFS = -20.0
TTS_ATTEMPTS = 3
LOGGER = logging.getLogger(__name__)


class Entry(TypedDict):
    id: str
    topic: str
    se: str
    en: str
    pl: str


class Segment(TypedDict):
    text: str
    start_ms: int
    end_ms: int


class EntryTiming(TypedDict):
    id: str
    entry_start_ms: int
    entry_end_ms: int
    target_playbacks: list[Segment]


class TimedEntry(EntryTiming, total=False):
    se: Segment
    pl: Segment
    en: Segment


class Manifest(TypedDict):
    section: str
    source_language: Language
    target_language: Language
    audio_file: str
    total_duration_ms: int
    entries: list[TimedEntry]


def load_topics(path: Path) -> dict[str, list[Entry]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("Transcript must be a nonempty JSON array.")
    topics: dict[str, list[Entry]] = {}
    seen_ids: set[str] = set()
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"Entry {index + 1} must be an object.")
        for key in ("id", "topic", "se", "en", "pl"):
            value = entry.get(key)
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise ValueError(f"Entry {index + 1}: {key} must be nonempty, trimmed text.")
            if key in LANGUAGES and re.search(r"[/()]|\.{3}|…", value):
                raise ValueError(f"Entry {index + 1}: {key} contains speech placeholders.")
        if entry["id"] in seen_ids:
            raise ValueError(f"Entry {index + 1}: duplicate ID {entry['id']!r}.")
        seen_ids.add(entry["id"])
        validated = Entry(
            id=entry["id"], topic=entry["topic"],
            se=entry["se"], en=entry["en"], pl=entry["pl"]
        )
        topics.setdefault(validated["topic"], []).append(validated)
    return topics


def topic_filename(
    topic: str, section_number: int, target: Language, source: Language = "se",
    recorded_at: datetime | None = None,
    double_output: bool = False,
) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_") or "topic"
    timestamp = (recorded_at or datetime.now().astimezone()).strftime("%Y-%m-%d_%H-%M-%S")
    mode = "_double" if double_output else ""
    return f"{section_number:02d}_{slug[:80]}_{source}_{target}{mode}_{timestamp}.mp3"


def speech_text(text: str) -> str:
    return text if text.endswith((".", "!", "?", "…")) else f"{text}."


def clip_path(text: str, lang: Language, cache: Path) -> Path:
    settings = [speech_text(text), lang, VOICES[lang], RATES[lang], "+0Hz"]
    digest = hashlib.sha256(
        json.dumps(settings, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return cache / f"{lang}_{digest}.mp3"


async def generate_clip(text: str, lang: Language, out_path: Path) -> None:
    if out_path.is_file() and out_path.stat().st_size > 0:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, TTS_ATTEMPTS + 1):
        try:
            with tempfile.TemporaryDirectory(dir=out_path.parent) as directory:
                pending = Path(directory) / "clip.mp3"
                communicate = edge_tts.Communicate(
                    text=speech_text(text), voice=VOICES[lang], rate=RATES[lang], pitch="+0Hz"
                )
                await communicate.save(str(pending))
                if not pending.is_file() or pending.stat().st_size == 0:
                    raise NoAudioReceived("TTS returned an empty audio file.")
                pending.replace(out_path)
            return
        except NoAudioReceived as error:
            if attempt == TTS_ATTEMPTS:
                raise RuntimeError(
                    f"Edge TTS returned no audio after {attempt} attempts: "
                    f"language={lang}, voice={VOICES[lang]}, text={text!r}. "
                    "Rerun the command to reuse completed cached clips."
                ) from error
            delay = 2 ** attempt
            LOGGER.warning(
                "Edge TTS returned no audio for %s %r (attempt %s/%s); retrying in %ss.",
                lang, text, attempt, TTS_ATTEMPTS, delay,
            )
            await asyncio.sleep(delay)


def silence(duration_ms: int) -> AudioSegment:
    return AudioSegment.silent(duration=duration_ms, frame_rate=SAMPLE_RATE).set_channels(1)


def prepare_clip(audio: AudioSegment, context: str) -> AudioSegment:
    audio = audio.set_frame_rate(SAMPLE_RATE).set_channels(1).set_sample_width(2)
    ranges = detect_nonsilent(
        audio, min_silence_len=100, silence_thresh=-60, seek_step=1
    )
    if not ranges:
        raise ValueError(f"Empty or silent speech clip: {context}")
    trimmed = audio[max(0, ranges[0][0] - 50):min(len(audio), ranges[-1][1] + 50)]
    if not isinstance(trimmed, AudioSegment):
        raise TypeError(f"Expected an audio segment when trimming {context}")
    audio = trimmed
    # Resampling can lose a frame; align the clip to its rounded millisecond length.
    aligned = audio[:len(audio)]
    if not isinstance(aligned, AudioSegment):
        raise TypeError(f"Expected an audio segment when aligning {context}")
    audio = aligned
    if len(audio) == 0 or audio.rms == 0:
        raise ValueError(f"Empty or silent speech clip: {context}")
    gain = VOICE_DBFS - audio.dBFS
    if audio.max_dBFS + gain > -1.0:
        LOGGER.warning(
            "Compressing high speech peaks before normalization: %s", context
        )
        for _ in range(3):
            audio = compress_dynamic_range(
                audio, threshold=-24.0, ratio=4.0, attack=0.1, release=50.0
            )
            gain = VOICE_DBFS - audio.dBFS
            if audio.max_dBFS + gain <= -1.0:
                break
        else:
            raise ValueError(
                f"Cannot normalize {context} to {VOICE_DBFS} dBFS without exceeding "
                "-1 dBFS peak headroom, even after compression. Check or regenerate this clip."
            )
    return audio.apply_gain(gain)


def append_entry(
    track: AudioSegment,
    item: Entry,
    clips: dict[Language, AudioSegment],
    target: Language,
    source: Language = "se",
    double_output: bool = False,
) -> tuple[AudioSegment, TimedEntry]:
    start = len(track)
    track += clips[source]
    source_end = len(track)
    track += silence(THINKING_MS)
    target_playbacks: list[Segment] = []
    for _ in range(2 if double_output else 1):
        target_start = len(track)
        track += clips[target]
        target_playbacks.append(Segment(
            text=item[target], start_ms=target_start, end_ms=len(track)
        ))
        track += silence(REPETITION_MS)
    timing = TimedEntry(
        id=item["id"],
        entry_start_ms=start,
        entry_end_ms=len(track),
        target_playbacks=target_playbacks,
    )
    timing[source] = Segment(text=item[source], start_ms=start, end_ms=source_end)
    timing[target] = target_playbacks[0]
    return track, timing


def export_section(
    output: Path, tracks: dict[Language, AudioSegment], manifests: dict[Language, Manifest]
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    # Stage all versions before replacing any existing deliverables.
    with tempfile.TemporaryDirectory(dir=output) as directory:
        staging = Path(directory)
        for target in manifests:
            manifest = manifests[target]
            audio_path = staging / manifest["audio_file"]
            with audio_path.open("w+b") as audio_file:
                tracks[target].export(
                    audio_file, format="mp3", bitrate="192k",
                    parameters=["-ar", str(SAMPLE_RATE), "-write_xing", "1"],
                )
            decoded = AudioSegment.from_file(str(audio_path), format="mp3")
            if decoded.frame_rate != SAMPLE_RATE or abs(
                len(decoded) - manifest["total_duration_ms"]
            ) > 1:
                raise RuntimeError(f"Exported audio does not match timing: {audio_path.name}")
            audio_path.with_suffix(".json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        for target in manifests:
            name = manifests[target]["audio_file"]
            (staging / name).replace(output / name)
            metadata_name = Path(name).with_suffix(".json").name
            (staging / metadata_name).replace(output / metadata_name)


async def build_audio_tracks(
    transcript: Path = ROOT / "course_transcript.json",
    output: Path = ROOT / "output",
    cache: Path = ROOT / ".audio_cache",
    topic: str | None = None,
    max_duration_seconds: float | None = None,
    source: Language = "se",
    targets: tuple[Language, ...] | None = None,
    double_output: bool = False,
) -> None:
    if source not in LANGUAGES:
        raise ValueError(f"Unsupported source language: {source!r}")
    if targets is None:
        targets = tuple(lang for lang in LANGUAGES if lang != source)
    if not targets or any(lang not in LANGUAGES for lang in targets):
        raise ValueError("Select at least one supported target language: se, en, pl.")
    if source in targets or len(set(targets)) != len(targets):
        raise ValueError("Targets must be unique and different from the source language.")
    selected_languages = (source, *targets)
    topics = load_topics(transcript)
    if topic is not None and topic not in topics:
        raise ValueError(f"Unknown topic {topic!r}. Available topics: {', '.join(topics)}")
    if max_duration_seconds is not None and (
        not math.isfinite(max_duration_seconds) or max_duration_seconds <= 0
    ):
        raise ValueError("Maximum duration must be a finite positive number of seconds.")
    limit_ms = (
        math.floor(max_duration_seconds * 1000)
        if max_duration_seconds is not None else None
    )
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError(
            "Install ffmpeg and ffprobe before rendering (macOS: brew install ffmpeg)."
        )
    output.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    recorded_at = datetime.now().astimezone()
    for section_number, (title, items) in enumerate(topics.items(), start=1):
        if topic is not None and title != topic:
            continue
        print(f"Rendering topic: {title}...", flush=True)
        tracks: dict[Language, AudioSegment] = {
            target: silence(LEAD_IN_MS) for target in targets
        }
        manifests: dict[Language, Manifest] = {
            target: Manifest(
                section=title,
                source_language=source,
                target_language=target,
                audio_file=topic_filename(
                    title, section_number, target, source, recorded_at, double_output
                ),
                total_duration_ms=LEAD_IN_MS,
                entries=[],
            )
            for target in targets
        }
        for index, item in enumerate(items, start=1):
            print(f"  Entry {index}/{len(items)}", flush=True)
            clips: dict[Language, AudioSegment] = {}
            for lang in selected_languages:
                text = item[lang]
                path = clip_path(text, lang, cache)
                await generate_clip(text, lang, path)
                audio = AudioSegment.from_file(str(path), format="mp3")
                clips[lang] = prepare_clip(audio, str(path))
            candidates: dict[Language, tuple[AudioSegment, TimedEntry]] = {
                target: append_entry(
                    tracks[target], item, clips, target, source, double_output
                )
                for target in targets
            }
            if limit_ms is not None and any(
                len(track) > limit_ms for track, _ in candidates.values()
            ):
                if not manifests[targets[0]]["entries"]:
                    raise ValueError(
                        f"Maximum duration is too short for the first entry in {title!r}."
                    )
                print("  Preview limit reached; keeping complete entries in all selected tracks.")
                break
            for target, (track, timing) in candidates.items():
                tracks[target] = track
                manifests[target]["entries"].append(timing)
                manifests[target]["total_duration_ms"] = len(track)
        export_section(output, tracks, manifests)
        for target in targets:
            manifest = manifests[target]
            print(
                f"Finished: {output / manifest['audio_file']} "
                f"({manifest['total_duration_ms'] / 1000:.2f}s, "
                f"{len(manifest['entries'])} entries)",
                flush=True,
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build course audio for any pair of transcript languages: se, en, pl."
    )
    parser.add_argument("--transcript", type=Path, default=ROOT / "course_transcript.json")
    parser.add_argument("--output", type=Path, default=ROOT / "output")
    parser.add_argument("--cache", type=Path, default=ROOT / ".audio_cache")
    parser.add_argument("--topic", help="Render only this exact topic title.")
    parser.add_argument(
        "--double-output", action="store_true",
        help="Play each target phrase twice, with a 2.5-second pause after each playback.",
    )
    parser.add_argument(
        "--source", choices=LANGUAGES, default="se",
        help="Prompt language (default: se).",
    )
    parser.add_argument(
        "--target", choices=LANGUAGES, nargs="+", metavar="LANG",
        help="One or more answer languages (default: all except the source).",
    )
    parser.add_argument(
        "--max-duration", type=float, metavar="SECONDS",
        help="Preview cap per track, including pauses. Keeps the same complete entries "
             "in all selected versions; does not pad or truncate speech.",
    )
    parser.add_argument("--list-topics", action="store_true", help="List topics without using TTS.")
    args = parser.parse_args()
    if args.list_topics:
        for topic, entries in load_topics(args.transcript).items():
            print(f"{topic}: {len(entries)} entries")
        return
    asyncio.run(build_audio_tracks(
        args.transcript, args.output, args.cache, args.topic, args.max_duration,
        source=args.source, targets=tuple(args.target) if args.target is not None else None,
        double_output=args.double_output,
    ))


if __name__ == "__main__":
    main()
