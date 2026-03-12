"""
App Opportunity Classifier.
Evaluates scored topics for mobile app buildability.
Augments topic_syntheses with app_fit_score and app_concept.
"""
from loguru import logger
from pipeline.synthesis.claude import assess_app_fit
from pipeline.utils import db


APP_FIT_THRESHOLD = 0.5  # Topics above this get surfaced in daily session


def classify_app_opportunities(scored_topics: list[dict], run_id: str) -> list[dict]:
    """
    Given list of scored topics, identify which ones are mobile app opportunities.
    Updates topic_syntheses table with app_fit_score.
    Returns filtered list of high-fit opportunities.
    """
    app_opportunities = []

    for topic_data in scored_topics:
        # Only evaluate topics with meaningful opportunity scores
        if topic_data.get("opportunity_score", 0) < 0.15:
            continue

        topic = topic_data["topic"]
        topic_id = _get_topic_id(topic)
        if not topic_id:
            continue

        # Get existing synthesis
        syntheses = db.select("topic_syntheses", filters={"topic_id": topic_id})
        if not syntheses:
            continue

        synthesis = syntheses[0]
        gap = synthesis.get("gap_analysis", "")
        brief = synthesis.get("opportunity_brief", "")

        if not gap or not brief:
            continue

        try:
            fit = assess_app_fit(topic, brief, gap)
            fit_score = fit.get("overall_fit", 0)

            # Update synthesis with app fit
            db.update("topic_syntheses", {"id": synthesis["id"]}, {
                "app_fit_score": fit_score,
                "app_concept": fit.get("app_concept"),
            })

            if fit_score >= APP_FIT_THRESHOLD:
                app_opportunities.append({
                    **topic_data,
                    "app_fit_score": fit_score,
                    "app_concept": fit.get("app_concept"),
                    "app_fit_breakdown": fit,
                    "build_recommendation": fit.get("build_recommendation"),
                })
                logger.info(f"App opportunity: {topic} (fit={fit_score:.2f}, rec={fit.get('build_recommendation')})")

        except Exception as e:
            logger.warning(f"App classification failed for {topic}: {e}")

    app_opportunities.sort(key=lambda x: x["app_fit_score"], reverse=True)
    logger.info(f"App classifier: {len(app_opportunities)} app opportunities identified")
    return app_opportunities


def _get_topic_id(topic_name: str) -> str | None:
    rows = db.select("topics", filters={"name": topic_name})
    return rows[0]["id"] if rows else None
