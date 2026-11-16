# Agent instructions

## Course workflow routing

- For an unqualified request to create a language course, follow
  [create-language-course](.github/skills/create-language-course/SKILL.md).
  A complete course includes both practice and the existing story season
  unless the user explicitly limits the scope.
- Before translating, correcting course text, or rendering a new language
  direction, follow
  [review-language-course](.github/skills/review-language-course/SKILL.md).
- For story authoring and rendering, follow
  [create-story-course](.github/skills/create-story-course/SKILL.md).
- For podcast packaging and feed verification, follow
  [package-podcast](.github/skills/package-podcast/SKILL.md).

The complete-course skill coordinates the component workflows; completing one
component does not complete the course.

## Hard gate for course publication

- A locally packaged course with any `pending_audio: true` episode is a draft.
  It may be committed to a course PR so the approved pipeline can generate
  audio, but it must never be merged to `main`, deployed, or described as
  published while any episode is pending.
- Before merging a course PR, inspect the final catalog and feed: every episode
  must have generated audio metadata, no pending flags, and a production
  enclosure. Confirm the pipeline staged the exact PR revision, listen to and
  review its staging links, and verify the final diff. If any check is absent,
  stop and leave the PR open.
- Merging pipeline code is not approval to generate audio. Only the explicit
  `publish-audio` approval authorizes paid synthesis and staging. Never infer
  that approval from a request to merge or publish code.
- Keep pipeline implementation changes separate from unrendered course data
  when merging infrastructure. If the task is to merge pipeline support,
  exclude pending course catalogs, draft feeds, and course-specific generated
  artwork from that merge.
- A production deployment failure caused by pending course data is a blocker,
  not a successful or harmless deployment. Do not retry deployment or remove
  its safeguard to make a pending course appear live.
