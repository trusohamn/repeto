"""Synchronize Spotify episode IDs into podcast course catalogs."""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
import website

BASE_URL = 'https://repeto.stream'
API_URL = 'https://api.spotify.com/v1'
TOKEN_URL = 'https://accounts.spotify.com/api/token'
PAGE_SIZE = 50
MAX_PAGES = 200
REQUEST_TIMEOUT = 30
MAX_RETRIES = 2
MAX_RETRY_DELAY = 60
SPOTIFY_EPISODE_ID = re.compile(r'^[A-Za-z0-9]{22}$')


class SpotifySyncError(RuntimeError):
    """A Spotify API or synchronization error that should stop the sync."""


class SpotifyClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        market: str = 'US',
        *,
        opener: Callable = urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not client_id or not client_secret:
            raise SpotifySyncError('Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET.')
        if re.fullmatch(r'[A-Z]{2}', market) is None:
            raise SpotifySyncError('SPOTIFY_MARKET must be a two-letter uppercase country code.')
        self.client_id = client_id
        self.client_secret = client_secret
        self.market = market
        self.opener = opener
        self.sleeper = sleeper
        self._token: str | None = None

    @classmethod
    def from_env(cls) -> SpotifyClient:
        return cls(
            os.environ.get('SPOTIFY_CLIENT_ID', ''),
            os.environ.get('SPOTIFY_CLIENT_SECRET', ''),
            os.environ.get('SPOTIFY_MARKET', 'US').upper(),
        )

    def _request_json(self, request: Request) -> dict:
        endpoint = urlsplit(request.full_url).path
        for attempt in range(MAX_RETRIES + 1):
            try:
                with self.opener(request, timeout=REQUEST_TIMEOUT) as response:
                    raw = response.read()
            except HTTPError as error:
                if error.code == 429 and attempt < MAX_RETRIES:
                    try:
                        retry_after = int((error.headers or {}).get('Retry-After', '1'))
                    except (TypeError, ValueError):
                        retry_after = 1
                    if retry_after > MAX_RETRY_DELAY:
                        raise SpotifySyncError(
                            f'Spotify requested a {retry_after}-second rate-limit delay; aborting without an early retry.'
                        ) from error
                    self.sleeper(max(retry_after, 0))
                    continue
                raise SpotifySyncError(f'Spotify returned HTTP {error.code} for {endpoint}.') from error
            except (URLError, TimeoutError) as error:
                raise SpotifySyncError(f'Spotify request failed for {endpoint}: {error.reason if isinstance(error, URLError) else error}.') from error

            try:
                payload = json.loads(raw.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise SpotifySyncError(f'Spotify returned invalid JSON for {endpoint}.') from error
            if not isinstance(payload, dict):
                raise SpotifySyncError(f'Spotify returned an unexpected response for {endpoint}.')
            return payload
        raise SpotifySyncError(f'Spotify rate limit retries exhausted for {endpoint}.')

    def access_token(self) -> str:
        if self._token:
            return self._token
        credentials = base64.b64encode(f'{self.client_id}:{self.client_secret}'.encode()).decode('ascii')
        request = Request(
            TOKEN_URL,
            data=urlencode({'grant_type': 'client_credentials'}).encode(),
            headers={
                'Authorization': f'Basic {credentials}',
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            method='POST',
        )
        response = self._request_json(request)
        token = response.get('access_token')
        if not isinstance(token, str) or not token:
            raise SpotifySyncError('Spotify token response did not contain an access token.')
        self._token = token
        return token

    def show_episodes(self, show_id: str) -> list[dict]:
        token = self.access_token()
        offset = 0
        url = f'{API_URL}/shows/{show_id}/episodes?{urlencode({"limit": PAGE_SIZE, "offset": offset, "market": self.market})}'
        visited: set[str] = set()
        episodes: list[dict] = []
        for _ in range(MAX_PAGES):
            if url in visited:
                raise SpotifySyncError(f'Spotify repeated an episode page for show {show_id}.')
            visited.add(url)
            request = Request(url, headers={'Authorization': f'Bearer {token}'})
            page = self._request_json(request)
            items = page.get('items')
            if not isinstance(items, list):
                raise SpotifySyncError(f'Spotify episode page for show {show_id} has no items list.')
            episodes.extend(item for item in items if isinstance(item, dict))
            next_url = page.get('next')
            if next_url is None:
                return episodes
            if not isinstance(next_url, str):
                raise SpotifySyncError(f'Spotify returned an invalid next-page URL for show {show_id}.')
            parsed = urlsplit(next_url)
            expected_path = f'/v1/shows/{show_id}/episodes'
            query = parse_qs(parsed.query)
            try:
                next_offset = int(query['offset'][0])
            except (KeyError, IndexError, ValueError) as error:
                raise SpotifySyncError(f'Spotify returned an invalid next-page offset for show {show_id}.') from error
            if (
                parsed.scheme != 'https'
                or parsed.netloc != 'api.spotify.com'
                or parsed.path != expected_path
                or next_offset <= offset
            ):
                raise SpotifySyncError(f'Spotify returned an unsafe or non-advancing page URL for show {show_id}.')
            offset = next_offset
            url = next_url
        raise SpotifySyncError(f'Spotify returned more than {MAX_PAGES} pages (10,000 episodes) for show {show_id}.')


def _normalized(value: str) -> str:
    return re.sub(r'\s+', ' ', value.strip()).casefold()


def _descriptions(episode: dict) -> str:
    values = (episode.get('description'), episode.get('html_description'))
    return '\n'.join(html.unescape(value) for value in values if isinstance(value, str))


def _episode_page(base_url: str, slug: str, episode: dict) -> str:
    return website.episode_url(base_url, slug, episode)


def match_episodes(
    course: dict,
    spotify_episodes: list[dict],
    base_url: str = BASE_URL,
) -> tuple[dict[str, str], list[str]]:
    """Match only by the stable transcript URL or a unique exact RSS episode title."""
    messages: list[str] = []
    eligible: dict[str, dict] = {}
    duplicate_ids: set[str] = set()
    for candidate in spotify_episodes:
        spotify_id = candidate.get('id')
        if not isinstance(spotify_id, str) or SPOTIFY_EPISODE_ID.fullmatch(spotify_id) is None:
            messages.append(f'Skipped Spotify episode with an invalid ID: {candidate.get("name", "(untitled)")!r}.')
            continue
        if candidate.get('is_playable') is False:
            messages.append(f'Spotify episode is unavailable in the configured market: {candidate.get("name", spotify_id)!r}.')
            continue
        if spotify_id in eligible:
            duplicate_ids.add(spotify_id)
        eligible[spotify_id] = candidate
    for spotify_id in duplicate_ids:
        eligible.pop(spotify_id, None)
        messages.append(f'Skipped duplicate Spotify episode ID {spotify_id}.')

    episodes = course.get('episodes', [])
    assigned: dict[str, str] = {}
    assigned_ids: dict[str, str] = {}
    blocked: set[str] = set()
    expected_pages: dict[str, str] = {}
    for episode in episodes:
        episode_id = episode['id']
        expected_pages[episode_id] = _episode_page(base_url, course['slug'], episode)
        stored_id = episode.get('spotify_episode_id')
        if stored_id is not None and (
            not isinstance(stored_id, str) or SPOTIFY_EPISODE_ID.fullmatch(stored_id) is None
        ):
            raise SpotifySyncError(f'Invalid stored Spotify episode ID for {course["slug"]}/{episode_id}.')

    for episode in episodes:
        episode_id = episode['id']
        page_url = expected_pages[episode_id]
        hits = [
            spotify_id for spotify_id, candidate in eligible.items()
            if page_url in _descriptions(candidate)
        ]
        if len(hits) > 1:
            blocked.add(episode_id)
            messages.append(f'Ambiguous stable episode link for {course["slug"]}/{episode_id}: {len(hits)} Spotify episodes.')
            continue
        if not hits:
            continue
        spotify_id = hits[0]
        if spotify_id in assigned_ids and assigned_ids[spotify_id] != episode_id:
            blocked.add(episode_id)
            blocked.add(assigned_ids[spotify_id])
            messages.append(f'One Spotify episode links to multiple course episodes in {course["slug"]}; neither was matched.')
            assigned.pop(assigned_ids[spotify_id], None)
            assigned_ids.pop(spotify_id, None)
            continue
        assigned[episode_id] = spotify_id
        assigned_ids[spotify_id] = episode_id

    for episode in episodes:
        episode_id = episode['id']
        if episode_id in assigned or episode_id in blocked:
            continue
        stored_id = episode.get('spotify_episode_id')
        if stored_id:
            if stored_id in assigned_ids:
                blocked.add(episode_id)
                messages.append(f'Stored Spotify ID {stored_id} is already assigned to another episode in {course["slug"]}.')
            elif stored_id in eligible:
                assigned[episode_id] = stored_id
                assigned_ids[stored_id] = episode_id
            else:
                messages.append(
                    f'Stored Spotify ID for {course["slug"]}/{episode_id} is not in current API results; omitting its player.'
                )

    title_owners: dict[str, list[str]] = {}
    for episode in episodes:
        expected_title = _normalized(f'{int(episode["episode"]):02d} {episode["title"]}')
        title_owners.setdefault(expected_title, []).append(episode['id'])
    for episode in episodes:
        episode_id = episode['id']
        if episode_id in assigned or episode_id in blocked:
            continue
        expected_title = _normalized(f'{int(episode["episode"]):02d} {episode["title"]}')
        if len(title_owners[expected_title]) > 1:
            blocked.add(episode_id)
            messages.append(f'Ambiguous exact title for {course["slug"]}/{episode_id}; no player was assigned.')
            continue
        candidates = [
            spotify_id for spotify_id, candidate in eligible.items()
            if spotify_id not in assigned_ids
            and isinstance(candidate.get('name'), str)
            and _normalized(candidate.get('name', '')) == expected_title
            and f'{base_url.rstrip("/")}/' not in _descriptions(candidate)
        ]
        if len(candidates) == 1:
            spotify_id = candidates[0]
            assigned[episode_id] = spotify_id
            assigned_ids[spotify_id] = episode_id
        elif len(candidates) > 1:
            blocked.add(episode_id)
            messages.append(f'Ambiguous exact Spotify title for {course["slug"]}/{episode_id}; no player was assigned.')
        else:
            messages.append(f'No Spotify episode match for {course["slug"]}/{episode_id} ({episode["title"]}).')

    for spotify_id, candidate in eligible.items():
        if spotify_id not in assigned_ids:
            messages.append(f'Spotify episode has no course match: {candidate.get("name", spotify_id)!r}.')
    return assigned, messages


def sync_catalogs(
    root: Path,
    client: SpotifyClient,
    base_url: str = BASE_URL,
) -> list[str]:
    """Fetch every configured show before writing any catalog, preventing partial syncs."""
    paths = sorted(path.parent for path in root.glob('*/course.json'))
    catalogs = [(path, json.loads((path / 'course.json').read_text(encoding='utf-8'))) for path in paths]
    shows: dict[str, list[dict]] = {}
    show_ids: dict[str, str] = {}
    for path, catalog in catalogs:
        show_url = catalog.get('links', {}).get('Spotify')
        if not show_url:
            continue
        match = website.SPOTIFY_SHOW.fullmatch(show_url) if isinstance(show_url, str) else None
        if match is None:
            raise SpotifySyncError(f'Invalid Spotify show URL for {path.name}: {show_url!r}.')
        show_id = match.group(1)
        show_ids[path.name] = show_id
        if show_id not in shows:
            try:
                shows[show_id] = client.show_episodes(show_id)
            except SpotifySyncError as error:
                raise SpotifySyncError(f'Unable to sync Spotify show {show_url}: {error}') from error

    prepared: list[tuple[Path, dict, int, list[str]]] = []
    for path, catalog in catalogs:
        show_id = show_ids.get(path.name)
        if not show_id:
            continue
        if catalog.get('spotify_show_id') != show_id:
            for episode in catalog['episodes']:
                episode.pop('spotify_episode_id', None)
        matches, messages = match_episodes(catalog | {'slug': path.name}, shows[show_id], base_url)
        updated = 0
        for episode in catalog['episodes']:
            spotify_id = matches.get(episode['id'])
            if spotify_id and episode.get('spotify_episode_id') != spotify_id:
                episode['spotify_episode_id'] = spotify_id
                updated += 1
            elif not spotify_id and 'spotify_episode_id' in episode:
                del episode['spotify_episode_id']
                updated += 1
        catalog['spotify_show_id'] = show_id
        prepared.append((path, catalog, updated, messages))

    report = []
    for path, catalog, updated, messages in prepared:
        matched = sum(bool(episode.get('spotify_episode_id')) for episode in catalog['episodes'])
        report.append(
            f'{path.name}: {matched}/{len(catalog["episodes"])} mapped; '
            f'{updated} IDs added, refreshed, or removed.'
        )
        report.extend(f'  - {message}' for message in messages)
    for path, catalog, _, _ in prepared:
        catalog_path = path / 'course.json'
        content = json.dumps(catalog, ensure_ascii=False, indent=2) + '\n'
        if catalog_path.read_text(encoding='utf-8') != content:
            catalog_path.write_text(content, encoding='utf-8')
    return report or ['No Spotify shows are configured; no catalogs changed.']


def _write_summary(report: str) -> None:
    summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary_path:
        markdown_report = re.sub(
            r'([\\`*_{}\[\]()#+\-.!|<>])',
            lambda match: '\\' + match.group(1),
            report,
        )
        with Path(summary_path).open('a', encoding='utf-8') as summary:
            summary.write(f'## Spotify episode sync\n\n{markdown_report}\n')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('podcast'))
    parser.add_argument('--base-url', default=BASE_URL)
    args = parser.parse_args()
    try:
        catalog_paths = sorted(args.root.glob('*/course.json'))
        if not catalog_paths:
            raise SpotifySyncError(f'No course catalogs found under {args.root}.')
        has_show = any(
            json.loads(path.read_text(encoding='utf-8')).get('links', {}).get('Spotify')
            for path in catalog_paths
        )
        if has_show:
            client = SpotifyClient.from_env()
            lines = sync_catalogs(args.root, client, args.base_url)
        else:
            lines = ['No Spotify shows are configured; no catalogs changed.']
    except SpotifySyncError as error:
        print(f'Spotify sync failed: {error}', file=sys.stderr)
        return 1
    report = '\n'.join(lines)
    print(report)
    _write_summary(report)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
