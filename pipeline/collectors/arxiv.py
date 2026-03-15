"""
ArXiv + Semantic Scholar paper velocity collector.
Uses ArXiv API (free, no auth) and Semantic Scholar Graph API (free, no auth).
Tracks paper count spikes in AI/ML/bio/econ categories over last 14 days
vs a 90-day rolling baseline — sudden research surges = builder leading signal.
signal_category: builder
"""
import re
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, timedelta
from loguru import logger
from dotenv import load_dotenv
import httpx

from pipeline.utils.rate_limiter import retry_with_backoff, rate_limited

load_dotenv()

ARXIV_API = "https://export.arxiv.org/api/query"
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"

# ArXiv category codes to monitor
ARXIV_CATEGORIES = [
    "cs.AI",   # Artificial Intelligence
    "cs.LG",   # Machine Learning
    "cs.HC",   # Human-Computer Interaction
    "cs.CL",   # Computation and Language (NLP)
    "cs.CV",   # Computer Vision
    "q-bio",   # Quantitative Biology
    "econ",    # Economics
    "stat.ML", # Statistics - Machine Learning
]

# Topic keywords to search across categories
TOPIC_QUERIES = [
    "large language model",
    "transformer architecture",
    "diffusion model",
    "reinforcement learning human feedback",
    "multimodal",
    "autonomous agent",
    "protein structure",
    "drug discovery machine learning",
    "quantum computing",
    "federated learning",
    "mechanistic interpretability",
    "retrieval augmented generation",
    "world model",
    "embodied AI",
    "synthetic biology",
]

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "using", "based", "via", "new", "towards", "approach", "method",
    "study", "analysis", "evaluation", "benchmark", "survey",
    "paper", "work", "model", "models", "learning", "deep",
}


@retry_with_backoff(max_retries=3)
def _fetch_arxiv_category(category: str, days: int = 14, max_results: int = 100) -> list[dict]:
    """
    Fetch recent papers from ArXiv for a given category.
    Returns list of {title, summary, categories, published}.
    """
    start_date = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
    query = f"cat:{category} AND submittedDate:[{start_date}0000 TO 99991231235959]"

    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    response = httpx.get(ARXIV_API, params=params, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    papers = []
    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        summary_el = entry.find("atom:summary", ns)
        published_el = entry.find("atom:published", ns)

        title = title_el.text.strip() if title_el is not None else ""
        summary = summary_el.text.strip() if summary_el is not None else ""
        published = published_el.text.strip() if published_el is not None else ""

        cats = [c.get("term", "") for c in entry.findall("atom:category", ns)]

        if title:
            papers.append({
                "title": title,
                "summary": summary[:500],
                "categories": cats,
                "published": published,
            })

    return papers


@retry_with_backoff(max_retries=3)
def _fetch_arxiv_baseline(category: str, days: int = 90) -> int:
    """
    Estimate baseline paper count for a category over the past N days.
    Uses a coarse count from ArXiv search (total results estimate).
    """
    start_date = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
    query = f"cat:{category} AND submittedDate:[{start_date}0000 TO 99991231235959]"

    params = {
        "search_query": query,
        "start": 0,
        "max_results": 1,  # We only need the totalResults count
    }

    response = httpx.get(ARXIV_API, params=params, timeout=30)
    response.raise_for_status()

    root = ET.fromstring(response.text)
    ns_opensearch = "http://a9.com/-/spec/opensearch/1.1/"
    total_el = root.find(f"{{{ns_opensearch}}}totalResults")
    return int(total_el.text) if total_el is not None else 0


@retry_with_backoff(max_retries=3)
def _fetch_semantic_scholar(query: str, days: int = 14) -> list[dict]:
    """
    Search Semantic Scholar for high-citation-velocity papers.
    Returns papers with citationCount and influentialCitationCount.
    """
    params = {
        "query": query,
        "limit": 50,
        "fields": "title,abstract,year,citationCount,influentialCitationCount,publicationDate,externalIds",
    }

    headers = {"User-Agent": "zeitgeist/1.0"}
    response = httpx.get(SEMANTIC_SCHOLAR_API, params=params, headers=headers, timeout=30)
    response.raise_for_status()

    cutoff = date.today() - timedelta(days=days)
    papers = []
    for paper in response.json().get("data", []):
        pub_date_str = paper.get("publicationDate", "")
        if pub_date_str:
            try:
                pub_date = date.fromisoformat(pub_date_str[:10])
                if pub_date < cutoff:
                    continue
            except ValueError:
                pass

        papers.append({
            "title": paper.get("title", ""),
            "citation_count": paper.get("citationCount", 0),
            "influential_citation_count": paper.get("influentialCitationCount", 0),
        })

    return papers


def _extract_ngrams(text: str, n: int = 2) -> list[str]:
    """Extract n-grams from text, filtered by stopwords."""
    words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9]{2,}\b", text.lower())
    filtered = [w for w in words if w not in STOPWORDS]

    if n == 1:
        return filtered
    return [" ".join(filtered[i:i+n]) for i in range(len(filtered) - n + 1)]


def collect() -> list[dict]:
    """
    Collects paper count signals from ArXiv and Semantic Scholar.
    Returns list of {topic, raw_value, baseline_value, spike_score,
                     signal_source, signal_category, fired, paper_count_14d,
                     baseline_90d_avg, top_cited_papers}.
    Fires if 14-day paper count significantly exceeds the per-14-day 90-day baseline.
    signal_category: builder
    """
    logger.info("Collecting ArXiv/Semantic Scholar signals...")
    results = []

    # --- ArXiv category-level signals ---
    category_signals = []
    for category in ARXIV_CATEGORIES:
        try:
            # Fetch recent papers (14 days) — for titles/keywords
            recent_papers = _fetch_arxiv_category(category, days=14)

            time.sleep(3)  # ArXiv is sensitive to rapid requests

            # Use true count (not capped by max_results) for spike calculation
            recent_count = _fetch_arxiv_baseline(category, days=14)

            time.sleep(3)

            # Estimate baseline (90 days -> divide by (90/14) to get per-14-day equivalent)
            baseline_90d = _fetch_arxiv_baseline(category, days=90)
            baseline_per_14d = baseline_90d / (90 / 14)

            time.sleep(3)

            if baseline_per_14d == 0:
                spike_score = 0.0
            else:
                spike_score = (recent_count - baseline_per_14d) / baseline_per_14d

            # Extract topic keywords from titles of recent papers
            topic_freq: dict[str, int] = defaultdict(int)
            for paper in recent_papers:
                for bigram in _extract_ngrams(paper["title"], n=2):
                    topic_freq[bigram] += 1
                for unigram in _extract_ngrams(paper["title"], n=1):
                    topic_freq[unigram] += 1

            top_topics = sorted(topic_freq.items(), key=lambda x: x[1], reverse=True)[:5]

            category_signals.append({
                "topic": f"arxiv:{category}",
                "raw_value": recent_count,
                "baseline_value": round(baseline_per_14d, 1),
                "spike_score": round(spike_score, 4),
                "signal_source": "arxiv",
                "signal_category": "builder",
                "fired": spike_score > 0.25,  # 25% above baseline
                "paper_count_14d": recent_count,
                "baseline_90d_avg": round(baseline_per_14d, 1),
                "top_keywords": [t for t, _ in top_topics],
                "arxiv_category": category,
            })

            logger.debug(
                f"ArXiv {category}: {recent_count} papers (14d), "
                f"baseline {baseline_per_14d:.1f}, spike={spike_score:.2f}"
            )

        except Exception as e:
            logger.warning(f"ArXiv: failed for category {category}: {e}")

        time.sleep(2)

    results.extend(category_signals)

    # --- Semantic Scholar topic-level signals ---
    topic_citation_scores: dict[str, float] = defaultdict(float)
    topic_paper_counts: dict[str, int] = defaultdict(int)
    topic_top_papers: dict[str, list[str]] = defaultdict(list)

    for query in TOPIC_QUERIES:
        try:
            papers = _fetch_semantic_scholar(query, days=14)

            for paper in papers:
                # Citation velocity: influential citations are worth more
                citation_weight = (
                    paper["citation_count"] * 1.0
                    + paper["influential_citation_count"] * 3.0
                )
                topic_citation_scores[query] += citation_weight
                topic_paper_counts[query] += 1
                if paper["title"] and len(topic_top_papers[query]) < 3:
                    topic_top_papers[query].append(paper["title"][:100])

            logger.debug(
                f"Semantic Scholar '{query}': {len(papers)} recent papers"
            )
            time.sleep(2)

        except Exception as e:
            logger.warning(f"Semantic Scholar: failed for query '{query}': {e}")

    # Normalize Semantic Scholar scores
    if topic_citation_scores:
        max_citation_score = max(topic_citation_scores.values())
        for query in TOPIC_QUERIES:
            if query not in topic_citation_scores:
                continue
            raw = topic_citation_scores[query]
            paper_count = topic_paper_counts[query]
            spike_score = raw / max_citation_score if max_citation_score > 0 else 0.0

            results.append({
                "topic": query,
                "raw_value": round(raw, 2),
                "baseline_value": None,  # Semantic Scholar doesn't expose historical
                "spike_score": round(spike_score, 4),
                "signal_source": "semantic_scholar",
                "signal_category": "builder",
                "fired": spike_score > 0.2 and paper_count >= 3,
                "paper_count_14d": paper_count,
                "baseline_90d_avg": None,
                "top_cited_papers": topic_top_papers.get(query, []),
            })

    logger.info(
        f"ArXiv/Scholar: {len(results)} signals, "
        f"{sum(1 for r in results if r['fired'])} fired"
    )
    return results
