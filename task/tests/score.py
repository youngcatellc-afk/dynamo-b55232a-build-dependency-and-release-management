"""Turn the CTRF report into the one or zero the run is judged on.

The verdict is read out of the report rather than off pytest's exit status, and it
is a one only when every expected check was collected, ran and passed. A suite that
was skipped, truncated, never collected, or short-circuited by something left lying
about under /app scores zero, because none of those states puts the expected number
of passes in the report.
"""

from __future__ import annotations

import json
import os

REPORT = "/logs/verifier/ctrf.json"
REWARD = "/logs/verifier/reward.txt"
EXPECTED_CHECKS = 8


def earned() -> int:
    if os.environ.get("PYTEST_STATUS", "1") != "0":
        return 0
    try:
        with open(REPORT, "r", encoding="utf-8") as handle:
            summary = json.load(handle)["results"]["summary"]
    except (OSError, ValueError, KeyError):
        return 0
    ran = int(summary.get("tests", 0))
    passed = int(summary.get("passed", 0))
    spoiled = sum(
        int(summary.get(name, 0)) for name in ("failed", "skipped", "pending", "other")
    )
    if ran != EXPECTED_CHECKS or passed != EXPECTED_CHECKS or spoiled:
        return 0
    return 1


def main() -> None:
    reward = earned()
    os.makedirs(os.path.dirname(REWARD), exist_ok=True)
    with open(REWARD, "w", encoding="utf-8") as handle:
        handle.write("%d\n" % reward)
    print("reward %d" % reward)


if __name__ == "__main__":
    main()
