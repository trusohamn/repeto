---
name: create-language-course
description: Create a complete Repeto source-to-target language course, including translation review, all practice topics, the existing story season, audio, timing manifests, podcast catalog, RSS and course page. Use for requests such as "create a Swedish-Spanish course"; do not interpret an unqualified course request as practice-only.
---

# Create a complete language course

## Scope and completion contract

An unqualified request to create a language course means the complete Repeto
course: season 1 with all shared practice topics and season 2 with all chapters
of the existing `magical_radio` story. Do not stop after practice packaging.
Only omit a season when the user explicitly requests practice-only or
story-only material. If the existing story lacks the requested translation,
resolve that gap before rendering; never silently leave the story out.
Do not invent a different story unless requested.

Use this skill as the orchestration checklist, together with:

- [Language review](../review-language-course/SKILL.md)
- [Story creation](../create-story-course/SKILL.md)
- [Podcast packaging](../package-podcast/SKILL.md)

Track practice review/render/package and story review/render/package separately.
Mark the course complete only after both seasons and the final feed pass
verification. A running render, an empty course directory, a cover, or a
practice-only feed is not a completed course.

## Establish the direction and preserve existing work

- Identify the source prompt language, target language, regional variety,
  course slug, artwork and existing catalog. Follow configured regional
  defaults; ask when the requested variety or direction is ambiguous.
- Read `courses/REQUIREMENTS.md`, `REQUIREMENTS.md`, the component skills,
  transcripts, narration settings and catalog before acting.
- Check Git status. Preserve user edits, artwork, contact settings, links,
  existing episode GUIDs, publication dates and season/episode identities.
- Configure the project interpreter. Run commands from the repository root,
  not the parent workspace directory.
- Practice uses Swedish `se`; stories and catalogs use Swedish `sv`.
  Spain Spanish uses `es` throughout. Do not interchange these codes.
  Germany German is `de` and France French is `fr`; Spanish, German and French
  are optional per practice entry, so a new target needs every entry, topic,
  chapter title and vocabulary item translated before rendering.
- Keep one shared practice source at `courses/practice/transcript.json`.
  Do not fork the entire corpus into a direction-specific transcript folder.
- Shared story data lives under `courses/stories/magical_radio/`.
  Use its existing full-chapter translations and stable vocabulary IDs.

## Review translations before synthesis

Follow the language-review skill for every practice phrase and every story
chapter, title, vocabulary item and source-language teaser.
Review source-to-target meaning directly, not only via an English pivot.
Preserve natural everyday wording; gender neutrality alone is not a reason
to replace a valid idiom with a less natural or less faithful sentence.
Flag meaningful ambiguities rather than silently changing the source.

Save a content baseline outside tracked course data. Count actual topics,
chapters and vocabulary entries; never assume that a historical count still
applies. Resolve high-confidence mistakes and record substantive changes.
For shared-text edits affecting existing catalog directions, use the approved
PR audio workflow described in [deployment](../../../docs/deploy.md): inspect
the inferred targets, authorize generation with `publish-audio`, review staged
audio and merge only after approval. Story generation selects affected chapters;
practice generation selects affected topics. Do not independently commit
generated MP3s for that workflow. Updating an existing course is a dependency,
not a substitute for creating the new course.

## Prepare locally, generate on the pipeline

Prepare both seasons' text, artwork, episode catalog and draft RSS locally,
before opening the PR. Pending episodes must not contain invented audio
durations, file sizes or checksums. The draft feed is for review, not
publication. Use the local draft packaging command described in the
[deployment guide](../../../docs/deploy.md).

On PR open the target report identifies pending and changed recordings without
calling speech services. Check its scope, then only add `publish-audio` when
authorized. The pipeline renders the selected practice topics and story
chapters, fills real audio metadata, stages the recordings and updates the PR
feed. Review the links and final diff before merge; promotion uses those exact
reviewed bytes. Do not generate paid audio locally as a substitute.

The story narration language is the target, not the source. Preserve the book
and chapter introductions, two whole-chapter readings, chimes, vocabulary
practice and double target playback. Updating existing directions affected by
shared text is also required, not a substitute for creating the new course.

## Verify the complete course

- The catalog must contain every current practice topic in season 1 and
  every story chapter in season 2, with no missing or duplicate episodes.
- Decode every new MP3. Check sample rate, durations, complete entry IDs and
  text, bounds, non-silent speech, pauses and both target playbacks.
- Check story narration provenance, both full readings, introductions,
  transitions and vocabulary. Verify the approved original is preserved.
- Parse the final RSS; check unique stable GUIDs, season/episode identities,
  publication dates, duration, every enclosure's actual byte length and path,
  show cover and story episode artwork.
- Confirm the course page shows both seasons and descriptions mention the
  story. Check the homepage links to the new course.
- Run relevant existing renderer, story and podcast tests. Passing machine
  checks is not native-speaker certification or a listening review.
- Verify unchanged episodes and unrelated courses remain unchanged.
- If a command fails, resolve the error and resume from completed artifacts.
  Report an unresolved blocker rather than announcing a completed course.

## Handoff

Report practice and story coverage separately, total audio duration, validation
results and any listening limitations. Link the final course page and RSS.
Register those deliverables as artifacts, not temporary renders or staging.
Do not commit, push, deploy or submit the feed to a podcast platform without
explicit permission. Local creation is not publication.
