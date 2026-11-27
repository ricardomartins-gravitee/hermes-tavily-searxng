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

    def test_invalid_queries_never_reach_transport(self):
        from tavily_searxng import Provider
        for query in ("x" * 10001, "bad\ud800"):
            with self.subTest(query=repr(query)), patch("tavily_searxng._request") as request:
                self.assertFalse(Provider().search(query)["success"])
                request.assert_not_called()

    def test_empty_url_delimiters_are_rejected(self):
        from tavily_searxng import Provider
        for url in ("https://example.org?", "https://example.org#"):
            with self.subTest(url=url), patch("tavily_searxng.get_provider_env", side_effect=lambda n: {"TAVILY_API_KEY": "", "SEARXNG_URL": url}[n]), patch("tavily_searxng._request") as request:
                self.assertFalse(Provider().search("query")["success"])
                request.assert_not_called()

    def test_hostile_output_is_bounded_and_safe(self):
        from tavily_searxng import Provider
        data = {"results": [{"url": "https://example.org", "title": "a" * 20000, "content": "b" * 100000}, {"url": "https://example.org/secret-key", "title": "secret-key"}]}
        with patch("tavily_searxng.get_provider_env", side_effect=lambda n: {"TAVILY_API_KEY": "secret-key", "SEARXNG_URL": ""}[n]), patch("tavily_searxng._request", return_value=data):
            result = Provider().search("query")
        self.assertNotIn("secret-key", str(result))
        self.assertLess(len(str(result)), 20000)
        self.assertTrue(result["metadata"]["partial"])

    def test_malformed_engine_metadata_is_not_accepted(self):
        from tavily_searxng import Provider
        with patch("tavily_searxng.get_provider_env", side_effect=lambda n: {"TAVILY_API_KEY": "", "SEARXNG_URL": "https://example.org"}[n]), patch("tavily_searxng._request", return_value={"results": [], "unresponsive_engines": {}}):
            self.assertFalse(Provider().search("query")["success"])

    def test_surrogates_in_upstream_text_are_safe(self):
        from tavily_searxng import Provider
        with patch("tavily_searxng.get_provider_env", side_effect=lambda n: {"TAVILY_API_KEY": "key", "SEARXNG_URL": ""}[n]), patch("tavily_searxng._request", return_value={"results": [{"url": "https://example.org", "title": "bad\ud800"}]}):
            result = Provider().search("query")
        result["data"]["web"][0]["title"].encode("utf-8")

    def test_rejects_unsafe_url_authority_and_controls(self):
        from tavily_searxng import Provider
        for base in ("https://@example.org", "https://example.org:bad", "https://example.org/\npath"):
            with self.subTest(base=repr(base)), patch("tavily_searxng.get_provider_env", side_effect=lambda n: {"TAVILY_API_KEY": "", "SEARXNG_URL": base}[n]), patch("tavily_searxng._request") as request:
                self.assertFalse(Provider().search("query")["success"])
                request.assert_not_called()

    def test_tavily_metadata_does_not_mark_partial(self):
        from tavily_searxng import Provider
        with patch("tavily_searxng.get_provider_env", side_effect=lambda n: {"TAVILY_API_KEY": "key", "SEARXNG_URL": ""}[n]), patch("tavily_searxng._request", return_value={"results": [], "unresponsive_engines": {"untrusted": True}}):
            self.assertFalse(Provider().search("query")["metadata"]["partial"])

    def test_truncated_row_is_not_counted_as_skipped(self):
        from tavily_searxng import Provider
        with patch("tavily_searxng.get_provider_env", side_effect=lambda n: {"TAVILY_API_KEY": "key", "SEARXNG_URL": ""}[n]), patch("tavily_searxng._request", return_value={"results": [{"url": "https://example.org", "content": "x" * 5000}]}):
            result = Provider().search("query")
        self.assertEqual(result["metadata"]["skipped_results"], 0)
        self.assertTrue(result["metadata"]["partial"])
