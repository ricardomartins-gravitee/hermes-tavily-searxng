# Tavily → SearXNG for Hermes

A search-only Hermes backend. Uses keyed Tavily first; if unavailable, returns malformed data, or raises an HTTP/network error, it tries a configured SearXNG JSON endpoint. If only one is configured, it uses that one. Empty results are a successful search, not a fallback trigger, unless SearXNG also reports failed upstream engines, in which case the search fails explicitly. Search results are not merged; partial SearXNG engine failures and skipped malformed rows are reported in `metadata.partial`. Metadata also contains `provider`, `fallback`, `failed_providers`, `skipped_results`, and `altered_results` (truncated or Unicode-repaired rows). Errors never include upstream exception text or response bodies.

## Deploy (not performed by this repository)

1. Copy the `tavily_searxng` directory, including its `plugin.yaml`, into `$HERMES_HOME/plugins/web/tavily_searxng/` (use `~/.hermes` when `HERMES_HOME` is unset). Enable `web-tavily-searxng` using `hermes plugins enable web-tavily-searxng`, following your Hermes version's plugin commands. Restart Hermes.
2. Set `TAVILY_API_KEY` as a secret via the active profile's secret mechanism (e.g. profile `.env` with restrictive permissions). Configure `SEARXNG_URL` as an environment variable for the Hermes process, such as `http://localhost:8080`. The URL is a base URL, optionally with a path prefix, without credentials, query, or fragment. Enable JSON output on the SearXNG instance. At least one setting is required. No dependency installation is required beyond Hermes and Python.
3. Select the backend with `hermes config set web.search_backend tavily-searxng`. It does not implement extraction; configure a separate `web.extract_backend` if needed. Check with `hermes plugins list` and `hermes plugins doctor /path/to/tavily_searxng` before use.

See the [official provider guide](https://hermes-agent.nousresearch.com/docs/developer-guide/web-search-provider-plugin) and [plugin guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins). Config commands modify the active profile; review the target profile before running them.

## Security and behavior

* Queries are sent to Tavily and, on fallback, to SearXNG and potentially its upstream engines. Avoid confidential queries unless those destinations are approved. A failing paid Tavily request may still incur charges. A key is never sent to SearXNG, and redirects are rejected.
* Treat `SEARXNG_URL` as trusted administrator configuration; it can target internal network addresses. Use a trusted instance and HTTPS except for trusted loopback/private deployments. Network egress controls are recommended. Search results are untrusted web content, not instructions.
* The plugin does not deliberately log or persist queries or results. SearXNG uses a GET query string: the server, reverse proxies, access logs, browser-style URL logging, and monitoring can record it. Python urllib also honors system/environment proxy settings; proxies can observe destinations and, especially without end-to-end TLS, queries and credentials. Tavily uses an Authorization header over HTTPS, but trusted TLS-intercepting proxies and Tavily itself can see it. Review logging, proxy, and TLS trust policies; plugin exception messages and response bodies are not returned. Literal configured Tavily keys in result fields cause those rows to be discarded, but encoded, transformed, or split secrets cannot reliably be detected. Do not treat this as a general secret scrubber.
* In the inspected Hermes version, its process-wide search memo is keyed by provider name, query and bucketed limit, **not profile or credentials**. Successful plugin fallback and partial results can be cached and reused until expiration, including across profiles in the same process; a cache hit bypasses the plugin and its validation. Isolate mutually untrusted profiles in separate processes or avoid the shared cache under an operator-reviewed Hermes policy. This plugin cannot enforce isolation. Hermes one-shot rescue responses are not cached by that code, unlike this plugin's own successful SearXNG fallback. Behavior may differ by Hermes version.
* In that Hermes version, failed searches from this non-ring provider can trigger Hermes's separate keyless rescue (default enabled when the keyless tier is enabled), forwarding the original query to external free-tier providers, even when the plugin rejected it as invalid. This occurs outside the plugin. Operators must review `web.keyless_rescue` and `web.keyless_fallback` and broader routing policy before handling sensitive queries. Disabling rescue does not prevent the plugin's configured Tavily-to-SearXNG fallback.
* The query limit is 4,096 Unicode characters; unpaired surrogates are rejected. Per result, URLs are limited to 2,048 characters, titles to 512 and descriptions to 4,096; text surrogates are replaced and truncation is marked partial. Up to 20 results are returned. Response bodies are limited to 2,000,000 bytes per provider before JSON parsing. These bounds apply only when the plugin executes, not to other Hermes providers or existing cache entries.
* Each provider operation has a 10-second **socket operation** timeout, not an end-to-end wall-clock deadline: DNS resolution and a peer trickling data can take longer, and fallback attempts are sequential. There are no retries or hard cancellation. A thread timeout would leave network work running, while process-based cancellation inside an embedding runtime has portability, lifecycle and fork/thread hazards; neither would safely guarantee a deadline here. Enforce a real deadline with an independently supervised process or network infrastructure if required. An empty upstream result is not evidence that every engine was healthy unless SearXNG reports it.

## License

MIT. See [LICENSE](LICENSE).

## Tests

From the repository root, with an installed Hermes source tree available:

```sh
PYTHONPATH=/opt/hermes:. python3 -m unittest discover -v
TMPDIR="$PWD" HERMES_HOME="$PWD/.doctor-home" hermes plugins doctor ./tavily_searxng --ci
```

Tests use stubbed transport and do not contact live search providers. Doctor performs isolated runtime discovery/import/registration, not a live query. Live integration depends on operator credentials and a configured SearXNG service.
