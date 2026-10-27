---
name: package-podcast
description: Package a completed Repeto audio course as a separate GitHub Pages podcast with an episode catalog, bilingual titles, cover, MP3s, and validated RSS. Use when preparing a generated course for RSS or Spotify.
---

# Package a Repeto podcast

Work from the repository root. This skill packages existing recordings; it
does not synthesize audio or submit shows to Spotify.

## Confirm scope

- Identify source/target languages, render directory, and podcast course slug.
  Example: `se` to `en`, `output/swedish_english_double`,
  `podcast/swedish-english`.
- Preserve the user's commit/push restrictions. Packaging is local by default;
  publishing requires separate authorization.
- Check Git status and preserve user edits, covers, and existing course data.
- Configure the project's Python environment and use `.venv/bin/python`.

## Validate inputs before packaging

1. Read `code/transcription.py`, `code/podcast.py`, and an existing
   `podcast/*/course.json` for the current schemas and conventions.
2. Load the current transcript with the renderer's `load_topics`. Do not
   hardcode topic or phrase counts.
3. Match exactly one selected render manifest per topic. If there are multiple
   renders, explicitly select a complete version; do not merge them or
   silently overwrite one with another.
4. Require the selected direction and every current phrase ID/text in order.
   For double output require exactly two target playbacks per entry.
5. Decode every referenced MP3 with pydub/FFmpeg. Verify 44100 Hz, duration
   within 1 ms of its manifest, nonempty speech segments, segment bounds, and
   the configured opening/think/repetition pauses. Reject preview-length,
   missing, corrupt, stale, or incomplete topics; report the exact failure.
6. For a new podcast show, require a cover and inspect its actual
   format/dimensions. Spotify artwork should be square JPEG, 1400-3000 pixels
   per side. When adding to an existing show, keep its existing cover and
   owner metadata; do not overwrite or replace them.

## Prepare catalog and audio

Use one directory per course:

```text
podcast/<slug>/
  cover.jpeg
  course.json
  audio/
    practice/<original-render-filename>.mp3
    stories/<story-id>/<original-render-filename>.mp3
  feed.xml
  index.html
```

- Copy validated MP3s without transcoding or renaming them.
- Store vocabulary-topic recordings under `audio/practice/`; store story
  chapters under `audio/stories/<story-id>/`. `course.json` episode `file`
  values are paths relative to `audio/`, not necessarily basenames.
- Create the catalog using the existing schema. Use the source audience's
  language for the show description; explain pauses, double playback, and
  AI-generated voices accurately.
- Use bilingual episode titles, source first, without a numeric prefix:
  `Hälsningar — Greetings`. `code/podcast.py` adds the number.
- Use season 1 and episodes 1 through the current topic count for a new course.
- Assign stable GUIDs such as `repeto:swedish-english:topic-01`.
  Never replace existing episode IDs, publication dates, or season/episode
  identities on reruns, even when titles or recordings change.
- Read filenames and `duration_ms` from selected manifests, not guesses.
- For a new course, reuse the existing author/public owner email only if they
  still apply. The email is publicly exposed in RSS; obtain permission for
  any new address.
- Stage a complete course in a temporary directory, including a copy of the
  cover, catalog, and audio. Call `build_feed` on a staged directory whose
  basename equals the intended slug; validate it before installing files.
- Refuse conflicting existing destination MP3s unless replacement is
  authorized. Identical copies are safe to reuse. Never remove unrelated files.
  File replacements are not an atomic multi-file transaction.

## Generate and verify

Run from the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -p test_podcast.py -v
.venv/bin/python code/podcast.py
```

The generator rebuilds all course feeds and the root course listing. Inspect
the diff to ensure existing courses have no unintended changes.

Parse the new RSS and verify:

- Exactly one item per expected topic, unique GUIDs and season/episode pairs.
- Correct bilingual numbered titles, source language, owner, and cover URL.
- Every enclosure maps to its packaged MP3, with actual byte length and
  `audio/mpeg` type; confirm copied bytes match the validated render.
- Duration and publication metadata match the catalog.
- All URLs use the correct HTTPS base URL and course slug.
- The root podcast index links to the new course.

Update the README feed list and report the local package path, topic/entry
counts, total duration, and expected feed URL. Do not call an unpublished URL
live or Spotify-ready online.

For a story that belongs in an existing language-direction show, use
`code/story_course.py --package-podcast --podcast-course <slug>`. This
appends its chapters as a new season, preserves the existing show metadata,
episode GUIDs, and publication dates, and stores the MP3s under
`audio/stories/<story-id>/`. Use a separate feed only when explicitly requested.

## Publish only when authorized

Commit/push only when requested. A push to `main` triggers the existing Pages
workflow. After deployment succeeds, fetch the public RSS, cover, and audio
and check enclosure byte lengths and HTTP availability before reporting it
live. A separate course feed is added as a separate externally hosted show
in Spotify for Creators; do not create or delete shows without authorization.
