import json
import tempfile
import unittest
from pathlib import Path

import stream_cli


class StreamCliTests(unittest.TestCase):
    def test_init_config_creates_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            stream_cli.init_config(config_path)

            self.assertTrue(config_path.exists())
            data = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertIn("providers", data)
            self.assertEqual(data["player"], "mpv")

    def test_static_provider_search_and_streams(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider_data_path = Path(tmp) / "provider.json"
            provider_data = {
                "catalog": [
                    {"id": "m1", "title": "My Movie", "year": 2025, "type": "movie"},
                    {"id": "s1", "title": "Another Show", "year": 2024, "type": "show"},
                ],
                "streams": {
                    "m1": [{"name": "1080p", "url": "https://example.com/movie.m3u8"}],
                },
            }
            provider_data_path.write_text(json.dumps(provider_data), encoding="utf-8")

            provider = {"name": "test-static", "type": "static", "path": str(provider_data_path)}
            matches = stream_cli.search_provider(provider, "movie")
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["id"], "m1")
            self.assertEqual(matches[0]["provider"], "test-static")

            streams = stream_cli.streams_for(provider, "m1")
            self.assertEqual(len(streams), 1)
            self.assertEqual(streams[0]["name"], "1080p")

    def test_collect_results_respects_provider_filter(self):
        config = {
            "player": "mpv",
            "providers": [
                {
                    "name": "first",
                    "type": "static",
                    "path": "/does/not/exist-first.json",
                },
                {
                    "name": "second",
                    "type": "static",
                    "path": "/does/not/exist-second.json",
                },
            ],
        }

        original = stream_cli.search_provider

        def fake_search(provider, query):
            return [{"id": provider["name"], "title": query, "provider": provider["name"]}]

        try:
            stream_cli.search_provider = fake_search
            results = stream_cli.collect_results(config, "demo", "second")
        finally:
            stream_cli.search_provider = original

        self.assertEqual([item["provider"] for item in results], ["second"])


if __name__ == "__main__":
    unittest.main()
