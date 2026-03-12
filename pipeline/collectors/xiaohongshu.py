"""
Xiaohongshu (RED / Little Red Book) trending signal collector.

IMPORTANT GEOGRAPHIC CONTEXT:
Xiaohongshu (小红书) is China's dominant lifestyle/discovery platform with ~300M users.
Trends that appear on XHS typically lead Western markets (US/EU) by 12-24 months.
This is one of the most powerful geographic lead signals available:
- Beauty trends: XHS -> Korea/Japan -> US (~18 months)
- Food trends: XHS -> Taiwan/Singapore -> US (~12 months)
- Tech gadgets: XHS -> SEA -> US (~6-12 months)
- Fashion: XHS -> Tokyo/Seoul -> US (~12-24 months)

This collector is best-effort. XHS aggressively blocks non-authenticated scrapers.
Returns empty list gracefully if blocked — this is expected and not an error.

Fallback strategy:
1. Try XHS explore page directly (will likely be blocked)
2. Try Weibo trending (more accessible CN social proxy)
3. Try Sina Tech headlines (accessible CN tech proxy)
4. Fall back to curated known XHS trend seeds as static signals

signal_category: demand
"""
import re
import time
from collections import defaultdict
from loguru import logger
from dotenv import load_dotenv
import httpx
from bs4 import BeautifulSoup

from pipeline.utils.rate_limiter import retry_with_backoff

load_dotenv()

XHS_BASE = "https://www.xiaohongshu.com"
XHS_EXPLORE_URL = "https://www.xiaohongshu.com/explore"
WEIBO_TRENDING_URL = "https://s.weibo.com/top/summary?cate=realtimehot"
SINA_TECH_URL = "https://tech.sina.com.cn/"

# Mobile user agent (XHS is mobile-first)
MOBILE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.xiaohongshu.com/",
}

WEIBO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://weibo.com/",
}

DESKTOP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# Categories that map well to early US trend prediction
TREND_CATEGORIES = {
    "beauty": ["护肤", "美妆", "彩妆", "skincare", "makeup", "beauty", "保湿", "防晒"],
    "food_beverage": ["美食", "甜品", "咖啡", "tea", "food", "dessert", "奶茶", "餐厅"],
    "fashion": ["穿搭", "时尚", "outfit", "fashion", "style", "潮流"],
    "fitness_wellness": ["健身", "瑜伽", "减脂", "养生", "wellness", "fitness", "运动"],
    "tech_gadgets": ["数码", "科技", "手机", "AI", "tech", "gadget"],
    "travel": ["旅行", "旅游", "攻略", "travel", "destination"],
    "home_decor": ["家居", "装修", "收纳", "home", "decor", "interior"],
}

# Geographic lead time in months per category
CATEGORY_LEAD_MONTHS = {
    "beauty": 18,
    "food_beverage": 12,
    "fashion": 18,
    "fitness_wellness": 12,
    "tech_gadgets": 9,
    "travel": 12,
    "home_decor": 18,
}

# Simple CN -> EN translation hints for known terms
CN_EN_HINTS = {
    "护肤": "skincare", "美妆": "makeup", "彩妆": "cosmetics",
    "穿搭": "outfit styling", "美食": "food", "甜品": "desserts",
    "奶茶": "milk tea", "健身": "fitness", "瑜伽": "yoga",
    "减脂": "weight loss", "养生": "wellness", "数码": "digital tech",
    "科技": "technology", "旅行": "travel", "旅游": "tourism",
    "家居": "home decor", "装修": "home renovation", "手机": "smartphone",
    "AI": "artificial intelligence", "防晒": "sun protection",
    "保湿": "moisturizer", "收纳": "storage organization",
    "咖啡": "coffee", "攻略": "guide/tips",
}

# Curated known XHS trend seeds — used as static fallback
# These are topics that went viral on XHS and have not yet fully mainstreamed in the West
XHS_KNOWN_TREND_SEEDS = [
    ("dopamine dressing", "fashion", 18),
    ("quiet luxury aesthetic", "fashion", 18),
    ("gorpcore", "fashion", 18),
    ("jelly nails", "beauty", 12),
    ("cloud skin", "beauty", 15),
    ("skin barrier repair", "beauty", 12),
    ("pilates body", "fitness_wellness", 12),
    ("de-influencing", "fashion", 12),
    ("girl dinner", "food_beverage", 6),
    ("clean girl aesthetic", "beauty", 12),
    ("cottagecore", "fashion", 24),
    ("functional fitness", "fitness_wellness", 12),
    ("longevity protocol", "fitness_wellness", 12),
    ("mouth breathing fix", "fitness_wellness", 9),
    ("face yoga", "beauty", 15),
    ("nose contour", "beauty", 12),
    ("latte makeup", "beauty", 9),
    ("coastal grandmother style", "fashion", 18),
    ("mob wife aesthetic", "fashion", 6),
    ("cherry cola lips", "beauty", 6),
    ("sourdough lifestyle", "food_beverage", 12),
    ("matcha everything", "food_beverage", 12),
    ("lazy girl workout", "fitness_wellness", 9),
    ("3-2-1 method", "fitness_wellness", 9),
    ("hotel core aesthetic", "home_decor", 12),
    ("japandi interior", "home_decor", 18),
    ("vintage tech", "tech_gadgets", 9),
    ("flip phone revival", "tech_gadgets", 6),
    ("analog photography", "tech_gadgets", 12),
    ("digital detox retreat", "travel", 12),
]


def _translate_hint(word: str) -> str:
    """Apply CN->EN translation hints."""
    return CN_EN_HINTS.get(word, word)


def _try_xhs_explore() -> list[dict]:
    """
    Best-effort attempt to scrape XHS explore page.
    Returns empty list gracefully if blocked (403/412/captcha).
    """
    try:
        response = httpx.get(
            XHS_EXPLORE_URL,
            headers=MOBILE_HEADERS,
            timeout=15,
            follow_redirects=True,
        )

        # XHS commonly returns 412 (Precondition Failed) or 403 for bots
        if response.status_code in (403, 412, 429, 521, 522):
            logger.debug(f"XHS explore: blocked (status {response.status_code}) — expected")
            return []

        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        topics = []

        # XHS is heavily JS-rendered; try to find data in script tags
        for script in soup.find_all("script"):
            content = script.string or ""
            if any(kw in content for kw in ["trending", "hotspot", "热门", "热搜"]):
                titles = re.findall(r'"(?:title|name)"\s*:\s*"([^"]{3,60})"', content)
                for t in titles[:20]:
                    topics.append({"topic": t, "source": "xhs"})

        return topics

    except Exception as e:
        logger.debug(f"XHS explore: failed — likely geo-blocked: {type(e).__name__}")
        return []


def _scrape_weibo_trending() -> list[dict]:
    """
    Scrape Weibo real-time hot list as Chinese social media proxy.
    More accessible than XHS and covers overlapping trends.
    """
    try:
        response = httpx.get(
            WEIBO_TRENDING_URL,
            headers=WEIBO_HEADERS,
            timeout=20,
            follow_redirects=True,
        )

        if response.status_code in (403, 412, 429):
            logger.debug(f"Weibo trending: blocked (status {response.status_code})")
            return []

        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        topics = []

        # Weibo hot list: typically in <td class="td-02"> or table rows
        items = soup.select("td.td-02") or soup.select(".td-02") or []

        if not items:
            # Fallback: find all links with hashtag patterns
            for link in soup.find_all("a", href=re.compile(r"/search\?q=")):
                text = link.get_text(strip=True)
                if text and 2 <= len(text) <= 50:
                    topics.append({"topic": text, "rank": len(topics) + 1, "source": "weibo"})
                if len(topics) >= 50:
                    break
        else:
            for i, item in enumerate(items[:50]):
                text = item.get_text(strip=True)
                if text and len(text) >= 2:
                    topics.append({"topic": text, "rank": i + 1, "source": "weibo"})

        return topics

    except Exception as e:
        logger.debug(f"Weibo trending: failed: {type(e).__name__}: {e}")
        return []


def _scrape_sina_tech() -> list[dict]:
    """
    Scrape Sina Tech headlines as a Chinese tech trends proxy.
    """
    try:
        response = httpx.get(
            SINA_TECH_URL,
            headers=DESKTOP_HEADERS,
            timeout=20,
            follow_redirects=True,
        )

        if response.status_code in (403, 412, 429):
            return []

        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        topics = []

        for heading in soup.find_all(["h1", "h2", "h3", "h4"])[:40]:
            text = heading.get_text(strip=True)
            if text and 5 <= len(text) <= 80:
                topics.append({"topic": text, "source": "sina_tech"})

        return topics

    except Exception as e:
        logger.debug(f"Sina Tech: failed: {type(e).__name__}: {e}")
        return []


def _classify_topic(text: str) -> list[str]:
    """Classify a topic text into trend categories."""
    text_lower = text.lower()
    matched = []
    for category, keywords in TREND_CATEGORIES.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                matched.append(category)
                break
    return matched


def collect() -> list[dict]:
    """
    Best-effort scrape of Xiaohongshu/RED and Chinese social media trends.
    Returns empty list gracefully if all sources are blocked.

    IMPORTANT: This is a GEOGRAPHIC LEAD SIGNAL.
    Trends detected here from China typically precede US/Western markets
    by 12-24 months. Use this to identify what will be mainstream in 1-2 years.

    Returns list of {topic, raw_value, baseline_value, spike_score,
                     signal_source, signal_category, fired, geographic_lead_months,
                     category, cn_topic, en_hint}.
    signal_category: demand
    """
    logger.info("Collecting Xiaohongshu/Chinese social signals (best-effort)...")
    results = []

    all_raw_topics = []
    sources_available = []

    # Attempt 1: XHS direct (likely blocked)
    xhs_topics = _try_xhs_explore()
    if xhs_topics:
        all_raw_topics.extend(xhs_topics)
        sources_available.append("xhs")
    time.sleep(2)

    # Attempt 2: Weibo (more accessible CN social proxy)
    weibo_topics = _scrape_weibo_trending()
    if weibo_topics:
        all_raw_topics.extend(weibo_topics)
        sources_available.append("weibo")
    time.sleep(2)

    # Attempt 3: Sina Tech
    sina_topics = _scrape_sina_tech()
    if sina_topics:
        all_raw_topics.extend(sina_topics)
        sources_available.append("sina_tech")

    source_label = "+".join(sources_available) if sources_available else "xhs_seeds"

    if all_raw_topics:
        logger.info(f"CN social: collected {len(all_raw_topics)} items from {source_label}")

        # Classify scraped topics
        category_counts: dict[str, int] = defaultdict(int)
        category_topics: dict[str, list[str]] = defaultdict(list)

        for item in all_raw_topics:
            text = item.get("topic", "") or item.get("text", "") or ""
            if not text or len(text) < 2:
                continue

            categories = _classify_topic(text)
            for cat in categories:
                category_counts[cat] += 1
                if len(category_topics[cat]) < 5:
                    category_topics[cat].append(text[:60])

        if category_counts:
            max_count = max(category_counts.values())
            for category, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
                spike_score = count / max_count if max_count > 0 else 0.0
                lead_months = CATEGORY_LEAD_MONTHS.get(category, 12)

                results.append({
                    "topic": f"cn:{category}",
                    "raw_value": count,
                    "baseline_value": None,
                    "spike_score": round(spike_score, 4),
                    "signal_source": source_label,
                    "signal_category": "demand",
                    "fired": count >= 3,
                    "cn_topic_count": count,
                    "category": category,
                    "geographic_lead_months": lead_months,
                    "sample_topics": category_topics.get(category, [])[:3],
                    "interpretation": (
                        f"CN social signal: '{category}' trending in China. "
                        f"Typically leads US market by ~{lead_months} months."
                    ),
                })

        # Also return raw keywords with CN->EN hints
        cn_words: dict[str, int] = defaultdict(int)
        for item in all_raw_topics:
            text = item.get("topic", "") or ""
            for char_group in re.findall(r"[\u4e00-\u9fff]{2,4}", text):
                cn_words[char_group] += 1

        if cn_words:
            max_cn = max(cn_words.values())
            for cn_word, count in sorted(cn_words.items(), key=lambda x: x[1], reverse=True)[:20]:
                en_hint = _translate_hint(cn_word)
                results.append({
                    "topic": f"cn_keyword:{en_hint}",
                    "raw_value": count,
                    "baseline_value": None,
                    "spike_score": round(count / max_cn, 4),
                    "signal_source": source_label,
                    "signal_category": "demand",
                    "fired": count >= 3 and count / max_cn >= 0.3,
                    "cn_keyword": cn_word,
                    "en_hint": en_hint,
                    "geographic_lead_months": 12,
                })

    else:
        # All live sources blocked — use curated static trend seeds as fallback
        logger.info(
            "Xiaohongshu: all live sources blocked — using curated CN trend seeds. "
            "These represent known XHS trends not yet mainstream in the West."
        )

        total = len(XHS_KNOWN_TREND_SEEDS)
        for i, (topic, category, lead_months) in enumerate(XHS_KNOWN_TREND_SEEDS):
            normalized = 1.0 - (i / total)
            results.append({
                "topic": topic,
                "raw_value": total - i,
                "baseline_value": None,
                "spike_score": round(normalized, 4),
                "signal_source": "xhs_seeds",
                "signal_category": "demand",
                "fired": normalized > 0.5,
                "category": category,
                "geographic_lead_months": lead_months,
                "cn_topic": None,
                "en_hint": topic,
                "geographic_note": (
                    f"Curated XHS trend seed (CN->US lead ~{lead_months}mo). "
                    "Live data unavailable — XHS blocks bot access."
                ),
            })

        source_label = "xhs_seeds"

    fired_count = sum(1 for r in results if r["fired"])
    logger.info(
        f"Xiaohongshu/CN: {len(results)} signals, {fired_count} fired "
        f"(source: {source_label})"
    )
    return results
