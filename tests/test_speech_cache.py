import asyncio
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
from pydub.generators import Sine

ROOT = Path(__file__).resolve().parents[1]


def load_renderer(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "code" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


renderer = load_renderer("transcription")
story = load_renderer("story_course")


def mp3_bytes(silent=False, frequency=440):
    audio = (
        AudioSegment.silent(duration=200)
        if silent else Sine(frequency).to_audio_segment(duration=200)
    )
    buffer = io.BytesIO()
    audio.export(buffer, format="mp3")
    return buffer.getvalue()


class FakeSpeechCache:
    def __init__(self, objects=None):
        self.objects = dict(objects or {})
        self.gets = []
        self.puts = []

    def fetch(self, key: str, destination_path: Path) -> bool:
        self.gets.append((key, destination_path))
        if key not in self.objects:
            return False
        destination_path.write_bytes(self.objects[key])
        return True

    def store(self, key: str, source_path: Path) -> None:
        self.puts.append((key, source_path))
        if key in self.objects:
            source_path.write_bytes(self.objects[key])
        else:
            self.objects[key] = source_path.read_bytes()


class RacingSpeechCache(FakeSpeechCache):
    def __init__(self, canonical):
        super().__init__()
        self.canonical = canonical

    def fetch(self, key: str, destination_path: Path) -> bool:
        self.gets.append((key, destination_path))
        self.objects[key] = self.canonical
        return False


class SpeechCacheTests(unittest.TestCase):
    def test_store_race_preserves_canonical_clip_in_practice_and_story(self):
        competing = mp3_bytes(frequency=440)
        canonical = mp3_bytes(frequency=880)
        self.assertNotEqual(canonical, competing)
        azure = story._azure()
        for clip_kind in ("practice", "vocabulary", "narration"):
            for engine in ("edge", "azure"):
                if clip_kind == "narration" and engine == "edge":
                    continue
                with self.subTest(clip_kind=clip_kind, engine=engine), tempfile.TemporaryDirectory() as directory:
                    cache = Path(directory)
                    backend = RacingSpeechCache(canonical)

                    async def save(path):
                        Path(path).write_bytes(competing)

                    with patch.object(story, "_renderer", return_value=renderer), patch.object(
                        story, "_azure", return_value=azure,
                    ), patch.object(renderer, "azure_speech", return_value=azure), patch.object(
                        renderer, "azure_credentials", return_value=("key", "region"),
                    ), patch.object(azure, "synthesize", return_value=competing), patch.object(
                        renderer.edge_tts, "Communicate",
                    ) as edge, patch.dict(renderer.VOICES), patch.dict(renderer.RATES):
                        edge.return_value.save = AsyncMock(side_effect=save)
                        if clip_kind == "practice":
                            path = renderer.clip_path("cat", "en", cache, engine=engine)
                            asyncio.run(renderer.generate_clip(
                                "cat", "en", path, engine=engine, speech_cache=backend,
                            ))
                        elif clip_kind == "vocabulary":
                            audio = asyncio.run(story._clip(
                                "cat", "en", cache, renderer.VOICES["en"], renderer.RATES["en"],
                                "+0Hz", engine, speech_cache=backend,
                            ))
                        else:
                            audio = asyncio.run(story._narration_clip(
                                "SSML", cache, "key", "region", speech_cache=backend,
                            ))
                    self.assertEqual(len(backend.puts), 1)
                    key, path = backend.puts[0]
                    self.assertEqual(backend.gets, [(key, path)])
                    self.assertEqual(backend.objects[key], canonical)
                    self.assertEqual(path.read_bytes(), canonical)
                    if clip_kind != "practice":
                        decoded = AudioSegment.from_file(io.BytesIO(canonical), format="mp3")
                        expected = (
                            renderer.prepare_clip(decoded, "canonical")
                            if clip_kind == "vocabulary"
                            else decoded.set_frame_rate(story.SAMPLE_RATE).set_channels(1)
                        )
                        self.assertEqual(audio.raw_data, expected.raw_data)

    def test_practice_hit_materializes_only_requested_clip_before_early_return(self):
        data = mp3_bytes()
        for engine in ("edge", "azure"):
            with self.subTest(engine=engine), tempfile.TemporaryDirectory() as directory:
                path = renderer.clip_path("Hej!", "se", Path(directory), engine=engine)
                backend = FakeSpeechCache({path.name: data, "unrequested.mp3": data})
                with patch.object(renderer.edge_tts, "Communicate") as edge, patch.object(
                    renderer, "generate_azure_clip", new_callable=AsyncMock,
                ) as azure:
                    asyncio.run(renderer.generate_clip(
                        "Hej!", "se", path, engine=engine, speech_cache=backend,
                    ))
                    asyncio.run(renderer.generate_clip(
                        "Hej!", "se", path, engine=engine, speech_cache=backend,
                    ))
                edge.assert_not_called()
                azure.assert_not_awaited()
                self.assertEqual(backend.gets, [(path.name, path)])
                self.assertEqual(backend.puts, [])
                self.assertEqual(path.read_bytes(), data)
                self.assertEqual(list(Path(directory).iterdir()), [path])
                self.assertGreater(len(AudioSegment.from_file(path)), 0)

    def test_practice_miss_synthesizes_then_stores_finished_clip_for_each_engine(self):
        data = mp3_bytes()

        async def save(path):
            Path(path).write_bytes(data)

        for engine in ("edge", "azure"):
            with self.subTest(engine=engine), tempfile.TemporaryDirectory() as directory:
                path = renderer.clip_path("Hej!", "se", Path(directory), engine=engine)
                backend = FakeSpeechCache()
                azure = renderer.azure_speech()
                with patch.object(renderer.edge_tts, "Communicate") as edge, patch.object(
                    renderer, "azure_credentials", return_value=("key", "region"),
                ), patch.object(azure, "synthesize", return_value=data) as synthesis:
                    edge.return_value.save = AsyncMock(side_effect=save)
                    asyncio.run(renderer.generate_clip(
                        "Hej!", "se", path, engine=engine, speech_cache=backend,
                    ))
                if engine == "edge":
                    edge.return_value.save.assert_awaited_once()
                    synthesis.assert_not_called()
                else:
                    synthesis.assert_called_once()
                    edge.assert_not_called()
                self.assertEqual(backend.gets, [(path.name, path)])
                self.assertEqual(backend.puts, [(path.name, path)])
                self.assertEqual(backend.objects[path.name], data)

    def test_backend_hit_without_materialized_audio_fails_explicitly(self):
        for narration in (False, True):
            with self.subTest(narration=narration), tempfile.TemporaryDirectory() as directory:
                backend = FakeSpeechCache()
                with patch.object(backend, "fetch", return_value=True), patch.object(
                    renderer.edge_tts, "Communicate",
                ) as edge:
                    with self.assertRaisesRegex(RuntimeError, "did not materialize a clip"):
                        if narration:
                            asyncio.run(story._narration_clip(
                                "SSML", Path(directory), "key", "region", speech_cache=backend,
                            ))
                        else:
                            asyncio.run(renderer.generate_clip(
                                "cat", "en", Path(directory) / "clip.mp3", speech_cache=backend,
                            ))
                edge.assert_not_called()
                self.assertEqual(backend.puts, [])

    def test_story_vocabulary_and_edge_narration_use_original_language_keys(self):
        data = mp3_bytes()
        for engine in ("edge", "azure"):
            for hit in (False, True):
                with self.subTest(engine=engine, hit=hit), tempfile.TemporaryDirectory() as directory:
                    cache = Path(directory)
                    key = story._speech_key(
                        "Katten", "sv", "sv-SE-SofieNeural", "-15%", "+2Hz", engine,
                    )
                    backend = FakeSpeechCache({key: data} if hit else {})
                    azure = renderer.azure_speech()

                    async def save(path):
                        Path(path).write_bytes(data)

                    with patch.object(story, "_renderer", return_value=renderer), patch.object(
                        renderer.edge_tts, "Communicate",
                    ) as edge, patch.object(
                        renderer, "azure_credentials", return_value=("key", "region"),
                    ), patch.object(azure, "synthesize", return_value=data) as synthesis, patch.dict(
                        renderer.VOICES,
                    ), patch.dict(renderer.RATES):
                        edge.return_value.save = AsyncMock(side_effect=save)
                        audio = asyncio.run(story._clip(
                            "Katten", "sv", cache, "sv-SE-SofieNeural", "-15%", "+2Hz",
                            engine, speech_cache=backend,
                        ))
                    self.assertEqual(audio.frame_rate, story.SAMPLE_RATE)
                    self.assertEqual(backend.gets, [(key, cache / key)])
                    self.assertEqual(backend.puts, [] if hit else [(key, cache / key)])
                    self.assertTrue(key.startswith("sv_" if engine == "edge" else "sv_azure_"))
                    if hit:
                        edge.assert_not_called()
                        synthesis.assert_not_called()
                    elif engine == "edge":
                        edge.return_value.save.assert_awaited_once()
                    else:
                        synthesis.assert_called_once()

    def test_story_azure_narration_hit_and_miss_use_ssml_key(self):
        data = mp3_bytes()
        azure = story._azure()
        for ssml in ("first SSML", "changed SSML"):
            for hit in (False, True):
                with self.subTest(ssml=ssml, hit=hit), tempfile.TemporaryDirectory() as directory:
                    digest = hashlib.sha256(
                        ("azure:audio-24khz-160kbitrate-mono-mp3:" + ssml).encode("utf-8")
                    ).hexdigest()
                    key = f"azure_{digest}.mp3"
                    path = Path(directory) / key
                    backend = FakeSpeechCache({key: data} if hit else {})
                    with patch.object(story, "_azure", return_value=azure), patch.object(
                        azure, "synthesize", return_value=data,
                    ) as synthesis:
                        audio = asyncio.run(story._narration_clip(
                            ssml, Path(directory), "credential", "region",
                            speech_cache=backend,
                        ))
                    self.assertGreater(len(audio), 0)
                    self.assertEqual(backend.gets, [(key, path)])
                    self.assertEqual(backend.puts, [] if hit else [(key, path)])
                    self.assertEqual(path.read_bytes(), data)
                    if hit:
                        synthesis.assert_not_called()
                    else:
                        synthesis.assert_called_once_with(ssml, "credential", "region")

    def test_failed_empty_invalid_or_silent_practice_outputs_are_never_stored(self):
        for engine in ("edge", "azure"):
            for response in (RuntimeError("synthesis failed"), b"", b"not mp3", mp3_bytes(True)):
                with self.subTest(engine=engine, response=type(response)), tempfile.TemporaryDirectory() as directory:
                    backend = FakeSpeechCache()
                    path = renderer.clip_path("Hej!", "se", Path(directory), engine=engine)
                    azure = renderer.azure_speech()

                    async def save(destination):
                        if isinstance(response, Exception):
                            raise response
                        Path(destination).write_bytes(response)

                    with patch.object(renderer.edge_tts, "Communicate") as edge, patch.object(
                        renderer, "azure_credentials", return_value=("key", "region"),
                    ), patch.object(
                        azure, "synthesize",
                        side_effect=response if isinstance(response, Exception) else None,
                        return_value=response,
                    ), patch.object(renderer.asyncio, "sleep", new_callable=AsyncMock):
                        edge.return_value.save = AsyncMock(side_effect=save)
                        with self.assertRaises((RuntimeError, CouldntDecodeError)):
                            asyncio.run(renderer.generate_clip(
                                "Hej!", "se", path, engine=engine, speech_cache=backend,
                            ))
                    self.assertEqual(backend.puts, [])

    def test_failed_empty_invalid_or_silent_narration_is_never_stored(self):
        azure = story._azure()
        for response in (azure.AzureSpeechError("failed"), b"", b"not mp3", mp3_bytes(True)):
            with self.subTest(response=type(response)), tempfile.TemporaryDirectory() as directory:
                backend = FakeSpeechCache()
                with patch.object(story, "_azure", return_value=azure), patch.object(
                    azure, "synthesize",
                    side_effect=response if isinstance(response, Exception) else None,
                    return_value=response,
                ):
                    with self.assertRaises((azure.AzureSpeechError, RuntimeError, CouldntDecodeError)):
                        asyncio.run(story._narration_clip(
                            "SSML", Path(directory), "key", "region", speech_cache=backend,
                        ))
                self.assertEqual(backend.puts, [])
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_practice_build_passes_backend_and_deterministic_keys(self):
        data = mp3_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcript = root / "transcript.json"
            transcript.write_text(json.dumps([{
                "id": "phrase_000001", "topic": "Greetings", "se": "Hej!",
                "en": "Hi!", "pl": "Witaj!", "ru": "Hi!",
            }]), encoding="utf-8")
            paths = [
                renderer.clip_path(text, language, root / "cache", engine="azure")
                for text, language in (("Hej!", "se"), ("Witaj!", "pl"))
            ]
            backend = FakeSpeechCache({path.name: data for path in paths})
            with patch.object(renderer, "generate_azure_clip", new_callable=AsyncMock) as synthesis, patch.object(
                renderer, "export_section",
            ):
                asyncio.run(renderer.build_audio_tracks(
                    transcript, root / "output", root / "cache", targets=("pl",),
                    speech_cache=backend,
                ))
            synthesis.assert_not_awaited()
            self.assertEqual(backend.gets, [(path.name, path) for path in paths])
            self.assertEqual(backend.puts, [])

    def test_full_story_render_passes_backend_to_vocabulary_and_all_narration(self):
        data = mp3_bytes()
        azure = story._azure()
        chapter = {
            "chapter_number": 1,
            "titles": {"pl": "Kot", "sv": "Katten", "en": "The Cat"},
            "chapter_text": {"pl": "Kot spi.", "sv": "Katten sover.", "en": "The cat sleeps."},
            "vocabulary": [{"id": 1, "text": {"pl": "kot", "sv": "katt", "en": "cat"}}],
        }
        transcript = {"story_id": "test", "titles": chapter["titles"], "chapters": [chapter]}
        for narration_engine in ("edge", "azure"):
            with self.subTest(narration_engine=narration_engine), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                transcript_path = root / "transcript.json"
                transcript_path.write_text(json.dumps(transcript), encoding="utf-8")
                source = root / "pl.txt"
                source.write_text("Rozdział 1: Kot\nKot spi.", encoding="utf-8")
                args = story.create_parser().parse_args([
                    "--transcript", str(transcript_path), "--source-text", str(source),
                    "--output", str(root / "audio"), "--cache", str(root / "cache"),
                    "--build-manifest", str(root / "manifest.json"),
                    "--source-language", "sv", "--target", "en", "--format", "wav",
                    "--tts-engine", "edge", "--narration-engine", narration_engine,
                ])
                keys = [
                    story._speech_key(text, lang, story.DEFAULT_VOICES[lang],
                                      story.DEFAULT_RATES[lang], "+0Hz")
                    for text, lang in (("katt", "sv"), ("cat", "en"))
                ]
                for text in ("The cat sleeps.", story.chapter_heading(chapter, "en"), "The Cat."):
                    if narration_engine == "edge":
                        key = story._speech_key(
                            text, "en", story.DEFAULT_VOICES["en"], story.DEFAULT_RATES["en"], "+0Hz",
                        )
                    else:
                        ssml = azure.build_ssml(
                            text, "-12%", 0, voice_name=azure.NARRATION_VOICES["en"],
                            style=azure.NARRATION_STYLES.get("en", "audiobook"), locale=azure.LOCALES["en"],
                        )
                        digest = hashlib.sha256(
                            ("azure:audio-24khz-160kbitrate-mono-mp3:" + ssml).encode("utf-8")
                        ).hexdigest()
                        key = f"azure_{digest}.mp3"
                    keys.append(key)
                backend = FakeSpeechCache({key: data for key in keys})
                with patch.object(story, "_azure", return_value=azure), patch.object(
                    azure, "load_dotenv",
                ), patch.object(azure, "check_voice", return_value={}), patch.object(
                    azure, "synthesize",
                ) as synthesis, patch.object(renderer.edge_tts, "Communicate") as edge, patch.object(
                    story, "_renderer", return_value=renderer,
                ), patch.dict(renderer.VOICES), patch.dict(renderer.RATES):
                    result = asyncio.run(story.render_story(args, speech_cache=backend))
                synthesis.assert_not_called()
                edge.assert_not_called()
                self.assertEqual(backend.gets, [(key, args.cache / key) for key in keys])
                self.assertEqual(backend.puts, [])
                self.assertTrue((args.output / result["chapters"]["1"]["targets"]["en"]["audio_file"]).is_file())

    def test_story_backend_errors_propagate_without_synthesis_recovery(self):
        data = mp3_bytes()
        for operation in ("fetch", "store"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                backend = FakeSpeechCache()

                async def save(path):
                    Path(path).write_bytes(data)

                with patch.object(story, "_renderer", return_value=renderer), patch.object(
                    backend, operation, side_effect=TimeoutError("cache unavailable"),
                ), patch.object(renderer.edge_tts, "Communicate") as edge, patch.object(
                    story.asyncio, "sleep", new_callable=AsyncMock,
                ) as sleep, patch.dict(renderer.VOICES), patch.dict(renderer.RATES):
                    edge.return_value.save = AsyncMock(side_effect=save)
                    with self.assertRaisesRegex(TimeoutError, "cache unavailable"):
                        asyncio.run(story._clip(
                            "cat", "en", Path(directory), "en-GB-SoniaNeural", "-5%",
                            "+0Hz", "edge", speech_cache=backend,
                        ))
                sleep.assert_not_awaited()
                if operation == "fetch":
                    edge.assert_not_called()
                else:
                    edge.return_value.save.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
