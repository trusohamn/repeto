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

Run commands from this project directory after setup below.

**Story audio (Swedish prompt → Polish vocabulary twice, then the whole Polish chapter):**

```sh
.venv/bin/python code/story_course.py --source-language sv --target pl
```

Use `--help` for language, voice, pause, output, and format options. Review
[course requirements](courses/REQUIREMENTS.md) and the reusable
[create-story-course skill](.github/skills/create-story-course/SKILL.md).
To add the chapters to the existing Swedish-to-Polish feed as a new season,
include `--package-podcast --podcast-course swedish-polish`. This updates the
existing catalog and RSS without creating a separate show.

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
