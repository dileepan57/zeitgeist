"""
Topic normalization and entity resolution.
Maps variant spellings/phrases to canonical topic names.

Note: Semantic similarity merging (sentence-transformers) is disabled on Windows
due to torch DLL compatibility issues. Topics are resolved by exact string match only.
Enable by setting ZEITGEIST_SEMANTIC_MERGE=1 in environment once torch is working.
"""
import os
import re
from loguru import logger

_model = None
_topic_registry: dict[str, str] = {}  # variant → canonical
_topic_embeddings: dict = {}  # canonical → embedding

SEMANTIC_MERGE_ENABLED = os.environ.get("ZEITGEIST_SEMANTIC_MERGE", "0") == "1"


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading sentence transformer model...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def normalize(topic: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    return re.sub(r"\s+", " ", topic.strip().lower())


def resolve_topic(raw_topic: str, threshold: float = 0.85) -> str:
    """
    Given a raw topic string, return the canonical form.
    If similar to an existing canonical topic (cosine > threshold), merge.
    Otherwise, register as new canonical topic.
    """
    normalized = normalize(raw_topic)

    # Exact match in registry
    if normalized in _topic_registry:
        return _topic_registry[normalized]

    # Semantic similarity check (only if enabled and model available)
    if SEMANTIC_MERGE_ENABLED and _topic_embeddings:
        try:
            import numpy as np
            from sklearn.metrics.pairwise import cosine_similarity
            model = _get_model()
            new_embedding = model.encode([normalized])[0]
            canonicals = list(_topic_embeddings.keys())
            existing_embeddings = np.array([_topic_embeddings[c] for c in canonicals])
            similarities = cosine_similarity([new_embedding], existing_embeddings)[0]
            best_idx = int(np.argmax(similarities))
            if similarities[best_idx] >= threshold:
                canonical = canonicals[best_idx]
                _topic_registry[normalized] = canonical
                logger.debug(f"Merged '{normalized}' → '{canonical}' (sim={similarities[best_idx]:.2f})")
                return canonical
        except Exception as e:
            logger.warning(f"Semantic merge failed, falling back to exact match: {e}")

    # Register as new canonical (exact match only)
    _register_canonical(normalized)
    return normalized


def _register_canonical(topic: str):
    if SEMANTIC_MERGE_ENABLED:
        try:
            import numpy as np
            model = _get_model()
            embedding = model.encode([topic])[0]
            _topic_embeddings[topic] = embedding
        except Exception as e:
            logger.warning(f"Could not compute embedding for '{topic}': {e}")
    _topic_registry[topic] = topic


def batch_resolve(topics: list[str]) -> dict[str, str]:
    """Resolve a list of raw topics, return {raw: canonical} map."""
    return {t: resolve_topic(t) for t in topics}
