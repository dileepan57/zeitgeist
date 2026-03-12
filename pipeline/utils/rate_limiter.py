import time
from functools import wraps
from loguru import logger


def rate_limited(calls_per_minute: int = 10):
    """Decorator that enforces a per-function rate limit."""
    min_interval = 60.0 / calls_per_minute
    last_called: dict[str, float] = {}

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = func.__name__
            now = time.time()
            elapsed = now - last_called.get(key, 0)
            if elapsed < min_interval:
                sleep_time = min_interval - elapsed
                logger.debug(f"Rate limiting {key}: sleeping {sleep_time:.2f}s")
                time.sleep(sleep_time)
            last_called[key] = time.time()
            return func(*args, **kwargs)
        return wrapper
    return decorator


def retry_with_backoff(max_retries: int = 3, base_delay: float = 2.0):
    """Decorator for exponential backoff retry."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"{func.__name__} failed after {max_retries} attempts: {e}")
                        raise
                    delay = base_delay ** (attempt + 1)
                    logger.warning(f"{func.__name__} attempt {attempt + 1} failed: {e}. Retrying in {delay}s")
                    time.sleep(delay)
        return wrapper
    return decorator
