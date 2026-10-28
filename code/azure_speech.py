"""Compare existing Polish chapter narration with an Azure SSML preview."""

import argparse
import io
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import TypedDict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from pydub import AudioSegment

ROOT = Path(__file__).resolve().parents[1]
STORY = ROOT / "courses/swedish-polish/stories/magical_radio"
SSML = "http://www.w3.org/2001/10/synthesis"
VOICE = "pl-PL-ZofiaNeural"
NARRATION_VOICES = {
    "pl": "pl-PL-Harper:MAI-Voice-2.1",
    "sv": "sv-SE-Harper:MAI-Voice-2.1",
    "en": "en-US-Harper:MAI-Voice-2.1",
    "ru": "ru-RU-SvetlanaNeural",
}
# Russian Harper (MAI) narration has audible high-frequency artifacts; Svetlana Neural has no styles.
NARRATION_STYLES: dict[str, str | None] = {
    "pl": "audiobook", "sv": "audiobook", "en": "audiobook", "ru": None,
}
LOCALES = {"pl": "pl-PL", "sv": "sv-SE", "en": "en-US", "ru": "ru-RU"}
MSTTS = "http://www.w3.org/2001/mstts"
ET.register_namespace("mstts", MSTTS)


class PassageOptions(TypedDict, total=False):
    volume: str
    contour: str


class Passage(PassageOptions):
    text: str
    intent: str
    rate: str
    pitch: str
    pause_after_ms: int


def validate_passages(data: object, text: str) -> list[Passage]:
    if not isinstance(data, list) or not data:
        raise ValueError("Delivery directions must be a nonempty array of passages.")
    passages: list[Passage] = []
    for entry in data:
        required = {"text", "intent", "rate", "pitch", "pause_after_ms"}
        if (
            not isinstance(entry, dict) or not required <= set(entry)
            or set(entry) - required - {"volume", "contour"}
        ):
            raise ValueError("Each passage requires text, intent, rate, pitch, pause_after_ms.")
        if any(not isinstance(entry[field], str) or not entry[field].strip()
               for field in ("text", "intent", "rate", "pitch")):
            raise ValueError("Passage text and delivery settings must be nonempty strings.")
        if not re.fullmatch(r"[+-]?\d+%", entry["rate"]):
            raise ValueError("Passage rate must be a percentage.")
        if not re.fullmatch(r"[+-]\d+%", entry["pitch"]):
            raise ValueError("Passage pitch must be a signed percentage.")
        pause = entry["pause_after_ms"]
        if type(pause) is not int or not 0 <= pause <= 2000:
            raise ValueError("Passage pauses must be integers between 0 and 2000 ms.")
        passages.append({
            "text": entry["text"], "intent": entry["intent"],
            "rate": entry["rate"], "pitch": entry["pitch"],
            "pause_after_ms": pause,
        })
        if "volume" in entry:
            volume = entry["volume"]
            if not isinstance(volume, str) or not re.fullmatch(r"[+-]\d+%", volume):
                raise ValueError("Passage volume must be a signed percentage.")
            if not -30 <= int(volume[:-1]) <= 20:
                raise ValueError("Preview volume adjustments must be between -30% and +20%.")
            passages[-1]["volume"] = volume
        if "contour" in entry:
            contour = entry["contour"]
            if not isinstance(contour, str) or not re.fullmatch(
                r"\(\d{1,3}%,[+-]\d{1,2}%\)(?: \(\d{1,3}%,[+-]\d{1,2}%\))*", contour
            ):
                raise ValueError("Invalid passage pitch contour.")
            positions = [int(value) for value in re.findall(r"\((\d+)%", contour)]
            if positions != sorted(set(positions)) or any(value > 100 for value in positions):
                raise ValueError("Pitch contour positions must increase from 0% to 100%.")
            passages[-1]["contour"] = contour
    if " ".join(passage["text"] for passage in passages) != text:
        raise ValueError("Directed passages must reconstruct the chapter text exactly.")
    return passages


def build_ssml(
    text: str, rate: str, pause_ms: int, *,
    voice_name: str = VOICE, style: str | None = None,
    passages: list[Passage] | None = None,
    locale: str = "pl-PL",
) -> str:
    if not re.fullmatch(r"[+-]?\d+%", rate):
        raise ValueError("Rate must be a percentage, for example -8%.")
    if not 0 <= pause_ms <= 2000:
        raise ValueError("Sentence pause must be between 0 and 2000 milliseconds.")
    if not text.strip():
        raise ValueError("Chapter text is empty.")
    speak = ET.Element(
        "speak",
        {"version": "1.0", "xmlns": SSML,
         "{http://www.w3.org/XML/1998/namespace}lang": locale},
    )
    voice = ET.SubElement(speak, "voice", name=voice_name)
    if style:
        voice = ET.SubElement(voice, f"{{{MSTTS}}}express-as", style=style)
    if passages is not None:
        passages = validate_passages(passages, text)
        paragraph = ET.SubElement(voice, "p")
        for index, passage in enumerate(passages):
            prosody = ET.SubElement(
                paragraph, "prosody", rate=passage["rate"],
                pitch=passage["pitch"],
            )
            for setting in ("volume", "contour"):
                value = passage.get(setting)
                if value is not None:
                    prosody.set(setting, value)
            prosody.text = passage["text"]
            if index < len(passages) - 1 and passage["pause_after_ms"]:
                ET.SubElement(paragraph, "break", time=f'{passage["pause_after_ms"]}ms')
        return ET.tostring(speak, encoding="unicode")
    prosody = ET.SubElement(voice, "prosody", rate=rate)
    paragraph = ET.SubElement(prosody, "p")
    if pause_ms == 0:
        paragraph.text = text
        return ET.tostring(speak, encoding="unicode")
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    for index, sentence in enumerate(sentences):
        if index:
            ET.SubElement(paragraph, "break", time=f"{pause_ms}ms")
        ET.SubElement(paragraph, "s").text = sentence
    return ET.tostring(speak, encoding="unicode")


def synthesize(ssml: str, key: str, region: str) -> bytes:
    validate_credentials(key, region)
    request = Request(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        data=ssml.encode("utf-8"),
        headers={
            "Ocp-Apim-Subscription-Key": key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-160kbitrate-mono-mp3",
            "User-Agent": "RepetoStoryPreview",
        },
        method="POST",
    )
    audio = request_bytes(request)
    if not audio:
        raise RuntimeError("Azure Speech returned no audio.")
    return audio


def validate_credentials(key: str, region: str) -> None:
    if not key.strip():
        raise ValueError("Set AZURE_SPEECH_KEY in the local .env file.")
    if not re.fullmatch(r"[a-z0-9]+", region):
        raise ValueError("Set AZURE_SPEECH_REGION to an Azure region such as swedencentral.")


def request_bytes(request: Request) -> bytes:
    try:
        with urlopen(request, timeout=90) as response:
            return response.read()
    except HTTPError as error:
        explanations = {
            400: "Azure rejected the SSML or voice settings.",
            401: "Check the Speech key and region.",
            403: "Check resource access and the free-tier quota.",
            429: "Quota or request-rate limit reached; retry later.",
        }
        raise RuntimeError(
            f"Azure Speech HTTP {error.code}. "
            + explanations.get(error.code, "Check Azure resource status.")
        ) from None
    except (URLError, TimeoutError):
        raise RuntimeError("Could not reach Azure Speech; check connectivity and region.") from None


def check_voice(
    key: str, region: str, voice_name: str, style: str | None, locale: str = "pl-PL",
) -> dict:
    validate_credentials(key, region)
    request = Request(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/voices/list",
        headers={"Ocp-Apim-Subscription-Key": key},
    )
    voices = json.loads(request_bytes(request))
    voice = next((voice for voice in voices if voice["ShortName"] == voice_name), None)
    if voice is None:
        raise ValueError(f"Voice is not advertised in this Azure region: {voice_name}")
    if voice["Locale"] != locale and locale not in voice.get("SecondaryLocaleList", []):
        raise ValueError(f"Voice does not advertise {locale} support: {voice_name}")
    if style and style not in voice.get("StyleList", []):
        raise ValueError(f"Voice {voice_name} does not advertise style {style!r}.")
    return {
        "voice": voice_name, "locale": voice["Locale"],
        "advertised_styles": voice.get("StyleList", []),
    }


def create_preview(args: argparse.Namespace) -> Path:
    transcript = json.loads((STORY / "generated/transcript.json").read_text())
    chapter = next(
        (chapter for chapter in transcript["chapters"]
         if chapter["chapter_number"] == args.chapter), None,
    )
    if chapter is None:
        raise ValueError(f"No chapter {args.chapter} in the story.")
    text = chapter["chapter_text"]["pl"]
    passages = (
        validate_passages(json.loads(args.directions.read_text(encoding="utf-8")), text)
        if args.directions else None
    )
    ssml = build_ssml(
        text, args.rate, args.pause_ms, voice_name=args.voice, style=args.style,
        passages=passages,
    )
    build = json.loads((STORY / "generated/manifest.json").read_text())
    original = build["chapters"][str(args.chapter)]["targets"]["pl"]
    original_audio = AudioSegment.from_file(
        STORY / "generated/audio/sv_pl" / original["audio_file"]
    )
    segment = original["chapter_reading"]
    start, end = segment["start_ms"], segment["end_ms"]
    if segment["text"] != text or not 0 <= start < end <= len(original_audio):
        raise ValueError("Existing narration does not match chapter text or timing.")
    baseline = original_audio[start:end]
    load_dotenv(ROOT / ".env", override=False)
    key = os.environ.get("AZURE_SPEECH_KEY", "")
    region = os.environ.get("AZURE_SPEECH_REGION", "")
    capabilities = check_voice(key, region, args.voice, args.style)
    audio = synthesize(ssml, key, region)
    decoded = AudioSegment.from_file(io.BytesIO(audio), format="mp3")
    if len(decoded) == 0 or decoded.rms == 0:
        raise RuntimeError("Azure preview is empty or silent.")
    args.output.mkdir(parents=True, exist_ok=True)
    destination = args.output / datetime.now().strftime(
        f"chapter-{args.chapter:02d}_%Y-%m-%d_%H-%M-%S-%f"
    )
    with tempfile.TemporaryDirectory(dir=args.output) as directory:
        pending = Path(directory) / "preview"
        pending.mkdir()
        (pending / "azure-ssml.mp3").write_bytes(audio)
        baseline.export(pending / "existing-edge.wav", format="wav")
        (pending / "narration.ssml").write_text(ssml, encoding="utf-8")
        metadata = {
            "chapter": args.chapter, "text": text, "voice": args.voice,
            "style": args.style, "voice_capabilities": capabilities,
            "rate": None if passages else args.rate,
            "sentence_pause_ms": None if passages else args.pause_ms,
            "passage_directions": passages,
            "delivery_mode": "passage_prosody" if passages else "global_prosody",
            "azure_duration_ms": len(decoded), "existing_duration_ms": len(baseline),
            "note": (
                "Explicit voice style requested; judge delivery by listening."
                if args.style else "Pacing comparison, not an emotional-style voice."
            ),
        }
        (pending / "comparison.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        pending.rename(destination)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chapter", type=int, default=1)
    parser.add_argument("--voice", default=VOICE)
    parser.add_argument("--style", help="Must be advertised for the selected Polish-capable voice.")
    parser.add_argument("--rate", default="-8%")
    parser.add_argument("--pause-ms", type=int, default=350)
    parser.add_argument(
        "--directions", type=Path,
        help="JSON passage directions; overrides global rate and pauses and preserves chapter text.",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "output/azure-preview")
    args = parser.parse_args()
    destination = create_preview(args)
    print(f"Preview saved to {destination}")
    print("Compare azure-ssml.mp3 with existing-edge.wav. Published files are unchanged.")


if __name__ == "__main__":
    main()
