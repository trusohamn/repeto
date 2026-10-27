import asyncio
import importlib.util
import json
import math
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydub import AudioSegment
from pydub.generators import Sine
from pydub.utils import mediainfo_json

SCRIPT = Path(__file__).resolve().parents[1] / "code" / "transcription.py"
SPEC = importlib.util.spec_from_file_location("transcription", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


def tone(duration=200):
    return Sine(440, sample_rate=24000).to_audio_segment(
        duration=duration
    ).apply_gain(-10)


def entry(topic="Greetings", identifier="phrase_000001"):
    return {"id": identifier, "topic": topic, "se": "Hej!", "en": "Hi!", "pl": "Cześć!"}


class RendererTests(unittest.TestCase):
    def test_real_transcript(self):
        topics = renderer.load_topics(renderer.ROOT / "course_transcript.json")
        self.assertEqual(len(topics), 30)
        self.assertGreater(sum(map(len, topics.values())), 0)

    def test_safe_numbered_filenames(self):
        self.assertEqual(
            renderer.topic_filename(
                "Greetings", 1, "pl", "en", datetime(2026, 10, 27, 11, 18, 30),
                double_output=True,
            ),
            "01_greetings_en_pl_double_2026-10-27_11-18-30.mp3",
        )
        self.assertEqual(
            renderer.topic_filename(
                "Greetings", 1, "pl", recorded_at=datetime(2026, 10, 27, 11, 18, 30)
            ),
            "01_greetings_se_pl_2026-10-27_11-18-30.mp3",
        )
        titles = ["I want / I need", "../Greetings?", "A/B", "A B", "???"]
        names = [
            renderer.topic_filename(title, index, "pl")
            for index, title in enumerate(titles, start=1)
        ]
        self.assertEqual(len(set(names)), len(names))
        for name in names:
            self.assertRegex(name, r"^[a-z0-9_-]+\.mp3$")

    def test_validation(self):
        invalid = [
            [], {}, [None], [{"topic": "Test"}], [dict(entry(), se="")],
            [dict(entry(), se=" Hej!")], [dict(entry(), se=42)],
            [dict(entry(), se="Hej / hej")], [dict(entry(), en="Hello...")],
            [dict(entry(), pl="Cześć (hej)")],
            [dict(entry(), id="")], [dict(entry(), id=None)],
            [entry(), entry("Numbers")],
            [{key: value for key, value in entry().items() if key != "id"}],
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transcript.json"
            for value in invalid:
                with self.subTest(value=value):
                    path.write_text(json.dumps(value), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        renderer.load_topics(path)

    def test_grouping_preserves_entry_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transcript.json"
            path.write_text(json.dumps([
                entry("Greetings"), entry("Numbers", "phrase_000002"),
                dict(entry(identifier="phrase_000003"), se="Hejdå!")
            ]), encoding="utf-8")
            topics = renderer.load_topics(path)
            self.assertEqual(list(topics), ["Greetings", "Numbers"])
            self.assertEqual([x["se"] for x in topics["Greetings"]], ["Hej!", "Hejdå!"])
            self.assertEqual(
                [x["id"] for x in topics["Greetings"]],
                ["phrase_000001", "phrase_000003"],
            )

    def test_cache_settings(self):
        original = renderer.clip_path("Hej!", "se", Path("cache"))
        self.assertEqual(original, renderer.clip_path("Hej!", "se", Path("cache")))
        self.assertNotEqual(original, renderer.clip_path("Hej.", "se", Path("cache")))
        with patch.dict(renderer.RATES, {"se": "-10%"}):
            self.assertNotEqual(original, renderer.clip_path("Hej!", "se", Path("cache")))
        with patch.dict(renderer.VOICES, {"se": "different-voice"}):
            self.assertNotEqual(original, renderer.clip_path("Hej!", "se", Path("cache")))

    def test_clip_cache_and_voice_configuration(self):
        async def save(path):
            Path(path).write_bytes(b"speech")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp3"
            with patch.object(renderer.edge_tts, "Communicate") as tts, \
                 patch.object(renderer.asyncio, "sleep", new_callable=AsyncMock):
                tts.return_value.save = AsyncMock(side_effect=save)
                asyncio.run(renderer.generate_clip("Cześć!", "pl", path))
                asyncio.run(renderer.generate_clip("Cześć!", "pl", path))
                tts.assert_called_once_with(
                    text="Cześć!", voice="pl-PL-ZofiaNeural", rate="-15%", pitch="+0Hz"
                )
                self.assertEqual(path.read_bytes(), b"speech")

    def test_unpunctuated_vocabulary_has_sentence_boundary_for_tts(self):
        async def save(path):
            Path(path).write_bytes(b"speech")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp3"
            with patch.object(renderer.edge_tts, "Communicate") as tts:
                tts.return_value.save = AsyncMock(side_effect=save)
                asyncio.run(renderer.generate_clip("Kanin", "se", path))
                tts.assert_called_once_with(
                    text="Kanin.", voice="sv-SE-SofieNeural", rate="-5%", pitch="+0Hz"
                )
        for text in ("Hej!", "Varför?", "Hej."):
            self.assertEqual(renderer.speech_text(text), text)
        self.assertEqual(
            renderer.clip_path("Kanin", "se", Path("cache")),
            renderer.clip_path("Kanin.", "se", Path("cache")),
        )

    def test_failed_or_empty_tts_does_not_publish_partial_clip(self):
        async def fail(path):
            Path(path).write_bytes(b"partial")
            raise ConnectionError("Offline")

        for save, error in [
            (AsyncMock(side_effect=fail), ConnectionError),
            (AsyncMock(), RuntimeError),
        ]:
            with self.subTest(error=error), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "clip.mp3"
                with patch.object(renderer.edge_tts, "Communicate") as tts, \
                     patch.object(renderer.asyncio, "sleep", new_callable=AsyncMock):
                    tts.return_value.save = save
                    with self.assertRaises(error):
                        asyncio.run(renderer.generate_clip("Hej!", "se", path))
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_no_audio_retries_with_fresh_requests_and_clean_staging(self):
        paths = []

        async def save(path):
            paths.append(Path(path))
            if len(paths) < 3:
                Path(path).write_bytes(b"partial")
                raise renderer.NoAudioReceived("No audio")
            Path(path).write_bytes(b"complete")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp3"
            with patch.object(renderer.edge_tts, "Communicate") as tts, \
                 patch.object(renderer.asyncio, "sleep", new_callable=AsyncMock) as sleep, \
                 self.assertLogs(renderer.LOGGER, level="WARNING") as logs:
                tts.return_value.save = AsyncMock(side_effect=save)
                asyncio.run(renderer.generate_clip("Fem", "se", path))
            self.assertEqual(tts.call_count, 3)
            self.assertEqual([x.args[0] for x in sleep.await_args_list], [2, 4])
            self.assertEqual(len(logs.output), 2)
            self.assertEqual(path.read_bytes(), b"complete")
            self.assertEqual(len(set(paths)), 3)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_no_audio_exhaustion_reports_context_and_leaves_no_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp3"
            with patch.object(renderer.edge_tts, "Communicate") as tts, \
                 patch.object(renderer.asyncio, "sleep", new_callable=AsyncMock), \
                 self.assertLogs(renderer.LOGGER, level="WARNING"):
                tts.return_value.save = AsyncMock(
                    side_effect=renderer.NoAudioReceived("No audio")
                )
                with self.assertRaisesRegex(RuntimeError, "after 3 attempts.*text='Fem'") as caught:
                    asyncio.run(renderer.generate_clip("Fem", "se", path))
            self.assertIsInstance(caught.exception.__cause__, renderer.NoAudioReceived)
            self.assertEqual(tts.call_count, 3)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_normalization_and_audio_format(self):
        prepared = renderer.prepare_clip(tone().set_channels(2), "test")
        self.assertEqual(prepared.frame_rate, 44100)
        self.assertEqual(prepared.channels, 1)
        self.assertEqual(prepared.sample_width, 2)
        self.assertAlmostEqual(prepared.dBFS, -20.0, delta=0.01)
        self.assertLessEqual(prepared.max_dBFS, -1.0)

    def test_tts_padding_is_trimmed_before_normalization(self):
        speech = tone(350)
        padded = renderer.silence(275) + speech + renderer.silence(1250)
        prepared = renderer.prepare_clip(padded, "padded greeting")
        self.assertAlmostEqual(prepared.dBFS, -20.0, delta=0.01)
        self.assertGreaterEqual(len(prepared), 440)
        self.assertLessEqual(len(prepared), 460)
        self.assertGreater(prepared[50:350].rms, 0)
        self.assertLessEqual(prepared.max_dBFS, -1.0)

    def test_high_peak_speech_is_compressed_before_normalization(self):
        speech = (
            tone(300).apply_gain(-18)
            + tone(5).fade_in(2).fade_out(2)
            + tone(300).apply_gain(-18)
        )
        with self.assertLogs(renderer.LOGGER, level="WARNING"):
            prepared = renderer.prepare_clip(speech, "high peak speech")
        self.assertEqual(len(prepared), len(speech))
        self.assertAlmostEqual(prepared.dBFS, -20.0, delta=0.01)
        self.assertLessEqual(prepared.max_dBFS, -1.0)

    def test_empty_silent_or_unscalable_clip_is_rejected(self):
        impulse = AudioSegment(
            data=b"\xff\x7f" + b"\x00\x00" * 44100,
            sample_width=2, frame_rate=44100, channels=1,
        )
        for audio in [AudioSegment.empty(), renderer.silence(100), impulse]:
            with self.subTest(audio=audio):
                with self.assertRaises(ValueError):
                    renderer.prepare_clip(audio, "test")

    def test_entry_timestamps_and_no_third_language(self):
        clips = {lang: renderer.prepare_clip(tone(123), lang) for lang in renderer.LANGUAGES}
        for target in renderer.TARGETS:
            with self.subTest(target=target):
                track, timing = renderer.append_entry(
                    renderer.silence(1000), entry(), clips, target
                )
                self.assertEqual(timing["id"], "phrase_000001")
                self.assertEqual(timing["entry_start_ms"], 1000)
                self.assertEqual(timing["se"]["start_ms"], 1000)
                self.assertEqual(timing["se"]["end_ms"], 1123)
                self.assertEqual(timing[target]["start_ms"], 3123)
                self.assertEqual(timing[target]["end_ms"], 3246)
                self.assertEqual(timing["entry_end_ms"], 5746)
                self.assertEqual(len(track), 5746)
                self.assertNotIn("en" if target == "pl" else "pl", timing)
                self.assertEqual(track[:1000].rms, 0)
                self.assertEqual(track[1123:3123].rms, 0)
                self.assertEqual(track[3246:].rms, 0)

    def test_invalid_topic_duration_or_missing_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            for duration in [0, -1, math.inf, math.nan]:
                with self.subTest(duration=duration):
                    with self.assertRaises(ValueError):
                        asyncio.run(renderer.build_audio_tracks(
                            output=output, max_duration_seconds=duration
                        ))
            with self.assertRaisesRegex(ValueError, "Unknown topic"):
                asyncio.run(renderer.build_audio_tracks(output=output, topic="Missing"))
            with patch.object(renderer.shutil, "which", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "ffmpeg"):
                    asyncio.run(renderer.build_audio_tracks(output=output))
            self.assertFalse(output.exists())

    def test_five_minute_cap_keeps_same_complete_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "input.json"
            transcript.write_text(json.dumps([
                entry(identifier=f"phrase_{i:06d}") for i in range(1, 101)
            ]), encoding="utf-8")
            clips = {"se": tone(200), "pl": tone(600), "en": tone(300)}

            def decode(path, **kwargs):
                return clips[Path(path).name.split("_")[0]]

            with patch.object(renderer.shutil, "which", return_value="/mock/ffmpeg"), \
                 patch.object(renderer, "generate_clip", new_callable=AsyncMock), \
                 patch.object(AudioSegment, "from_file", side_effect=decode), \
                 patch.object(renderer, "export_section") as export:
                asyncio.run(renderer.build_audio_tracks(
                    transcript, root / "output", root / "cache",
                    max_duration_seconds=300,
                ))
            _, tracks, manifests = export.call_args.args
            self.assertEqual(len(manifests["pl"]["entries"]), 56)
            self.assertEqual(len(manifests["en"]["entries"]), 56)
            self.assertEqual(len(tracks["pl"]), 297800)
            for target in renderer.TARGETS:
                self.assertLessEqual(len(tracks[target]), 300000)
                self.assertEqual(
                    manifests[target]["entries"][-1]["entry_end_ms"], len(tracks[target])
                )
            self.assertEqual(
                [x["id"] for x in manifests["pl"]["entries"]],
                [x["id"] for x in manifests["en"]["entries"]],
            )

    def test_preview_too_short_does_not_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "input.json"
            path.write_text(json.dumps([entry()]), encoding="utf-8")
            with patch.object(renderer.shutil, "which", return_value="/mock/ffmpeg"), \
                 patch.object(renderer, "generate_clip", new_callable=AsyncMock), \
                 patch.object(AudioSegment, "from_file", return_value=tone()), \
                 patch.object(renderer, "export_section") as export:
                with self.assertRaisesRegex(ValueError, "too short"):
                    asyncio.run(renderer.build_audio_tracks(
                        path, root / "output", root / "cache", max_duration_seconds=1
                    ))
                export.assert_not_called()

    def test_all_language_pairs_use_only_selected_clips(self):
        for source in renderer.LANGUAGES:
            for target in renderer.LANGUAGES:
                if source == target:
                    continue
                with self.subTest(source=source, target=target), \
                     tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    transcript = root / "input.json"
                    transcript.write_text(json.dumps([entry()]), encoding="utf-8")
                    with patch.object(renderer.shutil, "which", return_value="/mock/ffmpeg"), \
                         patch.object(renderer, "generate_clip", new_callable=AsyncMock) as synth, \
                         patch.object(AudioSegment, "from_file", return_value=tone()), \
                         patch.object(renderer, "export_section") as export:
                        asyncio.run(renderer.build_audio_tracks(
                            transcript, root / "output", root / "cache",
                            source=source, targets=(target,),
                        ))
                    self.assertEqual(
                        [call.args[1] for call in synth.await_args_list], [source, target]
                    )
                    _, tracks, manifests = export.call_args.args
                    self.assertEqual(list(tracks), [target])
                    manifest = manifests[target]
                    self.assertEqual(manifest["source_language"], source)
                    self.assertEqual(manifest["target_language"], target)
                    self.assertRegex(
                        manifest["audio_file"],
                        rf"^01_greetings_{source}_{target}_\d{{4}}-\d{{2}}-\d{{2}}_\d{{2}}-\d{{2}}-\d{{2}}\.mp3$",
                    )
                    timing = manifest["entries"][0]
                    self.assertEqual(timing["id"], entry()["id"])
                    self.assertEqual(timing[source]["text"], entry()[source])
                    self.assertEqual(timing[target]["text"], entry()[target])
                    self.assertEqual(
                        timing[target]["start_ms"] - timing[source]["end_ms"], 2000
                    )
                    for lang in set(renderer.LANGUAGES) - {source, target}:
                        self.assertNotIn(lang, timing)

    def test_invalid_language_selections_are_rejected(self):
        for targets in [(), ("en", "en"), ("se",)]:
            with self.subTest(targets=targets):
                with self.assertRaises(ValueError):
                    asyncio.run(renderer.build_audio_tracks(targets=targets))

    def test_cli_language_selection(self):
        with patch.object(sys, "argv", [
            "transcription.py", "--source", "en", "--target", "pl",
            "--topic", "Greetings", "--max-duration", "300",
        ]), patch.object(renderer, "build_audio_tracks", new_callable=AsyncMock) as build:
            renderer.main()
        build.assert_awaited_once()
        call = build.await_args
        assert call is not None
        self.assertEqual(call.kwargs, {
            "source": "en", "targets": ("pl",), "double_output": False,
        })

    def test_cli_double_output(self):
        with patch.object(sys, "argv", [
            "transcription.py", "--source", "en", "--target", "pl", "--double-output",
        ]), patch.object(renderer, "build_audio_tracks", new_callable=AsyncMock) as build:
            renderer.main()
        call = build.await_args
        assert call is not None
        self.assertTrue(call.kwargs["double_output"])

    def test_double_output_timing_all_language_pairs(self):
        clips = {lang: renderer.prepare_clip(tone(200), lang) for lang in renderer.LANGUAGES}
        for source in renderer.LANGUAGES:
            for target in renderer.LANGUAGES:
                if source == target:
                    continue
                for double in (False, True):
                    with self.subTest(source=source, target=target, double=double):
                        track, timing = renderer.append_entry(
                            renderer.silence(1000), entry(), clips, target, source, double
                        )
                        playbacks = timing["target_playbacks"]
                        self.assertEqual(len(playbacks), 2 if double else 1)
                        self.assertEqual(timing[target], playbacks[0])
                        self.assertEqual(timing[source]["start_ms"], 1000)
                        self.assertEqual(timing[source]["end_ms"], 1200)
                        cursor = 3200
                        for playback in playbacks:
                            self.assertEqual(playback, {
                                "text": entry()[target],
                                "start_ms": cursor, "end_ms": cursor + 200,
                            })
                            self.assertGreater(track[cursor:cursor + 200].rms, 0)
                            self.assertEqual(track[cursor + 200:cursor + 2700].rms, 0)
                            cursor += 2700
                        self.assertEqual(timing["entry_end_ms"], cursor)
                        self.assertEqual(len(track), cursor)

    def test_double_output_cap_includes_second_playback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "input.json"
            transcript.write_text(json.dumps([
                entry(), entry(identifier="phrase_000002"),
            ]), encoding="utf-8")
            with patch.object(renderer.shutil, "which", return_value="/mock/ffmpeg"), \
                 patch.object(renderer, "generate_clip", new_callable=AsyncMock), \
                 patch.object(AudioSegment, "from_file", return_value=tone(200)), \
                 patch.object(renderer, "export_section") as export:
                asyncio.run(renderer.build_audio_tracks(
                    transcript, root / "output", root / "cache",
                    max_duration_seconds=15, source="en", targets=("pl", "se"),
                    double_output=True,
                ))
            _, tracks, manifests = export.call_args.args
            for target in ("pl", "se"):
                self.assertIn(f"_en_{target}_double_", manifests[target]["audio_file"])
                self.assertEqual(len(tracks[target]), 8600)
                self.assertEqual(len(manifests[target]["entries"]), 1)
                self.assertEqual(len(manifests[target]["entries"][0]["target_playbacks"]), 2)

    def test_last_phrase_failure_publishes_no_topic_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "input.json"
            transcript.write_text(json.dumps([
                entry(), dict(entry(identifier="phrase_000002"), en="Goodbye!"),
            ]), encoding="utf-8")
            output = root / "output"
            output.mkdir()
            existing = output / "previous.mp3"
            existing.write_bytes(b"previous successful topic")

            async def synthesize(text, lang, path):
                if text == "Goodbye!" and lang == "en":
                    raise RuntimeError("Last phrase failed")

            with patch.object(renderer.shutil, "which", return_value="/mock/ffmpeg"), \
                 patch.object(renderer, "generate_clip", side_effect=synthesize), \
                 patch.object(AudioSegment, "from_file", return_value=tone()), \
                 patch.object(renderer, "export_section") as export:
                with self.assertRaisesRegex(RuntimeError, "Last phrase failed"):
                    asyncio.run(renderer.build_audio_tracks(
                        transcript, output, root / "cache",
                    ))
                export.assert_not_called()
            self.assertEqual(list(output.iterdir()), [existing])
            self.assertEqual(existing.read_bytes(), b"previous successful topic")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_real_mp3_export_manifests_and_preservation_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "input.json"
            transcript.write_text(json.dumps([
                entry("Unused", "phrase_000003"), entry("Greetings"),
                dict(entry(identifier="phrase_000002"), se="Hejdå!")
            ]), encoding="utf-8")

            async def synthesize(text, lang, path):
                with path.open("w+b") as audio_file:
                    tone(500).export(audio_file, format="mp3")

            output = root / "output"
            with patch.object(renderer, "generate_clip", side_effect=synthesize):
                asyncio.run(renderer.build_audio_tracks(
                    transcript, output, root / "cache", topic="Greetings"
                ))
            self.assertEqual(len(list(output.iterdir())), 4)
            manifests = {}
            for target in renderer.TARGETS:
                audio_path = next(output.glob(f"02_greetings_se_{target}_*.mp3"))
                manifest = json.loads(audio_path.with_suffix(".json").read_text())
                manifests[target] = manifest
                self.assertEqual(
                    [x["id"] for x in manifest["entries"]],
                    ["phrase_000001", "phrase_000002"],
                )
                self.assertEqual(manifest["audio_file"], audio_path.name)
                self.assertEqual(manifest["target_language"], target)
                audio = AudioSegment.from_file(str(audio_path), format="mp3")
                info = mediainfo_json(str(audio_path))["streams"][0]
                self.assertEqual(int(info["sample_rate"]), 44100)
                self.assertEqual(int(info["bit_rate"]), 192000)
                self.assertLessEqual(abs(len(audio) - manifest["total_duration_ms"]), 1)
                cursor = 1000
                for timing in manifest["entries"]:
                    self.assertEqual(timing["entry_start_ms"], cursor)
                    self.assertEqual(timing["se"]["start_ms"], cursor)
                    self.assertEqual(timing[target]["start_ms"] - timing["se"]["end_ms"], 2000)
                    self.assertEqual(timing["entry_end_ms"] - timing[target]["end_ms"], 2500)
                    for lang in ["se", target]:
                        segment = timing[lang]
                        self.assertEqual(set(segment), {"text", "start_ms", "end_ms"})
                        decoded_clip = audio[segment["start_ms"]:segment["end_ms"]]
                        self.assertAlmostEqual(decoded_clip.dBFS, -20.0, delta=0.5)
                    cursor = timing["entry_end_ms"]
                self.assertEqual(cursor, len(audio))
            self.assertEqual(
                [x["id"] for x in manifests["pl"]["entries"]],
                [x["id"] for x in manifests["en"]["entries"]],
            )
            originals = {path.name: path.read_bytes() for path in output.iterdir()}
            with patch.object(AudioSegment, "export", side_effect=RuntimeError("Export failed")):
                with self.assertRaisesRegex(RuntimeError, "Export failed"):
                    renderer.export_section(
                        output,
                        {target: tone(500) for target in renderer.TARGETS},
                        manifests,
                    )
            self.assertEqual(
                {path.name: path.read_bytes() for path in output.iterdir()}, originals
            )
            recreated = root / "removed-output"
            renderer.export_section(recreated, {
                target: AudioSegment.from_file(output / manifests[target]["audio_file"])
                for target in renderer.TARGETS
            }, manifests)
            self.assertEqual(len(list(recreated.iterdir())), 4)
            encode = AudioSegment.export
            calls = 0

            def fail_second(audio, *args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("Second track failed")
                return encode(audio, *args, **kwargs)

            tracks = {
                target: AudioSegment.from_file(output / manifests[target]["audio_file"])
                for target in renderer.TARGETS
            }
            with patch.object(AudioSegment, "export", new=fail_second):
                with self.assertRaisesRegex(RuntimeError, "Second track failed"):
                    renderer.export_section(
                        output,
                        tracks,
                        manifests,
                    )
            self.assertEqual(calls, 2)
            self.assertEqual(
                {path.name: path.read_bytes() for path in output.iterdir()}, originals
            )


if __name__ == "__main__":
    unittest.main()
