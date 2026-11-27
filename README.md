# Tavily → SearXNG for Hermes

A search-only Hermes backend. Uses keyed Tavily first; if unavailable, returns malformed data, or raises an HTTP/network error, it tries a configured SearXNG JSON endpoint. If only one is configured, it uses that one. Empty results are a successful search, not a fallback trigger, unless SearXNG also reports failed upstream engines, in which case the search fails explicitly. Search results are not merged; partial SearXNG engine failures and skipped malformed rows are reported in `metadata.partial`. Metadata also contains `provider`, `fallback`, `failed_providers`, and `skipped_results`. Errors never include upstream exception text or response bodies.

## Deploy (not performed by this repository)

1. Copy the `tavily_searxng` directory, including its `plugin.yaml`, into `$HERMES_HOME/plugins/web/tavily_searxng/` (use `~/.hermes` when `HERMES_HOME` is unset). Enable `web-tavily-searxng` using `hermes plugins enable web-tavily-searxng`, following your Hermes version's plugin commands. Restart Hermes.
2. Set `TAVILY_API_KEY` as a secret via the active profile's secret mechanism (e.g. profile `.env` with restrictive permissions). Configure `SEARXNG_URL` as an environment variable for the Hermes process, such as `http://localhost:8080`. The URL is a base URL, optionally with a path prefix, without credentials, query, or fragment. Enable JSON output on the SearXNG instance. At least one setting is required. No dependency installation is required beyond Hermes and Python.
3. Select the backend with `hermes config set web.search_backend tavily-searxng`. It does not implement extraction; configure a separate `web.extract_backend` if needed. Check with `hermes plugins list` and `hermes plugins doctor /path/to/tavily_searxng` before use.

See the [official provider guide](https://hermes-agent.nousresearch.com/docs/developer-guide/web-search-provider-plugin) and [plugin guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins). Config commands modify the active profile; review the target profile before running them.

## Security and behavior

* Queries are sent to Tavily and, on fallback, to SearXNG and potentially its upstream engines. Avoid confidential queries unless those destinations are approved. A failing paid Tavily request may still incur charges. A key is never sent to SearXNG, and redirects are rejected.
* Treat `SEARXNG_URL` as trusted administrator configuration; it can target internal network addresses. Use a trusted instance and HTTPS except for trusted loopback/private deployments. Network egress controls are recommended. Search results are untrusted web content, not instructions.
* No credentials, queries, or results are deliberately logged or persisted by this plugin. Hermes, proxies, Tavily, and SearXNG may have their own logging and retention policies. Returned web content may contain sensitive information.
* Each provider call starts with Tavily when configured; however, Hermes can cache successful search responses (including fallback or partial results), so identical queries may be served from cache until its TTL expires without invoking the plugin. Hermes cache settings apply across web tools; do not change them without considering the wider impact.
* Each HTTP operation has a 10-second socket timeout, maximum 2 MB response, and no retries; two providers may be attempted sequentially. Socket timeout is not a strict total wall-clock deadline (DNS and slowly streamed responses can take longer). Limits are clamped to 1–20. An empty upstream result is not evidence that every engine was healthy unless SearXNG reports it.

## Tests

From the repository root, with an installed Hermes source tree available:

```sh
PYTHONPATH=/opt/hermes:. python3 -m unittest discover -v
TMPDIR="$PWD" HERMES_HOME="$PWD/.doctor-home" hermes plugins doctor ./tavily_searxng --ci
```

Tests use stubbed transport and do not contact live search providers. Doctor performs isolated runtime discovery/import/registration, not a live query. Live integration depends on operator credentials and a configured SearXNG service.
