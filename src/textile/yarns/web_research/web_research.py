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

from textile.core.base import Yarn, strand

MAX_WEBPAGE_BODY_CHARS = 12000


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
        r'<a[^>]+href=[\'\"](?P<url>[^\'\"]+)[\'\"][^>]*class=[\'\"]result-link[\'\"][^>]*>(?P<title>.*?)</a>'
        r".*?"
        r'<td[^>]+class=[\'\"]result-snippet[\'\"][^>]*>(?P<snippet>.*?)</td>',
        re.DOTALL,
    )
    pattern_alt = re.compile(
        r'<a[^>]+class=[\'\"]result-link[\'\"][^>]*href=[\'\"](?P<url>[^\'\"]+)[\'\"][^>]*>(?P<title>.*?)</a>'
        r".*?"
        r'<td[^>]+class=[\'\"]result-snippet[\'\"][^>]*>(?P<snippet>.*?)</td>',
        re.DOTALL,
    )

    matches = list(pattern.finditer(content)) or list(pattern_alt.finditer(content))
    results = []
    for m in matches[:max_results]:
        href = m.group("url")
        title = html.unescape(re.sub(r"<[^>]+>", "", m.group("title"))).strip()
        snip = html.unescape(re.sub(r"<[^>]+>", "", m.group("snippet"))).strip()
        if "uddg=" in href:
            href = urllib.parse.unquote(href.split("uddg=")[-1].split("&")[0])
        if title and href:
            results.append((title, href, snip))
    return results


def _search_ddg_instant_and_wiki(query: str) -> list[tuple[str, str, str]]:
    """Fallback search using DuckDuckGo Instant Answer API and Wikipedia Full-Text Search API."""
    results = []
    # 1. DuckDuckGo Instant Answer API
    with contextlib.suppress(urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        api_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0 (Linux)"})
        with urllib.request.urlopen(req, timeout=4) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            abstract = data.get("AbstractText")
            source_url = data.get("AbstractURL")
            heading = data.get("Heading", query)
            if abstract and source_url:
                results.append((heading, source_url, abstract))
            for topic in data.get("RelatedTopics", [])[:3]:
                if isinstance(topic, dict) and topic.get("Text") and topic.get("FirstURL"):
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

    return results


def search_web(query: str) -> str:
    """Execute a web search and return formatted text results."""
    query_clean = query.strip()
    if not query_clean:
        return "Error: Empty search query."

    items: list[tuple[str, str, str]] = []
    with contextlib.suppress(urllib.error.URLError, OSError, ValueError):
        items = _search_ddg_lite(query_clean, max_results=8)

    if not items:
        with contextlib.suppress(urllib.error.URLError, OSError, ValueError):
            items = _search_ddg_instant_and_wiki(query_clean)

    if not items:
        return f"No web search results found for '{query_clean}'."

    formatted = []
    for title, url, snippet in items:
        formatted.append(f"### [{title}]({url})\n{snippet}\n")

    return f"## Web Search Results for '{query_clean}':\n\n" + "\n".join(formatted)


def fetch_webpage(url: str) -> str:
    """Fetch and return text content from a target URL."""
    url_clean = url.strip()
    if not url_clean.startswith("http://") and not url_clean.startswith("https://"):
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

    @strand(description="Search the internet for documentation, API references, or error solutions.")
    def search_web(self, query: str) -> str:
        """Search the internet for documentation, code examples, API references, or solutions.

        :param query: Search query terms.
        """
        return search_web(query)

    @strand(description="Fetch and read the text content of a web page URL.")
    def fetch_webpage(self, url: str) -> str:
        """Fetch and read the text content of a web page URL.

        :param url: Complete URL of the web page to read.
        """
        return fetch_webpage(url)
