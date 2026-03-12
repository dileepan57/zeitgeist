"""
Financial markets signal collector.
Uses yfinance library to track unusual volume in theme ETFs (ARK funds, sector ETFs).
Also tracks trending crypto from CoinGecko free API.
Fires if volume > 2x 30-day average — money moving into a theme = strong conviction signal.
signal_category: money
"""
import time
from datetime import date, timedelta
from loguru import logger
from dotenv import load_dotenv
import httpx

from pipeline.utils.rate_limiter import retry_with_backoff, rate_limited

load_dotenv()

COINGECKO_API = "https://api.coingecko.com/api/v3"

# Theme-mapped ETFs
# key = human-readable theme, value = list of ETF tickers
THEME_ETFS = {
    "AI & Innovation": ["ARKK", "ARKW", "AIQ", "BOTZ", "ROBO", "IRBO"],
    "Genomics & Biotech": ["ARKG", "IBB", "XBI", "GNOM"],
    "Fintech": ["ARKF", "FINX", "IPAY"],
    "Space & Defense": ["ARKX", "UFO", "ITA", "XAR"],
    "Clean Energy": ["ICLN", "QCLN", "ACES", "TAN", "FAN", "ARKO"],
    "Cybersecurity": ["HACK", "CIBR", "BUG"],
    "Cloud Computing": ["SKYY", "WCLD", "CLOU"],
    "Semiconductors": ["SOXX", "SMH", "SOXQ"],
    "EV & Autonomous": ["DRIV", "KARS", "IDRV", "LIT"],
    "Blockchain & Crypto": ["BKCH", "BLOK", "LEGR", "BITQ"],
    "Healthcare Innovation": ["IDNA", "HLTH", "PINK"],
    "Emerging Markets Tech": ["EMQQ", "KWEBcls", "CQQQ"],
    "Metaverse & VR": ["META", "METV", "XR"],
    "Water & Resources": ["PHO", "CGW", "FIW"],
}


@retry_with_backoff(max_retries=3)
def _get_etf_volume_data(ticker: str) -> dict | None:
    """
    Fetch ETF price and volume data using yfinance.
    Returns dict with today's volume, 30-day avg volume, and price data.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed. Run: pip install yfinance")
        return None

    try:
        tkr = yf.Ticker(ticker)
        # Get 35 days of daily data to compute 30-day avg
        hist = tkr.history(period="35d", interval="1d")

        if hist.empty or len(hist) < 5:
            return None

        today_vol = int(hist["Volume"].iloc[-1])
        # 30-day average (exclude today)
        avg_vol_30d = float(hist["Volume"].iloc[:-1].tail(30).mean())

        today_close = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else today_close
        price_change_pct = ((today_close - prev_close) / prev_close) * 100 if prev_close else 0

        return {
            "ticker": ticker,
            "today_volume": today_vol,
            "avg_volume_30d": round(avg_vol_30d, 0),
            "volume_ratio": round(today_vol / avg_vol_30d, 3) if avg_vol_30d > 0 else 0,
            "today_close": round(today_close, 2),
            "price_change_pct": round(price_change_pct, 2),
        }
    except Exception as e:
        logger.debug(f"yfinance: failed to fetch {ticker}: {e}")
        return None


@retry_with_backoff(max_retries=3)
def _fetch_coingecko_trending() -> list[dict]:
    """
    Fetch trending coins from CoinGecko's free trending endpoint.
    Returns top trending coins with market data.
    """
    response = httpx.get(
        f"{COINGECKO_API}/search/trending",
        timeout=30,
        headers={"User-Agent": "zeitgeist/1.0"},
    )
    response.raise_for_status()
    data = response.json()

    coins = []
    for item in data.get("coins", []):
        coin = item.get("item", {})
        coins.append({
            "name": coin.get("name", ""),
            "symbol": coin.get("symbol", ""),
            "market_cap_rank": coin.get("market_cap_rank"),
            "score": coin.get("score", 0),  # CoinGecko trending rank (lower = more trending)
        })
    return coins


@retry_with_backoff(max_retries=3)
def _fetch_coingecko_market_data(coin_ids: list[str]) -> list[dict]:
    """
    Fetch detailed market data including volume for specific coins.
    """
    if not coin_ids:
        return []

    ids_str = ",".join(coin_ids[:50])
    response = httpx.get(
        f"{COINGECKO_API}/coins/markets",
        params={
            "vs_currency": "usd",
            "ids": ids_str,
            "order": "volume_desc",
            "per_page": 50,
            "page": 1,
            "sparkline": False,
            "price_change_percentage": "1h,24h,7d",
        },
        timeout=30,
        headers={"User-Agent": "zeitgeist/1.0"},
    )
    response.raise_for_status()
    return response.json()


@retry_with_backoff(max_retries=3)
def _fetch_coingecko_top_volume() -> list[dict]:
    """
    Fetch top coins by 24h volume from CoinGecko.
    """
    response = httpx.get(
        f"{COINGECKO_API}/coins/markets",
        params={
            "vs_currency": "usd",
            "order": "volume_desc",
            "per_page": 50,
            "page": 1,
            "sparkline": False,
            "price_change_percentage": "24h,7d",
        },
        timeout=30,
        headers={"User-Agent": "zeitgeist/1.0"},
    )
    response.raise_for_status()
    return response.json()


def collect() -> list[dict]:
    """
    Tracks unusual volume in theme ETFs and trending crypto assets.
    Returns list of {topic, raw_value, baseline_value, spike_score,
                     signal_source, signal_category, fired, tickers,
                     volume_ratio, asset_type}.
    Fires if volume > 2x 30-day average.
    signal_category: money
    """
    logger.info("Collecting financial markets signals...")
    results = []

    # --- ETF Theme Volume Signals ---
    theme_data: dict[str, dict] = {}

    for theme, tickers in THEME_ETFS.items():
        theme_vol_ratios = []
        theme_ticker_data = []

        for ticker in tickers:
            data = _get_etf_volume_data(ticker)
            if data and data["avg_volume_30d"] > 0:
                theme_vol_ratios.append(data["volume_ratio"])
                theme_ticker_data.append(data)
            time.sleep(0.5)  # yfinance rate limit courtesy

        if not theme_vol_ratios:
            continue

        # Use max volume ratio for the theme (most unusual single ETF)
        max_ratio = max(theme_vol_ratios)
        avg_ratio = sum(theme_vol_ratios) / len(theme_vol_ratios)

        # Find the top mover ETF
        top_etf = max(theme_ticker_data, key=lambda x: x["volume_ratio"])

        theme_data[theme] = {
            "max_volume_ratio": max_ratio,
            "avg_volume_ratio": avg_ratio,
            "top_etf": top_etf,
            "all_tickers": theme_ticker_data,
        }

    # Normalize ETF signals
    if theme_data:
        max_ratio_overall = max(v["max_volume_ratio"] for v in theme_data.values())

        for theme, data in theme_data.items():
            ratio = data["max_volume_ratio"]
            spike_score = ratio / max_ratio_overall if max_ratio_overall > 0 else 0.0
            top_etf = data["top_etf"]

            results.append({
                "topic": theme,
                "raw_value": round(ratio, 3),
                "baseline_value": 1.0,  # 1.0 = exactly average volume
                "spike_score": round(spike_score, 4),
                "signal_source": "etf_markets",
                "signal_category": "money",
                "fired": ratio >= 2.0,  # 2x 30-day avg volume
                "volume_ratio": round(ratio, 3),
                "asset_type": "etf",
                "tickers": [t["ticker"] for t in data["all_tickers"]],
                "top_ticker": top_etf["ticker"],
                "top_ticker_price_change_pct": top_etf["price_change_pct"],
            })

    logger.debug(f"Markets: {len(results)} ETF theme signals collected")

    # --- CoinGecko Crypto Signals ---
    try:
        top_volume_coins = _fetch_coingecko_top_volume()
        time.sleep(2)

        trending_coins = _fetch_coingecko_trending()
        trending_names = {c["name"].lower() for c in trending_coins}

        if top_volume_coins:
            # Baseline: median 24h volume among top 50 coins
            volumes = [c.get("total_volume", 0) for c in top_volume_coins if c.get("total_volume")]
            volumes.sort()
            median_vol = volumes[len(volumes) // 2] if volumes else 1

            for coin in top_volume_coins[:30]:
                name = coin.get("name", "")
                symbol = coin.get("symbol", "").upper()
                vol_24h = coin.get("total_volume", 0)
                price_change_24h = coin.get("price_change_percentage_24h", 0) or 0
                price_change_7d = coin.get("price_change_percentage_7d_in_currency", 0) or 0
                market_cap = coin.get("market_cap", 0)

                if median_vol == 0:
                    continue

                volume_ratio = vol_24h / median_vol
                is_trending = name.lower() in trending_names

                # Spike score: combination of volume ratio and trending status
                spike_score = volume_ratio / 10.0  # normalize assuming 10x median = max
                if is_trending:
                    spike_score = min(spike_score * 1.5, 1.0)

                results.append({
                    "topic": f"crypto:{symbol}",
                    "raw_value": round(vol_24h, 0),
                    "baseline_value": round(median_vol, 0),
                    "spike_score": round(min(spike_score, 1.0), 4),
                    "signal_source": "coingecko",
                    "signal_category": "money",
                    "fired": volume_ratio >= 2.0 or is_trending,
                    "volume_ratio": round(volume_ratio, 3),
                    "asset_type": "crypto",
                    "coin_name": name,
                    "price_change_24h_pct": round(price_change_24h, 2),
                    "price_change_7d_pct": round(price_change_7d, 2),
                    "is_trending": is_trending,
                    "market_cap": market_cap,
                })

        logger.debug(f"Markets: {len([r for r in results if r['asset_type'] == 'crypto'])} crypto signals collected")

    except Exception as e:
        logger.warning(f"CoinGecko: failed to fetch crypto data: {e}")

    fired_count = sum(1 for r in results if r["fired"])
    logger.info(f"Markets: {len(results)} total signals, {fired_count} fired (volume > 2x avg)")
    return results
