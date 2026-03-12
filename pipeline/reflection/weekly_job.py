"""
Weekly reflection job.
Runs every Sunday. Orchestrates: calibrate → detect misses → generate knowledge.
"""
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

from pipeline.reflection.calibration import calibrate_signals
from pipeline.reflection.knowledge import generate_knowledge_brief


def run():
    logger.info("=== Weekly Reflection Starting ===")

    logger.info("Step 1: Calibrating signal performance...")
    calibrate_signals()

    logger.info("Step 2: Generating institutional knowledge brief...")
    brief = generate_knowledge_brief()
    if brief:
        logger.info(f"Knowledge brief generated ({len(brief)} chars)")
    else:
        logger.info("Insufficient data for knowledge brief yet")

    logger.info("=== Weekly Reflection Complete ===")


if __name__ == "__main__":
    run()
