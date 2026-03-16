"""
Per-scenario expected outcome assertions with tolerances.
Each entry defines what the scored topic should look like after running
the scenario through the scoring engine.
"""

# Each field in an assertion dict specifies a constraint:
#   {"eq": value}       — exact equality
#   {"min": value}      — result >= value
#   {"max": value}      — result <= value
#   {"in": [v1, v2]}    — result in list
#   {"true": True}      — result is truthy
#   {"false": True}     — result is falsy

EXPECTED_OUTCOMES: dict[str, dict] = {

    "media_cascade": {
        # Echo should be detected: only 1 adjusted category, not 3
        "echo_detected": {"eq": True},
        "independence_score": {"max": 0.25},  # ≤ 1/6 after echo removal
    },

    "early_emerging": {
        "timeline_position": {"eq": "EMERGING"},
        "lead_indicator_ratio": {"min": 0.8},  # builder signals dominate
        # Should not be suppressed (novel topic, strong builder signal)
        "opportunity_score": {"min": 0.01},
    },

    "full_convergence": {
        "independence_score": {"min": 0.95},  # All 6 categories = 1.0
        "timeline_position": {"in": ["PEAKING", "MAINSTREAM"]},
        "opportunity_score": {"min": 0.2},
    },

    "evergreen_suppressed": {
        # Evergreen + low spike → suppressed
        "opportunity_score": {"eq": 0.0},
    },

    "evergreen_strong": {
        # Strong spike on evergreen → not suppressed
        "opportunity_score": {"min": 0.01},
    },

    "high_frustration": {
        "frustration_score": {"min": 0.3},
        "actionability_score": {"min": 0.01},  # Must be > 0
    },

    "vocab_fragmentation": {
        # Tested via the vocabulary module directly (30 unique variants)
        # The engine result may not have fragmentation_score unless all topics are passed
        # We assert the vocabulary module independently
        "opportunity_score": {"min": 0.0},  # Should not crash
    },

    "zero_signals": {
        # No result should be returned
        "_result_count": {"eq": 0},
    },

    "crystallizing": {
        "timeline_position": {"eq": "CRYSTALLIZING"},
        "lead_indicator_ratio": {"min": 0.5},
    },

    "geographic_lead": {
        # XHS signal should produce a valid result, not suppressed
        "opportunity_score": {"min": 0.0},
        # Should not crash on geographic_lead_months field
        "_no_exception": {"eq": True},
    },
}


def check_assertion(field: str, constraint: dict, actual_value) -> tuple[bool, str]:
    """
    Check a single assertion constraint against an actual value.
    Returns (passed, failure_reason).
    """
    if "eq" in constraint:
        expected = constraint["eq"]
        if actual_value != expected:
            return False, f"{field}: expected {expected!r}, got {actual_value!r}"

    if "min" in constraint:
        if actual_value is None or actual_value < constraint["min"]:
            return False, f"{field}: expected >= {constraint['min']}, got {actual_value!r}"

    if "max" in constraint:
        if actual_value is None or actual_value > constraint["max"]:
            return False, f"{field}: expected <= {constraint['max']}, got {actual_value!r}"

    if "in" in constraint:
        if actual_value not in constraint["in"]:
            return False, f"{field}: expected one of {constraint['in']}, got {actual_value!r}"

    if "true" in constraint:
        if not actual_value:
            return False, f"{field}: expected truthy, got {actual_value!r}"

    if "false" in constraint:
        if actual_value:
            return False, f"{field}: expected falsy, got {actual_value!r}"

    return True, ""


def evaluate_scenario(scenario_name: str, results: list[dict], topic: str | None) -> dict:
    """
    Evaluate whether a scenario's results match expected outcomes.

    Returns:
    {
        "passed": bool,
        "failures": list[str],
        "assertions_checked": int,
        "topic_result": dict | None,
    }
    """
    expected = EXPECTED_OUTCOMES.get(scenario_name)
    if not expected:
        return {
            "passed": True,
            "failures": [],
            "assertions_checked": 0,
            "topic_result": None,
            "note": "No assertions defined for this scenario",
        }

    failures = []
    assertions_checked = 0

    # Special meta-assertion: result count
    if "_result_count" in expected:
        assertions_checked += 1
        count_constraint = expected["_result_count"]
        passed, reason = check_assertion("_result_count", count_constraint, len(results))
        if not passed:
            failures.append(reason)

    # Find the specific topic result
    topic_result = None
    if topic and results:
        for r in results:
            if r.get("topic") == topic:
                topic_result = r
                break
        if topic_result is None and results:
            topic_result = results[0]  # Use first result if topic not found

    # Check field-level assertions
    for field, constraint in expected.items():
        if field.startswith("_"):
            continue  # Already handled meta-assertions

        assertions_checked += 1
        if topic_result is None:
            if "_result_count" not in expected or expected["_result_count"].get("eq", 1) != 0:
                failures.append(f"{field}: no result found for topic '{topic}'")
            continue

        actual = topic_result.get(field)
        passed, reason = check_assertion(field, constraint, actual)
        if not passed:
            failures.append(reason)

    return {
        "passed": len(failures) == 0,
        "failures": failures,
        "assertions_checked": assertions_checked,
        "topic_result": topic_result,
    }
