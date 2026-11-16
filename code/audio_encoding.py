"""Shared final-audio encoding settings for course renderers."""

MP3_VBR_QUALITY = 4


def mp3_export_settings(
    bitrate: str | None = None,
) -> tuple[dict[str, str], list[str]]:
    parameters = ["-write_xing", "1"]
    options: dict[str, str] = {}
    if bitrate is None:
        parameters.extend(["-q:a", str(MP3_VBR_QUALITY)])
    else:
        options["bitrate"] = bitrate
    return options, parameters
