---
name: review-language-course
redescription: Translate or carefully review Repeto language-course phrases, stories and learner-facing copy, including changed course text in a Git diff; verify meaning, natural everyday usage, regional consistency and synchronized audio before packaging.
---

# Translate and review a Repeto course

## Establish the scope

- Read `courses/REQUIREMENTS.md`, the current transcript, and the relevant
  `create-story-course` and `package-podcast` skills.
- Confirm source, target, regional variety, audience and requested deliverables.
  Spain Spanish and Mexican Spanish are not interchangeable defaults.
- Inspect the worktree and existing course catalogs. Preserve user edits,
  original story text, covers and publication settings. Follow `AGENT.md` for
  branch and PR handling; never submit to a podcast platform without permission.
- Keep credentials private. Only established speech helpers may load them.
- Save a pre-edit content baseline outside the tracked course data. Determine
  counts from the actual files; do not assume a fixed number of phrases.

## Review changed course text in Git

When asked to review current changes, use this skill for linguistic review in
addition to any code review; code correctness and tests do not establish
translation quality. Keep a review-only task read-only unless the user also
asks for corrections.

1. Inspect `git status` and the complete relevant diff, including staged,
   unstaged, and newly added files. Establish exactly which text and metadata
   changed. Do not review only the examples selected by tests or assume a diff
   with no obvious code changes has no learner-facing impact.
2. For every changed practice entry, read every language field, its topic, and
   nearby unchanged entries. Check the source-to-target meaning in context,
   not just the changed language or a pivot translation. For stories, read the
   complete affected chapter and its vocabulary; for topic-title changes, check
   the corresponding phrases and every localized title.
3. Compare changed text to the base version where useful, but do not mistake
   unchanged neighboring text for reviewed new content. Check IDs, ordering,
   duplicate entries, and whether an apparent correction accidentally changes
   approved source text or stable content.
4. Report concrete language issues with the permanent phrase ID (or chapter),
   language, current wording, reason, and a suggested correction when
   confidence is high. Separate definite errors from valid alternatives and
   stylistic preferences. If there are no findings, state what changed text
   and languages were actually reviewed; do not claim a complete review from
   a structural test or a few spot checks.
5. Run relevant structural validators when available, but report separately
   whether linguistic review, machine validation, and audio listening were
   performed. Never imply that tests or text inspection verify recorded audio.
6. End with a short summary of the change and a checklist of applicable
   content-suitability and project checks, marking each passed, failed, or not
   verified. State the basis for each result. A child/family suitability check
   is a content review, not a certification of legal or platform compliance.
7. Estimate the resulting episode duration when changes add or materially
   alter episode content. Identify the assumed language direction and playback
   mode. For practice, include exact configured lead-in and inter-phrase pauses
   from `code/transcription.py`, then estimate speech time using comparable
   rendered manifests or clips for the same voices and playback mode. For
   stories, prefer comparable narration manifests for the same voice and
   narration settings; if none exist, use an explicit reasonable speaking-rate
   range and the chapter word count. Report a rounded range and assumptions,
   not false precision. If the direction or playback mode is unknown, give
   conditional estimates or state what is missing; do not imply an estimate
   is measured audio duration. When a final render manifest exists, report its
   measured duration separately from any pre-render estimate.

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
5. **Audio:** use the [PR audio workflow](../../../docs/deploy.md) for missing
   and changed recordings, including new locally packaged courses. It reuses
   verified cached clips and renders affected practice topics and story
   chapters only. Review staging before merging. Never merge or deploy while any
   course episode is pending, lacks verified audio metadata, or has not had its
   staging audio reviewed. A request to merge pipeline code is not paid-audio
   authorization. Keep both story readings consistent; preserve introductions,
   chimes, pauses and narration settings.
6. **Artifacts:** update timing JSON, build manifest, catalog, RSS and pages
   consistently. The automated workflow commits catalog, RSS and staging
   manifest changes, not temporary renders or timing manifests. Editing timing
   labels alone does not change the recorded speech.
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
  validation results, plus an episode-duration estimate when applicable.
  Summarize checks such as meaning, child/family suitability, rights basis,
  structure and project requirements as passed, failed, or not verified, with
  the evidence and limitations. Separate linguistic review, machine checks and
  listening. Do not claim general legal/platform compliance, error-free
  content, native-speaker review or publication unless those facts are verified.
