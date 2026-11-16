"""Extract public Spotify episode links locally with an anonymous browser."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import website

if TYPE_CHECKING:
    from playwright.sync_api import Page

EXTRACT_SCRIPT = Path(__file__).with_suffix('.js').read_text(encoding='utf-8')
EPISODE_URL = re.compile(r'https://open\.spotify\.com/episode/([A-Za-z0-9]{22})')
EPISODE_LINKS = 'a[href*="/episode/"]'
MAX_LOADS = 100


class ExtractionError(RuntimeError):
    """Public pages could not be completely or safely extracted."""


def reject_optional_cookies(page: Page) -> None:
    from playwright.sync_api import TimeoutError as BrowserTimeout

    reject = page.locator('#onetrust-reject-all-handler:visible')
    if not reject.is_visible():
        return
    try:
        reject.click(timeout=3000)
    except BrowserTimeout as error:
        if reject.is_visible():
            raise ExtractionError('Optional cookie rejection is blocked; inspect the public page.') from error
        print('Cookie control disappeared before clicking; continuing without accepting cookies.', file=sys.stderr)


def collect_show(page: Page, show_url: str) -> list[dict]:
    """Use only the public page and its visible load-more control."""
    from playwright.sync_api import TimeoutError as BrowserTimeout

    if website.SPOTIFY_SHOW.fullmatch(show_url) is None:
        raise ExtractionError(f'Invalid Spotify show URL: {show_url!r}')
    response = page.goto(show_url, wait_until='load')
    if response is None or response.status != 200:
        raise ExtractionError(f'Show page returned HTTP {response.status if response else "no response"}.')
    if page.url.rstrip('/') != show_url:
        raise ExtractionError(f'Show page redirected to {page.url}; no login or challenge will be bypassed.')
    page.locator(EPISODE_LINKS).first.wait_for(state='attached')
    reject_optional_cookies(page)

    more = page.get_by_text('Load more episodes', exact=True)
    for _ in range(MAX_LOADS):
        try:
            more.wait_for(state='visible', timeout=5000)
        except BrowserTimeout:
            return page.evaluate(EXTRACT_SCRIPT)
        reject_optional_cookies(page)
        previous = page.locator(EPISODE_LINKS).count()
        more.click()
        try:
            page.wait_for_function(
                '(previous) => document.querySelectorAll(\'a[href*="/episode/"]\').length > previous',
                arg=previous,
            )
        except BrowserTimeout as error:
            raise ExtractionError('Load more episodes did not add episodes; refusing a partial result.') from error
    raise ExtractionError(f'Show exceeded {MAX_LOADS} load-more clicks; refusing a partial result.')


def match_show(course: dict, rows: list[dict], base_url: str) -> dict:
    """Require exact transcript URLs and one-to-one mappings, never title guesses."""
    expected: dict[str, list[str]] = {}
    issues: list[str] = []
    for episode in course['episodes']:
        url = website.episode_url(base_url, course['slug'], episode)
        expected.setdefault(url, []).append(episode['id'])
    if len({episode['id'] for episode in course['episodes']}) != len(course['episodes']):
        issues.append('Course catalog contains duplicate episode IDs.')

    episodes = []
    claims: dict[str, list[str]] = {}
    for row in rows:
        url = row.get('url')
        match = EPISODE_URL.fullmatch(url) if isinstance(url, str) else None
        transcripts = row.get('transcript_urls')
        if (
            match is None or not isinstance(row.get('name'), str) or not row['name']
            or not isinstance(transcripts, list)
            or any(not isinstance(value, str) for value in transcripts)
        ):
            issues.append(f'Invalid episode card: {url!r}.')
            continue
        spotify_id = match.group(1)
        episodes.append(dict(row, id=spotify_id))
        if len(set(transcripts)) != 1:
            issues.append(f'{spotify_id}: expected exactly one transcript URL, found {len(set(transcripts))}.')
            continue
        transcript = transcripts[0]
        owners = expected.get(transcript, [])
        if len(owners) != 1:
            issues.append(f'{spotify_id}: transcript has {len(owners)} course matches: {transcript}')
            continue
        claims.setdefault(owners[0], []).append(spotify_id)

    duplicates = {key for key, count in Counter(ep['id'] for ep in episodes).items() if count > 1}
    for spotify_id in sorted(duplicates):
        issues.append(f'Duplicate Spotify episode ID: {spotify_id}')
    matches = {}
    for episode in course['episodes']:
        candidates = claims.get(episode['id'], [])
        if len(candidates) == 1 and candidates[0] not in duplicates:
            matches[episode['id']] = candidates[0]
        elif candidates:
            issues.append(f'Ambiguous match for {episode["id"]}: {candidates}')
        else:
            issues.append(f'Missing Spotify episode for {episode["id"]}')
    complete = bool(course['episodes']) and not issues and len(matches) == len(course['episodes'])
    return {
        'course': course['slug'],
        'show_url': course['links']['Spotify'],
        'expected_episodes': len(course['episodes']),
        'extracted_episodes': len(episodes),
        'complete': complete,
        'matches': matches,
        'issues': issues,
        'episodes': episodes,
    }


def read_courses(root: Path, selected: list[str]) -> list[tuple[Path, dict]]:
    paths = sorted(root.glob('*/course.json'))
    if not paths:
        raise ExtractionError(f'No course catalogs found under {root}.')
    unknown = set(selected) - {path.parent.name for path in paths}
    if unknown:
        raise ExtractionError(f'Unknown courses: {", ".join(sorted(unknown))}')
    courses = []
    for path in paths:
        if selected and path.parent.name not in selected:
            continue
        course = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(course, dict) or not isinstance(course.get('links', {}), dict):
            raise ExtractionError(f'{path}: expected a catalog object with a links object.')
        show_url = course.get('links', {}).get('Spotify')
        if not show_url:
            if selected:
                raise ExtractionError(f'{path.parent.name} has no Spotify show URL.')
            print(f'{path.parent.name}: skipped (no Spotify show URL).', file=sys.stderr)
            continue
        if not isinstance(show_url, str) or website.SPOTIFY_SHOW.fullmatch(show_url) is None:
            raise ExtractionError(f'{path}: invalid Spotify show URL: {show_url!r}')
        episodes = course.get('episodes')
        if not isinstance(episodes, list) or not episodes:
            raise ExtractionError(f'{path}: expected a nonempty episodes list.')
        for episode in episodes:
            if (
                not isinstance(episode, dict)
                or not isinstance(episode.get('id'), str) or not episode['id']
                or not isinstance(episode.get('season'), int) or episode['season'] < 1
                or not isinstance(episode.get('episode'), int) or episode['episode'] < 1
            ):
                raise ExtractionError(f'{path}: episodes need an ID and positive season/episode numbers.')
        if 'slug' in course and course['slug'] != path.parent.name:
            raise ExtractionError(f'{path}: catalog slug must match its directory name.')
        courses.append((path, dict(course, slug=path.parent.name)))
    if not courses:
        raise ExtractionError('No selected courses have Spotify shows.')
    return courses


def apply_results(courses: list[tuple[Path, dict]], results: list[dict]) -> None:
    """Do not modify any catalog unless every selected course was fully matched."""
    if (
        len(results) != len(courses)
        or len({result['course'] for result in results}) != len(results)
        or any(not result['complete'] for result in results)
    ):
        raise ExtractionError('Incomplete extraction; no course catalogs were changed.')
    by_course = {result['course']: result for result in results}
    prepared = []
    for path, course in courses:
        result = by_course.get(course['slug'])
        if result is None or result['show_url'] != course['links']['Spotify']:
            raise ExtractionError('Extraction does not match the selected catalogs.')
        catalog = json.loads(path.read_text(encoding='utf-8'))
        original = dict(course)
        if 'slug' not in catalog:
            del original['slug']
        if catalog != original:
            raise ExtractionError(f'{path} changed during extraction; rerun before applying.')
        if set(result['matches']) != {ep['id'] for ep in catalog['episodes']}:
            raise ExtractionError(f'{path}: extraction does not cover every episode.')
        mapped_ids = list(result['matches'].values())
        if len(set(mapped_ids)) != len(mapped_ids):
            raise ExtractionError(f'{path}: duplicate Spotify mappings.')
        show = website.SPOTIFY_SHOW.fullmatch(result['show_url'])
        if show is None:
            raise ExtractionError('Invalid extracted show URL.')
        catalog['spotify_show_id'] = show.group(1)
        for episode in catalog['episodes']:
            spotify_id = result['matches'][episode['id']]
            if not isinstance(spotify_id, str) or website.SPOTIFY_EPISODE_ID.fullmatch(spotify_id) is None:
                raise ExtractionError(f'{path}: invalid extracted episode ID.')
            episode['spotify_episode_id'] = spotify_id
        prepared.append((path, json.dumps(catalog, ensure_ascii=False, indent=2) + '\n'))
    for path, text in prepared:
        path.write_text(text, encoding='utf-8')


def extract_courses(courses: list[tuple[Path, dict]], base_url: str, headless: bool) -> list[dict]:
    try:
        from playwright.sync_api import Error as BrowserError, sync_playwright
    except ImportError as error:
        raise ExtractionError(
            'Install requirements-spotify.txt and run: python -m playwright install chromium'
        ) from error
    try:
        results = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=headless)
            try:
                context = browser.new_context(locale='en-US', viewport={'width': 390, 'height': 844})
                context.set_default_timeout(30000)
                context.set_default_navigation_timeout(60000)
                for _, course in courses:
                    page = context.new_page()
                    show_url = course['links']['Spotify']
                    print(f'{course["slug"]}: loading {show_url}', flush=True)
                    try:
                        rows = collect_show(page, show_url)
                        result = match_show(course, rows, base_url)
                    except (BrowserError, ExtractionError) as error:
                        result = {
                            'course': course['slug'], 'show_url': show_url,
                            'complete': False, 'matches': {}, 'episodes': [],
                            'issues': [str(error)],
                        }
                    finally:
                        page.close()
                    results.append(result)
                    print(f'  {len(result["matches"])}/{len(course["episodes"])} matched; complete={result["complete"]}', flush=True)
                    for issue in result['issues']:
                        print(f'  - {issue}', file=sys.stderr)
            finally:
                browser.close()
        return results
    except BrowserError as error:
        raise ExtractionError(f'Browser startup or shutdown failed: {error}') from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('podcast'))
    parser.add_argument('--course', action='append', default=[], help='Course slug; repeat to select several. Default: all configured shows.')
    parser.add_argument('--output', type=Path, default=Path('output/spotify-extract.json'))
    parser.add_argument('--base-url', default='https://repeto.stream')
    display = parser.add_mutually_exclusive_group()
    display.add_argument('--headless', action='store_true', help='Hide the browser window; public rendering may differ.')
    display.add_argument('--headed', action='store_false', dest='headless', help='Show the browser window (default).')
    parser.set_defaults(headless=False)
    parser.add_argument('--apply', action='store_true', help='Update catalogs only if every selected course is fully matched.')
    args = parser.parse_args(argv)
    try:
        courses = read_courses(args.root, args.course)
        base = urlsplit(args.base_url)
        if base.scheme != 'https' or not base.netloc or base.query or base.fragment:
            raise ExtractionError('--base-url must be an HTTPS site URL without a query or fragment.')
        if args.output.resolve() in {path.resolve() for path in args.root.glob('*/course.json')}:
            raise ExtractionError('--output must not overwrite a course catalog.')
        results = extract_courses(courses, args.base_url.rstrip('/'), args.headless)
        report = {
            'schema_version': 1,
            'source': 'spotify-public-browser',
            'collected_at': datetime.now(timezone.utc).isoformat(),
            'courses': results,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'Extraction report: {args.output}')
        if args.apply:
            apply_results(courses, results)
            print('Updated selected course catalogs. Nothing was published.')
        if any(not result['complete'] for result in results):
            print('Extraction incomplete; inspect the report. No catalogs changed.', file=sys.stderr)
            return 1
        return 0
    except (ExtractionError, OSError, ValueError) as error:
        print(f'Spotify extraction failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
