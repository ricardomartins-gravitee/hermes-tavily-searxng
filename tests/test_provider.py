import importlib.util
import os
import unittest
from unittest.mock import patch

class ProviderTests(unittest.TestCase):
    def test_tavily_success(self):
        self.assertIsNotNone(importlib.util.find_spec('tavily_searxng'), 'plugin package missing')
        from tavily_searxng import Provider
        with patch.dict(os.environ, {'TAVILY_API_KEY': 'test-key', 'SEARXNG_URL': ''}, clear=True), patch('tavily_searxng._request', return_value={'results': [{'title': 'A', 'url': 'https://example.org', 'content': 'B'}]}):
            result = Provider().search('query', 5)
        self.assertEqual(result['data']['web'][0]['description'], 'B')
        self.assertEqual(result['metadata']['provider'], 'tavily')

    def test_failed_tavily_falls_back_without_leaking_errors(self):
        from tavily_searxng import Provider
        with patch.dict(os.environ, {'TAVILY_API_KEY': 'secret-key', 'SEARXNG_URL': 'https://internal.example'}, clear=True), patch('tavily_searxng._request', side_effect=[ValueError('secret-key'), {'results': [{'title': 'A', 'url': 'https://example.org', 'content': 'B'}]}]):
            result = Provider().search('query')
        self.assertTrue(result['success'])
        self.assertEqual(result['metadata']['provider'], 'searxng')
        self.assertNotIn('secret-key', str(result))

    def test_both_fail_cleanly(self):
        from tavily_searxng import Provider
        with patch.dict(os.environ, {'TAVILY_API_KEY': 'secret-key', 'SEARXNG_URL': 'https://internal.example'}, clear=True), patch('tavily_searxng._request', side_effect=ValueError('secret-key')):
            result = Provider().search('query')
        self.assertFalse(result['success'])
        self.assertNotIn('secret-key', str(result))

    def test_partial_searxng_upstream_failures_are_visible(self):
        from tavily_searxng import Provider
        with patch.dict(os.environ, {"TAVILY_API_KEY": "", "SEARXNG_URL": "https://search.example"}, clear=True), patch("tavily_searxng._request", return_value={"results": [{"title": "A", "url": "https://example.org"}], "unresponsive_engines": [["engine", "secret error"]]}):
            result = Provider().search("query")
        self.assertTrue(result["metadata"]["partial"])
        self.assertNotIn("secret error", str(result))

    def test_empty_searxng_with_failed_engines_is_an_error(self):
        from tavily_searxng import Provider
        with patch("tavily_searxng.get_provider_env", side_effect=lambda n: {"TAVILY_API_KEY": "", "SEARXNG_URL": "https://search.example"}[n]), patch("tavily_searxng._request", return_value={"results": [], "unresponsive_engines": [["engine", "CAPTCHA"]]}):
            result = Provider().search("query")
        self.assertFalse(result["success"])

    def test_malformed_response_triggers_fallback(self):
        from tavily_searxng import Provider
        with patch.dict(os.environ, {"TAVILY_API_KEY": "key", "SEARXNG_URL": "https://search.example"}, clear=True), patch("tavily_searxng._request", side_effect=[{"results": "bad"}, {"results": []}]):
            result = Provider().search("query")
        self.assertEqual(result["metadata"]["provider"], "searxng")

    def test_skipped_malformed_rows_mark_partial(self):
        from tavily_searxng import Provider
        with patch.dict(os.environ, {"TAVILY_API_KEY": "key", "SEARXNG_URL": ""}, clear=True), patch("tavily_searxng._request", return_value={"results": [None, {"url": "https://example.org"}]}):
            result = Provider().search("query")
        self.assertTrue(result["metadata"]["partial"])

    def test_without_key_never_calls_tavily(self):
        from tavily_searxng import Provider
        with patch("tavily_searxng.get_provider_env", side_effect=lambda n: {"TAVILY_API_KEY": "", "SEARXNG_URL": "https://search.example"}[n]), patch("tavily_searxng._request", return_value={"results": []}) as request:
            result = Provider().search("query")
        self.assertEqual(result["metadata"]["provider"], "searxng")
        self.assertEqual(request.call_count, 1)
        self.assertNotIn("Authorization", request.call_args.args[2])

    def test_invalid_keyed_base_url_is_not_requested(self):
        from tavily_searxng import Provider
        with patch("tavily_searxng.get_provider_env", side_effect=lambda n: {"TAVILY_API_KEY": "", "SEARXNG_URL": "https://user:password@search.example"}[n]), patch("tavily_searxng._request") as request:
            result = Provider().search("query")
        self.assertFalse(result["success"])
        request.assert_not_called()
        self.assertNotIn("password", str(result))

    def test_tavily_request_uses_bearer_and_clamps_limit(self):
        from tavily_searxng import Provider
        with patch("tavily_searxng.get_provider_env", side_effect=lambda n: {"TAVILY_API_KEY": "secret", "SEARXNG_URL": ""}[n]), patch("tavily_searxng._request", return_value={"results": []}) as request:
            Provider().search("query", 100)
        self.assertEqual(request.call_args.args[1]["max_results"], 20)
        self.assertEqual(request.call_args.args[2]["Authorization"], "Bearer secret")
