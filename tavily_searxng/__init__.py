"""Search-only Hermes backend: keyed Tavily with SearXNG fallback."""
import json
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from agent.web_search_provider import WebSearchProvider, get_provider_env

TIMEOUT = 10
MAX_BODY = 2_000_000

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request(url, payload, headers):
    # No redirects: never forward bearer credentials or silently change endpoint.
    if headers.get('Authorization'):
        request = Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')
    else:
        request = Request(url + '?' + urlencode(payload), headers=headers, method='GET')
    with build_opener(_NoRedirect()).open(request, timeout=TIMEOUT) as response:
        raw = response.read(MAX_BODY + 1)
    if len(raw) > MAX_BODY:
        raise ValueError('response too large')
    return json.loads(raw)


def _normalize(data, limit):
    if not isinstance(data, dict) or not isinstance(data.get('results'), list) or data.get('error'):
        raise ValueError('invalid response')
    rows, skipped = [], 0
    for item in data['results']:
        if not isinstance(item, dict) or not isinstance(item.get('url'), str):
            skipped += 1
            continue
        url = item['url']
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                skipped += 1
                continue
        except ValueError:
            skipped += 1
            continue
        title, content = item.get('title'), item.get('content')
        rows.append({'title': title if isinstance(title, str) else '', 'url': url,
                     'description': content if isinstance(content, str) else '', 'position': len(rows) + 1})
        if len(rows) >= limit:
            break
    if data['results'] and not rows:
        raise ValueError('no usable results')
    return rows, skipped


class Provider(WebSearchProvider):
    @property
    def name(self):
        return 'tavily-searxng'

    @property
    def display_name(self):
        return 'Tavily with SearXNG fallback'

    def is_available(self):
        return bool(get_provider_env('TAVILY_API_KEY') or get_provider_env('SEARXNG_URL'))

    def search(self, query, limit=5):
        try:
            limit = max(1, min(int(limit), 20))
        except (TypeError, ValueError, OverflowError):
            return {'success': False, 'error': 'Invalid search limit.'}
        if not isinstance(query, str) or not query.strip():
            return {'success': False, 'error': 'Search query must be non-empty.'}
        key = get_provider_env('TAVILY_API_KEY')
        base = get_provider_env('SEARXNG_URL').rstrip('/')
        attempts = []
        if key:
            attempts.append(('tavily', 'https://api.tavily.com/search', {'query': query, 'max_results': limit, 'include_raw_content': False, 'include_images': False}, {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}))
        if base:
            try:
                parts = urlsplit(base)
                valid = parts.scheme in ('http', 'https') and parts.hostname and not parts.username and not parts.password and not parts.query and not parts.fragment
            except ValueError:
                valid = False
            if valid:
                attempts.append(('searxng', base + '/search', {'q': query, 'format': 'json', 'pageno': 1}, {'Accept': 'application/json'}))
        failed = []
        for name, url, payload, headers in attempts:
            try:
                data = _request(url, payload, headers)
                rows, skipped = _normalize(data, limit)
                if name == 'searxng' and not rows and data.get('unresponsive_engines'):
                    raise ValueError('no results with upstream engine failures')
                partial = bool(skipped or data.get('unresponsive_engines'))
                return {'success': True, 'data': {'web': rows}, 'metadata': {'provider': name, 'fallback': name == 'searxng' and bool(key), 'failed_providers': failed, 'skipped_results': skipped, 'partial': partial}}
            except Exception:
                # Neither raw exceptions nor upstream bodies may escape (they may contain secrets).
                failed.append(name)
        return {'success': False, 'error': 'No configured search provider succeeded.', 'metadata': {'failed_providers': failed}}


def register(ctx):
    ctx.register_web_search_provider(Provider())
