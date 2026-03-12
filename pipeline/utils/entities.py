"""
Topic normalization and entity resolution.
Maps variant spellings/phrases to canonical topic names.
"""
import re
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from loguru import logger

_model: SentenceTransformer | None = None
_topic_registry: dict[str, str] = {}  # variant → canonical
_topic_embeddings: dict[str, np.ndarray] = {}  # canonical → embedding


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
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

    # Semantic similarity check against existing canonicals
    if _topic_embeddings:
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

    # Register as new canonical
    _register_canonical(normalized)
    return normalized


def _register_canonical(topic: str):
    model = _get_model()
    embedding = model.encode([topic])[0]
    _topic_embeddings[topic] = embedding
    _topic_registry[topic] = topic


def batch_resolve(topics: list[str]) -> dict[str, str]:
    """Resolve a list of raw topics, return {raw: canonical} map."""
    return {t: resolve_topic(t) for t in topics}
