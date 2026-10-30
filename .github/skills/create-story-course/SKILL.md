---
name: create-story-course
description: Turn a chaptered, child-friendly story into a faithful multilingual transcript, validate its permanent IDs, render language-practice and full-chapter audio, and optionally package podcast feeds. Use for new or extended course stories.
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

- Follow [review-language-course](../review-language-course/SKILL.md) before
  rendering translations; structural validation does not establish language quality.
- Translate chapter titles and selected useful vocabulary into requested
  languages. Make translations natural and child-friendly (the courses serve
  beginners of all ages); preserve events, tone, and meaning. Do not translate the story sentence-by-sentence.
- Character names: preserve them within a course (one language version),
  across all chapters, titles, vocabulary, and episodes; never rename a
  character mid-course. When translating to a new target language, localize
  names to familiar equivalents in that language (Magiczne Radio in English:
  Maja → Maya, Tomek → Tom, Radiofon → Radiophone; in Russian: Маша, Миша,
  Радиофон). Name choices belong to
  one story; other stories choose their own. Never change the Polish
  original, and keep invented magic words such as `Reparo` pronounced identically
  in all languages, written in the target script when it differs (Russian
  `Репаро`) so TTS pronounces them correctly.
- Store the whole target-language story as one chapter-level `chapter_text`
  string per available target. Preserve the Polish original exactly. Only add
  full-chapter translations if requested; never create aligned sentence
  translations for practice.
- Use `courses/stories/magical_radio/generated/transcript.json`
  as the schema example.
- Give every chapter an optional `summary` map with a one- or two-sentence
  Swedish teaser (`"summary": {"sv": "…"}`) for podcast episode descriptions.
  Keep it faithful to the chapter text and avoid character names, because
  names are localized per target language.
- IDs are positive integers unique across all vocabulary items in the story.
  Treat IDs as permanent: preserve existing IDs and allocate new unused IDs
  only for new items. Never renumber to close gaps.
- Keep each chapter's vocabulary in learning order. Ensure title and
  vocabulary text maps contain the supported ISO 639-1 languages.
- Audit the whole chapter text and include enough words and short phrases for
  a beginner with little prior target-language knowledge to follow its characters,
  setting, actions, and plot-critical details. Cover important nouns, verbs,
  descriptions, and connectors where needed; do not rely on a word being taught
  in a later chapter. Prefer natural words and short chunks, never sentence-by-
  sentence story translations or practice.
- Validate the JSON and its exact Polish-source reconstruction before TTS:

  ```sh
  .venv/bin/python code/story_course.py --list
  ```

## Audio rendering

- Full story readings and the opening book title default to Azure Harper
  MAI-Voice-2.1 with `audiobook` style in Polish, Swedish, and English. Russian
  uses Azure `ru-RU-SvetlanaNeural` without a style (Russian Harper produced
  audible background artifacts).
  Spain Spanish uses `es-ES-ElviraNeural` without an expressive style; the
  configured region does not advertise Spain Spanish Harper.
  Prompts and vocabulary repetitions use the same Neural voices through
  licensed Azure Speech (`--tts-engine azure`, the default); use
  `--tts-engine edge` only when explicitly requested. Narration uses the
  language being read, not the native prompt language. Do not silently fall
  back if Azure credentials, language, or style are unavailable.
- Keep credentials in ignored `.env`; never inspect, print, or commit them.
  Use `--narration-voice`, `--narration-rate`, and `--narration-style` for
  Azure, independently from the vocabulary `--voice`, `--rate`, and `--pitch`.
- Author passage directions per chapter for suspense, dialogue, and reveals,
  preserving every original word and punctuation. Register approved directions
  in `generated/narration.json`: language -> chapter number -> passage array
  or a relative JSON filename. The renderer loads this map automatically.
  Undirected chapters use continuous audiobook narration at `-12%`.
  Do not claim all chapters have hand-directed delivery if only some do.
- Use `--narration-engine edge` only when explicitly choosing legacy behavior.
  Check saved SSML, narration provenance, cache behavior, and final timestamps.

- Use the story renderer; do not generate or publish files by hand:

  ```sh
  .venv/bin/python code/story_course.py --source-language sv --target pl
  ```

- Defaults are the whole Polish chapter, vocabulary practice with Swedish
  prompts and Polish targets, then the identical whole chapter again. Reuse
  the same narration clip for both readings; do not synthesize twice.
  Record both timestamps in chronological `chapter_readings` order and keep
  `chapter_reading` pointing to the final reading for compatibility.
  Separate story and practice in both directions with the locally generated
  quiet two-note chime and configured repetition pauses. Record chime
  timestamps and directions in `transitions`.
  Practice contains vocabulary only in a deterministic
  shuffled order within each chapter; preserve stable IDs and keep the story
  sentences in their original order. Story sentences are not individually
  translated or practiced. Every vocabulary target is played twice with the
  configured pauses.
- The default Swedish and Polish practice rates are both `-15%`; preserve these
  beginner-friendly rates unless the user requests a change.
- Speak the book title once at the beginning of chapter 1, before the first
  reading. Record it as a separate `book_introduction` manifest segment and
  do not repeat it in the full chapter reading.
- Announce each chapter's target-language number and title ("Rozdział
  drugi. Głos z radia.", `CHAPTER_HEADINGS`) with the narration voice; bare
  short titles can make expressive narrators switch into character voices.
  Announce it before its first reading, after the book title in chapter 1.
  Follow it with the configured repetition pause. Record `chapter_introduction` in
  both the audio manifest and build manifest; do not repeat the title later.
- Pass voice, rate, pitch, pauses, format, duration cap, paths, and podcast
  settings as CLI arguments when requested; check `--help` for current options.
- Use a duration cap only for an intentional validation preview. A cap rejects
  a chapter that would exceed it; it never publishes partial chapters.
- Check TTS availability and FFmpeg prerequisites. TTS sends text to Azure Speech
  (credentials in `.env`).
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
  chapter MP3s are moved (not copied) to `podcast/swedish-polish/audio/stories/<id>/`
  so each episode exists once; timing JSON stays in `generated/audio/`.
- Use `--cover` to select story artwork explicitly; otherwise packaging looks
  for `cover_se_pl.jpeg` for Swedish-to-Polish (or the matching direction),
  then the shared `cover.jpeg`, then legacy `cover.jpg`. A story cover is
  required even for an existing show.
- For another target (for example Swedish-to-English), add a full-chapter
  `chapter_text` translation for that language, then render with
  `--target en --package-podcast --podcast-course swedish-english`. Renders
  default to `generated/audio/<source>_<targets>/`; the shared build manifest
  keeps other targets' entries and records per-direction `renders`.
  Packaging copies it to `images/stories/<id>/cover.jpeg` and assigns it to
  every chapter via episode-level `itunes:image`, without replacing show art.
- When creating a separate feed instead, verify artwork and public owner
  metadata; owner email is exposed in RSS. Preserve existing episode GUIDs
  and publication dates when updating.
- Run the podcast tests and RSS builder. Verify episode counts, enclosures,
  actual file sizes, cover links, and target-language feed URLs.
- Publishing is separate: never commit, push, or submit a show to Spotify
  unless explicitly authorized.
