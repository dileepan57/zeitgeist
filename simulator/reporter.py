"""
Simulation report generator.
Produces a markdown summary of simulation run results.
"""
from datetime import datetime


def generate_report(run_results: dict) -> str:
    """
    Generate a markdown report from a run_all() result dict.
    """
    total = run_results.get("total", 0)
    passed = run_results.get("passed", 0)
    failed = run_results.get("failed", 0)
    pass_rate = run_results.get("pass_rate", 0)
    run_date = run_results.get("run_date", datetime.utcnow().date().isoformat())

    status_icon = "✅" if failed == 0 else "⚠️" if failed <= 2 else "❌"

    lines = [
        f"# Zeitgeist Simulator Report — {run_date}",
        "",
        f"## Summary {status_icon}",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Scenarios | {total} |",
        f"| Passed | {passed} |",
        f"| Failed | {failed} |",
        f"| Pass Rate | {pass_rate:.0%} |",
        "",
        "## Scenario Results",
        "",
    ]

    scenarios = run_results.get("scenarios", [])

    for s in scenarios:
        icon = "✅" if s["passed"] else "❌"
        lines.append(f"### {icon} `{s['scenario_name']}`")
        lines.append("")
        lines.append(f"*{s.get('description', '')}*")
        lines.append("")
        lines.append(f"- **Status**: {'PASS' if s['passed'] else 'FAIL'}")
        lines.append(f"- **Assertions checked**: {s.get('assertions_checked', 0)}")
        lines.append(f"- **Results returned**: {s.get('result_count', 'N/A')}")

        if s.get("failures"):
            lines.append("- **Failures**:")
            for f in s["failures"]:
                lines.append(f"  - {f}")

        if s.get("exception"):
            lines.append(f"- **Exception**: `{s['exception']}`")

        if s.get("topic_result"):
            tr = s["topic_result"]
            lines.append("- **Key scores**:")
            for key in ["opportunity_score", "independence_score", "timeline_position",
                        "echo_detected", "frustration_score", "lead_indicator_ratio"]:
                if key in tr:
                    lines.append(f"  - `{key}`: {tr[key]}")

        lines.append("")

    if failed > 0:
        lines.append("## Action Required")
        lines.append("")
        lines.append("The following scenarios are failing and need investigation:")
        for s in scenarios:
            if not s["passed"]:
                lines.append(f"- **{s['scenario_name']}**: {'; '.join(s.get('failures', ['unknown']))}")
        lines.append("")

    return "\n".join(lines)
