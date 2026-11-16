---
name: sync-spotify-episodes
description: Fetch Spotify episode URLs for Repeto shows from the public Spotify pages and store the verified episode IDs in course catalogs so the site shows players. Use after new episodes appear on Spotify, when a show gets a Spotify link, or when course pages lack episode players.
---

# Sync Spotify episode IDs

Work from the repository root. The full runbook is
[docs/spotify-extraction.md](../../../docs/spotify-extraction.md); this skill
is the short operational path.

## Why a local browser script

The Spotify Web API returns HTTP 403 for show episodes unless the developer
app owner has Premium. Do not reintroduce API credentials, a scheduled
workflow, or LLM/title guessing. `code/spotify_extract.py` opens the public
show page in Playwright Chromium (no login), clicks the text button
**Load more episodes** until it is gone, and matches each card by the exact
Repeto transcript URL in its description.

## Procedure

1. Prerequisites (once per machine, after the standard `.venv` setup):

   ```sh
   .venv/bin/python -m pip install -r requirements-spotify.txt
   .venv/bin/python -m playwright install chromium
   ```

2. Ensure each course has its real show URL in `podcast/<slug>/course.json`
   `links.Spotify` (`https://open.spotify.com/show/<22-char id>`). Courses
   without it are skipped.
3. Start from an up-to-date `main` on a new branch.
4. Report only (no catalog changes; opens a visible browser window):

   ```sh
   env .venv/bin/python code/spotify_extract.py            # all shows
   env .venv/bin/python code/spotify_extract.py --course english-french
   ```

   Check every course prints matched == expected. Details are in
   `output/spotify-extract.json` (git-ignored).
5. Apply (fresh extraction; writes only if every selected course is complete):

   ```sh
   env .venv/bin/python code/spotify_extract.py --apply
   git diff --stat -- podcast
   ```

   The diff should only add `spotify_show_id` and per-episode
   `spotify_episode_id` fields.
6. Validate:

   ```sh
   .venv/bin/python -m unittest discover -s tests -p 'test_spotify*.py'
   .venv/bin/python -m unittest discover -s tests -p 'test_podcast.py'
   ```

7. Commit the catalogs, push and open a PR into `main`. Merging deploys
   the site (`podcast.yml`); after it succeeds, check a live course page
   for `id="course-player"`.

## Pitfalls

- Do not use `--headless` by default: a headless live run rendered no episode
  cards. If the `env` prefix is omitted, the tool shell may sometimes fail with
  "No module named jinja2".
- Episodes Spotify has not ingested yet make a course incomplete; wait and
  rerun rather than applying partial data or relaxing exact matching.
- If public markup changed (no cards, load-more never disappears), rerun with
  the window visible, then fix `code/spotify_extract.js` and its fixture tests.
- This updates only metadata. It never generates audio, so the publication
  gates in `AGENT.md` still apply to any pending course data in the same PR.
