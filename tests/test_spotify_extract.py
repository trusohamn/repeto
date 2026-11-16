import copy
import importlib.util
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SPEC = importlib.util.spec_from_file_location(
    'spotify_extract', Path(__file__).resolve().parents[1] / 'code/spotify_extract.py'
)
assert SPEC and SPEC.loader
extract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extract)

SHOW = 'https://open.spotify.com/show/' + 's' * 22
BASE = 'https://repeto.stream'


def course_data():
    return {
        'slug': 'english-french',
        'links': {'Spotify': SHOW},
        'title': 'Unchanged title',
        'episodes': [
            {'id': 'practice-1', 'season': 1, 'episode': 1, 'title': 'Practice'},
            {'id': 'story-1', 'season': 2, 'episode': 1, 'title': 'Story'},
        ],
    }


def rows_for(course):
    return [
        {
            'url': 'https://open.spotify.com/episode/' + str(index) * 22,
            'name': episode['title'],
            'transcript_urls': [extract.website.episode_url(BASE, course['slug'], episode)],
        }
        for index, episode in enumerate(course['episodes'], start=1)
    ]


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.course = course_data()
        self.rows = rows_for(self.course)

    def test_exact_urls_cover_practice_and_story_despite_renamed_titles(self):
        self.rows[0]['name'] = 'Different Spotify title'
        result = extract.match_show(self.course, self.rows, BASE)
        self.assertTrue(result['complete'])
        self.assertEqual(result['matches'], {'practice-1': '1' * 22, 'story-1': '2' * 22})

    def test_missing_and_title_only_do_not_reuse_stored_ids(self):
        self.course['episodes'][0]['spotify_episode_id'] = '1' * 22
        self.rows[0]['transcript_urls'] = []
        result = extract.match_show(self.course, self.rows[:1], BASE)
        self.assertFalse(result['complete'])
        self.assertEqual(result['matches'], {})
        self.assertIn('Missing Spotify episode for story-1', result['issues'])

    def test_nonexact_or_cross_course_transcripts_are_not_matches(self):
        url = self.rows[0]['transcript_urls'][0]
        for bad in (url + '.evil', url + '?tracking=1', url.replace('english-french', 'english-polish')):
            with self.subTest(bad=bad):
                self.rows[0]['transcript_urls'] = [bad]
                result = extract.match_show(self.course, self.rows, BASE)
                self.assertFalse(result['complete'])
                self.assertNotIn('practice-1', result['matches'])

    def test_duplicate_ids_competing_claims_and_multi_url_cards_block_apply(self):
        for rows in (
            self.rows + [self.rows[0]],
            self.rows + [dict(self.rows[0], url='https://open.spotify.com/episode/' + '3' * 22)],
            [dict(self.rows[0], transcript_urls=[url for row in self.rows for url in row['transcript_urls']]), self.rows[1]],
            [self.rows[0], dict(self.rows[1], url=self.rows[0]['url'])],
        ):
            with self.subTest(rows=rows):
                self.assertFalse(extract.match_show(self.course, rows, BASE)['complete'])

    def test_invalid_urls_or_extra_episodes_fail_explicitly(self):
        for row in (
            dict(self.rows[0], url='https://example.com/episode/' + '1' * 22),
            dict(self.rows[0], url='https://open.spotify.com/episode/not-an-id'),
            dict(self.rows[0], name=''),
        ):
            with self.subTest(row=row):
                self.assertFalse(extract.match_show(self.course, [row], BASE)['complete'])
        extra = dict(self.rows[0], url='https://open.spotify.com/episode/' + '3' * 22,
                     transcript_urls=[BASE + '/unknown/transcripts/season-1-episode-01.html'])
        self.assertFalse(extract.match_show(self.course, self.rows + [extra], BASE)['complete'])

    def test_duplicate_local_ids_and_transcript_paths_are_ambiguous(self):
        for field in ('id', 'episode'):
            course = copy.deepcopy(self.course)
            course['episodes'][1][field] = course['episodes'][0][field]
            if field == 'episode':
                course['episodes'][1]['season'] = 1
            self.assertFalse(extract.match_show(course, self.rows, BASE)['complete'])


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.course = course_data()
        self.path = self.root / self.course['slug'] / 'course.json'
        self.path.parent.mkdir()
        self.catalog = dict(self.course)
        del self.catalog['slug']
        self.original = json.dumps(self.catalog, ensure_ascii=False, indent=2) + '\n'
        self.path.write_text(self.original, encoding='utf-8')
        self.courses = extract.read_courses(self.root, [])
        self.result = extract.match_show(self.course, rows_for(self.course), BASE)

    def test_report_only_default_and_explicit_apply(self):
        output = self.root / 'report.json'
        args = ['--root', str(self.root), '--output', str(output)]
        with patch.object(extract, 'extract_courses', return_value=[self.result]), redirect_stdout(io.StringIO()):
            self.assertEqual(extract.main(args), 0)
            self.assertEqual(self.path.read_text(), self.original)
            self.assertEqual(json.loads(output.read_text())['courses'][0]['extracted_episodes'], 2)
            self.assertEqual(extract.main(args + ['--apply']), 0)
        expected = copy.deepcopy(self.catalog)
        expected['spotify_show_id'] = 's' * 22
        for index, episode in enumerate(expected['episodes'], start=1):
            episode['spotify_episode_id'] = str(index) * 22
        self.assertEqual(json.loads(self.path.read_text()), expected)

    def test_one_failed_show_blocks_all_writes_and_still_saves_report(self):
        incomplete = dict(self.result, course='other-course', complete=False, issues=['HTTP 403'])
        output = self.root / 'report.json'
        with (
            patch.object(extract, 'extract_courses', return_value=[self.result, incomplete]),
            redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(extract.main(['--root', str(self.root), '--output', str(output), '--apply']), 1)
        self.assertEqual(self.path.read_text(), self.original)
        self.assertEqual(json.loads(output.read_text())['courses'][1]['issues'], ['HTTP 403'])

    def test_no_partial_updates_when_later_catalog_changed(self):
        second = copy.deepcopy(self.course)
        second['slug'] = 'other-course'
        second_path = self.root / 'other-course' / 'course.json'
        second_path.parent.mkdir()
        second_catalog = dict(second)
        del second_catalog['slug']
        second_path.write_text(json.dumps(second_catalog), encoding='utf-8')
        courses = extract.read_courses(self.root, [])
        second_path.write_text('{}', encoding='utf-8')
        results = [self.result, extract.match_show(second, rows_for(second), BASE)]
        with self.assertRaisesRegex(extract.ExtractionError, 'changed during extraction'):
            extract.apply_results(courses, results)
        self.assertEqual(self.path.read_text(), self.original)

    def test_invalid_mapping_and_incomplete_result_do_not_write(self):
        for result in (
            dict(self.result, complete=False),
            dict(self.result, matches={'practice-1': '1' * 22}),
            dict(self.result, matches={'practice-1': '1' * 22, 'story-1': '1' * 22}),
            dict(self.result, matches={'practice-1': 'bad', 'story-1': '2' * 22}),
        ):
            with self.subTest(result=result), self.assertRaises(extract.ExtractionError):
                extract.apply_results(self.courses, [result])
            self.assertEqual(self.path.read_text(), self.original)

    def test_course_selection_and_missing_invalid_show_configuration(self):
        self.assertEqual(len(extract.read_courses(self.root, ['english-french'])), 1)
        with self.assertRaisesRegex(extract.ExtractionError, 'Unknown courses'):
            extract.read_courses(self.root, ['unknown'])
        self.catalog['links'] = {}
        self.path.write_text(json.dumps(self.catalog))
        with self.assertRaisesRegex(extract.ExtractionError, 'no Spotify show'):
            extract.read_courses(self.root, ['english-french'])
        with redirect_stderr(io.StringIO()), self.assertRaisesRegex(extract.ExtractionError, 'No selected'):
            extract.read_courses(self.root, [])
        self.catalog['links']['Spotify'] = 'https://example.com/show/anything'
        self.path.write_text(json.dumps(self.catalog))
        with self.assertRaisesRegex(extract.ExtractionError, 'invalid Spotify show'):
            extract.read_courses(self.root, [])

    def test_output_cannot_overwrite_catalog(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(extract.main(['--root', str(self.root), '--output', str(self.path)]), 1)
        self.assertEqual(self.path.read_text(), self.original)

    def test_invalid_catalog_shapes_fail_before_browser_startup(self):
        for catalog in (
            [], dict(self.catalog, links=[]), dict(self.catalog, episodes=[]),
            dict(self.catalog, episodes=[{'id': 'missing-numbers'}]),
            dict(self.catalog, slug='another-course'),
        ):
            with self.subTest(catalog=catalog):
                self.path.write_text(json.dumps(catalog))
                with self.assertRaises(extract.ExtractionError):
                    extract.read_courses(self.root, [])

    def test_existing_slug_is_preserved_when_applying(self):
        self.path.write_text(json.dumps(self.course))
        extract.apply_results(extract.read_courses(self.root, []), [self.result])
        self.assertEqual(json.loads(self.path.read_text())['slug'], self.course['slug'])


@unittest.skipUnless(importlib.util.find_spec('playwright'), 'Install requirements-spotify.txt for browser fixtures.')
class BrowserFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.playwright = sync_playwright().start()
        if not Path(cls.playwright.chromium.executable_path).is_file():
            cls.playwright.stop()
            raise unittest.SkipTest('Install browser fixtures with: python -m playwright install chromium')
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)
        self.page.set_default_timeout(500)

    def fixture(self, html, status=200):
        self.page.route('**/*', lambda route: route.fulfill(status=status, content_type='text/html', body=html))

    def card(self, number):
        return (
            f'<div data-testid="episode-{number}"><a href="/episode/{str(number) * 22}">Title {number}</a>'
            f'<p>Transcript: {BASE}/english-french/transcripts/season-1-episode-{number:02d}.html</p>'
            '<div>Nov 12</div></div>'
        )

    def test_real_dom_multiple_loads_and_transcript_date_boundary(self):
        html = self.card(1) + '<div id="more" onclick="loadMore()">Load more episodes</div>'
        html += '<script>let n=1;function loadMore(){ n++; more.insertAdjacentHTML("beforebegin",'
        html += json.dumps(self.card(2)) + '.replaceAll("2",String(n))); if(n===3) more.remove(); }</script>'
        self.fixture(html)
        rows = extract.collect_show(self.page, SHOW)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['transcript_urls'], [BASE + '/english-french/transcripts/season-1-episode-01.html'])
        self.assertEqual(rows[-1]['url'], 'https://open.spotify.com/episode/' + '3' * 22)

    def test_stalled_load_more_is_error(self):
        self.fixture(self.card(1) + '<div>Load more episodes</div>')
        with self.assertRaisesRegex(extract.ExtractionError, 'did not add episodes'):
            extract.collect_show(self.page, SHOW)

    def test_optional_cookie_rejection_uses_public_control(self):
        self.fixture(
            self.card(1) + '<button id="onetrust-reject-all-handler" '
            'onclick="this.remove()">REJECT ALL</button>'
        )
        self.assertEqual(len(extract.collect_show(self.page, SHOW)), 1)
        self.assertEqual(self.page.locator('#onetrust-reject-all-handler').count(), 0)

    def test_cookie_disappearance_is_reported_but_blocked_control_fails(self):
        from playwright.sync_api import TimeoutError as BrowserTimeout
        page = MagicMock()
        control = page.locator.return_value
        control.is_visible.side_effect = [True, False]
        control.click.side_effect = BrowserTimeout('Control detached')
        with redirect_stderr(io.StringIO()) as stderr:
            extract.reject_optional_cookies(page)
        self.assertIn('disappeared', stderr.getvalue())
        control.is_visible.side_effect = [True, True]
        with self.assertRaisesRegex(extract.ExtractionError, 'cookie rejection is blocked'):
            extract.reject_optional_cookies(page)

    def test_unbounded_pagination_is_error(self):
        self.fixture(self.card(1) + '<div id="more" onclick=\'more.insertAdjacentHTML("beforebegin",'
                     + json.dumps(self.card(2)) + ')\'>Load more episodes</div>')
        with patch.object(extract, 'MAX_LOADS', 2):
            with self.assertRaisesRegex(extract.ExtractionError, 'exceeded 2'):
                extract.collect_show(self.page, SHOW)

    def test_card_boundaries_and_transcript_suffix(self):
        from playwright.sync_api import Error as BrowserError
        self.fixture('<section>' + self.card(1) + self.card(2) + '</section>')
        rows = extract.collect_show(self.page, SHOW)
        self.assertEqual([len(row['transcript_urls']) for row in rows], [1, 1])
        self.page.set_content(self.card(1).replace('.html</p>', '.html.evil</p>'))
        self.assertEqual(self.page.evaluate(extract.EXTRACT_SCRIPT)[0]['transcript_urls'], [])
        self.page.set_content('<section><a href="/episode/' + '1' * 22 + '">Unknown wrapper</a></section>')
        with self.assertRaisesRegex(BrowserError, 'unambiguous episode card'):
            self.page.evaluate(extract.EXTRACT_SCRIPT)
        self.page.set_content(self.card(1).replace('</div>', '<a href="/episode/' + '2' * 22 + '">Other</a></div>', 1))
        with self.assertRaisesRegex(BrowserError, 'unambiguous episode card'):
            self.page.evaluate(extract.EXTRACT_SCRIPT)

    def test_http_failure_and_missing_episodes(self):
        from playwright.sync_api import TimeoutError as BrowserTimeout
        self.fixture('<h1>Forbidden</h1>', status=403)
        with self.assertRaisesRegex(extract.ExtractionError, 'HTTP 403'):
            extract.collect_show(self.page, SHOW)
        self.page.unroute('**/*')
        self.fixture('<h1>Log in</h1>')
        with self.assertRaises(BrowserTimeout):
            extract.collect_show(self.page, SHOW)


if __name__ == '__main__':
    unittest.main()
