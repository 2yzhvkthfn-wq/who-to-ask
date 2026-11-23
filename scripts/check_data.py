"""Check that the fake company data is complete and consistent. Free: no OpenAI calls.

Since M4 the data is read from MongoDB. After a change to a file of the data folder, run the seed first:
    python -m scripts.seed_mongodb
"""

import sys

from checks import DatabaseChecker, DataChecker, ScenarioChecker
from utils.logging import logger


def main() -> None:
    """Run the database check, the data checks, and the scenario checks, and log every problem found."""
    # 1) MongoDB holds what the files hold. If not, the checks below would read old data, so it stops here
    database_result = DatabaseChecker().check()
    for problem in database_result["problems"]:
        logger.error(problem)
    if database_result["problems"]:
        logger.error("Data NOT checked: MongoDB is not ready")
        sys.exit(1)

    # 2) The data itself: fields, ids, dates, and who was at the company when
    data_result = DataChecker().check()
    for name, count in data_result["counts"].items():
        logger.info(f"{name}: {count}")

    # 3) The demo scenarios: does the data really make each one true?
    scenario_result = ScenarioChecker().check()

    # 4) List the problems, and stop with an error code if there are any
    problems = data_result["problems"] + scenario_result["problems"]
    for problem in problems:
        logger.error(problem)
    if problems:
        logger.error(f"Data NOT OK: {len(problems)} problem(s)")
        sys.exit(1)
    logger.info("Data OK, and every scenario exists in the data")


if __name__ == "__main__":
    main()
