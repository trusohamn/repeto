# Language audio course

Generate children's language-learning MP3s and timestamp JSON files from the
shared practice corpus in
[courses/practice/transcript.json](courses/practice/transcript.json). Supports
Swedish (`se`), English (`en`), and Polish (`pl`) in any direction.

## Podcast / Spotify

Swedish to Polish: https://trusohamn.github.io/repeto/swedish-polish/feed.xml

Swedish to English
https://trusohamn.github.io/repeto/swedish-english/feed.xml

To package another completed course, ask the agent to use the repository's
[package-podcast skill](.github/skills/package-podcast/SKILL.md).
Packaging does not commit, push, or publish anything by itself.

Each podcast lives in `podcast/<course>/` with `cover.jpeg`, `course.json`,
categorized audio, and generated RSS files. Vocabulary-topic MP3s live in
`audio/practice/`; story chapters live in `audio/stories/<story-id>/`. The
catalog's `file` path is relative to `audio/`. It stores permanent episode IDs
and publication dates; keep these unchanged when replacing recordings.
Story artwork lives under `images/stories/<story-id>/cover.jpeg`. Each chapter
sets an optional catalog `image` path relative to the podcast folder, emitted
as an episode-level `itunes:image`; the main show cover remains unchanged.
Episodes set `season` and `episode` explicitly. Swedish-to-Polish vocabulary
topics are season 1, episodes 1–30; *Den magiska radion* story chapters are season
2, episodes 1–8. These values become podcast metadata in Spotify; the title's
number uses `episode`, not its position in the JSON list.

```sh
.venv/bin/python code/podcast.py
```

Push changes to `main` to publish through GitHub Actions. One-time GitHub setup:
**Settings → Pages → Build and deployment → Source: GitHub Actions**.
In [Spotify for Creators](https://creators.spotify.com/), choose **Add a new show
→ Find an existing show → Somewhere else**, enter the RSS URL, and verify
using the code emailed to the feed owner. The owner email is public in RSS.

## Generate audio

### Azure story narration preview

For a local pacing comparison only, copy `.env.example` to `.env` and enter
your Azure Speech key and region locally. `.env` is ignored by Git; never
share or commit its contents. Install the project requirements before running:

```sh
.venv/bin/python code/azure_story_preview.py
```

This sends the actual first Polish chapter to Azure Speech using Zofia with
SSML sentence pauses (350 ms) and rate `-8%`. It loads `.env` without
overriding existing environment variables. Use `--chapter`, `--rate=-8%`,
`--pause-ms`, and `--output` to adjust the preview.
The ignored `output/azure-preview/` folder receives an Azure MP3, the existing
Edge narration extracted as WAV, SSML, and comparison metadata. No practice
audio, packaged episodes, or RSS are changed. This tests pacing, not a
voice-specific emotional style. Azure synthesis consumes the resource's
quota and can incur charges on a paid tier.

To test an explicit audiobook style with the Polish Harper voice:

```sh
.venv/bin/python code/azure_story_preview.py --voice pl-PL-Harper:MAI-Voice-2.1 --style audiobook --rate=0% --pause-ms 200
```

The preview checks the region's live voice list for Polish and requested-style
support before synthesis, and saves the advertised capabilities and requested
style in the comparison metadata. Availability and free-tier access can vary;
unsupported requests fail explicitly rather than falling back to a neutral voice.

For passage-directed previews, pass `--directions PATH` with a JSON array
of passages. The directions override global rate and pauses, and specify each passage's
rate, pitch, and pause. They must reconstruct the original chapter
exactly. Intent labels explain the desired emotion in saved metadata; they
are not spoken text or unsupported named emotion styles. Actual expressiveness
and whether the voice honors each prosody setting require a listening test.
The earlier volume test used unsupported decibel syntax. Optional `volume`
directions now use signed percentages; optional `contour` directions specify
increasing pitch-control positions, for example `(0%,+0%) (100%,-3%)`.

The approved delivery groups related sentences and avoids forcing each fragment
into a separate sentence tag. It is stored directly in the story's
`generated/narration.json`, rather than in separate experimental direction files.
Acceptance alone does not prove every setting changes the voice audibly.
Compare recordings by ear.

Run commands from this project directory after setup below.

**Story audio (whole Polish chapter → vocabulary practice → same chapter again):**

```sh
.venv/bin/python code/story_course.py --source-language sv --target pl
```

Story narration and the opening book title now default to Azure Harper
MAI-Voice-2.1, using the `audiobook` style and a `-12%` rate. Polish uses
`pl-PL-Harper:MAI-Voice-2.1`, Swedish `sv-SE-Harper:MAI-Voice-2.1`, and English
`en-US-Harper:MAI-Voice-2.1`. The narration voice follows the language being
read, independently of the prompt/native language. Vocabulary practice stays
on Edge TTS, including both target repetitions.

Each episode plays the complete target-language chapter before vocabulary
practice and repeats the identical narration clip afterward, without a second
synthesis request. Practice still uses Swedish prompts and two Polish answers.
The book title is spoken once before the first reading in chapter 1.
Every episode also announces its chapter title once in the target language,
using the narration voice, before the first reading (after the book title in
chapter 1). A repetition pause separates the title from the story. Its text
and timestamps are recorded in `chapter_introduction`.
Both story/practice transitions have a quiet, fading two-note chime (620 ms)
with the configured repetition pause on either side (default 2.5 seconds).
The chime is generated locally, with no external sound asset or TTS request.
Manifests record both readings in chronological `chapter_readings` order and
the `sequence` as `["story", "practice", "story"]`; the existing
`chapter_reading` field continues to identify the final reading. The
`transitions` array records each chime's direction and timestamps.

Configure `.env` as described above. Override narration independently with
`--narration-voice LANG=VOICE`, `--narration-rate LANG=RATE`, or
`--narration-style LANG=STYLE`. Use `--narration-engine edge` explicitly for
the previous all-Edge behavior; Azure failures never silently fall back.
Existing `--voice`, `--rate`, and `--pitch` settings control Edge speech.

The renderer automatically reads `narration.json` beside the transcript when
present. Its shape is `{"pl": {"1": [{...passage settings...}]}}`;
each chapter value is either a passage array or a JSON path relative to that
configuration. Use `--narration-directions PATH` to select another map.
The approved Polish chapter-one directions are configured; chapters without
directions use continuous audiobook narration at the selected narration rate.
Directions must preserve chapter text exactly. Native/target swaps do not
create missing story translations.

Azure voice/style/language support and chapter text are checked before
rendering practice. Cached narration is keyed by the complete SSML and output
format. Chapter manifests record engine, voice, style, locale, and exact SSML.
Rerenders create new files; packaging and publishing remain separate actions.

Use `--help` for language, voice, pause, output, and format options. Review
[course requirements](courses/REQUIREMENTS.md) and the reusable
[create-story-course skill](.github/skills/create-story-course/SKILL.md).
To add the chapters to the existing Swedish-to-Polish feed as a new season,
include `--package-podcast --podcast-course swedish-polish`. This updates the
existing catalog and RSS without creating a separate show. Packaging moves
each chapter MP3 into the podcast folder instead of copying it, so the audio
exists once; timing JSON stays under `generated/audio/`.

The same story also ships in English for the Swedish-to-English feed, using
the English `chapter_text` (a child-friendly translation of the Polish
original) and `en-US-Harper:MAI-Voice-2.1` narration:

```sh
.venv/bin/python code/story_course.py --source-language sv --target en --package-podcast --podcast-course swedish-english
```

Renders go to `generated/audio/<source>_<targets>/` (for example `sv_pl` or
`sv_en`) unless `--output` is given. The shared build manifest keeps every
direction: rendering one target leaves other targets' chapter entries intact,
`renders` records each direction's settings, and `settings` is the latest
render. Story artwork defaults to `cover_<source>_<target>.jpeg` (Swedish is
`se`), then the shared `cover.jpeg`.

Course sources live under `courses/`: reusable vocabulary shared across
language directions is stored once in `practice/`, while direction-specific
stories and their generated assets live under the corresponding course folder.

**English → Polish, Greetings preview (up to 5 minutes):**

```sh
.venv/bin/python code/transcription.py --source en --target pl --topic "Greetings" --max-duration 300 --output output/preview
```

Saves an MP3 and matching timestamp JSON in `output/preview/`, named like
`01_greetings_en_pl_2026-10-27_11-18-30.mp3` and `.json`.
The suffix is the render's local start date and time, shared by all its tracks.

```sh
# Polish → English, all topics
.venv/bin/python code/transcription.py --source pl --target en

# Swedish → Polish and English, separate files
.venv/bin/python code/transcription.py --source se --target pl en

# English → Polish, each answer played twice
.venv/bin/python code/transcription.py --source en --target pl --double-output --output output/double

# List available topic titles
.venv/bin/python code/transcription.py --list-topics
```

- `--source`: prompt language; defaults to `se`.
- `--target`: one or more answer languages; defaults to all except the source.
- `--double-output`: play each answer twice, with a 2.5-second pause after each.
  Adds `_double` before the date in both filenames, for example
  `01_greetings_en_pl_double_2026-10-27_11-18-30.mp3`.
- `--topic`: exact topic title; omit to render all topics.
- `--max-duration`: maximum seconds per track; omit for full topics.
  Keeps complete entries and may finish before the limit.
- `--output`: destination folder; defaults to the project's `output/`.
- `--transcript` and `--cache`: override the input JSON and speech-cache paths.

Each entry plays: **prompt → 2-second thinking pause → answer → 2.5-second
repetition pause**. Existing speech clips are reused from the cache.
With `--double-output`, the answer and repetition pause play once more.
Both playbacks have timestamps in `target_playbacks` in the manifest.
The duration cap includes both. Timestamped filenames keep separate renders
apart; avoid starting renders in the same output folder within the same second.
Uncached speech requires internet access and sends the text to Edge TTS.
Unpunctuated words receive a final full stop for TTS reliability; transcript
and manifest text stay unchanged. Cache keys use this speech text, so older
unpunctuated clips may need regenerating once.
Empty-audio responses are retried up to three attempts, with 2- and 4-second
waits. If rendering still fails, rerun the same command; completed speech clips
are cached and reused. No phrases are silently skipped.
High speech peaks are gently compressed when needed to reach consistent volume
without clipping; clips that still cannot meet the limits are rejected.
Do not run simultaneous renders into the same output folder.
Final MP3 and JSON files are published per topic only after every selected
entry and language track succeeds and passes export validation. A failed topic
publishes no final files; previously completed topics and cached clips remain.
If the output folder disappears during synthesis, export recreates it.
With a duration cap, success means all complete entries selected for the preview.

## Setup (macOS)

Requires Python 3.10+ and FFmpeg:

```sh
brew install ffmpeg
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

In VS Code, select this project's `.venv` with **Python: Select Interpreter**.

## Edit the transcript

Keep each entry's permanent `id` unchanged when editing or moving it. Assign
a new unused ID to new entries; never renumber or reuse deleted IDs.

## Tests

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python -m pyright
```

See [REQUIREMENTS.md](REQUIREMENTS.md) for audio specifications and the timestamp schema.
