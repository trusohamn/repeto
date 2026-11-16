# Spotify episode synchronization

Repeto uses the Spotify Web API to retrieve public episodes for each configured
show. The static-site build does not contact Spotify. A separate GitHub Actions
workflow runs daily at 06:15 UTC, independently of podcast deployments.
The synchronizer opens or updates a pull request when episode mappings change.
A maintainer reviews and merges that metadata PR before the episode embeds
appear on the site.

The workflow can also be started manually from the Actions tab on `main`;
both triggers execute code from `main`, without a deployment-related delay.
Spotify ingestion can take time: if episodes are still missing, the next daily
run retries discovery, or a maintainer can rerun manually sooner. If the
mappings have not changed, no further PR is created.

## One-time setup

This integration is optional. It does not generate audio or submit a podcast to
Spotify. Before enabling it, publish the podcast feed and confirm the show is
available on Spotify.

1. Sign in to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
   and create or select an app with Web API access. Follow Spotify's current
   account, app-creation, and quota requirements; a Spotify for Creators account
   alone is not an API credential. In the app settings, obtain the **Client ID**
   and **Client Secret**. This server-side client-credentials integration does
   not use a redirect callback or listener authorization.
2. Verify each course has its actual show URL in `podcast/<course>/course.json`:

   ```json
   {
     "links": {
       "Spotify": "https://open.spotify.com/show/SHOW_ID"
     }
   }
   ```

   Replace `SHOW_ID` with the show's 22-character Spotify ID. Search links and
   episode links are not show URLs. Keep any existing links and catalog fields.
3. In the GitHub repository, open **Settings > Secrets and variables > Actions >
   Repository secrets > New repository secret** and add `SPOTIFY_CLIENT_ID` and
   `SPOTIFY_CLIENT_SECRET`. These are repository secrets, not `audio-production`
   environment secrets. Alternatively, use the interactive CLI prompts:

   ```sh
   gh secret set SPOTIFY_CLIENT_ID --repo trusohamn/repeto
   gh secret set SPOTIFY_CLIENT_SECRET --repo trusohamn/repeto
   ```

   Do not paste credentials into chat, commit them, or put their values in
   command-line arguments. Rotate the secret in Spotify and replace the GitHub
   secret if it is exposed.
4. Under **Settings > Actions > General > Workflow permissions**, enable
   **Allow GitHub Actions to create and approve pull requests**. The workflow
   requests `contents: write` and `pull-requests: write`; repository or
   organization policies must allow those permissions and the actions used in
   [spotify-sync.yml](../.github/workflows/spotify-sync.yml). It creates PRs but
   does not approve or merge them.
5. Merge the reviewed integration code into `main` before expecting scheduled
   or manual runs there. Keep the existing audio publication safeguards.
   The workflow's `SPOTIFY_MARKET` is currently `US`; change that workflow
   value if another market is required. A repository variable of the same
   name does not override the hard-coded workflow value.
6. Follow [First live verification](#first-live-verification) rather than
   assuming configured secrets imply working API access.

## Local setup and safe live test

Use the Python environment from the [main setup guide](../README.md#1-set-up).
Spotify synchronization needs no Azure or R2 credentials. For local use, add
the optional Spotify values to the git-ignored `.env`, using
[.env.example](../.env.example) as the list of variable names.
The sync script reads environment variables; it does **not** load `.env`
automatically.

Run this from the repository root to explicitly load `.env` and test real API
retrieval and matching against temporary copies of the catalogs. It prints
the sync report without changing tracked catalogs, rendering audio, or
publishing anything:

```sh
.venv/bin/python - <<'PY'
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from dotenv import load_dotenv

load_dotenv(".env")
with tempfile.TemporaryDirectory(prefix="repeto-spotify-") as directory:
    root = Path(directory)
    for catalog in Path("podcast").glob("*/course.json"):
        destination = root / catalog.parent.name
        destination.mkdir()
        shutil.copy2(catalog, destination / "course.json")
    subprocess.run(
        [sys.executable, "code/spotify_sync.py", "--root", str(root)],
        env=os.environ.copy(),
        check=True,
    )
PY
```

For intentional updates to the working catalogs, export the credentials into
the process environment using your local secret-management method, then run:

```sh
.venv/bin/python code/spotify_sync.py --root podcast
git diff -- podcast
```

Use `--base-url https://YOUR-SITE` for a fork hosted elsewhere; it must match
the transcript URLs in that site's feeds. Local `SPOTIFY_MARKET` defaults to
`US` and can be set in the environment or the explicitly loaded `.env`.

## First live verification

1. Run the temporary-copy local test above. A real verification requires an
   OAuth token response and successful episode retrieval for the configured
   shows. Mocked unit tests do not establish that the app has API access.
2. Inspect the report for the expected show/course counts and matched
   episodes. Investigate missing and ambiguous matches; a successful process
   exit can still report zero matches and does not prove matching succeeded.
3. After the integration is on `main`, open **Actions > Sync Spotify episode
   IDs > Run workflow**, select `main`, and start the run. Or use:

   ```sh
   gh workflow run spotify-sync.yml --ref main --repo trusohamn/repeto
   gh run list --workflow spotify-sync.yml --limit 5 --repo trusohamn/repeto
   ```

4. Open that run's logs and summary. If mappings changed, review the
   `automation/spotify-episode-sync` PR: only course catalogs should change,
   with `spotify_show_id` and per-episode `spotify_episode_id` mappings.
   Verify representative IDs on Spotify. If nothing changed, no PR is expected.
5. Review and merge the metadata PR separately, then confirm **Publish
   podcasts** succeeded. On a matched episode page, verify the player and
   direct episode link refer to the correct recording, including on mobile.
   Unmatched pages should retain the show link without a guessed player.

PRs opened with the workflow's default GitHub token do not automatically
trigger other PR workflows. Do not treat absent checks as passing; run the
relevant local checks or use the repository's approved manual verification
process before merging. Never bypass pending-audio publication gates.

The initial implementation was tested with mocked Spotify responses, not
live app credentials. Complete this live verification before treating the
integration as operational.

## Troubleshooting and disabling

| Symptom | Action |
| --- | --- |
| Missing-credentials error | Check both repository secrets, or the local process environment. The script does not read `.env` by itself. |
| HTTP 400 or 401 | Check the app credentials and rotate/reconfigure them if necessary. |
| HTTP 403 | Check the app's API access, account eligibility, quota mode, and organization restrictions; do not assume public shows bypass app restrictions. |
| HTTP 404 or unavailable show | Confirm the configured show ID and market, and verify that Spotify has ingested the show. |
| HTTP 429 | Let the bounded retry finish; if it fails, rerun later rather than repeatedly starting jobs. |
| Missing or ambiguous matches | Inspect the report, titles and transcript links, and Spotify ingestion status. The next daily run retries discovery; manual reruns are available. |
| PR creation denied | Check Actions PR-creation settings, token permissions, and organization policies. |
| Manual workflow absent or run skipped | Confirm the workflow is on `main` and the selected ref is `main`. |

Daily scheduling is best-effort: GitHub can delay scheduled jobs. On an inactive
public repository, GitHub may disable scheduled workflows; check Actions if
runs stop. To pause synchronization, disable **Sync Spotify episode IDs** in
the Actions UI. This does not disable podcast deployment or remove existing
players. Re-enable it to resume discovery. Changes and removals of stored
mappings are proposed in a PR rather than deployed automatically.

## Data source and platform limits

The synchronizer uses Spotify's
[Get Show Episodes endpoint](https://developer.spotify.com/documentation/web-api/reference/get-a-shows-episodes)
and [Client Credentials flow](https://developer.spotify.com/documentation/web-api/tutorials/client-credentials-flow).
It fetches every page (50 episodes per request) in the configured market. It
needs a Spotify Developer app's **Client ID** and **Client Secret**; it does not
need a listener's account or user scopes.

The optional `SPOTIFY_MARKET` environment variable selects the two-letter
country market; the workflow defaults to `US`. Availability can vary by market.
The Web API also enforces app quotas and rate limits; the synchronizer honors
`Retry-After` for a small bounded number of `429` retries (up to 60 seconds per
retry), then fails without writing partial catalog updates. It reads at most
200 pages (10,000 episodes) per show. Spotify Developer Mode has quota
restrictions, and API access depends on Spotify's current developer policies
and app status.

## Matching and playback behavior

Each RSS item already includes its transcript-page URL in the description. The
synchronizer first uses that URL as a stable identifier. If Spotify does not
return it, the synchronizer accepts only a unique exact match for the RSS
episode title, including the episode number. It does not fuzzy-match titles.
Conflicting or missing matches are listed in the workflow run summary and do
not receive a new player ID. The discovered Spotify episode ID is stored as
`spotify_episode_id` on that catalog episode, and the catalog records which
show it belongs to. No episode URLs need to be entered by hand.

Generated episode transcript pages embed Spotify's responsive episode player
only when the episode ID is present and belongs to the currently configured
show. A direct Spotify episode link and the existing show link remain available
as fallbacks. Spotify can delay ingestion, restrict an episode in a market, or
make it unavailable later; in those cases the API may not return a match or the
embed may not play. Missing IDs are reported and omitted rather than guessed.
When retrieval fails, the workflow fails visibly and preserves all existing
catalog data.

Spotify's [rate-limit documentation](https://developer.spotify.com/documentation/web-api/concepts/rate-limits)
and [embed documentation](https://developer.spotify.com/documentation/embeds)
describe platform limits and player behavior. The player is hosted by Spotify
and therefore depends on Spotify availability and its embed terms.
