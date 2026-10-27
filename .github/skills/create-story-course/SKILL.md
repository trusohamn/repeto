---
name: create-story-course
description: Turn a chaptered children's story into a faithful multilingual transcript, validate its permanent IDs, render language-practice and full-chapter audio, and optionally package podcast feeds. Use for new or extended course stories.
---

# Create or extend a Repeto story course

## Source and scope

- Read `courses/REQUIREMENTS.md` and the story's
  `courses/<course-slug>/stories/<story-id>/complete/<source>.txt`.
- Keep shared practice data in `courses/practice/transcript.json`; do not
  duplicate that corpus into individual direction-specific course folders.
- Inspect existing `generated/transcript.json`, `generated/manifest.json`, and
  any rendered files before changing or regenerating them.
- Ask for clarification if the source, target languages, pronunciation, or
  intended chapter boundaries are ambiguous. Do not invent missing story text.
- Preserve the original language exactly in the chapter-level `chapter_text`,
  including punctuation and dialogue.

## Transcript authoring

- Translate chapter titles and selected useful vocabulary into requested
  languages. Make translations natural for children; preserve names, events,
  tone, and meaning. Do not translate the story sentence-by-sentence or alter
  names and the magic word `Reparo`.
- Store the whole target-language story as one chapter-level `chapter_text`
  string per available target. Preserve the Polish original exactly. Only add
  full-chapter translations if requested; never create aligned sentence
  translations for practice.
- Use `courses/swedish-polish/stories/magical_radio/generated/transcript.json`
  as the schema example.
- IDs are positive integers unique across all vocabulary items in the story.
  Treat IDs as permanent: preserve existing IDs and allocate new unused IDs
  only for new items. Never renumber to close gaps.
- Keep each chapter's vocabulary in learning order. Ensure title and
  vocabulary text maps contain the supported ISO 639-1 languages.
- Audit the whole chapter text and include enough words and short phrases for
  a child with little prior target-language knowledge to follow its characters,
  setting, actions, and plot-critical details. Cover important nouns, verbs,
  descriptions, and connectors where needed; do not rely on a word being taught
  in a later chapter. Prefer natural words and short chunks, never sentence-by-
  sentence story translations or practice.
- Validate the JSON and its exact Polish-source reconstruction before TTS:

  ```sh
  .venv/bin/python code/story_course.py --list
  ```

## Audio rendering

- Use the story renderer; do not generate or publish files by hand:

  ```sh
  .venv/bin/python code/story_course.py --source-language sv --target pl
  ```

- Defaults are Swedish prompts, Polish targets, then the original whole chapter
  read once in Polish. Practice contains vocabulary only in a deterministic
  shuffled order within each chapter; preserve stable IDs and keep the story
  sentences in their original order. Story sentences are not individually
  translated or practiced. Every vocabulary target is played twice with the
  configured pauses.
- The default Swedish and Polish TTS rates are both `-15%`; preserve these
  child-friendly rates unless the user requests a change.
- Speak the book title once at the beginning of chapter 1, before vocabulary
  practice. Record it as a separate `book_introduction` manifest segment and
  do not repeat it in the full chapter reading.
- Pass voice, rate, pitch, pauses, format, duration cap, paths, and podcast
  settings as CLI arguments when requested; check `--help` for current options.
- Use a duration cap only for an intentional validation preview. A cap rejects
  a chapter that would exceed it; it never publishes partial chapters.
- Check TTS availability and FFmpeg prerequisites. TTS sends text to Edge TTS.
  Do not hide failures or claim a render succeeded unless every chapter and
  selected language passed decode and timing validation.
- Rerenders produce new timestamped files. Preserve prior audio and manifests
  unless replacement or cleanup has been explicitly requested.

## Podcast packaging

- Package only when explicitly requested. For the existing Swedish-to-Polish
  show, reuse its show artwork:

  ```sh
  .venv/bin/python code/story_course.py --package-podcast --podcast-course swedish-polish
  ```

- For this story, append to the existing Swedish-to-Polish show as a new
  season. The existing show artwork and owner metadata are retained, and
  chapter MP3s are stored under `podcast/swedish-polish/audio/stories/<id>/`.
- When creating a separate feed instead, verify artwork and public owner
  metadata; owner email is exposed in RSS. Preserve existing episode GUIDs
  and publication dates when updating.
- Run the podcast tests and RSS builder. Verify episode counts, enclosures,
  actual file sizes, cover links, and target-language feed URLs.
- Publishing is separate: never commit, push, or submit a show to Spotify
  unless explicitly authorized.
