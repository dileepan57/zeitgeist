"""
Pipeline entrypoint.
Orchestrates: collect → score → synthesize → store.
Run directly or triggered by GitHub Actions.
"""
import sys
from datetime import date
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

from pipeline.utils import db
from pipeline.scoring import engine as scoring_engine
from pipeline.synthesis import claude as synthesis
from pipeline.reflection.knowledge import get_latest_knowledge

# Phase 1 collectors (core)
from pipeline.collectors import wikipedia, reddit, google_trends, gdelt, github_trending

# Phase 2 collectors (added incrementally)
PHASE2_COLLECTORS = []
try:
    from pipeline.collectors import youtube
    PHASE2_COLLECTORS.append(youtube)
except ImportError:
    pass
try:
    from pipeline.collectors import arxiv
    PHASE2_COLLECTORS.append(arxiv)
except ImportError:
    pass
try:
    from pipeline.collectors import stackoverflow
    PHASE2_COLLECTORS.append(stackoverflow)
except ImportError:
    pass
try:
    from pipeline.collectors import markets
    PHASE2_COLLECTORS.append(markets)
except ImportError:
    pass
try:
    from pipeline.collectors import job_postings
    PHASE2_COLLECTORS.append(job_postings)
except ImportError:
    pass
try:
    from pipeline.collectors import uspto
    PHASE2_COLLECTORS.append(uspto)
except ImportError:
    pass
try:
    from pipeline.collectors import sbir
    PHASE2_COLLECTORS.append(sbir)
except ImportError:
    pass
try:
    from pipeline.collectors import producthunt
    PHASE2_COLLECTORS.append(producthunt)
except ImportError:
    pass
try:
    from pipeline.collectors import kickstarter
    PHASE2_COLLECTORS.append(kickstarter)
except ImportError:
    pass
try:
    from pipeline.collectors import app_store
    PHASE2_COLLECTORS.append(app_store)
except ImportError:
    pass
try:
    from pipeline.collectors import amazon_movers
    PHASE2_COLLECTORS.append(amazon_movers)
except ImportError:
    pass
try:
    from pipeline.collectors import discord
    PHASE2_COLLECTORS.append(discord)
except ImportError:
    pass
try:
    from pipeline.collectors import substack
    PHASE2_COLLECTORS.append(substack)
except ImportError:
    pass
try:
    from pipeline.collectors import federal_register
    PHASE2_COLLECTORS.append(federal_register)
except ImportError:
    pass
try:
    from pipeline.collectors import itunes
    PHASE2_COLLECTORS.append(itunes)
except ImportError:
    pass
try:
    from pipeline.collectors import crunchbase
    PHASE2_COLLECTORS.append(crunchbase)
except ImportError:
    pass
try:
    from pipeline.collectors import xiaohongshu
    PHASE2_COLLECTORS.append(xiaohongshu)
except ImportError:
    pass

CORE_COLLECTORS = [wikipedia, reddit, google_trends, gdelt, github_trending]
TOP_N_FOR_SYNTHESIS = 20  # Run Claude on top N topics only (cost management)


def run(run_date: date | None = None, dry_run: bool = False):
    today = run_date or date.today()
    logger.info(f"=== Zeitgeist Pipeline Starting: {today} ===")

    # Create daily run record
    run_record = db.insert("daily_runs", {
        "run_date": today.isoformat(),
        "status": "running",
    })
    run_id = run_record[0]["id"]
    logger.info(f"Run ID: {run_id}")

    try:
        # ── Step 1: Collect ─────────────────────────────
        all_signals: list[dict] = []
        all_collectors = CORE_COLLECTORS + PHASE2_COLLECTORS

        for collector in all_collectors:
            logger.info(f"Running collector: {collector.__name__.split('.')[-1]}")
            try:
                signals = collector.collect()
                all_signals.extend(signals)
                logger.info(f"  → {len(signals)} signals")
            except Exception as e:
                logger.error(f"Collector {collector.__name__} failed: {e}")

        logger.info(f"Total raw signals collected: {len(all_signals)}")

        if not all_signals:
            logger.error("No signals collected — aborting")
            db.update("daily_runs", {"id": run_id}, {"status": "failed"})
            return

        # ── Step 2: Score ────────────────────────────────
        logger.info("Running scoring engine...")
        scored_topics = scoring_engine.run(all_signals)
        logger.info(f"Scored {len(scored_topics)} unique topics")

        # ── Step 3: Store topics and scores ─────────────
        if not dry_run:
            _store_results(run_id, scored_topics)

        # ── Step 4: Synthesize top topics ───────────────
        institutional_knowledge = get_latest_knowledge()
        user_thesis = _get_user_thesis()

        top_topics = [t for t in scored_topics if t["opportunity_score"] > 0.1][:TOP_N_FOR_SYNTHESIS]
        logger.info(f"Running Claude synthesis on top {len(top_topics)} topics...")

        for topic_data in top_topics:
            topic_name = topic_data["topic"]
            logger.info(f"  Synthesizing: {topic_name}")
            try:
                gap = synthesis.analyze_gap(topic_name, topic_data, user_thesis)
                brief = synthesis.generate_opportunity_brief(
                    topic_name, topic_data, gap, institutional_knowledge, user_thesis
                )
                app_fit = synthesis.assess_app_fit(topic_name, brief, gap)

                if not dry_run:
                    _store_synthesis(run_id, topic_data, gap, brief, app_fit)

            except Exception as e:
                logger.error(f"Synthesis failed for {topic_name}: {e}")

        # ── Step 5: Finalize ─────────────────────────────
        if not dry_run:
            db.update("daily_runs", {"id": run_id}, {
                "status": "complete",
                "topics_scored": len(scored_topics),
            })

        logger.info(f"=== Pipeline Complete: {len(scored_topics)} topics scored, {len(top_topics)} synthesized ===")
        logger.info(f"Top 5 opportunities:")
        for t in scored_topics[:5]:
            logger.info(f"  [{t['opportunity_score']:.3f}] {t['topic']} — {t['timeline_position']}")

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        db.update("daily_runs", {"id": run_id}, {"status": "failed"})
        raise


def _store_results(run_id: str, scored_topics: list[dict]):
    """Store topics, signals, and scores in Supabase."""
    for topic_data in scored_topics:
        topic_name = topic_data["topic"]

        # Upsert topic
        existing = db.select("topics", filters={"name": topic_name})
        if existing:
            topic_id = existing[0]["id"]
        else:
            topic_record = db.insert("topics", {
                "name": topic_name,
                "canonical_name": topic_name,
                "first_seen": date.today().isoformat(),
            })
            topic_id = topic_record[0]["id"]

        # Insert signals
        for signal in topic_data.get("signals", []):
            db.insert("topic_signals", {
                "run_id": run_id,
                "topic_id": topic_id,
                "signal_source": signal.get("signal_source"),
                "signal_category": signal.get("signal_category"),
                "raw_value": signal.get("raw_value"),
                "baseline_value": signal.get("baseline_value"),
                "spike_score": signal.get("spike_score"),
                "fired": signal.get("fired", False),
            })

        # Insert score
        db.insert("topic_scores", {
            "run_id": run_id,
            "topic_id": topic_id,
            "independence_score": topic_data.get("independence_score"),
            "velocity_score": topic_data.get("lead_indicator_ratio"),
            "frustration_score": topic_data.get("frustration_score"),
            "supply_gap_score": topic_data.get("supply_gap_score"),
            "demand_score": topic_data.get("demand_score"),
            "opportunity_score": topic_data.get("opportunity_score"),
            "timeline_position": topic_data.get("timeline_position"),
            "vocabulary_fragmentation": topic_data.get("vocabulary_fragmentation"),
            "lead_indicator_ratio": topic_data.get("lead_indicator_ratio"),
            "categories_fired": topic_data.get("categories_fired", []),
            "sources_fired": topic_data.get("sources_fired", []),
        })

        # Store as recommendation
        db.insert("recommendations", {
            "run_id": run_id,
            "topic_id": topic_id,
            "recommendation_date": date.today().isoformat(),
            "confidence_score": topic_data.get("opportunity_score"),
            "opportunity_brief": f"Score: {topic_data.get('opportunity_score', 0):.3f}, Position: {topic_data.get('timeline_position')}",
        })


def _store_synthesis(run_id: str, topic_data: dict, gap: str, brief: str, app_fit: dict):
    """Store Claude synthesis results."""
    # Get topic_id
    existing = db.select("topics", filters={"name": topic_data["topic"]})
    if not existing:
        return
    topic_id = existing[0]["id"]

    db.insert("topic_syntheses", {
        "run_id": run_id,
        "topic_id": topic_id,
        "gap_analysis": gap,
        "opportunity_brief": brief,
        "app_fit_score": app_fit.get("overall_fit"),
        "app_concept": app_fit.get("app_concept"),
    })


def _get_user_thesis() -> dict | None:
    rows = db.select("user_thesis", limit=1)
    return rows[0] if rows else None


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        logger.info("DRY RUN mode — no data will be stored")
    run(dry_run=dry_run)
