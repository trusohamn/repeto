import importlib.util
import json
import unittest
import xml.etree.ElementTree as ET
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

SPEC = importlib.util.spec_from_file_location(
    "azure_preview", Path(__file__).resolve().parents[1] / "code/azure_speech.py"
)
assert SPEC and SPEC.loader
preview = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preview)


class AzurePreviewTests(unittest.TestCase):
    def test_passage_directions_preserve_actual_chapter_and_emit_prosody(self):
        data = json.loads((
            preview.STORY / "generated/narration.json"
        ).read_text())["pl"]["1"]
        transcript = json.loads((preview.STORY / "generated/transcript.json").read_text())
        text = transcript["chapters"][0]["chapter_text"]["pl"]
        passages = preview.validate_passages(data, text)
        root = ET.fromstring(preview.build_ssml(
            text, "-8%", 350, passages=passages,
            voice_name="pl-PL-Harper:MAI-Voice-2.1", style="audiobook",
        ))
        prosodies = root.findall(f".//{{{preview.SSML}}}prosody")
        self.assertEqual(len(prosodies), len(passages))
        for element, passage in zip(prosodies, passages, strict=True):
            for setting in ("rate", "pitch"):
                self.assertEqual(element.get(setting), passage[setting])
        self.assertEqual(
            " ".join("".join(s.itertext()) for s in prosodies),
            text,
        )
        self.assertEqual(len(root.findall(f".//{{{preview.SSML}}}break")), len(passages) - 1)

    def test_natural_delivery_emits_volume_contour_and_preserves_text(self):
        data = json.loads((preview.STORY / "generated/narration.json").read_text())["pl"]["1"]
        text = json.loads((preview.STORY / "generated/transcript.json").read_text())["chapters"][0]["chapter_text"]["pl"]
        passages = preview.validate_passages(data, text)
        root = ET.fromstring(preview.build_ssml(text, "-8%", 350, passages=passages))
        prosodies = root.findall(f".//{{{preview.SSML}}}prosody")
        self.assertEqual(" ".join("".join(p.itertext()) for p in prosodies), text)
        self.assertEqual(len(prosodies), len(passages))
        self.assertEqual(prosodies[2].get("volume"), "-12%")
        self.assertEqual(prosodies[2].get("contour"), passages[2]["contour"])
        self.assertFalse(root.findall(f".//{{{preview.SSML}}}s"))

    def test_invalid_or_altered_passage_directions_are_rejected(self):
        passage = {
            "text": "Kot śpi.", "intent": "Calm",
            "rate": "-12%", "pitch": "+2%", "pause_after_ms": 350,
        }
        for field, value in [
            ("text", "Changed text."), ("rate", "slow"), ("pitch", "high"),
            ("pause_after_ms", True),
            ("pause_after_ms", -1), ("intent", ""),
            ("volume", "-2dB"), ("volume", "+99%"),
            ("contour", "(110%,+2%)"), ("contour", "(80%,+2%) (20%,-2%)"),
        ]:
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    preview.validate_passages([{**passage, field: value}], "Kot śpi.")

    def test_storytelling_style_is_explicit_and_preserves_polish_text(self):
        text = "Jest sobota. Dzieci otwierają szeroko oczy."
        root = ET.fromstring(preview.build_ssml(
            text, "-8%", 350,
            voice_name="pl-PL-Harper:MAI-Voice-2.1", style="audiobook",
        ))
        voice = root.find(f"{{{preview.SSML}}}voice")
        assert voice is not None
        self.assertEqual(voice.get("name"), "pl-PL-Harper:MAI-Voice-2.1")
        expression = voice.find(f"{{{preview.MSTTS}}}express-as")
        assert expression is not None
        self.assertEqual(expression.get("style"), "audiobook")
        self.assertEqual(
            " ".join("".join(s.itertext()) for s in root.findall(f".//{{{preview.SSML}}}s")),
            text,
        )

    def test_capabilities_reject_unavailable_language_voice_and_style(self):
        voices = [
            {"ShortName": "polish", "Locale": "pl-PL", "StyleList": ["audiobook"]},
            {"ShortName": "english", "Locale": "en-US", "StyleList": ["audiobook"]},
            {"ShortName": "neutral", "Locale": "pl-PL"},
        ]
        with patch.object(preview, "request_bytes", return_value=json.dumps(voices).encode()):
            result = preview.check_voice("fake", "swedencentral", "polish", "audiobook")
            self.assertEqual(result["advertised_styles"], ["audiobook"])
            for name, style in [
                ("missing", None), ("english", "audiobook"),
                ("neutral", "audiobook"), ("polish", "story"),
            ]:
                with self.subTest(voice=name, style=style):
                    with self.assertRaises(ValueError):
                        preview.check_voice("fake", "swedencentral", name, style)

    def test_ssml_preserves_text_and_escapes_xml(self):
        text = "Jest sobota. Maja mówi: „A & B < C!”"
        root = ET.fromstring(preview.build_ssml(text, "-8%", 350))
        ns = {"s": preview.SSML}
        sentences = root.findall(".//s:s", ns)
        self.assertEqual(" ".join("".join(sentence.itertext()) for sentence in sentences), text)
        pause = root.find(".//s:break", ns)
        voice = root.find("s:voice", ns)
        assert pause is not None and voice is not None
        self.assertEqual(pause.get("time"), "350ms")
        self.assertEqual(voice.get("name"), preview.VOICE)

    def test_invalid_settings_fail_before_request(self):
        for rate, pause in [("bad", 350), ("-8%", -1), ("-8%", 2001)]:
            with self.subTest(rate=rate, pause=pause):
                with self.assertRaises(ValueError):
                    preview.build_ssml("Kot śpi.", rate, pause)
        with self.assertRaises(ValueError):
            preview.build_ssml("", "-8%", 350)
        with patch.object(preview, "urlopen") as request:
            for key, region in [("", "swedencentral"), ("fake", "../bad")]:
                with self.assertRaises(ValueError):
                    preview.synthesize("<speak/>", key, region)
            request.assert_not_called()

    def test_http_errors_do_not_expose_credentials(self):
        error = HTTPError("https://example.com", 401, "secret-key", Message(), None)
        with patch.object(preview, "urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "HTTP 401") as caught:
                preview.synthesize("<speak/>", "secret-key", "swedencentral")
        self.assertNotIn("secret-key", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
