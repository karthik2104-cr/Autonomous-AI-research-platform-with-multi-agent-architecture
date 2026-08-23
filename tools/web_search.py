import logging
import time

logger = logging.getLogger(__name__)

_RETRY_DELAY_SECONDS = 1.5


def _search_once(query: str, max_results: int) -> list[dict[str, str]]:
    from ddgs import DDGS

    with DDGS() as client:
        raw = list(client.text(query, max_results=max_results))

    results: list[dict[str, str]] = []
    for item in raw:
        title = str(item.get("title") or "")
        url = str(item.get("href") or item.get("url") or "")
        snippet = str(item.get("body") or item.get("snippet") or "")
        if not url and not snippet:
            continue
        results.append({"title": title, "url": url, "snippet": snippet})
    return results


def web_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Return [{title, url, snippet}, ...]. Never raises — empty list on failure."""
    try:
        return _search_once(query, max_results)
    except Exception:
        logger.warning("web_search failed for %r; retrying once", query, exc_info=True)
        time.sleep(_RETRY_DELAY_SECONDS)
        try:
            return _search_once(query, max_results)
        except Exception:
            logger.warning("web_search retry failed for %r; returning no results", query, exc_info=True)
            return []
