"""Write data/scenario_evidence.md: for each scenario, who has which evidence and why they rank where they do."""

import sys

from checks import ScenarioChecker
from config.settings import PROJECT_ROOT, settings
from utils.logging import logger

REPORT_NAME = "scenario_evidence.md"


def main() -> None:
    """Build the report from the data and save it next to the data."""
    # 1) Build the report. It is only worth saving if the scenarios hold
    result = ScenarioChecker().check()
    for problem in result["problems"]:
        logger.error(problem)
    if result["problems"]:
        logger.error("The report was NOT saved: fix the problems above first")
        sys.exit(1)

    # 2) Save it
    path = PROJECT_ROOT / settings.DATA_DIR / REPORT_NAME
    try:
        path.write_text(result["report"], encoding="utf-8", newline="\n")
    except OSError as e:
        logger.error(f"Could not write {REPORT_NAME}: {e}")
        raise
    logger.info(f"Saved {settings.DATA_DIR / REPORT_NAME}")


if __name__ == "__main__":
    main()
