import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

SPEC = importlib.util.spec_from_file_location(
    'spotify_sync', Path(__file__).resolve().parents[1] / 'code/spotify_sync.py'
)
assert SPEC and SPEC.loader
spotify_sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(spotify_sync)


class Response:
    def __init__(self, value):
        self.data = json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return self.data


class SpotifySyncTests(unittest.TestCase):
    def setUp(self):
        self.client = spotify_sync.SpotifyClient('client', 'secret', sleeper=lambda _: None)
        self.course = {
            'slug': 'english-swedish',
            'episodes': [
                {'id': 'repeto:english-swedish:topic-01', 'title': 'Greetings', 'season': 1, 'episode': 1},
                {'id': 'repeto:english-swedish:topic-02', 'title': 'Numbers', 'season': 1, 'episode': 2},
            ],
        }

    def test_client_credentials_and_episode_pagination(self):
        show_id = '4pCmGojSZmODKl9qvxTrgq'
        page_two = f'https://api.spotify.com/v1/shows/{show_id}/episodes?offset=50&limit=50&market=US'
        requests = []

        def open_request(request, timeout):
            requests.append(request)
            if request.full_url == spotify_sync.TOKEN_URL:
                return Response({'access_token': 'token'})
            if len(requests) == 2:
                return Response({'items': [{'id': 'a' * 22, 'name': '01 Greetings'}], 'next': page_two})
            return Response({'items': [{'id': 'b' * 22, 'name': '02 Numbers'}], 'next': None})

        self.client.opener = open_request
        episodes = self.client.show_episodes(show_id)
        self.assertEqual([item['name'] for item in episodes], ['01 Greetings', '02 Numbers'])
        self.assertEqual(requests[0].get_method(), 'POST')
        self.assertIn('Basic ', requests[0].get_header('Authorization'))
        self.assertEqual(requests[1].get_header('Authorization'), 'Bearer token')
        self.assertIn('limit=50&offset=0&market=US', requests[1].full_url)
        self.assertEqual(requests[2].full_url, page_two)

    def test_rate_limit_retries_using_retry_after(self):
        waits = []
        request = type('RequestStub', (), {'full_url': 'https://api.spotify.com/v1/test'})()
        error = HTTPError(request.full_url, 429, 'rate limited', {'Retry-After': '2'}, io.BytesIO())
        calls = []

        def open_request(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise error
            return Response({'ok': True})

        client = spotify_sync.SpotifyClient('client', 'secret', opener=open_request, sleeper=waits.append)
        self.assertEqual(client._request_json(request), {'ok': True})
        self.assertEqual(waits, [2])

    def test_rejects_non_advancing_or_external_pagination_url(self):
        show_id = '4pCmGojSZmODKl9qvxTrgq'
        calls = []

        def open_request(request, timeout):
            calls.append(request)
            if request.full_url == spotify_sync.TOKEN_URL:
                return Response({'access_token': 'token'})
            return Response({
                'items': [],
                'next': 'https://example.com/v1/shows/4pCmGojSZmODKl9qvxTrgq/episodes?offset=50',
            })

        self.client.opener = open_request
        with self.assertRaisesRegex(spotify_sync.SpotifySyncError, 'unsafe or non-advancing'):
            self.client.show_episodes(show_id)

    def test_stable_episode_url_matches_even_when_spotify_title_differs(self):
        expected_url = 'https://repeto.stream/english-swedish/transcripts/season-1-episode-01.html'
        items = [{'id': 'a' * 22, 'name': 'Updated Spotify title', 'description': f'Transcript: {expected_url}'}]
        matches, messages = spotify_sync.match_episodes(self.course, items)
        self.assertEqual(matches['repeto:english-swedish:topic-01'], 'a' * 22)
        self.assertNotIn('No Spotify episode match for english-swedish/repeto:english-swedish:topic-01', '\n'.join(messages))

    def test_unique_exact_rss_title_is_used_when_no_stable_url_is_returned(self):
        items = [
            {'id': 'a' * 22, 'name': '01 Greetings'},
            {'id': 'b' * 22, 'name': '02 Numbers'},
        ]
        matches, messages = spotify_sync.match_episodes(self.course, items)
        self.assertEqual(matches, {
            'repeto:english-swedish:topic-01': 'a' * 22,
            'repeto:english-swedish:topic-02': 'b' * 22,
        })
        self.assertEqual(messages, [])

    def test_stored_id_missing_from_current_show_is_not_kept(self):
        course = {
            'slug': 'english-swedish',
            'episodes': [{
                'id': 'repeto:english-swedish:topic-01',
                'title': 'Greetings',
                'season': 1,
                'episode': 1,
                'spotify_episode_id': 'z' * 22,
            }],
        }
        matches, messages = spotify_sync.match_episodes(course, [])
        self.assertEqual(matches, {})
        self.assertIn('omitting its player', '\n'.join(messages))

    def test_missing_ambiguous_and_unavailable_episodes_are_not_guessed(self):
        duplicate_title = {
            'slug': 'course',
            'episodes': [
                {'id': 'first', 'title': 'Same', 'season': 1, 'episode': 1},
                {'id': 'second', 'title': 'Missing', 'season': 1, 'episode': 2},
            ],
        }
        items = [
            {'id': 'a' * 22, 'name': '01 Same'},
            {'id': 'b' * 22, 'name': '01 Same'},
            {'id': 'c' * 22, 'name': '02 Later', 'is_playable': False},
        ]
        matches, messages = spotify_sync.match_episodes(duplicate_title, items)
        self.assertEqual(matches, {})
        self.assertIn('Ambiguous exact Spotify title', '\n'.join(messages))
        self.assertIn('No Spotify episode match', '\n'.join(messages))
        self.assertIn('unavailable in the configured market', '\n'.join(messages))

    def test_failed_show_fetch_does_not_partially_update_catalogs(self):
        class Client:
            def show_episodes(self, show_id):
                if show_id == '4pCmGojSZmODKl9qvxTrgq':
                    return [{'id': 'a' * 22, 'name': '01 Greetings'}]
                raise spotify_sync.SpotifySyncError('HTTP 503')

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for slug, show_id in (
                ('one', '4pCmGojSZmODKl9qvxTrgq'),
                ('two', '4w75JxIfvzSrVubxY8CVrq'),
            ):
                folder = root / slug
                folder.mkdir()
                config = {
                    'links': {'Spotify': f'https://open.spotify.com/show/{show_id}'},
                    'episodes': [{'id': 'repeto:one:topic-01', 'title': 'Greetings', 'season': 1, 'episode': 1}],
                }
                (folder / 'course.json').write_text(json.dumps(config), encoding='utf-8')
            first = (root / 'one/course.json').read_text(encoding='utf-8')
            with self.assertRaisesRegex(spotify_sync.SpotifySyncError, 'Unable to sync Spotify show'):
                spotify_sync.sync_catalogs(root, Client())
            self.assertEqual((root / 'one/course.json').read_text(encoding='utf-8'), first)

    def test_sync_persists_current_show_and_episode_ids(self):
        show_id = '4pCmGojSZmODKl9qvxTrgq'
        requested = []

        class Client:
            def show_episodes(self, requested_show_id):
                requested.append(requested_show_id)
                return [
                    {'id': 'a' * 22, 'name': '01 Greetings'},
                    {'id': 'b' * 22, 'name': '02 Numbers'},
                ]

        with tempfile.TemporaryDirectory() as directory:
            course_dir = Path(directory) / 'english-swedish'
            course_dir.mkdir()
            catalog = {
                'links': {'Spotify': f'https://open.spotify.com/show/{show_id}'},
                'spotify_show_id': 'z' * 22,
                'episodes': [
                    {
                        'id': episode['id'],
                        'title': episode['title'],
                        'season': episode['season'],
                        'episode': episode['episode'],
                        'spotify_episode_id': 'z' * 22,
                    }
                    for episode in self.course['episodes']
                ],
            }
            path = course_dir / 'course.json'
            path.write_text(json.dumps(catalog), encoding='utf-8')
            report = spotify_sync.sync_catalogs(Path(directory), Client())
            updated = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(requested, [show_id])
            self.assertEqual(updated['spotify_show_id'], show_id)
            self.assertEqual(
                [episode['spotify_episode_id'] for episode in updated['episodes']],
                ['a' * 22, 'b' * 22],
            )
            self.assertIn('2 IDs added, refreshed, or removed', '\n'.join(report))


if __name__ == '__main__':
    unittest.main()
