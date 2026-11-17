import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("website", ROOT / "code/website.py")
assert SPEC and SPEC.loader
website = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(website)


class CoursePlayerPageTests(unittest.TestCase):
    def setUp(self):
        self.course = {
            "slug": "english-polish",
            "title": "English to Polish",
            "cover": "cover.jpg",
            "description": "A short course.",
            "source_language": "en",
            "target_language": "pl",
            "ui": "en",
            "spotify_show_id": "s" * 22,
            "links": {"Spotify": "https://open.spotify.com/show/" + "s" * 22},
            "seasons": {"1": "Practice"},
            "episodes": [
                {
                    "id": "practice-1", "season": 1, "episode": 1, "title": "First episode",
                    "phrases": 5, "duration_ms": 60000, "spotify_episode_id": "a" * 22,
                },
                {
                    "id": "practice-2", "season": 1, "episode": 2, "title": "Second episode",
                    "phrases": 5, "duration_ms": 60000, "spotify_episode_id": "b" * 22,
                },
            ],
        }

    def test_player_is_rendered_in_the_playlist_layout_with_selected_control(self):
        page = website.course_page(
            self.course,
            "https://repeto.stream",
            {"css": "site.css", "js": "site.js", "player": "course-player.js"},
        )

        self.assertIn('<div class="episode-layout">', page)
        self.assertLess(page.index('class="course-player"'), page.index('<ol class="episodes">'))
        self.assertIn('aria-pressed="true" aria-controls="course-player"', page)
        self.assertIn("aria-live=\"polite\"", page)

    def test_player_script_is_included_in_hashed_site_assets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            assets = website.write_assets(Path(temp_dir))

            self.assertIn("player", assets)
            self.assertTrue((Path(temp_dir) / assets["player"]).is_file())


if __name__ == "__main__":
    unittest.main()
