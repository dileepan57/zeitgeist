"""
Simulator for pressure-testing the Zeitgeist recommender system.
Runs controlled synthetic signal scenarios through the real scoring engine
and asserts expected behaviors.
"""
from simulator.runner import run_all, run_scenario
from simulator.scenarios import get_all_scenarios, SCENARIOS

__all__ = ["run_all", "run_scenario", "get_all_scenarios", "SCENARIOS"]
