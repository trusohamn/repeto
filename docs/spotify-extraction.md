# Local Spotify episode extraction

The local collector visits public Spotify show pages, clicks **Load more
episodes** until it disappears, and extracts each episode's title, Spotify URL,
and Repeto transcript URL. It uses ordinary Playwright Chromium with an anonymous
session: no Spotify account, Premium subscription, Developer app, API secrets,
Azure, or R2 access is required. No LLM guesses episode IDs.

The former Web API synchronizer and daily workflow have been removed. The API
attempt obtained a token but received HTTP 403 for show episodes; the app owner
did not have the Premium subscription currently required for development-mode
Web API access. Browser extraction is independent of that API.

## Install

From the repository root, complete the [standard Python setup](../README.md#1-set-up),
then install the optional collector dependency and its browser:

```sh
.venv/bin/python -m pip install -r requirements-spotify.txt
.venv/bin/python -m playwright install chromium
```

These are local installations, not GitHub Actions configuration. The collector
does not read `.env` or use credentials. Existing `SPOTIFY_CLIENT_ID` and
`SPOTIFY_CLIENT_SECRET` repository secrets can be removed in **Settings >
Secrets and variables > Actions** if no other integration uses them.

Each selected catalog needs the actual show URL in `links.Spotify`:

```json
{
  "links": {
    "Spotify": "https://open.spotify.com/show/SHOW_ID"
  }
}
```

Replace `SHOW_ID` with the show's 22-character ID, not an episode ID or search
URL. Existing catalog metadata and audio are not otherwise changed.

## Extract without changing catalogs

```sh
# Every configured show, sequentially.
.venv/bin/python code/spotify_extract.py

# One show (repeat --course for several).
.venv/bin/python code/spotify_extract.py --course english-french

# Watch the browser when investigating a failure.
.venv/bin/python code/spotify_extract.py --course english-french --headed
```

The default output is `output/spotify-extract.json`, which is git-ignored.
The browser window is visible by default. `--headless` is optional, but public
rendering can differ; a headless live attempt returned no episode cards while
the normal visible browser loaded successfully. No access restriction is bypassed.
`--output PATH` changes the destination; each run replaces that report, so use
different paths to retain snapshots. `--root PATH` selects another catalog root;
`--base-url https://example.com` selects the exact transcript-site prefix.

The JSON contains a collection timestamp and one result per selected course:
show URL, extracted episode metadata, exact matches keyed by permanent Repeto
episode ID, completeness, and explicit issues. Failed shows retain their error
in the report and do not prevent attempting the other shows. Console output
gives matched/expected counts. Exit status is zero only when all selected
courses match completely; failures return nonzero.

Courses without a show URL are explicitly skipped when scanning all catalogs.
Explicitly selecting such a course, an unknown course, or an invalid show URL
is an error. Initial configuration/browser startup errors print a diagnostic
and may occur before a report can be written.

## Apply complete mappings

Inspect the report, then run again with the explicit mutation flag:

```sh
.venv/bin/python code/spotify_extract.py --course english-french --apply
git diff -- podcast
```

`--apply` performs a fresh extraction. Every selected catalog must have complete,
unambiguous coverage before any catalog is written. One failing show blocks
updates to all selected catalogs; narrow `--course` to apply independently
verified shows. The collector:

- Requires an exact canonical transcript URL for every local episode.
- Refuses title-only guesses, duplicate Spotify IDs, multiple transcript
  URLs in a card, unknown transcript URLs, and competing matches.
- Checks the catalog has not changed during collection.
- Sets `spotify_show_id` and each episode's `spotify_episode_id` using the
  existing website schema; it never deletes mappings because a scrape missed
  an episode.

Review changes on a separate branch and PR. The site build uses stored IDs;
it never contacts Spotify. A valid episode mapping renders a lazy-loaded,
accessible Spotify player and direct episode link on its transcript page.
The show-level Spotify button is only shown when no episode player is available,
avoiding duplicate "Listen on Spotify" links.

Course pages with mappings show one large Spotify player above the episode list,
starting with the first mapped episode. Each mapped episode number becomes a
play button: one click switches the player to that episode and starts it from 0:00 through
Spotify's Embed iFrame API. Without JavaScript or if that API fails to load, the
static player still works and clicking a row loads the episode without autoplay.
Spotify decides playback; signed-out listeners may only get previews. The
player does not automatically advance to the next episode.
Mappings are bound to the current show ID so changing a show does not embed
episodes from the previous show.

Extraction does not rebuild feeds, start audio generation, create a PR, merge,
deploy, or submit anything to Spotify. Existing course publication gates still
apply. Nothing runs on a timer; to stop discovery, simply do not run the script.
The old hosted daily workflow has also been manually disabled, so it no longer
runs while the code-removal change awaits merge. Its definition is removed
from the default branch only when this change is merged.

## Limits and failure recovery

Spotify's public UI is not a supported extraction API. Markup, localization,
regional availability, consent dialogs, and public access can change. Respect
Spotify's applicable terms; do not bypass login, challenges, or access controls.
The collector does not use private endpoints, session tokens, stealth plugins,
or retries designed to evade restrictions.

The browser uses English UI, rejects optional cookies when the control is
available, waits for pagination progress, and bounds loading to 100 clicks.
An unchanged episode count after clicking load-more is an error. A disappearing
control alone is not proof of completeness: exact coverage of the selected
catalog is also mandatory. This verifies all catalog episodes, not an
independently known total of unpublished or inaccessible Spotify episodes.
Unexpected extra episodes are reported for manual investigation.

If a show fails:

1. Inspect its `issues` in the report; rerun that course with `--headed`.
2. Check the public show in a normal signed-out browser and confirm the actual
   show URL and the transcript URL in each description.
3. If Spotify has not ingested all episodes, wait and rerun on demand.
4. For missing browser executables, rerun the Chromium installation command.
5. If the public markup changed, update the collector and fixture tests; do not
   relax exact matching or apply partial data to force success.

## Developer validation

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_spotify*.py' -v
.venv/bin/python -m unittest discover -s tests -p 'test_podcast.py' -v
.venv/bin/python -m pyright code/spotify_extract.py tests/test_spotify_extract.py
```

Browser fixture tests use intercepted local HTML, not the live service, and
require the optional Playwright package and Chromium. They are explicitly
skipped if Playwright or Chromium is absent; the pure matching/safety tests
still run. Developer requirements include the optional Python dependency for
type checking; browser installation remains explicit.
Validate the live service separately with the report-only command and check
the actual matched/expected counts. Never claim a fixture-only run proves
current Spotify access or all-show completeness.

The initial local live verification extracted and exactly matched all 646
catalog episodes across all 17 configured shows (38 per show: 30 practice
topics and 8 story chapters). It was report-only: no catalogs or audio changed.
This records that run, not a guarantee of future public-page availability.
