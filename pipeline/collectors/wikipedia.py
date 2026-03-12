"""
Wikipedia page view spike collector.
Uses Wikimedia REST API — free, no auth required.
Detects articles with significant view spikes vs. their 60-day baseline.
"""
import httpx
from datetime import date, timedelta
from loguru import logger
from pipeline.utils.rate_limiter import retry_with_backoff

WIKIMEDIA_BASE = "https://wikimedia.org/api/rest_v1"
HEADERS = {"User-Agent": "zeitgeist/1.0 (contact@zeitgeist.app)"}

# Top articles to seed — Wikipedia also provides a global top-1000 list daily
TOP_ARTICLES_URL = f"{WIKIMEDIA_BASE}/metrics/pageviews/top/en.wikipedia/all-access/{{year}}/{{month}}/{{day}}"
ARTICLE_VIEWS_URL = f"{WIKIMEDIA_BASE}/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/{{article}}/daily/{{start}}/{{end}}"


@retry_with_backoff(max_retries=3)
def get_top_articles(target_date: date | None = None) -> list[dict]:
    """Fetch top 1000 Wikipedia articles for a given date."""
    d = target_date or date.today() - timedelta(days=1)
    url = TOP_ARTICLES_URL.format(year=d.year, month=f"{d.month:02d}", day=f"{d.day:02d}")
    response = httpx.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    articles = response.json()["items"][0]["articles"]
    # Filter out meta pages
    skip_prefixes = ("Special:", "Wikipedia:", "File:", "Template:", "Help:", "Portal:", "Talk:", "User:")
    return [a for a in articles if not any(a["article"].startswith(p) for p in skip_prefixes)]


@retry_with_backoff(max_retries=3)
def get_article_views(article: str, days: int = 60) -> list[int]:
    """Get daily view counts for an article over the past N days."""
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days)
    url = ARTICLE_VIEWS_URL.format(
        article=article.replace(" ", "_"),
        start=start.strftime("%Y%m%d"),
        end=end.strftime("%Y%m%d"),
    )
    response = httpx.get(url, headers=HEADERS, timeout=30)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    items = response.json().get("items", [])
    return [item["views"] for item in items]


def collect(top_n: int = 100) -> list[dict]:
    """
    Returns list of {topic, raw_value, baseline_value, spike_score, signal_source, signal_category}
    for articles with significant spikes.
    """
    logger.info("Collecting Wikipedia signals...")
    results = []

    try:
        top_articles = get_top_articles()[:top_n]
    except Exception as e:
        logger.error(f"Wikipedia top articles fetch failed: {e}")
        return results

    for article_data in top_articles:
        article = article_data["article"]
        try:
            views = get_article_views(article, days=60)
            if len(views) < 7:
                continue

            current = views[-1]
            baseline = sum(views[:-7]) / max(len(views) - 7, 1)

            if baseline == 0:
                continue

            spike_score = (current - baseline) / baseline

            if spike_score > 0.5:  # 50% above baseline minimum
                results.append({
                    "topic": article.replace("_", " "),
                    "raw_value": current,
                    "baseline_value": round(baseline, 2),
                    "spike_score": round(spike_score, 4),
                    "signal_source": "wikipedia",
                    "signal_category": "demand",
                    "fired": spike_score > 1.0,  # fires if 2x baseline
                })
        except Exception as e:
            logger.warning(f"Wikipedia: failed to get views for {article}: {e}")

    logger.info(f"Wikipedia: {len(results)} topics with spikes, {sum(1 for r in results if r['fired'])} fired")
    return results
