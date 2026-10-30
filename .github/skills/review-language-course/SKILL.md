---
name: review-language-course
description: Translate or carefully review Repeto language-course phrases, stories and learner-facing copy; verify meaning, natural everyday usage, regional consistency and synchronized audio before packaging. Use before rendering a new language or when correcting an existing course.
---

# Translate and review a Repeto course

## Establish the scope

- Read `courses/REQUIREMENTS.md`, the current transcript, and the relevant
  `create-story-course` and `package-podcast` skills.
- Confirm source, target, regional variety, audience and requested deliverables.
  Spain Spanish and Mexican Spanish are not interchangeable defaults.
- Inspect the worktree and existing course catalogs. Preserve user edits,
  original story text, covers and publication settings. Never commit, push or
  submit to a podcast platform without permission.
- Keep credentials private. Only established speech helpers may load them.
- Save a pre-edit content baseline outside the tracked course data. Determine
  counts from the actual files; do not assume a fixed number of phrases.

## Translate for listeners, not word-for-word matching

- Read every source phrase and its topic. For stories, read every whole chapter,
  chapter title and vocabulary item. Search and automated flags are aids, not
  evidence of a complete linguistic review.
- Preserve the intended situation, tone, number, person, negation, time and
  degree of certainty. Check against the original language, not solely an
  intermediate English translation.
- Prefer common everyday speech appropriate to beginners and children.
  Do not make short idioms formal merely to make them more explicit:
  `Wesołych Świąt!` is a normal Christmas greeting in context.
- Distinguish an error from a valid alternative or stylistic preference.
  Explain uncertain choices rather than confidently "correcting" them.
  For example, `glows gold` is grammatical; `glows with a golden light`
  can be clearer. Swedish `målar med pensel` does not require an article.
- Preserve existing grammatical gender where the source specifies it.
  Where it does not, choose a consistent usable form or a genuinely natural
  neutral construction. Do not insert spoken slash or parenthetical alternatives.
- Translate informal singular/plural address deliberately. Use Spain Spanish
  `tú` and `vosotros` where appropriate; keep regional vocabulary consistent.
- Check language-specific distinctions: Swedish `en/ett`, adjective agreement,
  verb particles and reflexives; Polish case, aspect and numerals; Spanish
  articles, agreement, `ser/estar`, prepositions, accents and question marks.
- A narrative present does not mean every English verb should be simple present.
  Use the form natural for what is happening in the scene. Do not mechanically
  convert an entire story to the progressive.
- Preserve intentional story magic without inventing events or explanations.
  Keep localized character names and magic words consistent across chapters.

## Check meaning across the learning pair

- Ask whether a learner answering the source prompt would reasonably produce
  the target answer. A fluent target sentence with a different meaning fails.
- Check easily confused concepts, such as shoulder/arm, hand/palm,
  cheerful/excited/nervous, lending/borrowing and forgetting/forgetting to do.
- Watch for distinctions that the source does not encode. Swedish
  `farmor/mormor`, `farfar/morfar`, `moster/faster` and `morbror/farbror`
  need explicit teaching choices; do not present one as the only translation
  of a general grandparent, aunt or uncle.
- Requests and classroom commands need idiomatic equivalents, not just
  dictionary verbs: a command to get up from a chair differs from a description
  of standing. Sharing toys is not dividing them into pieces.
- Keep vocabulary useful for the actual story. Check noun sense and verb usage
  in context, not merely whether a dictionary offers that translation.
- Review titles as titles. Avoid literal labels such as "The Stairs Going Down"
  when "Down the Stairs" is the natural heading.
- Review all language mentions in instructions, congratulations and recap
  phrases. Shared content must not tell an English or Spanish learner to
  answer in Polish accidentally. Check the whole recap, not one spotted phrase.
  Keep ordinary example sentences about Poland or Polish when they genuinely
  teach that meaning; not every language mention is an instruction.
- Review topic names, source-language summaries, show descriptions and UI labels
  as well as spoken text.

## Review before spending on speech

- Finish a full linguistic pass before rendering. Maintain a compact change
  list with permanent ID or chapter, language, old/new wording and reason.
- For a large new translation, a separate-context review may help, but it does
  not constitute native-speaker certification. Give it a complete bounded scope.
  Do not ask multiple agents to repeat the same review without a distinct need.
- Resolve high-confidence errors; flag material ambiguity for the user rather
  than changing the approved source or plot to fit a convenient translation.
- Preserve every existing ID, topic, chapter number and ordering unless a
  structural change is explicitly requested. Never renumber to close gaps.

## Validate text and synchronization separately

Use the configured project interpreter and existing validators and tests.

1. **Structure:** parse the actual dataset, verify unique stable IDs, expected
   language coverage, trimmed nonempty strings, and no TTS placeholders.
   Use `transcription.load_topics` and `story_course.load_transcript`; the latter
   must reconstruct the approved Polish original exactly.
2. **Linguistics:** inspect all entries as described above. Passing a JSON
   parser, unit test or type checker does not establish correct natural language.
3. **Regression:** add focused tests for concrete mistakes and direction-neutral
   instructions, not claims that an automated test proves all grammar correct.
4. **Impact:** identify every packaged direction using each changed language.
   Practice historically uses Swedish `se`; stories and catalogs use `sv`.
   Compare the pre-edit baseline and packaged timing text, not just the git diff.
5. **Audio:** synthesize only changed clips, reusing unchanged narration and
   vocabulary clips. Recompose only affected episodes through existing helpers.
   Keep both story readings consistent; preserve book and chapter introductions,
   chimes, pauses and narration voice settings.
6. **Artifacts:** update timing JSON, build manifest, catalog, RSS and pages
   together. Editing timing labels alone does not change the recorded speech.
   Preserve episode GUIDs, publication dates and season/episode numbers.
7. **Verification:** decode changed MP3s; check text, bounds, non-silent segments,
   sample rate, duration, repetitions and pauses. Confirm every enclosure's path
   and actual byte length, including after the final feed rebuild. Verify
   unaffected episodes are unchanged when claiming they were preserved.

Use the packaging skill for staging and final feed checks. Avoid duplicating
entire audio libraries; remove only known superseded files after successful
replacement and validation.

## Listening and honest completion

- Signal analysis cannot detect all extra spoken words, bad pronunciation,
  misplaced stress, odd voices or unnatural delivery. These need listening.
- For new voices, prioritize a short sample with questions, numbers, commands
  and dialogue before rendering everything. For corrected narration, listen
  around the edited sentence and the start/end where possible.
- If direct listening is unavailable, state that explicitly. Never claim to
  have heard an artifact disappear based only on silence detection.
- Report the actual coverage, substantive examples, affected courses and
  validation results. Separate linguistic review, machine checks and listening.
  Do not call a course error-free, native-reviewed or published unless verified.
