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

## Roles, delegation and Git

- Use the [Developer](.github/agents/developer.agent.md) profile for code and
  pipeline work and the [Creator](.github/agents/creator.agent.md) profile for
  course creation and review when a specialized role is useful. Both follow
  these shared instructions and the applicable skills.
- The coordinating assistant is responsible for tracking each delegated
  agent directly. Give it a bounded task and an explicit completion report.
  An agent that was spawned for a task must do that work directly, not spawn
  another agent. If it stops reporting, state that monitoring is unconfirmed
  and investigate or take over instead of claiming active monitoring.
- Use Git and GitHub CLI (`gh`), not GitKraken tools. Preserve user changes and
  use a separate branch and PR into `main`; never push directly to `main`.
  Course PRs should be non-draft by default so they can be reviewed and
  reported on. Respect an explicit instruction to work locally or use a draft.
- Creating a PR, generating audio, merging, promotion and submitting a feed
  are distinct actions. Follow the user's authorization for each. Never infer
  approval for paid generation from a request to create or merge a PR.

## Hard gate for course publication

- A locally packaged course with any `pending_audio: true` episode is a draft.
  It may be committed to a course PR so the approved pipeline can generate
  audio, but it must never be merged to `main`, deployed, or described as
  published while any episode is pending.
- Before merging a course PR, inspect the final catalog and feed: every episode
  must have generated audio metadata, no pending flags, and a production
  enclosure. Confirm the staging manifest identifies the approved input
  revision, its input fingerprint and staged objects match the final PR data,
  and the final diff contains no unreviewed changes. The workflow's subsequent
  metadata commit can make the final head SHA differ from the approved input
  SHA. Listen to and review the staging links; if any check is absent, stop
  and leave the PR open. Generation approval alone is not merge approval.
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
- After an authorized generation run, verify the actual run result, catalog,
  staging manifest and feed; do not assume completion from a running agent.
  Production feed enclosures use the production audio domain and can remain
  unavailable until promotion after merge. Use staging links for review.
