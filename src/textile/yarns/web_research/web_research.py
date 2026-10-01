"""
Live Web Research & Internet Search Capability Yarn.
Provides search query execution and webpage content fetching.
Layer 10 (Core POSIX).
"""

import contextlib
import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request

from textile import Yarn, strand

MAX_WEBPAGE_BODY_CHARS = 12000
MIN_FALLBACK_RESULTS = 2


def _search_ddg_lite(query: str, max_results: int = 8) -> list[tuple[str, str, str]]:
    """Query DuckDuckGo Lite endpoint using text browser headers."""
    url = "https://lite.duckduckgo.com/lite/"
    data = urllib.parse.urlencode({"q": query}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": "w3m/0.5.3+git20230121",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=6) as resp:  # noqa: S310
        content = resp.read().decode("utf-8", errors="replace")

    pattern = re.compile(
        r"<a[^>]+href=[\'\"](?P<url>[^\'\"]+)[\'\"][^>]*class=[\'\"]result-link[\'\"][^>]*>(?P<title>.*?)</a>"
        r".*?"
        r"<td[^>]*class=[\'\"]result-snippet[\'\"][^>]*>(?P<snippet>.*?)</td>",
        re.DOTALL | re.IGNORECASE,
    )

    results: list[tuple[str, str, str]] = []
    for match in pattern.finditer(content):
        href = match.group("url").strip()
        title = html.unescape(re.sub(r"<[^>]+>", "", match.group("title"))).strip()
        snippet = html.unescape(re.sub(r"<[^>]+>", "", match.group("snippet"))).strip()
        if href and title:
            results.append((title, href, snippet))
        if len(results) >= max_results:
            break
    return results


def search_web(query: str) -> str:
    """Execute a web search and return formatted text results."""
    clean_query = query.strip()
    if not clean_query:
        return "Error: Empty search query provided."

    results: list[tuple[str, str, str]] = []

    # 1. DuckDuckGo Instant Answer API
    with contextlib.suppress(urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        ddg_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(clean_query)}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(ddg_url, headers={"User-Agent": "TextileAgent/1.0 (Universal Linux Desktop)"})
        with urllib.request.urlopen(req, timeout=4) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            abstract = data.get("AbstractText", "")
            heading = data.get("Heading", "")
            abstract_url = data.get("AbstractURL", "")
            if abstract and heading:
                results.append((f"Abstract: {heading}", abstract_url, abstract))

            for topic in data.get("RelatedTopics", [])[:3]:
                if isinstance(topic, dict) and "FirstURL" in topic and "Text" in topic:
                    results.append((topic["Text"][:60] + "...", topic["FirstURL"], topic["Text"]))

    # 2. Wikipedia Full-Text Search API
    with contextlib.suppress(urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        wiki_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&utf8=&format=json&srlimit=5"
        req = urllib.request.Request(wiki_url, headers={"User-Agent": "TextileAgent/1.0 (Universal Linux Desktop)"})
        with urllib.request.urlopen(req, timeout=4) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            search_items = data.get("query", {}).get("search", [])
            for item in search_items:
                title = item.get("title", "")
                snippet = html.unescape(re.sub(r"<[^>]+>", "", item.get("snippet", ""))).strip()
                page_url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
                if title and page_url:
                    results.append((title, page_url, snippet))

    # 3. DuckDuckGo Lite Fallback HTML scraper if API returned fewer than 2 results
    if len(results) < MIN_FALLBACK_RESULTS:
        with contextlib.suppress(urllib.error.URLError, OSError, ValueError):
            ddg_lite_items = _search_ddg_lite(clean_query)
            for title, url, snippet in ddg_lite_items:
                if not any(r[1] == url for r in results):
                    results.append((title, url, snippet))

    if not results:
        return f"No search results found for query '{clean_query}'."

    output_lines = [f"## Web Search Results for '{clean_query}':\n"]
    for i, (title, url, snippet) in enumerate(results[:8], 1):
        output_lines.append(f"{i}. **{title}**\n   URL: {url}\n   Snippet: {snippet}\n")

    return "\n".join(output_lines)


def fetch_webpage(url: str) -> str:
    """Fetch and extract readable plain text content from a web page URL."""
    url_clean = url.strip()
    if not url_clean.startswith(("http://", "https://")):
        url_clean = "https://" + url_clean

    try:
        req = urllib.request.Request(  # noqa: S310
            url_clean,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"},
        )
        with urllib.request.urlopen(req, timeout=12) as response:  # noqa: S310
            response.headers.get("Content-Type", "")
            raw_data = response.read()

        text = raw_data.decode("utf-8", errors="replace")

        # Remove script and style tags
        text = re.sub(r'<script[^>]*">.*?</script>', "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)

        # Strip HTML tags
        clean_text = html.unescape(re.sub(r"<[^>]+>", " ", text))

        # Collapse whitespace
        lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
        body = "\n".join(lines)

        if len(body) > MAX_WEBPAGE_BODY_CHARS:
            body = body[:MAX_WEBPAGE_BODY_CHARS] + "\n\n...[Content Truncated]"

        return f"## Web Page Content for {url_clean}:\n\n{body}"
    except (urllib.error.URLError, OSError, ValueError, UnicodeDecodeError) as e:
        return f"Error fetching webpage '{url_clean}': {e}"


class WebResearch(Yarn):
    def is_available(self) -> bool:
        return True

    @strand(tier="observe")
    def search_web(self, query: str) -> str:
        """Search the internet for documentation, code examples, API references, or solutions.

        :param query: Search query terms.
        """
        return search_web(query)

    @strand(tier="observe")
    def fetch_webpage(self, url: str) -> str:
        """Fetch and read the text content of a web page URL.

        :param url: Complete URL of the web page to read.
        """
        return fetch_webpage(url)
