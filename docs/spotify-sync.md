# Spotify episode synchronization

Repeto uses the Spotify Web API to retrieve public episodes for each configured
show. The static-site build does not contact Spotify. After the `Publish
podcasts` workflow successfully deploys from `main`, a separate GitHub Actions
workflow waits 30 minutes for Spotify ingestion, then runs the synchronizer.
Failed deployments do not trigger synchronization, and there is no daily poll.
The synchronizer opens or updates a pull request when episode mappings change.
A maintainer reviews and merges that metadata PR before the episode embeds
appear on the site.

The workflow can also be started manually from the Actions tab on `main`;
manual runs skip the 30-minute delay. Both triggers execute code from `main`.
The delay does not guarantee Spotify has ingested the feed: if episodes are
still missing, check the run summary and rerun manually later. Merging a mapping
PR causes another deployment and post-deployment check; if the mappings have
not changed, no further PR is created.

## Setup and data source

The synchronizer uses Spotify's
[Get Show Episodes endpoint](https://developer.spotify.com/documentation/web-api/reference/get-a-shows-episodes)
and [Client Credentials flow](https://developer.spotify.com/documentation/web-api/tutorials/client-credentials-flow).
It fetches every page (50 episodes per request) in the configured market. It
needs a Spotify Developer app's **Client ID** and **Client Secret**; it does not
need a listener's account or user scopes. Set the GitHub Actions repository
secrets `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET`. For local runs, export
the same variables before running:

```sh
python code/spotify_sync.py --root podcast
```

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
