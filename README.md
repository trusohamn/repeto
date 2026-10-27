# Language audio course

Generate children's language-learning MP3s and timestamp JSON files from
[course_transcript.json](course_transcript.json). Supports Swedish (`se`),
English (`en`), and Polish (`pl`) in any direction.

## Podcast / Spotify

RSS: https://trusohamn.github.io/repeto/swedish-polish/feed.xml

Each course lives in `podcast/<course>/` with `cover.jpeg`, `course.json`, and
`audio/`. The catalog stores permanent episode IDs and publication dates;
keep these unchanged when replacing recordings.

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
